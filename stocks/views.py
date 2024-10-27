import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode
import requests
from rest_framework.exceptions import APIException

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status

from stocks.exceptions import (
    ApiRequestFailureException,
    ApiResponseParseFailureException,
    HttpStatusCodeFailureException,
    DatabaseSaveFailureException, StockSearchFailureException, StockNotFoundException,
    WeeklyRecommendationNotFoundException, WeeklyRecommendationStockSaveException,
    WeeklyRecommendationStockDeleteException,
)
from stocks.models import Stock, WeeklyRecommendation, WeeklyRecommendationStock, DailyStockData
from stocks.serializers import StockSerializer
from django.conf import settings

logger = logging.getLogger(__name__)


# 주식 이름으로 검색 (admin 용)
class StockSearchView(GenericAPIView):
    serializer_class = StockSerializer

    def get(self, request):
        query = request.GET.get('query')

        if not query:
            return Response({"error": "쿼리 문이 있어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        stocks = self.search_stocks(query)
        stock_response_serializer = self.get_serializer(stocks, many=True)
        logger.info(stock_response_serializer.data)

        return Response(stock_response_serializer.data, status=status.HTTP_200_OK)

    def search_stocks(self, query):
        try:
            return Stock.objects.filter(itms_name__icontains=query)
        except Exception:
            raise StockSearchFailureException


# 공공 데이터 포탈에서 한국 주식 정보 받아오기 (admin 용)
class FetchAllStocksInfoView(GenericAPIView):
    serializer_class = StockSerializer

    def post(self, request):
        try:
            self.fetch_and_save_all_stocks_info()
            return Response({"message": "모든 주식 기본 정보가 저장됐습니다."}, status=status.HTTP_200_OK)
        except APIException as e:
            logger.error(f"error : {str(e)}")
            raise e

    def fetch_and_save_all_stocks_info(self):
        today = datetime.now() - timedelta(days=1)
        yesterday = today - timedelta(days=2)
        formatted_today = today.strftime("%Y%m%d")
        formatted_yesterday = yesterday.strftime("%Y%m%d")
        page_no = 1
        num_of_rows = 100

        while True:
            service_key = settings.PUBLIC_DATA_SECRET_KEY
            params = {
                "serviceKey": service_key,
                "resultType": "json",
                "beginBasDt": formatted_yesterday,
                "endBasDt": formatted_today,
                "pageNo": page_no,
                "numOfRows": num_of_rows
            }
            query_string = urlencode(params, safe='=')
            url = f"http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo?{query_string}"

            try:
                response = requests.get(url, verify=False)
                if response.status_code != 200:
                    raise HttpStatusCodeFailureException()
            except requests.exceptions.RequestException as e:
                raise ApiRequestFailureException(f"API 요청 실패: {str(e)}")

            try:
                data = response.json()
                items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

                if not items:
                    break  # 더 이상 데이터가 없으면 루프 종료

                self.save_stocks_from_api(items)
                page_no += 1
            except Exception:
                raise ApiResponseParseFailureException()

    def save_stocks_from_api(self, items):
        for item in items:
            isin_code = item.get('isinCd')
            srtn_code = item.get('srtnCd')
            itms_name = item.get('itmsNm')
            mrkt_cls = item.get('mrktCtg', "Unknown")

            if not Stock.objects.filter(isin_code=isin_code).exists():
                try:
                    Stock.objects.create(
                        isin_code=isin_code,
                        srtn_code=srtn_code,
                        itms_name=itms_name,
                        mrkt_cls=mrkt_cls
                    )
                except Exception:
                    raise DatabaseSaveFailureException()


# 주차별 추천 주식 불러오기
class WeeklyRecommendationStocksView(GenericAPIView):
    serializer_class = StockSerializer

    def get(self, request):
        # URL 파라미터로부터 시작 날짜 받기
        start_date_str = request.GET.get('startDate')

        if not start_date_str:
            return Response({"error": "시작 날짜를 제공해야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 받은 날짜 문자열을 datetime 객체로 변환
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "날짜 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식이어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 주차별 주식 가져오기
        weekly_stocks = self.get_weekly_stocks(start_date)

        # 주식 데이터를 직렬화
        serializer = self.get_serializer(weekly_stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_weekly_stocks(self, start_date):
        try:
            weekly_recommendation = WeeklyRecommendation.objects.get(start_date=start_date)
        except Exception:
            raise WeeklyRecommendationNotFoundException()

        try:
            weekly_stocks = WeeklyRecommendationStock.objects.filter(weekly_recommendation=weekly_recommendation).select_related('stock')
            return [stock_relation.stock for stock_relation in weekly_stocks]
        except Exception:
            logger.error(f"error : {str(weekly_recommendation)}")
            raise StockNotFoundException()


# 주차별 추천 리스트에 주식에 추가
class AddStockToWeeklyView(GenericAPIView):

    def post(self, request, stock_id):
        # URL 파라미터로부터 시작 날짜 받기 (request.GET 사용)
        start_date_str = request.GET.get('startDate')

        if not start_date_str:
            return Response({"error": "시작 날짜를 제공해야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 받은 날짜 문자열을 datetime 객체로 변환
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "날짜 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식이어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 주차별 주식 추가 로직
        self.add_stock_to_weekly(start_date, stock_id)

        return Response({"message": "주식이 주차별 추천 목록에 추가되었습니다."}, status=status.HTTP_200_OK)

    def delete(self, request, stock_id):
        # URL 파라미터로부터 시작 날짜 받기 (request.GET 사용)
        start_date_str = request.GET.get('startDate')

        if not start_date_str:
            return Response({"error": "시작 날짜를 제공해야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 받은 날짜 문자열을 datetime 객체로 변환
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "날짜 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식이어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 주차별 주식 삭제 로직
        self.delete_stock_from_weekly(start_date, stock_id)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def add_stock_to_weekly(self, start_date, stock_id):
        try:
            stock = Stock.objects.get(id=stock_id)
        except Exception:
            raise StockNotFoundException()

        try:
            weekly_recommendation, created = WeeklyRecommendation.objects.get_or_create(
                start_date=start_date,
                defaults={'end_date': start_date + timedelta(days=6)}
            )
            weekly_recommendation_stock = WeeklyRecommendationStock(
                weekly_recommendation=weekly_recommendation,
                stock=stock
            )
            weekly_recommendation_stock.save()
        except Exception:
            raise WeeklyRecommendationStockSaveException()

    def delete_stock_from_weekly(self, start_date, stock_id):
        try:
            stock = Stock.objects.get(id=stock_id)
        except Exception:
            logger.error(f"error : {str(stock_id)}")
            raise StockNotFoundException()

        try:
            weekly_recommendation = WeeklyRecommendation.objects.get(start_date=start_date)
            weekly_recommendation_stock = WeeklyRecommendationStock.objects.get(weekly_recommendation=weekly_recommendation, stock=stock)
            weekly_recommendation_stock.delete()
        except Exception:
            logger.error(f"error : {str(weekly_recommendation)}")
            raise WeeklyRecommendationStockDeleteException()


class FetchWeeklyStockDailyDataView(GenericAPIView):

    def post(self, request):
        stock_requests = request.data

        if len(stock_requests) != 10:
            return Response({"error": "10개의 주식을 선택해야 데이터를 저장할 수 있습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            for stock_request in stock_requests:
                isin_cd = stock_request.get('isinCd')

                if not (isin_cd):
                    return Response({"error": "주식 코드가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

                # 주식 데이터를 가져와 저장하는 함수 호출
                self.fetch_and_save_stock_data_by_code_and_date(isin_cd)

            return Response({"message": "주식 데이터가 성공적으로 저장되었습니다."}, status=status.HTTP_200_OK)

        except (ApiRequestFailureException, ApiResponseParseFailureException, DatabaseSaveFailureException) as e:
            logger.error(f"주식 데이터를 저장하는 중 오류 발생: {str(e)}")
            return Response({"error": "주식 데이터를 저장하는 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_and_save_stock_data_by_code_and_date(self, isin_cd):
        """
        공공 데이터 포털 API에서 주식 데이터를 가져와 저장하는 로직
        """
        url_template = "http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"

        # 종료 날짜는 현재 날짜로, 시작 날짜는 현재 날짜로부터 1년 전으로 설정
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        formatted_start_date = start_date.strftime("%Y%m%d")  # 1년 전 날짜
        formatted_end_date = end_date.strftime("%Y%m%d")  # 현재 날짜

        page_no = 1
        num_of_rows = 100

        while True:
            params = {
                "serviceKey": settings.PUBLIC_DATA_SECRET_KEY,
                "resultType": "json",
                "beginBasDt": formatted_start_date,
                "endBasDt": formatted_end_date,
                "isinCd": isin_cd,
                "pageNo": page_no,
                "numOfRows": num_of_rows
            }
            response = requests.get(url_template, params=params)

            if response.status_code != 200:
                raise HttpStatusCodeFailureException()

            data = response.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

            if not items:
                break  # 데이터가 더 이상 없을 때 루프 종료

            # 주식 데이터 저장 로직
            self.save_stock_data(isin_cd, items)
            page_no += 1

    def save_stock_data(self, isin_cd, items):
        """
        API로 가져온 데이터를 데이터베이스에 저장하는 로직
        """
        try:
            stock = Stock.objects.get(isin_code=isin_cd)
        except Stock.DoesNotExist:
            raise StockNotFoundException(f"ISIN 코드 {isin_cd}에 해당하는 주식을 찾을 수 없습니다.")

        for item in items:
            bas_dt = datetime.strptime(item.get('basDt'), '%Y%m%d').date()  # 기준일자
            clpr = item.get('clpr')  # 종가
            hipr = item.get('hipr')  # 고가
            lopr = item.get('lopr')  # 저가
            mkp = item.get('mkp')  # 시가
            vs = item.get('vs')  # 대비
            flt_rt = item.get('fltRt')  # 등락률
            trqu = item.get('trqu')  # 거래량
            tr_prc = item.get('trPrc')  # 거래대금
            lstg_st_cnt = item.get('lstgStCnt')  # 상장주식수
            mrkt_tot_amt = item.get('mrktTotAmt')  # 시가총액

            # 기존 데이터 중복 삽입 방지
            if not DailyStockData.objects.filter(stock=stock, bas_dt=bas_dt).exists():
                # 데이터 저장
                try:
                    DailyStockData.objects.create(
                        stock=stock,
                        bas_dt=bas_dt,
                        clpr=clpr,
                        hipr=hipr,
                        lopr=lopr,
                        mkp=mkp,
                        vs=vs,
                        flt_rt=flt_rt,
                        trqu=trqu,
                        tr_prc=tr_prc,
                        lstg_st_cnt=lstg_st_cnt,
                        mrkt_tot_amt=mrkt_tot_amt
                    )
                    logger.info(f"ISIN 코드 {isin_cd}의 주식 데이터가 {bas_dt}일자로 저장되었습니다.")
                except Exception as e:
                    logger.error(f"데이터베이스 저장 실패: {str(e)}")
                    raise DatabaseSaveFailureException()

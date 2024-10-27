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
    WeeklyStockRecommendationException, WeeklyStockRecommendationRetrieveFailureException
)
from stocks.models import Stock, WeeklyStockRecommendation, WeeklyStockRecommendationStock
from stocks.serializers import StockSerializer, StockSearchResponseSerializer
from django.conf import settings

logger = logging.getLogger(__name__)


# 주식 이름으로 검색 (admin 용)
class StockSearchView(GenericAPIView):
    serializer_class = StockSearchResponseSerializer

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
class WeeklyStocksView(GenericAPIView):
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
        # 해당 시작 날짜의 주차별 주식 추천을 가져옴
        try:
            weekly_stock_recommendation = WeeklyStockRecommendation.objects.filter(start_date=start_date)
        except Exception:
            raise WeeklyStockRecommendationRetrieveFailureException()


# 주차별 추천 10개 주식에 추가
class AddWeeklyStocksView(GenericAPIView):

    def post(self, request, stock_id):
        start_date_str = request.data.get('startDate')

        if not start_date_str:
            return Response({"error": "startDate가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = self.parse_date(start_date_str)
        except ValueError:
            return Response({"error": "날짜 형식이 잘못되었습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            self.add_stock_to_weekly(start_date, stock_id)
            return Response({"message": "주식이 주간 추천 목록에 성공적으로 추가되었습니다."}, status=status.HTTP_200_OK)
        except Exception:
            raise WeeklyStockRecommendationException()

    def add_stock_to_weekly(self, start_date, stock_id):
        try:
            stock = Stock.objects.get(id=stock_id)
        except Stock.DoesNotExist:
            raise StockNotFoundException()

        # 주차별 추천 주식 목록을 찾거나 새로 만듭니다.
        weekly_stocks, created = WeeklyStockRecommendation.objects.get_or_create(
            start_date=start_date,
            defaults={'end_date': start_date + timedelta(days=6)}
        )

        # 이미 주간 추천에 해당 주식이 있는지 확인합니다.
        if not weekly_stocks.stocks.filter(stock=stock).exists():
            weekly_stock_recommendation_stock = WeeklyStockRecommendationStock(
                stock=stock,
                weekly_stock_recommendation=weekly_stocks
            )
            weekly_stock_recommendation_stock.save()  # 새로운 추천 주식을 저장합니다.
        else:
            raise WeeklyStockRecommendationException()

    def parse_date(self, date_str):
        from datetime import datetime
        return datetime.strptime(date_str, "%Y-%m-%d").date()  # yyyy-MM-dd 형식의 문자열을 date로 변환

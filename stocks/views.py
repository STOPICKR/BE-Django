import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode
import requests
from django.core.exceptions import ObjectDoesNotExist
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
from stocks.models import Stock, WeeklyRecommendation, WeeklyRecommendationStock, DailyStockData, \
    WeeklyRecommendationStockTestResult, WeeklyRecommendationStockPredictResult
from stocks.serializers import StockSerializer, DailyStockDataSerializer, DailyStockDataWithStockSerializer
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


class LatestWeeklyStocksDataView(GenericAPIView):
    serializer_class = DailyStockDataWithStockSerializer

    def get(self, request):
        try:
            response_data = self.get_latest_weekly_stocks_data()
            if not response_data:
                return Response({"message": "No content"}, status=status.HTTP_204_NO_CONTENT)
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error retrieving weekly stocks: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_latest_weekly_stocks_data(self):
        # Step 1: 최근 주차 추천 불러오기
        latest_weekly_stocks = self.get_latest_weekly_recommendation()
        if latest_weekly_stocks is None:
            return []

        # Step 2: Define the date range (one year from now)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)

        # Step 3: Get the stocks from WeeklyRecommendationStock
        stock_data_list = []
        for weekly_stock in latest_weekly_stocks:
            stock = weekly_stock.stock

            # Step 4: Get stock data for the date range
            daily_stock_data = self.get_stock_data_by_date_range(stock, start_date, end_date)

            # Step 5: Append the stock with data to the response list
            stock_data_list.append({
                'isin_code': stock.isin_code,
                'itms_name': stock.itms_name,
                'daily_stock_data': daily_stock_data
            })

        return stock_data_list

    def get_latest_weekly_recommendation(self):
        try:
            # Step 1: Get the latest WeeklyRecommendation
            latest_weekly_recommendation = WeeklyRecommendation.objects.latest('start_date')

            # Step 2: Get related WeeklyRecommendationStock entries
            return WeeklyRecommendationStock.objects.filter(weekly_recommendation=latest_weekly_recommendation)
        except WeeklyRecommendation.DoesNotExist:
            raise WeeklyRecommendationNotFoundException("No weekly recommendation data found.")
        except Exception as e:
            logger.error(f"Error retrieving weekly recommendations: {str(e)}")
            raise WeeklyRecommendationNotFoundException("Error retrieving weekly recommendations.")

    def get_stock_data_by_date_range(self, stock, start_date, end_date):
        try:
            # Step 1: Get DailyStockData for the given stock and date range
            daily_stock_data = DailyStockData.objects.filter(stock=stock, bas_dt__range=[start_date, end_date])

            # Step 2: Serialize the DailyStockData using the StockDataResponseDto serializer
            serializer = DailyStockDataSerializer(daily_stock_data, many=True)

            return serializer.data
        except DailyStockData.DoesNotExist:
            raise StockNotFoundException(f"Daily stock data for ISIN code {stock.isin_code} not found.")
        except Exception as e:
            logger.error(f"Error querying daily stock data for {stock.isin_code}: {str(e)}")
            raise StockNotFoundException(f"Error retrieving stock data for ISIN code {stock.isin_code}.")


class StockAITestView(GenericAPIView):

    def post(self, request):
        # 주식 테스트 실행
        self.test_and_save_weekly_stocks()
        return Response({"message": "주식 테스트 및 예측이 완료되었습니다."}, status=status.HTTP_200_OK)

    def start_testing(self, stock_name, stock_srtn_code, test_runs, window_size):
        """
        Django에서 외부 API로 테스트 요청을 보냄
        """
        print(f"Sending test request with test_runs={test_runs} for stock {stock_srtn_code}")

        # 외부 API에 테스트 요청을 보냄
        url = f"https://sqxle43k4j.execute-api.ap-northeast-2.amazonaws.com/default/api/test/?stock={stock_name}&start_date={stock_srtn_code}&test_runs={test_runs}&window_size={window_size}"
        response = requests.get(url)
        return response

    def test_and_save_weekly_stocks(self):
        try:
            latest_weekly_recommendation = WeeklyRecommendation.objects.latest('start_date')
        except ObjectDoesNotExist:
            return {"error": "No weekly stock recommendations found"}

        start_date = latest_weekly_recommendation.start_date
        five_years_before_start_date = start_date - timedelta(days=365 * 5)
        one_year_before_start_date = start_date - timedelta(days=365)

        test_formatted_date = five_years_before_start_date.strftime('%Y-%m-%d')
        save_formatted_date = one_year_before_start_date.strftime('%Y-%m-%d')

        for weekly_recommendation_stock in WeeklyRecommendationStock.objects.filter(weekly_recommendation=latest_weekly_recommendation):
            stock = weekly_recommendation_stock.stock
            stock_srtn_code = stock.srtn_code

            # 각 주식에 대해 testruns를 1로 하여 10번 요청 실행하고 평균 저장
            self.calculate_and_save_average_profit(stock, stock_srtn_code, test_formatted_date, latest_weekly_recommendation)

        return {"message": "Weekly stocks tested and saved successfully"}

    def calculate_and_save_average_profit(self, stock, stock_srtn_code, test_formatted_date, latest_weekly_recommendation):
        """
        10번의 테스트를 실행하고, 평균 profit 값을 저장하는 함수
        """
        profits = []  # profit 값을 저장할 리스트

        for _ in range(10):
            response = self.start_testing(stock.srtn_code, test_formatted_date, 1, 10)
            if response.status_code == 200:
                test_result_data = response.json()
                profit = test_result_data.get('average_profit')
                if profit is not None:
                    profits.append(float(profit))

        # profit 리스트에 값이 있는 경우 평균을 계산하여 저장
        if profits:
            average_profit = sum(profits) / len(profits)  # 평균 계산

            # 평균 profit 값을 데이터베이스에 저장
            self.save_test_result_to_db(stock, average_profit, latest_weekly_recommendation)

    def save_test_result_to_db(self, stock, average_profit, latest_weekly_recommendation):
        """
        평균 profit 값을 데이터베이스에 저장하는 함수
        """
        WeeklyRecommendationStockTestResult.objects.create(
            profit=average_profit,  # 10번 테스트의 평균 profit 저장
            stock=stock,
            weekly_recommendation=latest_weekly_recommendation,
        )


class StockAIPredictView(GenericAPIView):

    def post(self, request):
        # 주식 예측 실행
        self.predict_and_save_weekly_stocks()
        return Response({"message": "주식 테스트 및 예측이 완료되었습니다."}, status=200)

    def start_prediction(self, stock_name, days_ago, window_size):
        """
        Django에서 외부 API로 예측 요청을 보냄
        """
        url = f"https://sqxle43k4j.execute-api.ap-northeast-2.amazonaws.com/default/api/predict/?stock={stock_name}&days_ago={days_ago}&window_size={window_size}"
        response = requests.get(url)
        return response

    def predict_and_save_weekly_stocks(self):
        """
        주차별 추천 주식에 대해 예측하고 결과를 저장하는 함수
        """
        try:
            latest_weekly_recommendation = WeeklyRecommendation.objects.latest('start_date')
        except ObjectDoesNotExist:
            return {"error": "No weekly stock recommendations found"}

        for weekly_stock in WeeklyRecommendationStock.objects.filter(weekly_recommendation=latest_weekly_recommendation):
            stock = weekly_stock.stock
            stock_name = stock.srtn_code

            # 각 주식에 대해 예측을 실행하고 저장
            self.save_prediction_result(stock, stock_name, latest_weekly_recommendation)

        return {"message": "Weekly stocks predicted and saved successfully"}

    def save_prediction_result(self, stock, stock_name, latest_weekly_recommendation):
        """
        외부 API를 호출하여 예측 후 결과를 저장하는 함수
        """
        # 동기 방식으로 예측 요청
        response = self.start_prediction(stock_name, 0, 10)
        if response.status_code == 200:
            prediction_result_data = response.json()
            self.save_prediction_result_to_db(stock, prediction_result_data, latest_weekly_recommendation)

    def save_prediction_result_to_db(self, stock, prediction_result_data, latest_weekly_recommendation):
        """
        예측 결과를 데이터베이스에 저장
        """
        # 예측 결과를 데이터베이스에 저장
        WeeklyRecommendationStockPredictResult.objects.create(
            stock=stock,
            weekly_recommendation=latest_weekly_recommendation,
            action=prediction_result_data.get('action'),
            target_date=prediction_result_data.get('target_date')
        )


class StockAITestResultView(GenericAPIView):

    def get(self, request, isin_code):
        # ISIN 코드로 Stock 엔티티 조회
        stock = Stock.objects.get(isin_code=isin_code)

        # Stock과 관련된 WeeklyRecommendation 중 가장 최신의 주차 추천을 가져옴
        latest_weekly_recommendation = WeeklyRecommendation.objects.filter(
            weeklyrecommendationstock__stock=stock
        ).order_by('-start_date').first()

        if latest_weekly_recommendation:
            # 해당 WeeklyRecommendation을 기준으로 가장 최신의 TestResult 가져오기
            latest_test_result = WeeklyRecommendationStockTestResult.objects.filter(
                stock=stock,
                weekly_recommendation=latest_weekly_recommendation
            ).order_by('-id').first()

            if latest_test_result:
                return Response({
                    'stock': stock.isin_code,
                    'weekly_recommendation': f"{latest_weekly_recommendation.start_date} - {latest_weekly_recommendation.end_date}",
                    'average_profit': latest_test_result.profit,
                }, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'No test result found for the given stock.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({'error': 'No weekly recommendation found for the given stock.'}, status=status.HTTP_404_NOT_FOUND)


# PredictResult 조회 뷰
class StockAIPredictResultView(GenericAPIView):

    def get(self, request, isin_code):
        # ISIN 코드로 Stock 엔티티 조회
        stock = Stock.objects.get(isin_code=isin_code)

        # 해당 Stock과 관련된 PredictionResult 중 가장 최근 target_date가 있는 결과 조회
        latest_predict_result = WeeklyRecommendationStockPredictResult.objects.filter(
            stock=stock
        ).order_by('-target_date').first()

        if latest_predict_result:
            return Response({
                'action': latest_predict_result.action,
                'target_date': latest_predict_result.target_date,
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'No prediction result found for the given stock.'}, status=status.HTTP_404_NOT_FOUND)
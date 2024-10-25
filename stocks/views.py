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
    DatabaseSaveFailureException, StockSearchFailureException
)
from stocks.models import Stock
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

from django.urls import path

from stocks.views import FetchAllStocksInfoView, StockSearchView

urlpatterns = [

    # 주식 검색
    path('', StockSearchView.as_view(), name="stock-search"),
    # 주식 기본 데이터 저장 (처음 해야할 작업)
    path('info/', FetchAllStocksInfoView.as_view(), name="fetch-all-stocks-info"),
]
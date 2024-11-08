from django.contrib import admin, messages
import requests
from django.urls import path
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.authtoken.models import Token

from stocks.models import Stock, DailyStockData, WeeklyRecommendation, WeeklyRecommendationStock, \
    WeeklyRecommendationStockTestResult, WeeklyRecommendationStockPredictResult


class StockAdmin(admin.ModelAdmin):
    search_fields = ['itms_name']
    change_list_template = "admin/stocks/stock/change_list.html"  # 커스텀 템플릿 사용

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('fetch-all-stocks-info/', self.admin_site.admin_view(self.fetch_all_stocks_info), name='fetch_all_stocks_info'),
        ]
        return custom_urls + urls

    def fetch_all_stocks_info(self, request):
        # url = f"{settings.AWS_LAMBDA_URL}/stocks/info/"
        url = "http://127.0.0.1:8000/stocks/info/"
        token, created = Token.objects.get_or_create(user=request.user)  # 토큰이 없으면 새로 생성
        headers = {'Authorization': f'Token {token.key}'}

        try:
            response = requests.post(url, headers=headers)
            if response.status_code == 200:
                self.message_user(request, "주식 정보가 성공적으로 불러와졌습니다.", messages.SUCCESS)
            else:
                self.message_user(request, "주식 정보를 불러오는 중 문제가 발생했습니다.", messages.ERROR)
        except requests.exceptions.RequestException as e:
            self.message_user(request, f"요청 실패: {str(e)}", messages.ERROR)
        return redirect("..")


class DailyStockDataAdmin(admin.ModelAdmin):
    search_fields = ['stock']
    change_list_template = "admin/stocks/daily_stock_data/change_list.html"  # 커스텀 템플릿 사용

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('fetch_all_stocks_daily_info/', self.admin_site.admin_view(self.fetch_all_stocks_daily_info), name='fetch_all_stocks_daily_info'),
        ]
        return custom_urls + urls

    def fetch_all_stocks_daily_info(self, request):
        # url = f"{settings.AWS_LAMBDA_URL}/stocks/info/"
        url = "http://127.0.0.1:8000/stocks/weekly/daily-data/"
        token, created = Token.objects.get_or_create(user=request.user)  # 토큰이 없으면 새로 생성
        headers = {'Authorization': f'Token {token.key}'}

        try:
            response = requests.post(url, headers=headers)
            if response.status_code == 200:
                self.message_user(request, "주식 일자별 정보가 성공적으로 불러와졌습니다.", messages.SUCCESS)
            else:
                self.message_user(request, "주식 일자별 정보를 불러오는 중 문제가 발생했습니다.", messages.ERROR)
        except requests.exceptions.RequestException as e:
            self.message_user(request, f"요청 실패: {str(e)}", messages.ERROR)
        return redirect("..")


class WeeklyRecommendationStockAdmin(admin.ModelAdmin):
    autocomplete_fields = ['stock']  # Stock 필드를 검색 가능하게 설정


admin.site.register(Stock, StockAdmin)
admin.site.register(DailyStockData, DailyStockDataAdmin)
admin.site.register(WeeklyRecommendation)
admin.site.register(WeeklyRecommendationStock, WeeklyRecommendationStockAdmin)
admin.site.register(WeeklyRecommendationStockTestResult)
admin.site.register(WeeklyRecommendationStockPredictResult)
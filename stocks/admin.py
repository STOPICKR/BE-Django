from django.contrib import admin

from stocks.models import *


class StockAdmin(admin.ModelAdmin):
    search_fields = ['itms_name']


# Register your models here.
admin.site.register(Stock, StockAdmin)
admin.site.register(DailyStockData)
admin.site.register(WeeklyRecommendation)
admin.site.register(WeeklyRecommendationStock)

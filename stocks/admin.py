from django.contrib import admin

from stocks.models import *

# Register your models here.
admin.site.register(Stock)
admin.site.register(DailyStockData)
admin.site.register(WeeklyStockRecommendation)
admin.site.register(WeeklyStockRecommendationStock)

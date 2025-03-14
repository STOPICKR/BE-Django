from rest_framework import serializers


class StockSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    isin_code = serializers.CharField(max_length=50)
    srtn_code = serializers.CharField(max_length=50)
    itms_name = serializers.CharField(max_length=50)
    mrkt_cls = serializers.CharField(max_length=50)


class DailyStockDataSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    bas_dt = serializers.DateField()
    clpr = serializers.IntegerField()
    hipr = serializers.IntegerField()
    lopr = serializers.IntegerField()
    mkp = serializers.IntegerField()
    vs = serializers.DecimalField(max_digits=10, decimal_places=2)
    flt_rt = serializers.DecimalField(max_digits=10, decimal_places=2)
    trqu = serializers.IntegerField()
    tr_prc = serializers.DecimalField(max_digits=20, decimal_places=2)
    lstg_st_cnt = serializers.IntegerField()
    mrkt_tot_amt = serializers.IntegerField()


class DailyStockDataWithStockSerializer(serializers.Serializer):
    isin_code = serializers.CharField(max_length=50)
    itms_name = serializers.CharField(max_length=50)
    dailt_stock_data = DailyStockDataSerializer(many=True)


class WeeklyRecommendationSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class WeeklyRecommendationStockSerializer(serializers.Serializer):
    weekly_stock_recommendation_id = serializers.IntegerField()
    stock_id = serializers.IntegerField()


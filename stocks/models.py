from django.db import models


# 주식 종목
class Stock(models.Model):
    isin_code = models.CharField(max_length=50, verbose_name="ISIN 코드")
    srtn_code = models.CharField(max_length=50, verbose_name="단축 코드")
    itms_name = models.CharField(max_length=50, verbose_name="종목 명")
    mrkt_cls = models.CharField(max_length=50, verbose_name="시장 구분", default="Unknown")

    def __str__(self):
        return self.itms_name


# 주식 종목 일별 데이터
class DailyStockData(models.Model):
    bas_dt = models.DateField(null=False, verbose_name="기준일자")  # 기준일자
    clpr = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="종가")
    hipr = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="고가")
    lopr = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="저가")
    mkp = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="시가")
    vs = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="대비")
    flt_rt = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="등락률")
    trqu = models.BigIntegerField(verbose_name="거래량")
    tr_prc = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="거래대금")
    lstg_st_cnt = models.BigIntegerField(verbose_name="상장주식수")
    mrkt_tot_amt = models.BigIntegerField(verbose_name="시가총액")
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        verbose_name="종목",
    )

    def __str__(self):
        return f"{self.stock} - {self.bas_dt}"


# 주차별 추천
class WeeklyRecommendation(models.Model):
    start_date = models.DateField(null=False)
    end_date = models.DateField(null=False)

    def __str__(self):
        return f"{self.start_date} - {self.end_date}"


# 주차별 추천 주식 종목
class WeeklyRecommendationStock(models.Model):
    weekly_recommendation = models.ForeignKey(
        WeeklyRecommendation,
        on_delete=models.CASCADE,
    )
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.stock} - {self.weekly_recommendation}"


class WeeklyRecommendationStockTestResult(models.Model):
    profit = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
    )
    weekly_recommendation = models.ForeignKey(
        WeeklyRecommendation,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.stock} - {self.weekly_recommendation}"


class WeeklyRecommendationStockPredictResult(models.Model):
    action = models.CharField(max_length=50)
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
    )
    weekly_recommendation = models.ForeignKey(
        WeeklyRecommendation,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.stock} - {self.weekly_recommendation}"
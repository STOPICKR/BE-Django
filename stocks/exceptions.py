from rest_framework import status
from rest_framework.exceptions import APIException


class ApiRequestFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "API 요청 중 오류가 발생했습니다."
    default_code = "api_request_failure"


class ApiResponseParseFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "API 응답 처리 중 오류가 발생했습니다."
    default_code = "api_response_parse_failure"


class HttpStatusCodeFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "API 응답 상태 코드가 200이 아닙니다."
    default_code = "http_status_code_failure"


class DataValidationFailureException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "유효하지 않은 데이터입니다."
    default_code = "data_validation_failure"


class DatabaseSaveFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "데이터베이스 저장 중 오류가 발생했습니다."
    default_code = "database_save_failure"


class StockSearchFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "주식 검색 중 오류가 발생했습니다."
    default_code = "stock_search_failure"


class StockNotFoundException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "주식을 존재하지 않습니다."
    default_code = "stock_not_found_failure"


class WeeklyStockRecommendationException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "주간 추천 주식 저장 중 오류가 발생했습니다."
    default_code = "weekly_stock_recommendation_failure"


class WeeklyStockRecommendationRetrieveFailureException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "주간 추천 주식 검색 중 오류가 발생했습니다."
    default_code = "weekly_stock_recommendation_retrieve_failure"

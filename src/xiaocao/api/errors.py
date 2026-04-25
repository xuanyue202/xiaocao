class XiaocaoError(Exception):
    """Base error for expected Xiaocao failures."""


class ApiError(XiaocaoError):
    pass


class ApiNotFoundError(ApiError):
    pass


class ApiAuthError(ApiError):
    pass


class ApiRateLimitError(ApiError):
    pass


class ApiSchemaError(ApiError):
    pass


class NoTradeDayError(XiaocaoError):
    pass


class NoDataError(XiaocaoError):
    pass


class InvalidDateError(XiaocaoError):
    pass

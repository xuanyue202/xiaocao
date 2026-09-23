class XiaocaoError(Exception):
    """Base error for expected Xiaocao failures."""


class ApiError(XiaocaoError):
    pass


class ApiNotFoundError(ApiError):
    pass


class ApiAuthError(ApiError):
    def __init__(
        self,
        message: str,
        *,
        failure_category: str | None = None,
        official_login_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_category = failure_category
        self.official_login_code = official_login_code


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

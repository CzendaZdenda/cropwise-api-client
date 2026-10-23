class CropwiseException(Exception):
    """
    Base exception class for the Cropwise API client library.
    All custom library exceptions inherit from this class.
    """
    pass


class CropwiseAuthException(CropwiseException):
    """
    Raised when authentication fails.
    Occurs due to invalid credentials, missing tokens, or insufficient permissions.
    """
    pass


class CropwiseApiException(CropwiseException):
    """
    Raised when the Cropwise server returns an API error response.
    Handles standard HTTP error statuses such as 4xx and 5xx responses.
    """
    pass
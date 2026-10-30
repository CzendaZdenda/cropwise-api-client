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


class CropwiseValueError(CropwiseException):
    """
    Raised when user provides invalid argument values, shapes, 
    or unparseable date/time strings to library methods.
    """
    pass

class CropwiseOdometerDuplicateError(CropwiseApiException):
    """
    Raised when an odometer state record already exists for the specified timestamp.
    Typically triggered by a language-agnostic HTTP 422 error containing 'measuring_time'.
    """
    pass
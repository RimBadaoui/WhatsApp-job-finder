class SDKError(Exception):
    pass


class EventValidationError(SDKError):
    pass


class UnsupportedEventTypeError(SDKError):
    pass


class MediaDownloadError(SDKError):
    pass


class MediaExpiredError(MediaDownloadError):
    pass


class MediaUnavailableError(MediaDownloadError):
    pass


class MediaTooLargeError(MediaDownloadError):
    pass

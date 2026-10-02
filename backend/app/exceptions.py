"""Custom exceptions for Paperless-AIssist."""


class PaperlessAissistError(Exception):
    """Base exception for all application errors."""

    pass


class ConfigurationError(PaperlessAissistError):
    """Raised when configuration is missing or invalid."""

    pass


class LLMError(PaperlessAissistError):
    """Raised when LLM operations fail."""

    pass


class LLMUnavailableError(LLMError):
    """Raised when the LLM service is unreachable or the model is not available."""

    pass


class LLMHttpError(LLMError):
    """A request the provider refused, with what it said.

    The message alone cannot tell a rejected parameter from a wrong key, and
    callers that fall back on one but not the other need the status and body.
    """

    def __init__(self, message: str, *, status_code: int, body: str):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class DocumentProcessingError(PaperlessAissistError):
    """Raised when document processing fails."""

    pass


class PaperlessAPIError(PaperlessAissistError):
    """Raised when Paperless API calls fail."""

    pass

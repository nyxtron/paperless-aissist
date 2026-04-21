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


class DocumentProcessingError(PaperlessAissistError):
    """Raised when document processing fails."""

    pass


class PaperlessAPIError(PaperlessAissistError):
    """Raised when Paperless API calls fail."""

    pass

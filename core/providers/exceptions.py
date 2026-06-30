class ProviderException(Exception):
    """Base exception class for all AI provider errors in J.A.R.V.I.S."""
    pass

class ProviderUnavailable(ProviderException):
    """Raised when the requested provider is offline, unreachable, or disabled."""
    pass

class AuthenticationError(ProviderException):
    """Raised when provider authentication fails (e.g. invalid API key)."""
    pass

class RateLimitError(ProviderException):
    """Raised when the provider rate limits are exceeded (HTTP 429)."""
    pass

class TimeoutError(ProviderException):
    """Raised when the provider request times out."""
    pass

class ModelNotFound(ProviderException):
    """Raised when the requested model name is not found on the provider."""
    pass

class ContextLengthExceeded(ProviderException):
    """Raised when the input context exceeds the model's token limit."""
    pass

class InvalidConfiguration(ProviderException):
    """Raised when configuration values are invalid or missing."""
    pass

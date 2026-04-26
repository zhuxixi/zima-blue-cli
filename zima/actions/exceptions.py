class ProviderError(Exception):
    """Base exception for action provider errors."""


class ProviderNotFoundError(ProviderError):
    """Raised when a requested provider is not found in the registry."""

import pytest

from zima.actions.exceptions import ProviderError, ProviderNotFoundError


class TestActionExceptions:
    def test_provider_error_is_exception(self):
        """ProviderError should be a subclass of Exception."""
        assert issubclass(ProviderError, Exception)

    def test_provider_not_found_error_is_provider_error(self):
        """ProviderNotFoundError should be a subclass of ProviderError."""
        assert issubclass(ProviderNotFoundError, ProviderError)

    def test_can_raise_and_catch_provider_error(self):
        """ProviderError can be raised and caught."""
        with pytest.raises(ProviderError):
            raise ProviderError("something went wrong")

    def test_can_raise_and_catch_provider_not_found_error(self):
        """ProviderNotFoundError can be raised and caught."""
        with pytest.raises(ProviderNotFoundError):
            raise ProviderNotFoundError("provider not found")

    def test_provider_not_found_error_caught_as_provider_error(self):
        """ProviderNotFoundError can be caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise ProviderNotFoundError("provider not found")

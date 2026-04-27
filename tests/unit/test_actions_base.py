import pytest

from zima.actions.base import ActionProvider


class TestActionProvider:
    def test_can_subclass_and_call_methods(self):
        """Test that ActionProvider can be subclassed and methods work."""

        class TestProvider(ActionProvider):
            @property
            def name(self) -> str:
                return "test"

            def add_label(self, repo: str, issue: str, label: str) -> None:
                pass

            def remove_label(self, repo: str, issue: str, label: str) -> None:
                pass

            def post_comment(self, repo: str, issue: str, body: str) -> None:
                pass

            def fetch_diff(self, repo: str, issue: str) -> str:
                return "diff"

        provider = TestProvider()
        assert provider.name == "test"
        provider.add_label("o/r", "1", "bug")
        provider.remove_label("o/r", "1", "bug")
        provider.post_comment("o/r", "1", "ok")
        assert provider.fetch_diff("o/r", "1") == "diff"

    def test_abstract_methods_must_be_implemented(self):
        """Test that missing abstract methods prevent instantiation."""
        with pytest.raises(TypeError):

            class BadProvider(ActionProvider):
                pass

            BadProvider()

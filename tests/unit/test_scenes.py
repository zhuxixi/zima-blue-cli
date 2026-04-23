"""Unit tests for quickstart scene definitions."""

from tests.base import TestIsolator
from zima.scenes import QUICKSTART_SCENES


class TestQuickstartScenes(TestIsolator):
    """Test scene definitions."""

    def test_scenes_is_dict(self):
        """Test that QUICKSTART_SCENES is a non-empty dict."""
        assert isinstance(QUICKSTART_SCENES, dict)
        assert len(QUICKSTART_SCENES) > 0

    def test_code_review_scene_structure(self):
        """Test code-review scene has required fields."""
        scene = QUICKSTART_SCENES["code-review"]
        assert scene["name"] == "Code Review"
        assert "workflow_template" in scene
        assert "variables" in scene
        assert "pr_url" in scene["variables"]

    def test_custom_scene_structure(self):
        """Test custom scene has required fields."""
        scene = QUICKSTART_SCENES["custom"]
        assert "name" in scene
        assert "workflow_template" in scene
        assert "variables" in scene

    def test_all_scenes_have_required_keys(self):
        """Test every scene has name, description, workflow_template, variables."""
        for key, scene in QUICKSTART_SCENES.items():
            assert "name" in scene, f"Scene {key} missing 'name'"
            assert "description" in scene, f"Scene {key} missing 'description'"
            assert "workflow_template" in scene, f"Scene {key} missing 'workflow_template'"
            assert "variables" in scene, f"Scene {key} missing 'variables'"
            assert isinstance(scene["variables"], dict), f"Scene {key} variables not a dict"

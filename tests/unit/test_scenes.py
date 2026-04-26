"""Unit tests for quickstart scene definitions."""

from tests.base import TestIsolator
from zima.scenes import BUILTIN_SCENES, QUICKSTART_SCENES, Scene, load_scenes


class TestSceneDataclass:
    """Test Scene dataclass creation."""

    def test_scene_creation_with_defaults(self):
        """Test Scene can be created with default provider and scan_command."""
        scene = Scene(
            name="Test Scene",
            description="A test scene",
            workflow_template="Hello {{ name }}",
            variables={"name": ""},
        )
        assert scene.name == "Test Scene"
        assert scene.description == "A test scene"
        assert scene.workflow_template == "Hello {{ name }}"
        assert scene.variables == {"name": ""}
        assert scene.provider == "github"
        assert scene.scan_command is None

    def test_scene_creation_with_all_fields(self):
        """Test Scene can be created with all fields specified."""
        scene = Scene(
            name="Code Review",
            description="Review PRs/MRs with AI agent",
            workflow_template="CR {{ pr_url }}",
            variables={"pr_url": ""},
            provider="github",
            scan_command=["gh", "pr", "list"],
        )
        assert scene.provider == "github"
        assert scene.scan_command == ["gh", "pr", "list"]


class TestBuiltinScenes:
    """Test BUILTIN_SCENES structure."""

    def test_builtin_scenes_is_dict(self):
        """Test that BUILTIN_SCENES is a non-empty dict."""
        assert isinstance(BUILTIN_SCENES, dict)
        assert len(BUILTIN_SCENES) > 0

    def test_all_scenes_are_scene_objects(self):
        """Test every scene is a Scene dataclass instance."""
        for key, scene in BUILTIN_SCENES.items():
            assert isinstance(scene, Scene), f"Scene {key} is not a Scene instance"

    def test_code_review_scene_structure(self):
        """Test code-review scene has correct fields."""
        scene = BUILTIN_SCENES["code-review"]
        assert scene.name == "Code Review"
        assert scene.description == "Review PRs/MRs with AI agent"
        assert scene.workflow_template == "CR {{ pr_url }}"
        assert scene.variables == {"pr_url": ""}
        assert scene.provider == "github"
        assert scene.scan_command == [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--label",
            "need-review",
            "--json",
            "number,title,url",
        ]

    def test_custom_scene_structure(self):
        """Test custom scene has correct fields."""
        scene = BUILTIN_SCENES["custom"]
        assert scene.name == "Custom Task"
        assert scene.description == "Write your own prompt template"
        assert scene.workflow_template == ""
        assert scene.variables == {}
        assert scene.provider == "github"
        assert scene.scan_command is None

    def test_all_scenes_have_required_keys(self):
        """Test every scene has name, description, workflow_template, variables."""
        for key, scene in BUILTIN_SCENES.items():
            assert scene.name, f"Scene {key} missing 'name'"
            assert scene.description, f"Scene {key} missing 'description'"
            assert scene.workflow_template is not None, f"Scene {key} missing 'workflow_template'"
            assert isinstance(scene.variables, dict), f"Scene {key} variables not a dict"


class TestQuickstartScenesAlias:
    """Test QUICKSTART_SCENES backward compatibility alias."""

    def test_alias_points_to_builtin(self):
        """Test QUICKSTART_SCENES is the same object as BUILTIN_SCENES."""
        assert QUICKSTART_SCENES is BUILTIN_SCENES

    def test_alias_has_same_keys(self):
        """Test QUICKSTART_SCENES has the same keys as BUILTIN_SCENES."""
        assert set(QUICKSTART_SCENES.keys()) == set(BUILTIN_SCENES.keys())


class TestLoadScenes(TestIsolator):
    """Test load_scenes() function."""

    def test_loads_builtin_scenes(self):
        """Test load_scenes returns built-in scenes when no user file exists."""
        scenes = load_scenes()
        assert "code-review" in scenes
        assert "custom" in scenes
        assert isinstance(scenes["code-review"], Scene)

    def test_merges_user_scenes(self, isolated_zima_home):
        """Test load_scenes merges user-defined scenes from scenes.yaml."""
        scenes_file = isolated_zima_home / "scenes.yaml"
        scenes_file.write_text(
            "scenes:\n"
            "  my-scene:\n"
            "    name: My Scene\n"
            "    description: A user scene\n"
            '    workflow_template: "Do {{ thing }}"\n'
            "    variables:\n"
            '      thing: ""\n'
            "    provider: gitlab\n",
            encoding="utf-8",
        )
        scenes = load_scenes()
        assert "my-scene" in scenes
        assert isinstance(scenes["my-scene"], Scene)
        assert scenes["my-scene"].name == "My Scene"
        assert scenes["my-scene"].provider == "gitlab"

    def test_user_scenes_override_builtin(self, isolated_zima_home):
        """Test user scenes can override built-in scenes."""
        scenes_file = isolated_zima_home / "scenes.yaml"
        scenes_file.write_text(
            "scenes:\n"
            "  code-review:\n"
            "    name: Overridden CR\n"
            "    description: Custom code review\n"
            '    workflow_template: "Review {{ pr_url }}"\n'
            "    variables:\n"
            '      pr_url: ""\n'
            "    provider: gitlab\n"
            "    scan_command:\n"
            "      - glab\n"
            "      - mr\n"
            "      - list\n",
            encoding="utf-8",
        )
        scenes = load_scenes()
        assert scenes["code-review"].name == "Overridden CR"
        assert scenes["code-review"].provider == "gitlab"
        assert scenes["code-review"].scan_command == ["glab", "mr", "list"]
        # Ensure other builtins are still present
        assert "custom" in scenes

    def test_user_scene_with_scan_command_none(self, isolated_zima_home):
        """Test user scene without scan_command defaults to None."""
        scenes_file = isolated_zima_home / "scenes.yaml"
        scenes_file.write_text(
            "scenes:\n"
            "  no-scan:\n"
            "    name: No Scan\n"
            "    description: Scene without scan command\n"
            '    workflow_template: "Hello"\n'
            "    variables: {}\n",
            encoding="utf-8",
        )
        scenes = load_scenes()
        assert scenes["no-scan"].scan_command is None

    def test_empty_scenes_yaml(self, isolated_zima_home):
        """Test load_scenes handles empty scenes.yaml gracefully."""
        scenes_file = isolated_zima_home / "scenes.yaml"
        scenes_file.write_text("", encoding="utf-8")
        scenes = load_scenes()
        assert "code-review" in scenes
        assert "custom" in scenes

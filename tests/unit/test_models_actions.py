from zima.models.actions import ActionsConfig, PostExecAction


class TestPostExecAction:
    def test_default_action(self):
        """Test creating a PostExecAction with default values."""
        action = PostExecAction()
        assert action.condition == "always"
        assert action.type == "github_label"
        assert action.add_labels == []
        assert action.remove_labels == []
        assert action.repo == ""
        assert action.issue == ""
        assert action.body == ""

    def test_full_action(self):
        """Test creating a fully configured PostExecAction."""
        action = PostExecAction(
            condition="success",
            type="github_comment",
            body="Review approved",
            repo="owner/repo",
            issue="123",
        )
        assert action.condition == "success"
        assert action.type == "github_comment"
        assert action.body == "Review approved"

    def test_to_dict(self):
        """Test converting PostExecAction to dictionary."""
        action = PostExecAction(
            condition="success",
            type="github_label",
            add_labels=["zima:needs-fix"],
            remove_labels=["zima:needs-review"],
            repo="owner/repo",
            issue="42",
        )
        d = action.to_dict()
        assert d["condition"] == "success"
        assert d["type"] == "github_label"
        assert d["addLabels"] == ["zima:needs-fix"]
        assert d["removeLabels"] == ["zima:needs-review"]
        assert d["repo"] == "owner/repo"
        assert d["issue"] == "42"

    def test_to_dict_omits_empty_fields(self):
        """Test that to_dict omits empty optional fields."""
        action = PostExecAction(condition="always", type="github_label")
        d = action.to_dict()
        assert "addLabels" not in d
        assert "removeLabels" not in d
        assert "repo" not in d
        assert "issue" not in d
        assert "body" not in d

    def test_from_dict(self):
        """Test creating PostExecAction from dictionary."""
        d = {
            "condition": "failure",
            "type": "github_comment",
            "body": "Failed",
            "repo": "o/r",
            "issue": "1",
        }
        action = PostExecAction.from_dict(d)
        assert action.condition == "failure"
        assert action.body == "Failed"

    def test_from_dict_defaults(self):
        """Test that from_dict uses correct defaults for missing fields."""
        d = {"condition": "success", "type": "github_label"}
        action = PostExecAction.from_dict(d)
        assert action.add_labels == []
        assert action.remove_labels == []
        assert action.repo == ""
        assert action.issue == ""
        assert action.body == ""

    def test_validate_valid(self):
        """Test validation with valid action configuration."""
        action = PostExecAction(condition="success", type="github_label")
        assert action.validate() == []

    def test_validate_invalid_condition(self):
        """Test validation catches invalid condition."""
        action = PostExecAction(condition="invalid", type="github_label")
        errors = action.validate()
        assert len(errors) == 1
        assert "Invalid condition" in errors[0]

    def test_validate_invalid_type(self):
        """Test validation catches invalid action type."""
        action = PostExecAction(condition="success", type="invalid")
        errors = action.validate()
        assert len(errors) == 1
        assert "Invalid type" in errors[0]


class TestActionsConfig:
    def test_empty_config(self):
        """Test creating an empty ActionsConfig."""
        config = ActionsConfig()
        assert config.post_exec == []

    def test_with_actions(self):
        """Test creating ActionsConfig with actions."""
        action = PostExecAction(condition="success", type="github_label")
        config = ActionsConfig(post_exec=[action])
        assert len(config.post_exec) == 1

    def test_to_dict(self):
        """Test converting ActionsConfig to dictionary."""
        config = ActionsConfig(post_exec=[PostExecAction(condition="success", type="github_label")])
        d = config.to_dict()
        assert "postExec" in d
        assert len(d["postExec"]) == 1

    def test_from_dict(self):
        """Test creating ActionsConfig from dictionary."""
        d = {"postExec": [{"condition": "success", "type": "github_label", "addLabels": ["a"]}]}
        config = ActionsConfig.from_dict(d)
        assert len(config.post_exec) == 1
        assert config.post_exec[0].condition == "success"

    def test_validate_all_actions(self):
        """Test validating all actions in config."""
        config = ActionsConfig(
            post_exec=[
                PostExecAction(condition="success", type="github_label"),
                PostExecAction(condition="invalid", type="invalid"),
            ]
        )
        errors = config.validate()
        assert len(errors) == 2
        assert "Action[1]" in errors[0]

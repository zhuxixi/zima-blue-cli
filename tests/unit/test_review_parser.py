from zima.review.parser import ReviewIssue, ReviewResult


class TestReviewIssue:
    def test_create_issue(self):
        """Test creating a ReviewIssue with explicit values."""
        issue = ReviewIssue(
            severity="error",
            file="src/foo.py",
            line=42,
            message="变量未定义",
        )
        assert issue.severity == "error"
        assert issue.file == "src/foo.py"
        assert issue.line == 42
        assert issue.message == "变量未定义"

    def test_default_values(self):
        """Test ReviewIssue default field values."""
        issue = ReviewIssue()
        assert issue.severity == "warning"
        assert issue.file == ""
        assert issue.line == 0
        assert issue.message == ""


class TestReviewResult:
    def test_default_result(self):
        """Test ReviewResult default field values."""
        result = ReviewResult()
        assert result.verdict == ""
        assert result.summary == ""
        assert result.issues == []

    def test_result_with_issues(self):
        """Test creating a ReviewResult containing issues."""
        issue = ReviewIssue(severity="warning", file="a.py", line=1, message="x")
        result = ReviewResult(
            verdict="needs_fix",
            summary="发现 2 个问题",
            issues=[issue],
        )
        assert result.verdict == "needs_fix"
        assert result.summary == "发现 2 个问题"
        assert len(result.issues) == 1

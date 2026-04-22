from zima.review.parser import ReviewIssue, ReviewParser, ReviewResult


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


class TestReviewParser:
    def test_parse_approved_review(self):
        """Test parsing an approved review with no issues."""
        stdout = "Some review text\n<zima-review>\n  <verdict>approved</verdict>\n  <summary>LGTM</summary>\n</zima-review>"
        result = ReviewParser.parse(stdout)
        assert result.verdict == "approved"
        assert result.summary == "LGTM"
        assert result.issues == []

    def test_parse_needs_fix(self):
        """Test parsing a review that needs fixes with multiple issues."""
        stdout = """Review complete.
<zima-review>
  <verdict>needs_fix</verdict>
  <summary>发现 2 个问题</summary>
  <issues>
    <issue severity="error" file="src/foo.py" line="42">变量未定义</issue>
    <issue severity="warning" file="src/bar.py" line="10">缺少类型注解</issue>
  </issues>
</zima-review>"""
        result = ReviewParser.parse(stdout)
        assert result.verdict == "needs_fix"
        assert result.summary == "发现 2 个问题"
        assert len(result.issues) == 2
        assert result.issues[0].severity == "error"
        assert result.issues[0].file == "src/foo.py"
        assert result.issues[0].line == 42  # Note: line is now int
        assert result.issues[0].message == "变量未定义"

    def test_parse_no_block(self):
        """Test parsing when no review block is present."""
        result = ReviewParser.parse("No review block here")
        assert result.verdict == "needs_discussion"
        assert "No review block" in result.summary

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML returns fallback result."""
        result = ReviewParser.parse("<zima-review><unclosed>")
        assert result.verdict == "needs_discussion"
        assert "Invalid" in result.summary

    def test_parse_empty_issues(self):
        """Test parsing a review with explicit empty issues list."""
        stdout = "<zima-review><verdict>approved</verdict><summary>OK</summary><issues></issues></zima-review>"
        result = ReviewParser.parse(stdout)
        assert result.verdict == "approved"
        assert result.issues == []

    def test_parse_unclosed_tag(self):
        """Test parsing unclosed review tag with valid inner content."""
        stdout = "<zima-review><verdict>approved</verdict><summary>OK</summary>"
        result = ReviewParser.parse(stdout)
        assert result.verdict == "approved"
        assert result.summary == "OK"

    def test_parse_line_edge_cases(self):
        """Test parsing issues with various line attribute formats."""
        # Missing line attribute
        stdout = '<zima-review><verdict>needs_fix</verdict><summary>x</summary><issues><issue severity="error" file="a.py">msg</issue></issues></zima-review>'
        result = ReviewParser.parse(stdout)
        assert result.issues[0].line == 0

        # Non-numeric line
        stdout = '<zima-review><verdict>needs_fix</verdict><summary>x</summary><issues><issue severity="error" file="a.py" line="abc">msg</issue></issues></zima-review>'
        result = ReviewParser.parse(stdout)
        assert result.issues[0].line == 0

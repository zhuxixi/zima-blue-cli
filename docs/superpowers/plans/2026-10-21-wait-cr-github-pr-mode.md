# wait-cr GitHub-native wait mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `pi/zima-pr-monitor/scripts/wait-cr.py` 增加 `--pr owner/repo#N` 远程等待模式，并让本地模式在无 zima 运行态时立即以 exit 3 说明原因。

**Architecture:** 纯函数判定层（ref 解析、meta 识别、review 选择、摘要行）+ 可注入 IO 层（`gh` 子进程）+ 注入时钟的控制循环（`run_pr_loop`）。既有本地模式 `run_loop` 及其辅助函数一行不动，只在 `main()` 前置 `has_local_runtime` 检查。

**Tech Stack:** Python 3 stdlib（`argparse` / `json` / `re` / `subprocess` / `datetime` / `pathlib`）、pytest + `importlib` 加载脚本、`gh` CLI 2.x。

**Spec:** `docs/superpowers/specs/2026-10-21-wait-cr-github-pr-mode-design.md`（issue #264）

## Global Constraints

- 脚本保持 **stdlib-only**，不新增依赖（spec §9）。
- 不修改 `run_loop` / `is_active` / `is_stale` / `format_summary` / `load_states` / `tail_log` / `pid_alive` 的签名与行为（spec §9、A10）。
- 新增纯函数不得做 IO；`main()` 是唯一 argparse 与真实 IO 编排点（spec §3.5）。
- 测试不 sleep 真时间、不访问网络、不起 `gh` 子进程（spec §3.5）。
- 退出码固定：`0` 收敛 / `1` 超时 / `2` 本地无执行 / `3` 本地无 runtime / `4` head 变更 / `5` PR 非 OPEN / `6` 启动期 gh 失败 / `64` 用法错误（spec §4）。
- 文档改动不写主机名、内网地址（spec §5、§9）。
- commit 格式 `type(scope): description`；`git add <file>` 逐文件，不用 `git add -A`。

## Review Focus

- **时钟偏差**：本地时钟与 GitHub 时间差 > `--since-minutes` 时，旧 review 可能被当成本轮 → `select_meta_review` 必须有「早于 not_before 就丢弃」的测试。
- **并发 push**：head 变更与旧 head review 同一次快照出现时，必须先判 head 变更（exit 4），不能被旧 review 抢成 exit 0。
- **gh 输出异常**：`gh` 返回空串/非 JSON/无 `headRefOid` 时不能静默轮询到超时，启动期必须 exit 6。
- **argparse 默认退出码**：`--timeout abc` 这类错误默认 exit 2，会和「本地无执行」混淆 → 必须被 `_Parser.error` 改成 64。
- **本地回归**：`TestMain` 既有用例只造了 `history/pjobs/<code>`，preflight 检查的是 `history/pjobs` 目录本身，不能被写成 `state_dir` 存在性判断。

---

### Task 1: 纯函数判定层

**Files:**
- Modify: `pi/zima-pr-monitor/scripts/wait-cr.py`（新增 import + 常量 + `GhQueryError` + 5 个纯函数）
- Test: `tests/unit/test_wait_cr.py`（追加 5 个测试类）

**Interfaces:**
- Consumes: 既有 `parse_iso(value) -> datetime | None`（`wait-cr.py:40`）
- Produces:
  - `parse_pr_ref(text: str) -> tuple[str, str, int]`（坏输入抛 `ValueError`）
  - `meta_marker(body: str) -> str | None`（返回 `"pi"` / `"cc"` / `None`）
  - `parse_meta_json(body: str) -> dict | None`
  - `select_meta_review(reviews: list[dict], head_sha: str, not_before: datetime) -> dict | None`
  - `format_review_summary(review: dict) -> str`
  - 常量 `META_MARKERS`, `META_JSON_RE`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_wait_cr.py` 末尾追加：

```python
class TestParsePrRef:
    def test_parses_owner_repo_number(self):
        assert wait_cr.parse_pr_ref("zhuxixi/zima-blue-cli#264") == (
            "zhuxixi",
            "zima-blue-cli",
            264,
        )

    def test_strips_surrounding_space(self):
        assert wait_cr.parse_pr_ref("  a/b#7 ") == ("a", "b", 7)

    @pytest.mark.parametrize("bad", ["a/b", "a#1", "/b#1", "a/#1", "a/b/c#1", "a/b#x", "a/b#0"])
    def test_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            wait_cr.parse_pr_ref(bad)


class TestMetaMarker:
    def test_pi_marker(self):
        assert wait_cr.meta_marker("<!-- pi-cr-meta {}\n-->") == "pi"

    def test_cc_marker_tolerates_whitespace(self):
        assert wait_cr.meta_marker("<!--cc-cr-meta\n{}") == "cc"

    def test_kimi_marker_is_ignored(self):
        assert wait_cr.meta_marker("<!-- kimi-cr-meta {} -->") is None

    def test_prose_mention_is_not_a_marker(self):
        assert wait_cr.meta_marker("we use pi-cr-meta in reviews") is None

    def test_empty_body(self):
        assert wait_cr.meta_marker("") is None


class TestParseMetaJson:
    def test_parses_payload(self):
        body = '<!-- pi-cr-meta {"round": 2, "blocking_new_count": 0} -->'
        assert wait_cr.parse_meta_json(body) == {"round": 2, "blocking_new_count": 0}

    def test_bad_json_returns_none(self):
        assert wait_cr.parse_meta_json('<!-- pi-cr-meta {"round": 2 -->') is None

    def test_non_object_json_returns_none(self):
        assert wait_cr.parse_meta_json('<!-- pi-cr-meta [1, 2] -->') is None

    def test_no_marker_returns_none(self):
        assert wait_cr.parse_meta_json("plain review body") is None


def meta_review(head, minutes_ago, review_id="PRR_1", marker="pi", **extra):
    submitted = (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
    body = f'<!-- {marker}-cr-meta {{"round": 1}} -->'
    return {"id": review_id, "submittedAt": submitted, "commit": {"oid": head}, "body": body, **extra}


class TestSelectMetaReview:
    HEAD = "a" * 40

    def test_picks_review_for_target_head(self):
        review = meta_review(self.HEAD, 1)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is review

    def test_ignores_review_for_other_head(self):
        review = meta_review("b" * 40, 1)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_ignores_review_older_than_window(self):
        review = meta_review(self.HEAD, 30)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_ignores_review_without_metadata(self):
        review = meta_review(self.HEAD, 1)
        review["body"] = "just a comment"
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_returns_newest_match(self):
        older = meta_review(self.HEAD, 5, review_id="PRR_old")
        newer = meta_review(self.HEAD, 1, review_id="PRR_new")
        assert wait_cr.select_meta_review([older, newer], self.HEAD, cutoff_minutes_ago(10)) is newer

    def test_tolerates_malformed_entries(self):
        good = meta_review(self.HEAD, 1)
        reviews = [None, {"commit": None}, {"commit": {}}, good]
        assert wait_cr.select_meta_review(reviews, self.HEAD, cutoff_minutes_ago(10)) is good


class TestFormatReviewSummary:
    def test_includes_identity_and_meta_counts(self):
        review = meta_review(self.HEAD, 1, review_id="PRR_x", round=2)
        review["body"] = (
            '<!-- pi-cr-meta {"round": 2, "blocking_new_count": 0, '
            '"blocking_open_count": 1} -->'
        )
        review["author"] = {"login": "zhuxixi"}
        line = wait_cr.format_review_summary(review)
        assert "review=PRR_x" in line
        assert "head=aaaaaaaaaaaa" in line
        assert "author=zhuxixi" in line
        assert "meta=pi" in line
        assert "round=2" in line
        assert "blocking_new=0" in line
        assert "blocking_open=1" in line

    def test_missing_counts_render_dash(self):
        review = meta_review(self.HEAD, 1)
        line = wait_cr.format_review_summary(review)
        assert "round=1" in line
        assert "blocking_new=-" in line
        assert "blocking_open=-" in line
```

`TestFormatReviewSummary.test_includes_identity_and_meta_counts` 里的 `meta_review(..., round=2)` 会与 `**extra` 冲突，实现测试时改成：

```python
    def test_includes_identity_and_meta_counts(self):
        review = meta_review(self.HEAD, 1, review_id="PRR_x")
        review["author"] = {"login": "zhuxixi"}
        review["body"] = (
            '<!-- pi-cr-meta {"round": 2, "blocking_new_count": 0, '
            '"blocking_open_count": 1} -->'
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k "ParsePrRef or MetaMarker or ParseMetaJson or SelectMetaReview or FormatReviewSummary"`
Expected: FAIL（`AttributeError: module 'wait_cr' has no attribute 'parse_pr_ref'`）

- [ ] **Step 3: 写实现**

在 `wait-cr.py` 的 import 区加 `import re`、`import subprocess`，在常量区加：

```python
META_MARKERS = {
    "pi": re.compile(r"<!--\s*pi-cr-meta"),
    "cc": re.compile(r"<!--\s*cc-cr-meta"),
}
META_JSON_RE = re.compile(r"<!--\s*(?:pi|cc)-cr-meta\s+(\{.*?\})\s*-->", re.DOTALL)
GH_START_ATTEMPTS = 3
GH_TIMEOUT = 120
```

在 `parse_iso` 之后加：

```python
class GhQueryError(RuntimeError):
    """``gh`` failed, or returned output that is not a PR payload."""


def parse_pr_ref(text: str) -> tuple[str, str, int]:
    """Parse ``owner/repo#123`` into its three parts.

    Strict on purpose: a mistyped reference must fail at startup (exit 64)
    instead of polling the wrong repository until the timeout.
    """
    raw = (text or "").strip()
    slug, sep, number = raw.rpartition("#")
    owner, slash, repo = slug.partition("/")
    if not sep or not owner or not slash or not repo or "/" in repo:
        raise ValueError(f"expected owner/repo#number, got {text!r}")
    if not number.isdigit() or int(number) <= 0:
        raise ValueError(f"expected a positive PR number, got {number!r}")
    return owner, repo, int(number)


def meta_marker(body: str) -> str | None:
    """Return ``"pi"`` / ``"cc"`` when the body carries a CR metadata block.

    Requires the HTML-comment opener so prose that merely mentions
    ``pi-cr-meta`` does not count. ``kimi-cr-meta`` is retired and never matches.
    """
    for kind, pattern in META_MARKERS.items():
        if pattern.search(body or ""):
            return kind
    return None


def parse_meta_json(body: str) -> dict | None:
    """Best-effort metadata JSON for the summary line only.

    A malformed block must never influence the convergence decision, so every
    failure collapses to ``None``.
    """
    match = META_JSON_RE.search(body or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def select_meta_review(
    reviews: list[dict], head_sha: str, not_before: datetime
) -> dict | None:
    """Newest metadata review written against ``head_sha`` after ``not_before``.

    ``not_before`` is what keeps a review from an earlier round on the same
    head from ending the wait instantly, while still accepting a round that
    finished moments before the wait started.
    """
    newest: dict | None = None
    newest_at: datetime | None = None
    for review in reviews or []:
        if not isinstance(review, dict):
            continue
        commit = review.get("commit")
        oid = commit.get("oid") if isinstance(commit, dict) else None
        if oid != head_sha:
            continue
        if meta_marker(str(review.get("body") or "")) is None:
            continue
        submitted = parse_iso(review.get("submittedAt"))
        if submitted is None or submitted < not_before:
            continue
        if newest_at is None or submitted >= newest_at:
            newest, newest_at = review, submitted
    return newest


def format_review_summary(review: dict) -> str:
    """One-line summary of the matching review — the session's only signal."""
    body = str(review.get("body") or "")
    meta = parse_meta_json(body) or {}
    author = review.get("author")
    login = author.get("login") if isinstance(author, dict) else None
    commit = review.get("commit")
    oid = commit.get("oid") if isinstance(commit, dict) else None

    def field(key: str) -> str:
        value = meta.get(key)
        return "-" if value is None else str(value)

    parts = [
        f"review={review.get('id') or '?'}",
        f"head={str(oid or '?')[:12]}",
        f"submittedAt={review.get('submittedAt') or '?'}",
        f"author={login or '?'}",
        f"meta={meta_marker(body) or '?'}",
        f"round={field('round')}",
        f"blocking_new={field('blocking_new_count')}",
        f"blocking_open={field('blocking_open_count')}",
    ]
    return "wait-cr: converged: " + " ".join(parts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k "ParsePrRef or MetaMarker or ParseMetaJson or SelectMetaReview or FormatReviewSummary"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add pi/zima-pr-monitor/scripts/wait-cr.py tests/unit/test_wait_cr.py
git commit -m "feat(skill): pure helpers for wait-cr PR mode (#264)"
```

---

### Task 2: IO 层与控制循环

**Files:**
- Modify: `pi/zima-pr-monitor/scripts/wait-cr.py`（`has_local_runtime` / `_gh_runner` / `fetch_pr_state` / `run_pr_loop`）
- Test: `tests/unit/test_wait_cr.py`（`TestFetchPrState` / `TestRunPrLoop` / `TestHasLocalRuntime`）

**Interfaces:**
- Consumes: Task 1 的 `select_meta_review` / `format_review_summary` / `GhQueryError` / `parse_iso`
- Produces:
  - `has_local_runtime(zima_home: Path) -> bool`
  - `_gh_runner(argv: list[str]) -> str`（抛 `GhQueryError`）
  - `fetch_pr_state(owner, repo, number, runner=_gh_runner) -> dict`
  - `run_pr_loop(pr, *, timeout=DEFAULT_TIMEOUT, poll=DEFAULT_POLL, since_minutes=DEFAULT_SINCE_MINUTES, fetch=None, sleep=time.sleep, monotonic=time.monotonic, out=None) -> int`

- [ ] **Step 1: 写失败测试**

```python
class TestHasLocalRuntime:
    def test_true_when_pjobs_dir_exists(self, tmp_path):
        (tmp_path / "history" / "pjobs").mkdir(parents=True)
        assert wait_cr.has_local_runtime(tmp_path) is True

    def test_false_when_only_configs(self, tmp_path):
        (tmp_path / "configs").mkdir()
        assert wait_cr.has_local_runtime(tmp_path) is False


class TestFetchPrState:
    def test_builds_gh_argv_and_parses(self):
        seen = {}

        def runner(argv):
            seen["argv"] = argv
            return json.dumps({"headRefOid": "a" * 40, "state": "OPEN", "reviews": []})

        data = wait_cr.fetch_pr_state("o", "r", 7, runner=runner)
        assert seen["argv"] == [
            "pr",
            "view",
            "7",
            "--repo",
            "o/r",
            "--json",
            "reviews,headRefOid,state",
        ]
        assert data["headRefOid"] == "a" * 40

    def test_non_json_output_raises(self):
        with pytest.raises(wait_cr.GhQueryError):
            wait_cr.fetch_pr_state("o", "r", 7, runner=lambda argv: "not json")

    def test_missing_head_raises(self):
        with pytest.raises(wait_cr.GhQueryError):
            wait_cr.fetch_pr_state("o", "r", 7, runner=lambda argv: '{"reviews": []}')


class TestRunPrLoop:
    PR = ("o", "r", 7)
    HEAD = "a" * 40

    def snap(self, reviews=(), head=None, state="OPEN"):
        return {"headRefOid": head or self.HEAD, "state": state, "reviews": list(reviews)}

    def drive(self, snapshots, *, timeout=2100, poll=30, calls=None):
        """Feed snapshots to run_pr_loop with a fake clock; last one repeats."""
        calls = calls if calls is not None else {"n": 0}
        seq = list(snapshots)

        def fetch():
            index = min(calls["n"], len(seq) - 1)
            return seq[index]

        def fake_sleep(sec):
            calls["n"] += 1

        def fake_monotonic():
            return 1000.0 + calls["n"] * poll

        return wait_cr.run_pr_loop(
            self.PR,
            timeout=timeout,
            poll=poll,
            since_minutes=10,
            fetch=fetch,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )

    def test_converges_on_first_snapshot(self, capsys):
        rc = self.drive([self.snap([meta_review(self.HEAD, 1)])])
        out = capsys.readouterr().out
        assert rc == 0
        assert "review=PRR_1" in out

    def test_converges_after_waiting(self, capsys):
        rc = self.drive(
            [self.snap(), self.snap(), self.snap([meta_review(self.HEAD, 1)])]
        )
        assert rc == 0
        assert "converged" in capsys.readouterr().out

    def test_timeout_is_one_and_never_says_trigger_failed(self, capsys):
        rc = self.drive([self.snap()], timeout=60)
        err = capsys.readouterr().err
        assert rc == 1
        assert "timeout" in err
        assert "trigger failed" not in err

    def test_head_change_is_four(self, capsys):
        rc = self.drive([self.snap(), self.snap(head="b" * 40)])
        assert rc == 4
        assert "head moved" in capsys.readouterr().err

    def test_closed_pr_is_five(self, capsys):
        rc = self.drive([self.snap(), self.snap(state="MERGED")])
        assert rc == 5
        assert "MERGED" in capsys.readouterr().err

    def test_head_change_wins_over_matching_review(self, capsys):
        stale = meta_review(self.HEAD, 1)
        rc = self.drive([self.snap(), self.snap([stale], head="b" * 40)])
        assert rc == 4

    def test_startup_gh_failure_is_six(self, capsys):
        def fetch():
            raise wait_cr.GhQueryError("boom")

        rc = wait_cr.run_pr_loop(
            self.PR,
            timeout=60,
            poll=1,
            fetch=fetch,
            sleep=lambda sec: None,
            monotonic=lambda: 1000.0,
        )
        assert rc == 6
        assert "gh query failed" in capsys.readouterr().err

    def test_loop_gh_failure_recovers(self, capsys):
        state = {"n": 0}

        def fetch():
            state["n"] += 1
            if state["n"] == 2:
                raise wait_cr.GhQueryError("blip")
            if state["n"] == 1:
                return self.snap()
            return self.snap([meta_review(self.HEAD, 1)])

        ticks = {"n": 0}

        def fake_sleep(sec):
            ticks["n"] += 1

        rc = wait_cr.run_pr_loop(
            self.PR,
            timeout=2100,
            poll=30,
            fetch=fetch,
            sleep=fake_sleep,
            monotonic=lambda: 1000.0 + ticks["n"] * 30.0,
        )
        err = capsys.readouterr().err
        assert rc == 0
        assert "retrying" in err
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k "HasLocalRuntime or FetchPrState or RunPrLoop"`
Expected: FAIL（`AttributeError: ... has_local_runtime`）

- [ ] **Step 3: 写实现**

在 `format_review_summary` 之后加：

```python
def has_local_runtime(zima_home: Path) -> bool:
    """True when this host holds any zima PJob runtime state to watch.

    ``history/pjobs`` is the directory zima creates on first execution; its
    absence means no local execution can ever be observed, so waiting on it
    would only produce a misleading "nothing appeared" verdict.
    """
    return (Path(zima_home) / "history" / "pjobs").is_dir()


def _gh_runner(argv: list[str]) -> str:
    """Run one ``gh`` subcommand and return its stdout.

    The single subprocess call in the remote path, so tests can inject a fake
    runner and never touch the network.
    """
    try:
        proc = subprocess.run(
            ["gh", *argv],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhQueryError(f"gh could not run: {exc}") from exc
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = lines[-1] if lines else f"exit {proc.returncode}"
        raise GhQueryError(f"gh {' '.join(argv)} failed: {detail}")
    return proc.stdout


def fetch_pr_state(owner: str, repo: str, number: int, runner=_gh_runner) -> dict:
    """Read ``headRefOid`` + ``state`` + ``reviews`` for one pull request."""
    argv = [
        "pr",
        "view",
        str(number),
        "--repo",
        f"{owner}/{repo}",
        "--json",
        REVIEW_JSON_FIELDS,
    ]
    raw = runner(argv)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GhQueryError(f"unparseable gh output: {exc}") from exc
    if not isinstance(data, dict) or not data.get("headRefOid"):
        raise GhQueryError("gh output has no headRefOid")
    return data


def run_pr_loop(
    pr: tuple[str, str, int],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    poll: int = DEFAULT_POLL,
    since_minutes: int = DEFAULT_SINCE_MINUTES,
    fetch: Callable[[], dict] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    out: TextIO | None = None,
) -> int:
    """Poll GitHub until this round's review lands; return the exit code.

    The poll order is a contract: a head change or a closed PR invalidates the
    round *before* a matching review is accepted, so a review written for a
    superseded commit can never be reported as convergence.
    """
    if out is None:
        out = sys.stdout
    owner, repo, number = pr
    if fetch is None:
        def fetch() -> dict:
            return fetch_pr_state(owner, repo, number)

    not_before = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    deadline = monotonic() + timeout
    elapsed = 0

    snapshot: dict | None = None
    head_sha: str | None = None
    for attempt in range(1, GH_START_ATTEMPTS + 1):
        try:
            snapshot = fetch()
            head_sha = str(snapshot.get("headRefOid") or "")
            if head_sha:
                break
        except GhQueryError as exc:
            print(
                f"wait-cr: gh query failed ({attempt}/{GH_START_ATTEMPTS}): {exc}",
                file=sys.stderr,
            )
    if not head_sha:
        print(
            "wait-cr: cannot read the pull request; check `gh auth status` and "
            "the --pr reference",
            file=sys.stderr,
        )
        return 6

    while True:
        if snapshot is None:
            try:
                snapshot = fetch()
            except GhQueryError as exc:
                print(f"wait-cr: gh query failed, retrying: {exc}", file=sys.stderr)

        if snapshot is not None:
            state = str(snapshot.get("state") or "OPEN").upper()
            if state != "OPEN":
                print(
                    f"wait-cr: PR {owner}/{repo}#{number} is {state}; "
                    "nothing left to wait for",
                    file=sys.stderr,
                )
                return 5
            current = str(snapshot.get("headRefOid") or "")
            if current != head_sha:
                print(
                    f"wait-cr: head moved {head_sha[:12]} -> {current[:12]}; "
                    "this round was superseded, re-trigger and wait again",
                    file=sys.stderr,
                )
                return 4
            review = select_meta_review(
                snapshot.get("reviews") or [], head_sha, not_before
            )
            if review is not None:
                print(format_review_summary(review), file=out)
                return 0
            snapshot = None

        if monotonic() >= deadline:
            print(
                f"wait-cr: timeout after {timeout}s; no {owner}/{repo}#{number} "
                f"review for head {head_sha[:12]} since {not_before.isoformat()}",
                file=sys.stderr,
            )
            return 1

        print(
            f"[{elapsed:>5}s] waiting for a CR review on {owner}/{repo}#{number} "
            f"head {head_sha[:12]}",
            file=out,
            flush=True,
        )
        sleep(poll)
        elapsed += poll
```

同时把常量区补上 `REVIEW_JSON_FIELDS = "reviews,headRefOid,state"`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k "HasLocalRuntime or FetchPrState or RunPrLoop"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add pi/zima-pr-monitor/scripts/wait-cr.py tests/unit/test_wait_cr.py
git commit -m "feat(skill): remote wait loop for wait-cr --pr (#264)"
```

---

### Task 3: `main()` 模式分派与退出码

**Files:**
- Modify: `pi/zima-pr-monitor/scripts/wait-cr.py`（`_Parser` + `main()` 重写 + 模块 docstring 退出码表）
- Test: `tests/unit/test_wait_cr.py`（`TestMainLocal` / `TestMainRemote` / `TestUsage`）

**Interfaces:**
- Consumes: Task 1/2 的全部函数与 `DEFAULT_GRACE`
- Produces: `main(argv=None) -> int`，`_Parser`（argparse 用法错误 → 64）

- [ ] **Step 1: 写失败测试**

```python
class TestMainLocal:
    def test_missing_runtime_is_three_without_sleeping(self, tmp_path, capsys, monkeypatch):
        slept = []
        monkeypatch.setattr(wait_cr.time, "sleep", lambda sec: slept.append(sec))
        rc = wait_cr.main(
            ["some-code", "--zima-home", str(tmp_path), "--grace", "1", "--timeout", "1"]
        )
        err = capsys.readouterr().err
        assert rc == 3
        assert "no local zima runtime" in err
        assert "--pr" in err
        assert slept == []

    def test_existing_runtime_still_uses_local_loop(self, tmp_path, capsys):
        state_dir = tmp_path / "history" / "pjobs" / "code"
        state_dir.mkdir(parents=True)
        started = datetime.now(timezone.utc).isoformat()
        write_state(state_dir, "a", {"status": "success", "started_at": started})
        rc = wait_cr.main(
            ["code", "--zima-home", str(tmp_path), "--grace", "0", "--timeout", "5", "--poll", "1"]
        )
        assert rc == 0


class TestMainRemote:
    def test_converges_via_injected_fetch(self, monkeypatch, capsys):
        head = "a" * 40
        snap = {
            "headRefOid": head,
            "state": "OPEN",
            "reviews": [meta_review(head, 1)],
        }
        monkeypatch.setattr(wait_cr, "fetch_pr_state", lambda *a, **k: snap)
        rc = wait_cr.main(["--pr", "o/r#7", "--timeout", "30"])
        assert rc == 0
        assert "converged" in capsys.readouterr().out

    def test_startup_gh_failure_is_six(self, monkeypatch, capsys):
        def boom(*args, **kwargs):
            raise wait_cr.GhQueryError("not logged in")

        monkeypatch.setattr(wait_cr, "fetch_pr_state", boom)
        rc = wait_cr.main(["--pr", "o/r#7", "--timeout", "30"])
        assert rc == 6
        assert "gh query failed" in capsys.readouterr().err


class TestUsage:
    def test_no_mode_is_64(self, capsys):
        assert wait_cr.main([]) == 64
        assert "exactly one" in capsys.readouterr().err

    def test_both_modes_is_64(self, capsys):
        assert wait_cr.main(["code", "--pr", "o/r#7"]) == 64

    def test_remote_with_grace_is_64(self, capsys):
        assert wait_cr.main(["--pr", "o/r#7", "--grace", "5"]) == 64

    def test_remote_with_zima_home_is_64(self, tmp_path, capsys):
        assert wait_cr.main(["--pr", "o/r#7", "--zima-home", str(tmp_path)]) == 64

    def test_bad_pr_ref_is_64(self, capsys):
        assert wait_cr.main(["--pr", "o/r"]) == 64

    def test_argparse_error_is_64(self):
        with pytest.raises(SystemExit) as excinfo:
            wait_cr.main(["--pr", "o/r#7", "--timeout", "abc"])
        assert excinfo.value.code == 64
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k "TestMainLocal or TestMainRemote or TestUsage"`
Expected: FAIL（`--pr` 未定义 / 无 `_Parser`）

- [ ] **Step 3: 写实现**

把 `main()` 整体替换为：

```python
class _Parser(argparse.ArgumentParser):
    """Argparse that exits 64 on usage errors.

    Exit 2 already means "no execution appeared" in local mode, so the
    argparse default would collide with a runtime verdict.
    """

    def error(self, message):  # noqa: D401 - argparse contract
        self.print_usage(sys.stderr)
        self.exit(64, f"wait-cr: usage error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: pick the observation mode and run it."""
    parser = _Parser(
        description="Wait for a Zima CR round to finish (local state files or GitHub reviews)."
    )
    parser.add_argument("pjob_code", nargs="?", help="PJob code to wait for (local mode)")
    parser.add_argument(
        "--pr",
        metavar="OWNER/REPO#N",
        help="wait for the CR review of this pull request (remote mode)",
    )
    parser.add_argument(
        "--since-minutes",
        type=int,
        default=DEFAULT_SINCE_MINUTES,
        help="local: count executions started within N minutes; remote: accept reviews submitted within N minutes",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll", type=int, default=DEFAULT_POLL)
    parser.add_argument("--grace", type=int, default=None, help="local mode only")
    parser.add_argument(
        "--zima-home",
        type=Path,
        default=None,
        help="local mode only (default: $ZIMA_HOME or ~/.zima)",
    )
    args = parser.parse_args(argv)

    if bool(args.pjob_code) == bool(args.pr):
        print(
            "wait-cr: usage error: give exactly one of <pjob_code> or --pr owner/repo#N",
            file=sys.stderr,
        )
        return 64

    if args.pr:
        if args.grace is not None or args.zima_home is not None:
            print(
                "wait-cr: usage error: --grace/--zima-home only apply to local mode",
                file=sys.stderr,
            )
            return 64
        try:
            pr = parse_pr_ref(args.pr)
        except ValueError as exc:
            print(f"wait-cr: usage error: {exc}", file=sys.stderr)
            return 64
        return run_pr_loop(
            pr,
            timeout=args.timeout,
            poll=args.poll,
            since_minutes=args.since_minutes,
        )

    zima_home = args.zima_home or Path(os.environ.get("ZIMA_HOME") or Path.home() / ".zima")
    if not has_local_runtime(zima_home):
        missing = zima_home / "history" / "pjobs"
        print(
            f"wait-cr: no local zima runtime (missing {missing}); this host cannot "
            "watch PJob state — use --pr owner/repo#N to wait on GitHub reviews",
            file=sys.stderr,
        )
        return 3

    state_dir = zima_home / "history" / "pjobs" / args.pjob_code
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)
    return run_loop(
        state_dir=state_dir,
        cutoff=cutoff,
        timeout=args.timeout,
        poll=args.poll,
        grace=DEFAULT_GRACE if args.grace is None else args.grace,
    )
```

模块 docstring 换成 spec §4 的两种模式说明 + 退出码表（0/1/2/3/4/5/6/64），保留原有"strictly read-only"表述。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wait_cr.py -q`
Expected: PASS（既有 328 行用例 + 新增用例全绿）

- [ ] **Step 5: 提交**

```bash
git add pi/zima-pr-monitor/scripts/wait-cr.py tests/unit/test_wait_cr.py
git commit -m "feat(skill): wait-cr --pr mode and local fail-fast exit 3 (#264)"
```

---

### Task 4: 文档与文档契约测试

**Files:**
- Modify: `pi/zima-pr-monitor/SKILL.md`（§等待节律、§多执行流陷阱、§合并）
- Modify: `CLAUDE.md:9`
- Test: `tests/unit/test_wait_cr.py`（`TestSkillDocContract`）

**Interfaces:**
- Consumes: Task 3 定稿的退出码与命令形态
- Produces: 无代码接口；SKILL.md 的 `--pr 'owner/repo#N'` 与 exit 3/4/5/6 表格

- [ ] **Step 1: 写失败测试**

```python
SKILL_PATH = Path(__file__).resolve().parents[2] / "pi" / "zima-pr-monitor" / "SKILL.md"
CLAUDE_PATH = Path(__file__).resolve().parents[2] / "CLAUDE.md"


class TestSkillDocContract:
    def test_documents_both_wait_modes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "wait-cr.py <pjob-code>" in text
        assert "--pr 'owner/repo#N'" in text

    def test_documents_remote_exit_codes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        for code in ("| 3 |", "| 4 |", "| 5 |", "| 6 |"):
            assert code in text, code

    def test_keeps_foreground_blocking_rule(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "禁止结束 turn" in text
        assert "禁止后台监听" in text or "后台监听" in text

    def test_marks_pjob_ps_local_only(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "本地模式专属" in text

    def test_mode_choice_is_a_heuristic(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "启发式" in text

    def test_claude_md_mentions_both_channels(self):
        text = CLAUDE_PATH.read_text(encoding="utf-8")
        assert "history/pjobs" in text
        assert "reviews" in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wait_cr.py -q -k TestSkillDocContract`
Expected: FAIL（`--pr 'owner/repo#N'` 未出现在 SKILL.md）

- [ ] **Step 3: 改文档**

`SKILL.md` §等待节律替换为「先选模式 → 本地/远程两块 → 退出码表 → 时长表」：模式选择表按 `$ZIMA_HOME/history/pjobs` 是否存在分叉，并写明这是**启发式**、已知 CR 在别处触发时直接用 `--pr`；本地块保留现有步骤 1-4 并把 `zima pjob ps` 标为本地模式专属；远程块给出命令与「目标 head 上出现带 meta 的 review」判据；退出码表列出 0/1/3/4/5/6 及各自处置；时长表原样保留并说明两模式通用。

`SKILL.md` §多执行流陷阱：把 `zima pjob ps` 那句改成「本地模式专属：…；远程模式只能按触发时钟（<15min）推断，这不构成确定性检查」。

`SKILL.md` §合并：in-flight 检查按模式分叉，**保留** `TestMergeGate` 钉住的 `auto` / `design-only`、`gh pr merge <N> --squash --delete-branch`、「`stepwise` 档行为不变——收敛 + CI 全绿即合并」三句原样。

`CLAUDE.md:9` 把「block-waits read-only on `~/.zima/history/pjobs/<code>/<execution_id>.json`」改写为双通道：本地模式读 state 文件；远程 `--pr` 模式轮询 PR reviews（`pi-cr-meta` / `cc-cr-meta`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wait_cr.py tests/unit/test_issue_driven_contracts.py tests/unit/test_cr_batch_contracts.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add pi/zima-pr-monitor/SKILL.md CLAUDE.md tests/unit/test_wait_cr.py
git commit -m "docs(skill): document wait-cr topology split (#264)"
```

---

## Self-Review

- **Spec coverage**：§2 D1（Task 2/3）、D2（Task 1 `select_meta_review` + Task 3 传 `since_minutes`）、D3（Task 2 exit 4）、D4（Task 2 exit 5）、D5（Task 3 preflight）、D6（Task 2 启动重试 + 循环告警）、D7（Task 3 `_Parser`）、D8（不碰 `run_loop`）、§3.1-3.5（Task 1/2/3）、§4（Task 3 docstring + Task 4 文档）、§5.1-5.5（Task 4）、§7 A1-A13（Task 1-4 测试）、U1-U3（实现后人工执行）。
- **Placeholder scan**：无 TBD；每个 Task 的所有 step 都带可直接落地的代码或命令。
- **Type consistency**：`parse_pr_ref` 返回 3-tuple，Task 2 `run_pr_loop(pr=...)` 解包同一形状；`meta_review()` 测试工厂在 Task 1 定义，Task 2/3 复用；`REVIEW_JSON_FIELDS` 在 Task 2 常量区定义，Task 3 不重复定义。
- **Review Focus**：五类风险分别由 `TestSelectMetaReview.test_ignores_review_older_than_window`（时钟）、`TestRunPrLoop.test_head_change_wins_over_matching_review`（并发 push）、`TestMainRemote.test_startup_gh_failure_is_six`（gh 异常）、`TestUsage.test_argparse_error_is_64`（argparse 退出码）、`TestMainLocal.test_existing_runtime_still_uses_local_loop`（本地回归）钉住。

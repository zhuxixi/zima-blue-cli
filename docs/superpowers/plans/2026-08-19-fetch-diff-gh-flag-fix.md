# fetch-diff-gh-flag-fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `GitHubProvider.fetch_diff` 使用不存在的 gh flag 导致 pinned CR 路径必 skip 的 bug。

**Architecture:** 单点修复——`zima/providers/github.py` 的 `fetch_diff` 命令参数从 `pr view --patch` 改为 `pr diff`，同步修正测试断言。pinned/rescan 两调用方同函数受益，逻辑不动。

**Tech Stack:** Python 3.10+、pytest（unittest.mock）。

## Global Constraints

- 只动 2 个文件：`zima/providers/github.py`（1 行）+ `tests/unit/test_providers_github.py`（1 处断言）
- 不动重试逻辑、SkipAction、rescan/pinned 分支的其他行为
- commit 用 conventional commits
- 工作目录：`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-164-fix-fetch-diff-gh-flag`（本文件相对路径相对此目录）

---

### Task 1: fetch_diff 命令修正（TDD）

**Files:**
- Modify: `zima/providers/github.py:86-91`（fetch_diff 的 `_run` 参数）
- Modify: `tests/unit/test_providers_github.py:110-118`（test_fetch_diff 断言）

**Interfaces:**
- Consumes: `GitHubProvider._run(args, capture=True, check=False)`（既有，不变）
- Produces: `fetch_diff(repo, issue) -> str` 语义不变（成功返回 patch、失败返回 ""）；只有命令参数变化。pinned（actions_runner L376）与 rescan（L412）调用方无需改动。

- [ ] **Step 1: 改测试断言为正确命令（先写失败测试）**

`tests/unit/test_providers_github.py` `test_fetch_diff`（L110-118）改为：

```python
            assert args == [
                "gh",
                "pr",
                "diff",
                "123",
                "--repo",
                "owner/repo",
            ]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-164-fix-fetch-diff-gh-flag
uv run pytest tests/unit/test_providers_github.py::TestGitHubProvider::test_fetch_diff -v
```
Expected: FAIL（断言不匹配，实现仍为 `pr view --patch`）

- [ ] **Step 3: 改实现**

`zima/providers/github.py` `fetch_diff` 内：

```python
        result = self._run(
            ["pr", "diff", issue, "--repo", repo],
            capture=True,
            check=False,
        )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/unit/test_providers_github.py -v
```
Expected: PASS（全部 provider 测试，含 failure 分支）

- [ ] **Step 5: Commit**

```bash
git add zima/providers/github.py tests/unit/test_providers_github.py
git commit -m "fix(webhook): use gh pr diff in fetch_diff (pr view --patch is not a flag)"
```

---

### Task 2: 全量验证收尾

**Files:** 无新增。

- [ ] **Step 1: 全量测试**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-164-fix-fetch-diff-gh-flag
uv run pytest tests/ -q
```
Expected: PASS（933+ 全绿）

- [ ] **Step 2: spec/plan commit**

```bash
git add docs/superpowers/specs/2026-08-19-fetch-diff-gh-flag-fix-design.md docs/superpowers/plans/2026-08-19-fetch-diff-gh-flag-fix.md
git commit -m "docs: spec + plan for fetch_diff gh flag fix (#164)"
```

- [ ] **Step 3: push + PR**

```bash
git push -u origin issue-164-fix-fetch-diff-gh-flag
gh pr create --base main --head issue-164-fix-fetch-diff-gh-flag \
  --title "fix(webhook): fetch_diff uses gh pr diff (pr view --patch is not a flag)" \
  --body "## Summary

Closes #164.

- \`fetch_diff\` 命令从 \`gh pr view <n> --patch\`（不存在的 flag）改为 \`gh pr diff <n>\`
- 同步修正 \`test_fetch_diff\` 的坏断言（该断言把 bug 固化了）
- pinned CR 路径不再误 skip；rescan 路径 pr_diff 首次有真实值（示例模板 \`{{pr_diff}}\` 开始生效，1MB cap 不触发）

## Test

\`uv run pytest tests/ -q\` 全绿

## Notes

- 0.7.1 首次真实 webhook CR 触发暴露（PR #162 现场，见 #164 evidence）
- 修复方向已在真实链路验证（22:06 热修实测 fetch_diff 成功 → agent spawn）"
```

- [ ] **Step 4: 打标签触发 CR**

```bash
gh pr edit <新PR号> --add-label zima:needs-review
```

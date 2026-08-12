# 实现计划 — Webhook 多仓库路由 (#145)

参照 spec `docs/superpowers/specs/2026-08-12-webhook-multi-repo-routing-design.md`。

## Task 1 — `payload.py`：暴露 repo 校验

- [ ] 新增 `is_valid_repo(value: str) -> bool`（复用 `_VALID_REPO`）。
- **验证**: `uv run pytest tests/unit/test_webhook_payload.py`（既有全绿）+ 新增 1 个 `test_is_valid_repo` 单测覆盖合法/非法/大小写。

## Task 2 — `server.py`：路由模型 + trigger_pjobs（TDD 先写测试）

- [ ] `TestTriggerPjobs` 新增用例（先红）：
  - `test_trigger_routes_only_matching_repo`：3 路由（A→repo1, B→repo2, C→repo1），事件 repo=repo2 → 仅 B 被 spawn。
  - `test_trigger_broadcast_when_repo_none`：路由 repo 全 None → 全部 spawn（向后兼容）。
  - `test_trigger_routes_no_match_ignored`：事件 repo 不在任何绑定 → 零 spawn，stderr 有 "matched no" 日志。
  - `test_trigger_routes_case_insensitive`：`PjobRoute("a","Owner/Repo")` 匹配事件 `owner/repo`。
  - `test_trigger_routes_dedup_still_works`：路由模式下重复 (event,code) 去重。
- [ ] 引入 `@dataclass PjobRoute(code, repo|None)`、`_route_matches`。
- [ ] 改 `trigger_pjobs(event, routes)`：按 spec §3.5 路由 + 零匹配日志。
- [ ] 改 `WebhookRequestHandler.pjob_routes` ClassVar；`do_POST` 中 `triggered=list(statuses.keys())`。
- [ ] 改 `make_handler(routes, ...)`、`run_server(port, routes, ...)`。
- **验证**: `uv run pytest tests/unit/test_webhook_server.py -v` 全绿。

## Task 3 — `server.py` HTTP handler 路由测试（TDD）

- [ ] `TestWebhookRequestHandler`：`make_handler` 改传 `routes`；既有 `test_valid_labeled_event` 改用 `routes=[PjobRoute("claude-cr")]`（广播）保持绿。
- [ ] 新增 e2e 风格用例（单测内）：两条路由不同 repo，事件只触发匹配那条。
- **验证**: `uv run pytest tests/unit/test_webhook_server.py tests/integration/test_webhook_end_to_end.py -v`。

## Task 4 — `commands/webhook.py`：`--repo` 选项 + 配对校验

- [ ] 加 `repo: List[str] = typer.Option([], "--repo", ...)`。
- [ ] 校验：`repo` 非空时 `len(repo)==len(pjob)`，否则退出 1 + 明确文案；每个 repo 过 `is_valid_repo`。
- [ ] 构建 `routes`：无 repo → `[PjobRoute(c, None) for c in pjob]`；有 → `zip` 配对。
- [ ] `run_server(port=port, routes=routes, ...)`。
- **验证**: `uv run pytest tests/integration/test_webhook_command.py -v`；新增用例：
  - `test_repo_paired_with_pjob_accepted`（合法配对通过校验，mock run_server）
  - `test_repo_count_mismatch_fails`
  - `test_invalid_repo_value_fails`
  - `test_help_shows_repo_option`

## Task 5 — 同步 e2e 集成测试

- [ ] `tests/integration/test_webhook_end_to_end.py`：`make_handler` 改 `routes=[PjobRoute("claude-cr"), PjobRoute("kimi-cr")]`（广播，保留"触发两者"语义）。
- [ ] 新增 `test_labeled_event_routes_by_repo`：两路由不同 repo，事件只触发匹配的。
- **验证**: `uv run pytest tests/integration/test_webhook_end_to_end.py -v`。

## Task 6 — 文档

- [ ] `examples/webhook/README.md`：加"多仓库路由"小节 + 示例命令。
- [ ] `AGENTS.md` webhook 段（约 L114-121）：补 `--repo` 路由说明。
- [ ] `CLAUDE.md` Webhook Server gotcha：补路由/向后兼容行为。
- **验证**: 人工通读三处一致。

## Task 7 — 全量验证

- [ ] `uv run black zima/ tests/ --line-length 100`
- [ ] `uv run ruff check zima/ tests/`
- [ ] `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
- **Gate**: 三者全绿才进 CR。

## Task 8 — 本地 CR → PR → 双 bot CR

- [ ] `feature-dev:code-reviewer`（或 `/code-review`）过改动。
- [ ] 修复后 commit、push、开 PR（base main）、打 `zima:needs-review`。
- [ ] zima-pr-monitor babysit → 收敛 → 合并 → 退出 worktree（remove）+ prune。

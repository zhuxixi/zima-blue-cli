---
name: github-code-review-batch
description: |
  对 GitHub Pull Request 进行批量/调度式代码审查（一次性短会话，非监听模式），
  Claude Code 端。多 Agent 并行检查 CLAUDE.md / AGENTS.md 合规性、bug 和逻辑安全问题，
  通过 issue 验证机制过滤误报。状态通过 PR 评论的 metadata 持久化，
  供外部调度器（如 zima daemon）交替调度 CR/fix agent。

  Use when: 用户要求对指定 PR 进行一次性批量审查或调度式审查，
  且不希望启动后台监听进程。
  
  触发词: "batch review pr", "review pr batch", "scheduled review pr"
---

# GitHub Code Review Batch (Claude Code)

GitHub PR 批量/调度代码审查工具，**非监听模式**。

本 Skill 是**双 CR Agent 交叉验证体系**的一部分：Claude Code 和 Kimi CLI 分别独立审查同一 PR，互相校验审查结论。两个 Agent 的审查结果通过各自的 HTML metadata（`cc-cr-meta` / `kimi-cr-meta`）独立持久化，**互不干扰**——两边读取评论流时严格忽略对方的 metadata 评论，保证交叉验证的独立性。

**与监听模式的区别**：
- 每次调用都是独立短会话，执行完立即结束，不启动 background watcher
- 状态完全通过 PR 评论中的 HTML metadata 持久化，下次调用时恢复
- 适用于外部调度器交替调度 CR agent 和 fix agent 的场景
- 每次结束输出机器可读的【状态报告】，供调度器决策是否继续调度 fix agent

## 触发与 PR 编号提取

> **⚠️ 触发短语是外部契约**：调度器（zima daemon）通过 skill 名 + 字面短语 `"batch review pr"` / `"review pr batch"` / `"scheduled review pr"` 调用本 skill。改动这些字面短语会破坏外部调度契约——优化 description 时务必保留这三个短语原文。

支持的调用方式：

```
batch review pr
batch review pr #123
review pr batch 456
scheduled review pr owner/repo#101
```

PR 编号提取规则（依次尝试）：
- `#123` 格式
- 直接数字 `456`
- `owner/repo#123` 格式
- 都未提供 → 使用 `Bash` 执行 `gh pr view --json number` 获取当前分支关联的 PR
- 当前分支也无关联 PR → 提示用户明确提供 PR 编号

## 前置要求

1. **GitHub CLI (`gh`)** 已安装并认证：`gh --version` / `gh auth status`，需要对仓库的读取和评论权限
2. 当前目录在 Git 仓库中且有 GitHub remote（`git remote -v` 验证）
3. **Python 3** 可用（用于运行 `scripts/` 下的辅助脚本）

## 主流程总览

执行流程是一个 11 步状态机。SKILL.md 仅给出骨架，遇到任何一步规则不清楚时，read 对应 reference 小节。

| 步骤 | 目的 | 详细规则 |
|------|------|----------|
| Step 0 | 检测 previous metadata，判断首次/增量审查 | [flow.md#step-0](references/flow.md#step-0) |
| Step 0.2a | 解析 committer 对历史 issues 的回应（wontfix / resolved / clarified） | [flow.md#step-0-2a](references/flow.md#step-0-2a) |
| Step 1 | PR 资格审查（closed/draft/trivial 检查） | [flow.md#step-1](references/flow.md#step-1) |
| Step 2 | 收集 CLAUDE.md / AGENTS.md（含子目录） | [flow.md#step-2](references/flow.md#step-2) |
| Step 3 | summarizer 生成变更摘要 | [flow.md#step-3](references/flow.md#step-3), [subagent-prompts.md#summarizer](references/subagent-prompts.md#summarizer) |
| Step 3.5 | diff 预处理（过滤测试文件 + 长度兜底） | `scripts/compress_diff.py` |
| Step 4 | 5 个并行审查 Agent | [subagent-prompts.md](references/subagent-prompts.md) |
| Step 5 | issue-validator 并行验证 | [subagent-prompts.md#issue-validator](references/subagent-prompts.md#issue-validator) |
| Step 6 | 过滤 + 去重 + 优先级排序 | [flow.md#step-6](references/flow.md#step-6) |
| Step 7 | 最终资格审查（防止给已关闭 PR 发评论） | [flow.md#step-7](references/flow.md#step-7) |
| Step 8 | 终端输出 Markdown 报告 | [flow.md#step-8](references/flow.md#step-8) |
| Step 9 | 构建并发布 PR Review 评论（含 metadata） | `scripts/build_review_body.py` |
| Step 10 | 输出机器可读状态报告 | `scripts/render_status_report.py` |

**增量审查分支**：[Step 0](references/flow.md#step-0) 检测到有新 commit 且存在上一轮 metadata 时，跳过 Step 3-5，改用单个 delta-reviewer agent。流程详见 [delta-review.md](references/delta-review.md)。

## 关键约束（why 优先）

- **`Bash` 执行所有 `gh` 和 `git` 命令**：保持环境无关性。`gh` CLI 是不依赖 MCP 的最大公约数，跨调度器/容器/裸机都能跑
- **`Agent` 启动所有审查/验证 sub-agent**：本 skill 需要的并行+独立上下文执行语义，其他工具（如内联 LLM 调用）保证不了
- **不依赖任何 MCP 工具（如 `pull_request_read`、`add_issue_comment`）**：保持 skill 在不同环境间可移植，避免对接环境时被 MCP 配置卡住
- **每轮发布新评论，不编辑旧评论**：metadata 是审查历史的事实记录，覆写会丢失中间状态——下游 fix agent 与人类 reviewer 都依赖完整的轮次链
- **Acknowledged issues 不计入 open**：尊重 committer 决策，避免跨轮反复打扰；调度器只对真正 open 的 issues 调度 fix agent

## 输出契约

每次执行（除 [Step 1](references/flow.md#step-1)/[Step 7](references/flow.md#step-7) 提前终止外）必须产出三个产物：

1. **终端 Markdown review 报告**（[Step 8](references/flow.md#step-8)）
2. **PR 评论**（[Step 9](references/flow.md#step-9)）：由 `scripts/build_review_body.py` 生成，包含 `<!-- cc-cr-meta ... -->` 机器可读 header + 人类可读 Round-N 部分。完整样例见 [output-examples.md](references/output-examples.md)
3. **终端状态报告**（[Step 10](references/flow.md#step-10)）：由 `scripts/render_status_report.py` 生成，三态：
   - `NEEDS_FIX` — 仍有 open issues 需要修复
   - `PASS` — 无 open issues（可能有 acknowledged）
   - `NO_NEW_COMMITS` — Step 0 检测到无新 commit，本轮跳过
   - 状态报告还含 `Critical issues:` 计数与派生的 `Verdict:`（#119：SKIP / BLOCK_MERGE / READY_TO_MERGE / MERGE_WITH_CAUTION），均追加在 `Status:` 行之后，不影响 grep

zima daemon 通过 grep `Status: <state>` 决策下一步动作（可选消费 `Verdict:` 优先处理含 critical 的 PR）。

## SubAgent 概览

| Agent | 职责 | 并发数 |
|-------|------|--------|
| summarizer | 摘要 PR 变更意图 | 1 |
| claude-compliance-checker | 检查 CLAUDE.md 合规 | 2（独立运行交叉验证） |
| agents-compliance-checker | 检查 AGENTS.md 合规 | 1 |
| bug-scanner | 扫描 bug、缺失导入、未解析引用 | 1 |
| logic-analyzer | 逻辑/安全分析、资源泄漏、竞态 | 1 |
| issue-validator | 验证 issue 是否值得保留 | 每个候选 issue 1 个 |
| delta-reviewer | 增量审查（替代上述 Step 3-5） | 1（仅增量模式） |

每个 agent 的输入契约、输出 schema、prompt 模板：[subagent-prompts.md](references/subagent-prompts.md)。

## 边界情况与故障排除

完整边界情况表（22 条）+ 故障排除（4 类）+ 常见误报类型（6 种）见 [edge-cases.md](references/edge-cases.md)。

几条最容易遇到的：
- 无新 commit 时：Step 0 直接输出状态报告 `NO_NEW_COMMITS` 退出
- Metadata 完全无法解析：**报错并停止**，不静默 fallback 到 Round-1（避免破坏调度器状态机）
- 审查中途 PR 被关闭：Step 7 拦截，不发布评论
- 所有 issues 都被 committer acknowledged：状态报告输出 `PASS`

## 常用 gh 命令

```bash
gh pr view --json number                                        # 当前分支关联 PR
gh pr view <PR>                                                 # PR 详情
gh pr view <PR> --comments                                      # 所有评论（用于 Step 0.2a）
gh pr view <PR> --json reviews                                  # review 评论（喂给 parse_metadata.py）
gh pr view <PR> --json state                                    # PR 状态（Step 7 二次检查）
gh pr view <PR> --json headRefOid --jq '.headRefOid'            # head SHA（40 字符）
gh pr view <PR> --json headRepositoryOwner,headRepository       # 仓库信息（构建链接）
gh pr diff <PR>                                                 # 完整 diff
gh pr diff <PR> --name-only                                     # 变更文件列表（Step 2）
gh pr review <PR> --comment --body-file /tmp/cc-cr-{pr}.md      # 发布 review 评论
```

## 限制说明

1. 仅支持 GitHub 仓库（不支持 GitLab、Bitbucket）
2. 依赖 `gh` CLI 与 Python 3
3. 极大 PR（>1000 行）的审查可能不够全面
4. 不能替代完整的测试套件和人工代码审查
5. 非代码文件变更（图片、二进制）无法有效审查
6. 仅静态分析，不执行代码或运行测试
7. 非监听模式：多轮修复依赖外部调度器交替调度 CR agent 和 fix agent

## 设计原理

1. **多 Agent 并行**：从不同角度独立审查，避免单一视角的盲区
2. **冗余检查**：两个 CLAUDE.md checker 独立运行交叉验证
3. **Issue 验证**：每个发现的问题都经过独立验证，大幅降低误报率
4. **HIGH SIGNAL**：只报告高置信度的问题，避免噪音淹没真正重要的问题
5. **终端与 PR 同步**：终端输出和 PR 评论完全一致，确保透明性
6. **进阶披露**：SKILL.md 只载骨架，详细规则在 references/，确定性逻辑在 scripts/

# Issue #29 Refinement & Borobo Launch Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine issue #29 into actionable sub-issues on GitHub, then scaffold the borobo project as the first implementation step.

**Architecture:** borobo is a separate GitHub repo — a FastAPI-based GitHub App bot that receives webhooks, manages FSM state via `zima:*` labels, and dispatches tasks to the running zima daemon. It shares `~/.zima/` as the data contract.

**Tech Stack:** GitHub CLI (`gh`), Python 3.10+, FastAPI, PyJWT, PyGithub

> ⚠️ **Outdated Reference (Issue #43)**: This document references `~/.zima/agents/<code>/logs/` for execution results. The actual implementation uses the system temp directory (`zima-pjobs/`) and stores history centrally in `~/.zima/history/pjobs.json`. See [AGENTS.md](../../../AGENTS.md) for the accurate data layout.

---

## Task 1: Update issue #29 with refined spec

**Files:**
- None (GitHub issue update only)

- [ ] **Step 1: Update issue #29 body with refined description**

Replace the current issue body with a condensed version pointing to the spec and sub-issues:

```bash
gh issue edit 29 --body "$(cat <<'EOF'
## Borobo: GitHub App Bot for Automated Dev Workflow

> **Design Spec:** `docs/superpowers/specs/2026-04-20-issue-29-borobo-design.md`
> **JFox Note:** [202604191043230289] GitHub CR Bot 生态分析

### 目标

将 issue #29 的宏大愿景拆解为可执行的子项目。核心思路：

- **borobo** (新仓库): GitHub App bot，接收 webhook，管理 FSM 状态机，调度 zima daemon
- **zima-blue-cli** (现有): Agent 调度引擎，不感知 GitHub

### 工作流程

```
brainstorm (human) → needs-spec → needs-plan → needs-impl → needs-review → needs-fix → needs-test → done
                     ──issue labels──▶          ──PR events──▶                            ──human──▶
```

### Sub-Issues

- [ ] Sub 1: borobo 项目骨架 (GitHub App + Webhook 验签)
- [ ] Sub 2: FSM 状态机引擎
- [ ] Sub 3: Issue 事件处理 (spec → plan → impl)
- [ ] Sub 4: PR 事件处理 (review → fix → test)
- [ ] Sub 5: borobo ↔ zima daemon 集成
- [ ] Sub 6: 多仓库配置系统

### 依赖关系

```
Sub1 → Sub2 → Sub3 ─┐
               Sub4 ─┤→ Sub5
               Sub6 ─┘
```

### 约束

- 单台 Ubuntu 服务器，单体部署
- CLI subprocess 执行模型 (Claude Code / Kimi CLI)
- 文件持久化 (JSONL/JSON)
- 多仓库支持
- borobo 和 zima 是独立仓库，通过 `~/.zima/` 共享数据

---

_原 issue 内容已归档到设计文档中。_
EOF
)"
```

- [ ] **Step 2: Add labels to issue #29**

```bash
gh issue edit 29 --add-label "enhancement"
```

(Issue already has `enhancement` — verify it's still there.)

- [ ] **Step 3: Verify issue update**

```bash
gh issue view 29 --json title,labels,body --jq '.title, (.labels | map(.name)), (.body | length)'
```

Expected: title unchanged, body length > 500, labels contain `enhancement`

---

## Task 2: Create sub-issues

**Files:**
- None (GitHub issue creation only)

- [ ] **Step 1: Create Sub 1 — borobo 项目骨架**

```bash
gh issue create --title "Sub 1: borobo 项目骨架 (GitHub App + Webhook)" --body "$(cat <<'EOF'
## 目标

初始化 borobo Python 项目，实现最小可运行的 GitHub App Webhook 接收端。

## 验收标准

- [ ] FastAPI 应用能启动并监听 8000 端口
- [ ] GitHub App 注册完成，获取 App ID 和 Private Key
- [ ] Webhook 接收端点 (`POST /webhook`) 能验签 (`X-Hub-Signature-256`)
- [ ] JWT 生成 + Installation Token 换取可工作
- [ ] 收到 webhook 后打印事件类型和 payload
- [ ] `pyproject.toml` 配置完整 (hatchling, 依赖声明)
- [ ] 基本测试覆盖 (签名验证、JWT 生成)

## 技术要点

- FastAPI + uvicorn
- PyJWT + cryptography (GitHub App 私钥签名)
- Webhook Secret 验签 (HMAC-SHA256)
- smee.io 用于本地开发代理

## 关联

- Parent: #29
- Design: `docs/superpowers/specs/2026-04-20-issue-29-borobo-design.md`
- JFox Note: 202604191043230289 (包含完整的 GitHub App 技术详解)
EOF
)" --label "enhancement"
```

- [ ] **Step 2: Create Sub 2 — FSM 状态机引擎**

```bash
gh issue create --title "Sub 2: FSM 状态机引擎" --body "$(cat <<'EOF'
## 目标

实现 borobo 的 FSM 状态机，管理 issue 生命周期状态转换。

## 验收标准

- [ ] 状态定义：8 个状态 (open, needs-spec, needs-plan, needs-impl, needs-review, needs-fix, needs-test, done)
- [ ] 转换规则：每个转换有明确的触发来源和 guard 条件
- [ ] 事件日志：所有状态转换记录到 JSONL
- [ ] Label 管理：通过 GitHub API 读写 `zima:*` 标签
- [ ] 循环保护：`needs-fix → needs-review` 最多 3 次
- [ ] 超限处理：超过 3 次循环发 issue comment 通知人工
- [ ] 测试覆盖：每个转换、guard、循环保护

## 状态转换图

```
(open)            → zima:needs-spec
zima:needs-spec   → zima:needs-plan      [guard: spec in issue body]
zima:needs-plan   → zima:needs-impl      [guard: plan file committed]
zima:needs-impl   → zima:needs-review    [guard: PR linked to issue]
zima:needs-review → zima:needs-fix       [guard: review has issues]
zima:needs-review → zima:needs-test      [guard: review approved]
zima:needs-fix    → zima:needs-review    [guard: max 3 cycles]
zima:needs-test   → zima:done            [guard: human confirmed]
```

## 关联

- Parent: #29
- Depends on: Sub 1
EOF
)" --label "enhancement"
```

- [ ] **Step 3: Create Sub 3 — Issue 事件处理**

```bash
gh issue create --title "Sub 3: Issue 事件处理 (spec → plan → impl)" --body "$(cat <<'EOF'
## 目标

处理 `issues.labeled` 事件，驱动 spec → plan → impl 阶段的状态转换。

## 验收标准

- [ ] `issues.labeled` 事件路由到 FSM engine
- [ ] Guard 条件检查：issue body 含 spec 段落 / plan 文件存在
- [ ] 触发 zima daemon 任务注入（或创建 PJob 配置）
- [ ] 转换后自动更新 GitHub labels (`zima:*`)
- [ ] 转换后发 issue comment 记录状态变化
- [ ] 测试覆盖

## 事件源

- `issues.labeled` — 标签添加时触发
- 检查标签是否为 `zima:*` 前缀，忽略其他标签

## 关联

- Parent: #29
- Depends on: Sub 2
EOF
)" --label "enhancement"
```

- [ ] **Step 4: Create Sub 4 — PR 事件处理**

```bash
gh issue create --title "Sub 4: PR 事件处理 (review → fix → test)" --body "$(cat <<'EOF'
## 目标

处理 `pull_request.opened` / `synchronize` 事件，驱动 review → fix → test 阶段。

## 验收标准

- [ ] `pull_request.opened` 触发 code review
- [ ] `pull_request.synchronize` 触发 re-review (fix 后)
- [ ] PR ↔ Issue 关联 (解析 `Closes #N` 或 GitHub linked PRs)
- [ ] Review 结果解析 → `needs-fix` 或 `needs-test`
- [ ] 循环计数与超限处理 (max 3)
- [ ] 超限时发 issue comment 通知人工
- [ ] 测试覆盖

## 事件源

- `pull_request.opened` — PR 创建
- `pull_request.synchronize` — PR 有新 commit
- `pull_request_review.submitted` — Review 提交 (可选)

## 关联

- Parent: #29
- Depends on: Sub 2
EOF
)" --label "enhancement"
```

- [ ] **Step 5: Create Sub 5 — borobo ↔ zima daemon 集成**

```bash
gh issue create --title "Sub 5: borobo ↔ zima daemon 集成" --body "$(cat <<'EOF'
## 目标

实现 borobo 与 zima daemon 的双向交互：任务注入、去重决策、结果读取。

## 验收标准

- [ ] 读取 zima configs (`~/.zima/configs/pjobs/`, `schedules/`) 理解 PJob 覆盖范围
- [ ] 去重决策：daemon 是否已覆盖当前 repo/event
- [ ] 任务注入机制：写入 queue 目录或 API 调用
- [ ] 新 PJob 注册：为未覆盖的 repo 生成配置
- [ ] 读取执行结果 (`~/.zima/agents/<code>/logs/`)
- [ ] 测试覆盖

## 关联

- Parent: #29
- Depends on: Sub 3, Sub 4
- 需要细化：与 zima daemon 的具体交互协议待设计
EOF
)" --label "enhancement"
```

- [ ] **Step 6: Create Sub 6 — 多仓库配置系统**

```bash
gh issue create --title "Sub 6: 多仓库配置系统" --body "$(cat <<'EOF'
## 目标

实现 per-repo 配置系统，支持不同仓库使用不同的 FSM 规则和 PJob 映射。

## 验收标准

- [ ] 配置文件格式设计 (YAML, 存放在 `configs/repos/`)
- [ ] 每个 repo 独立的 FSM 规则和 PJob 映射
- [ ] Repo 注册/注销 API 或 CLI
- [ ] 配置热加载 (无需重启 borobo)
- [ ] 测试覆盖

## 配置示例

```yaml
repo: zhuxixi/zima-blue-cli
fsm:
  enabled: true
  labels_prefix: "zima:"
pjob_mapping:
  needs-plan: write-plan-pjob
  needs-impl: subagent-impl-pjob
  needs-review: code-review-pjob
  needs-fix: fix-pjob
```

## 关联

- Parent: #29
- Depends on: Sub 2
EOF
)" --label "enhancement"
```

- [ ] **Step 7: Verify all sub-issues created**

```bash
gh issue list --state open --label enhancement --json number,title --jq '.[] | "\(.number): \(.title)"'
```

Expected: issue #29 + 6 new sub-issues visible

---

## Task 3: Commit the spec document

**Files:**
- New: `docs/superpowers/specs/2026-04-20-issue-29-borobo-design.md`

- [ ] **Step 1: Stage and commit the spec**

```bash
git add docs/superpowers/specs/2026-04-20-issue-29-borobo-design.md
git commit -m "docs(spec): add borobo GitHub App bot design for issue #29"
```

- [ ] **Step 2: Verify commit**

```bash
git log --oneline -1
```

Expected: commit message matches

---

## Task 4: Commit this plan document

**Files:**
- New: `docs/superpowers/plans/2026-04-20-issue-29-borobo-plan.md`

- [ ] **Step 1: Stage and commit the plan**

```bash
git add docs/superpowers/plans/2026-04-20-issue-29-borobo-plan.md
git commit -m "docs(plan): add issue #29 refinement and borobo launch plan"
```

- [ ] **Step 2: Verify commit**

```bash
git log --oneline -1
```

Expected: commit message matches

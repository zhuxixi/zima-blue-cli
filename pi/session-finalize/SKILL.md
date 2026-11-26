---
name: session-finalize
description: |
  会话收尾编排：回放当前会话旅程 → 归纳主线任务并确认是否结束 → 已结束则依次执行
  jfox-session-to-permanent 与 jfox-session-summary → 展示总结与写入结果。
  Use when the user wants to wrap up or finalize the current session, save it to the
  knowledge base, or says "finalize", "session finalize", "会话收尾", "收尾", "结束会话",
  "沉淀这个会话".
  Triggers: "finalize", "session finalize", "会话收尾", "收尾", "结束会话", "沉淀这个会话".
---

# Session Finalize

会话收尾的唯一入口：先把「这个会话干了什么」讲清楚，确认主线是否结束，结束后把现状与历史沉淀进 jfox，最后展示写入结果。本技能只做编排，不改 `jfox-session-to-permanent` / `jfox-session-summary` 的规则。

## 何时使用

- 用户说 `finalize`、`session finalize`、`会话收尾`、`收尾`、`结束会话`、`沉淀这个会话`
- 长会话结束前，用户想先看旅程再决定是否沉淀

## 前置检查（第 0 段）

逐项检查，任一失败即停并给出指引：

1. `jfox kb current --json` 必须成功；失败 → 提示先用 `/skill:jfox-common` 初始化知识库。
2. 可用技能列表里必须同时有 `jfox-session-to-permanent` 与 `jfox-session-summary`；缺任一 → 提示安装 jfox pi 技能包。
3. `question` 工具可用（由 pi 本地扩展提供）；不可用时**不停止**，本次所有选择题降级为文本提问，并在报告首行注明 `question 不可用，已降级为文本提问`。
4. 读 `$PI_SESSION_FILE`；为空或文件不存在 → **不停止**，第 1 段降级（见「失败与降级」）。

## 第 1 段：旅程回放

运行技能目录下的脚本（必须用绝对路径 + `python3` 前缀；触发会话的 cwd 通常是别的项目）：

```bash
python3 <skill-dir>/scripts/session_journey.py --file "$PI_SESSION_FILE" --json
```

读取 JSON 后，用中文写 3–8 个阶段：

```markdown
本会话共 <N> 轮、跨 <时长>，改动 <M> 个文件。

### 阶段 1 — <一句话诉求>
- 诉求：<用户原话摘要>
- 动作：bash ×12、read ×8、edit ×5；写入 a.py / b.md
- 结论：<该阶段最后一条 assistant 叙述>
```

纪律：

- 只呈现「用户在推动什么、做了什么、落到哪里」，不复述 toolResult，不读 `thinking`。
- 阶段划分以用户消息为边界；脚本已按「合并最短相邻对」处理超过 8 个阶段的情况。
- 每阶段最多 3 条 bullet，单条不超过 120 字。

降级：`$PI_SESSION_FILE` 为空、文件不存在或脚本失败时，用当前会话上下文 + `git status --short` 回放，并输出一行 `旅程回放降级：未找到会话文件`（脚本失败时改为 `旅程回放降级：脚本不可用`）。降级不阻止后续段落。

## 第 2 段：主线判定

先给结论，再列证据：

```markdown
主线：<一句话，动词开头，说明这个会话要达成的结果>

当前进度：
- <证据 1>
- <证据 2>

这条主线是否已经结束？
```

证据来源顺序：会话内 todo → `git status --short` / `git log --oneline -5` → `gh pr view`（若涉及 PR）→ issue 状态。取不到的证据标注「未确认」，不编造。

然后用 `question` 工具提问，三个选项：`已结束` / `未结束` / `其他`。

- **已结束** → 进入第 3 段。
- **未结束** → 只输出「未收尾」报告（主线 / 卡点 / 下一步），再问一次：`只报状态` / `也写 session 笔记`。默认不写任何笔记；用户选后者时只走 `jfox-session-summary`，**不写 permanent**。
- **其他** → 请用户说明，按说明处置后重新提问。

## 第 3 段：执行沉淀

顺序固定：先 permanent，后 summary。

### 3.1 幂等检查

```bash
jfox list --type session --limit 200 --format json --include-archived
```

按 `$PI_SESSION_FILE` 匹配 `session_file`：

| 结果 | 处置 |
|------|------|
| 命中（活跃） | `question`：更新已有笔记 / 跳过 session 笔记 / 另建一条 |
| 命中（已归档） | 同样三选一，并提示该笔记已归档 |
| 未命中 | 按标题 `jfox search "Session: <topic>" --type session` 二次匹配；仍无 → 直接继续 |
| 老笔记无 `session_file` | 退化为标题匹配 `Session: <topic>`；仍无结论则继续 |

扫最近 200 条；活跃 + 归档超过 200 条时明确提示「可能漏检」，不得静默新建。

### 3.2 permanent

按名定位已安装的 `jfox-session-to-permanent` skill，读其 `SKILL.md` 并完整遵循：去重、分批（每批 ≤5）、`question` 审阅、落库。不重复、不放宽它的规则。

### 3.3 summary

按 `jfox-session-summary` 生成并直接写入。两条硬要求：

1. 写入命令必须带 `--session-path "$PI_SESSION_FILE"`、`--agent pi-coding-agent`、`--agent-model "${PI_PROVIDER}/${PI_MODEL}"`（变量为空则省略）与标题 `Session: <topic>`。`session_file` 只在传了 `--session-path` 时存在，它是 3.1 幂等的唯一依据。
2. 若本次写入了 permanent 笔记，在「完成的工作」下补一条 `- 沉淀永久笔记：<标题>（<ID>）`。

### 3.4 失败处理

| 失败点 | 行为 |
|--------|------|
| permanent 任一写入失败 | 停止链路，不写 summary；报告失败笔记与重试命令 |
| permanent 被用户全部跳过 | 继续 summary（用户全部跳过不等于失败） |
| summary 写入失败 | 报告 permanent 已写入的结果 + 错误；不重试、不静默 |
| 重复触发且用户选择「跳过」 | 跳过 summary，仍展示上次写入的笔记信息 |

## 第 4 段：收尾展示

```markdown
## 收尾完成

### 会话总结
<summary 全文>

### 本次写入
| 类型 | 标题 | ID |
|------|------|----|
| session | Session: ... | ... |
| permanent | ... | ... |

### 未完成事项
- <...>

### 下一步
<一句话>
```

## 幂等与重复触发

- 写入前必做 3.1；命中同一 `session_file` 时由用户选择更新、跳过或另建。
- 选「跳过」不报错，按成功收尾展示上次笔记。
- 同一会话第二次 finalize 时主线重新判定，不复用上一次结论。

## 失败与降级

| 情形 | 行为 | 用户可见提示 |
|------|------|--------------|
| `$PI_SESSION_FILE` 为空 | 用上下文 + git 回放 | `旅程回放降级：未找到会话文件` |
| 文件不存在 / 为空 / 0 条有效消息 | 同上 | 同上 |
| `python3` 或脚本不可用 | 用上下文回放 | `旅程回放降级：脚本不可用` |
| `jfox kb current` 失败 | 第 0 段停止 | 初始化指引 |
| 缺任一 jfox skill | 第 0 段停止 | 安装指引 |

## 与两个 jfox skill 的边界

- 本技能只决定「何时调用、以什么顺序调用、失败怎么办」，不复制它们的去重阈值、审阅交互或写入格式。
- `jfox-session-to-permanent` 记现状（事实 / 决策 / 文件位置），`jfox-session-summary` 记行为历史（做了什么）；两者都写，顺序不可颠倒。

---
name: zima-pr-monitor
description: Use when monitoring a PR under Zima Blue code review — after creating a PR and adding zima:needs-review, when polling or babysitting CR results, parsing cc-cr-meta/pi-cr-meta review bodies, or deciding if a PR has converged and is mergeable.
---

# Zima PR Monitor

盯一个走 Zima CR 的 PR，直到收敛 + CI 全绿 → 合并。是 github-issue-driven 流程的步 8-9。

> 体系沿革：曾为 cc + kimi 双 bot 交叉验证，kimi 因调用成本过高已移除（单 bot 化）；现主力切换中——cc 版（`cc-cr-meta`）与 pi 版（`pi-cr-meta`，github-code-review-batch 已 pi 适配）共存，同一 PR 由哪个 bot 审，看 review meta 前缀。

## 触发与机制
开 PR + 打标签触发：
```bash
gh pr create --base main --title "..." --body "..."
gh pr edit <N> --add-label zima:needs-review   # webhook 扫到 → 触发该仓库绑定的 CR PJob
```
- webhook 事件驱动触发（smee → webhook-server → PJob）；Zima daemon ~45min 轮询为备用路径。
- 同账号发 review，区分靠 body 的 HTML meta：`<!-- cc-cr-meta {...} -->`（cc 版） / `<!-- pi-cr-meta {...} -->`（pi 版，主力），字段含 `round` / `new_count` / `resolved_count` / `issues[]`（每条 status: resolved/acknowledged/open）。历史 kimi 版评论（`kimi-cr-meta`）直接忽略；**kimi 未出现 = 正常态，不是未收敛信号**。

## 轮询节律
- 距下个 ~45min cycle 远 → 惰性 ~30min 一次；
- 接近 / 在 cycle 内 → 激进 5-10min，cycle 内平均 ~7min。

## 每轮
```bash
gh pr view <N> --json state,labels,statusCheckRollup,reviews
```
决策树（**用 state 判终态，不用 label**）：
- `MERGED/CLOSED` → 结束。
- 有 open issue → 读 issue → **worktree** 修 → push → `gh pr edit <N> --add-label zima:needs-review`（重打触发下轮）。
- 仍 needs-review / CI pending → 等。

## ⚠️ 收敛判定（最易踩坑）
**`new_count==0` ≠ 可合并！** `new_count` 只计"本轮新发现"，**不带历史 carried open**。真正可合并 = 该 PR 的 CR bot（cc 或 pi，看 meta 前缀）最新 round 同时满足：
- `new_count == 0`，**且**
- **无 carried open issue**（逐条看 `issues[].status`，不能只看汇总数字）。

另：label 消失 ≠ 审完（bot 发完 review 就移标签，但流程可能还在收尾）→ 看 review meta 确认本轮报告存在。kimi 永远不会出现（已移除），不要等它。CI 必须 `gh pr checks` 全绿（Windows fast job ~24-27min 是瓶颈）。

## babysit 必带 stuck 检测（否则空转数天）
- 每轮存快照，比对进展（新 review / 新 commit / CI 变化 / label 转换）；有进展清零，无进展 +1。
- 连续 K 轮（~3 轮 / 90min）零进展 → **停 + 报警**。
- **label 死状态守卫**：`zima:needs-review` 不在 + 无新 review + state OPEN = "CR 不会被触发"的死状态 → 报"需手动重打标签" + 停。（专防"忘打标签空转两天"旧坑。）

## 合并
CR bot 0 open + CI 全绿 → `gh pr merge <N> --squash --delete-branch`。

## CR 验证纪律
读 **PR HEAD**（`gh pr diff <N>` / `gh pr view <N> --json`），**不读本地工作区**——工作区可能停在别的分支 → 虚假回归。

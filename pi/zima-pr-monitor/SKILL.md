---
name: zima-pr-monitor
description: Use when monitoring a PR under Zima Blue dual-bot (cc + kimi) code review — after creating a PR and adding zima:needs-review, when polling or babysitting CR results, parsing cc-cr-meta/kimi-cr-meta review bodies, or deciding if a PR has converged and is mergeable.
---

# Zima PR Monitor

盯一个走 Zima 双 Bot CR 的 PR，直到双 bot 收敛 + CI 全绿 → 合并。是 github-issue-driven 流程的步 8-9。

## 触发与机制
开 PR + 打标签触发：
```bash
gh pr create --base main --title "..." --body "..."
gh pr edit <N> --add-label zima:needs-review   # Zima daemon 扫到 → 同时触发 cc + kimi 双 bot
```
- Zima daemon ~45min 一个 review cycle。
- 双 bot 同账号发 review，区分靠 body 的 HTML meta：`<!-- cc-cr-meta {...} -->` / `<!-- kimi-cr-meta {...} -->`，字段含 `round` / `new_count` / `resolved_count` / `issues[]`（每条 status: resolved/acknowledged/open）。

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
**`new_count==0` ≠ 可合并！** `new_count` 只计"本轮新发现"，**不带历史 carried open**。真正可合并 = 双 bot（cc AND kimi）最新 round 同时满足：
- `new_count == 0`，**且**
- **无 carried open issue**（逐条看 `issues[].status`，不能只看汇总数字）。

另：label 消失 ≠ 两 bot 都审完（一个 bot 发完就移标签，另一个可能还在跑）→ 看 review meta 确认两份都在。CI 必须 `gh pr checks` 全绿（Windows fast job ~24-27min 是瓶颈）。

## babysit 必带 stuck 检测（否则空转数天）
- 每轮存快照，比对进展（新 review / 新 commit / CI 变化 / label 转换）；有进展清零，无进展 +1。
- 连续 K 轮（~3 轮 / 90min）零进展 → **停 + 报警**。
- **label 死状态守卫**：`zima:needs-review` 不在 + 无新 review + state OPEN = "CR 不会被触发"的死状态 → 报"需手动重打标签" + 停。（专防"忘打标签空转两天"旧坑。）

## 合并
双 bot 0 open + CI 全绿 → `gh pr merge <N> --squash --delete-branch`。

## CR 验证纪律
读 **PR HEAD**（`gh pr diff <N>` / `gh pr view <N> --json`），**不读本地工作区**——工作区可能停在别的分支 → 虚假回归。

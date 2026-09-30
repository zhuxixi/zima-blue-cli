# 轮次报告 / state 索引模板（复制即用）

## 轮次报告 — `<issue 目录>/research/spec-review-round-<k>.md`

第 1–4 段由复核者写；第 5 段由起草者追加。两人都只追加，不覆盖。

```markdown
# spec-review round <k> — <owner>/<repo> issue #<N>

- Round k: <k>
- Reviewer: `<provider>/<model>` (selected) · `<provider>/<model>` (physical)
- Drafter: `<provider>/<model>`
- Reviewed spec sha256: `<sha256sum <spec 绝对路径> 的输出>`
- Mode: `cross-model` | `degraded (same-model)` | `cross-model (post-hoc same-physical)`
- 时间：<ISO8601>

## 五视角核对表

| # | 视角 | 结论 |
|---|---|---|
| ① | 验收矩阵完备性 | 核对通过 / 有发现（R<k>-G<n> …） |
| ② | 可测性拆分可实现性 + 触发时序 | … |
| ③ | 部署/执行路径真实性 | … |
| ④ | 契约与边界 | … |
| ⑤ | 命令与命名可追溯 | … |

## 发现表

### 真缺口（阻塞，必须修订）

**R<k>-G1 · <一句话结论>**
- 定位：`<文件:行>` 或 spec 原句
- 问题：…
- 建议：…
- 若不复核的代价：…

### 细化（应修订）

**R<k>-D1 · <一句话结论>** —— 同上四要素。

## 收敛判定

- 真缺口：<n>；细化：<n>
- 结论：<继续 / 收敛>
- 下一轮目标：…

继续 → 第一行；收敛 → 第二行：

[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。
[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。

---

## 修订摘要（起草者追加）

修订者：`<provider>/<model>` (selected) · `<provider>/<model>` (physical) @ <ISO8601>
修订后 spec 新 sha256：`<hash>`（外部记录）

| 发现 | 级别 | 处置 | 改动位置 |
|---|---|---|---|
| R<k>-G1 | 真缺口 | 接受并改 / 部分接受 / 拒绝并给证据（附证据） | <章节> |
```

## state 索引 — `<issue 目录>/research/spec-cross-review-state.md`

```markdown
# spec-cross-review state — Issue #<N>

- 当前状态：reviewing / revising / converged / awaiting-user-confirmation / approved
- 轮次上限：4（被调整时写明调整人与依据）
- 草稿：`../spec.md`（v<k>，当前 sha256 `<hash>`）

| 轮次 | 复核者 | Mode | 真缺口 | 细化 | 结论 |
|---|---|---|---|---|---|
| 1 | <provider>/<model> | cross-model | 2 | 3 | 未收敛 → 起草者修订 |

Open findings：<编号列表或"无">

下一步：<切到哪个模型 + 触发词 + 轮次>
```

## 两条硬规则

- hash 口径固定为 `sha256sum <spec 绝对路径>`（文件字节流原样）；**哈希只记在轮次文件与 state 索引里，不写回被计算的文件自身**——否则自引用，下一轮对账永远不相等。
- 版本对账：下一轮报告头必须核到上一轮修订摘要里的新 hash；不一致则先对齐再审。

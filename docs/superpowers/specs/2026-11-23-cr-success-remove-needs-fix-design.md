# Issue #267 修复设计：success 分支摘除 `zima:needs-fix`

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-23T08:12:00+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-23T08:30:00+08:00（第 1 轮复核：R1-D1/D2/D3/D4 全部接受）

## 1. 结论与范围

在 code-review scene 的 success 分支补摘 `zima:needs-fix`，让「本轮审查通过」同时表达「此前的不通过状态已解除」。issue 提议的 B 方案（advisory-only 轮次不应标 `needs-fix`）经 `pi-agent-board#242` 的真实时间线证伪，不纳入本次改动。

本次改动只覆盖仓库产物：scene 定义、示例模板、测试。现网 PJob YAML 的 actions 是创建时的快照（见 §9），迁移属人工部署动作，不进本 PR。

## 2. 根因

`zima/scenes.py:45-51` 的 success 分支 `remove_labels=["zima:needs-review"]`，而 `zima/scenes.py:53-62` 的 failure 分支 `add_labels=["zima:needs-fix"]`。两个分支不对称：`needs-fix` 只被写、从不被读回清除。

全仓复核（`rg -n 'needs-fix'`）确认没有任何代码路径移除该标签，唯一例外是 `examples/auto-merge/auto-merge-guarded.py:835-844` 的手动兜底摘除。所以这不是能力缺失，是同一 `PostExecAction` 里漏了一个标签名。

该遗漏与功能同源引入：`9883848 feat(scenes): add default_actions to Scene for postExec label transitions`（2026-04-30）首次定义这两个分支时就只写了单向流转，不是后续回归。

## 3. 语义正确性证据

**success 分支等价于「本轮 verdict 通过」，因此摘除历史残留的 `needs-fix` 是正确语义。** `zima/execution/executor.py:1074-1079` 把 `<zima-review>` 的 verdict 映射成 effective returncode：`approved → 0`，`needs_fix` / `needs_discussion → 1`。走 success 分支 ⇒ 本轮判定 approved ⇒ 当前无 blocking finding ⇒ 历史轮次留下的 `needs-fix` 已过期。若本轮真有 blocking，本轮走 failure 分支并重新加上该标签。

**`pi-agent-board#242` 的时间线同时证明 A 正确、B 不成立。** 该 PR 四轮 review 的 `pi-cr-meta` 计数与标签事件按时间对齐后如下表（标签事件取自 issue timeline API）：

| 轮次 | blocking_open_count | advisory_open_count | 标签事件 | 解读 |
|---|---|---|---|---|
| — | — | — | 03:10 labeled `needs-review` | 人工/调度触发 |
| round 1 | **0** | 2 | 03:26 unlabeled `needs-review` | 只有 advisory → approved → success 分支，**未标 `needs-fix`** |
| round 2 | **1** | 2 | 03:51:57 labeled `needs-fix`；03:52:01 unlabeled `needs-review` | 有 blocking → failure 分支，行为正确 |
| round 3 | **0** | 2 | 04:09 unlabeled `needs-review` | approved，`needs-fix` 残留（本 bug） |
| round 4 | **0** | 1 | 04:20 unlabeled `needs-review` | 同上，残留 |
| — | — | — | 04:31:24 unlabeled `needs-fix` | 人工清理（04:45 合并） |

round 1 正是 issue 所称「只有 advisory 也被标上」的反例：它只摘了 `needs-review`，根本没有加 `needs-fix`。这与 `pi/github-code-review-batch/SKILL.md:100`、`:102` 的约定一致——pi-cr 的 XML verdict 由 blocking open count 驱动——因此 advisory-only 轮次本来就落在 success 分支。

结论：issue 的 B 方案描述的现象在当前代码下不可复现，不需要新的 `condition` 类型或 verdict 分级；A 已足够让标签在任意收敛态正确。

## 4. 设计决策

| 编号 | 决策 | 依据 |
|---|---|---|
| D1 | success 分支 `remove_labels` 改为 `["zima:needs-review", "zima:needs-fix"]` | §2 根因、§3 语义 |
| D2 | failure 分支保持不变 | 本轮有 blocking 时 `needs-fix` 本就是正确状态；改它会破坏现有 16 个现网配置的一致语义 |
| D3 | 不引入新的 condition 或 verdict 分级 | §3 已证伪 B 的触发条件 |
| D4 | 顺序固定为 `needs-review` 在前、`needs-fix` 在后 | 与 failure 分支的书写顺序一致，便于对账；`_execute_action` 逐标签独立 try/except，顺序不影响结果 |
| D5 | 不改 `examples/auto-merge/auto-merge-guarded.py` 的摘除逻辑 | 它对旧版本 zima 仍是必要的兜底，且幂等；删掉会降低向后兼容性 |
| D6 | 不改历史 spec `docs/superpowers/specs/2026-08-30-auto-merge-guarded-design.md` | 该目录是当期设计快照（每文件只在对应 PR 落地时写入），追改会破坏历史可追溯性 |
| D7 | 现网 16 个 PJob YAML 迁移不进本 PR | skill 纪律：部署/配置变更属人工；且 PR 合并前修改本机运行时配置会让 CR 行为早于代码变更 |

## 5. 变更清单

| 文件 | 行 | 改动 |
|---|---|---|
| `zima/scenes.py` | 48 | success 分支 `remove_labels` 追加 `"zima:needs-fix"` |
| `zima/templates/examples.py` | ~226-228 | `REVIEWER_PJOB` 示例的 success 分支 `removeLabels` 追加 `zima:needs-fix`，与 scene 保持同源一致 |
| `tests/unit/test_scenes.py` | 124 | `success_action.remove_labels` 断言改为两元素 |
| `tests/unit/test_examples.py` | 303（扩展既有断言） | `REVIEWER_PJOB` 的 success 分支 `remove_labels` 断言改为两元素 |
| `tests/unit/test_quickstart.py` | 302 | scene → `_create_all_configs` → 落盘 YAML 的 `postExec[0]["removeLabels"]` 断言改为两元素（实现阶段发现，原计划遗漏） |
| `tests/unit/test_actions_runner.py` | 新增用例 | success 条件下两个 `remove_labels` 都调到 provider |
| `tests/integration/test_executor_actions.py` | 新增用例 | 用 `BUILTIN_SCENES["code-review"].default_actions` 驱动一次 approved 执行，断言两个标签都被摘 |

不改动：`zima/models/actions.py`、`zima/execution/actions_runner.py`、`zima/providers/github.py`（现有机制已支持多标签摘除）。

## 6. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | code-review scene 的 success 分支同时摘两个标签 | 自动化验证（unit） | `uv run pytest tests/unit/test_scenes.py -q` | `remove_labels == ["zima:needs-review", "zima:needs-fix"]`，且 `add_labels == []`、`require_review is True` 不变 |
| A2 | ActionsRunner 对多标签摘除逐条调用 provider | 自动化验证（unit） | `uv run pytest tests/unit/test_actions_runner.py -q` | `remove_label` 被调用两次，参数分别为两个标签；无异常、`errors` 为空 |
| A3 | 从 scene 到 executor 的端到端：approved 执行摘两个标签 | 自动化验证（integration） | `uv run pytest tests/integration/test_executor_actions.py -q` | mock provider 收到 `(repo, pr, "zima:needs-review")` 与 `(repo, pr, "zima:needs-fix")` 两次 `remove_label`，且 `add_label` 未被调用 |
| A4 | failure 分支行为不回归 | 自动化验证（unit + integration） | 同上两条命令的既有用例 | 既有 failure 用例全绿：仍 `add_label("zima:needs-fix")` + `remove_label("zima:needs-review")` |
| A5 | 示例模板与 scene 不再分叉 | 自动化验证（unit） | `uv run pytest tests/unit/test_examples.py tests/unit/test_quickstart.py -q`（扩展现有 `REVIEWER_PJOB` 断言，`tests/unit/test_examples.py:303`；并通过 quickstart 落盘路径间接验证 scene，`tests/unit/test_quickstart.py:302`） | 解析后 `spec.actions.post_exec[0].remove_labels == ["zima:needs-review", "zima:needs-fix"]`；quickstart 生成的 YAML 同值 |
| A6 | 代码风格与静态检查 | 自动化验证（static） | `uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100` | 两条命令退出码 0 |
| U1 | 现网真实 PR 收敛后标签自动归零，且干净轮次无摘除告警 | 用户实测 | 迁移 16 个 PJob 后，任选一个 PR 先制造 failure 轮再跑到 blocking=0；观察时间线与该轮 PJob 输出 | `needs-fix` 在收敛轮被自动摘除、无需人工 `gh pr edit`；且输出中无 `Failed to remove label 'zima:needs-fix'`（验证「标签未贴」路径的真实 gh 行为，见 §10 第二行） |

U1 无法自动化的原因：需要一个真实的 failure→收敛两阶段 PR 序列，且依赖本机 `~/.zima/configs` 迁移（人工部署动作，不在 CI 可达范围）。执行时机：PR 合并后由用户在本机执行迁移再观察。

## 7. 可测性拆分设计

本次改动不新增生产代码路径，可测性由「配置断言 + 既有执行器行为」两层构成：

1. **配置层（纯数据，无副作用）**：`BUILTIN_SCENES["code-review"].default_actions` 是模块级常量，可直接断言字段值。测试边界就是对象本身，不需要启动任何进程。对应 A1、A5。
2. **动作执行层（副作用已隔离在 provider 边界）**：`ActionsRunner._execute_action` 只通过 `ActionProvider` 协议产生副作用，provider 可替换为 mock。测试边界是 `remove_label` 的调用序列，不碰 `gh` 子进程。对应 A2。
3. **编排层（跨组件：verdict → returncode → 分支选择 → provider 调用）**：`PJobExecutor` 已支持用 `mockCommand` 注入 agent stdout、用 `executor._actions_runner._registry` 替换 provider，因此整条链路可在 integration 层确定性验证，不需要真实 GitHub 或真实 agent。对应 A3、A4。

三个边界各测一次即可，不引入重复的「scene → runner」中间层测试——因为第 3 层已经覆盖了 scene 常量到 provider 调用的完整路径。

## 8. 非目标

- 不改 verdict 解析与 `_matches_condition` 的实现。
- 不处理 `zima:wait-human-merge`（`scripts/init_labels.py:20` 定义但全仓无消费方），与本 issue 无关。
- 不改 auto-merge 脚本的摘除兜底。
- 不处理并发流导致的标签抖动（同一 PR 多条 CR 流交错时可能短暂闪烁；按「本轮 approved 即当前无 blocking」的语义这是可接受的最终一致）。

## 9. 部署与迁移（人工，PR 合并后）

`Scene.default_actions` 只在 quickstart 创建 PJob 时写入一次（`zima/commands/quickstart.py:204`），之后是 YAML 快照。本机 `~/.zima/configs/pjobs/` 有 16 个 PJob 含 `condition: success` 分支。

迁移动作**不依赖片段抄写**：在每个文件的 `condition: success` 动作块的 `removeLabels` 列表末尾追加一行 `- zima:needs-fix`，新行与原列表项保持**同级缩进**（各文件缩进可能不同，按所在文件现有列表项对齐，不要套用统一模板）。修改前先备份：`cp -a ~/.zima/configs/pjobs ~/.zima/configs/pjobs.bak-267`。

**无需重启 daemon**：daemon 每轮以全新子进程拉起 PJob（`zima/core/daemon_scheduler.py:162-166`），执行时重新读取 YAML；改动在下一轮执行自动生效。

## 10. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| `gh issue edit --remove-label` 对仓库里不存在的标签报错 | 该标签摘除失败 | `zima/execution/actions_runner.py:174-181` 逐标签 try/except，失败只进 `action_errors` 并打 warning，不中断 PJob；且现有 success 分支已对 `needs-review` 承担同一风险 |
| **标签存在但未贴在该 PR**（D1 后的最高频路径：从未被标过的干净 PR 也会调用 `remove_label("zima:needs-fix")`） | 若 `gh` 对此报错，每个干净轮次都会产出一条 warning 与 `action_errors` 记录 | 行为未实测，不做假设：列入 U1 观察项（收敛轮观察 PJob 输出无 `Failed to remove label 'zima:needs-fix'`）。即使报错也不阻断执行，仅噪声；`MagicMock` 测试测不出该语义，只能靠 U1 |
| 现网未迁移导致「修了但没效果」的错觉 | 用户以为 PR 无效 | §9 明确迁移步骤，并写在 PR 描述与最终报告里 |
| 并发 CR 流互相摘标签 | 标签短暂闪烁 | §8 明确接受；最终一致由「最后收敛的那轮」决定 |
| 历史 spec 仍写着「残留需手动清理」 | 读者误以为行为未变 | D6 保留快照；issue #267 关闭后在评论里给出权威结论 |

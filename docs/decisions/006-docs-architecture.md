# ADR 006: 文档自动化架构——人工基线、生成参考与 CI 漂移门禁

## 状态

✅ **已接受** (2026-09-05)

关联：issue #228（立项）· issue #196（双路径决策）· jfox #456（已验证的参考路线）· spec `docs/superpowers/specs/2026-09-05-docs-automation-design.md`

## 背景

本文档体系在 #228 立项前存在三处已证实的漂移：

- **README 讲的是单路径故事**：快速上手整章只教 `zima agent create ...` 系列 CLI 命令，与实际已形成的双路径现实（agent 直接写/复制 YAML 到 `$ZIMA_HOME/configs/`，CLI 受约束写入作为人类补充）矛盾，把读者引向「zima = 命令行配置工具」的错误心智（#196 的核心发现）。
- **`docs/API-INTERFACE.md` 是手工维护的命令快照**：标注的最后更新为 2026-03-28，实际命令面早已演进——`pjob actions` 子命令组（provider/list/add/remove，#73）整组缺失、`pjob run --failure-guard-off`（#202）等运行时 override 未覆盖。这类快照每次 CLI 演进都要人工同步，漏了没有任何机制发现。
- **`docs/design/CLI-INTERFACE.md` 自述「实现前文档，可能与代码不一致」**，却仍被当作用户接口参考引用。

## 决策驱动因素

- **配置主路径已变为 agent 直接落 YAML**（#196 决策：保留 CLI + YAML 双路径，`validate` 作为共同质量门）——文档必须如实呈现双路径，而不是单一路径的教学。
- **CLI 命令面是可从代码确定性推导的事实**：真实 Typer 命令树包含路径、参数、类型、默认值、choices，重新生成近乎零成本；而人工转录同一事实既慢又会漂移。
- **手工命令表已被证明会漂移**（API-INTERFACE 的实际状态即为证据）。
- **jfox #456 已验证分层路线**：人工基线 → 确定性生成 → CI 门禁 → 自动 draft PR → AI 辅助审查，每层稳定后再上下一层；跳层（先上智能）是已知反模式。

## 问题

如何在 CLI 持续演进的前提下，让面向用户的文档始终与真实命令面一致，且不引入持续的人工同步负担？

## 决策

**采用三层边界 + 英文范围 + 封闭写入路径：**

1. **三层边界**：
   - `README.md` 与 `docs/guides/**` 是**人工维护的叙事基线**（产品故事、双路径适用场景、配置目录约定）——叙事不可从代码推导，永远人工写；
   - `docs/cli-reference.md` 是**生成物**，由 `scripts/generate_cli_docs.py` 从真实 Typer 命令树 + `docs/cli-descriptions.yaml`（人工维护的英文一句话描述，与命令树精确双向覆盖）确定性渲染，头部带 GENERATED_MARKER，禁止手改；
   - **CI 漂移门禁**：lint job 重跑生成器，`git diff --exit-code` + untracked 生成文件检查，任一命中即失败并给出本地重生成命令。
2. **面向用户的文档只用英文**。范围表：`README.md`、`docs/guides/**`、`docs/cli-reference.md`、`docs/cli-descriptions.yaml`、`examples/*/README.md` 必须英文；`docs/{design,decisions,history,reports}/**` 与 workflow YAML 内的业务 prompt 内容可保留中文（后者是用户数据不是文档）。
3. **不新增 `zima apply/import` 等 CLI 配置写入路径**（#196 已决策）——文档自动化不改变双路径模型。

## 替代方案（否掉的）

- **README 也自动生成** —— 否。README 承载产品叙事（为什么有两条路径、何时用哪个），叙事无法从命令树可靠推导；生成的 README 必然退化为命令列表堆砌。
- **继续手工维护命令快照** —— 否。API-INTERFACE.md 的现状（缺失整组子命令、缺失新 flag、更新日期过期五个月）就是该方案失效的实证。
- **bot / AI 辅助先行** —— 否。违反 docs-as-code 分层顺序：确定性生成与 CI 门禁未稳定前上智能层，会把「防漂移」变成「带幻觉的文档生成」。
- **第一轮就上 docs-sync bot** —— 否。gate 先行收益最大、风险最低；自动开 PR 的 bot（jfox Phase 4）留待门禁验证后评估。

## 后果

- **正面**：命令面漂移被结构性阻止（CI 红灯即修复信号）；改命令的 PR 顺带必须补描述条目，CLI 评审心智负担下降；面向用户文档全英文后可触达国际化受众。
- **负面/中性**：新增约 86 条英文描述目录的维护义务（新增命令必须同步补条目，否则 CI 失败——这是刻意的强制同步点）；生成器直接依赖 `click` 类型，`click` 需从传递依赖提升为直接依赖；`scripts/` 需纳入 ruff/black lint 范围。
- **中性**：`docs/API-INTERFACE.md` 已删除，其内容去向：CLI 命令表由生成的 cli-reference 取代，配置规范并入 `docs/guides/configuration.md`，数据模型/运行接口/执行流程迁至 `docs/architecture/data-and-runtime-reference.md`。

## 依据来源

- issue #196（双路径决策与 CLI 价值重估）、issue #228（本 ADR 的立项与 spec）
- jfox #456（五阶段路线图）、PR #474（CLI Reference 双源生成）、#477（Phase 3 CI 漂移门禁）、#488（untracked 检查补丁）
- spec：`docs/superpowers/specs/2026-09-05-docs-automation-design.md` §3（英文范围表）、§4（API-INTERFACE 拆分映射）
- 本仓库实证：API-INTERFACE.md 漂移盘点（#228 调研）、PR 1 各 task 的 review 记录

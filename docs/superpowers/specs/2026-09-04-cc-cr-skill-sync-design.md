# Spec：pr-automation cc 版 skill 与 pi 版对齐同步 + 版本 bump（Issue #221）

日期：2026-09-04（rev3：并入 reviewer 对抗评审结论——P0 补 run_tool_layer.py、P1 重写适配清单与 A5 模式、P2 若干）。依据：`research/分叉时间线与同步策略.md`（3 轮调研，结论已评论回 issue）。

## 目标

把 `plugins/pr-automation/skills/github-code-review-batch/`（cc 版）从落后状态同步到与 `pi/github-code-review-batch/`（pi 版）当前状态等价，恢复 cc 回退路径的 blocking 语义 / XML trailer / #174 files 过滤能力；同步后 bump plugin 与 marketplace 版本号 0.5.1 → 0.6.0。

## 非目标

- **不做字节级 parity 门禁**：#212（cr-batch 降本重构：trivial 前置脚本化 / 模型分档 / 双 checker 合并 / validator 批量化 / summarizer 降档）将对 pi 版大改，parity 门禁落地即碎。推迟到 #212 系列落地稳定后再评估。
- 不做 `--meta-tag` 参数化（K3 双 bot 前置，另开 issue）。
- 不给 cc 端新增 pr-monitor skill。
- 不改 pi 版的任何行为。
- 不动 zima daemon / webhook-server / PJob 配置。

## 改动设计

### 1. scripts 同步（cc ← pi，7 文件）

| 文件 | 动作 |
|---|---|
| `issue_policy.py` | 从 pi 原样复制（零 pi 字面量，已验证） |
| `render_status_report.py` | 从 pi 原样复制（零 pi 字面量，已验证） |
| `compress_diff.py` | 从 pi 原样复制（零 pi 字面量，已验证） |
| `run_tool_layer.py` | 从 pi 原样复制（零 pi 字面量，已验证）——**必需**：#174 的 `filter_to_files()` / `run_tool(..., files=)` / `--files` CLI flag 在此文件；不复制则 flow.md 的 `--files` 指令会 argparse exit 2 硬挂 Step 4，或被迫删节丢掉 #174 目标 |
| `build_review_body.py` | 从 pi 复制 + 按规则全文件替换（sed 语义）：`pi-cr-meta`→`cc-cr-meta`、`Generated with pi-coding-agent`→`Generated with Claude Code`（共 2 处字面量，L174、L324） |
| `parse_metadata.py` | 从 pi 复制 + 按规则全文件替换（sed 语义）：`pi-cr-meta`→`cc-cr-meta`、`Generated with pi-coding-agent`→`Generated with Claude Code`、变量名 `PI_MARKER`→`CC_MARKER`（3 条规则覆盖 7 处字面量，含 docstring 与正则） |
| `apply_suppressions.py`、`match_committer_response.py` | 两版已字节一致，不动 |
| `__pycache__/` | 不入库（根 `.gitignore` L2 已覆盖） |

替换后 cc 版语义：写/读 `cc-cr-meta`、识别 `Generated with Claude Code` 署名评论——与现有 cc 行为契约一致，历史 `pi-cr-meta`/`kimi-cr-meta` 评论被忽略。

### 2. SKILL.md + references 措辞适配（人工逐段审，不可纯 sed）

references 共 5 个文件（非 4 个）：`edge-cases.md` 两版一致、零 pi 残留，**不动**；其余 4 个 + SKILL.md 按下表适配。

**删除类（pi 环境专属，cc 不可继承）**：
- `subagent` 工具 + `workflowScript`/`runs.all` 派发机制 → 改写为 Claude Code `Agent`/Task 并行派发（点位：SKILL.md L78 附近、flow.md L202/L205/L272、subagent-prompts.md L3 的 pi 派发引言）
- `pi-subagents` 解析链、`modelScope` 政策细则、`agent:"reviewer"`/`context:"fresh"` 参数、`subagent({action:"models"})` 查询（flow.md L216–223 整段）→ cc 侧无对应机制，整段删除或改写为「按 Claude Code sub-agent 默认模型派发」
- 项目级 `.pi/settings.json` 说明（flow.md L218）→ 随 modelScope 段一并删除

**方向翻转类（语义对称，不可遗漏）**：
- flow.md L19–26 Step 0 metadata 识别条件：`Generated with pi-coding-agent` / `<!-- pi-cr-meta` / 提取正则 → 翻转为 cc 版。**现 cc 版 flow.md L18–24 已有正确翻转写法，作 canonical 样例照抄**
- flow.md L308 suppress 文件路径：pi 版读 `.pi/cr-suppressions.json`（`.claude/` 兼容）→ **方向反转**：cc 版主路径 `.claude/cr-suppressions.json`（`.pi/` 兼容），不是删除
- 身份叙事：pi 版 SKILL.md「历史 cc 版评论严格忽略」→ cc 版「历史 pi-cr-meta 与 kimi-cr-meta 评论严格忽略」

**字面量替换类**（SKILL.md + 4 个 references 内）：`pi-cr-meta`→`cc-cr-meta`、`pi-coding-agent`→`Claude Code`——集中在 output-examples.md 的示例 metadata header（L10,45,72,88,124,165）与 `🤖 Generated with pi-coding-agent` 示例行（L35,62,80,111,155,179）、flow.md L19/L23/L24/L26/L412/L454。**合法豁免**：flow.md L42 式跨 bot 三方罗列（「pi 版包含… cc 版包含… kimi 版包含…」）与身份段落的忽略名单提及 `pi-cr-meta` 是合法内容，保留。

**保留不变类**：三个触发短语、`Status:` 三态契约（`NEEDS_FIX`/`PASS`/`NO_NEW_COMMITS`）、`<zima-review>` XML trailer 要求（cc 型 agent 退出码同样不反映 verdict，必需）、blocking/advisory 全部语义、触发短语外部契约警告框。

### 3. cc 侧契约测试

新文件 `tests/unit/test_cr_batch_plugin_contracts.py`：

- **round-trip**：cc 版 `build_review_body.py` 产出 → cc 版 `parse_metadata.py` 读回，round-trip 成功且 marker 为 `<!-- cc-cr-meta`（subprocess 黑盒，同现有 contract 测试法）。
- **SKILL.md 静态断言**（镜像 pi contract 测试的契约 1/2/6）：三个触发短语原文存在、`NEEDS_FIX|PASS|NO_NEW_COMMITS` 三态存在、`<zima-review>` 存在、`gh` CLI 路径表述存在。
- **run_tool_layer `--files` smoke**：cc 版脚本带 `--files` 参数跑一个最小输入，断言 exit 0 且输出为合法 JSON（防 P0 复归）。
- **边界说明**：只测 cc 版自身契约，不做与 pi 版的字节/行为 parity 断言（见非目标）。

### 4. 版本 bump + README

- `plugins/pr-automation/.claude-plugin/plugin.json`：`0.5.1` → `0.6.0`。
- `.claude-plugin/marketplace.json`：`0.5.1` → `0.6.0`。
- `plugins/pr-automation/README.md` 两处：(a) Skills 表补能力对齐说明（blocking/advisory、XML trailer、#174 files 过滤）；(b) 「Relationship to zima daemon」段的忽略名单从仅 `kimi-cr-meta` 更新为 `pi-cr-meta` + `kimi-cr-meta`（身份翻转后的隔离契约）。
- **Release note 必写**：cc 回退路径的 `PASS`/`NEEDS_FIX` 判定边界变化——旧 cc 版任何 open issue 都 NEEDS_FIX；新版 advisory-only 轮次报 PASS 不触发 fix。这是本 issue 的意图，但会改变 8 套 cc fallback PJob 的调度器可见行为，release note 里显式点名。

## 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | cc 版脚本 round-trip 契约 + SKILL.md 静态契约 + `--files` smoke | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_plugin_contracts.py -q` | round-trip 等价；触发短语/三态/XML/gh 断言全过；`--files` exit 0 |
| A2 | pi 版既有契约不回归（改动未触碰 pi 行为） | 自动化验证（unit） | `uv run pytest tests/unit/ -q` | 既有 6 个 cr_batch 测试文件全绿 |
| A3 | 版本号两处一致 bump | 自动化验证（static） | `grep -h '"version"' plugins/pr-automation/.claude-plugin/plugin.json .claude-plugin/marketplace.json` | 两处均为 0.6.0 |
| A4 | scripts 无 pi 残留字面量 | 自动化验证（static） | `rg -n "pi-cr-meta\|pi-coding-agent\|PI_MARKER" plugins/pr-automation/skills/*/scripts/*.py` | 零命中 |
| A5 | SKILL.md/references 无 pi 环境残留 | 自动化验证（static） | `rg -n "\.pi/\|pi-subagents\|modelScope\|pi-coding-agent\|workflowScript\|runs\.all\|pi-cr-meta" plugins/pr-automation/skills/*/SKILL.md plugins/pr-automation/skills/*/references/` | 零命中，**豁免**见 §2 合法豁免条（跨 bot 罗列、忽略名单提及、suppress 段的 `.pi/cr-suppressions.json` 兼容路径） |
| U1 | Claude Code 真实加载 + 真实 PR 跑通一轮 cc CR | 用户实测 | 更新 plugin 后对真实 PR 打 `zima:needs-review`（cc PJob 回退路径） | PR 评论含 `cc-cr-meta` + 状态报告，stdout 含 `<zima-review>`，postExec 标签流转正常 |

## 风险与对策

- **替换漏点** → A4/A5 双 grep 兜底（模式已按真实残留清单修正，不再依赖不存在的 `~/.pi` 字面量）。
- **run_tool_layer.py 漏同步** → 已列入同步表 + A1 的 `--files` smoke 防复归。
- **flow.md Step 0 方向漏翻转**（cc prose 指引 agent 去识别 pi bot 评论）→ §2 点名 L19–26 + 现 cc 版 L18–24 canonical 样例；A5 grep 兜底。
- **cc 版 SKILL.md 适配引入契约漂移** → A1 静态断言 + U1 实测双重兜底。
- **pi 版被误改** → A2 既有测试全绿门禁；改动原则上只读 pi 目录。
- **#212 落地后再次分叉** → 已知且接受：本 issue 只恢复 cc 回退路径的当前能力，#212 系列落地后需再做一次对齐（届时一并评估 parity 门禁）；合并前在 issue 区留待办评论跟踪。
- **8 套 cc fallback PJob 行为边界变化**（advisory-only → PASS 不再触发 fix）→ §4 release note 显式点名，README 同步说明。

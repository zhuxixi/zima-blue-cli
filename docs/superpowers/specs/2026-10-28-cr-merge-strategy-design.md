# Issue #253 设计规格：按合并形态分流的规范检查（squash 下 (#N) 误报根治）

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-27T23:35:00+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-27T23:52:00+08:00 — 接受 R1-G1/G2/G3 与 R1-D1~D5
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-28T00:05:00+08:00 — 接受 R2-G1/D1/D2
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-28T00:18:00+08:00 — 收敛轮：接受 R3-D1/D2

- Issue: https://github.com/zhuxixi/zima-blue-cli/issues/253
- 分支建议：`issue-253-cr-merge-strategy-disambiguation`
- 调研留档：`~/.github-issue-driven/zhuxixi/zima-blue-cli/issue-253/research/`
- 授权档位：`auto`（`authorization.md`），合并前仍需用户明确许可

## 1. 目标与边界

### 1.1 目标

1. 让「commit/PR 元数据类规范规则」**以落地形态为准**：只有 squash 会重写 subject 并自动追加 `(#N)`；rebase 与 merge commit 都把分支 subject 原样带入默认分支（rebase 不追加 `(#N)`）。
2. 用**确定性步骤**取代 checker 的自由裁量：合并形态由父流程调脚本探测一次，结果注入 checker 与 validator，使同一 head SHA 的多次审查结论一致。
3. 切断 checker 的**契约外取数**：输入包没有 commit 列表时，不得自行 `git log` / `gh pr view --json commits`。
4. 让元数据类 finding 无法伪造代码锚点：`file/lines` 指向规范文件与规则位置。
5. 元数据类 finding **默认非 blocking**，且该判定由确定性脚本 `issue_policy.py` 兜底（不依赖模型自觉）；显式 `blocking: true` 可覆盖（逃生口）。

### 1.2 非目标

- 不改 `build_review_body.py` / `parse_metadata.py` / `render_status_report.py`，不向 `pi-cr-meta` schema 增加字段（探测结果落 `/tmp` 与脚本 stdout）。
- 不改 delta-review 路径（增量轮按 Step 0 分支跳过 Step 3–5，不跑规范 checker）。
- 不实现「PR 标题必须手写 `(#N)`」——squash 落地时 GitHub 自动追加。
- 不修 SKILL.md 里既有的「11 步状态机」措辞（现状表已 13 行，历史笔误，与本 issue 无关）。
- 不做跨轮探测缓存复用（每轮重探一次，成本 1–2 次 `gh` 调用）。

## 2. 背景与根因

四个缺口（详见 research/01）：

| 缺口 | 现象 | 证据 |
|---|---|---|
| G1 输入越界 | checker 自取 commit 列表并出 finding | PR #152 metadata 自述 "Commit subjects (**not the code**)"；Step 4 输入包无 commit 列表 |
| G2 落地形态未知 | 不知仓库/本 PR 是 squash / rebase / merge commit | 全仓无 squash 处理；pi-agent-board 三种方式全开 |
| G3 锚点虚构 | 元数据 finding 填无关代码位置 | `file: src/ui/dashboard.ts`, `lines: 1036-1056` |
| G4 不确定 | 同 head SHA 两流结论相反 | 15:17Z 判合规 vs 17:22Z 判 blocking |

实证（2026-10-27，pi-agent-board 最近 10 个已合并 PR）：9 个 squash（subject 以 ` (#N)` 收尾）、1 个 merge commit（#248 release PR）。「看最近 2–3 个 PR」会判错，「10 个里 ≥8 个」能稳定判对。

## 3. 方案选择

| 方案 | 内容 | 判定 |
|---|---|---|
| A 纯结构性 | 父流程探测 + 条件给料 | 不覆盖 unknown 形态，挡不住 checker 自取数 |
| B 纯提示词 | checker/validator 文本约束 + 降级 | 治不了同 SHA 不一致，全靠模型自觉 |
| **C 组合（采用）** | 确定性探测脚本 + 条件给料 + 提示词/validator + `issue_policy.py` 钳制 | 互补，且 blocking 兜底落在代码层 |

与 issue 建议的差异：issue 建议「checker 提示词里自行探测」；本设计把探测提到父流程并落成脚本。理由：探测一次全轮复用、validator 需要同一结论、脚本可被单测锁定（与 #121 确定性 tool-layer 同向）。

## 4. 组件契约与数据流

### 4.1 新增 Step 2.5：合并形态探测

`flow.md` 在 Step 2 与 Step 3 之间新增 `## Step 2.5: 合并形态探测 {#step-2-5}`：

```bash
# pi 侧
python scripts/merge_strategy.py --repo <owner>/<repo> --pr <PR> \
    --json-out /tmp/pi-cr-merge-strategy.json
# cc 侧（同一脚本，仅临时文件前缀不同）
python scripts/merge_strategy.py --repo <owner>/<repo> --pr <PR> \
    --json-out /tmp/cc-cr-merge-strategy.json
```

脚本内部（stdlib only，经 `gh api` 取数，无 `pi-cr` / `cc-cr` 字面量，两侧逐字拷贝）：

**执行范围（R3-D2）**：Step 2.5 仅**完整轮**（Round-1 全量审查）执行；增量轮按 Step 0 分支跳过
Step 3–5，Step 2.5 一并跳过（不探测、不写 JSON），因此 delta-review 路径零改动。

1. `gh api repos/<owner>/<repo> --jq '{squash:.allow_squash_merge, merge:.allow_merge_commit, rebase:.allow_rebase_merge}'`
2. 仅一种为 true → 直接定论（`basis: flags`）。
3. 否则一次 GraphQL 取最近 10 个已合并 PR：`nodes{ number mergeCommit{ message } }`，
   脚本取 `message` 首行（`split("\n")[0]`）再交给分类器。
   **禁止用 `messageHeadline`**：实测它对长 subject 截断到 70 字符并追加 `…`
   （pi-agent-board #249/#247 均被截尾，`(#N)` 后缀丢失，会把 squash 误判成 rebase）。
4. 分类写 JSON，stdout 打印一行 `merge_strategy=<...> basis=<...>`。

### 4.2 输出契约（`/tmp/{pi,cc}-cr-merge-strategy.json`）

```json
{
  "schema": 1,
  "repo": "zhuxixi/pi-agent-board",
  "pr": 251,
  "strategy": "squash | rebase | merge | unknown",
  "basis": "flags | history | history-ambiguous | probe-failed",
  "evidence": {
    "flags": {"squash": true, "merge": true, "rebase": true},
    "merged_sampled": 10,
    "buckets": {"squash": 9, "rebase": 0, "merge": 1},
    "sample_prs": [249, 248, 247]
  },
  "policy": {
    "inject_branch_subjects": false,
    "check_pr_title": true,
    "metadata_max_severity": "low"
  }
}
```

**历史分类器（纯函数 `classify_headline(pr_number, headline)`）**——三种落地形态的可判别信号：

| 落地 headline | 形态 |
|---|---|
| `^Merge pull request #` | `merge` |
| 以 ` (#<该 PR 号>)` 收尾 | `squash`（GitHub 自动追加） |
| 其余 | `rebase`（subject 原样落地、无自动尾号） |

判定表（`decide()`，纯函数）：

| flags | 历史 | strategy | basis |
|---|---|---|---|
| 恰一种 true | — | 该种 | flags |
| 多种 true | 样本 n∈[5,10] 且某桶计数 ≥ `ceil(0.8 × n)` | 该桶 | history |
| 多种 true | 其余 | `unknown` | history-ambiguous |
| 取数失败 | — | `unknown` | probe-failed |

`policy` 派生（`render_policy()`）：

| strategy | inject_branch_subjects | check_pr_title | metadata_max_severity |
|---|---|---|---|
| `squash` | false（subject 被重写） | true（仅 type token；`(#N)` 自动追加） | low |
| `rebase` | true（subject 原样落地、无自动 `(#N)`） | false | low |
| `merge` | true | false | low |
| `unknown` | false | true | low |

### 4.3 注入契约（Step 4 / Step 5 输入包）

- Step 4：checker 输入包增加 `- 合并形态：{merge_strategy}（basis={basis}）` 与 `- PR 标题：{pr_title}`。
- `inject_branch_subjects=true`（rebase / merge）时，父额外执行
  `gh pr view <PR> --json commits --jq '.commits[].messageHeadline'`，结果作为「分支 commit subject 列表」注入；为 false 时不注入，并注明「本仓库按 squash 落地，分支 subject 被重写」。
- Step 5：issue-validator 输入包增加 `{merge_strategy}`（读 Step 2.5 的 JSON，不重复探测）。
- 探测失败不阻塞流程：按 `unknown` 继续，stdout 已给出降级行。

### 4.4 checker 契约变更（claude-compliance-checker 与 agents-compliance-checker 同改）

任务清单新增三条：

1. **输入边界**：只使用输入包提供的材料；**不得**自行执行 `git log`、`gh pr view --json commits` 等命令获取输入包之外的 commit 信息。
2. **落地形态维度**（补充既有「区分适用于代码审查的规则」分类）：规则作用对象分三类——代码行 / commit 元数据 / PR 元数据；元数据类规则只在「该元数据会成为落地 subject」时成立：
   - `squash`：分支 subject 被重写、`(#N)` 由 GitHub 自动追加 → 只校验 `{pr_title}` 的 type token（单值、合法），不要求标题含 `(#N)`。
   - `rebase` / `merge`：逐条核对注入的「分支 commit subject 列表」（rebase 不追加 `(#N)`，规则真实适用）。
   - `unknown`：只校验 `{pr_title}` type token，元数据类 finding 必须 `severity: low`。
   - **所有形态**：元数据类 finding 给 `severity: low`，需要阻断时必须显式 `blocking: true` 并在 description 说明理由。
3. **锚点规则**：元数据类 finding 的 `file` 填规范文件相对路径（`CLAUDE.md` / `AGENTS.md`），`lines` 填规则行号或章节；**禁止**填任意代码位置。

### 4.5 validator 契约变更（Step 5）

- 元数据类 finding 且 `{merge_strategy}=squash` → `valid: false`（subject 不落地），explanation 写 `merge_strategy=squash: branch subjects are rewritten on squash merge`。
- `unknown` → 保留，强制 `severity: low` 与 `blocking: false`。
- `rebase` / `merge` → 按既有规则校验（必须能定位规则原文）。

### 4.6 确定性 blocking 钳制（`scripts/issue_policy.py`）

`is_blocking()` 现有顺序：显式 boolean → severity 派生。插入一条规则（位置在显式 boolean **之后**，保留逃生口）：

```python
# Metadata-class findings anchor at the guideline file, not a code line.
# Substring match: the prompt contract says reason "contains" the guideline name
# (agents-checker never pins a canonical exact string).
reason = str(issue.get("reason", ""))
file_name = PurePosixPath(str(issue.get("file", ""))).name
if any(g in reason for g in ("CLAUDE.md", "AGENTS.md")) and file_name in {"CLAUDE.md", "AGENTS.md"}:
    return False
```

- 两侧副本同步（脚本逐字拷贝，无 pi/cc 差异）。
- 保证边界：真实「PR 本身修改 AGENTS.md/CLAUDE.md 且违规」的 finding 默认被降级；checker 需显式 `blocking: true` 才能恢复阻断（逃生口已在 `is_blocking` 首位）。

## 5. 提示词文本骨架

checker prompt 输入区新增 `PR 标题：{pr_title}`，并追加段落：

```
输入边界（必须遵守）：
- 只使用上面给出的材料。不得自行运行 git log / gh pr view --json commits 获取额外 commit 信息。
- 合并形态：{merge_strategy}（basis={basis}）
  · squash：分支 commit subject 在合并时被重写，(#N) 由 GitHub 自动追加 → 只校验 PR 标题的 type token
    是否为单一合法 type，不要求标题包含 (#N)，不检查分支 commit subject。
  · rebase / merge：分支 subject 原样进入默认分支（rebase 不追加 (#N)）→ 逐条核对下方
    「分支 commit subject 列表」。
  · unknown：无法确定落地形态 → 只校验 PR 标题 type token。
- 元数据类 finding 一律 severity=low；确需阻断时显式给 blocking: true 并说明理由。
- 元数据类 finding 的 file 填规范文件路径、lines 填规则行号/章节；没有代码行可锚时不要编造位置。
```

## 6. 文件级改动范围

### 6.1 pi 主版

| 文件 | 改动 |
|---|---|
| `pi/github-code-review-batch/scripts/merge_strategy.py` | 新增：`classify_headline` / `classify_flags` / `classify_history` / `decide` / `render_policy` 纯函数 + `probe()` IO + CLI |
| `pi/github-code-review-batch/scripts/issue_policy.py` | `is_blocking()` 增加 §4.6 钳制 |
| `pi/github-code-review-batch/references/flow.md` | 新增 Step 2.5；Step 4 输入包（`{merge_strategy}` / `{pr_title}` / 条件注入 subject 列表）；Step 5 validator 输入 |
| `pi/github-code-review-batch/references/subagent-prompts.md` | 两个 checker 的任务清单 + prompt（含 `{pr_title}` 输入行）；validator 任务清单 + prompt |
| `pi/github-code-review-batch/references/edge-cases.md` | 「常见误报类型」补第 7 类：合并策略相关规则 |
| `pi/github-code-review-batch/SKILL.md` | 主流程总览表补 Step 2.5 行；关键约束补「合并形态是父流程注入的变量」 |

### 6.2 cc 插件同步版

- 脚本：`merge_strategy.py`、`issue_policy.py` 逐字拷贝（无 pi/cc 字面量差异）。
- 文档：`SKILL.md` / `references/*` 按各自 harness 手工移植（沿用 CLAUDE.md:15 的「docs drift on purpose」约定，仅 checker 段保持 byte-identical）。
- cc 侧临时文件用 `/tmp/cc-cr-merge-strategy.json`（与既有 `/tmp/cc-cr-diff-meta.json` 命名一致）。

### 6.3 测试

- 新增 `tests/unit/test_cr_batch_merge_strategy.py`（命名沿用 `test_cr_batch_*` 约定）。
- `tests/unit/test_cr_batch_issue_policy.py`：新增钳制用例（guideline 锚点 → False；显式 `blocking: true` → True；代码锚点 spec finding → 保持原派生）。
- `tests/unit/test_cr_batch_contracts.py`：`TestPortability.SCRIPT_NAMES` 增加 `merge_strategy.py`；新增 `TestMergeStrategyDisambiguation` 文档契约类。
- `tests/unit/test_cr_batch_plugin_contracts.py`：新增镜像断言类 `TestCcMergeStrategyMirror`（类名钉死，供 `-k MergeStrategy` 命中），含脚本存在性与 cc JSON 路径 token。

### 6.4 明确不修改

`build_review_body.py`、`parse_metadata.py`、`render_status_report.py`、`compress_diff.py`、`run_tool_layer.py`、`zima/` 包、delta-review 文档。

## 7. 测试与可测性拆分设计

设计约束：探测逻辑进纯函数，IO 只在 `probe()`；文档契约用 section 提取 + token 断言，不启动 LLM、不访问网络。

| 测试单元 | 独立职责 | 测试边界 |
|---|---|---|
| `classify_headline(pr, headline)` | 三种落地形态判别 | 纯函数；输入必须是 `message` 首行；含「自定义 squash message 无尾号 → 误判 rebase」与「`messageHeadline` 截断形态（尾部 `…`）不得进入分类器」两条边界 |
| `classify_flags(flags)` | 单开方式定论 | 纯 dict 入出 |
| `classify_history(rows)` | 多数判定 + 样本不足/模糊 | 纯 list 入出；阈值语义钉为 `ceil(0.8n)`，覆盖 n=4 / 5 / 9 / 10 |
| `decide(flags_res, hist_res)` | 信号合成、fail-safe 优先级 | 覆盖 4 种 basis |
| `render_policy(strategy)` | 派生注入策略 | 4 种 strategy |
| `probe(repo, pr, run=…)` | 取数与写 JSON、失败降级 | stub `gh`，验证命令形态、写盘、exit 0 |
| `issue_policy.is_blocking` | guideline 锚点钳制 | 纯 dict 入出，含逃生口 |
| pi 文档 section 提取 | Step 2.5 / Step 4 / checker / validator / edge-cases / SKILL 总览 | 只验文档契约，不评 LLM 效果 |
| cc 文档 section 提取 | 镜像一致性 + cc 路径命名 | 同上 |
| 既有契约套件 | 触发词、metadata、状态报告、模型分档不回归 | 运行现有测试文件 |

提示词对模型行为的影响**不进入自动化断言**，交由 §9 的 U1/U2 覆盖（与 #225 一致）。

## 8. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 单开方式定论 | 自动化（unit） | `uv run pytest tests/unit/test_cr_batch_merge_strategy.py -k classify_flags` | squash/rebase/merge 单开各 1 例 + 多开 1 例 |
| A2 | 历史分桶（三形态） | 自动化（unit） | `... -k classify_history` | n=10 时 9 squash + 1 merge→squash；rebase 桶→rebase；n=4→unknown；n=5 全 squash→squash（`ceil(0.8×5)=4`）；n=10 分裂 5/5→unknown |
| A3 | 信号合成 fail-safe | 自动化（unit） | `... -k decide` | probe-failed / ambiguous 一律 unknown |
| A4 | 策略派生 | 自动化（unit） | `... -k render_policy` | squash 不注入、rebase/merge 注入并检查 subject、全部 metadata_max_severity=low |
| A5 | 探测脚本正常路径 | 自动化（unit，subprocess + stub gh） | `... -k probe_ok` | exit 0、JSON schema 完整、stdout 恰一行 |
| A6 | 探测脚本失败降级 | 自动化（unit，stub gh 非零/未认证） | `... -k probe_failed` | exit 0、JSON `strategy=unknown basis=probe-failed`、stdout 一行降级说明 |
| A7 | blocking 钳制 | 自动化（unit） | `uv run pytest tests/unit/test_cr_batch_issue_policy.py -k guideline_anchor` | guideline 锚点 spec finding → False；非 canonical reason（如 `AGENTS.md 规范`，子串匹配）→ False；显式 `blocking:true` → True；代码锚点不改原派生 |
| A8 | pi 文档契约 | 自动化（unit） | `uv run pytest tests/unit/test_cr_batch_contracts.py -k MergeStrategy` | Step 2.5（含「仅完整轮执行」句）、输入边界、锚点、四形态策略、`{pr_title}`、edge-cases 第 7 类、SKILL 总览行、SCRIPT_NAMES 均通过 |
| A9 | cc 插件镜像 | 自动化（unit） | `uv run pytest tests/unit/test_cr_batch_plugin_contracts.py -k MergeStrategy` | cc 侧镜像类名钉为 `TestCcMergeStrategyMirror`；同 token 断言 + `/tmp/cc-cr-merge-strategy.json` |
| A10 | 无回归 | 自动化（static/build） | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`、`uv run ruff check zima/ tests/`、`uv run black --check zima/ tests/ --line-length 100` | 全绿；既有 CR 契约文件零新增失败 |
| U1 | 真实 PR 不再产出该类 blocking | 用户实测 | §9 协议，样本 `zhuxixi/pi-agent-board#251` | 取证三件套一致，且无「commit subject 缺 (#N)」类 finding |
| U2 | 同输入结论一致 | 用户实测（可 pending） | §9 同输入再跑一次 | 两次结论一致；成本敏感时标 pending 并如实呈现 |

## 9. U1 / U2 实测协议

**部署前置（R1-G1）：pi 从已安装副本加载 skill（`pi install <repo path>`，见 CLAUDE.md:9），worktree 里的改动在合并前不会被全局安装加载。** 因此 U1 不依赖全局安装：

1. 在 `zhuxixi/pi-agent-board` 建临时 worktree（如 `/tmp/u1-pi-agent-board`，checkout PR #251 head）。
2. 开一个 pi session，cwd 设为该 worktree，并在任务里**显式指定 skill 根**为
   `<本 issue worktree>/pi/github-code-review-batch`（读该目录的 SKILL.md 与 references，
   不读 `~/.pi/...` 下的已安装副本）。
3. 执行 Step 0–8（跳过 Step 9，不发 PR 评论），把 Step 2.5 stdout、`/tmp/pi-cr-merge-strategy.json`、
   Step 8 报告保存到 `~/.github-issue-driven/zhuxixi/zima-blue-cli/issue-253/research/u1-run-{1,2}/`。
4. **未做第 2 步（仍在跑已安装旧副本）时结论无效**，须重跑。

样本：`#251`（5 commits、预期 squash、AGENTS.md 含 `(#N)` 规则）。

取证对象（R1-D5，三者缺一不可）：Step 2.5 的 stdout 行、`/tmp/pi-cr-merge-strategy.json` 内容、
Step 8 报告的 findings 列表。**不要求**终端报告里出现 `merge_strategy` 字样（Step 8 由未修改的
`build_review_body.py` 生成，不含该字段）。

通过标准：`strategy=squash` 且 `basis ∈ {flags, history}`；报告中无「commit subject 缺 `(#N)`」类
finding（含 advisory）；U2 两次运行结论一致。

成本：单会话形态约 57 万 tokens/次；U2 可标 pending。

## 10. 风险与降级

| 风险 | 处理 |
|---|---|
| 提示词仍被模型无视（自取 commit） | validator + §4.6 确定性钳制双兜底 |
| squash 使用了自定义 commit message（无 `(#N)` 尾号）→ 被历史分类器判成 rebase | 后果仅为「多检查一遍 subject 且 finding 为 low 非阻断」；在 `classify_headline` 单测里钉住该边界行为 |
| 混合仓库判成多数桶，恰好本 PR 用了少数形态 | 最坏是多一条 low finding（rebase/merge 桶）或不检查（squash 桶），不再产生 blocking |
| GraphQL 字段截断（`messageHeadline` 70 字符 + `…`） | 只用 `mergeCommit.message` 首行；`classify_headline` 单测钉住「含尾部 `…` 的输入」边界 |
| guideline 锚点钳制误伤「PR 修改 AGENTS.md 且违规」 | 逃生口：显式 `blocking: true` 优先级最高；单测覆盖 |
| 两副本漂移 | 脚本逐字拷贝；文档按 harness 移植，checker 段 byte-identical 由既有契约测试锁 |
| 无 gh 认证 / 离线 | `probe-failed → unknown`，exit 0，流程继续 |

## 11. 与 issue #253 建议的对照

| issue 建议 | 本设计 | 差异理由 |
|---|---|---|
| 1. checker 提示词内加合并策略消歧 | 父流程 Step 2.5 探测 + 脚本 + 注入 | 一次探测全轮复用；validator 与钳制需要同一结论；可单测 |
| 2. 该类 finding 一律降 advisory | squash：直接不检查；rebase/merge：检查但 severity=low；unknown：检查标题且 low | squash 下规则不适用；rebase/merge 下规则真实有效但只值 advisory |
| 3. edge-cases 补合并策略类误报 | 采纳（第 7 类） | — |
| 未提：输入越界 / 锚点虚构 / blocking 派生 | 新增 §4.4 输入边界与锚点、§4.6 代码层钳制 | 只消来源不够：模型仍可自取数，medium 仍会派生 blocking |

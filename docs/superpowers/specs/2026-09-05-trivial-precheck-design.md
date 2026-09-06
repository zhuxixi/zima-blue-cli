# Issue #223：Step 1 trivial 判定前置确定性脚本 — 设计 Spec

- 状态：**待用户批准（已根据 spec review 修订）**
- 日期：2026-09-05
- 范围：zima-blue-cli 仓内 `pi/github-code-review-batch` skill 包（scripts + references/flow.md + references/edge-cases.md + SKILL.md + tests）
- 上游：#212 优化点 1（tracking issue）
- 承接：#206（docs-only 静默空跑，已关闭；已决定 docs-only 暂定 trivial）

> 本文是设计 spec，不是实现计划；获得确认后才可进入 worktree 和 `writing-plans`。

## 1. 背景与问题

github-code-review-batch 的 Step 1（PR 资格审查）由 parent agent 读取 PR 后用 LLM 心证 trivial。docs-only PR 可能因此空跑 5-7 分钟、没有 review 评论、没有 `<zima-review>` verdict；过去 zima executor 还可能把 exit 0 当作 success，误摘 `needs-review` 标签，形成“审完无结论”的假象。

#206 已决策：docs-only PR 暂定 trivial、接受跳过；修复形态是把 trivial 判断变成确定性规则，并且命中后输出有效状态报告和 approved verdict。

**架构边界**：本 issue 修改的是已经启动的 `github-code-review-batch` skill 内部流程，不能阻止 zima PJob 先启动 parent Pi。这里的“无需启动 LLM”严格指：parent 不读取完整 diff 做推理、不执行 Step 2-9、不派发审查 subagent；parent Pi 本身仍会启动并执行少量流程指令。如果要求在 parent Pi 启动前由 zima executor/preExec 短路，需要另开 issue，本 spec 不扩大范围。

## 2. 目标

1. 新增确定性脚本 `scripts/trivial_check.py`，由 Step 1 在首轮候选路径调用。
2. v1 只把以下情况判定为 trivial：PR 为 `OPEN` 且非 draft；成功拿到完整文件列表；没有 rename/copy；至少有一个变更文件；所有变更文件路径都以 `.md` 结尾（大小写不敏感）。
3. 脚本在自身内部复核 pi-cr metadata：只要发现已有有效 metadata，或 metadata 数据无法确认，就不输出 approved 快速报告，避免接入层误调用或历史状态不明时误跳过。
4. trivial 命中时由脚本直接输出状态报告：`Status: PASS`、`Verdict: READY_TO_MERGE`、`Note: trivial precheck skip: ...` 和 approved XML trailer；parent 不手工组装报告 payload，不进入 Step 2-9。
5. GitHub API 失败、数据不完整、数据格式异常、renderer 失败时 fail-open 到现有 Step 1 路径，绝不输出 approved。

## 3. 非目标

- **不新增 Status 枚举值**：保留 `NEEDS_FIX` / `PASS` / `NO_NEW_COMMITS` 三态，避免破坏 zima 调度器的 grep 契约。trivial 用 `PASS`，由 `Note` 标明它是策略性跳过，不是全量审查结论。
- **不把 bot 作者、标题关键词或纯规模阈值作为自动批准条件**：Dependabot/Renovate 也可能修改源代码；`update`/`format` 等标题可能误伤；一行代码也可能是关键修复。后续扩大规则需另开 issue 做误判评估。
- **不改变 closed/draft/自动化 PR 的业务判定逻辑**：trivial 脚本只把 `OPEN` 且非 draft 作为快速路径的安全前置；不满足时返回非 trivial，交回现有 Step 1。
- **不在增量审查中重新判定 trivial**：已有 previous pi-cr metadata 的 PR 继续走现有 `NO_NEW_COMMITS` / delta-review 分支，不用全零 PASS 覆盖历史 findings。脚本内部 metadata 复核是防误调用，不改变该流程边界。
- **不修改 zima executor/preExec**：本 issue 不新增 preExec action，不改 `zima/execution`，不承诺 parent Pi 零启动或 PJob 零模型调用。
- **trivial 命中不发普通 PR review 评论**：只输出终端状态报告；PJob 的 stdout 会被 executor 捕获，approved verdict 用于 postExec 标签流转。
- **不动 cc 版 skill**（如存在独立副本）：本 spec 只改本仓 `pi/` 包。

## 4. 总体设计

### 4.1 改动面

| 改动点 | 文件 | 性质 |
|---|---|---|
| 确定性判定、metadata 防护与报告入口 | `pi/github-code-review-batch/scripts/trivial_check.py` | 新脚本；stdlib-only |
| 状态报告可选说明 | `pi/github-code-review-batch/scripts/render_status_report.py` | 新增可选 `note`，旧 caller 行为不变 |
| Step 0 / Step 1 接入契约 | `pi/github-code-review-batch/references/flow.md` | 明确轮次、退出码和 shell 接线 |
| 边界情况说明 | `pi/github-code-review-batch/references/edge-cases.md` | 更新 trivial 预期行为 |
| 输出契约 | `pi/github-code-review-batch/SKILL.md` | Step 1 trivial 仍需状态报告 |
| 单元与契约测试 | `tests/unit/test_cr_batch_trivial_check.py`、`tests/unit/test_cr_batch_contracts.py` | 纯函数、API fixture、renderer/XML 和文档契约 |

### 4.2 数据流与轮次边界

```text
Step 0：现有 pi-cr metadata 检查
  ├─ 确认无 previous pi-cr metadata（首轮候选）
  │    ↓
  │  Step 1：python3 scripts/trivial_check.py "<PR>" --report
  │    ├─ exit 0：stdout 已是完整状态报告 → 原样保留并结束，不走 Step 2-9
  │    ├─ exit 1：数据有效但非 trivial → 继续现有 closed/draft/自动化检查
  │    └─ exit 2：数据或脚本异常 → 记录 stderr，继续现有 Step 1
  │
  ├─ 有 previous pi-cr metadata
  │    → 保持现有 NO_NEW_COMMITS / delta-review 分支，不运行 precheck
  │
  └─ Step 0 无法确认 metadata 状态
       → 沿用现有完整首轮降级，但不运行 precheck，不得走 approved 快速路径
```

- `trivial_check.py` 自己在 PR 基础字段查询中读取 `reviews`，作为第二道防线复核 metadata：无候选 pi-cr metadata 为 `empty`；发现有效 pi-cr metadata 为 `present`；发现带 pi-cr 标记但 JSON 损坏、reviews 结构异常或 API 失败为 `unavailable`。
- 只有 `metadata_state=empty` 才可能进入 trivial approved 路径；`present` 返回 exit 1；`unavailable` 返回 exit 2。
- `--report` 固定生成 Round-1 报告（`round=1`、`previous_head_sha=null`），因为它只适用于无 previous metadata 的首轮。
- parent Pi 仍会启动，但不会读取 `gh pr diff` 完整内容、不会执行 LLM 推理、不派发 Step 2-9 的审查 agent。节省目标是消除 skill 内的完整 diff 读取和后续审查调用，而不是消除 parent 进程启动。

## 5. 组件设计：`trivial_check.py`

### 5.1 CLI 与退出码

```text
python3 scripts/trivial_check.py <pr> [--repo OWNER/REPO]
python3 scripts/trivial_check.py <pr> --report [--repo OWNER/REPO]
```

- `<pr>` 支持纯数字、`https://github.com/OWNER/REPO/pull/N`、`owner/repo#N`。
- 脚本先把 ref 归一化为 `(owner/repo, number)`，不能把 `owner/repo#N` 原样传给 `gh`；URL / `owner/repo#N` 与显式 `--repo` 冲突时 exit 2；v1 只接受 github.com HTTPS URL。
- 纯数字没有 `--repo` 时，通过当前 worktree 执行 `gh repo view --json nameWithOwner` 解析 repo；所有 repo/ref 均作为 `subprocess.run` 的独立 argv 元素传递，不使用 `shell=True` 或 shell 字符串拼接。
- 默认模式：stdout 输出一个判定 JSON；数据有效时无论 true/false 都 exit 0；数据/API 异常 exit 2。
- `--report` 模式：trivial 且 metadata_state=empty 时 stdout 直接输出最终状态报告并 exit 0；数据有效但非 trivial（包括 metadata_state=present、closed/draft、混合文件、rename、非 `.md`）stdout 为空并 exit 1；数据/API 异常 exit 2。
- flow.md 的 shell 示例必须引用 PR 参数，并显式保存和判断退出码，不能让 exit 1 被外层 `set -e` 当成脚本故障。

### 5.2 GitHub 数据获取与完整性校验

PR 基础字段使用一次 `gh pr view` 获取：

```bash
gh pr view <number> --repo <owner/repo> \\
  --json number,state,isDraft,changedFiles,headRefOid,reviews
```

文件列表使用 REST API 全量分页获取：

```bash
gh api --paginate --slurp \\
  "repos/<owner>/<repo>/pulls/<number>/files?per_page=100"
```

约束如下：

- 不使用 `gh pr view --json files` 作为安全判定依据，因为当前 gh CLI 的 GraphQL 查询只取 `files(first: 100)`；REST 使用 `filename` 字段，不能误读成 GraphQL 的 `path`。
- `--paginate --slurp` 的结果必须是“数组的数组”，实现先校验每页是数组，再 flatten；不能使用 `-f/--field`，避免 GET 被切换成 POST。
- `changedFiles` 必须是非负整数（拒绝 bool），`number` 必须是正整数，`state` / `isDraft` / `headRefOid` 必须存在且类型正确；`headRefOid` 必须是 40 位十六进制字符串。
- 文件记录必须含非空 `filename` 和 `status`；`filename` 必须唯一；status 只接受 GitHub 已知值 `added` / `modified` / `deleted` / `renamed` / `copied` / `changed` / `unchanged`，未知值 exit 2。
- REST flatten 后的文件数必须等于 `changedFiles`。`changedFiles=0` 且文件列表为空是合法数据，交给非 trivial 规则处理；数量不一致（包括只拿到前 100 个文件）exit 2。
- `previous_filename` 非空、status 为 `renamed` 或 `copied` 时，数据有效但非 trivial；不能把 `.py → .md` rename 当成 docs-only。

归一化后的内部数据结构：

```json
{
  "number": 123,
  "state": "OPEN",
  "is_draft": false,
  "head_sha": "40-char-sha",
  "changed_files": 2,
  "metadata_state": "empty",
  "files": [
    {"path": "README.md", "status": "modified", "previous_path": null}
  ]
}
```

### 5.3 metadata 防护

脚本对 `reviews` 做只读、fail-closed 检查，不修改现有 `parse_metadata.py` 的兼容行为：

- `empty`：reviews 结构合法，且没有同时包含 `Generated with pi-coding-agent` 与 `<!-- pi-cr-meta` 的候选评论；
- `present`：存在带上述标记且能解析为 JSON 对象的 pi-cr metadata；此时 `--report` exit 1；
- `unavailable`：reviews 结构非法、API 失败，或存在 pi-cr 标记但 metadata JSON 无法解析；此时 exit 2。

该复核解决 Step 0 误把“parser 输出 `{}`”当成“没有历史”的风险：当前 `parse_metadata.py` 在没有候选评论时也会正常输出 `{}`，因此 precheck 不能只依赖 `{}`。

### 5.4 规则集 v1

所有规则均为确定性规则，且必须全部满足：

| 规则 | 判定 | 不满足时 |
|---|---|---|
| G0 metadata-empty | `metadata_state == "empty"` | `present` → exit 1；`unavailable` → exit 2 |
| G1 eligibility | `state == "OPEN"` 且 `is_draft == false` | exit 1，交回现有 Step 1 |
| G2 non-empty | `changed_files > 0` | exit 1 |
| G3 no rename/copy | 所有文件 status 不是 `renamed`/`copied`，且 `previous_path` 为空 | exit 1 |
| G4 markdown-only | 所有 `path.lower().endswith(".md")` | exit 1 |

标题、作者、变更行数不参与 v1 自动批准。允许漏判，不允许误判。

### 5.5 默认模式输出

```json
{
  "trivial": true,
  "matched_rules": ["markdown-only"],
  "reason": "all 2 changed files have .md extension",
  "stats": {"files_total": 2, "markdown_files": 2, "changed_files": 2},
  "pr": {"number": 123, "state": "OPEN", "is_draft": false, "head_sha": "40-char-sha"},
  "metadata_state": "empty"
}
```

`--report` 复用同一份数据和判定结果，不重新解析或让 parent LLM 手工组装 payload。

## 6. 命中路径与状态报告

### 6.1 `--report` 的确定性接线

`trivial_check.py --report` 直接 import 同目录的 `render_status_report.render()`，完整调用链固定为：

```text
normalize ref → fetch PR/reviews → fetch paginated files → normalize → evaluate
  → build_report_payload → render_status_report.render → stdout
```

只有 G0-G4 全部满足时才调用 renderer。payload 固定包含：

```json
{
  "pr_number": 123,
  "round": 1,
  "head_sha": "40-char-sha",
  "previous_head_sha": null,
  "open_count": 0,
  "new_count": 0,
  "unresolved_count": 0,
  "resolved_count": 0,
  "acknowledged_count": 0,
  "blocking_open_count": 0,
  "blocking_new_count": 0,
  "advisory_open_count": 0,
  "advisory_new_count": 0,
  "critical_count": 0,
  "status": "PASS",
  "note": "trivial precheck skip: all 2 changed files have .md extension"
}
```

stdout 已经是最终报告：含 `Status: PASS`、`Verdict: READY_TO_MERGE`、`Note:` 行和 approved XML trailer。renderer 失败时不输出半截报告，直接 exit 2。

### 6.2 `render_status_report.py` 的可选 note

新增可选输入字段 `note: str`：

- 有非空 note 时，在 `Verdict:` 行之后、`Diff truncated` / `Coverage` 行之前插入 `Note: ...`。
- note 先删除 XML 不允许的控制字符，再把 CR/LF 转为空格、压缩连续空白、限制最大长度 240；该规范化只做一次。
- 人类可读行使用规范化文本；XML `<summary>` 使用同一份规范化原文，并在写出 XML 文本节点前用 `xml.sax.saxutils.escape` 转义 `&<>`，保证 `ReviewParser` 仍能解析出 approved verdict。
- note 为空或缺失时，输出必须与改动前逐字节一致；旧 caller 零影响。
- trivial 路径的 note 只包含固定文案和数字统计，不把未经处理的 PR 标题、路径或 API 原文带入报告。

## 7. 文档契约改动

**`references/flow.md`：**

1. Step 0 分支说明明确：只有成功确认无 previous pi-cr metadata 的首轮才进入 precheck；NO_NEW_COMMITS、delta-review、metadata 状态未知都不进入。Step 0 的 `gh` / parser 失败仍按原有完整首轮降级，但不能把未知状态当成空历史。
2. Step 1 开头加入带引号的命令和退出码处理：

   ```bash
   set +e
   python3 scripts/trivial_check.py "<PR>" --report
   rc=$?
   set -e
   if [ "$rc" -eq 0 ]; then
       # stdout 已是最终状态报告，原样保留并结束
       exit 0
   elif [ "$rc" -eq 1 ]; then
       # 数据有效但非 trivial，继续现有 Step 1 资格检查
       :
   else
       # 脚本/API 异常，记录 stderr，继续现有 Step 1
       :
   fi
   ```

3. 从 Step 1 的检查列表中删除 trivial 条件及“如何判断 trivial PR”的 LLM 心证清单；LLM 只保留 closed/draft/自动化 PR 的现有检查，不再自行宣布 trivial。
4. 明确 parent Pi 仍启动；本优化不读取完整 diff、不派发后续审查 agent。

**`SKILL.md`：**把“除 Step 1/Step 7 提前终止外必须产出三个产物”改成：Step 1 trivial 路径仍豁免终端 review 报告和 PR 评论，但必须产出终端状态报告；Step 7 已停止路径继续不产出。

**`references/edge-cases.md`：**把 trivial 行为更新为：首轮确定性 `.md` precheck；命中输出 PASS + approved 状态报告并结束；数据异常回到现有 Step 1；有 previous metadata 的增量轮不运行 precheck。

## 8. 错误处理与降级

- PR ref 不支持、repo 解析失败、gh 非零退出、超时、非法 JSON、reviews 不可确认、文件页不是数组、文件记录缺字段/未知 status、重复文件名、`changedFiles != len(files)`、`headRefOid` 非法 → exit 2 + stderr；不输出报告。
- state/draft/空文件/rename/copy/非 `.md` 是数据有效但非 trivial → `--report` exit 1；不输出 approved。
- 所有 subprocess 使用 `stdin=subprocess.DEVNULL`、`capture_output=True`、有限 timeout、`check=False`，由调用方统一映射为 exit 2；不使用 `shell=True`。
- renderer 的 note 缺失/为空时保持旧行为；renderer 在 `--report` 中异常时 exit 2，不能输出部分报告。
- 规则判定只使用 PR metadata 和文件列表，不读取完整 diff；脚本不会因为无法获取 diff 而改变结果。

## 9. 可测性拆分设计（实现阶段硬约束）

| 函数 | 职责 | 性质 |
|---|---|---|
| `normalize_pr_ref(ref, explicit_repo)` | 解析数字 / github.com URL / `owner/repo#N`，检测 repo 冲突 | 纯函数 |
| `parse_pr_view(raw)` | 校验 number/state/isDraft/changedFiles/headRefOid/reviews 类型 | 纯函数 |
| `inspect_metadata(reviews)` | 返回 `empty` / `present` / `unavailable` | 纯函数 |
| `flatten_file_pages(raw)` | 校验并 flatten `--paginate --slurp` 数组 | 纯函数 |
| `normalize_file(record)` | REST `filename/status/previous_filename` → 内部结构 | 纯函数 |
| `classify_files(files)` | 统计 markdown/non-markdown/rename/copy/duplicate | 纯函数 |
| `evaluate(pr_data)` | 执行 G0-G4，返回 trivial、规则和 reason | 纯函数 |
| `build_report_payload(pr_data, result)` | 组装固定 Round-1 PASS payload | 纯函数 |
| `format_note(note)` | 控制字符清理、单行化、压缩空白、长度限制 | 纯函数 |
| `fetch_pr_data(ref, repo)` | 执行 repo/view/files 两类 gh 调用并校验 | 唯一外部 IO 入口 |
| `main(argv)` | 参数解析、调用、退出码和 stdout/stderr 组装 | 薄壳 |

测试边界：除 `fetch_pr_data` 外全部纯函数单测；`fetch_pr_data` 使用 mock `subprocess.run` 验证 argv、`--paginate --slurp`、超时、非零退出和 JSON 异常映射；真实 GitHub 交互留给 U1/U2。

## 10. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | PR ref 与基础字段归一化 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_trivial_check.py -k "ref or parse"` | 数字/HTTPS URL/`owner/repo#N` 正确解析；repo 冲突、非 github.com URL、非法 number 拒绝；GraphQL 字段类型和 SHA 校验正确 |
| A2 | metadata 防护 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_trivial_check.py -k "metadata"` | 无 pi 标记为 empty；有效 pi metadata 为 present；损坏 pi metadata、非法 reviews 结构为 unavailable；present 不会产生 approved |
| A3 | 文件列表完整性与 trivial 规则 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_trivial_check.py -k "file or classify or evaluate"` | open+非 draft+metadata empty+完整文件列表+非空+无 rename/copy+纯 `.md` 才为 true；混合文件、空文件、closed/draft、rename/copy、重复文件名不 approved；101 文件隐藏源文件 fixture fail-open |
| A4 | API fetch 与 fail-open | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_trivial_check.py -k "fetch or error or fail_open"` | gh 不存在、超时、非零退出、非法 JSON、分页页结构异常、文件数不一致均 exit 2 且 stdout 为空；命令使用 `--paginate --slurp`，不使用 `-f` |
| A5 | report 与 XML 安全 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_trivial_check.py tests/unit/test_cr_batch_contracts.py` | `--report` 直接产生 PASS/READY_TO_MERGE/approved XML/Note；note 含 `&<>`、换行和控制字符仍能被 `ReviewParser` 解析；无 note 的 golden output 与改动前逐字节一致；非 trivial 不产生报告 |
| A6 | skill 外部契约 | 自动化验证（static/build） | `uv run pytest tests/unit/test_cr_batch_contracts.py && python -m py_compile pi/github-code-review-batch/scripts/trivial_check.py pi/github-code-review-batch/scripts/render_status_report.py && uv run ruff check tests/ && uv run black --check tests/ --line-length 100` | contract test 覆盖新脚本 stdlib-only、Status 三态、旧 renderer caller 兼容、脚本可编译、测试代码 lint/format 通过；测试白名单显式允许同目录本地模块 |
| U1 | docs-only 真实端到端 | 用户实测 | 部署本版本 skill；对一个无 previous pi-cr metadata 的 docs-only PR 打 `zima:needs-review` 触发 CR job | parent Pi 仍启动但不读完整 diff、不派发审查 subagent；skill 内 <1 分钟结束；stdout 含 trivial Note 和 approved XML；`needs-review` 正确摘除、无 `needs-fix`，不发布普通 CR 评论 |
| U2 | 正常代码 PR 回归 | 用户实测 | 对一个无 previous pi-cr metadata、Step 0 metadata 检查成功的正常代码 PR 触发例行 CR | precheck 返回 exit 1，继续完整 Step 1-10；正常 PR 仍产生 review/comment/status report |

## 11. PR 规模约束

生产代码（不含 tests 和 `.md` 文档）以 **≤200 个新增 Python 行**为上限，对齐 zima CR 的全量审查舒适区。实现完成后必须用 `git diff --numstat` 核对；如果超过 200 行，不得在本 PR 内继续堆功能，应回到 issue 重新拆分。测试代码和文档不计入该代码行上限，但 flow.md / SKILL.md 的契约性改动必须人工审阅。

## 12. 关联

- 母 issue：#212（优化点 1）；本 issue：#223
- 承接：#206（docs-only 静默空跑，已关闭）
- 契约参考：#119（Verdict 派生）、#120（覆盖提示）、#176（zima-review XML trailer）
- JFox gotcha：REST PR 文件字段是 `filename`，GraphQL 是 `path`；GraphQL `files` 查询存在前 100 个文件限制
- spec 先例：`docs/superpowers/specs/2026-08-31-cr-failure-guard-design.md`

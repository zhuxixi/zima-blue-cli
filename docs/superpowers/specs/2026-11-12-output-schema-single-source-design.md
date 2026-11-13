# 根因报告与修复设计 — issue #274：spec-reviewer outputSchema 机器可读单源

- 状态：v3 定稿候选，第 2 轮交叉复核已收敛，待用户确认设计
- Drafted: kimi-coding/k3.1-pro (selected) · kimi-coding/k3.1-pro (physical) @ 2026-11-12T08:28:19+08:00
- Revised: kimi-coding/k3.1-pro (selected) · kimi-coding/k3.1-pro (physical) @ 2026-11-12T08:41:10+08:00
- Revised: kimi-coding/k3.1-pro (selected) · kimi-coding/k3.1-pro (physical) @ 2026-11-12T08:53:22+08:00
- 仓库基线：`main`（`31c0655eccde35ec6c4de3d433f174c8428784c0`）
- 上游 issue：zhuxixi/zima-blue-cli#274
- 调研存档：`~/.github-issue-driven/zhuxixi/zima-blue-cli/issue-274/research/`

## 1. 问题与根因

`spec-cross-review` 每轮派发 `spec-reviewer` 时，需要把结构化输出约束作为 `options.outputSchema` 传给 subagent。当前 schema 只存在于 `references/dispatch-contract.md` 的 JavaScript/Markdown 代码块中，父 session 必须重新生成嵌套 JSON；该步骤没有机器可读定义源，也没有结构校验。

两次独立失败证明这不是一次偶然笔误：

1. **文档定义源本身不合法**：`lens` / `verdict` / `level` 三个字符串枚举只有 `enum`、没有 `type:"string"`，Moonshot 在首次派发时以 400 拒绝。局部修正曾使后续派发成功，但没有回流到契约文档。
2. **人工转写破坏嵌套结构**：父 session 手写参数时把根级 `required` 和 `type` 错放进 `properties`，Moonshot 再次以 400 拒绝。程序化重建并检查每层 `required ⊆ properties` 后，同一路径可用。

根因位于“Markdown 定义源 → 父 session 人工转写”这一数据流起点。pi-subagents 的包装与 provider 的校验均按输入工作，不是本 issue 的修复对象。

## 2. 目标

1. 为 outputSchema 建立唯一、机器可读、可解析的定义源 `pi/spec-cross-review/references/output-schema.json`。
2. 父 session 每轮从该文件读取并解析 JSON object，将同一对象传给 `options.outputSchema`；不再从 Markdown 抄写或重建 schema。
3. 把三处已验证修正回流到单源：所有字符串枚举显式声明 `type:"string"`。
4. 用低成本契约测试验证 JSON 合法性、字段语义和每层 `required ⊆ properties`，并阻止 Markdown 副本重新出现。
5. 保持 reviewer 结构化输出的字段、枚举和复核语义不变。

## 3. 非目标与边界

- 不修改 pi-subagents 的包装层，不新增上游客户端校验；issue 中的上游加固只是可选后续事项。
- 不调整五个复核视角、发现分级、收敛条件、模型选择或报告格式。
- 不新增运行时 Python 依赖，不引入 schema 代码生成器；JSON 文件本身就是定义源。
- 不修改 `package.json`：现有 `pi.skills: ["./pi"]` 已覆盖新增 references 文件。
- 不直接编辑本机 `zima-blue-cli-mdbot` 副本；本 issue 只通过主仓隔离 worktree 和 PR 交付。
- 不用契约测试冒充真实 provider 验收；首次实战派发单列为 U1。

## 4. 修复设计

### D1 · 新增机器可读单源

新增 `pi/spec-cross-review/references/output-schema.json`，内容为合法 JSON object，沿用当前契约的完整结构：

- 根级必填：`round`、`reviewedSha256`、`lenses`、`findings`、`counts`、`convergence`。
- `lenses` 固定 5 项；每项含 `lens`、`verdict`、`findingIds`。
- `findings[]` 含 `id`、`level`、`location`、`why`、`suggestion`、`costIfSkipped`。
- `counts` 含 `gaps`、`details`、`passes`；`convergence` 含 `converged`、`summary`。
- `lens` 枚举与 `references/checklist.md` 的五个标题保持一致；`verdict` 为 `核对通过` / `有发现`；`level` 为 `真缺口` / `细化` / `核对通过`。
- 上述三个枚举字段均显式写 `type:"string"`；其他字段类型、数组长度和整数下限保持现契约。
- 不增加 `mode` 字段；Mode 仍由父判定。

该文件以第二次失败后的已验证 `/home/elling/.github-issue-driven/zhuxixi/pi-agent-board/issue-258/research/output-schema-r1.json` 为语义参考，但以仓库内新文件为唯一交付定义源，不在运行时依赖仓库外留痕文件。

### D2 · 派发契约删除可抄写副本

修改 `references/dispatch-contract.md`：

- 开头同时声明 checklist 与 outputSchema 的单一定义源；后者指向 `references/output-schema.json`。
- 删除完整 `const outputSchema = {...}` JavaScript/Markdown 代码块，不保留第二份字段全文。
- `## outputSchema` 只保留派发契约：父使用 read 工具读取 JSON 文件，将其解析为 object，并把该对象作为 `options.outputSchema` 传入；禁止手工重录、复制字段、增删字段或按轮重建。
- 文件缺失、JSON 解析失败或结构契约测试失败时，父不得用手写 schema 兜底；按现有“派发失败”路径停止、留痕并报告。
- child 侧仍只返回结构化报告，回报处置规则不变。

### D3 · SKILL 编排路径同步消费 JSON

修改 `pi/spec-cross-review/SKILL.md` 的每轮编排与相关引用：

- 父在每轮渲染任务时，除读盘注入 `checklist.md` 外，还必须读取并解析 `references/output-schema.json`，将得到的 object 传给 `options.outputSchema`。
- child 的结构化报告契约引用从“dispatch-contract.md 中的 outputSchema”改为“references/output-schema.json”。
- 失败处理明确覆盖 schema 文件缺失或不可解析；处置仍是停止、留痕、不静默重派。

### D4 · 契约测试升级为结构门禁

修改 `tests/unit/test_spec_cross_review_contracts.py`，保持现有 pytest 风格并新增独立测试边界：

1. **读取与解析**：新增 `SCHEMA = SKILL_DIR / "references" / "output-schema.json"`；用 `json.loads(_read(SCHEMA))` 解析，根值必须为 dict。新测试类固定命名为 `TestOutputSchema`，既有 `TestDispatchContract` / `TestSkillStructure` / `TestEdgeCaseCoverage` 类名沿用。
2. **纯递归结构遍历**：新增只接收 dict/list 并产出 schema 节点的辅助函数，不改变被测文件；对每个含 `required` 的 object 节点，验证 `required` 为 list、每个条目为字符串且存在于该节点 `properties`；对含 `properties` 的节点验证它是 dict。
3. **枚举约束**：遍历所有含 `enum` 的节点，验证 `type == "string"`；另精确检查 `lens` / `verdict` / `level`，防止漏字段时遍历测试假绿。
4. **语义契约**：直接对解析后的 JSON 断言根级字段、嵌套字段、数组约束和枚举值；lens 枚举继续与 checklist 标题对应。原先只搜索 Markdown 字段字符串的断言改为消费 JSON。
5. **单源、失败分支与禁止回潮**：`dispatch-contract.md` 必须包含 `references/output-schema.json` 和 `options.outputSchema` 的读盘注入规则，且不得包含 `const outputSchema`；`SKILL.md` 每轮编排必须引用该 JSON 文件。`dispatch-contract.md` 与 `SKILL.md` 均须明确「文件缺失或 JSON 不可解析 → 停止、留痕、不手写兜底、不静默重试」；`references/edge-cases.md` 也须记录该分支。`TestEdgeCaseCoverage` 必须新增 `不手写兜底` 与 `不可解析` 两个字面量 marker 断言，不得复用既有 `schema` marker 充当新分支验证。
6. **回归边界**：保留任务模板占位符、profile、报告模板、edge cases、step-4 wiring 等既有断言，不因本次重构削弱。A1/A2/A3/A5 的验收命令运行完整测试文件而非 pytest `-k` 选择器，避免新类未命名或部分匹配导致漏跑。

### D5 · 变更记录与交付范围

实现时在隔离 worktree 中交付：新 JSON、`dispatch-contract.md`、`SKILL.md`、`references/edge-cases.md`、对应契约测试，以及按仓惯例更新的 `CHANGELOG.md`。spec 与 plan 分别落位为 `docs/superpowers/specs/2026-11-12-output-schema-single-source-design.md` 和 `docs/superpowers/plans/2026-11-12-output-schema-single-source.md`。不直接改主 checkout。

## 5. 可测性拆分设计（实现硬约束）

本次改动是数据文件、文档和静态契约测试，可自动化验证的是 schema 结构与派发文档契约，不是真实模型行为。

| 独立单元 | 责任 | 测试方式与边界 |
|---|---|---|
| `_read(path) -> str` | 读取 UTF-8 文本 | 沿用现有辅助函数；只负责 IO，不嵌套业务断言 |
| `json.loads(...)` 解析结果 | 把机器可读单源变成 dict/list 数据 | 在 fixture 或辅助函数中解析；JSON 非法时测试直接失败 |
| 纯递归 schema 节点遍历 | 访问任意嵌套 object/array 节点 | 只遍历 dict/list，不修改输入；结构约束测试与字段语义测试分开 |
| 结构断言 | 校验 `required ⊆ properties`、required/properties 类型、枚举带 string type | 对完整遍历结果执行；另对三个已知枚举做精确定位断言，避免“字段缺失导致遍历跳过” |
| 语义断言 | 校验根字段、嵌套字段、枚举和 lens/checklist 对齐 | 直接消费解析后的 JSON，不再搜索 Markdown 副本 |
| 文档断言 | 锁定读盘注入路径并禁止 Markdown schema 回潮 | 只检查必要路径/规则与禁止字面量，不复制 JSON 全文到测试 |
| 真实派发验收 | 验证 provider 接受同一 schema | 属 U1 用户实测；unit 测试通过不能替代 |

实现不得把结构遍历与文档字符串断言耦合成一个不可定位失败原因的大测试；每个功能点应能由独立测试名定位。不得为了测试而在 Markdown 或测试代码中重新维护一份完整 schema。

## 6. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | JSON 单源可解析且递归结构合法 | 自动化验证（unit/static） | 在 worktree 根目录运行完整文件：`uv run pytest tests/unit/test_spec_cross_review_contracts.py` | 命令退出码 0，完整文件无 deselected；`TestOutputSchema` 全部用例运行并通过：文件存在且根为 object、每个 object 的 required 键均存在于 properties、所有 enum 节点显式 `type:"string"`（包括 lens/verdict/level） |
| A2 | 结构化输出语义保持不变 | 自动化验证（unit/static） | 在 worktree 根目录运行完整文件：`uv run pytest tests/unit/test_spec_cross_review_contracts.py` | 命令退出码 0，完整文件无 deselected；根级与嵌套必填字段、lenses 5 项约束、counts/convergence 字段、枚举文本和 lens/checklist 对齐全部通过；无 mode 字段 |
| A3 | 父派发路径不再从 Markdown 手工转写 | 自动化验证（unit/static） | 运行上述完整测试文件，并在 worktree 根目录执行 `rg -n "const outputSchema" pi/spec-cross-review` | pytest 退出码 0且完整文件无 deselected；rg 无命中；dispatch-contract 与 SKILL 均指向 JSON 单源并说明传入 `options.outputSchema`，完整 Markdown schema 副本被删除 |
| A4 | 既有流程契约与项目测试不回归 | 自动化验证（integration/build 门禁） | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` | 命令退出码为 0，既有测试全绿，覆盖率不低于 60% |
| A5 | schema 缺失/不可解析失败分支不会手写兜底 | 自动化验证（unit/static） | 在 worktree 根目录运行完整文件：`uv run pytest tests/unit/test_spec_cross_review_contracts.py` | 命令退出码 0且完整文件无 deselected；dispatch-contract、SKILL、edge-cases 均含停止/留痕/不手写兜底/不静默重试契约；`TestEdgeCaseCoverage` 对 `不手写兜底` 与 `不可解析` 两个新字面量的断言均通过 |
| A6 | 变更记录与 spec/plan 落位齐全 | 自动化验证（static/build 检查） | 在设置 `WT` 为 worktree 绝对路径后：`git -C "$WT" diff --name-only origin/main...HEAD`；`test -f` 检查 D5 两个文档路径；`git -C "$WT" diff origin/main...HEAD -- CHANGELOG.md \| rg '^\+.*#274'` | diff 含新 JSON、三份 skill 文档、测试、CHANGELOG 和 D5 的 spec/plan；两个 test 命令退出码 0；CHANGELOG 新增条目含 #274 |
| U1 | 真实 spec-reviewer 首次派发通过 schema 层 | 用户实测 | **可执行时机与部署前置**：PR 合并后，在主 checkout `/home/elling/git-repo/github/zima-blue-cli` 执行 `git checkout main && git pull --ff-only`，用 `git rev-parse HEAD` 记录合并后 commit；从该目录新开 Pi session，确保加载新版 SKILL.md；任选一个真实 issue 执行步 4，父从 `references/output-schema.json` 读盘构造第 1 轮首次派发，不重试、不手写替代 schema | 首次请求不再因 outputSchema 结构/缺 type 被 provider 400；child 进入实际只读复核并返回符合 JSON 契约的结构化报告，reviewedSha256 与被审 spec 一致；记录 run ID、实际模型和报告路径。未执行前状态为 `pending` |

## 7. 失败处理与风险

- JSON 文件缺失或不可解析：实现测试失败；运行时父按派发失败停止，不手写兜底、不静默重试。
- 文档与 JSON 漂移：测试禁止 Markdown 完整副本，字段语义只从 JSON 读取；checklist/lens 对齐继续由测试锁定。
- 结构测试覆盖有限：递归规则能拦截本 issue 两类错误，但不声称覆盖所有 JSON Schema/Moonshot 方言约束，因此保留 U1。
- 本次不改变 reviewer 输出语义，预计无业务流程迁移；所有代码仓改动可逆，真实派发会产生一次 subagent 成本并在 issue 留痕。

## 8. 交付物

1. `pi/spec-cross-review/references/output-schema.json`（新增）
2. `pi/spec-cross-review/references/dispatch-contract.md`（删除 schema 副本，改读盘注入）
3. `pi/spec-cross-review/SKILL.md`（同步每轮编排与失败处理）
4. `pi/spec-cross-review/references/edge-cases.md`（schema 缺失/不可解析失败分支）
5. `tests/unit/test_spec_cross_review_contracts.py`（结构、单源与失败分支契约测试）
6. `CHANGELOG.md`（修复记录）
7. `docs/superpowers/specs/2026-11-12-output-schema-single-source-design.md`
8. `docs/superpowers/plans/2026-11-12-output-schema-single-source.md`

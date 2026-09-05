# Spec: zima-blue-cli 文档自动化链路（issue #228）

> Draft v2 (post-review). 基于 jfox #456 已验证路线 + 本 session 调研 + review 修正。
> 语言决策：面向用户的文档全英文；内部设计文档（本 spec、ADR 正文）保持中文。

## 1. 目标与非目标

**目标**

1. README 呈现双路径配置叙事（CLI 受约束写入 / YAML 直写），明确唯一配置根目录 `${ZIMA_HOME:-~/.zima}/configs/`；
2. `docs/cli-reference.md` 由真实 Typer 命令树确定性生成，杜绝手工快照漂移；
3. **两个受支持的示例配置包**（`examples/webhook/`、`examples/sdd/`）永远可执行（结构校验 + 严格模板渲染校验进 CI）；不覆盖 `examples/` 下其他目录（auto-merge、workflows/ 散例——它们不是 Zima 配置包，无统一安装协议）；
4. CI 漂移门禁：生成物与事实源不一致时，lint job 失败并给出本地重生成命令。

**非目标**

- 不自动生成 README（产品叙事人工维护）；
- 第一轮不做 docs-sync bot（jfox Phase 4）与 AI 文档审查（Phase 5）；
- 不新增 `zima apply/import` 等 CLI 配置写入路径（#196 已决策）；
- 不做 README 命令示例的逐条自动执行验证（人工审阅覆盖）；
- 不给 `examples/` 全目录做通用安装/校验协议（仅两个命名配置包）。

## 2. 总体架构

```
事实源                          生成/校验                    产物               门禁
─────────────────────────────────────────────────────────────────────────────────
zima.cli (真实 Typer app) ──► scripts/generate_cli_docs.py ─► docs/cli-reference.md ─► CI: 重跑生成器
docs/cli-descriptions.yaml ─┘   （结构×描述 双向精确校验）                              + git diff --exit-code
                                                                                    + untracked 检查
examples/{webhook,sdd}/     ─► tests/integration/test_examples_validate.py ─► pytest（CI 已跑）
README.md ────────────────────► 人工基线（PR 1 重写配置章节）
```

分层依据：docs-as-code 防漂移分层顺序（人工基线 → 确定性生成 → CI 门禁）。

## 3. 面向用户文档的英文范围（硬边界）

| 范围 | 处理 |
|---|---|
| **必须英文** | `README.md`、`docs/guides/**`、`docs/cli-reference.md`（生成物）、`docs/cli-descriptions.yaml`、`examples/*/README.md`（PR 1 翻译 `examples/webhook/README.md`；其余实现时核对，已英文则不动） |
| **可保留中文** | `docs/design/**`、`docs/decisions/**`、`docs/history/**`、`docs/reports/**`、workflow YAML 内的业务 prompt 内容（是用户数据不是文档） |

验收方式为**按上表文件清单人工审阅**（U1），不用"中文字符数为零"的机械扫描（会误伤代码示例与合法内容）。

## 4. PR 1 · 文档基线（人工叙事 + API-INTERFACE 内容拆分）

**README.md 重写**（Quick Start / Advanced Usage / CLI Commands 三节）

- 新增 "Configuration" 小节：7 类实体 + 目录表（`configs/{agents,workflows,variables,envs,pmgs,pjobs,schedules}/<code>.yaml`）；
- 双路径叙事：**CLI path**（`quickstart` / `create --example` / `validate`）与 **YAML path**（copy `examples/webhook/` → edit → `validate` → `run`）并列，各自适用场景一句话；
- 所有 YAML path 示例明确目标目录是 `$ZIMA_HOME/configs/`，不是项目目录；
- CLI Commands 节收窄为常用命令概览。

**`docs/guides/configuration.md` 新增**（英文），并**吸收 `docs/API-INTERFACE.md` 的用户相关内容**：目录约定、7 实体最小示例、secret 引用（env/file/cmd/vault，不落明文，来自原 §4 配置文件规范 + §1.5 Env 密钥来源）、validate 工作流（entity validate → pjob validate --check-render → pjob run --dry-run）。

**`docs/API-INTERFACE.md` 拆分迁移后删除**（本 PR 内完成，不留空壳）：

| 原 API-INTERFACE 章节 | 去向 |
|---|---|
| §1 CLI 命令接口（手工快照，已漂移） | 废弃；由 PR 2 的 `docs/cli-reference.md` 取代（PR 1 至 PR 2 落地前的短窗口由 README 命令概览承担） |
| §4 配置文件规范 + §1.5 密钥来源 | → `docs/guides/configuration.md` |
| §2 数据模型接口 / §3 核心运行接口 / §5 执行流程 | → `docs/architecture/data-and-runtime-reference.md`（新文件，中文保留，标注来源） |
| §6 版本历史 | → `CHANGELOG.md` 已覆盖，丢弃 |

- `docs/design/CLI-INTERFACE.md` 顶部加"历史设计稿，非用户参考"标注（不删）；
- README 中所有指向 API-INTERFACE 的链接改为指向 guides 或移除；
- `examples/webhook/README.md` 英文化（内容不变，仅翻译）。

**`docs/decisions/006-docs-architecture.md`（ADR）**：三层边界（README 人工基线 / cli-reference 生成物 / CI 门禁）、面向用户文档英文决策（含 §3 范围表）、替代方案（生成 README / 纯手工 / bot 优先）按 ADR 模板记录否决理由。

**验收**：A8（README 叙事）、A9（ADR）、U1（英文范围清单）。

## 5. PR 2 · CLI Reference 生成器

**事实源与产物**

- `scripts/generate_cli_docs.py`：从 `typer.main.get_command(zima.cli.app)` 提取命令树（不触发 callback 执行）。zima 的 `cli.py` import 无 IO 副作用（`ConfigManager` 懒实例化），无需 jfox 的配置隔离机制。
- `docs/cli-descriptions.yaml`：人工维护，英文一句话描述。**覆盖契约：提取 root + 全部 group + 全部 leaf 的完整路径（当前实测 86 条 = 11 个 group 节点（含 root）+ 75 个 leaf——以提取器输出为准，不写死数量）**，键为完整命令路径（如 `zima pjob actions add`）。
- `docs/cli-reference.md`：生成物，头部 `GENERATED_MARKER`（含重生成命令与 "Do not edit manually"）。

**双源契约**：结构来自命令树，描述只来自 YAML；`validate_descriptions` 双向精确覆盖——**completeness 由"提取路径集合 == 描述键集合"的集合等价证明**，不使用任何数量阈值（数量阈值无法发现"漏提取 N 条但总数仍达标"）。缺失、多余、重复键、空描述均报错退出非零。

**依赖声明**：生成器直接 `import click`（参数归一化需 click 类型），`pyproject.toml` 将 `click` 从传递依赖提升为直接依赖（一行改动）。

**可测性拆分（硬约束）**

```
scripts/generate_cli_docs.py
├── normalize_parameter(param) -> NormalizedParameter      # 纯函数：click 参数 → 展示记录
├── extract_commands(root, name) -> tuple[NormalizedCommand]  # 纯遍历：递归 root+group+leaf，不调 callback
├── load_descriptions(path) -> dict[str, str]              # IO + 格式校验（唯一键/字段白名单/非空）
├── validate_descriptions(paths, descriptions) -> None     # 纯校验：集合等价（missing/unknown 双向）
├── render_reference(commands, descriptions) -> str        # 纯渲染：确定性输出（排序键 = path.split()）
└── write_reference(path, content) -> None                 # IO：统一 LF + UTF-8
```

- 测试边界：`tests/unit/test_generate_cli_docs.py` 用**构造的** click 命令树（不依赖真实 zima.cli，防测试脆）；一条 integration 冒烟（真实 app：关键命令存在断言——`zima pjob actions add` / `zima pjob run` / `zima daemon start` / `zima webhook-server` / `zima quickstart`——且 descriptions 键集 == 提取路径集）。
- **CI ruff/black 范围在本 PR 扩为 `zima/ tests/ scripts/`**（`scripts/` 是本 PR 引入的，质量门随代码同 PR 落地）。

**验收**：A1/A2/A3（unit）+ A10（真实树冒烟 + lint-imports 兼容实证）。

## 6. PR 3 · 示例配置包可执行性校验（纯测试，不加脚本）

**形态决策**：写成 `tests/integration/test_examples_validate.py`——CI 已跑 pytest，零接入成本，覆盖率统计不受影响（`--cov=zima` 不含 examples）。

**覆盖矩阵（按配置包中实际存在的实体校验，缺失类型不视为失败也不声称覆盖）**：

| 配置包 | agent | workflow | variable | env | pjob |
|---|:--:|:--:|:--:|:--:|:--:|
| `examples/webhook/` | ✓(2) | ✓(2) | ✓(1) | ✓(1) | ✓(2) |
| `examples/sdd/` | ✓(4) | ✓(6) | — | ✓(1) | ✓(12) |

（两包均无 pmg / schedule 示例，不在本 PR 范围。）

**可测性拆分**

```
tests/integration/test_examples_validate.py
├── _install_scene(scene_dir, zima_home)     # IO：复制 examples/<scene>/{agents,...} → tmp ZIMA_HOME/configs/
├── _validate_entity(kind, code, store)      # 进程内：ConfigManager.load + <Model>.from_dict + .validate()
└── 用例
    ├── test_webhook_examples_validate       # 矩阵 webhook 行全实体 validate = 0 errors
    ├── test_sdd_examples_validate           # 矩阵 sdd 行同上
    └── test_example_pjobs_strict_render     # 见下：严格渲染契约
```

- 复用 `tests/conftest.py` 的 `isolated_zima_home` fixture（函数级，每用例独立场景安装）。

**严格渲染契约（A7，替代 lenient render + "{{" 残留检查）**：

对配置包内每个 PJob：加载其引用的 workflow，用 `jinja2.meta.find_undeclared_variables` 提取模板变量，为每个变量提供哨兵值（如 `XTEST_<name>`），在 **`StrictUndefined`** 环境下渲染。判据：

1. 渲染不抛 `UndefinedError` / `TemplateError`（证明模板语法正确且无遗漏变量来源）；
2. 输出包含全部哨兵值（证明变量真正被代入而非静默置空）。

**不使用** `PJobExecutor.render_prompt`（lenient 路径，未定义变量静默变空，会产生假阳性）也不检查输出中是否残留 `{{`（模板可合法包含字面量花括号）。sdd 场景的 `issue_number` 等变量在运行时由 webhook/`--set-var` 注入而非静态 Variable 配置——哨兵策略天然覆盖这类"变量来自运行时"的情况。

- **不调 `build_command` / `--show-command`**——那会触发 env secret 解析，CI 环境没有真实 secret 值。
- env 的 secret 条目只验结构（source 合法性），不解析值——与 entity validate 语义一致。

**验收**：A6（结构）/ A7（严格渲染）。

## 7. PR 4 · CI 漂移门禁

**改动 `.github/workflows/integration-test.yml`**（学 jfox PR #477 + #488 补丁；ruff/black 范围已在 PR 2 落地，本 PR 只加 gate 与 paths）：

1. lint job 末尾追加 step "Check generated docs are up to date"：
   ```bash
   uv run python scripts/generate_cli_docs.py
   untracked="$(git ls-files --others --exclude-standard -- docs/cli-reference.md)"
   if ! git diff --exit-code; then tracked_drift=1; else tracked_drift=0; fi
   if [ "$tracked_drift" -ne 0 ] || [ -n "$untracked" ]; then
     echo "::error::Generated docs stale. Regenerate: uv run python scripts/generate_cli_docs.py"
     git diff --name-only; [ -n "$untracked" ] && printf '%s\n' "$untracked"
     exit 1
   fi
   ```
   （untracked 检查堵"删除后重建生成物绕过 diff"漏洞——jfox #488 实证过。）
2. push/pull_request 两处 paths 追加：`'scripts/**'`、`'docs/cli-descriptions.yaml'`、`'**/*.md'`、`'examples/**'`。
3. 生成器依赖 typer/click/pyyaml 均在直接依赖内（PR 2 已提升 click），lint job 零额外安装。

**Zima 特有约束**：lint job 的 import-linter 门禁契约限定 `zima` 包（root_package = zima），`scripts/` 不在分层内，生成器 import `zima.cli` 无违规（PR 2 已实证，本 PR gate 不改变该结论）。

**验收**：A4（CI static）+ A5（gate 逻辑本地自动化自证）。

## 8. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 命令树结构提取 | 自动化（unit） | `uv run pytest tests/unit/test_generate_cli_docs.py -k "extract or normalize"` | 路径/参数/类型/默认值/choices 归一化断言通过 |
| A2 | 描述目录精确覆盖校验 | 自动化（unit） | 同文件 `-k descriptions` | missing / unknown / duplicate key / empty description 四类负例均按预期报错 |
| A3 | 生成物确定性 | 自动化（unit） | 同文件 `-k render` | 同输入两次渲染字节一致；CRLF 输入下产物仍为 LF |
| A4 | 生成物与命令面同步 | 自动化（build/CI static） | CI gate step（PR 4） | `git diff --exit-code` 通过且无 untracked 生成物 |
| A5 | 门禁可拦截漂移 | 自动化（build，本地执行 gate 同款逻辑） | 临时 checkout 制造漂移（改命令参数不重生成）→ 运行 gate step 同款 shell → 恢复重生成 → 再跑 | 红态 exit 非 0 且输出含重生成命令；绿态 exit 0。输出贴 PR 描述 |
| A6 | 示例包结构有效 | 自动化（integration） | `uv run pytest tests/integration/test_examples_validate.py -k validate` | 覆盖矩阵内全部实体 validate = 0 errors |
| A7 | 示例 PJob 模板严格可渲染 | 自动化（integration） | 同文件 `-k strict_render` | StrictUndefined + 哨兵渲染：无异常且全部哨兵值出现在输出 |
| A8 | README 双路径叙事 | 用户实测 | 人工审阅 PR 1 | 用户确认双路径、目录表、示例正确性 |
| A9 | ADR 006 文档架构 | 用户实测 | 人工审阅 ADR | 用户确认边界与替代方案记录 |
| A10 | 真实命令树冒烟 + lint-imports 兼容 | 自动化（integration） | 关键命令存在断言（`pjob actions add` / `pjob run` / `daemon start` / `webhook-server` / `quickstart`）+ descriptions 键集 == 提取路径集；`uv run lint-imports` | 断言全过且契约无违规 |
| U1 | 用户面向文档英文一致性 | 用户实测 | 按 §3 文件清单人工审阅 PR 1/PR 2 | 清单内文件无中文正文（YAML prompt 内容除外） |

## 9. 风险与开放点

| 风险 | 缓解 |
|------|------|
| descriptions YAML 首次编写 ~86 条英文描述工作量 | 逐命令组提交；docstring 已有英文一句话可作底稿 |
| Typer → click 参数类型归一化边界（`List[str]` option、secondary_opts） | A1 用例显式覆盖 multiple/flag/choices；jfox 同款 normalize 逻辑已验证 |
| Windows 生成器输出换行不一致破坏确定性 | `write_reference` 显式 `newline="\n"`（A3 用例） |
| 严格渲染需在测试侧构造 StrictUndefined 环境（执行层无现成 strict 入口） | 测试内直接用 jinja2 Environment(strict_undefined) + meta 提取，不改执行层（lenient 是运行时的刻意设计，不回改） |
| PR 1 拆分 API-INTERFACE 内容迁移遗漏 | 迁移映射表（§4）逐行核对；PR 1 自审 checklist 含"原文件六章节各有去向" |
| gate 后 paths 触发遗漏（同 jfox 踩过的 yaml 不在 `**/*.md` 坑） | PR 4 paths 一次补全 `scripts/**`、`docs/cli-descriptions.yaml`、`examples/**`、`**/*.md` |

## 10. PR 顺序与依赖

PR 1（基线 + API 拆分，无代码依赖）→ PR 2（生成器 + scripts lint 范围 + click 依赖，含 A10）→ PR 3（示例包校验，与 PR 2 无文件冲突但按序落地保持单一主题）→ PR 4（CI gate + paths，依赖 PR 2 的生成器与 lint 范围）。PR 1 与 PR 2 可并行开发；PR 4 必须最后。

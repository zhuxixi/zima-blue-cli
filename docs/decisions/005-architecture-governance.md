# ADR 005: 架构治理契约——隔离领域层 + lint-imports 质量门

## 状态

✅ **已接受** (2026-07-28)

## 背景

本项目长期以 vibe coding 方式演进，没有声明过依赖方向。一次架构体检（`arch-audit`）发现领域核心层 `zima.models` 向外泄漏：

- **反向依赖**：`models → config`（3 处）、`models.actions → providers.defaults`、`scenes → providers.defaults`、`actions.registry → providers`
- **框架泄漏**：`models/env.py` 直接 `import subprocess`（执行 cmd 源密钥）、`models/workflow.py` 直接 `import jinja2`（既校验又完整渲染模板）

这些都没有真依赖环（Tarjan 无 size>1 的 SCC），但方向是反的：被依赖最多的领域包同时也是向外耦合最严重的包，metrics 落在痛苦区（`models` I=0.38、A=0.00、D=0.62、31 个具体类、0 抽象）。

## 讨论过程

关键发现：两处框架泄漏**在 `execution` 里已有重复实现**，且语义不同——

- 真正的执行路径走 `PJobExecutor._resolve_secret`（timeout=10、失败返回 None、Windows `_fix_shell_command`）和 `executor._render_workflow`/`render_prompt`（裸 `Template`、出错吞成 HTML 注释），偏**宽容**；
- `models` 里的那份（`SecretResolver`、`WorkflowConfig.render`）只服务 CLI `env`/`workflow` 命令，偏**严格**（失败即抛）。

所以修复不是「合并」，而是把 CLI 专用的严格逻辑**搬到 `execution` 适配层**，把 `models` 瘦成纯数据。

关于插件注册的回边 `actions.registry → providers`：registry 已经有 `_discover_entry_points()`（走 `zima.action_providers` entry point），却额外硬 import 了 `providers.BUILTIN_PROVIDERS`。实测 entry-point 在 editable install（`uv sync`）下可被发现（`uv run` 会重建 dist-info 的 `entry_points.txt`），于是改用 entry-point 注册内置 github provider，彻底去掉回边。

## 决策

1. **采纳 `.arch-governance.yml` 作为本仓依赖方向的单一事实源**。分层为细粒度线性序（外→内：`__main__` → `cli` → `commands` → `daemon_runner|webhook` → `core` → `providers` → `scenes` → `templates` → `execution` → `review` → `config` → `actions` → `models` → `utils`）。外层可 import 内层，反向即违规。选线性序而非粗粒度分层，是因为 import-linter 把同层 `|` 连接的包视为互斥，粗分组会误伤合法的同层 import。
2. **`zima.models` 是框架无关的领域核**（最内层）。通过 `forbidden_imports` 禁止其 import `subprocess`/`jinja2`/`requests`/`typer`/`rich`。`yaml`（BaseConfig 自序列化）和 `platform`（PMG 平台条件）属刻意设计，不禁。
3. **依赖在缝上倒置**：`models` 通过 `zima/models/ports.py` 的 `ConfigStore` Protocol 依赖抽象，不依赖具体 `ConfigManager`；`ConfigManager` 由调用方注入。密钥解析与模板渲染移至 `zima/execution/secret_resolver.py`、`zima/execution/template_renderer.py`。
4. **内置 provider 走 entry-point 注册**（`pyproject.toml` 的 `[project.entry-points."zima.action_providers"]`），`actions` 层不再 import `providers`。
5. **CI 挂质量门**：`integration-test.yml` 的 `lint` job 在 ruff/black 后跑 `uv run lint-imports`；`.importlinter`/`.arch-governance.yml` 加入 push/PR 的 `paths` 过滤。

## 后果

- 6 条违规全部消除，`layers` 与 `models-no-forbidden` 两个契约变绿；agent 执行路径行为零变更。
- executor 保留**并行的宽松实现**（`_resolve_secret`、`_render_workflow`/`render_prompt`），与 execution 适配层的严格版并存——已在代码里加 `# NOTE: parallel implementation ...` 注释，防日后误以为是重复代码而合并。
- 新增/迁移的测试：`tests/unit/test_secret_resolver.py`、`test_template_renderer.py`、`test_models_defaults.py`。
- 未来若要给 `models` 补抽象（把痛苦区往主序列拉），优先在现有缝上做（env 解析、模板渲染、provider 查找都已倒置到位）。

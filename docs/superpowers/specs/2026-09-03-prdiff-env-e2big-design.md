# Issue #201 Spec：E2BIG 根治 + needs-fix 误标门控

- 状态：**已批准（2026-09-03，用户委托 agent 决策，四项定案见 §6）**
- 日期：2026-09-03
- 范围：zima-blue-cli 的 scan_pr 发现变量注入与 postExec 门控
- 调研依据：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-201/research/`（R1/R2/R3，已评论回 issue）
- 自评修正：`_substitute_env` 字段透传陷阱、`omit_empty` 保留 False、success 条件语义、A4 成本

---

## 1. 根因报告

两个独立缺陷，链路均在调研 R1/R2 源码级确认：

**缺陷 A（E2BIG）**：`_DISCOVERED_TEXT_MAX = 1_048_576`（executor.py:44，#158 引入）按**字符数**截断 `pr_*` 动态变量，但 Linux MAX_ARG_STRLEN = 131072 按**字节**限制单个 envp 字符串（含 `KEY=` 前缀与结尾 NUL）。UTF-8 下 CJK 1 字符 = 3 字节，cap 无论设多大字符数，字节数都可能 3 倍膨胀超限；1MB 的 cap 在字节语义下更是永远等不到生效。Popen 直接 `OSError: [Errno 7] Argument list too long`，agent 从未启动。

**缺陷 B（误标）**：CR PJob 的 `condition: failure` postExec 动作无条件打 `zima:needs-fix` + 摘 `zima:needs-review`。E2BIG 类「审查未发生」的失败（FAILED / returncode=1 / stdout 空）同样命中该条件，导致 PR 被误标 needs-fix 且摘除 needs-review；webhook 只认 needs-review 事件、scan_pr pinned 路径无该标签即 SkipAction → PR 卡死，只能人工重打标签。FailureGuard（#202）只防重复空烧，不防首次误标。

## 2. 修复设计

### 2.1 缺陷 A：字节级截断

**契约不变**：`pr_diff` 等 `pr_*` 变量仍注入 env 与 Jinja 渲染上下文，仅把截断单位从字符改为字节，cap 降至安全值。

- 新常量：`_DISCOVERED_TEXT_MAX_BYTES = 100_000`（单串安全预算 131063 字节，留余量；任何 UTF-8 内容截到 100_000 字节必不触发 E2BIG）。
- 新纯函数（zima/execution/executor.py 或 zima/utils.py）：
  ```python
  def truncate_utf8_bytes(text: str, limit: int) -> str:
      """Truncate text to at most limit UTF-8 bytes without splitting a
      codepoint; the tail is dropped with errors='ignore'."""
  ```
  实现：`text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")`。
- 替换 executor.py:465-477 截断循环的比较与切片；cap 仍作用于所有 `pr_*` 键（语义不变，pr_title/pr_url 同步从 1MB 降到 100KB，无实际影响）。
- 警告文案保留 `"pr_diff exceeds"` 前缀（现有测试断言它），单位从 chars 改 bytes；`test_overlong_pr_diff_truncated_loudly` 断言随之更新。

### 2.2 缺陷 B：opt-in `requireReview` 门控

**不改变任何现有 PJob 的默认行为**；新增字段按需启用。

- `PostExecAction`（zima/models/actions.py）新增布尔字段 `require_review: bool = False`，YAML 别名 `requireReview`。语义：**该 action 仅在 stdout 存在有效 review 信号时执行**；无信号（启动失败/崩溃无 verdict/timeout 无输出）时跳过并打印 warning。
- 判定复用 FailureGuard 的 `_has_valid_review_signal(stdout)`，提升为公共函数 `has_valid_review_signal`（zima/execution/failure_guard.py）：完整 `Status: PASS|NEEDS_FIX|NO_NEW_COMMITS` 行或格式良好的 `<zima-review>` verdict 即视为有效（实测 zc/pi 两类 CR job 成功执行 stdout 均含 Status 行，zc 无 XML——Status 行 fallback 必不可少）。
- **门控点（含关键实现约束）**：`_run_post_exec_actions`（executor.py:1012）计算一次 `has_review = has_valid_review_signal(result.stdout)`，透传给 `ActionsRunner.run(..., has_review_signal: bool = True)`（关键字参数，默认 True 保持旧行为）。**门控判定在 `run()` 循环里对 substitution 之前的原始 action 做**——`_substitute_env`（actions_runner.py:131-140）显式枚举字段重建 PostExecAction，同时必须透传 `require_review`，否则字段丢回 False、门控静默失效。
- 跳过时 print Warning（不写 action_errors、不改变 returncode）。
- `omit_empty` 保留 False（serialization.py:338）：`PostExecAction.to_dict` 覆写，`require_review` 为 False 时丢弃该键，避免所有 YAML 多一行 `requireReview: false` 噪音。
- **`condition: success` 的语义含义（显式声明）**：agent 退出码 0 但无 review 信号（guard 的 `invalid_no_review`）时，`requireReview` 同样跳过「摘 needs-review」——这正是期望语义：无 review 不摘待审标签，与 guard 把该类计入失败 streak 一致。
- 用户本机 CR PJob YAML（~/.zima，不在仓库）需手动给 success/failure 两个 add_label 动作补 `requireReview: true`——spec 通过后执行（附操作片段），是 U1 实测的前置条件。
- 仓库内内置 code-review quickstart 模板（zima/templates/examples.py）同步带 `requireReview: true`，新生成 PJob 默认免疫。

## 3. 可测性拆分设计（实现硬约束）

| 单元 | 形式 | 位置 | 测试边界 |
|------|------|------|----------|
| `truncate_utf8_bytes(text, limit)` | 纯函数 | executor.py 或 utils.py | 输入输出无副作用；覆盖 ASCII 边界、CJK 3 字节码点不劈裂（errors=ignore 尾部丢弃）、空串、limit=0 |
| `has_valid_review_signal(stdout)` | 纯函数（promote 现有私有） | failure_guard.py | 覆盖完整 Status 行、截断 Status 行、合法/非法 zima-review XML、空 stdout（现有 failure_guard 测试已覆盖大部分，补 promote 后导入路径） |
| `PostExecAction.require_review` | 模型字段 + to_dict 覆写 | models/actions.py | YAML roundtrip（`requireReview` 别名、默认 False、False 时 to_dict 丢键、from_dict 仍默认 False） |
| 门控判定 | `run()` 循环三行判断（substitution 之前） | execution/actions_runner.py | mock provider 断言「未调用」；含 `_substitute_env` 透传断言（requireReview 动作经 substitute 后字段保持 True） |
| executor 接线 | 薄接线 | executor.py | 截断循环改字节；`_run_post_exec_actions` 传 `has_review` |

**测试边界**：门控逻辑不依赖 provider 真实行为（fake/mock provider 断言调用与否）；字节截断不依赖真实大 PR（构造字符串直接测）；唯一真实子进程用例直接对 `_run_command` 薄层传大 env 调假命令（`python -c`），不走完整 execute 链路。

## 4. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 字节截断纯函数 | 自动化验证（unit） | 新增单测（文件位置 plan 定） | ASCII 100_000 字节边界恰好截断；CJK 超限截断后 encode 长度 ≤ limit 且无半码点乱码；空串、limit=0 安全 |
| A2 | cap 常量安全 | 自动化验证（static/unit） | 单测断言 `_DISCOVERED_TEXT_MAX_BYTES + len("pr_diff=") + 1 <= 131072` | 任何 UTF-8 值按 cap 截断后不触发 MAX_ARG_STRLEN |
| A3 | executor 截断接线 | 自动化验证（unit） | 复用 `_run_with_discovered`：pr_diff 超 cap（CJK 混合）→ env/render 值 ≤ cap 字节、警告含 `"pr_diff exceeds"` 与 bytes；小 diff 原样 | 结果 SUCCESS；截断值解码无异常；警告输出 |
| A4 | 真实 Popen 不 E2BIG | 自动化验证（integration） | isolated_zima_home 下直接调 executor._run_command，env 注入 100_000 字节 CJK 值，假命令 `python -c "pass"` | returncode 0；不再抛 Argument list too long |
| A5 | requireReview 模型 | 自动化验证（unit） | YAML `requireReview: true/false/缺省` 三态 roundtrip + validate 不报错 + to_dict 在 False 时丢键 | 字段语义正确，缺省 False，旧 YAML 加载不变，序列化无噪音 |
| A6 | postExec 门控 | 自动化验证（unit/integration） | fake provider：无 review 信号 + requireReview → 不调用、有 Warning；`Status: NEEDS_FIX`/zima-review verdict + requireReview → 照常调用；无字段 → 旧行为不变；success 条件无信号 + requireReview → 摘标签被跳过 | 跳过与放行均符合矩阵；含 substitute 透传断言 |
| A7 | 兼容回归 | 自动化验证（integration） | 全量 `uv run pytest tests/unit/ tests/integration/ -q`（含现有 postExec、failure_guard、#158 套件） | 旧执行路径/Status/XML 契约零变化；coverage ≥60% |
| U1 | 真实大 diff PR 端到端 | 用户实测 | **前置**：uv tool 升级 + 本机 CR PJob YAML 补 `requireReview: true`。在 jfox 大 diff PR 打 needs-review 触发 CR：观察 (a) 不再 13s E2BIG；(b) 若仍失败，标签保持 needs-review 不误标 needs-fix | (a)(b) 均成立；失败记录 runtime_state 可解释 |

## 5. 非目标（本版不做）

- 不实现 pr_diff 落临时文件 + `pr_diff_file` 传路径（调研 R3：当前无消费方；留后续 issue）。
- 不改变 pi CR skill / Status / `<zima-review>` / ReviewParser 契约。
- 不调整 FailureGuard 阈值与策略（本修复与其互补，guard 继续管重复空烧）。
- 不做全局「启动失败跳过 failure postExec」默认行为（影响非 CR PJob）。
- 不自动修改用户 ~/.zima 下的 PJob 配置（人工更新，spec 通过后执行）。
- 不处理 EnvConfig file 源 / pmg 参数等其他潜在的大值进 env 路径（用户自控，非 scan 注入）。

## 6. 决策记录（2026-09-03 定案，用户委托 agent 决策）

1. **缺陷 A = 字节级截断 cap 100_000 字节**。否决字符截断（CJK 字节 3 倍膨胀，#205 实证失效）；否决 pr_diff 落文件（当前无消费方，过度设计，列后续 issue）。
2. **缺陷 B = opt-in `requireReview` 字段，默认 False**。否决全局默认（会静默改变非 CR PJob 的失败语义）。
3. **门控信号 = 有效 review 信号**（Status 行 / zima-review XML），复用 FailureGuard 判定。接受连带语义：`condition: success` 动作在「exit 0 但无 review」时同样跳过（不摘 needs-review）——刻意设计，防止无审查静默放行。
4. **配套 = 仓库改内置 quickstart 模板；本机 18 个 CR PJob YAML 由 agent 手动补 `requireReview: true`，diff 交用户过目**。

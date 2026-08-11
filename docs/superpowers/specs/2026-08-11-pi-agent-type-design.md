# Spec: pi-coding-agent as a new agent type for code review

- **Issue**: https://github.com/zhuxixi/zima-blue-cli/issues/143
- **Date**: 2026-08-11
- **Status**: Draft (pending user approval)

## 概述

为 zima 新增 `pi` agent type，让 zima 能以子进程方式调用 `pi -p`（pi-coding-agent 的 print 模式）执行 code review，替代已清理的 kimi CR 任务（Kimi 涨价后不划算）。pi 通过 ollama provider 调 `deepseek-v4-flash:0731-cloud` 云模型（ollama.com 托管，本地无 GPU），成本低于 Kimi。

## 背景

本机原有 5 套 kimi CR PJob（zima/jfox/boktionary/scan2book/voice-input），因 Kimi 涨价已全部清理（20 个配置 + schedule 引用）。pi-coding-agent 已成为本机主力 coding agent，其 headless 模式（`pi -p` + stdin pipe）与 zima 现有 claude 类型执行路径几乎同构——executor 的 `needs_stdin_pipe` + `subprocess.Popen(stdin=prompt_file, cwd=work_dir)` 机制可直接复用，executor 本身零改动。

## 目标

1. zima 原生支持 `type: pi` 的 Agent 配置，`zima agent create --type pi` 可创建。
2. `_build_pi_command` 构造正确的 `pi -p` 命令（含 provider/model/thinking/tools 等参数化 flag）。
3. pi agent 经 stdin pipe 接收 prompt（与 claude 同机制），工作目录靠 `Popen(cwd=)`。
4. 保留现有 `<zima-review>` XML verdict + 标签流转契约。
5. 配套测试覆盖 pi 的 create/validate/build_command/needs_stdin_pipe。

## 架构与组件

### 改动边界

只动 Agent type 识别 + 命令构造层。**executor、ReviewParser、ConfigBundle 零改动**——pi 复用 claude 的 stdin pipe 执行路径和现有 review 解析逻辑。

### 核心组件契约

**AgentConfig（`zima/models/agent.py`）**：
- `type="pi"` → `needs_stdin_pipe` 返回 `True`（prompt 经 stdin，与 claude 一致）
- `get_cli_command_template()` 对 pi 返回 `["pi", "-p"]`（除非 `mockCommand` 覆盖）
- 新增 `_build_pi_command(cmd, params) -> list[str]`：把 camelCase 参数转成 pi CLI flag
- `build_command()` 加 `elif self.type == "pi"` 分支
- prompt 传递：pi 与 claude 一样，prompt_file 由 executor 作为 stdin pipe，**不加到 cmd**

**PJobExecutor（`zima/execution/executor.py`）**：零改动。现有 `stdin_file = prompt_file if bundle.agent.needs_stdin_pipe else None` + `Popen(stdin=stdin_handle, cwd=work_dir)` 自动适用 pi。

**ReviewParser（`zima/review/parser.py`）**：零改动。已支持从 stdout 正则提取 `<zima-review>` verdict 映射 effective_returncode。

## 数据流

```
zima pjob run <pi-cr-job>
  → 加载 PJobConfig (agent: pi-cr-agent, workflow: pi-cr-workflow)
  → 解析 bundle (agent + workflow + variable + env)
  → preExec: scan_pr (扫 zima:needs-review 标签的 PR)
  → 渲染 workflow 模板 → prompt.md (含 CR 指令 + 要求输出 <zima-review> + 用 gh 发评论)
  → build_command: ["pi","-p","--provider","ollama","--model","deepseek-v4-flash:0731-cloud",
                    "--thinking","max","--no-session","--mode","text",
                    "--tools","read,bash,grep,find,ls"]
  → Popen(stdin=prompt.md, cwd=work_dir)
  → pi 子进程:
      - 读 stdin 拿 CR prompt
      - 用 bash 跑 gh pr comment 发 review 评论到 PR
      - 输出 <zima-review><verdict>...</verdict>...</zima-review> 到 stdout
  → 捕获 stdout
  → ReviewParser.parse(stdout) → verdict (approved/needs_fix/needs_discussion)
  → effective_returncode = 0 if approved else 1
  → postExec: add_label 按 effective_returncode
      - approved → remove zima:needs-review
      - needs_fix/needs_discussion → add zima:needs-fix, remove zima:needs-review
  → 记录历史
```

## _build_pi_command flag 设计

基于 `pi --help` 实际 flag。参数用 camelCase（与 claude 一致，PR #58 统一序列化）。

| 参数（camelCase） | pi CLI flag | 默认 | 说明 |
|------------------|------------|------|------|
| `provider` | `--provider` | 必配 | 如 `ollama`；pi 比 claude 多一维 |
| `model` | `--model` | 必配 | 如 `deepseek-v4-flash:0731-cloud` |
| `thinking` | `--thinking` | `max` | CR 需深度思考，默认 max，可配；见决策 4 |
| `noSession` | `--no-session` | `true` | CR 一次性，不存 session |
| `outputFormat` | `--mode` | `text` | **注意：pi 用 `--mode`，不是 claude 的 `--output-format`**；值 text/json/rpc |
| `tools` | `--tools` | `[read,bash,grep,find,ls]` | 只读白名单，见决策 7 |
| `excludeTools` | `--exclude-tools` | — | 可选黑名单 |
| `noContextFiles` | `--no-context-files` | `false` | 见决策 5 |
| `systemPrompt` | `--system-prompt` | — | 可选 |
| `appendSystemPrompt` | `--append-system-prompt` | — | 可选 |
| `mockCommand` | （覆盖整个命令） | — | 测试用，与 kimi/claude 一致 |

**不支持的 flag**（CR 不需要）：`--continue`/`--resume`/`--session`/`--session-id`/`--fork`（session 续接，CR 一次性）、`--export`、`--tui-mode`、`--list-models`。**pi 无 `--add-dir` 等价 flag**，addDirs 对 pi 暂不支持（CR 在单个 repo 跑，不需要）。

## AGENT_PARAMETER_TEMPLATES["pi"]

```python
"pi": {
    "provider": "",          # 必须由配置指定
    "model": "",             # 必须由配置指定
    "thinking": "max",
    "noSession": True,
    "outputFormat": "text",
    "tools": ["read", "bash", "grep", "find", "ls"],
    "noContextFiles": False,
    "addDirs": [],
}
```

## 关键设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 退出码 vs XML verdict | 靠 `<zima-review>` verdict | pi 进程成功即 returncode=0，与 review 结论无关；退出码无法区分 approved/needs_fix。executor 已支持 verdict 映射 effective_returncode，要求 workflow prompt 强制输出 `<zima-review>` |
| 2 | prompt 传递 | stdin pipe（`needs_stdin_pipe=True`） | 与 claude 同机制，executor 零改动复用。**已实测验证**：`echo "..." | pi -p` 成功（deepseek-v4-flash:0731-cloud，exit 0），zima 的 `Popen(stdin=prompt_file)` + `pi -p` 机制可行 |
| 3 | work-dir | 不传 flag，靠 `Popen(cwd=work_dir)` | 学 PR #71：pi 无 `--work-dir`/`--cwd` flag，工作目录靠 executor 的 Popen cwd 处理 |
| 4 | thinking | 默认 `max`（可配） | CR 是深度推理任务（理解代码、找 bug、判断设计），需最强思考等级。jfox「DeepSeek 批量结构化生成」关 thinking 的结论针对批量/轻量/不需推理任务（10× 快），**不适用 CR**。用户明确要 max。ollama thinkingLevelMap 需支持 `max→max`（配置层 models.json） |
| 5 | `--no-context-files` | 默认 `false`（读项目 AGENTS.md） | CR 跑在 bot clone，读项目 AGENTS.md/CLAUDE.md 提供项目规范上下文有助 CR 质量；可配 true 关掉 |
| 6 | 输出模式 | `--mode text` | ReviewParser 从 stdout 正则找 `<zima-review>`，text 够用；`--mode json` 是未来优化，本次不做 |
| 7 | tools 白名单 | `read,bash,grep,find,ls`（只读 A 方案） | pi 替代的是已删的 kimi cr（只读 review）。bash 给：跑 gh 发 PR 评论 + git diff 读改动 + gh pr 读 PR；不给 edit/write：pi 不碰代码。基于 27 个 zima 自动 CR session 实测数据（Bash 287/Read 37/Edit 32/Grep 2）——其中 Edit 是 zc 的 review-fix 闭环用的，pi 只做只读 review 不需要 |
| 8 | PR 评论机制 | agent 自发（pi 用 bash 跑 gh） | 跟 kimi/zc 现状一致（postExec 只有 add_label，评论一直由 agent 用 gh 自发）；pi workflow 模板指示 pi 用 `gh pr comment` 发评论 |

## 错误处理与降级

1. **stdin pipe 已验证可行**（决策 2）：实测 `echo "..." | pi --provider ollama --model deepseek-v4-flash:0731-cloud --thinking off --no-session -p` 成功（exit 0）。fallback 方案备而不用：`pi -p "$(cat prompt.md)"`（ARG_MAX 风险）或 `--mode json` 管道。
2. **pi 未安装**：`get_cli_command_template` 返回 `["pi","-p"]`，Popen 会 FileNotFoundError，executor 已有 `_friendly_error` 处理 FileNotFoundError → "File not found"。
3. **provider/model 未配**：`_build_pi_command` 不校验 provider/model 非空（保持与 claude 的 model 可省略一致，PR #55），由 pi 子进程报错；executor 捕获非零退出码 + stderr。
4. **thinking 等级生效**：`--thinking max` 经 pi 的 ollama provider thinkingLevelMap 映射 `max→max` 才生效。这是配置层（本机 `~/.pi/agent/models.json`）的事，代码层只确保传 `--thinking max`。jfox「Ollama reasoning_effort 实测行为」：取 max 被接受且响应带 reasoning；不传时默认仍思考但非 max 档，故显式传 max 确保最高档。
5. **pi 工具名核对**：`--tools` 白名单的 `read/bash/grep/find/ls` 须是 pi 内置工具名，实现时核对 pi 实际工具名（README 示例 `pi --tools read,grep,find,ls` 已佐证）。

## 测试策略

- **单元 `tests/unit/test_models_agent.py`**：
  - 更新 `VALID_AGENT_TYPES == {"kimi","claude","pi"}` 断言
  - `test_create_pi_agent`：create + type 校验
  - `test_build_pi_command`：各 flag 正确构造（含 `--mode` 而非 `--output-format`、`--thinking max`、`--no-session`、`--tools` 逗号拼接）
  - `test_pi_needs_stdin_pipe`：返回 True
  - `test_pi_no_work_dir_flag`：不传 work-dir/cwd
- **单元 `tests/unit/test_utils.py`**：更新 utils.py 那份 `VALID_AGENT_TYPES` 断言
- **单元 `tests/unit/test_models_env.py`**：`VALID_ENV_FOR_TYPES` 加 pi 的断言（如现有测试覆盖）
- **单元 `test_models_pmg.py`（如存在）**：`VALID_PMG_FOR_TYPES` 加 pi 的断言
- **集成 `tests/integration/test_agent_commands.py`**：`zima agent create --type pi` CLI 流程 + `zima agent types` 显示 pi
- 用 `mockCommand` 覆盖真实 pi 调用（现有测试套路），不依赖真实 pi 安装

## 非目标（本次不做）

- **配置层**：5 套 CR 流切 pi（本机 `~/.zima/configs/` 新建 pi agent/workflow/variable/pjob）。注：pi 侧 `~/.pi/agent/models.json` 已配好 ollama provider 的 `deepseek-v4-flash:0731-cloud`（含 thinkingLevelMap max→max），ollama 已 pull 该模型，部署前置就绪，只剩 zima 配置层。本机部署，不进仓库，issue 已划清边界。
- **quickstart 支持 pi**：`quickstart.py` 注入 pi 默认参数（issue #106 类似），YAGNI，后续单独 issue。
- **`--mode json` 结构化输出解析**：未来优化，text 模式够用。
- **pi_runner.py**：不需要，主路径用 executor 通用 subprocess。
- **review-fix 闭环（B 方案）**：pi 只做只读 review，fix 由 zc（claude）或人做。pi 不给 edit/write。

## 代码层文件清单（约 12 文件）

| 文件 | 改动 |
|------|------|
| `zima/models/agent.py` | `VALID_AGENT_TYPES` 加 `"pi"`；`AGENT_PARAMETER_TEMPLATES` 加 pi 模板；`get_cli_command_template()` 加 `pi:["pi","-p"]`；新增 `_build_pi_command()`；`build_command()` 加 pi 分支；`needs_stdin_pipe` 对 pi True |
| `zima/utils.py` | 第 259 行 `VALID_AGENT_TYPES = {"kimi","claude"}` 加 `"pi"`（重复定义，后续可合并去重） |
| `zima/models/env.py` | `VALID_ENV_FOR_TYPES = {"kimi","claude"}` 加 `"pi"` |
| `zima/models/pmg.py` | `VALID_PMG_FOR_TYPES = {"kimi","claude"}` 加 `"pi"` |
| `zima/commands/agent.py` | 第 28 行 `--type` help 文本补 pi；第 430 行 descriptions 字典加 `"pi"`；example 提示补 pi |
| `zima/templates/examples.py` | Agent example 加 pi 版本；第 87 行 `forTypes:[kimi,claude]` 加 pi |
| `AGENTS.md` | 扩展点文档的 agent type 列表补 pi |
| `CLAUDE.md` | 同上（若有 type 列表） |
| `tests/unit/test_models_agent.py` | 更新断言 + 补 pi 测试 |
| `tests/unit/test_utils.py` | 更新 VALID_AGENT_TYPES 断言 |
| `tests/unit/test_models_env.py` | 更新 VALID_ENV_FOR_TYPES 断言 |
| `tests/integration/test_agent_commands.py` | 补 `--type pi` CLI 测试 |

## 风险与验证项

1. **stdin pipe**（决策 2）：**已实测验证可行**（`echo | pi -p` 成功，exit 0）。唯一技术风险解除。
2. **pi 工具名**：`read/bash/grep/find/ls` 实现时核对 pi 实际内置工具名。
3. **thinking 等级**：依赖本机 models.json 配置层配好 thinkingLevelMap（支持 max→max），代码层只管传 `--thinking max`。
4. **CR 耗时与 timeout**：thinking max 显著增加 CR 耗时（jfox 实测开思考比关思考慢约 10×）。zima pjob 的 `execution.timeout` 默认 600s，thinking max 的 CR 可能超时。配置层需把 pi CR pjob 的 timeout 调大（建议 1800s+）。代码层不涉及 timeout（由 pjob 配置）。
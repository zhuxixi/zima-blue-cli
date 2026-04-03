# Zima CLI 接口设计文档
> ⚠️ 本文档写于实现前，部分内容可能已与代码不一致。最新状态请参考代码和 `docs/API-INTERFACE.md`。

> 本文档定义 zima CLI 的命令接口，包括五组配置的 CRUD 操作和 PJob 管理。

---

## 📋 目录

1. [命令总览](#1-命令总览)
2. [全局选项](#2-全局选项)
3. [Agent 管理](#3-agent-管理)
4. [Workflow 管理](#4-workflow-管理)
5. [Variable 管理](#5-variable-管理)
6. [Env 管理](#6-env-管理)
7. [PMG 管理](#7-pmg-管理)
8. [PJob 管理](#8-pjob-管理)
9. [系统命令](#9-系统命令)

---

## 1. 命令总览

```
zima
├── agent          # Agent 配置管理
├── workflow       # Workflow 配置管理
├── variable       # Variable 配置管理
├── env            # Env 配置管理
├── pmg            # PMG 配置管理
├── pjob           # Plain Job 管理
└── system         # 系统命令
    ├── init       # 初始化 zima
    ├── doctor     # 诊断检查
    └── version    # 版本信息
```

---

## 2. 全局选项

```bash
zima [GLOBAL_OPTIONS] <command>
```

| 选项 | 简写 | 说明 |
|------|------|------|
| `--config` | `-c` | 指定配置文件目录 |
| `--verbose` | `-v` | 详细输出模式 |
| `--quiet` | `-q` | 静默模式 |
| `--help` | `-h` | 显示帮助 |
| `--version` | `-V` | 显示版本 |

---

## 3. Agent 管理

**命令**: `zima agent <subcommand>`

### 3.1 创建 Agent

```bash
zima agent create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ✅ | 显示名称 |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--type` | `-t` | string | ✅ | 实例类型 (kimi/claude/gemini) |
| `--description` | `-d` | string | ❌ | 描述 |
| `--from` | `-f` | string | ❌ | 从现有配置复制 |
| `--interactive` | `-i` | bool | ❌ | 交互式创建 |

**示例**:

```bash
# 基础创建
zima agent create \
  --name "测试用 Agent" \
  --code test-agent \
  --type kimi \
  --description "用于测试的 Agent"

# 从现有配置复制
zima agent create \
  --name "生产环境 Agent" \
  --code prod-agent \
  --type kimi \
  --from test-agent

# 交互式创建
zima agent create --interactive
```

### 3.2 更新 Agent

```bash
zima agent update <code> [OPTIONS]
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | Agent 编码 |

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 显示名称 |
| `--description` | `-d` | string | 描述 |
| `--set-param` | `-p` | key=value | 设置参数 |
| `--remove-param` | `-r` | string | 移除参数 |
| `--set-default` | | key=value | 设置默认关联 |

**示例**:

```bash
# 更新名称和描述
zima agent update test-agent \
  --name "更新后的名称" \
  --description "新的描述"

# 设置参数
zima agent update test-agent \
  --set-param model=kimi-k2-072515-preview \
  --set-param yolo=true

# 设置默认 workflow
zima agent update test-agent \
  --set-default workflow=code-review-workflow
```

### 3.3 删除 Agent

```bash
zima agent delete <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--force` | `-f` | bool | 强制删除，不提示 |
| `--cascade` | | bool | 级联删除关联的 pjobs |

**示例**:

```bash
zima agent delete test-agent
zima agent delete test-agent --force
```

### 3.4 列出 Agents

```bash
zima agent list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--type` | `-t` | string | 按类型筛选 |
| `--format` | | string | 输出格式 (table/json/yaml) |
| `--all` | `-a` | bool | 显示详细信息 |

**示例**:

```bash
zima agent list
zima agent list --type kimi
zima agent list --format json
zima agent list --all
```

### 3.5 查看 Agent 详情

```bash
zima agent show <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--format` | | string | 输出格式 (yaml/json) |

**示例**:

```bash
zima agent show test-agent
zima agent show test-agent --format json
```

### 3.6 编辑 Agent

使用系统默认编辑器打开配置文件。

```bash
zima agent edit <code>
```

### 3.7 验证 Agent 配置

```bash
zima agent validate <code>
```

**示例**:

```bash
zima agent validate test-agent
# 输出: ✓ Agent 'test-agent' 配置有效
```

### 3.8 测试 Agent 启动

测试生成启动命令，但不实际执行。

```bash
zima agent test <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--workflow` | `-w` | string | 指定 workflow |
| `--variable` | `-v` | string | 指定 variable |
| `--env` | `-e` | string | 指定 env |
| `--pmg` | `-p` | string | 指定 pmg |

**示例**:

```bash
zima agent test test-agent
# 输出生成的命令行
```

---

## 4. Workflow 管理

**命令**: `zima workflow <subcommand>`

### 4.1 创建 Workflow

```bash
zima workflow create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ✅ | 显示名称 |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--description` | `-d` | string | ❌ | 描述 |
| `--from-file` | `-f` | path | ❌ | 从文件导入模板 |
| `--template` | `-t` | string | ❌ | 模板内容（直接输入） |
| `--editor` | `-e` | bool | ❌ | 使用编辑器创建 |

**示例**:

```bash
# 交互式创建
zima workflow create \
  --name "代码审查工作流" \
  --code code-review \
  --description "系统化的代码审查流程"

# 从文件导入
zima workflow create \
  --name "Bug 修复工作流" \
  --code bug-fix \
  --from-file ./prompts/bug-fix.md

# 使用编辑器
zima workflow create --code my-workflow --editor
```

### 4.2 更新 Workflow

```bash
zima workflow update <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 显示名称 |
| `--description` | `-d` | string | 描述 |
| `--template` | `-t` | string | 模板内容 |
| `--from-file` | `-f` | path | 从文件更新模板 |
| `--add-skill` | | string | 添加技能引用 |
| `--remove-skill` | | string | 移除技能引用 |

**示例**:

```bash
zima workflow update code-review \
  --name "更新的名称" \
  --add-skill advanced-code-review
```

### 4.3 删除 Workflow

```bash
zima workflow delete <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--force` | `-f` | bool | 强制删除 |

### 4.4 列出 Workflows

```bash
zima workflow list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--tag` | `-t` | string | 按标签筛选 |
| `--format` | | string | 输出格式 |

**示例**:

```bash
zima workflow list
zima workflow list --tag code-review
```

### 4.5 查看 Workflow

```bash
zima workflow show <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--render` | `-r` | string | 使用指定 variable 渲染模板 |
| `--format` | | string | 输出格式 |

**示例**:

```bash
zima workflow show code-review
zima workflow show code-review --render v1g
```

### 4.6 编辑 Workflow

```bash
zima workflow edit <code>
```

### 4.7 验证 Workflow

```bash
zima workflow validate <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--with-variable` | `-v` | string | 使用指定 variable 验证 |

### 4.8 渲染 Workflow

渲染模板并输出最终结果。

```bash
zima workflow render <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--variable` | `-v` | string | ✅ | 使用的 variable |
| `--output` | `-o` | path | ❌ | 输出到文件 |

**示例**:

```bash
zima workflow render code-review --variable v1g
zima workflow render code-review --variable v1g --output ./rendered.md
```

---

## 5. Variable 管理

**命令**: `zima variable <subcommand>`

### 5.1 创建 Variable

```bash
zima variable create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ✅ | 显示名称 |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--description` | `-d` | string | ❌ | 描述 |
| `--for-workflow` | `-w` | string | ❌ | 关联的 workflow |
| `--from-file` | `-f` | path | ❌ | 从 YAML/JSON 文件导入 |
| `--editor` | `-e` | bool | ❌ | 使用编辑器 |
| `--set` | `-s` | key=value | ❌ | 设置变量值 |

**示例**:

```bash
# 基础创建
zima variable create \
  --name "代码审查变量组" \
  --code v1g \
  --for-workflow code-review

# 从文件导入
zima variable create \
  --name "Python 项目变量" \
  --code python-vars \
  --from-file ./vars.yaml

# 使用编辑器
zima variable create --code my-vars --editor

# 直接设置变量
zima variable create \
  --code quick-vars \
  --set "task.name=快速任务" \
  --set "task.objective=完成代码审查"
```

### 5.2 更新 Variable

```bash
zima variable update <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 显示名称 |
| `--description` | `-d` | string | 描述 |
| `--set` | `-s` | key=value | 设置变量值 |
| `--remove` | `-r` | string | 移除变量 |
| `--merge-file` | `-f` | path | 从文件合并 |

**示例**:

```bash
zima variable update v1g \
  --set "task.name=新任务名称" \
  --set "agent.role=架构师"
```

### 5.3 删除 Variable

```bash
zima variable delete <code> [OPTIONS]
```

### 5.4 列出 Variables

```bash
zima variable list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--for-workflow` | `-w` | string | 筛选适用于指定 workflow 的变量 |
| `--format` | | string | 输出格式 |

### 5.5 查看 Variable

```bash
zima variable show <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--format` | | string | 输出格式 (yaml/json) |

### 5.6 编辑 Variable

```bash
zima variable edit <code>
```

---

## 6. Env 管理

**命令**: `zima env <subcommand>`

### 6.1 创建 Env

```bash
zima env create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ✅ | 显示名称 |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--description` | `-d` | string | ❌ | 描述 |
| `--from-file` | `-f` | path | ❌ | 从 .env 文件导入 |
| `--editor` | `-e` | bool | ❌ | 使用编辑器 |
| `--set` | `-s` | key=value | ❌ | 设置环境变量 |
| `--for-type` | `-t` | string | ❌ | 指定 Agent 类型 |

**示例**:

```bash
# 基础创建
zima env create \
  --name "Claude 第三方环境" \
  --code env3 \
  --description "使用 GLM 代理的 Claude"

# 从 .env 文件导入
zima env create \
  --name "生产环境" \
  --code prod-env \
  --from-file ./.env.prod

# 直接设置变量
zima env create \
  --code kimi-env \
  --for-type kimi \
  --set "KIMI_API_KEY=${KIMI_KEY}" \
  --set "KIMI_MODEL=kimi-k2-072515-preview"
```

### 6.2 更新 Env

```bash
zima env update <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 显示名称 |
| `--description` | `-d` | string | 描述 |
| `--set` | `-s` | key=value | 设置变量 |
| `--remove` | `-r` | string | 移除变量 |
| `--set-secret` | | name=source | 设置密钥引用 |
| `--override` | `-o` | bool | 设置 overrideExisting |

### 6.3 删除 Env

```bash
zima env delete <code> [OPTIONS]
```

### 6.4 列出 Envs

```bash
zima env list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--for-type` | `-t` | string | 按 Agent 类型筛选 |
| `--format` | | string | 输出格式 |

### 6.5 查看 Env

```bash
zima env show <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--format` | | string | 输出格式 |
| `--expand` | `-e` | bool | 展开密钥引用（显示实际值） |

**示例**:

```bash
zima env show env3
zima env show env3 --expand
```

### 6.6 编辑 Env

```bash
zima env edit <code>
```

### 6.7 验证 Secrets

验证所有密钥引用是否有效。

```bash
zima env verify-secrets <code>
```

**示例**:

```bash
zima env verify-secrets env3
# 输出:
# ✓ ANTHROPIC_API_KEY (source: env) - OK
# ✓ KIMI_API_KEY (source: file) - OK
# ✗ GOOGLE_API_KEY (source: cmd) - FAILED: command not found
```

---

## 7. PMG 管理

**命令**: `zima pmg <subcommand>`

### 7.1 创建 PMG

```bash
zima pmg create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ✅ | 显示名称 |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--description` | `-d` | string | ❌ | 描述 |
| `--for-type` | `-t` | string | ❌ | 适用的 Agent 类型 |
| `--extends` | `-e` | string | ❌ | 继承的 PMG |
| `--editor` | | bool | ❌ | 使用编辑器 |

**示例**:

```bash
zima pmg create \
  --name "Kimi 默认参数组" \
  --code kimi-default-pmg \
  --for-type kimi \
  --description "Kimi CLI 的默认启动参数"

zima pmg create \
  --name "详细模式参数组" \
  --code verbose-pmg \
  --extends kimi-default-pmg
```

### 7.2 更新 PMG

```bash
zima pmg update <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 显示名称 |
| `--description` | `-d` | string | 描述 |
| `--add-param` | `-a` | string | 添加参数（JSON 格式） |
| `--remove-param` | `-r` | string | 移除参数 |
| `--set-raw` | | string | 设置 raw 字符串 |
| `--add-condition` | | string | 添加条件参数 |

**示例**:

```bash
zima pmg update kimi-default-pmg \
  --add-param '{"name":"quiet","type":"flag","enabled":true}'
```

### 7.3 删除 PMG

```bash
zima pmg delete <code> [OPTIONS]
```

### 7.4 列出 PMGs

```bash
zima pmg list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--for-type` | `-t` | string | 按 Agent 类型筛选 |
| `--format` | | string | 输出格式 |

### 7.5 查看 PMG

```bash
zima pmg show <code> [OPTIONS]
```

### 7.6 编辑 PMG

```bash
zima pmg edit <code>
```

### 7.7 预览生成的参数

```bash
zima pmg preview <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--for-os` | | string | 指定操作系统 |
| `--with-env` | `-e` | string | 加载指定 env 以评估条件 |

**示例**:

```bash
zima pmg preview kimi-default-pmg
# 输出: --print --yolo --max-steps-per-turn 50 --max-ralph-iterations 10
```

---

## 8. PJob 管理

**命令**: `zima pjob <subcommand>`

PJob（Plain Job）是配置的组合执行单元，将 agent、workflow、variable、env、pmg 组合成可执行的命令。

### 8.1 创建 PJob

```bash
zima pjob create [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `--name` | `-n` | string | ❌ | 显示名称（默认继承 agent 名称） |
| `--code` | `-c` | string | ✅ | 唯一编码 |
| `--description` | `-d` | string | ❌ | 描述 |
| `--agent` | `-a` | string | ✅ | Agent code |
| `--workflow` | `-w` | string | ✅ | Workflow code |
| `--variable` | `-v` | string | ❌ | Variable code（默认使用 agent defaults） |
| `--env` | `-e` | string | ❌ | Env code（默认使用 agent defaults） |
| `--pmg` | `-p` | string | ❌ | PMG code（默认使用 agent defaults） |
| `--dry-run` | | bool | ❌ | 只预览，不保存 |

**示例**:

```bash
# 完整配置
zima pjob create \
  --name "每日代码审查" \
  --code daily-code-review \
  --agent test-agent \
  --workflow code-review-workflow \
  --variable v1g \
  --env env3 \
  --pmg kimi-default-pmg

# 使用 agent 默认值
zima pjob create \
  --code quick-review \
  --agent test-agent \
  --workflow code-review-workflow

# 只预览不保存
zima pjob create \
  --code test-job \
  --agent test-agent \
  --workflow code-review-workflow \
  --dry-run
```

### 8.2 更新 PJob

```bash
zima pjob update <code> [OPTIONS]
```

**选项**:

所有创建时的选项都可以更新，外加：

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--unset-variable` | | bool | 移除 variable 配置 |
| `--unset-env` | | bool | 移除 env 配置 |
| `--unset-pmg` | | bool | 移除 pmg 配置 |

**示例**:

```bash
zima pjob update daily-code-review \
  --variable new-vars \
  --env prod-env
```

### 8.3 删除 PJob

```bash
zima pjob delete <code> [OPTIONS]
```

### 8.4 列出 PJobs

```bash
zima pjob list [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--agent` | `-a` | string | 按 Agent 筛选 |
| `--workflow` | `-w` | string | 按 Workflow 筛选 |
| `--format` | | string | 输出格式 |
| `--all` | | bool | 显示完整配置 |

### 8.5 查看 PJob

```bash
zima pjob show <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--format` | | string | 输出格式 |
| `--render` | `-r` | bool | 渲染完整的执行命令 |

**示例**:

```bash
zima pjob show daily-code-review
zima pjob show daily-code-review --render
```

### 8.6 执行 PJob

```bash
zima pjob run <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--timeout` | `-t` | int | 超时时间（秒） |
| `--detach` | `-d` | bool | 后台运行 |
| `--log-file` | `-l` | path | 日志文件路径 |
| `--env-override` | `-e` | key=value | 临时覆盖环境变量 |
| `--param-override` | `-p` | key=value | 临时覆盖参数 |
| `--interactive` | `-i` | bool | 交互模式（覆盖 --print） |

**示例**:

```bash
# 普通执行
zima pjob run daily-code-review

# 带超时
zima pjob run daily-code-review --timeout 600

# 后台运行
zima pjob run daily-code-review --detach --log-file ./logs/run.log

# 临时覆盖环境变量
zima pjob run daily-code-review \
  --env-override "DEBUG=true" \
  --env-override "KIMI_MODEL=kimi-k2-072515-preview"
```

### 8.7 预览 PJob 命令

只生成命令，不实际执行。

```bash
zima pjob preview <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--with-env` | `-e` | bool | 显示环境变量设置 |
| `--export-script` | `-o` | path | 导出为可执行脚本 |

**示例**:

```bash
zima pjob preview daily-code-review
# 输出:
# 环境变量:
#   KIMI_API_KEY=***
#   KIMI_MODEL=kimi-k2-072515-preview
#
# 执行命令:
#   kimi --print --yolo \
#     --prompt /tmp/prompt_xxx.md \
#     --work-dir ./workspace \
#     --max-steps-per-turn 50

zima pjob preview daily-code-review --export-script ./run.sh
```

### 8.8 查看 PJob 日志

```bash
zima pjob logs <code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--follow` | `-f` | bool | 实时跟踪 |
| `--lines` | `-n` | int | 显示行数 |
| `--since` | | string | 从指定时间开始 |

### 8.9 检查 PJob 状态

```bash
zima pjob status <code>
```

**输出示例**:

```
PJob: daily-code-review
Status: completed
Last Run: 2026-03-25 14:30:00
Duration: 45.3s
Exit Code: 0
```

### 8.10 克隆 PJob

```bash
zima pjob clone <source-code> <new-code> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--name` | `-n` | string | 新名称 |

**示例**:

```bash
zima pjob clone daily-code-review weekly-code-review \
  --name "每周代码审查"
```

---

## 9. 系统命令

### 9.1 初始化 Zima

```bash
zima init [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--force` | `-f` | bool | 强制重新初始化 |
| `--config-dir` | `-c` | path | 指定配置目录 |

**示例**:

```bash
zima init
zima init --config-dir ~/.config/zima
```

### 9.2 诊断检查

```bash
zima doctor [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--fix` | `-f` | bool | 自动修复问题 |

**示例**:

```bash
zima doctor
# 输出:
# ✓ Config directory exists
# ✓ Agent configs valid
# ✓ kimi CLI found in PATH
# ✓ claude CLI found in PATH
# ⚠ No default agent configured
```

### 9.3 版本信息

```bash
zima version [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--check-update` | | bool | 检查更新 |

### 9.4 查看配置目录

```bash
zima config path
```

### 9.5 导出配置

```bash
zima config export [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--output` | `-o` | path | 输出文件 |
| `--format` | `-f` | string | 格式 (zip/tar) |

### 9.6 导入配置

```bash
zima config import <path> [OPTIONS]
```

**选项**:

| 选项 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--merge` | `-m` | bool | 合并而非覆盖 |

---

## 附录：命令速查表

### Agent

```bash
zima agent create -n <name> -c <code> -t <type>
zima agent update <code> [--name ...] [--set-param ...]
zima agent delete <code>
zima agent list [--type ...]
zima agent show <code>
zima agent edit <code>
```

### Workflow

```bash
zima workflow create -n <name> -c <code>
zima workflow update <code>
zima workflow delete <code>
zima workflow list
zima workflow show <code>
zima workflow render <code> -v <variable>
```

### Variable

```bash
zima variable create -n <name> -c <code>
zima variable update <code> --set key=value
zima variable delete <code>
zima variable list
zima variable show <code>
```

### Env

```bash
zima env create -n <name> -c <code>
zima env update <code> --set KEY=VALUE
zima env delete <code>
zima env list
zima env show <code>
zima env verify-secrets <code>
```

### PMG

```bash
zima pmg create -n <name> -c <code>
zima pmg update <code> --add-param '{...}'
zima pmg delete <code>
zima pmg list
zima pmg show <code>
zima pmg preview <code>
```

### PJob

```bash
zima pjob create -c <code> -a <agent> -w <workflow> [-v ...] [-e ...] [-p ...]
zima pjob update <code>
zima pjob delete <code>
zima pjob list
zima pjob show <code> --render
zima pjob run <code> [--timeout ...] [--detach]
zima pjob preview <code>
zima pjob logs <code> [-f]
```

---

> "配置是意图的表达，执行是意图的实现。" —— Zima Blue

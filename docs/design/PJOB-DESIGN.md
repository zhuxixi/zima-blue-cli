# PJob (Parameterized Job) 设计文档

> PJob 是 Zima Blue 的执行层，将 Agent、Workflow、Variable、Env、PMG 五组配置串联成可执行的任务。

---

## 📋 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [Schema 定义](#3-schema-定义)
4. [执行流程](#4-执行流程)
5. [配置组合优先级](#5-配置组合优先级)
6. [CLI 命令设计](#6-cli-命令设计)
7. [使用示例](#7-使用示例)
8. [测试方案](#8-测试方案)
9. [实现阶段](#9-实现阶段)

---

## 1. 概述

### 1.1 什么是 PJob

PJob（Plain Job，一般任务）是 **任务的执行单元**，它：

- 引用 **5 组配置**：Agent、Workflow、Variable、Env、PMG
- 将 Workflow 模板渲染为最终 Prompt
- 解析 Env 中的 Secrets
- 组合 PMG 构建命令行参数
- 生成并执行完整的 Agent 命令

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **配置即任务** | PJob 本身只存储配置引用，不存储实际内容 |
| **可重复执行** | 相同的 PJob 可以多次运行，结果可复现 |
| **配置覆盖** | PJob 中显式指定的配置优先级高于 Agent defaults |
| **环境隔离** | 每次执行独立解析 Secrets，不持久化敏感信息 |
| **执行追踪** | 记录执行历史，支持查看日志和重试 |

### 1.3 文件位置

```
~/.zima/configs/pjobs/{code}.yaml
```

---

## 2. 核心概念

### 2.1 PJob 与五组配置的关系

```
┌─────────────────────────────────────────────────────────────┐
│                        PJob (任务)                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────┐  ┌─────────┐ │
│  │  Agent  │  │ Workflow│  │ Variable│  │ Env │  │   PMG   │ │
│  │ (执行器) │  │ (模板)  │  │ (变量值) │  │(环境)│  │ (参数)  │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └──┬──┘  └────┬────┘ │
│       │            │            │          │          │      │
│       └────────────┴────────────┴──────────┴──────────┘      │
│                              ↓                               │
│                    ┌──────────────────┐                      │
│                    │   渲染 & 执行     │                      │
│                    │                  │                      │
│                    │ 1. Render Prompt │                      │
│                    │ 2. Resolve Env   │                      │
│                    │ 3. Build Params  │                      │
│                    │ 4. Execute       │                      │
│                    └────────┬─────────┘                      │
│                             ↓                                │
│                    ┌──────────────────┐                      │
│                    │  Agent Command   │                      │
│                    │  (kimi/claude)   │                      │
│                    └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 PJob 执行流程

```
启动 PJob
    │
    ▼
加载 PJob 配置
    ├─ agent: kimi-code-assistant
    ├─ workflow: code-review
    ├─ variable: python-project-vars
    ├─ env: kimi-prod-env
    └─ pmg: verbose-pmg
    │
    ▼
解析配置引用
    ├─ 加载 Agent 配置 → 确定 CLI 工具 (kimi/claude/gemini)
    ├─ 加载 Workflow 模板
    ├─ 加载 Variable 值
    ├─ 加载 Env 配置 → 解析 Secrets
    └─ 加载 PMG 配置 → 构建参数
    │
    ▼
渲染 Prompt
    ├─ Workflow 模板 + Variable 值
    └─ 生成最终 Prompt 文件 (/tmp/pjob-{id}.md)
    │
    ▼
构建命令
    ├─ Agent 基础命令
    ├─ PMG 参数 (--model, --yolo, etc.)
    ├─ Prompt 文件路径 (--prompt /tmp/...)
    └─ 工作目录 (--work-dir)
    │
    ▼
设置环境
    ├─ 解析 Env Secrets
    ├─ 注入环境变量
    └─ 确认工作目录存在
    │
    ▼
执行命令
    ├─ 启动子进程
    ├─ 实时输出到控制台
    └─ 捕获退出码
    │
    ▼
清理与记录
    ├─ 删除临时 Prompt 文件
    ├─ 记录执行历史
    └─ 返回执行结果
```

### 2.3 临时文件管理

```
/tmp/
└── zima-pjobs/
    ├── pjob-{pjob-code}-{uuid}/
    │   ├── prompt.md          # 渲染后的 Prompt
    │   ├── env.sh             # 导出的环境变量脚本
    │   └── output.log         # 执行日志（可选）
    └── ...
```

执行完成后自动清理临时文件。

---

## 3. Schema 定义

### 3.1 完整结构

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: daily-code-review        # 唯一编码
  name: 每日代码审查             # 显示名称
  description: 每天早上自动审查昨日提交
  labels:                        # 标签（用于过滤和分组）
    - automation
    - code-review
    - daily
  annotations:                   # 额外元数据
    cron: "0 9 * * *"           # 计划执行时间（可选）
createdAt: "2026-03-26T10:00:00Z"
updatedAt: "2026-03-26T10:00:00Z"
spec:
  # 核心配置引用（必填）
  agent: kimi-code-assistant     # Agent code
  workflow: code-review          # Workflow code
  
  # 可选配置引用（未指定时使用 Agent defaults）
  variable: python-project-vars  # Variable code
  env: kimi-prod-env            # Env code
  pmg: verbose-pmg              # PMG code
  
  # 运行时覆盖（可选，优先级最高）
  overrides:
    # 覆盖 Agent 参数
    agentParams:
      model: "kimi-k2-072515-preview"
      yolo: true
    
    # 覆盖 Variable 值
    variableValues:
      task:
        name: "紧急代码审查"
        priority: "high"
    
    # 覆盖 Env 变量
    envVars:
      DEBUG: "true"
    
    # 覆盖 PMG 参数
    pmgParams:
      - name: verbose
        type: flag
        enabled: true
  
  # 执行选项
  execution:
    # 工作目录（默认使用 Agent 配置或当前目录）
    workDir: "./workspace"
    
    # 超时时间（秒）
    timeout: 600
    
    # 是否保留临时文件（用于调试）
    keepTemp: false
    
    # 失败重试次数
    retries: 0
    
    # 是否异步执行
    async: false
  
  # 前置/后置钩子
  hooks:
    # 执行前运行的命令
    preExec:
      - "git pull origin main"
      - "echo 'Starting code review...'"
    
    # 执行后运行的命令
    postExec:
      - "echo 'Code review completed'"
  
  # 输出处理
  output:
    # 保存输出到文件
    saveTo: "./reports/code-review-{{ date }}.md"
    
    # 是否追加模式
    append: false
    
    # 输出格式处理
    format: "raw"  # raw | json | extract-code-blocks
```

### 3.2 字段详解

#### metadata

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 唯一编码 |
| `name` | string | ✅ | 显示名称 |
| `description` | string | ❌ | 描述说明 |
| `labels` | array | ❌ | 标签列表，用于分类 |
| `annotations` | object | ❌ | 额外元数据（键值对） |

#### spec.agent（必填）

引用 Agent 配置的 code。

#### spec.workflow（必填）

引用 Workflow 配置的 code。

#### spec.variable（可选）

引用 Variable 配置的 code。未指定时：
1. 使用 Agent 的 `defaults.variable`
2. 如果都没有，使用空值渲染模板

#### spec.env（可选）

引用 Env 配置的 code。未指定时：
1. 使用 Agent 的 `defaults.env`
2. 如果都没有，使用当前环境变量

#### spec.pmg（可选）

引用 PMG 配置的 code。未指定时：
1. 使用 Agent 的 `defaults.pmg`
2. 如果都没有，使用 Agent 的基础参数

#### spec.overrides

运行时覆盖配置，优先级最高。

| 字段 | 说明 |
|------|------|
| `agentParams` | 覆盖 Agent 的 parameters |
| `variableValues` | 覆盖 Variable 的 values |
| `envVars` | 额外环境变量（覆盖 Env 中的同名变量） |
| `pmgParams` | 额外 PMG 参数（追加到 PMG 参数列表） |

#### spec.execution

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `workDir` | string | Agent 配置或当前目录 | 工作目录 |
| `timeout` | integer | 600 | 超时时间（秒） |
| `keepTemp` | boolean | false | 保留临时文件 |
| `retries` | integer | 0 | 失败重试次数 |
| `async` | boolean | false | 异步执行 |

#### spec.hooks

前置/后置钩子命令列表，按顺序执行。

#### spec.output

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `saveTo` | string | - | 输出保存路径（支持模板变量） |
| `append` | boolean | false | 追加模式 |
| `format` | string | raw | 输出格式处理 |

---

## 4. 执行流程

### 4.1 详细执行步骤

```python
class PJobExecutor:
    """PJob 执行器"""
    
    def execute(self, pjob_code: str, dry_run: bool = False) -> ExecutionResult:
        # 1. 加载 PJob 配置
        pjob = self.load_pjob(pjob_code)
        
        # 2. 加载并合并所有引用配置
        config_bundle = self.resolve_config_bundle(pjob)
        
        # 3. 应用 overrides
        config_bundle.apply_overrides(pjob.spec.overrides)
        
        # 4. 创建临时目录
        temp_dir = self.create_temp_dir(pjob_code)
        
        # 5. 渲染 Workflow 模板
        prompt_content = self.render_workflow(
            config_bundle.workflow,
            config_bundle.variable
        )
        prompt_file = temp_dir / "prompt.md"
        prompt_file.write_text(prompt_content)
        
        # 6. 解析 Env Secrets
        env_vars = self.resolve_env(config_bundle.env)
        env_vars.update(config_bundle.overrides.env_vars)
        
        # 7. 构建命令行参数
        params = config_bundle.pmg.build_params()
        
        # 8. 构建完整命令
        command = self.build_command(
            agent=config_bundle.agent,
            prompt_file=prompt_file,
            work_dir=config_bundle.execution.work_dir,
            params=params
        )
        
        # 9. 如果是 dry-run，只返回命令
        if dry_run:
            return ExecutionResult(
                command=command,
                env=env_vars,
                dry_run=True
            )
        
        # 10. 执行前置钩子
        self.run_hooks(pjob.spec.hooks.pre_exec, env_vars)
        
        # 11. 执行主命令
        result = self.run_command(
            command=command,
            env=env_vars,
            work_dir=config_bundle.execution.work_dir,
            timeout=config_bundle.execution.timeout
        )
        
        # 12. 执行后置钩子
        self.run_hooks(pjob.spec.hooks.post_exec, env_vars)
        
        # 13. 处理输出
        if pjob.spec.output.save_to:
            self.save_output(result.output, pjob.spec.output)
        
        # 14. 清理临时文件
        if not pjob.spec.execution.keep_temp:
            self.cleanup_temp_dir(temp_dir)
        
        # 15. 记录执行历史
        self.record_execution(pjob_code, result)
        
        return result
```

### 4.2 命令构建示例

**输入配置：**

```yaml
# PJob
spec:
  agent: kimi-assistant
  workflow: code-review
  variable: project-vars
  env: prod-env
  pmg: default-pmg
```

**生成的命令：**

```bash
# Kimi Agent
ZIMA_ENV_VAR1=value1 \
ZIMA_ENV_VAR2=value2 \
kimi \
  --print \
  --model kimi-k2-072515-preview \
  --yolo \
  --max-steps-per-turn 50 \
  --work-dir ./workspace \
  --prompt /tmp/zima-pjobs/pjob-daily-code-review-abc123/prompt.md
```

### 4.3 后台执行设计

PJob 支持后台执行模式，适用于长时间运行的任务。

#### 后台执行原理

```
用户: zima pjob run <pjob-code> --background
    ↓
CLI: 生成 execution_id 和日志路径
    ↓
CLI: 启动 detached 子进程
    ├─ Windows: creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    └─ Unix: start_new_session=True
    ↓
子进程: 执行 PJob (background_runner.py)
    ↓
子进程: 输出写入日志文件
    ↓
子进程: 完成后更新执行历史
    ↓
CLI: 立即返回，显示 PID 和日志路径
```

#### 后台执行特点

| 特性 | 说明 |
|------|------|
| **进程独立** | 后台进程有自己的进程组，不受终端影响 |
| **日志持久** | 输出写入 `~/.zima/logs/background/<pjob>-<id>.log` |
| **历史记录** | 完成后自动更新 `zima pjob history` |
| **Ctrl+C 安全** | 终端关闭不会影响后台进程 |

#### 日志跟踪 (--follow)

使用 `--background --follow` 可以后台运行并实时跟踪日志：

```bash
# 后台运行并实时跟踪日志
zima pjob run daily-review --background --follow

# 按 Ctrl+C 停止跟踪（进程继续运行）
⚠ Stopped following log output.
   ✓ Background process (PID: 12345) is still running.
```

跟踪模式特点：
- 实时显示日志输出（类似 `tail -f`）
- 按 Ctrl+C 只停止跟踪，不停止后台进程
- 可随时重新查看日志：`Get-Content <log-path> -Tail 100`

---

## 5. 配置组合优先级

### 5.1 优先级从高到低

```
┌─────────────────────────────────────────────────────────┐
│ 1. PJob.spec.overrides（最高优先级）                      │
│    ├─ agentParams                                       │
│    ├─ variableValues                                    │
│    ├─ envVars                                           │
│    └─ pmgParams                                         │
├─────────────────────────────────────────────────────────┤
│ 2. PJob.spec 中显式指定的配置引用                         │
│    ├─ variable                                          │
│    ├─ env                                               │
│    └─ pmg                                               │
├─────────────────────────────────────────────────────────┤
│ 3. Agent.spec.defaults                                  │
│    ├─ workflow                                          │
│    ├─ variable                                          │
│    ├─ env                                               │
│    └─ pmg                                               │
├─────────────────────────────────────────────────────────┤
│ 4. 系统默认值（最低优先级）                               │
│    └─ 工作目录 = 当前目录                                │
└─────────────────────────────────────────────────────────┘
```

### 5.2 配置组合示例

**Agent 配置：**

```yaml
spec:
  defaults:
    workflow: default-workflow
    variable: default-vars
    env: default-env
    pmg: default-pmg
```

**PJob 配置：**

```yaml
spec:
  agent: my-agent
  workflow: code-review          # 覆盖 Agent default.workflow
  # variable: 未指定，使用 Agent default.variable
  env: prod-env                  # 覆盖 Agent default.env
  # pmg: 未指定，使用 Agent default.pmg
  overrides:
    envVars:
      DEBUG: "true"             # 覆盖 prod-env 中的 DEBUG
```

**最终使用的配置：**

| 配置 | 来源 |
|------|------|
| workflow | `code-review` (PJob 显式指定) |
| variable | `default-vars` (Agent default) |
| env | `prod-env` (PJob 显式指定) + `DEBUG=true` (override) |
| pmg | `default-pmg` (Agent default) |

---

## 6. CLI 命令设计

### 6.1 命令结构

```
zima pjob [command] [options]
```

### 6.2 完整命令列表

#### pjob create - 创建 PJob

```bash
# 基础用法
zima pjob create \
  --agent kimi-assistant \
  --workflow code-review \
  --name "代码审查任务" \
  --code daily-review

# 完整用法
zima pjob create \
  --agent kimi-assistant \
  --workflow code-review \
  --variable python-vars \
  --env prod-env \
  --pmg verbose-pmg \
  --name "代码审查任务" \
  --code daily-review \
  --description "每日自动代码审查" \
  --label automation \
  --label daily \
  --work-dir ./workspace \
  --timeout 600 \
  --output ./reports/review-{{date}}.md

# 从现有 PJob 复制
zima pjob create \
  --from existing-pjob \
  --name "新任务" \
  --code new-pjob \
  --env staging-env
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--agent` | `-a` | Agent code（必填） |
| `--workflow` | `-w` | Workflow code（必填） |
| `--variable` | `-v` | Variable code |
| `--env` | `-e` | Env code |
| `--pmg` | `-p` | PMG code |
| `--name` | `-n` | PJob 名称（必填） |
| `--code` | `-c` | PJob code（必填） |
| `--description` | `-d` | 描述 |
| `--label` | `-l` | 标签（可多次使用） |
| `--work-dir` | | 工作目录 |
| `--timeout` | `-t` | 超时时间 |
| `--output` | `-o` | 输出保存路径 |
| `--from` | | 从现有 PJob 复制 |

#### pjob list - 列出 PJob

```bash
# 列出所有
zima pjob list

# 按标签过滤
zima pjob list --label automation
zima pjob list --label daily --label code-review

# 按 Agent 类型过滤
zima pjob list --agent-type kimi

# 详细格式
zima pjob list --format table

# JSON 格式
zima pjob list --format json
```

#### pjob show - 查看详情

```bash
# 查看配置
zima pjob show daily-review

# 查看执行历史
zima pjob show daily-review --history

# 查看最近 5 次执行
zima pjob show daily-review --history --limit 5

# JSON 格式
zima pjob show daily-review --format json
```

#### pjob update - 更新配置

```bash
# 更新引用配置
zima pjob update daily-review --env staging-env
zima pjob update daily-review --pmg quiet-pmg

# 添加/删除标签
zima pjob update daily-review --add-label urgent
zima pjob update daily-review --remove-label daily

# 更新执行选项
zima pjob update daily-review --timeout 1200 --retries 2

# 更新输出路径
zima pjob update daily-review --output ./new-reports/review.md

# 编辑完整配置
zima pjob update daily-review --edit
```

#### pjob delete - 删除

```bash
# 删除（需确认）
zima pjob delete daily-review

# 强制删除
zima pjob delete daily-review --force

# 批量删除
zima pjob delete --label obsolete --force
```

#### pjob run - 执行任务

```bash
# 执行任务
zima pjob run daily-review

# 试运行（只显示命令，不执行）
zima pjob run daily-review --dry-run

# 覆盖变量值
zima pjob run daily-review --set-var "task.name=紧急审查"
zima pjob run daily-review --set-var "task.priority=high"

# 覆盖环境变量
zima pjob run daily-review --set-env "DEBUG=true"

# 覆盖 Agent 参数
zima pjob run daily-review --set-param "model=kimi-k1.5"

# 后台执行（detached 进程，立即返回）
zima pjob run daily-review --background
zima pjob run daily-review -b

# 后台执行并实时跟踪日志
zima pjob run daily-review --background --follow
zima pjob run daily-review -b -f

# 保留临时文件（调试）
zima pjob run daily-review --keep-temp

# 指定工作目录
zima pjob run daily-review --work-dir /path/to/project
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--dry-run` | | 只显示命令，不执行 |
| `--set-var` | | 覆盖变量值（key=value） |
| `--set-env` | | 覆盖环境变量（key=value） |
| `--set-param` | | 覆盖 Agent 参数（key=value） |
| `--work-dir` | | 临时指定工作目录 |
| `--background` | `-b` | 后台执行（detached 进程） |
| `--follow` | `-f` | 跟踪日志输出（需配合 `--background`） |
| `--keep-temp` | | 保留临时文件 |
| `--timeout` | `-t` | 临时指定超时 |

#### pjob render - 渲染模板

```bash
# 渲染 Workflow 模板
zima pjob render daily-review

# 保存到文件
zima pjob render daily-review --output rendered-prompt.md

# 查看渲染后的环境变量
zima pjob render daily-review --show-env

# 查看完整执行命令
zima pjob render daily-review --show-command
```

#### pjob history - 执行历史

```bash
# 查看执行历史
zima pjob history daily-review

# 最近 10 次
zima pjob history daily-review --limit 10

# 只看失败的
zima pjob history daily-review --status failed

# 查看某次执行的详情
zima pjob history daily-review --id 5

# 清理历史记录
zima pjob history daily-review --clear
```

#### pjob validate - 验证配置

```bash
# 验证 PJob 配置
zima pjob validate daily-review

# 验证所有引用的配置是否存在
zima pjob validate daily-review --strict

# 验证模板渲染
zima pjob validate daily-review --check-render
```

#### pjob copy - 复制

```bash
# 复制 PJob
zima pjob copy daily-review weekly-review --name "每周审查"

# 复制并修改配置
zima pjob copy daily-review staging-review \
  --name "Staging 审查" \
  --env staging-env \
  --add-label staging
```

#### pjob export/import - 导入导出

```bash
# 导出为 YAML
zima pjob export daily-review --output daily-review.yaml

# 导出为 Shell 脚本
zima pjob export daily-review --format shell --output run-review.sh

# 导入
zima pjob import daily-review.yaml
```

---

## 7. 使用示例

### 7.1 日常代码审查

```bash
# 1. 创建 Agent
zima agent create \
  --name "Kimi 代码助手" \
  --code kimi-assistant \
  --type kimi \
  --set-param model=kimi-k2-072515-preview \
  --set-param yolo=true

# 2. 创建 Workflow
zima workflow create \
  --name "代码审查" \
  --code code-review \
  --from-file ./workflows/code-review.md

# 3. 创建 Variable
zima variable create \
  --name "Python 项目变量" \
  --code python-vars \
  --for-workflow code-review \
  --from-file ./vars/python-project.yaml

# 4. 创建 Env
zima env create \
  --name "生产环境" \
  --code prod-env \
  --for-type kimi \
  --set-var KIMI_API_KEY="${KIMI_API_KEY}"

# 5. 创建 PMG
zima pmg create \
  --name "默认参数" \
  --code default-pmg \
  --for-type kimi \
  --add-param max-steps-per-turn long 50 \
  --add-param y short true

# 6. 创建 PJob
zima pjob create \
  --name "每日代码审查" \
  --code daily-review \
  --agent kimi-assistant \
  --workflow code-review \
  --variable python-vars \
  --env prod-env \
  --pmg default-pmg \
  --work-dir ./my-project \
  --output ./reports/code-review-{{date}}.md \
  --label automation \
  --label daily

# 7. 运行
zima pjob run daily-review

# 8. 查看结果
zima pjob history daily-review
cat ./reports/code-review-$(date +%Y-%m-%d).md
```

### 7.2 多环境配置

```bash
# 创建相同任务的不同环境版本
zima pjob copy daily-review staging-review \
  --name "Staging 代码审查" \
  --env staging-env \
  --variable staging-vars \
  --add-label staging

zima pjob copy daily-review dev-review \
  --name "Dev 代码审查" \
  --env dev-env \
  --variable dev-vars \
  --add-label dev
```

### 7.3 CI/CD 集成

```bash
# 在 CI 中运行
zima pjob run daily-review \
  --set-var "task.name=CI 代码审查" \
  --set-env "CI=true" \
  --work-dir $CI_PROJECT_DIR \
  --output $CI_PROJECT_DIR/reports/review.md
```

### 7.4 调试和开发

```bash
# 试运行查看命令
zima pjob run daily-review --dry-run

# 渲染模板查看内容
zima pjob render daily-review --output /tmp/prompt.md
cat /tmp/prompt.md

# 保留临时文件调试
zima pjob run daily-review --keep-temp
ls /tmp/zima-pjobs/pjob-daily-review-*/
```

---

## 8. 测试方案

### 8.1 测试策略概览

PJob 的测试分为以下几个层次：

| 层次 | 说明 | 测试数量目标 |
|------|------|-------------|
| **单元测试** | 模型方法、配置解析、命令构建 | 40+ |
| **集成测试** | 完整执行流程、配置组合 | 30+ |
| **Mock 测试** | Agent 命令执行、环境变量注入 | 20+ |
| **E2E 测试** | CLI 命令端到端 | 15+ |

### 8.2 单元测试

#### PJobConfig 模型测试

```python
class TestPJobConfig:
    """PJobConfig 模型单元测试"""
    
    class TestCreate:
        """测试创建"""
        
        def test_create_minimal_pjob(self):
            """测试创建最简 PJob"""
            config = PJobConfig.create(
                code="test-pjob",
                name="Test PJob",
                agent="test-agent",
                workflow="test-workflow"
            )
            assert config.metadata.code == "test-pjob"
            assert config.spec.agent == "test-agent"
            assert config.spec.workflow == "test-workflow"
        
        def test_create_full_pjob(self):
            """测试创建完整 PJob"""
            config = PJobConfig.create(
                code="full-pjob",
                name="Full PJob",
                agent="agent1",
                workflow="workflow1",
                variable="var1",
                env="env1",
                pmg="pmg1",
                labels=["test", "automation"],
                execution={"timeout": 300, "retries": 2}
            )
            assert config.spec.variable == "var1"
            assert "test" in config.metadata.labels
            assert config.spec.execution.timeout == 300
        
        def test_create_with_overrides(self):
            """测试创建带 overrides 的 PJob"""
            config = PJobConfig.create(
                code="override-pjob",
                name="Override PJob",
                agent="agent1",
                workflow="workflow1",
                overrides={
                    "agentParams": {"model": "custom-model"},
                    "envVars": {"DEBUG": "true"}
                }
            )
            assert config.spec.overrides.agent_params["model"] == "custom-model"
    
    class TestValidation:
        """测试验证"""
        
        def test_validate_missing_required_fields(self):
            """测试缺少必填字段"""
            config = PJobConfig(metadata=Metadata(code="test"))
            errors = config.validate()
            assert any("agent is required" in e for e in errors)
            assert any("workflow is required" in e for e in errors)
        
        def test_validate_nonexistent_references(self):
            """测试引用不存在的配置"""
            config = PJobConfig.create(
                code="test",
                name="Test",
                agent="nonexistent-agent",
                workflow="nonexistent-workflow"
            )
            errors = config.validate(resolve_refs=True)
            assert any("agent not found" in e for e in errors)
    
    class TestConfigResolution:
        """测试配置解析"""
        
        def test_resolve_config_bundle(self):
            """测试解析配置组合"""
            # 创建测试配置
            create_test_agent("test-agent", defaults={
                "variable": "default-var",
                "env": "default-env"
            })
            create_test_workflow("test-workflow")
            create_test_variable("custom-var")
            
            pjob = PJobConfig.create(
                code="test",
                name="Test",
                agent="test-agent",
                workflow="test-workflow",
                variable="custom-var"  # 覆盖 default
            )
            
            bundle = pjob.resolve_config_bundle()
            assert bundle.agent.code == "test-agent"
            assert bundle.workflow.code == "test-workflow"
            assert bundle.variable.code == "custom-var"  # PJob 指定优先
            assert bundle.env.code == "default-env"  # 使用 Agent default
```

#### PJobExecutor 测试

```python
class TestPJobExecutor:
    """PJob 执行器单元测试"""
    
    class TestCommandBuilding:
        """测试命令构建"""
        
        def test_build_kimi_command(self):
            """测试构建 Kimi 命令"""
            agent = create_test_agent("kimi-agent", type="kimi")
            pmg = create_test_pmg("test-pmg", for_types=["kimi"])
            
            executor = PJobExecutor()
            command = executor.build_command(
                agent=agent,
                prompt_file=Path("/tmp/prompt.md"),
                work_dir="./workspace",
                params=["--model", "kimi-k2", "--yolo"]
            )
            
            assert "kimi" in command
            assert "--print" in command
            assert "--prompt" in command
            assert "/tmp/prompt.md" in command
            assert "--work-dir" in command
            assert "./workspace" in command
            assert "--model" in command
            assert "--yolo" in command
        
        def test_build_claude_command(self):
            """测试构建 Claude 命令"""
            agent = create_test_agent("claude-agent", type="claude")
            
            executor = PJobExecutor()
            command = executor.build_command(
                agent=agent,
                prompt_file=Path("/tmp/prompt.md"),
                work_dir="./workspace",
                params=[]
            )
            
            assert "claude" in command
            assert "--print" in command
            assert "-p" in command  # Claude 使用短格式
    
    class TestEnvResolution:
        """测试环境变量解析"""
        
        def test_resolve_env_with_secrets(self, monkeypatch):
            """测试解析带 Secrets 的环境变量"""
            monkeypatch.setenv("TEST_API_KEY", "secret123")
            
            env = EnvConfig.create(
                code="test-env",
                name="Test Env",
                for_type="kimi",
                secrets=[{
                    "name": "API_KEY",
                    "source": "env",
                    "key": "TEST_API_KEY"
                }]
            )
            
            executor = PJobExecutor()
            env_vars = executor.resolve_env(env)
            
            assert env_vars["API_KEY"] == "secret123"
        
        def test_resolve_env_with_overrides(self):
            """测试环境变量被 overrides 覆盖"""
            env = EnvConfig.create(
                code="test-env",
                name="Test Env",
                for_type="kimi",
                variables={"DEBUG": "false", "LOG_LEVEL": "info"}
            )
            
            executor = PJobExecutor()
            env_vars = executor.resolve_env(env)
            env_vars.update({"DEBUG": "true"})  # 模拟 override
            
            assert env_vars["DEBUG"] == "true"
            assert env_vars["LOG_LEVEL"] == "info"
```

### 8.3 集成测试

#### PJob 完整生命周期测试

```python
class TestPJobLifecycle:
    """PJob 完整生命周期集成测试"""
    
    def test_full_lifecycle(self):
        """完整生命周期测试"""
        # Step 1: 创建依赖配置
        create_test_agent("lifecycle-agent")
        create_test_workflow("lifecycle-workflow")
        create_test_variable("lifecycle-var")
        create_test_env("lifecycle-env")
        create_test_pmg("lifecycle-pmg")
        
        # Step 2: 创建 PJob
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Lifecycle Test",
            "--code", "lifecycle-pjob",
            "--agent", "lifecycle-agent",
            "--workflow", "lifecycle-workflow",
            "--variable", "lifecycle-var",
            "--env", "lifecycle-env",
            "--pmg", "lifecycle-pmg"
        ])
        assert result.exit_code == 0
        
        # Step 3: 验证创建
        result = runner.invoke(app, ["pjob", "show", "lifecycle-pjob"])
        assert "Lifecycle Test" in result.output
        
        # Step 4: 试运行
        result = runner.invoke(app, ["pjob", "run", "lifecycle-pjob", "--dry-run"])
        assert result.exit_code == 0
        assert "kimi" in result.output  # 命令中包含 kimi
        
        # Step 5: 渲染模板
        result = runner.invoke(app, ["pjob", "render", "lifecycle-pjob"])
        assert result.exit_code == 0
        
        # Step 6: 更新
        result = runner.invoke(app, [
            "pjob", "update", "lifecycle-pjob",
            "--timeout", "1200"
        ])
        assert result.exit_code == 0
        
        # Step 7: 复制
        result = runner.invoke(app, [
            "pjob", "copy", "lifecycle-pjob", "copied-pjob",
            "--name", "Copied PJob"
        ])
        assert result.exit_code == 0
        
        # Step 8: 删除
        result = runner.invoke(app, ["pjob", "delete", "copied-pjob", "--force"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["pjob", "delete", "lifecycle-pjob", "--force"])
        assert result.exit_code == 0
```

#### 配置组合优先级测试

```python
class TestConfigResolutionPriority:
    """配置组合优先级集成测试"""
    
    def test_pjob_override_takes_priority(self):
        """测试 PJob 显式指定优先于 Agent default"""
        # 创建 Agent 带 defaults
        create_test_agent("priority-agent", defaults={
            "variable": "default-var",
            "env": "default-env"
        })
        
        # 创建额外的配置
        create_test_variable("default-var", values={"source": "default"})
        create_test_variable("custom-var", values={"source": "custom"})
        create_test_env("default-env", variables={"ENV": "default"})
        create_test_env("custom-env", variables={"ENV": "custom"})
        
        # 创建 PJob，显式指定 variable，不指定 env
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Priority Test",
            "--code", "priority-pjob",
            "--agent", "priority-agent",
            "--workflow", "test-workflow",
            "--variable", "custom-var"  # 覆盖 default
            # env 使用 default
        ])
        assert result.exit_code == 0
        
        # 验证配置解析
        result = runner.invoke(app, ["pjob", "render", "priority-pjob", "--show-config"])
        assert result.exit_code == 0
        # 验证使用了 custom-var 和 default-env
        assert "custom-var" in result.output
        assert "default-env" in result.output
    
    def test_overrides_highest_priority(self):
        """测试 overrides 具有最高优先级"""
        create_test_agent("override-agent")
        create_test_workflow("override-workflow")
        
        # 创建带 overrides 的 PJob
        pjob = PJobConfig.create(
            code="override-pjob",
            name="Override Test",
            agent="override-agent",
            workflow="override-workflow"
        )
        pjob.spec.overrides.agent_params = {"model": "overridden-model"}
        save_config(pjob)
        
        # 渲染并验证 overrides 生效
        result = runner.invoke(app, ["pjob", "render", "override-pjob", "--show-config"])
        assert "overridden-model" in result.output
```

#### 执行流程测试

```python
class TestPJobExecution:
    """PJob 执行流程集成测试"""
    
    @patch("zima.models.pjob.subprocess.run")
    def test_execute_with_mocked_agent(self, mock_run):
        """使用 Mock 测试 Agent 执行"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Success")
        
        # 创建完整配置
        create_test_agent("exec-agent", type="kimi")
        create_test_workflow("exec-workflow", template="# {{task.name}}")
        create_test_variable("exec-var", values={"task": {"name": "Test Task"}})
        create_test_env("exec-env", variables={"ENV": "test"})
        
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Execution Test",
            "--code", "exec-pjob",
            "--agent", "exec-agent",
            "--workflow", "exec-workflow",
            "--variable", "exec-var",
            "--env", "exec-env"
        ])
        assert result.exit_code == 0
        
        # 执行
        result = runner.invoke(app, ["pjob", "run", "exec-pjob"])
        assert result.exit_code == 0
        
        # 验证 subprocess.run 被调用
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "kimi" in call_args[0][0]
    
    def test_dry_run_outputs_command(self):
        """测试 dry-run 输出命令而不执行"""
        create_test_agent("dry-agent", type="kimi")
        create_test_workflow("dry-workflow")
        
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Dry Run Test",
            "--code", "dry-pjob",
            "--agent", "dry-agent",
            "--workflow", "dry-workflow"
        ])
        assert result.exit_code == 0
        
        # 试运行
        result = runner.invoke(app, ["pjob", "run", "dry-pjob", "--dry-run"])
        assert result.exit_code == 0
        assert "kimi" in result.output
        assert "--print" in result.output
        assert "DRY RUN" in result.output
```

### 8.4 Mock 测试

```python
class TestPJobWithMocks:
    """使用 Mock 的 PJob 测试"""
    
    @patch("zima.models.pjob.PJobExecutor.run_command")
    @patch("zima.models.pjob.PJobExecutor.resolve_env")
    def test_env_injection(self, mock_resolve_env, mock_run_command):
        """测试环境变量注入"""
        mock_resolve_env.return_value = {"API_KEY": "secret123", "DEBUG": "true"}
        mock_run_command.return_value = ExecutionResult(returncode=0, output="OK")
        
        executor = PJobExecutor()
        result = executor.execute("test-pjob")
        
        # 验证环境变量传递给 run_command
        call_kwargs = mock_run_command.call_args[1]
        assert call_kwargs["env"]["API_KEY"] == "secret123"
        assert call_kwargs["env"]["DEBUG"] == "true"
    
    @patch("zima.models.pjob.tempfile.mkdtemp")
    @patch("zima.models.pjob.shutil.rmtree")
    def test_temp_file_cleanup(self, mock_rmtree, mock_mkdtemp):
        """测试临时文件清理"""
        mock_mkdtemp.return_value = "/tmp/zima-test-123"
        
        executor = PJobExecutor()
        executor.execute("test-pjob")
        
        # 验证临时目录被创建和清理
        mock_mkdtemp.assert_called_once()
        mock_rmtree.assert_called_once_with("/tmp/zima-test-123")
    
    @patch("zima.models.pjob.PJobExecutor.run_hooks")
    def test_pre_post_hooks(self, mock_run_hooks):
        """测试前置/后置钩子"""
        executor = PJobExecutor()
        executor.execute("test-pjob-with-hooks")
        
        # 验证钩子被调用
        assert mock_run_hooks.call_count == 2
```

### 8.5 测试覆盖率目标

| 组件 | 目标覆盖率 |
|------|-----------|
| PJobConfig 模型 | 95% |
| PJobExecutor | 90% |
| 配置解析逻辑 | 90% |
| 命令构建 | 95% |
| CLI 命令 | 80% |

### 8.6 测试数据准备

```python
# tests/fixtures/pjobs.py

def create_test_pjob(
    code: str = "test-pjob",
    name: str = "Test PJob",
    agent: str = "test-agent",
    workflow: str = "test-workflow",
    variable: str = None,
    env: str = None,
    pmg: str = None,
    **kwargs
) -> PJobConfig:
    """创建测试 PJob"""
    
    # 自动创建依赖配置
    if not config_exists("agent", agent):
        create_test_agent(agent)
    if not config_exists("workflow", workflow):
        create_test_workflow(workflow)
    if variable and not config_exists("variable", variable):
        create_test_variable(variable)
    if env and not config_exists("env", env):
        create_test_env(env)
    if pmg and not config_exists("pmg", pmg):
        create_test_pmg(pmg)
    
    pjob = PJobConfig.create(
        code=code,
        name=name,
        agent=agent,
        workflow=workflow,
        variable=variable,
        env=env,
        pmg=pmg,
        **kwargs
    )
    
    save_config("pjob", code, pjob.to_dict())
    return pjob
```

---

## 9. 实现阶段

### Phase 1: 基础模型（预计 2-3 小时）

- [ ] 创建 `PJobConfig` 数据类
- [ ] 实现 `PJobMetadata`, `PJobSpec`, `ExecutionOptions`, `OutputOptions`
- [ ] 实现基础 CRUD 方法
- [ ] 编写单元测试（15-20 个）

### Phase 2: 配置解析（预计 2-3 小时）

- [ ] 实现 `ConfigBundle` 类
- [ ] 实现配置优先级解析逻辑
- [ ] 实现 `resolve_config_bundle()` 方法
- [ ] 编写集成测试（10-15 个）

### Phase 3: 执行引擎（预计 3-4 小时）

- [ ] 创建 `PJobExecutor` 类
- [ ] 实现模板渲染
- [ ] 实现环境变量解析
- [ ] 实现命令构建
- [ ] 实现子进程执行
- [ ] 编写集成测试（15-20 个）

### Phase 4: CLI 命令（预计 2-3 小时）

- [ ] 实现 `pjob create`, `list`, `show`, `update`, `delete`
- [ ] 实现 `pjob run`, `render`, `history`
- [ ] 实现 `pjob validate`, `copy`, `export`, `import`
- [ ] 编写 CLI 集成测试（10-15 个）

### Phase 5: 测试与完善（预计 2-3 小时）

- [ ] 完善边界情况测试
- [ ] 性能测试（执行速度）
- [ ] 错误处理优化
- [ ] 文档和示例

**预计总时间：11-16 小时**

**预计测试总数：60-80 个**

---

> "执行即力量，配置即智慧。" —— Zima Blue

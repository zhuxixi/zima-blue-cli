# Zima CLI 问题排查与修复清单

> 基于 coverage-agent 测试的完整问题记录

---

## 一、已确认修复的问题 ✅

### 1. PMGConfig.build_params 方法缺失
**状态**: 已修复 ✅
**问题**: `'PMGConfig' object has no attribute 'build_params'`
**文件**: `zima/models/pmg.py`
**修复**: 添加 `build_params()` 方法，将参数转换为命令行参数列表

---

## 二、待修复问题 🔧

### 问题 1: Windows 文件写入错误
**严重级别**: P0 (阻塞执行)
**错误信息**: `[Errno 22] Invalid argument`
**堆栈**:
```python
File "zima\execution\executor.py", line ~245, in _run_command
    sys.stderr.write(line)
OSError: [Errno 22] Invalid argument
```
**复现步骤**:
1. 创建任意 PJob
2. 执行 `zima pjob run <job-name>`
3. 等待 Agent 执行（约 5 分钟后）
4. 出现文件写入错误

**分析**:
- 发生在 `executor.py` 的 stderr 写入时
- 可能是 Windows 路径或编码问题
- 332 秒后才出现，说明是长时间运行后的资源问题

**建议修复**:
```python
# executor.py 中 stderr 写入添加异常处理
try:
    sys.stderr.write(line)
except OSError as e:
    logger.warning(f"Failed to write to stderr: {e}")
```

---

### 问题 2: PowerShell 命令分隔符不支持
**严重级别**: P1 (用户体验)
**问题**: Agent 生成的命令使用 `&&`，但 PowerShell 不支持
**错误**: `The token '&&' is not a valid statement separator in this version`

**复现步骤**:
1. Agent 执行 `cd <path> && pytest ...`
2. PowerShell 报错
3. Agent 重试用 `;` 成功

**建议修复**:
- 在 Agent 的 system prompt 中说明 Windows 使用 `;` 而非 `&&`
- 或在 Zima 层自动转换命令

---

### 问题 3: 后台任务超时限制
**严重级别**: P2 (功能限制)
**问题**: pytest 运行超过 60 秒，后台任务被强制终止
**错误**: `Command timed out after 60s`

**说明**:
- 当前后台任务硬编码 60 秒超时
- pytest 覆盖率测试通常需要 2-5 分钟
- 需要支持自定义超时或前台执行模式

**建议**:
- `zima pjob run --foreground` 前台执行模式
- 或读取 PJob 配置中的 `timeout` 字段

---

## 三、配置验证清单

### 已验证可用的配置

```yaml
# Agent 配置 - 正常
apiVersion: zima.io/v1
kind: Agent
spec:
  type: kimi
  parameters:
    model: kimi-code/kimi-for-coding
    workDir: C:/path/to/project
    promptFile: C:/path/to/prompt.md

# Workflow 配置 - 正常
apiVersion: zima.io/v1
kind: Workflow
spec:
  format: jinja2
  template: "..."

# Variable 配置 - 正常
apiVersion: zima.io/v1
kind: VariableConfig
spec:
  forWorkflow: workflow-code
  values:
    key: value

# Env 配置 - 正常
apiVersion: zima.io/v1
kind: EnvironmentConfig
spec:
  type: kimi
  variables:
    KEY: value

# PJob 配置 - 正常（无 PMG）
apiVersion: zima.io/v1
kind: PJob
spec:
  agent: agent-code
  workflow: workflow-code
  variable: var-code
  env: env-code
```

---

## 四、快速测试命令

```bash
# 1. 验证配置
zima pjob validate coverage-pjob

# 2. 渲染 workflow
zima workflow render coverage-workflow -v coverage-vars

# 3. 运行 PJob（前台，观察实时输出）
zima pjob run coverage-pjob

# 4. 查看执行历史
zima pjob history coverage-pjob

# 5. 查看详细错误
zima pjob history coverage-pjob --detail <execution-id>
```

---

## 五、当前部署状态

| 组件 | 代码 | 状态 |
|------|------|------|
| Agent | coverage-agent | ✅ 创建成功 |
| Workflow | coverage-workflow | ✅ 创建成功 |
| Variable | coverage-vars | ✅ 3 个变量已设置 |
| Env | coverage-env | ✅ 5 个环境变量已设置 |
| PJob | coverage-pjob | ✅ 创建成功 |

---

## 六、修复优先级

1. **P0** - Windows 文件写入 `[Errno 22]`（阻塞执行）
2. **P1** - PowerShell 命令分隔符（用户体验）
3. **P2** - 后台任务超时限制（功能增强）

---

## 七、Agent Prompt 文件位置

```
C:\Users\zhuzh\.zima\agents\coverage-agent\tasks\main.txt
```

**Prompt 内容**:
- 目标：覆盖率 26% → 50%
- 三阶段执行策略
- 8 个模块测试计划
- pytest 命令参考

---

## 八、最近一次执行日志

**Execution ID**: `987094fb`
**Duration**: 332.0 秒（5分32秒）
**Status**: failed
**Error**: `[Errno 22] Invalid argument`（executor.py stderr 写入）

**执行阶段**:
1. ✅ MCP 连接（8 servers, 59 tools）
2. ✅ 读取 prompt
3. ✅ 列出目录文件
4. ✅ 修复 PowerShell `&&` → `;`
5. ✅ 运行 pytest
6. ❌ 332 秒后文件写入错误

---

## 九、相关文件路径

```
Zima CLI 源码:
C:\Users\zhuzh\work\personal\zima-blue-cli\

配置目录:
C:\Users\zhuzh\.zima\configs\
  - agents\coverage-agent.yaml
  - workflows\coverage-workflow.yaml
  - variables\coverage-vars.yaml
  - envs\coverage-env.yaml
  - pjobs\coverage-pjob.yaml

Agent 工作目录:
C:\Users\zhuzh\.zima\agents\coverage-agent\tasks\main.txt

执行日志:
C:\Users\zhuzh\.zima\pjobs\coverage-pjob\results\
```

---

## 十、建议的修复代码

### executor.py - stderr 写入保护

```python
# zima/execution/executor.py

def _run_command(self, command, ...):
    # ... 现有代码 ...
    
    for line in process.stderr:
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except OSError as e:
            # Windows 文件写入错误保护
            logger.warning(f"Failed to write to stderr: {e}")
            # 继续执行，不要中断
```

### agent 配置 - PowerShell 提示

```python
# 在 Agent 的 system prompt 中添加：
"""
注意：当前环境是 Windows PowerShell。
- 使用分号 `;` 分隔多条命令
- 不要使用 `&&` 或 `||`
- 示例：`cd path; python script.py`
"""
```

---

**文档生成时间**: 2026-03-29
**测试 Agent**: coverage-agent
**目标项目**: zk-cli (26% → 50% 覆盖率)

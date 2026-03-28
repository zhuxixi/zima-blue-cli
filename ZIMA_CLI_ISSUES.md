# Zima CLI 问题与优化建议

> 基于创建 coverage-agent 的实际使用体验整理

---

## 1. 执行引擎问题

### 1.1 执行立即失败（0.0s）无详细日志
**现象**：`zima pjob run` 执行后立即返回 failed，持续时间 0.0s，没有有用的错误信息。

**期望**：
- 提供详细的错误堆栈
- 在 `zima pjob history` 中显示失败原因
- 增加 `--debug` 或 `--verbose` 模式输出详细日志

### 1.2 工作目录依赖不明确
**现象**：执行失败时提示需要 `./workspace` 目录，但错误信息隐藏在 Kimi CLI 的输出中。

**期望**：
- 在 PJob 执行前自动检查并创建工作目录
- 或在验证阶段检查 `workDir` 是否存在

---

## 2. 配置字段不一致

### 2.1 命名规范不统一
| 位置 | 当前使用 | 实际要求 |
|------|----------|----------|
| PMG | `for_types` | `forTypes` (camelCase) |
| Variable | `for_workflow` | `forWorkflow` (camelCase) |
| PJob output | 字符串路径 | 对象 `{saveTo, format, append}` |

**建议**：统一使用 snake_case 或 camelCase，并在验证时给出清晰的错误提示。

### 2.2 缺少配置示例
**现象**：用户不清楚正确的配置结构，需要通过试错来发现。

**建议**：
- 提供完整的配置示例（类似 Kubernetes 的 example）
- `zima <resource> create --example` 输出示例配置

---

## 3. 验证机制问题

### 3.1 验证通过但执行失败
**现象**：`zima pjob validate` 显示 valid，但实际执行失败。

**期望**：
- 验证时检查 Agent 类型是否存在
- 验证时检查 Variable 是否能正确渲染模板
- 验证时检查工作目录是否存在

### 3.2 错误信息不明确
**现象**：错误信息如 `"str" object has no attribute "get"` 难以理解。

**期望**：
- 提供用户友好的错误信息
- 指出具体哪个字段有问题
- 提供修复建议

---

## 4. Workflow 模板渲染

### 4.1 变量传递问题
**现象**：即使设置了 Variable，`zima workflow render` 输出为空变量。

**原因**：`forWorkflow` 字段必须正确关联，且变量名必须与模板完全匹配。

**建议**：
- 渲染失败时提示 "未找到变量 XXX，已配置的变量有: YYY"
- 支持嵌套变量（如 `{{ coverage.target }}`）

### 4.2 模板语法检查
**现象**：模板语法错误只在执行时发现。

**建议**：`zima workflow validate` 时检查 Jinja2 语法。

---

## 5. PMG 参数限制

### 5.1 参数名唯一性
**现象**：不能定义两个相同名称的参数（如 `--cov-report=term-missing` 和 `--cov-report=html`）。

**建议**：
- 支持同名的多值参数（如 `values: ["term-missing", "html"]`）
- 或允许使用不同的参数名映射到同一个 CLI 参数

---

## 6. Windows 环境兼容性问题

### 6.1 Unicode 编码错误
**现象**：报错信息中的 `✓` `✗` 等字符在 Windows 终端导致 `UnicodeEncodeError: 'gbk' codec can't encode character`。

**建议**：
- Windows 环境下使用 ASCII 字符替代
- 或检测终端编码自动调整输出

### 6.2 命令分隔符
**现象**：Windows PowerShell 不支持 `&&` 和 `||` 作为命令分隔符。

**建议**：
- 文档中注明 Windows 用户应使用 `;` 分隔命令
- 或使用跨平台的命令执行方式

---

## 7. Agent 类型支持

### 7.1 Agent 类型文档缺失
**现象**：用户不知道支持的 Agent 类型有哪些（`kimi`, `gemini`, `claude`）。

**建议**：
- `zima agent create --help` 列出支持的类型
- `zima agent types` 命令列出所有支持的类型

### 7.2 PMG forTypes 验证
**现象**：错误提示 `Invalid forType: coverage-agent. Valid: {'kimi', 'gemini', 'claude'}` 很有用，但应该在创建时就验证。

---

## 8. 命令行用户体验

### 8.1 Agent 创建重复问题
**现象**：`zima create` 如果 Agent 已存在，报错后有 Unicode 编码问题。

**建议**：
- 添加 `--force` 或 `--overwrite` 选项
- 或提供 `zima agent update` 命令

### 8.2 缺少批量操作
**现象**：创建完整 Agent 需要执行 10+ 个命令。

**建议**：
- 支持从 YAML 文件批量创建所有配置：`zima apply -f config.yaml`
- 或 `zima init` 向导式创建

---

## 9. 文档缺失

### 9.1 缺少完整配置参考
- Agent 配置所有字段说明
- Workflow 模板语法说明
- Variable、PMG、Env、PJob 完整字段参考

### 9.2 缺少故障排查指南
- 常见错误及解决方法
- 调试技巧

---

## 10. 建议的优先级

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | 执行失败无详细日志 | 无法诊断问题 |
| P0 | Unicode 编码错误 | Windows 用户无法使用 |
| P1 | 配置字段命名统一 | 降低学习成本 |
| P1 | 验证机制增强 | 提前发现问题 |
| P2 | 批量操作支持 | 提升效率 |
| P2 | 完整配置参考 | 降低使用门槛 |

---

## 附录：正确配置示例

### Agent (kimi 类型)
```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: coverage-agent
  name: Coverage Agent
spec:
  type: kimi
  parameters:
    model: kimi-code/kimi-for-coding
    maxStepsPerTurn: 50
    yolo: true
    workDir: C:/Users/zhuzh/work/personal/jfox/zk-cli
    promptFile: C:/Users/zhuzh/.zima/agents/coverage-agent/tasks/main.txt
```

### PMG
```yaml
apiVersion: zima.io/v1
kind: ParametersGroup
metadata:
  code: coverage-pmg
  name: Coverage PMG
spec:
  forTypes:
    - kimi
  parameters:
    - name: verbose
      type: flag
      enabled: true
```

### PJob
```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: coverage-pjob
  name: Coverage Job
spec:
  agent: coverage-agent
  workflow: coverage-workflow
  variable: coverage-vars
  env: coverage-env
  pmg: coverage-pmg
```

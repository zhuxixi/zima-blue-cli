# ADR 001: 使用 subprocess 调用 kimi-cli

## 状态

✅ 已接受

## 背景

ZimaBlue CLI 需要调度 Kimi Code Agent 执行周期性任务。我们面临两种集成方式：

1. **直接调用**: 导入 kimi-cli 的 Python 模块，直接调用 `KimiCLI.create()`
2. **subprocess 调用**: 通过 `subprocess.run(["kimi", "--print", ...])` 调用命令行

## 决策

我们决定使用 **subprocess 方式** 调用 kimi-cli。

## 原因

### 1. 解耦性

- 直接调用会深度依赖 kimi-cli 的内部 API
- subprocess 方式通过标准 CLI 接口交互，更加稳定

### 2. 进程隔离

- 每个 Agent 周期都是独立的进程
- 超时 kill 不会影响 ZimaBlue 主进程
- 便于资源管理和错误隔离

### 3. 简化设计

- 无需了解 kimi-cli 内部类结构
- 通过命令行参数控制行为即可
- 更容易调试和监控

### 4. 兼容性

- kimi-cli 的 CLI 接口相对稳定
- 内部 API 可能随版本变化

## 权衡

| 优点 | 缺点 |
|------|------|
| 进程隔离，更稳定 | 进程启动有一定开销 |
| 解耦，不依赖内部 API | 需要解析文本输出 |
| 易于调试 | 无法直接共享内存 |
| 兼容性好 | - |

## 实施

```python
# 使用 subprocess 调用
result = subprocess.run(
    ["kimi", "--print", "--yolo", "--prompt-file", "prompt.md"],
    stdout=f,
    stderr=subprocess.STDOUT,
    timeout=840
)
```

## 相关文档

- [架构设计](../architecture/README.md)
- [进度恢复机制](../architecture/progress-recovery.md)

# JFox Coverage Agent

ZK-CLI 项目测试覆盖率提升 Agent。

## 目标

循环执行测试覆盖率提升工作：
1. **analyze** - 分析测试现状，确定优先处理项
2. **execute** - 运行指定测试文件（单文件，控制时间）
3. **fix** - 修复失败的测试用例
4. **verify** - 验证修复结果

## 为什么分批处理？

ZK-CLI 完整测试套件运行时间约 **30 分钟**，频繁运行不可行。
本 Agent 采用策略：
- 每批只运行 **1 个测试文件**
- 单个文件控制在 **5 分钟内**
- 优先处理高优先级文件

## 项目配置

| 配置项 | 值 |
|--------|-----|
| 周期间隔 | 15 分钟 |
| 最大执行时间 | 14 分钟 |
| 项目路径 | `C:/Users/zhuzh/work/personal/jfox/zk-cli` |
| 测试目录 | `tests/` |

## 测试文件优先级

### P0 - 阻塞性问题
- 测试文件无法导入
- 核心功能测试全部失败

### P1 - 高优先级
1. `test_kb_current.py` - kb current 命令（最简单，热身）
2. `test_core_workflow.py` - 核心功能
3. `test_backlinks.py` - 反向链接

### P2 - 中优先级
4. `test_hybrid_search.py` - 混合搜索
5. `test_suggest_links.py` - 链接建议
6. `test_formatters.py` - 格式化输出
7. `test_cli_format.py` - CLI 格式

### P3 - 低优先级
8. `test_template.py` - 模板功能
9. `test_advanced_features.py` - 高级功能
10. `test_integration.py` - 集成测试

## 已知问题

来自 DEVELOPMENT_PLAN.md：
- Issue #13: `--kb` 参数未完全实现
- Issue #14: `kb current` 命令待实现
- Issue #15: MCP Server 扩展待开发
- Issue #16: `suggest-links` 命令待实现

## 启动方式

### 前台运行（测试）
```bash
cd C:/Users/zhuzh/work/personal/zima-blue-cli
zima start jfox-coverage-agent
```

### 后台守护进程
```bash
zima start jfox-coverage-agent --detach
```

### 查看状态
```bash
zima status jfox-coverage-agent
```

### 查看日志
```bash
zima logs jfox-coverage-agent
```

### 停止 Agent
```bash
zima stop jfox-coverage-agent
```

## 状态文件

`agent_state.json` 记录：
- 当前处理阶段
- 各测试文件状态
- 已完成的修复
- 执行历史

## 预期工作流程

```
Cycle 1: analyze -> 确定 test_kb_current.py 为首个目标
Cycle 2: execute -> 运行 test_kb_current.py，发现 kb current 命令缺失
Cycle 3: fix -> 实现 kb current 命令
Cycle 4: verify -> 验证测试通过
Cycle 5: analyze -> 确定下一个目标 test_backlinks.py
...
```

## 完成标准

- [ ] 所有 P1 优先级测试文件通过
- [ ] 所有 P2 优先级测试文件通过
- [ ] 主要模块测试覆盖率 > 80%

## 注意事项

1. **不要一次运行所有测试** - 会耗时 30 分钟+
2. **始终检查 agent_state.json** - 避免重复工作
3. **记录每个修复** - 便于追踪进度
4. **优先修复简单问题** - 在时间不足时最大化产出

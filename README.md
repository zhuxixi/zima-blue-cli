# Zima Blue CLI

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue CLI** 是一个个人 Agent 编排平台，让你能够在自己的电脑上运行一个 7x24 小时自主工作的 AI Agent 工厂。

```
你的职责：说话、决策、审查
Agent 的职责：执行、迭代、交付
```

第二天早上醒来，Agent 已经帮你实现了多个版本。

---

## ⚠️ 重要声明

> **本项目采用迭代式设计**
> 
> - `docs/history/` 中的早期文档仅供参考，记录了设计演进过程
> - **请以 `docs/architecture/` 中的最新设计为准**
> - 实现时以本仓库根目录的 `AGENTS.md` 和最新架构文档为最终依据

---

## 核心概念

### Agent = kimi-cli 的单次执行

每个 15 分钟周期，ZimaBlue 会：
1. 生成 Prompt 文件
2. 调用 `kimi --print --prompt-file ...`
3. kimi-cli 执行完成后退出
4. ZimaBlue 等待下一周期

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  苏醒    │────►│  执行    │────►│  休眠    │
│ 读Session│     │ 启动kimi │     │ 等待15min│
└──────────┘     └──────────┘     └──────────┘
```

### 三层记忆

| 层级 | 形式 | 用途 |
|------|------|------|
| **Session** | Markdown 文件 | Agent 的"日记"，记录每轮做了什么 |
| **日志** | kimi 输出 | 完整执行记录，用于排查问题 |
| **检查点** | JSON 文件 | 超时时的状态快照，用于恢复 |

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/zhuxixi/zima-blue-cli.git
cd zima-blue-cli

# 安装依赖
pip install -e "."

# 创建 Agent
zima agent create \
  --name zk-coverage-agent \
  --workspace ./agents/zk-coverage-agent \
  --task coverage_check

# 启动 Agent
zima agent start zk-coverage-agent

# 查看状态
zima agent status zk-coverage-agent

# 查看日志
zima agent logs zk-coverage-agent -f
```

---

## 文档结构

```
docs/
├── vision/           # 项目愿景和故事
│   ├── README.md     # 愿景总览
│   └── story.md      # 齐马蓝故事背景
│
├── architecture/     # 最新架构设计 ⭐ 以此为准
│   ├── README.md     # 架构总览
│   └── progress-recovery.md  # 进度恢复机制
│
├── history/          # 历史设计文档（仅供参考）
│   ├── ralph-loop-design.md
│   ├── kimiworld-design.md
│   └── agent-cycle-timeline.md
│
└── decisions/        # 架构决策记录 (ADR)
    ├── 001-use-subprocess.md
    ├── 002-15min-cycle.md
    └── 003-early-completion.md
```

---

## 工作原理

### 15 分钟循环

```
┌─────────────────────────────────────────────────────────┐
│  苏醒 (3min)  →  执行 (9min)  →  结束 (3min)            │
│                                                           │
│  • 读 Session    • 启动 kimi    • 解析结果               │
│  • 确定任务      • 执行 AI      • 写 Session             │
│  • 生成 Prompt   • 等待完成     • 更新状态               │
└─────────────────────────────────────────────────────────┘
```

### 异步任务支持

```
第1轮: 分析覆盖率
        │
        ▼
第2轮: 启动全量测试 ──► 异步运行
        │                 │
        ▼                 │
第3轮: 检查状态 ◄─────────┘ 还没完
        │
        ▼
第4轮: 检查状态 ◄───────── 完成了！
        │
        ▼
第5轮: 修复失败的测试
```

---

## 命名来源

**Zima Blue** 源自 Alastair Reynolds 的科幻短篇《齐马蓝》。

> 故事讲述了一个艺术家机器人历经万年升级进化，最终回归最初简单的泳池清洁机器人状态——象征着**回归本质、无尽循环、自我进化**。

这与我们的愿景完美契合：
- 🔄 **无尽循环** — Agent 7x24 小时持续工作
- 🎯 **回归本质** — 剥离复杂管理，回归"说话→执行"
- 📈 **自我进化** — 从简单开始，逐步学习和改进

[阅读完整故事](docs/vision/story.md)

---

## 开发

详见 [AGENTS.md](AGENTS.md) 了解开发规范和设计原则。

---

## License

MIT

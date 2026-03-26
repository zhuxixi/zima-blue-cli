# Zima Blue CLI

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue CLI** 是一个 Agent 启动器，管理 Kimi CLI 的执行参数，让 AI 执行明确的 SOP 任务。

```
定义 Prompt 模板 → 配置参数 → 执行 → 获取结果
```

---

## ⚠️ 重要声明

> **本项目采用迭代式设计**
> 
> - `docs/history/` 中的早期文档仅供参考，记录了设计演进过程
> - **请以 `docs/architecture/` 中的最新设计为准**
> - 实现时以本仓库根目录的 `AGENTS.md` 和最新架构文档为最终依据

---

## 核心概念

### Agent = Prompt 模板 + 工作空间

```
agents/my-agent/
├── agent.yaml       # 配置：元数据、Prompt文件、Kimi参数
├── prompt.md        # Prompt模板（定义工作流）
└── workspace/       # 工作目录
```

### 执行流程

```bash
# 单次执行，无后台进程
zima run my-agent

# Kimi 执行 Prompt 定义的工作流
# 完成后返回结果
```

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/zhuxixi/zima-blue-cli.git
cd zima-blue-cli

# 安装依赖
pip install -e "."

# 创建 Agent
zima create my-agent

# 运行 Agent
zima run my-agent

# 查看日志
zima logs my-agent
```

---

## CLI 命令

```bash
zima create <name>          # 创建 Agent
zima run <name>             # 单次执行
zima list                   # 列出所有 Agent
zima show <name>            # 查看配置
zima logs <name>            # 查看日志
```

---

## 文档结构

```
docs/
├── vision/           # 项目愿景和故事
├── architecture/     # 最新架构设计 ⭐ 以此为准
├── history/          # 历史设计（仅供参考）
└── decisions/        # 架构决策记录 (ADR)
    ├── 001-use-subprocess.md
    ├── 002-15min-cycle.md (已废弃)
    ├── 003-early-completion.md (已废弃)
    └── 004-single-execution.md ⭐ 当前架构
```

---

## 适用场景

- **SOP 任务**：运维脚本、数据处理、报告生成
- **研发任务**：测试覆盖、代码重构（通过 Prompt 定义工作流）
- **CI/CD 集成**：作为构建步骤，返回结构化结果

---

## 命名来源

**Zima Blue** 源自 Alastair Reynolds 的科幻短篇《齐马蓝》。

> 故事讲述了一个艺术家机器人历经万年升级进化，最终回归最初简单的泳池清洁机器人状态——象征着**回归本质、自我进化**。

---

## 开发

详见 [AGENTS.md](AGENTS.md) 了解开发规范和设计原则。

---

## License

MIT

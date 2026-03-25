# Boktionary 全自动研发工厂设计方案

> 基于 Ralph Loop 的 7x24 小时自主迭代系统
> 
> 讨论日期: 2026-03-25
> 状态: 设计阶段

---

## 1. 愿景

构建一个**自进化的研发工厂**，利用：
- **知识库 (zk)** 作为「记忆/上下文」载体
- **GitHub Issues** 作为「任务队列」
- **Kimi Code** 作为「执行者」

实现夜间自动迭代，最大化利用非工作时间，减少重复性人工参与。

---

## 2. 核心挑战

### 2.1 大型 Issue 的拆分难题

大型 Issue 需要拆分才能进入 Ralph Loop，但拆分过程需要人的判断力。

**两难：**
- 完全自动拆分 → 容易理解错意图
- 完全人工拆分 → 违背夜间自动化初衷

**解决方向：** 分层拆分 + 异步协作

---

## 3. 分层拆分策略

```
大 Issue (Epic)
    │
    ├── 🌙 阶段1: AI 自动分析（夜间）
    │   ├── 读取知识库了解上下文
    │   ├── 分析代码库识别涉及模块
    │   └── 生成「初步拆分方案」
    │   ↓
    ├── ☀️ 阶段2: 人工审查确认（白天）
    │   ├── 审阅拆分合理性
    │   ├── 调整优先级和验收标准
    │   └── 确认或要求修改
    │   ↓
    └── 🌙 阶段3: AI 自动执行（夜间）
        ├── 将确认方案转为 prd.json
        └── Ralph Loop 逐个执行
```

**核心洞察：**
- 不是"要不要人参与"，而是"在哪个环节以什么形式参与"
- AI 擅长：分析、枚举、结构化
- 人擅长：判断、决策、把握方向
- 异步协作：通过 GitHub Issue 评论区接力，不需要实时在线

---

## 4. 职责分离设计

### 4.1 存储位置分工

| 存储位置 | 存储内容 | 生命周期 |
|---------|---------|---------|
| **知识库 (zk)** | 结论、决策、技术方案、经验教训 | 长期、结构化 |
| **GitHub Issue** | 任务、拆分方案、执行状态、临时信息 | 短期、动态 |

### 4.2 知识库不存什么

❌ **不存储：**
- Issue 拆分的中间过程
- 临时的任务列表
- 未确认的假设

✅ **存储：**
- ADR (架构决策记录)
- 验证过的技术方案
- 项目结构和约定
- 复盘总结

---

## 5. 安全边界（信任等级分层）

| 等级 | 操作类型 | 夜间自动 | 示例 |
|------|---------|---------|------|
| 🟢 L1 | 只读/分析 | ✅ 完全自动 | 查询知识库、阅读代码、生成方案 |
| 🟡 L2 | 本地修改 | ✅ 完全自动 | 编写代码、本地测试、生成文档 |
| 🟠 L3 | 本地提交 | ⚠️ 次日审查 | `git commit` 到 feature 分支 |
| 🔴 L4 | 远程操作 | ❌ 禁止自动 | `git push`、合并 PR、部署生产 |

**夜间只能执行 L1-L2**

---

## 6. Ralph Loop 核心机制

```
┌──────────────────────────────────────────────────────────────┐
│                    每个迭代 = 全新 AI 实例                    │
├──────────────────────────────────────────────────────────────┤
│  1. Pick Task     → 从 prd.json 选择下一个未完成的故事        │
│  2. Implement     → AI 编写/修改代码                         │
│  3. Validate      → 运行测试、类型检查、质量验证               │
│  4. Commit        → 如果检查通过，提交代码                    │
│  5. Update State  → 标记故事为完成，记录学习到 progress.txt   │
│  6. Reset Context → 清除上下文，为下一个迭代做准备            │
└──────────────────────────────────────────────────────────────┘
```

**关键设计原则：**
- Small Tasks: 每个任务能在 1-2 小时内完成
- Fresh Context: 每次迭代都是新的 AI 实例
- Persistent Memory: git历史 + progress.txt + 知识库
- Validation Loop: 必须有测试/检查作为反馈
- Compound Learning: AGENTS.md/知识库积累知识

---

## 7. 完整流程示例

### 7.1 Issue 拆分流程

以 **"修复定时任务卡点"** 为例：

```
【晚上 22:00】Agent 开始巡检
    │
    ├── 扫描到 Issue #88: "修复定时任务卡点，完善 ETL 流程"
    ├── 判断: 大 Issue（描述模糊，涉及多个模块）
    │
    ├── 【自动分析】
    │   ├── 读取知识库: 了解 ETL 架构、之前卡点记录
    │   ├── 读取代码: 定时任务实现、异常处理逻辑
    │   └── 生成拆分方案:
    │       1. 诊断卡点（日志分析、定位瓶颈）
    │       2. 设计超时策略（技术方案文档）
    │       3. 实现超时机制（编码）
    │       4. 增加监控告警（可观测性）
    │       5. 补充集成测试（质量保证）
    │
    └── 💬 更新到 Issue #88 评论区:
        └── 「【拆分方案 - 待审查】」
            - Task 1: ...
            - Task 2: ...
            - 风险: ...
        └── 添加标签: `needs-review`

【第二天早上】你看到 Issue #88 有新评论
    │
    ├── 审阅拆分方案
    ├── 回复确认或调整意见
    └── 修改标签: `confirmed` / `needs-refinement`

【第二天晚上】Agent 再次巡检
    │
    ├── 看到标签 `confirmed`
    ├── 读取确认后的方案
    ├── 生成 prd.json
    └── Ralph Loop 开始执行 Task 1...
```

### 7.2 小 Issue 直接执行流程

```
【晚上】Agent 巡检
    │
    ├── 发现 Issue #90: "修复 typo in README"
    ├── 判断: 小 Issue（范围明确，可直接执行）
    │
    ├── 直接执行:
    │   ├── 修改代码
    │   ├── 本地测试通过
    │   └── git commit
    │
    └── 更新 Issue:
        ├── 评论: 「已完成，本地已提交，等待 push」
        └── 标签: `ready-for-review`

【第二天】你审查后决定:
    ├── ✅ push → 直接 push 到远程
    └── ❌ 有问题 → 回复修改意见
```

---

## 8. Issue 大小判断标准

### 8.1 大 Issue 特征（需要拆分）

```python
def should_decompose(issue):
    if len(issue.body) > 1500:        # 描述很长
        return True
    if has_keywords(["重构", "架构", "集成", "迁移", "完善"]):
        return True
    if estimate_hours(issue) > 4:      # 估算超过 4 小时
        return True
    if involves_multiple_modules():    # 跨模块
        return True
    if has_unclear_scope():            # 范围模糊
        return True
    return False
```

### 8.2 小 Issue 特征（直接执行）

- 修改范围明确（单个文件或函数）
- 有现成的测试用例可以参考
- 描述具体，没有模糊词汇
- 估算工时 < 2 小时

---

## 9. 拆分方案输出格式

当生成拆分方案时，在 Issue 评论区添加：

```markdown
## 【拆分方案 - 待审查】

### 分析摘要
定时任务卡点的根本原因是缺少超时机制...

### 建议拆分

#### Task 1: 诊断当前卡点
- **目标**: 分析日志，定位具体卡点位置
- **验收标准**: 输出卡点分析报告，包含瓶颈位置和建议
- **估算**: 1h
- **依赖**: 无

#### Task 2: 设计超时策略
- **目标**: 确定超时和重试机制的技术方案
- **验收标准**: 产出设计文档，评审通过
- **估算**: 1.5h
- **依赖**: Task 1

#### Task 3: 实现超时机制
- **目标**: 在 ETL 调度器中添加超时控制
- **验收标准**: 
  - 任务超时后自动重试3次
  - 重试间隔指数退避（1s, 5s, 15s）
  - 有单元测试覆盖
- **估算**: 2h
- **依赖**: Task 2

### 风险提示
- ⚠️ 可能引入并发问题
- ⚠️ 需要兼容现有调度器配置

### 建议
建议先做 Task 1 的诊断，确认卡点后再决定后续方案。
```

---

## 10. 渐进式实施路径

### Phase 1: 人工触发（现在就可以开始）
- 手动运行 Agent 分析某个 Issue
- 人工审查拆分方案
- 确认后手动触发执行

### Phase 2: 半自动（减少人工介入）
- 定时巡检 Issue
- 自动分析并添加拆分评论
- 人工审查确认
- 确认后自动执行

### Phase 3: 全自主（长期目标）
- 完善的自动化测试和验证
- Agent 可以安全地提交代码
- 只在异常或关键决策时通知人

---

## 11. 待解决问题

- [x] 设计 Agent 的触发机制（定时/事件驱动）→ **使用 KimiWorld 调度程序，15分钟周期**
- [x] ~~定义 progress.txt 的具体格式和位置~~ → **不使用 progress.txt，改用 Kimi CLI 日志输出 + Agent 个人知识库**
- [x] ~~设计 prd.json 的生成和存储方式~~ → **直接存储到 GitHub Issue 评论区**
- [x] 确定如何通知"有待审查的拆分方案" → **通过 GitHub Issue 标签 `needs-review` + 可选的邮件/Slack 通知**
- [ ] 设计如何防止 Agent 陷入无限循环
- [ ] 成本控制和 API 调用限制
- [x] **Kimi CLI 非交互模式加载 Skill** → **使用 `--print --skills-dir --yolo` 参数组合**

---

## 12. 下一步行动

1. **试点拆分流程**
   - 从 Boktionary 挑选一个需要拆分的大 Issue
   - 手动演示完整的拆分 → 审查 → 确认流程
   - 验证方案可行性

2. **设计最小可行 Skill**
   - 封装 Issue 分析逻辑
   - 集成 GitHub API
   - 实现基本的拆分建议

3. **完善知识库内容**
   - 补充 Boktionary 的架构决策记录
   - 整理 ETL 相关的技术方案
   - 建立项目约定和最佳实践

---

## 13. Kimi CLI 非交互模式与 Skill 集成

### 13.1 已确认的技术细节

基于对 kimi-cli 源码的分析，确认以下方案可行：

**命令格式**：
```bash
kimi-cli \
  --print \                    # 非交互模式
  --yolo \                     # 自动批准所有操作
  --skills-dir ./skills \      # 指定 Skills 目录（自动加载目录下所有 Skill）
  --prompt-file prompt.md \    # 从文件读取提示词
  --work-dir ./workspace \     # 工作目录
  --max-steps-per-turn 50      # 每轮最大步数
```

**关键发现**：
1. `--print` 模式隐式添加 `--yolo`，无需人工确认
2. `--skills-dir` 会覆盖自动发现机制，只加载指定目录的 Skills
3. Skills 会在 Runtime 初始化时加载，并注册为 `/skill:{name}` 命令
4. 所有输出（stdout/stderr）都可以通过重定向捕获到日志文件

### 13.2 日志捕获实现

```python
import subprocess
from datetime import datetime

# 生成带时间戳的日志文件
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"cycle_{timestamp}.log"

# 执行 Kimi CLI，合并 stdout/stderr 到日志文件
with open(log_file, "w", encoding="utf-8") as f:
    result = subprocess.run(
        cmd,
        timeout=900,           # 15分钟超时
        stdout=f,              # 标准输出写入文件
        stderr=subprocess.STDOUT,  # 错误输出合并到 stdout
        text=True,
        cwd=workspace
    )
```

**日志保留策略**：保留所有历史日志，不自动清理。

---

## 参考

- [Ralph Loop - snarktank/ralph](https://github.com/snarktank/ralph)
- [Self-Improving Coding Agents - AddyOsmani](https://addyosmani.com/blog/self-improving-agents/)
- OODA Loop (Observe-Orient-Decide-Act)
- PDCA Loop (Plan-Do-Check-Act)
- kimi-cli 源码：`--print` 模式分析

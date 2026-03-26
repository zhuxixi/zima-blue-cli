# Zima v2 - Agent 调度器设计

## 核心理念转变

### v1: 循环守护进程
```
Zima ──15min──> Kimi ──15min──> Kimi ──15min──> ...
```
问题：调度逻辑分散在 kimi 和 zima 之间，难以控制

### v2: SOP Agent 模板
```
Template (Prompt + 终止条件) ──单次唤起──> Kimi ──完成──> 结果
```
优势：明确的输入→处理→输出，可复用、可验证

---

## 使用场景

### 场景 A: 运维 SOP（目标明确）
```
任务: 服务器磁盘清理
输入: 服务器 IP
工作流:
  1. 检查磁盘使用率
  2. 清理日志文件 (>30天)
  3. 清理临时文件
  4. 生成清理报告
终止条件: 报告生成完成
输出: 清理报告 JSON
```

### 场景 B: 研发任务（目标相对明确）
```
任务: 提高测试覆盖率到 80%
输入: 项目路径
工作流:
  1. 分析当前覆盖率
  2. 找出未覆盖代码
  3. 为关键路径编写测试
  4. 运行测试验证
终止条件: 覆盖率>=80% 或 达到最大迭代
输出: 覆盖率报告 + 新增测试文件
```

---

## CLI 接口设计

### 1. 创建 Agent 模板
```bash
zima create \
  --name coverage-improver \
  --template templates/coverage.md \
  --workspace ./workspaces/coverage \
  --max-time 30m \
  --output-format json
```

### 2. 运行 Agent（单次执行）
```bash
zima run coverage-improver \
  --input project_path=./jfox/zk-cli \
  --input target_coverage=80
```

### 3. 运行并指定终止条件
```bash
zima run coverage-improver \
  --input project_path=./jfox/zk-cli \
  --until "coverage >= 80" \
  --max-iterations 5
```

### 4. 查看结果
```bash
zima result coverage-improver --last
```

---

## 模板格式 (templates/coverage.md)

```markdown
# Agent: {{ name }}

## 任务描述
{{ description }}

## 输入参数
- project_path: {{ input.project_path }}
- target_coverage: {{ input.target_coverage }}% (默认: 80)

## 工作流
1. **分析阶段**
   - 运行 `pytest --cov` 获取当前覆盖率
   - 识别未覆盖的关键代码路径

2. **实现阶段**
   - 为未覆盖代码编写测试
   - 遵循项目测试规范

3. **验证阶段**
   - 运行测试确保通过
   - 检查覆盖率是否达标

## 终止条件
{{#if termination.manual }}
- 用户确认完成
{{else}}
- 覆盖率 >= {{ input.target_coverage }}%
- 或达到最大迭代次数
{{/if}}

## 输出格式
```json
{
  "status": "completed|partial|failed",
  "coverage_before": "{{ metrics.before }}%",
  "coverage_after": "{{ metrics.after }}%",
  "files_created": ["{{#each files}}"{{ this }}"{{#unless @last}},{{/unless}}{{/each}}"],
  "summary": "{{ summary }}"
}
```

## 执行规则
- 每轮最多 {{ config.max_steps }} 步
- 总时间限制 {{ config.max_time }}
- 完成后必须输出上述 JSON
```

---

## 架构对比

| 维度 | v1 (循环守护) | v2 (SOP Agent) |
|------|--------------|----------------|
| 唤起方式 | 定时 15min | 按需 `zima run` |
| 控制权 | kimi 自主 | 模板定义明确 |
| 终止条件 | kimi 决定 | 模板预定义 + 参数 |
| 可复用性 | 低（单次任务） | 高（模板可复用） |
| 验证方式 | 难 | 明确（JSON 输出） |
| 适用场景 | 开放式研发 | 明确 SOP 任务 |

---

## 实现优先级

### P0 - 核心
1. 模板引擎 (Jinja2)
2. `zima run` 单次执行
3. 终止条件解析器
4. 结果收集器

### P1 - 增强
1. 模板市场/库
2. 条件循环 (`--until`)
3. 结果对比（多次运行）

### P2 - 生态
1. Web UI 管理模板
2. 模板版本控制
3. CI/CD 集成

---

## 示例：完整使用流程

```bash
# 1. 创建模板
zima template init coverage \
  --from-prompt "提高 {project} 的测试覆盖率到 {target}%"

# 2. 编辑模板（添加详细工作流）
vim ~/.zima/templates/coverage.md

# 3. 运行
zima run coverage \
  --set project=./myproject \
  --set target=80 \
  --watch  # 实时查看进度

# 4. 查看结果
cat ~/.zima/results/coverage/2026-03-26-09-30.json
```

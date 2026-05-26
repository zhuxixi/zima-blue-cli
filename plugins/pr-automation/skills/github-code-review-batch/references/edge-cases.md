# Edge Cases, Troubleshooting, and Common False Positives

---

## 边界情况处理 {#边界情况}

| 情况 | 处理方式 |
|------|----------|
| PR 已关闭/已合并 | [Step 1](flow.md#step-1) 或 [Step 7](flow.md#step-7) 捕获，停止执行并向用户说明 |
| PR 是草稿 | [Step 1](flow.md#step-1) 捕获，停止执行并向用户说明 |
| PR 是 trivial/自动化 | [Step 1](flow.md#step-1) 捕获，停止执行并向用户说明 |
| 已有 bot 评论 | 正常审查，不跳过（非监听模式下多轮审查是预期行为） |
| PR 由 AI 生成 | 正常审查，不跳过 |
| 无 CLAUDE.md / AGENTS.md | 仅执行 bug scanner 和 logic analyzer |
| 大 PR（超过 50 个文件） | 正常处理，并行 Agent 保证效率 |
| 所有 issue 验证为无效 | 输出 "No issues found" |
| 审查过程中 PR 关闭 | [Step 7](flow.md#step-7) 捕获，不发布评论 |
| `gh` 命令失败 | 向用户报告错误详情，停止执行 |
| 当前分支无关联 PR | 提示用户提供 PR 编号 |
| 提取不到完整 SHA | 使用 `gh pr view <PR> --json headRefOid` 获取 head SHA，失败则报错 |
| Agent 返回格式错误的 JSON | 尝试解析，失败则忽略该 Agent 的输出 |
| diff 过大无法完整处理 | [Step 3.5](flow.md#step-3-5) 预处理：过滤测试文件 + 4000 字符硬限制（hunk-only 压缩 + 截断），不再丢弃整个分析 |
| 无新 commit（调度器轮询） | [Step 0](flow.md#step-0-3) 检测 → 输出状态报告（含仍 open 的 issues），Status: `NO_NEW_COMMITS` |
| Metadata 部分损坏（能拿到 round） | 以读到的 round 为底线，本轮 round+1，其余 fallback 默认值，输出警告 |
| Metadata 完全无法解析 | 报错并停止；**不再静默 fallback 到 Round-1**（避免破坏外部调度器状态机） |
| Round 编号溢出（>99） | 继续递增，无上限 |
| committer 评论中无明确信号 | 分类为 null，按原有流程处理 |
| committer 回应与代码实际不符 | delta-reviewer 结合 diff 判断，**以代码为准** |
| 所有 open issues 被标记 acknowledged | 输出状态报告，Status: `PASS`（无真正 open issues） |

---

## 故障排除 {#故障排除}

### 问题：无法获取 PR 信息

**原因**：`gh` 未安装、未认证、或当前目录不在 Git 仓库中。

**解决**：
1. 运行 `gh --version` 确认已安装
2. 运行 `gh auth status` 确认已认证
3. 运行 `git remote -v` 确认有 GitHub remote

### 问题：审查后没有发布评论

**原因**：
- PR 在审查过程中被关闭或合并（[Step 7](flow.md#step-7) 拦截）
- `gh pr review` 命令失败
- PR 未通过资格审查

**排查**：
1. 检查终端输出中的资格审查结果
2. 检查 [Step 7](flow.md#step-7) 的输出
3. 检查 `gh pr review` 是否有错误信息

### 问题：Agent 输出格式错误

**原因**：SubAgent 没有按要求输出 JSON。

**解决**：
- 在 prompt 中明确要求输出 JSON
- 如果解析失败，忽略该 Agent 的输出，继续处理其他 Agent 的结果

### 问题：代码链接无法点击

**原因**：SHA 不完整、格式不正确、或行号计算错误。

**解决**：
- 确保使用 `gh pr view <PR> --json headRefOid --jq '.headRefOid'` 获取完整 40 字符 SHA
- 确保格式严格为 `https://github.com/owner/repo/blob/[sha]/path#L[start]-L[end]`
- 由 [build_review_body.py](../scripts/build_review_body.py) 生成时这些约束已固化

---

## 常见误报类型 {#常见误报}

以下是审查 Agent 容易产生误报的场景，[issue-validator](subagent-prompts.md#issue-validator) 应特别注意识别：

1. **原有问题**：问题在 PR 之前就已经存在，不是本次变更引入的
2. **误读逻辑**：Agent 误解了代码的执行路径或条件分支
3. **过度推断**：从代码中推导出了没有直接证据支持的结论
4. **假设性问题**：基于某种假设场景（如极端输入）提出的问题
5. **规范误用**：将不适用于当前代码类型的规范规则强加于此
6. **上下文缺失**：由于未读取完整上下文而做出的错误判断

### 有效 issue 示例

```json
{
  "description": "函数返回了未初始化的变量，在错误路径中可能导致未定义行为",
  "reason": "bug",
  "file": "src/api/handlers.py",
  "lines": "45-52",
  "suggestion": "在错误路径中为 result 设置默认值或提前返回"
}
```

### 无效 issue 示例（应被 validator 过滤）

```json
{
  "description": "这个函数名不够描述性",
  "reason": "CLAUDE.md",
  "file": "src/utils.py",
  "lines": "12-15",
  "suggestion": "改为更具描述性的名字"
}
```

过滤原因：CLAUDE.md 中并未明确规定函数命名的具体要求，属于主观判断。

---

## 审查覆盖原则 {#审查覆盖原则}

各 checker 共享的判断框架。

### 优先标记以下问题（高优先级）

- **编译/解析错误**：语法错误、无法通过编译的代码
- **缺失导入**：使用了未导入的模块、函数、类
- **未解析引用**：引用了不存在的变量、函数、属性
- **确定性逻辑错误**：代码逻辑明显错误，不依赖外部输入即可判定
- **规范违规**：`CLAUDE.md` 或 `AGENTS.md` 中的规则违反（尽量引用规则原文；对于逻辑/安全问题，无需强制引用规范）
- **资源泄漏与安全漏洞**：未关闭的文件句柄、未释放的连接、明显的注入风险、竞态条件

### 同样值得关注的问题（中优先级）

- **错误处理缺失**：关键路径缺少异常处理、错误码被静默吞掉
- **边界条件问题**：空值、空列表、零除等未处理的边界情况
- **文档与代码不一致**：PR 描述或文档声称做了某事，但代码实际未做到（如声称更新了某文件但 diff 中不存在）
- **潜在的逻辑缺陷**：条件判断明显不合理、循环/递归终止条件有问题

### 不标记以下问题

- **代码风格问题**：缩进、命名风格、括号位置等纯格式问题
- **一般代码质量问题**：函数过长、圈复杂度高等（除非导致明确错误）
- **主观性建议**："这里可以优化..."、"建议换一种写法..." 等没有明确对错的意见
- **PR 未修改的原有代码中的问题**：只审查变更内容
- **Linter / TypeChecker 可以捕获的问题**：如果静态分析工具已经能发现，不重复报告
- **已被 lint-ignore 注释忽略的规则**：代码中明确有 `eslint-disable`、`type: ignore` 等注释的，尊重开发者意图

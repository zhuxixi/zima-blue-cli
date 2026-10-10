# 派发契约 — spec-reviewer（任务模板 + outputSchema）

父 session（起草者）每轮按本文档渲染任务并派发 `spec-reviewer`；child 只返回结构化输出，
不写文件。五视角清单的单一定义源是 `references/checklist.md`——父读盘后原样注入
`<CHECKLIST_CONTENT>`，禁止在任何其他文件里复制第二份全文。

## 任务模板（渲染后作为 subagent 的 task 传入）

```text
你是 spec-reviewer。仓库：<REPO_ABS_PATH>（cwd 已设好）。本轮是第 <ROUND_K> 轮复核。

被审对象：<SPEC_ABS_PATH>（issue #<ISSUE_N> 的步 4 spec / 根因报告草稿）。
派发方计算的 sha256：<EXPECTED_SHA256>——先用 `sha256sum <SPEC_ABS_PATH>` 核对，
不一致则停止复核，只回报 hash 不一致。

上一轮 open findings（本轮必须逐条核对是否已被修订）：<PREV_OPEN_FINDINGS>
（第 1 轮为「无」）。

五视角清单（逐条核对，每条结论都要能指向被核对材料）：
<CHECKLIST_CONTENT>

硬规则：
- 只读：禁止修改任何文件（你的 tools 也没有写权限）；bash 只用于只读查询
  （git log/show/diff、gh 读、sha256sum）。
- 禁止引用任何对话记忆，只信磁盘上的材料。
- 每条发现必须给定位（文件:行号 或 spec 原句）；给不出定位的发现按「待证」处理，
  不计入真缺口。
- 发现编号：R<ROUND_K>-G<n>（真缺口）/ R<ROUND_K>-D<n>（细化）/ R<ROUND_K>-P<n>（核对通过，可省）。
- 每条发现写清：为什么是问题、建议修订、若不复核会在实现阶段付出什么代价。
- 只返回结构化报告，不写文件、不派下级、不发评论。
```

## 注入变量（父负责渲染）

| 占位符 | 来源 |
|---|---|
| `<REPO_ABS_PATH>` | 目标仓库绝对路径（同时作为 subagent 的 cwd） |
| `<ROUND_K>` | `spec-cross-review-state.md`（轮次 k 的唯一权威来源） |
| `<ISSUE_N>` | issue 编号 |
| `<SPEC_ABS_PATH>` | `<issue 目录>/spec.md` 绝对路径 |
| `<EXPECTED_SHA256>` | 父侧 `sha256sum <SPEC_ABS_PATH>` 的输出 |
| `<PREV_OPEN_FINDINGS>` | state 的 Open findings（编号 + 一句话）；第 1 轮填「无」 |
| `<CHECKLIST_CONTENT>` | `references/checklist.md` 全文（父读盘后原样注入） |

## outputSchema（父在派发时传入）

```js
const outputSchema = {
  type: "object",
  required: ["round", "reviewedSha256", "lenses", "findings", "counts", "convergence"],
  properties: {
    round: { type: "integer", minimum: 1 },
    reviewedSha256: { type: "string" },
    lenses: {
      type: "array", minItems: 5, maxItems: 5,
      items: {
        type: "object",
        required: ["lens", "verdict", "findingIds"],
        properties: {
          lens: { enum: ["验收矩阵完备性", "可测性拆分可实现性 + 触发时序", "部署/执行路径真实性", "契约与边界", "命令与命名可追溯"] },
          verdict: { enum: ["核对通过", "有发现"] },
          findingIds: { type: "array", items: { type: "string" } }
        }
      }
    },
    findings: {
      type: "array",
      items: {
        type: "object",
        required: ["id", "level", "location", "why", "suggestion", "costIfSkipped"],
        properties: {
          id: { type: "string" },
          level: { enum: ["真缺口", "细化", "核对通过"] },
          location: { type: "string" },
          why: { type: "string" },
          suggestion: { type: "string" },
          costIfSkipped: { type: "string" }
        }
      }
    },
    counts: {
      type: "object",
      required: ["gaps", "details", "passes"],
      properties: {
        gaps: { type: "integer", minimum: 0 },
        details: { type: "integer", minimum: 0 },
        passes: { type: "integer", minimum: 0 }
      }
    },
    convergence: {
      type: "object",
      required: ["converged", "summary"],
      properties: {
        converged: { type: "boolean" },
        summary: { type: "string" }
      }
    }
  }
};
```

## 回报处置（父）

- `structuredOutput` 缺失或不合 schema → 按「派发失败」处理（见 SKILL.md 失败处理）。
- `reviewedSha256` 必须与父派发时的 `EXPECTED_SHA256` 一致；不一致按 hash 不匹配处理。
- 父据结构化输出写轮次报告第 1–4 段、末尾附 verbatim JSON、更新 state、发 issue 评论。
- `Mode` 由父判定（preflight 结果 + 事后撞真身检查），不由 child 填。

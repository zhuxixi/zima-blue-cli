# Output Examples

本文件包含 [build_review_body.py](../scripts/build_review_body.py) 输出的完整样例，用于 review 评论格式的参考与回归核验。

---

## Round-1：混合 blocking / advisory findings

```markdown
<!-- pi-cr-meta
{"round":1,"pr_number":123,"head_sha":"abc123def4567890123456789012345678901234","previous_head_sha":null,"total_issues":3,"resolved_count":0,"new_count":3,"acknowledged_count":0,"issues":[{"id":"issue-1","description":"Missing error handling for OAuth callback","reason":"bug","file":"src/auth.ts","lines":"67-72","status":"open","first_round":1,"severity":"high","blocking":true},{"id":"issue-2","description":"Inconsistent naming pattern","reason":"AGENTS.md","file":"src/utils.ts","lines":"23-28","status":"open","first_round":1,"severity":"low","blocking":false},{"id":"issue-3","description":"Memory leak: OAuth state not cleaned up","reason":"bug","file":"src/auth.ts","lines":"88-95","status":"open","first_round":1,"severity":"critical","blocking":true}],"timestamp":"2026-04-21T10:00:00Z","blocking_open_count":2,"blocking_new_count":2,"advisory_open_count":1,"advisory_new_count":1}
-->

### Code Review | Round-1

Found 2 blocking issues:

1. Memory leak: OAuth state not cleaned up (bug, critical)

https://github.com/owner/repo/blob/abc123def4567890123456789012345678901234/src/auth.ts#L88-L95

2. Missing error handling for OAuth callback (bug, high)

https://github.com/owner/repo/blob/abc123def4567890123456789012345678901234/src/auth.ts#L67-L72

<details>
<summary>Advisory / non-blocking findings (1)</summary>

1. Inconsistent naming pattern (AGENTS.md, low)

https://github.com/owner/repo/blob/abc123def4567890123456789012345678901234/src/utils.ts#L23-L28

</details>

🤖 Generated with pi-coding-agent
```

> `total_issues=3` / `new_count=3` 保留全部事实；`blocking_open_count=2` / `blocking_new_count=2` 才驱动 fix 与收敛。issue 按 `severity` 降序排列（critical 在前），metadata `issues[]` 保留输入顺序（issue-1/2/3）。

---

## Round-1：仅 advisory findings（不阻塞）

```markdown
<!-- pi-cr-meta
{"round":1,"pr_number":124,"head_sha":"abc123def4567890123456789012345678901234","previous_head_sha":null,"total_issues":1,"resolved_count":0,"new_count":1,"acknowledged_count":0,"issues":[{"id":"issue-1","description":"Inconsistent naming pattern","reason":"AGENTS.md","file":"src/utils.ts","lines":"23-28","status":"open","first_round":1,"severity":"low","blocking":false}],"timestamp":"2026-04-21T10:05:00Z","blocking_open_count":0,"blocking_new_count":0,"advisory_open_count":1,"advisory_new_count":1}
-->

### Code Review | Round-1

No blocking issues found. 1 advisory findings remain.

<details>
<summary>Advisory / non-blocking findings (1)</summary>

1. Inconsistent naming pattern (AGENTS.md, low)

https://github.com/owner/repo/blob/abc123def4567890123456789012345678901234/src/utils.ts#L23-L28

</details>

🤖 Generated with pi-coding-agent
```

> Finding 保持 `status: open`，但 effective `blocking=false`，因此状态报告为 `PASS`、不会触发 fix。此处仅放宽 finding 的 blocking gate；monitor 仍须通过 **multi-flow** 收敛确认、**in-flight** 检查和 **CI** 全绿这三项既有安全门后才能合并。

---

## Round-1：无问题

```markdown
<!-- pi-cr-meta
{"round":1,"pr_number":123,"head_sha":"abc123def4567890123456789012345678901234","previous_head_sha":null,"total_issues":0,"resolved_count":0,"new_count":0,"acknowledged_count":0,"issues":[],"timestamp":"2026-04-21T10:00:00Z","blocking_open_count":0,"blocking_new_count":0,"advisory_open_count":0,"advisory_new_count":0}
-->

### Code Review | Round-1

No issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance.

🤖 Generated with pi-coding-agent
```

---

## Round-2：增量审查（部分问题已修复，部分被 committer 拒绝修复）

```markdown
<!-- pi-cr-meta
{"round":2,"pr_number":123,"head_sha":"fed789abc0123456789012345678901234567890","previous_head_sha":"abc123def4567890123456789012345678901234","total_issues":1,"resolved_count":1,"acknowledged_count":1,"new_count":0,"issues":[{"id":"issue-2","description":"Daemon binds to localhost only, no auth needed","reason":"logic","file":"src/server.py","lines":"45-50","status":"open","first_round":1,"resolution":"acknowledged","committer_note":"daemon binds to localhost only, authentication not needed for local service","severity":"medium","blocking":true},{"id":"issue-3","description":"Memory leak: OAuth state not cleaned up","reason":"bug","file":"src/auth.ts","lines":"88-95","status":"open","first_round":1,"resolution":null,"committer_note":null,"severity":"critical","blocking":true}],"timestamp":"2026-04-21T10:30:00Z","blocking_open_count":1,"blocking_new_count":0,"advisory_open_count":0,"advisory_new_count":0}
-->

### Code Review | Round-2 (Re-check)

Previous Round-1 issues: 3
- **Resolved**: 1 (Missing error handling)
- **Acknowledged / Won't Fix**: 1
- **Still open**: 1 blocking; 0 advisory

New issues found: 0 blocking; 0 advisory

#### Acknowledged / Won't Fix

2. Daemon binds to localhost only, no auth needed (committer: daemon binds to localhost only, authentication not needed for local service)

#### Still Open from Round-1

3. Memory leak: OAuth state not cleaned up (bug, critical)

https://github.com/owner/repo/blob/fed789abc0123456789012345678901234567890/src/auth.ts#L88-L95

🤖 Generated with pi-coding-agent
```

**说明**：
- 如果 `acknowledged_issues` 为空，省略 "Acknowledged / Won't Fix" 小节及其标题
- Acknowledged issues 不计入 "Still open" 数量
- Acknowledged issues 不会触发外部 fix agent 调度；调度器只关注未 acknowledged/wontfix、`status: open` 且 effective `blocking=true` 的 findings

---

## Round-2：carried / new advisory 分开披露

```markdown
<!-- pi-cr-meta
{"round":2,"pr_number":125,"head_sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","previous_head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","total_issues":2,"resolved_count":0,"new_count":1,"acknowledged_count":0,"issues":[{"id":"issue-1","description":"Existing naming inconsistency","reason":"AGENTS.md","file":"src/old.ts","lines":"10-12","status":"open","first_round":1,"severity":"low","blocking":false},{"id":"issue-2","description":"New explanatory comment could be clearer","reason":"docs","file":"src/new.ts","lines":"20-22","status":"open","first_round":2,"severity":"low","blocking":false}],"timestamp":"2026-04-21T10:30:00Z","blocking_open_count":0,"blocking_new_count":0,"advisory_open_count":2,"advisory_new_count":1}
-->

### Code Review | Round-2 (Re-check)

Previous Round-1 issues: 1
- **Resolved**: 0
- **Still open**: 0 blocking; 1 advisory

New issues found: 0 blocking; 1 advisory

No blocking issues remain. Advisory findings remain for visibility.

<details>
<summary>Advisory / non-blocking findings (2)</summary>

#### Carried from previous rounds (1)

1. Existing naming inconsistency (AGENTS.md, low)

https://github.com/owner/repo/blob/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/src/old.ts#L10-L12

#### New this round (1)

1. New explanatory comment could be clearer (docs, low)

https://github.com/owner/repo/blob/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/src/new.ts#L20-L22

</details>

🤖 Generated with pi-coding-agent
```

> Round-N 非空 `issues[]` 是 metadata 与正文共同使用的 canonical current collection；`first_round == round` 的 finding 归入 new，其余归入 carried。这里全量 `new_count=1` 保留本轮 advisory 事实，但 `blocking_new_count=0`，因此不会触发 fix。此处同样只放宽 blocking gate；**multi-flow** 收敛、**in-flight** 检查和 **CI** 全绿仍是合并前置条件。

---

## Round-3：全部修复

```markdown
<!-- pi-cr-meta
{"round":3,"pr_number":123,"head_sha":"aaa111bbb222333444555666777888999000aaaa","previous_head_sha":"fed789abc0123456789012345678901234567890","total_issues":0,"resolved_count":1,"new_count":0,"acknowledged_count":0,"issues":[],"timestamp":"2026-04-21T11:00:00Z","blocking_open_count":0,"blocking_new_count":0,"advisory_open_count":0,"advisory_new_count":0}
-->

### Code Review | Round-3 (Re-check)

Previous Round-2 issues: 1
- **Resolved**: 1 (Memory leak)
- **Still open**: 0 blocking; 0 advisory

New issues found: 0 blocking; 0 advisory

✅ **All issues resolved!**

🤖 Generated with pi-coding-agent
```

---

## 评论格式硬性要求

代码链接必须遵循以下精确格式，否则 GitHub Markdown 无法正确渲染：

```
https://github.com/owner/repo/blob/[full-sha]/path/file.ext#L[start]-L[end]
```

要求：
- 使用完整 SHA（40 字符，**不是缩写**）
- `#L` 表示行号
- 行范围格式：`L[start]-L[end]`
- 至少包含 1 行上下文（评论目标行的前后至少各 1 行）

这些要求由 [build_review_body.py](../scripts/build_review_body.py) 固化，但若手动构建 body 时需自行遵守。

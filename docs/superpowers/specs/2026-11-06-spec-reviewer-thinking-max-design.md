# spec-reviewer 思考档位对齐 CR 决策（max）

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-06T00:20:00+08:00

Issue: #270 · Repo: zhuxixi/zima-blue-cli

## 背景

`pi/agents/spec-reviewer.md:9` 把复核者的思考档位钉在 `high`。本仓另一条 CR 路径（webhook pjob 的 `pi`
agent type）在同职责上用的是最高档 `max`，两处口径不一致，且 `high` 侧没有任何理由记录。

调研取证的结论：**`high` 是写下的，但不是决策出来的。**

| 证据 | 内容 |
|---|---|
| `git log --follow pi/agents/spec-reviewer.md` | 只有一次提交（`b531ad4`，PR #255），`thinking: high` 自文件诞生即存在，无后续修改 |
| PR #255 正文 | 交付物清单写「`thinking: high`，**故意不带 model 字段**」——「故意」修饰的是 model 字段，对 high 本身零解释 |
| `docs/superpowers/specs/2026-10-10-spec-cross-review-automation-design.md` | `grep -c thinking` = 2：`:41` 是 run 产物字段表格行、`:82` 是代码块里的 profile 片段，两处都无档位决策论述 |
| `docs/superpowers/specs/2026-08-11-pi-agent-type-design.md:75`, `:109` | CR 侧既有决策：「需最强思考等级」「**用户明确要 max**」 |
| `examples/webhook/agents/pi.yaml:34` | 同仓 CR 路径实际取值 `thinking: max` |

机制事实（决定改动位置）：`thinking` 在 profile frontmatter 里，优先级高于 `subagents.defaultThinking`；
`agentOverrides.<name>.thinking` 与单次派发的 `model` 后缀（`provider/id:max`）能覆盖它。
所以只改 user settings 的默认值对 `spec-reviewer` 无效，必须改 profile 本身，
或在部署侧永久覆盖——前者才是「仓库自带正确默认」的做法。

机制出处：pi-subagents `docs/models.md`（`defaultThinking` 只填「未声明 thinking 的 agent」；`agentOverrides.<name>.thinking` 覆盖 frontmatter）与 `docs/tool-reference.md`（`model` 上 `:max` 后缀覆盖 agent thinking）。本机实测（2026-11-06）：仅改 frontmatter 后 `subagent({action:"models", agent:"spec-reviewer"})` 返回 `Thinking: max`，而 user settings 未设 `agentOverrides.spec-reviewer.thinking`——证明 frontmatter 的值实际生效。

## 决策

| ID | 决策 | 理由 |
|---|---|---|
| D1 | `pi/agents/spec-reviewer.md:9` 由 `thinking: high` 改为 `thinking: max` | 与 `2026-08-11` CR 决策对齐；仓库自带的 profile 默认值应等于推荐值，而不是留一个需要每台机器手工覆盖的坑 |
| D2 | 同步更新契约测试断言（`tests/unit/test_spec_cross_review_contracts.py:86`） | 该断言目前钉的是 `thinking: high`，不改则改动无法通过测试——它同时充当本次改动的回归锁 |
| D3 | `SKILL.md` 部署前置补一条**前置条件**：复核者模型必须支持 `max` 档 | 换模型是部署侧动作（`agentOverrides.model`）；若新模型 `thinkingLevelMap` 无 `max`，改 profile 后会在派发时才炸。把前提写在部署前置，和 #271 同一类问题 |
| D4 | **非目标**：不改 `model` 字段（保持「模型是部署策略」的既有设计）、不改 spec-cross-review 流程文本、不改 `docs/` 下历史 spec/plan 里记录的 `thinking: high`（历史留档不追写）、不动其他 profile | 控制改动面；历史文档记录的是当时事实 |

D3 的措辞约束：`tests/unit/test_spec_cross_review_contracts.py:361` 禁止 `SKILL_DIR` 下任何文档出现 `~/.pi/` 字面量（`assert "~/.pi/" not in text`），新增前置条件必须沿用既有「用户级 settings.json」写法（见 `SKILL.md:155`），否则 CI 直接红。

## 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | profile 档位为 max | 自动化验证（unit） | `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q` | 全部通过；`TestProfileContract::test_frontmatter_fields` 断言 `thinking: max` |
| A2 | 解析结果确为 max | 自动化验证（static） | `rg -n '^thinking:' pi/` | 唯一命中 `pi/agents/spec-reviewer.md:9` 且值为 `max`；`pi/` 下无 `thinking: high`（`docs/` 历史留档按 D4 不改，不纳入本项） |
| A3 | 部署前置写明 max 前提（失败分支） | 自动化验证（unit） | 同 A1 套件内新增断言：`SKILL.md` 部署前置含复核者模型需支持 `max` 的说明 | 断言通过，防止文档回退 |
| U1 | 真实派发跑在 max 档 | 用户实测 | 合并后在新 session 执行 `subagent({action:"models", agent:"spec-reviewer"})`，再在任一 issue 步 4 跑一轮复核；读 run 目录 `status.json`（本机 `/tmp/pi-subagents-uid-<uid>/async-subagent-runs/<run-id>/status.json`）的 `thinking`，以及 run 产物 `meta.json` 的 `model`（应为 `<provider>/<id>:max`） | `Thinking: max`；`status.json` 的 `thinking` 为 `max`；`meta.json` 的 `model` 带 `:max` 后缀 |

触发时机说明（U1）：`subagent({action:"models"})` 读取的是当前 profile，**必须在新 session 里验证**——
已加载的 session 持有的 agent 定义可能是旧的；run 产物则要等真实一轮复核跑完才有。轮次报告头**不含** Thinking 字段（`references/report-template.md` 头部字段块），不要拿它当证据。

## 可测性拆分

本次改动是纯文本契约，没有可拆的业务逻辑，测试直接用现有 `_read()` + 字符串断言：

- 接缝 1（profile）：`PROFILE` 常量已存在（`tests/unit/test_spec_cross_review_contracts.py:35`），
  `TestProfileContract.profile` fixture 已读取全文 → 只改断言字面量，无需新增 fixture。
- 接缝 2（部署文档）：`SKILL_DIR / "SKILL.md"` 已在 `TestSkillStructure` 使用 → 在既有类里加一条
  断言方法即可，不新建文件。
- 不新增 frontmatter 解析依赖：主包本就依赖 `pyyaml`（`pyproject.toml:30`），但本测试文件的既有断言全部是 `in head` 字面匹配（未 import yaml），
  本次沿用同一风格（`assert "thinking: max" in head`）。

## 代价与风险

1. **成本上升**：JFox 笔记《subagent 的思考等级怎么指定》记录同一「只回一个 ok」任务，
   `max` 输出 1765 token / $0.0030，`low` 输出 208 token / $0.0009；`high` 未测。
   复核每轮输入是长 spec + 真实代码，绝对成本高于该样本，但轮次上限已固定为 4。
2. **首字延迟上升**：max 档思考更久，单轮 wall time 变长。可接受——复核是离线流程，不阻塞用户。
3. **无封顶闸门**：本机未配 `subagents.maxThinking`，改动后没有任何机制阻止更高档；当前
   `max` 已是最高档，故不引入新风险。
4. **回滚方式**：单行 revert（profile + 测试断言成对回退），无数据/迁移副作用。

## 实施范围

- `pi/agents/spec-reviewer.md`（1 行）
- `tests/unit/test_spec_cross_review_contracts.py`（断言更新 + 1 条部署前置断言）
- `pi/spec-cross-review/SKILL.md`（部署前置补 1 条前置条件）
- `CHANGELOG.md` `[Unreleased]` 的 `### Changed` 小节追加一条（现行 Unreleased 段用 `### Changed`，非 `### Changes`）

## 保证边界

- 本 spec 只保证**仓库自带的默认值**是对的；部署侧若在 `~/.pi/agent/settings.json` 里用
  `agentOverrides.spec-reviewer.thinking` 覆盖成别的档位，仓库无能为力——那属于部署策略，
  与 D4 的非目标一致。
- 不保证所有 provider 都支持 `max`：这正是 D3 要把前置条件写进部署文档的原因。

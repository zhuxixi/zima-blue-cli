# Pi 发版 Skill 设计（issue #146）

- **日期**：2026-08-12
- **关联 issue**：[#146](https://github.com/zhuxixi/zima-blue-cli/issues/146)
- **状态**：设计已批准，待用户审 spec

## 背景与目标

zima-blue-cli 的发版流程（bump version → CHANGELOG → PR → GitHub Release → PyPI）在 Claude Code 侧已由 `.claude/skills/release/`（PR #118）实现并经 6 次实战验证。但该目录是 Claude Code 专属，Pi agent 读不到。

**目标**：让 Pi（使用 DeepSeek v4-flash 等低成本模型）也能独立完成发版这种简单任务，降低对高价 Claude 模型的依赖。

## 现状

- Claude 侧 `.claude/skills/release/`：`SKILL.md`（9 步流程）+ `release_helper.py`（纯标准库、agent-agnostic 的 CLI 脚本，处理版本计算 / CHANGELOG / 文件更新）。
- `release_helper.py` 的 `PROJECT_ROOT = Path(__file__).resolve().parents[3]`，基于其所在位置 `.claude/skills/release/` 定位仓库根；脚本位置不变则计算不受影响。
- Pi skill 发现路径含项目级 `.pi/skills/`（项目信任后加载）。当前 `.pi/` 仅有 `worktrees/`，无任何 skill。
- 两侧共同缺口：「PyPI 发布验证」——创建 Release 后无人确认 publish.yml 真把包发上了 PyPI。

## 方案决策

**选定：Pi 专属 SKILL.md + 复用现有脚本**（调研三选一中的选项 1）。

理由：
1. Claude 侧零改动——不碰在用的 skill，降低风险。
2. `release_helper.py` 是纯标准库、agent-agnostic，任何 agent 用 `uv run python` 即可调用，无需重写或复制（避免双份同步维护）。
3. Pi 拿到独立、干净的 SKILL.md，能补上 PyPI 验证缺口、去掉 Claude 水印。

否决方案：
- **挂载复用**（`.pi/settings.json` 指向 `.claude/skills`）：最省事，但用 Claude SKILL.md 原样，水印与 PyPI 缺口都解决不了（改就得动 Claude 在用的那份）。
- **完全独立**（复制脚本到 `.pi/`）：解耦但脚本两份、需同步维护。

## 架构与组件

```
zima-blue-cli/
├── .claude/skills/release/        # 不改动
│   ├── SKILL.md                   # Claude 用（不动）
│   └── release_helper.py          # Pi 复用（不动）
├── .pi/
│   └── skills/release/            # 新增
│       └── SKILL.md               # Pi 专属（本次唯一交付物）
└── ...
```

- **新增**：`.pi/skills/release/SKILL.md`
- **复用（只读调用）**：`.claude/skills/release/release_helper.py`
- **改动**：无（Claude 侧、脚本、pyproject、workflow 都不动）

### 关于 skill name 冲突
Pi skill name 用 `release`。Claude 的 release skill 不在 Pi 发现路径（Pi 不读 `.claude/`），全局 Pi skills（`~/.pi/agent/skills/`、`~/.agents/skills/`）也无同名，故 `.pi/skills/release` 对 Pi 无冲突。

## SKILL.md 详细设计

### Frontmatter
```yaml
---
name: release
description: Release a new version of zima-blue-cli. Bumps version, generates CHANGELOG, creates PR and GitHub Release, verifies PyPI publish. Triggers on "发版", "release", "bump version", "发布版本".
---
```

### 流程（10 步；基于 Claude 的 9 步，去水印 + 新增 Step 10 PyPI 验证）

**Step 1 · 前置校验**（任一失败→停止报原因）
- 当前分支 == main：`git branch --show-current`
- 工作区干净：`git status --porcelain` 为空
- 无未合并 bump 分支：`git branch --list 'chore/bump-*'` 为空
- 无未合并 bump PR：`gh pr list --state open --head 'chore/bump-*'` 为空

**Step 2 · dry-run 预览**
- `uv run python .claude/skills/release/release_helper.py <version> --dry-run`
- 解析 JSON：`current_version` / `new_version` / `changelog_preview` / `changelog_summary`

**Step 3 · 展示摘要 + 等用户确认**
- 展示当前→新版本、变更摘要、CHANGELOG 预览、将修改文件（pyproject.toml / uv.lock / CHANGELOG.md）
- **必须等用户明确确认**才继续

**Step 4 · 正式运行脚本**
- `uv run python .claude/skills/release/release_helper.py <version>`
- 退出码非 0 → 读错误 JSON、停止

**Step 5 · git 操作**（发版 skill 的功能逻辑，在 main 干净态建 bump 分支）
- `git checkout -b chore/bump-version-<new_version>`
- `git add pyproject.toml uv.lock CHANGELOG.md`
- `git commit -m "chore: bump version to <new_version>"`
- `git push -u origin chore/bump-version-<new_version>`

**Step 6 · 创建 PR**
- `gh pr create --title "chore: bump version to <new_version>" --body "<changelog>"`
- **PR body 去掉 `🤖 Generated with Claude Code` 水印**，仅含 changelog，不强调具体 agent

**Step 7 · 等用户合并**
- 告知 PR URL，等用户确认已合并

**Step 8 · 切回 main 并 pull**
- `git checkout main && git pull origin main`

**Step 9 · 创建 GitHub Release**（触发 publish.yml）
- `gh release create v<new_version> --title "v<new_version>" --notes "<changelog>"`

**Step 10 · PyPI 发布验证（新增）**
- 监控 publish.yml：`gh run list --workflow=publish.yml --limit 1 --json databaseId,status,conclusion` 拿最新 run；轮询 `gh run view <id> --json status,conclusion` 至 `status=completed`（超时上限 10 分钟）
- 查 PyPI：轮询 `curl -fsSL https://pypi.org/pypi/zima-blue-cli/json | jq -r '.info.version'`，确认 == new_version（PyPI 有缓存延迟，重试间隔 15s、上限 5 分钟）
- workflow failure 或 PyPI 超时未出现 → 报错、停止，提示人工排查

### 触发与调用
- `/skill:release patch` / `0.6.1` / `minor` / `major`
- 自然语言"发版"、"bump version"等（description 触发词匹配）
- 参数透传给 release_helper.py

### 关键 gate（不可省）
- Step 3（预览确认）、Step 7（合并确认）必须人工确认——发版不可逆。

## 脚本调用契约

- **路径**：仓库根相对 `.claude/skills/release/release_helper.py`（Pi 执行时 cwd = 仓库根）
- **输入**：位置参数 `<version | patch | minor | major>`，可选 `--dry-run`
- **输出**：JSON（`current_version` / `new_version` / `changelog_preview` / `changelog_summary` / `files_modified`；错误时 `{error: ...}` 且退出码 1）
- **副作用（非 dry-run）**：改 pyproject.toml、跑 `uv lock`、更新 CHANGELOG.md
- Pi 仅依赖脚本位置稳定性这一条契约——`.claude/skills/release/` 长期稳定。

## 错误处理 / 降级
- 脚本退出码非 0 → 展示错误 JSON，停止
- git / PR / Release 失败 → 展示错误，建议手动修复
- PyPI 验证超时 / workflow 失败 → 不回滚 Release（已不可逆），报错提示人工查 Actions / PyPI

## 非目标（YAGNI）
- 不重写或移动 `release_helper.py`
- 不改 Claude 的 SKILL.md
- 不做多组件 release-all（issue 明确单组件）
- 不把脚本提到共享 `scripts/` 位置（未来可选，本次不做）

## 验收标准（对应 issue）
- [ ] `.pi/skills/release/SKILL.md` 存在，Pi 能发现（`/skill:release` 可用）
- [ ] Pi 下 `uv run python .claude/skills/release/release_helper.py patch --dry-run` 跑通、JSON 正确（跨目录调用路径验证）
- [ ] SKILL.md 含完整 10 步（含 PyPI 验证）
- [ ] PR body 无 Claude 水印
- [ ] 真实发版一次端到端走完（含 PyPI 上线确认）

## 风险与缓解
| 风险 | 缓解 |
|---|---|
| Pi skill 跨目录引用 `.claude/` 下脚本，Claude 重构会断 | SKILL.md 注明依赖路径；脚本位置长期稳定；未来可提共享位置 |
| workflow 监控在 agent 环境阻塞 | 用 `gh run view --json` 轮询 + 超时上限，不用阻塞式 `gh run watch` |
| PyPI 缓存延迟导致误判失败 | 轮询重试（15s 间隔、5 分钟上限） |

## 与 Claude 侧的关系
- 不改动 Claude 的 `.claude/skills/release/`
- 两套 SKILL.md（Claude 9 步、Pi 10 步）并存，脚本共用一份
- 未来若想让两侧流程统一（都含 PyPI 验证），另开 issue 改 Claude 侧——本次不做

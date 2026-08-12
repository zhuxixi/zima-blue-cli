# Pi Release Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Pi agent 能独立发版 zima-blue-cli——新增 `.pi/skills/release/SKILL.md`，复用既有 `release_helper.py`，补上 PyPI 发布验证。

**Architecture:** 单文件交付（`.pi/skills/release/SKILL.md`），调用既有 `.claude/skills/release/release_helper.py`（不改）。基于 Claude 的 9 步流程扩展为 10 步（去 Claude 水印 + 新增 Step 10 PyPI 验证）。

**Tech Stack:** Pi skill（SKILL.md frontmatter）、bash / gh / uv / curl / jq 命令、`release_helper.py`（纯 stdlib）。

## Global Constraints

- 不改动 `.claude/skills/release/`（Claude 侧零改动）
- 不重写或移动 `release_helper.py`
- SKILL.md 调用脚本用仓库根相对路径：`uv run python .claude/skills/release/release_helper.py ...`
- PR body / Release notes **不含** `🤖 Generated with Claude Code` 水印
- 关键 gate（Step 3 预览确认、Step 7 合并确认）必须人工确认，不可自动跳过
- 发版不可逆；PyPI 验证失败不回滚，只报错

## File Structure

- **Create**: `.pi/skills/release/SKILL.md`（唯一交付物）
- **复用（不改）**: `.claude/skills/release/release_helper.py`（CLI：`<version|patch|minor|major> [--dry-run]`，输出 JSON）

---

### Task 1: 创建 Pi release SKILL.md

**Files:**
- Create: `.pi/skills/release/SKILL.md`

**Interfaces:**
- Consumes: `.claude/skills/release/release_helper.py`（输入 `<version|patch|minor|major>` + 可选 `--dry-run`；输出 JSON `current_version`/`new_version`/`changelog_preview`/`changelog_summary`/`files_modified`，错误时 `{error}` + 退出码 1）
- Produces: Pi 可发现的 `/skill:release` 命令（项目级 `.pi/skills/release/`）

- [ ] **Step 1: 创建目录**

```bash
mkdir -p .pi/skills/release
```

- [ ] **Step 2: 写 SKILL.md（完整内容如下）**

创建 `.pi/skills/release/SKILL.md`，内容：

````markdown
---
name: release
description: Release a new version of zima-blue-cli. Bumps version, generates CHANGELOG, creates PR and GitHub Release, and verifies the PyPI publish. Triggers on "发版", "release", "bump version", "发布版本".
---

# Release Skill (Pi)

将 zima-blue-cli 发版流程从多步手动操作简化为一条命令。覆盖版本 bump → CHANGELOG → PR → GitHub Release → PyPI 验证。复用 `.claude/skills/release/release_helper.py`（agent-agnostic 脚本，不重写）。

## 用法

```
/skill:release 0.7.0      # 指定具体版本号
/skill:release patch      # bump patch: 0.6.0 → 0.6.1
/skill:release minor      # bump minor: 0.6.0 → 0.7.0
/skill:release major      # bump major: 0.6.0 → 1.0.0
```

## 执行流程

严格按步骤执行，每一步完成后再进入下一步。

### Step 1: 前置校验

任一项失败立即停止并告知用户原因：

```bash
git branch --show-current          # 期望 main
git status --porcelain             # 期望空
git branch --list 'chore/bump-*'   # 期望空
gh pr list --state open --head "chore/bump-*"  # 期望空
```

### Step 2: dry-run 预览

```bash
uv run python .claude/skills/release/release_helper.py <version> --dry-run
```

解析 JSON，提取 `current_version`、`new_version`、`changelog_preview`、`changelog_summary`。

### Step 3: 展示变更摘要并等待确认

向用户展示：

```
📦 Release 预览:
  当前版本: {current_version}
  新版本号: {new_version}
  变更摘要: {changelog_summary}

CHANGELOG 预览:
{changelog_preview}

将修改的文件:
  - pyproject.toml
  - uv.lock
  - CHANGELOG.md
```

**必须等待用户明确确认后才继续。** 用户拒绝或要求修改则停止。

### Step 4: 正式运行脚本

```bash
uv run python .claude/skills/release/release_helper.py <version>
```

退出码非 0 → 读错误 JSON，告知用户，停止流程。

### Step 5: Git 操作

```bash
git checkout -b chore/bump-version-{new_version}
git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "chore: bump version to {new_version}"
git push -u origin chore/bump-version-{new_version}
```

### Step 6: 创建 PR

```bash
gh pr create \
  --title "chore: bump version to {new_version}" \
  --body "$(cat <<'EOF'
## Summary
Bump version from {current_version} to {new_version}

{changelog_preview}
EOF
)"
```

记录返回的 PR URL。PR body 不加 agent 水印。

### Step 7: 等待合并

告知用户：

```
PR 已创建: {PR_URL}
请合并此 PR 后告知我，我将继续创建 GitHub Release 并验证 PyPI 发布。
```

等待用户确认 PR 已合并。

### Step 8: 切回 main 并拉取最新

```bash
git checkout main
git pull origin main
```

### Step 9: 创建 GitHub Release

```bash
gh release create v{new_version} \
  --title "v{new_version}" \
  --notes "$(cat <<'EOF'
{changelog_preview}
EOF
)"
```

Release 创建后会触发 `.github/workflows/publish.yml` 自动发布到 PyPI。

### Step 10: 验证 PyPI 发布

**(a) 监控 publish workflow** —— 创建 Release 后轮询 publish.yml 直到完成（超时上限 10 分钟）：

```bash
RUN_ID=$(gh run list --workflow=publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN_ID" --json status,conclusion
```

`status=completed` 且 `conclusion=success` → 进入 (b)；`conclusion=failure` → 报错停止，提示用户查 Actions。

**(b) 确认 PyPI 上线** —— PyPI 有缓存延迟，轮询重试（间隔 15s、上限 5 分钟）：

```bash
curl -fsSL https://pypi.org/pypi/zima-blue-cli/json | jq -r '.info.version'
```

返回 == `{new_version}` 即成功。超时未出现 → 报错，提示人工查 PyPI。

成功后告知用户：

```
✅ Release v{new_version} 已发布并上线 PyPI。
```

## 错误处理

- 脚本非零退出码 → 读错误 JSON，展示，停止
- git 操作失败 → 展示错误，建议手动修复
- PR 创建失败 → 检查同名 PR / 权限
- Release 创建失败 → 检查 tag 是否已存在
- publish workflow failure → 报错，提示查 Actions
- PyPI 超时未上线 → 报错，提示查 PyPI（不回滚 Release，已不可逆）

## 注意事项

- 不使用 `--no-verify`，保持 pre-commit hook
- 始终在新分支操作，不直接改 main
- 每个确认点（Step 3、Step 7）必须等待，不自动跳过
- 发版不可逆；PyPI 验证失败不回滚，只报错提示人工
- 复用脚本位于 `.claude/skills/release/release_helper.py`（长期稳定，勿移动）
````

- [ ] **Step 3: 验证 frontmatter 合规**

确认 `name: release`（≤64 字符、小写+连字符、合规）、`description`（≤1024 字符、含触发词"发版"/"release"/"bump version"/"发布版本"）。Pi 加载时无 validation warning。

- [ ] **Step 4: 验证脚本路径可调（dry-run）**

```bash
uv run python .claude/skills/release/release_helper.py patch --dry-run
```

期望：输出 JSON，含 `current_version`、`new_version`、`changelog_preview`，无 `error` 字段。这验证 SKILL.md 里写的跨目录脚本路径正确。

- [ ] **Step 5: 验证内容完整性**

逐项核对 SKILL.md：
- 含 10 步流程（确认 Step 10 PyPI 验证存在）
- Step 6 的 PR body 模板**无** `🤖 Generated with Claude Code` 水印
- frontmatter 触发词齐全
- Step 3、Step 7 有"必须等待用户确认"的 gate 语句

- [ ] **Step 6: Commit**

```bash
git add .pi/skills/release/SKILL.md
git commit -m "feat(skill): add pi release skill for #146"
```

---

## Self-Review（plan 作者自检）

- **Spec coverage**：spec 的交付物（.pi/skills/release/SKILL.md）→ Task 1 Step 2；脚本路径契约 → Step 4 验证；去水印 → Step 5 验证；PyPI 验证 → Step 2 内容的 Step 10 + Step 5 核对；验收"Pi 能发现 skill"→ Step 3 frontmatter 合规。全覆盖。
- **Placeholder scan**：SKILL.md 内容完整给出，无 TBD/TODO。`{new_version}` 等是流程占位（运行时由脚本输出填入），非 plan 占位。
- **Type consistency**：脚本输入输出契约（Task 1 Interfaces）与 SKILL.md Step 2/4 的调用一致。

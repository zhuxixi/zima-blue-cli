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

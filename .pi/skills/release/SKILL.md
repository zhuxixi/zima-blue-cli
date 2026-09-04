---
name: release
description: Release a new version of zima-blue-cli. Bumps version, generates CHANGELOG, creates PR and GitHub Release, verifies the PyPI publish, and upgrades and restarts the local service. Triggers on "发版", "release", "bump version", "发布版本".
---

# Release Skill (Pi)

将 zima-blue-cli 发版流程从多步手动操作简化为一条命令。覆盖版本 bump → CHANGELOG → PR → GitHub Release → PyPI 验证 → 本机服务升级重启。复用 `.claude/skills/release/release_helper.py`（agent-agnostic 脚本，不重写）。

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

成功后进入 Step 11（本机服务升级与重启）。

### Step 11: 本机服务升级与重启（发版闭环）

PyPI 验证通过后，更新本机安装并重启常驻服务，让新版本立即生效。
仅当发版机运行着 zima 服务时执行；纯 CI / 无本机服务的环境跳过本步。

**(a) 更新本机安装**

```bash
uv tool update zima-blue-cli
```

**(b) 排空 in-flight PJob（必须）**

systemd restart 默认 KillMode=control-group，会连坐 cgroup 内正在执行的
CR PJob（单轮约 8-10 分钟）。重启前必须等运行中的 CR job 结束：

```bash
pgrep -f "[z]ima.execution.background_runner" || echo "no inflight"
```

有输出（存在 in-flight）则每 30s 轮询一次直至进程消失；超时上限 15 分钟。
超时仍忙 → 询问用户：继续重启（会中断该 CR job）或放弃本轮（服务跑旧版，下次手动重启）。

**(c) 重启 webhook-server**

```bash
systemctl --user restart zima-webhook
systemctl --user is-active zima-webhook   # 期望 active
journalctl --user -u zima-webhook --since "<重启时刻>" --no-pager | tail -8
```

验证：日志含 `Connected to smee.io` 与 `Webhook server listening`。
注：smee DNS 抖动为已知自愈项（重启后 ~10 分钟内自动恢复），此时缺
`Connected to smee.io` 仅作 warning，不算失败。

restart 前复查一次 `pgrep -f "[z]ima.execution.background_runner"`——排空后到
重启前的小窗口内新触发的事件（若 spawn 了新 CR job）等它跑完再 restart。

**(d) 重启 daemon（如本机在跑）**

```bash
~/.local/bin/zima daemon status
```

- 显示 running：从输出/`ps` 记录当前 schedule 名，然后

```bash
~/.local/bin/zima daemon stop && ~/.local/bin/zima daemon start --schedule <schedule>
```

验证：`~/.local/bin/zima daemon status` 显示 running。

- 显示 not running 但 `ps` 里存在进程（游离态，daemon.pid 丢失）：
  先 `kill <PID>` 再用上面同款 `zima daemon start --schedule <schedule>` 正规拉起。
- 本机未跑 daemon：跳过。

**(e) 版本确认与收尾**

```bash
zima --version   # 期望 == {new_version}
```

全部通过后告知用户：

```
✅ Release v{new_version} 已发布、上线 PyPI，本机服务已升级重启至新版本。
```

## 错误处理

- 脚本非零退出码 → 读错误 JSON，展示，停止
- git 操作失败 → 展示错误，建议手动修复
- PR 创建失败 → 检查同名 PR / 权限
- Release 创建失败 → 检查 tag 是否已存在
- publish workflow failure → 报错，提示查 Actions
- PyPI 超时未上线 → 报错，提示查 PyPI（不回滚 Release，已不可逆）
- Step 11 排空超时 → 询问用户继续（中断 in-flight）或放弃本轮
- Step 11 任一步失败 → 展示错误并停止，不自动回滚；人工回滚路径：
  `uv tool install zima-blue-cli==<old> && systemctl --user restart zima-webhook`，
  daemon 同步 stop/start；注意 `==<old>` 会钉住版本，恢复自动升级需
  `uv tool install --upgrade zima-blue-cli==<new>`

## 注意事项

- 不使用 `--no-verify`，保持 pre-commit hook
- 始终在新分支操作，不直接改 main
- 每个确认点（Step 3、Step 7）必须等待，不自动跳过
- 发版不可逆；PyPI 验证失败不回滚，只报错提示人工
- 复用脚本位于 `.claude/skills/release/release_helper.py`（长期稳定，勿移动）
- Step 11 的 systemd user service（`zima-webhook.service`）形态是本机部署事实，
  非产品默认；非 systemd 部署的机器按实际方式重启
- daemon 的 schedule 名机器相关（如 cosmobo），从 status/ps 读取，不硬编码

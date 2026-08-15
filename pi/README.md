# Zima Blue Pi Skills

zima-blue-cli 仓库的 pi 技能包：GitHub issue-driven 研发闭环（issue → 调研 → 设计 → 实现 → Zima 双 Bot CR → 合并）。

## 技能列表

| 技能 | 角色 | 对应流程步 |
|------|------|-----------|
| `github-issue-driven` | 10 步闭环主流程 | 全部 |
| `issue-research` | 调研（JFox KB + git + 过往 issue/PR） | 步 3 |
| `zima-pr-monitor` | PR 监听（双 bot 收敛判定 + 合并） | 步 8-9 |

## 安装

本地路径（开发期，改仓库即时生效，同 jfox 模式）：

```json
// ~/.pi/agent/settings.json
{ "packages": ["/home/elling/git-repo/github/zima-blue-cli"] }
```

或 `pi install /home/elling/git-repo/github/zima-blue-cli`。

发布后可按 git tag 安装：`pi install git:github.com/zhuxixi/zima-blue-cli@vX.Y.Z`。

## 前置依赖

- `gh` CLI（已登录）
- `jfox` CLI（调研中枢，JFox 知识库）
- superpowers pi package（提供 `brainstorming` / `systematic-debugging` / `writing-plans` / `subagent-driven-development` / `requesting-code-review` 技能）

## 注意

- 若全局 `~/.agents/skills/`（或 `~/.pi/agent/skills/`）下还有同名旧技能，pi 会优先加载全局版、本包版本被遮蔽——迁移完成后应移除旧版，让本包成为唯一来源。
- worktree 路径约定为 `<repo>/.pi/worktrees/`（已加入本仓库 .gitignore；其他仓库需自行 ignore）。

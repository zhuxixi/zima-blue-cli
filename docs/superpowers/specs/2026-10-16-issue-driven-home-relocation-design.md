# Spec — Issue #259：调研/spec 留档目录从 `~/.claude/github-issue-driven/` 迁到 `~/.github-issue-driven/`

- 状态：**v5（三轮复核收敛 + 用户已确认设计；步 5 转正为 worktree 内的首个 commit）**
- Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T08:56:48+08:00
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:21:39+08:00（第 1 轮 2 真缺口 + 5 细化的处置见 §11）
- 日期：2026-10-16 · 仓库基线：`main`（本仓）
- 上游 issue：zhuxixi/zima-blue-cli#259（refactor / skill）
- 调研存档：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-259/research/`（01 现状机制盘点 / 02 设计史与外部先例 / 03 迁移与兼容方案）
- 命名合规：无新增 skill / agent 名；新增脚本与测试文件名沿用仓内 kebab-case snake_case 约定

---

## 1. 背景与问题

`github-issue-driven` 流程的调研与 spec 留档固定落在 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/`。该路径是 Claude Code 时代的既成事实，pi 技能包在 2026-08-15（#152）迁移时以「跨 harness 共用同一份调研」为由显式保留（KB `202608152307247296`）。

问题不在「共享」，而在**共享位置寄生在另一个工具的配置根目录**：

1. **命名空间越界**：pi 会话的产物写进 Claude Code 的 home（该目录含 `.credentials.json`）。pi-only 用户（装了本包、没装 Claude Code）也会被凭空创建 `~/.claude`。
2. **生命周期错配**：留档按纪律「不清理、长期保留」（调研时点 2026-10-16 实测 590 文件 / 7.4 MB / 10 个 `<owner>/<repo>`；该目录持续增长——本 issue 的调研与复核留痕正写入其中），却位于最容易被工具自身重置、迁移、清理的位置。
3. **契约自相矛盾**：`tests/unit/test_spec_cross_review_contracts.py:359` 已立规「skill 文档不得引用机器私有配置」（禁 `~/.pi/`），却让 `~/.claude/` 大摇大摆留在同一批文档里（11 处）。

同向先例有两条：scan2book 项目级 skill 从 `.claude/skills/` 迁到 `.agents/skills/`（KB `202608152309386360`，理由「目录名有误导性」）；#250 契约 A3 的「不得引用机器私有配置」。

## 2. 目标

1. 留档目录默认值迁到 `~/.github-issue-driven/`，**目录名 `github-issue-driven` 保持不变**（跨仓库消费方正则依赖）。
2. 引入三层解析规则（env → 新默认 → 迁移前旧路径），旧路径以符号链接兜底，使历史引用与 CC 侧流程无感。
3. 提供幂等、可测的一次性迁移脚本，并把「文档不得引用 harness 私有目录」扩成自动化契约。

## 3. 非目标

1. **不改留档策略本身**：仍是全局约定目录、不进项目目录、不清理、跨 harness 共享。
2. **不改写历史文档**：`docs/superpowers/**` 中 32 处旧路径引用（zima 23 / jfox 9）是历史留痕，不追改；由符号链接保活。
3. **不改 CC 侧两份手工拷贝**（`~/.claude/skills/github-issue-driven/`、`~/.claude/skills/issue-research/`）：仓库外文件、内容已与 pi 版分叉；符号链接足以让它们继续工作。作为独立 follow-up 处理。
4. **不改 pi-auto-rename 的测试 fixture**（跨仓库）：其 `RE_DRIVEN_PATH` 正则只匹配 `github-issue-driven/<owner>/<repo>/issue-<N>/` 后缀，改父目录不影响行为；fixture 中的旧字面量属另一仓库的清理项。
5. 不引入自动归档 / 自动清理 / 搬迁以外的目录结构变更。

## 4. 关键事实依据（调研对齐）

- 硬约束：`pi-auto-rename/lib/auto-rename-core.ts:624` 的 `RE_DRIVEN_PATH` 只认目录名后缀 → 目录名不可改（R1）。
- 迁移是同一文件系统内的 rename（`/dev/mapper/ubuntu--vg-ubuntu--lv`）→ 毫秒级、原子、无跨设备拷贝风险（R3）。
- 旧路径的存活消费者：历史文档 32 处引用、CC 侧 skill 拷贝（CC transcript 149 文件引用，最近 2026-10-15）、pi-auto-rename（R1）。
- 现成验收面：`test_no_hardcoded_machine_private_config_reference` 已存在同形断言，可直接扩展（R1）。
- 本机有两份同源 checkout（`zima-blue-cli`、`zima-blue-cli-mdbot`）→ 脚本必须幂等（R1）。

## 5. 设计

### D1 · 新默认路径

- 新默认：`~/.github-issue-driven/`（保留末尾目录名 `github-issue-driven`）。
- 备选 A（未采纳）：`~/.local/share/github-issue-driven/`（XDG 语义更正，但本机无其它 XDG 使用者、路径更长）。**采纳理由**：与本机 `~/.zima` / `~/.pi` / `~/.agents` 的「一个约定一个 `~/.<name>`」风格一致，且最短路径便于在 skill 文档里反复出现。
- 不论选哪个，本 spec 的三层解析、迁移脚本、契约测试设计不变（路径常量集中一处）。

### D2 · 目录解析规则（skill 文档中的定稿文本）

```text
留档目录解析（研究 / spec / 复核留痕统一规则）：
1. `$GITHUB_ISSUE_DRIVEN_HOME` 非空 → 用它；
2. 否则用 `~/.github-issue-driven/`；
3. 若默认目录不存在、而本机仍留有迁移前的旧路径，先做一次性迁移——在**本技能包仓库
   （zima-blue-cli）的主 checkout** 内执行 `python scripts/migrate_issue_driven_home.py`；
   同一 issue 的产物禁止写到两处。
```

（脚本路径按**包**定位而非按 cwd：被本 skill 治理的其余 9 个 `owner/repo` 会话与任一 worktree 里都不存在该脚本——R1-G1。）

- 定稿文本写入 `pi/github-issue-driven/SKILL.md` 的「关键纪律」区；`issue-research` 与 `spec-cross-review` 引用同名规则，不复制第二份全文（沿用 #250「单一定义源」纪律）。
- 规则文本中**不出现** `~/.claude` 字面量（旧路径只以「迁移前的旧路径」指代，唯一权威定义在脚本里）。

### D3 · 兼容：旧路径符号链接

- 迁移后旧路径留符号链接（`~/.claude/github-issue-driven` → `~/.github-issue-driven`），使历史文档引用、CC 侧 skill 拷贝、pi-auto-rename 无需任何改动即可继续工作。
- 文档必须写明删除语义的坑：**删旧路径用 `unlink`，禁止 `rm -rf <dir>/`（带斜杠会穿透符号链接删真实数据）**。该句写入迁移脚本的 `--help` 与执行后输出（**验收归属：A2 文案断言 + A3 `--help` 断言**——它是 §8.3 两条缓解里唯一可自动验证的一条，不能无 ID 认领）。
- 符号链接存在时不重复迁移（见 D4 决策表）。

### D4 · 迁移脚本 `scripts/migrate_issue_driven_home.py`

- 形态：Python 脚本（仓内 `scripts/` 既有约定；**选 Python 而非 bash 的原因是决策逻辑要能被 pytest 直接 import 做纯函数测试**）。
- 决策表（纯函数 `resolve_action(legacy_state, new_state) -> Action`，`legacy_state` / `new_state` ∈ {`absent`, `dir`, `symlink_to_new`, `symlink_other`}）：

| legacy | new | Action | 行为 |
|--------|-----|--------|------|
| `absent` | `absent` | `noop_fresh` | 全新环境，无动作（退出码 0） |
| `absent` | `dir` | `noop_migrated` | 已迁移，无动作（0） |
| `dir` | `absent` | `migrate` | `mv` 旧 → 新，再建符号链接（0） |
| `dir` | `dir` | `conflict` | 两侧都有真实目录 → 报错退出（非 0），不自动合并 |
| `symlink_to_new` | `dir` | `noop_migrated` | 已迁移（0） |
| `symlink_to_new` | `absent` | `conflict` | 悬空链接 → 报错退出（非 0） |
| `symlink_other` | 任意（4 格） | `conflict` | 旧路径被指向别处 → 报错退出（非 0） |
| 未列出的组合（6 格） | 未列出的组合 | `conflict` | **保守兜底**：一律报错退出（非 0），不猜、不动数据 |

状态空间 4×4 = 16 格，上表显式定义 6 格 + `symlink_other` 行 4 格 = 10 格，余 6 格由兜底行接管。纯函数必须对全部输入有确定返回，**不允许抛未捕获异常**。

- `--dry-run`：只打印将要执行的动作与源/目标路径，不做任何写操作。
- 幂等：连续执行两次，第二次为 `noop_migrated`（0）。
- 输出契约（供人工与测试核对）：第一行 `<action>: <legacy> -> <new>`；迁移后打印文件数与「删除旧路径请用 `unlink`」提示。
- 环境变量 `GITHUB_ISSUE_DRIVEN_HOME` 非空时脚本以它为 `new`（与 D2 一致），避免脚本与 skill 规则出现两套口径；**验收归属：A2 的 `resolve_home` 断言 + A3 的 env 覆盖集成用例**（否则该分支可硬编码新路径而全绿——R2-G1）。

### D5 · 文档改造点（逐文件）

| 文件 | 位置 | 改动 |
|------|------|------|
| `pi/github-issue-driven/SKILL.md` | L19、L20、L28、L46、L60、L66、L70 | 路径 → `~/.github-issue-driven/`；L46 的裸 `~/.claude` 一并改；「关键纪律」区插入 D2 定稿文本 |
| `pi/issue-research/SKILL.md` | L25、L33 | 路径 → `~/.github-issue-driven/`；L33 的「一定放 `~/.claude/...`」改为「一定放留档目录（见 github-issue-driven 步 3 的解析规则）」 |
| `pi/spec-cross-review/SKILL.md` | L29、L123 | 留痕目录 → `~/.github-issue-driven/...`（目录树示意同步） |
| `pi/README.md` | 「注意」区 | 加一行：留档目录默认 `~/.github-issue-driven/`（可用 `GITHUB_ISSUE_DRIVEN_HOME` 覆盖；迁移用 `scripts/migrate_issue_driven_home.py`） |

口径校验（A1 命令同时覆盖）：`rg -n --glob '*.md' "~/\.claude" pi/` 必须**零命中**（含裸 `~/.claude`，不能只查全路径）。**扫描面（实测 rg 14.1.0，第 3 轮修正）**：`pi/.ignore` 内容为 `README.md`，纯目录参数形式（`rg <pat> pi/`）会跳过 `pi/README.md`；带 `--glob '*.md'` 后白名单覆盖 `.ignore`，README 重新进入扫描面；显式文件参数（`rg <pat> pi/README.md`）也不受 `.ignore` 影响。因此 `--glob '*.md'` 是必需项，**`--no-ignore` 非必需**（第 2 轮曾误标为必须，第 3 轮实测证伪，R3-D1）。

### D6 · 契约与测试

新增三个测试文件（2 unit + 1 integration）；不改既有契约测试的断言（`tests/unit/test_spec_cross_review_contracts.py` 由 **#254** 引入——避免动别人的契约）：

1. `tests/unit/test_issue_driven_home_contracts.py`
   - `test_no_claude_home_reference`：`pi/**/*.md` 全文不含 `~/.claude`。
   - `test_new_home_documented`：`~/.github-issue-driven` 同时出现在 `pi/github-issue-driven/SKILL.md`、`pi/issue-research/SKILL.md`、`pi/spec-cross-review/SKILL.md`。
   - `test_env_override_documented`：`GITHUB_ISSUE_DRIVEN_HOME` 出现在 `pi/github-issue-driven/SKILL.md`。
   - `test_readme_documents_home`：`~/.github-issue-driven` 出现在 `pi/README.md`——D5 四个文档改动点里唯一没有正向断言的（忘加该行 A1–A5 仍全绿），补上（R3-D4）。
   - `test_legacy_path_defined_once`：**口径固定为两半**——`pi/**/*.md` 零出现 + `scripts/migrate_issue_driven_home.py` 内至少出现 1 次。**不做全仓唯一性断言**（`docs/superpowers/**` 历史文档按非目标 2 保留旧字面量、`tests/**` 夹具也需要它，豁免口径同 A4）。
2. `tests/unit/test_migrate_issue_driven_home.py`：决策表 16 格全覆盖（7 行展开 + 兜底行）+ `describe_action` 文案（含 `unlink` 警告句）。
3. `tests/integration/test_migrate_issue_driven_home.py`：tmp HOME 下跑真实脚本（`uv run python scripts/migrate_issue_driven_home.py`），场景**点名为四态**——`migrate`（旧有新无）、`noop_migrated`（旧是新目录的符号链接）、`noop_fresh`（两侧皆无）、`conflict`（两侧皆有真实目录；断言非 0 退出且**不移动文件、不建符号链接**）；另加幂等（连跑两次第二次为 `noop_migrated`）、`--dry-run` 无副作用（文件系统快照不变）、env 覆盖、`--help` 含 `unlink` 警告句。

### D7 · 存量数据迁移（本地一次性，非仓库产物）

在本机执行一次，并按文件数 / 目录数对账后记录到 issue：

**执行目录**：脚本在 PR 合并前进不了 `main`，因此 D7 与 U2 都在 **issue worktree**（脚本所在 checkout）内执行。

```bash
python scripts/migrate_issue_driven_home.py --dry-run   # 预期 migrate
python scripts/migrate_issue_driven_home.py             # 执行
python scripts/migrate_issue_driven_home.py             # 预期 noop_migrated（幂等验证）
ls -la ~/.github-issue-driven | head
readlink ~/.claude/github-issue-driven                  # 预期指向新目录
```

对账口径（**集合对账，不做严格计数相等**）：该目录被活跃会话持续写入（本条 issue 的调研与复核留痕就在其中），两次 `find | wc -l` 之间任何落盘都会使严格相等断裂。改为：迁移前 `find <legacy> -type f | sed "s|^<legacy>/||" | sort > /tmp/before.txt`，迁移后 `find <new> -type f | sed "s|^<new>/||" | sort > /tmp/after.txt`，`comm -23 /tmp/before.txt /tmp/after.txt` 必须为空（迁移前文件一个不漏）。计数仅作参考（调研时点为 590，**不硬编码历史快照**）。

### D8 · 与 issue 原文的差异（需用户知悉）

| 项 | issue 原文 | 本 spec |
|----|-----------|---------|
| 引用点计数 | 「9 处」 | **11 处 `~/.claude`**（多出 `github-issue-driven/SKILL.md:46` 的裸写法，与 `issue-research/SKILL.md:33`），另加 `pi/README.md` 一行约定 |
| 迁移脚本形态 | 未指定 | Python（为可测性；见 D4） |
| A4 对账范围 | 未指定豁免 | `docs/superpowers/**` 历史文档豁免；旧路径字面量只允许出现在脚本与测试 |
| 环境变量 | 「建议无论选哪个都加」 | 采纳，且脚本与 skill 共用同一优先级（D2/D4） |
| 兼容策略 | 「新路径优先，不存在时回退读旧路径，兼容期内两处皆可读」（运行期双读回退） | 改为**一次性迁移 + 旧路径符号链接**：效果等价（旧路径可读、跨 harness 不变）且不需要运行期双读；代价是依赖一次性动作完成（R2-D2 补记） |

## 6. 可测性拆分设计（自动化类功能点的实现硬约束）

| 层 | 单元 | 依赖 | 测法 |
|----|------|------|------|
| 纯解析 | `resolve_home(env_value: str | None, home: Path) -> Path`（env 非空 → 该路径；空/None → `home/'.github-issue-driven'`） | 无 | unit：env 有值 / 空串 / None 三态 |
| 纯决策 | `resolve_action(legacy_state, new_state) -> Action`（枚举字符串，无 IO） | 无 | unit 参数化覆盖 D4 决策表 16 格 |
| 纯格式化 | `describe_action(action, legacy, new) -> str` | 无 | unit 断言首行契约文本 + `unlink` 警告句 |
| IO 探测 | `inspect_paths(legacy: Path, new: Path) -> tuple[State, State]`（**入参是两个已解析的路径**，不在内部读 env——env 解析归纯函数层） | 文件系统（只读） | integration：tmp HOME 构造 4 种形态（`absent` / `dir` / `symlink_to_new` / `symlink_other`），与 A3 的四态场景对齐 |
| IO 执行 | `apply_action(action, legacy, new) -> int`（`mv` + `symlink`，唯一副作用点） | 文件系统（写） | integration：tmp HOME 真实迁移 + 幂等 + dry-run 零写入 |
| CLI 壳 | `main(argv=None) -> int` | 上面各层 | integration：subprocess 调用，核对退出码与 stdout 首行 |

测试边界（如实声明）：A1–A4 只能证明「文档口径统一、脚本语义正确、旧路径不再被教学」，**证明不了**「agent 在真实会话里一定按新路径落盘」「CC 侧流程自动跟随」——后者由 U1 兜底。

## 7. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 活跃 skill 文档口径迁移 | 自动化（unit/static） | `uv run pytest tests/unit/test_issue_driven_home_contracts.py -v` | 5 条断言全过（含 `pi/README.md` 的正向断言）；`rg -n --glob '*.md' "~/\.claude" pi/` 零命中 |
| A2 | 迁移决策表与路径解析语义 | 自动化（unit） | `uv run pytest tests/unit/test_migrate_issue_driven_home.py -v` | `resolve_home` 三态（env 有值 / 空串 / None）；`resolve_action` 16 格全覆盖（7 行展开 + 未列出组合默认 `conflict`）；`describe_action` 文案含 `unlink` 警告句 |
| A3 | 迁移脚本真实行为与幂等 | 自动化（integration） | `uv run pytest tests/integration/test_migrate_issue_driven_home.py -v` | 四态场景全过：`migrate`（新目录含原文件、旧路径为指向新目录的符号链接）、`noop_migrated`（重复执行）、`noop_fresh`（两侧皆无 → 0）、`conflict`（两侧皆有 → **非 0 且不动数据**：无 `mv`、无新符号链接）；`--dry-run` 不改动文件系统；`--help` 含 `unlink` 警告句；**env 覆盖用例**：`GITHUB_ISSUE_DRIVEN_HOME=<tmp>/custom` 时迁移目标是 `<tmp>/custom`，且默认路径不被创建 |
| A4 | 仓内活跃文件无旧路径残留 | 自动化（static） | `rg -n --glob '*.md' "claude/github-issue-driven" pi/ README.md CLAUDE.md` | 零命中（旧字面量只允许在 `scripts/migrate_issue_driven_home.py` 与 `tests/**`）。`--glob '*.md'` 是必需项：纯目录参数形式会被 `pi/.ignore`（内容 `README.md`）静默跳过 `pi/README.md`；`--no-ignore` 非必需（R3-D1 实测修正） |
| A5 | 既有契约与套件不回归 | 自动化（build） | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` | 全绿；覆盖率 ≥60%；既有契约测试 `test_spec_cross_review_contracts.py`（**#254** 引入）不变仍过 |
| U1 | 真实会话与 CC 侧兼容 | 用户实测 | 主 checkout 先 `git checkout main && git pull`，再发起新会话取一个小 issue 走步 3 + 步 4；再在 CC 侧任一流程里写一次留档 | 新产物落在 `~/.github-issue-driven/`；旧路径符号链接可读到同一文件；pi-auto-rename 仍识别 issue 号（会话标题带 issue 号）；CC 侧写入经符号链接落到新目录 |
| U2 | 本机存量迁移对账 | 用户实测 | 在 issue worktree 内按 D7 的三条命令执行并核对（**集合对账**，不做严格计数相等） | 迁移前把 `find <legacy> -type f`（去掉前缀）`| sort` 落盘一份清单，迁移后同法取新目录清单，`comm -23 <before> <after>` **为空**（迁移前文件全部在新位置）；计数仅作参考（该目录被活跃会话持续写入，严格相等不保证，R2-D3）；`readlink` 指向新目录；第二次执行为 noop（幂等） |

用户实测可执行时机：U2 在 PR 合并前即可执行，但必须在 **issue worktree**（脚本所在 checkout）内跑——脚本此时还没进 `main`；**U1 必须在 PR 合并回 `main` 之后**，且主 checkout 先 `git checkout main && git pull`，再从主 checkout（pi 包加载路径，见 `~/.pi/agent/settings.json` 的 `packages`）发起的会话中执行——未拉取的主 checkout 与 worktree 是同一类陷阱：验收证明的是旧行为。

## 8. 保证边界

1. 契约测试只锁文档口径，不锁真实会话行为（U1 兜底）。
2. 迁移脚本只保证单机幂等；不保证两个会话同一时刻并发执行（`mv` 竞态由人避免，文档注明）。**计数类不变量不作保证**：目录被活跃会话写入，只保证「迁移前快照是迁移后快照的子集」（D7 的集合对账口径）。
3. 符号链接无法防护 `rm -rf <dir>/` 的穿透删除——只能用文档禁令 + 输出提示缓解。
4. 迁移不改变 `~/.claude` 下其它内容（不清理、不重命名该目录本身）。
5. `GITHUB_ISSUE_DRIVEN_HOME` 只影响本流程的留档路径，不改变任何 zima / jfox 运行期数据目录。

## 9. 交付物清单

- `pi/github-issue-driven/SKILL.md`（7 处路径 + D2 定稿文本）
- `pi/issue-research/SKILL.md`（2 处）
- `pi/spec-cross-review/SKILL.md`（2 处）
- `pi/README.md`（1 行约定）
- `scripts/migrate_issue_driven_home.py`（新增，含 `--dry-run` 与 `--help`）
- `tests/unit/test_issue_driven_home_contracts.py`（新增）
- `tests/unit/test_migrate_issue_driven_home.py`（新增）
- `tests/integration/test_migrate_issue_driven_home.py`（新增）
- `docs/superpowers/specs/2026-10-16-issue-driven-home-relocation-design.md`（步 5 首 commit；由本文件转正）
- 本机一次性迁移执行 + issue 留痕（非仓库产物）

## 10. ⏸ 时用户决定（2026-10-16，已定）

| 待决项 | 用户决定 | 落地影响 |
|--------|----------|----------|
| 新路径最终选择 | **确认 B：`~/.github-issue-driven/`** | D1 定稿，无备选残留 |
| CC 侧两份旧 skill 拷贝（`~/.claude/skills/{github-issue-driven,issue-research}`） | **明确「不要动」** | 本 issue 不改它们、不开 follow-up；旧路径符号链接使其继续可用；其内容与 pi 版分叉的问题不在本 issue 追踪 |
| `pi-auto-rename` fixture 中的旧路径字面量 | **不追踪**（用户判断该仓工作已完成、属既有遗留） | 本 issue 不改它、不开 follow-up。事实核对：`test/work-evidence.test.ts:65/91/94/104/117` 仍有 5 处字面量；正则只匹配后缀，**无功能影响**；该仓当前仅剩 1 个 open issue（#13，2026-10-16 新开，与本议题无关） |
| U2 本机存量迁移（590 文件 `mv` + 符号链接） | **执行前另行确认**（遵守用户 AGENTS.md 副作用规则） | U2 不在步 5–7 内自动执行；执行前单独报备 |

---

## 11. 第 1 轮复核发现的处置（修订记录）

复核者：spec-reviewer `zai-coding-cn/glm-5.3`（fresh context）· 被审版本 sha256 `0919b4ff…` · 真缺口 2 / 细化 5 / 核对通过 5。

| 发现 | 级别 | 处置 | 改动位置 |
|------|------|------|----------|
| R1-G1 D2 定稿文本内嵌 cwd 相对脚本路径，跨仓会话不可达 | 真缺口 | **接受并改**：迁移指令改为「在本技能包仓库（zima-blue-cli）的主 checkout 内执行」，并注明脚本按包定位而非按 cwd | §5 D2 文本 + 其后说明 |
| R1-G2 `unlink` 防穿透提示无验收项 | 真缺口 | **接受并改**：A2 增 `describe_action` 文案断言、A3 增 `--help` 断言；D3/D6 标注验收归属 | §5 D3、D6；§7 A2/A3 |
| R1-D1 决策表 16 格只定义 10 格，与「全组合」措辞矛盾 | 细化 | **接受并改**：补兜底行「未列出的组合一律 `conflict`」，A2 改「16 格全覆盖」 | §5 D4、D6；§7 A2 |
| R1-D2 `test_legacy_path_defined_once` 扫描口径歧义 | 细化 | **接受并改**：口径固定为「`pi/**/*.md` 零出现 + 脚本内 ≥1 次」，显式免除全仓唯一性断言 | §5 D6 |
| R1-D3 「新增两个测试文件」与清单三处不一致 | 细化 | **接受并改**：改为三个（2 unit + 1 integration） | §5 D6 首句 |
| R1-D4 580/9 快照已过期 | 细化 | **接受并改**：标注时点（调研时点 590 文件 / 7.4 MB / 10 个 repo），U2 不变量改为「前后一致、以执行时刻实测 N 为准」 | §1.2、§5 D7、§7 U2 |
| R1-D5 U1 缺 `git pull` 前置、U2 缺执行目录 | 细化 | **接受并改**：U1 增 `git checkout main && git pull`；D7/U2 明确在 issue worktree 内执行 | §5 D7；§7 U1、U2 与末段 |

另记：第 1 轮 child 的 `lenses[0].findingIds` 引用了不存在的 `R1-D6`（findings 数组无此项），按笔误处理，不计入裁定。

未接受项：无。

## 12. 第 2 轮复核发现的处置（修订记录）

复核者：spec-reviewer `zai-coding-cn/glm-5.3`（fresh context）· 被审版本 sha256 `d0eb2664…` · 真缺口 1 / 细化 3 / 核对通过 7（第 1 轮 7 项修订全部磁盘核实到位）。

| 发现 | 级别 | 处置 | 改动位置 |
|------|------|------|----------|
| R2-G1 `GITHUB_ISSUE_DRIVEN_HOME` 分支（三层解析的脚本半边）无验收归属：A2 是纯函数（无 env 入参）、A3 场景清单不含 env 用例、§6 `inspect_paths(home)` 表达不了 env 覆盖 | 真缺口 | **接受并改**：新增纯函数 `resolve_home(env_value, home)`；`inspect_paths` 入参改为两个已解析路径 `(legacy, new)`；A2 增 `resolve_home` 三态断言；A3 增 env 覆盖集成用例（迁移目标为 env 指定路径、默认路径不被创建） | §5 D4；§6 表；§7 A2/A3 |
| R2-D1 A4 的 rg 目录参数形式遵守 `pi/.ignore`，会静默跳过 `pi/README.md`（实测） | 细化 | **接受并改**：A4 与 D5 口径校验均加 `--no-ignore`，并注明原因 | §5 D5；§7 A4 |
| R2-D2 D8 差异表漏列「兼容策略」差异（issue 建议运行期双读回退，spec 改为一次性迁移 + 符号链接） | 细化 | **接受并改**：D8 补一行 | §5 D8 |
| R2-D3 U2 严格计数相等在活跃写入窗口下会假失败（spec 自己指出该目录正被写入） | 细化 | **接受并改**：U2/D7 改为集合对账（`comm -23 before after` 为空），计数仅作参考；§8.2 补「计数类不变量不作保证」 | §5 D7；§7 U2；§8.2 |

未接受项：无。

- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:21:39+08:00（第 1 轮处置完成，开第 2 轮）
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:30:43+08:00（第 2 轮 1 真缺口 + 3 细化的处置见 §12）
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:41:31+08:00（第 3 轮收敛：0 真缺口；6 项细化处置见 §13）
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T20:45:55+08:00（用户 ⏸ 确认：路径取 B、CC 侧不动、pi-auto-rename 不追踪、U2 执行前另行确认——见 §10）

## 13. 第 3 轮复核发现的处置（收敛轮）

复核者：spec-reviewer `zai-coding-cn/glm-5.3`（fresh context）· 被审版本 sha256 `423a99d0…` · **真缺口 0** / 细化 6 / 核对通过 4 → **收敛**。

| 发现 | 级别 | 处置 | 改动位置 |
|------|------|------|----------|
| R3-D1 `--no-ignore` 归因被实测证伪（带 `--glob '*.md'` 时 glob 白名单覆盖 `.ignore`） | 细化 | **接受并改**：A4/D5 口径说明改为实测机制（纯目录参数才被 `pi/.ignore` 跳过；`--glob '*.md'` 已足够，`--no-ignore` 非必需），命令统一为 `rg -n --glob '*.md' …` | §5 D5；§7 A4 |
| R3-D2 §5 D6 首句「两个测试文件」与括注自相矛盾 | 细化 | **接受并改**：首句重写为「三个（2 unit + 1 integration）」，删除重复括注 | §5 D6 |
| R3-D3 头部状态行仍写 v2 | 细化 | **接受并改**：状态行更新为 v4 | 头部 |
| R3-D4 `pi/README.md` 新增行无正向断言 | 细化 | **接受并改**：新增 `test_readme_documents_home`，A1 通过标准同步（4 → 5 条） | §5 D6；§7 A1 |
| R3-D5 `conflict` 失败分支缺端到端集成用例、「三态」未定义 | 细化 | **接受并改**：A3 场景点名为四态（`migrate` / `noop_migrated` / `noop_fresh` / `conflict`）+ 幂等 + dry-run + env 覆盖；`conflict` 断言「非 0 且不动数据」；§6 探测行与 A3 对齐 | §5 D6；§6；§7 A3 |
| R3-D6 契约测试归属错置（#254 引入，非 #250） | 细化 | **接受并改**：两处（§5 D6 首句与 §7 A5）改为「既有契约测试（`test_spec_cross_review_contracts.py`，#254 引入）」 | §5 D6；§7 A5 |

未接受项：无。

收敛判定：真缺口 0 → 本轮为收敛轮；6 项细化已处置。进入 ⏸，等用户确认设计后进步 5（worktree）。

# 进度保存与恢复机制

> 基于 Kimi CLI 日志的断点续传设计

---

## 1. 核心洞察：Kimi CLI 的日志特性

Kimi CLI 的执行过程具有以下特点：

1. **全量输出**：所有思考、命令执行、文件读写都会打印到 stdout
2. **结构化隐含**：虽然没有严格的结构化格式，但有明显的阶段标记
3. **幂等可重入**：同样的 Prompt 可以重复执行，Kimi 会基于当前状态继续

```
Kimi CLI 典型输出结构：
│
├─ 🔍 分析阶段
│   ├─ 读取文件: zk/cli.py
│   ├─ 识别命令: kb import, kb export...
│   └─ 发现: 3个命令未覆盖
│
├─ 💭 思考阶段
│   ├─ 这些命令需要补充测试...
│   └─ 计划: 先写 kb import 的测试
│
├─ ✏️ 执行阶段
│   ├─ 写入: tests/test_kb_import.py
│   ├─ 运行: pytest tests/test_kb_import.py -v
│   └─ 结果: ✅ 通过
│
└─ ✅ 完成
    └─ 写入结果文件...
```

---

## 2. 日志实时捕获机制

### 2.1 为什么必须实时写入？

如果等到 kimi 退出再读取输出，**超时 kill 后会丢失数据**。

```python
# ❌ 错误做法：等进程结束再读取
result = subprocess.run(cmd, capture_output=True, timeout=840)
print(result.stdout)  # 超时后被 kill，这里拿不到数据！

# ✅ 正确做法：实时写入文件
with open(log_file, "w", encoding="utf-8") as f:
    process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    # 即使被 kill，已写入的内容也保留了
```

### 2.2 实现代码

```python
# zima/executor/kimi_runner.py

import subprocess
import signal
from datetime import datetime
from pathlib import Path

class KimiRunner:
    def run_with_recovery(self, prompt_file: Path, cycle_num: int) -> CycleResult:
        """
        执行 kimi-cli，支持超时后的进度恢复
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"cycle_{timestamp}.log"
        
        cmd = [
            "kimi",
            "--print",
            "--yolo",
            "--prompt-file", str(prompt_file),
            "--work-dir", str(self.workspace),
            "--max-steps-per-turn", "50",
        ]
        
        print(f"🚀 启动周期 {cycle_num}，日志: {log_file}")
        
        # 关键：实时写入日志文件
        with open(log_file, "w", encoding="utf-8") as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,           # 实时写入文件
                stderr=subprocess.STDOUT,  # stderr 合并到 stdout
                cwd=self.workspace
            )
            
            try:
                # 等待完成或超时
                return_code = process.wait(timeout=840)  # 14分钟
                
                # 正常完成
                return self._parse_completed(log_file, return_code)
                
            except subprocess.TimeoutExpired:
                # ⏰ 超时！需要保存进度
                print(f"⏰ 周期 {cycle_num} 超时，正在保存进度...")
                
                # 1. 优雅终止
                process.terminate()
                try:
                    process.wait(timeout=5)
                except:
                    process.kill()  # 强制 kill
                
                # 2. 基于日志分析进度
                progress = self._analyze_progress_from_log(log_file)
                
                # 3. 生成检查点
                checkpoint = self._create_checkpoint(log_file, progress)
                
                return CycleResult(
                    status="timeout",
                    progress=progress,
                    log_file=log_file,
                    checkpoint=checkpoint,  # 关键：保存检查点
                    message=f"超时中断，已完成约 {progress}%"
                )
```

---

## 3. 从日志解析进度

### 3.1 启发式进度分析

```python
def _analyze_progress_from_log(self, log_file: Path) -> int:
    """
    从日志分析当前进度（0-100）
    
    基于 Kimi CLI 的输出特征进行启发式判断
    """
    if not log_file.exists():
        return 0
    
    content = log_file.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # 关键标记检测
    markers = {
        'git_commit': False,
        'test_run': False,
        'file_write': False,
        'analysis_complete': False,
    }
    
    for line in lines:
        line_lower = line.lower()
        
        # 分析阶段完成标记
        if any(kw in line_lower for kw in ['分析完成', '识别出', '发现', 'analysis complete']):
            markers['analysis_complete'] = True
            
        # 文件写入标记
        if any(kw in line_lower for kw in ['写入', 'write', 'edit', '修改']):
            markers['file_write'] = True
            
        # 测试运行标记
        if any(kw in line_lower for kw in ['pytest', '测试', 'test', 'running test']):
            markers['test_run'] = True
            
        # Git 提交标记（通常接近完成）
        if any(kw in line_lower for kw in ['git commit', '提交']):
            markers['git_commit'] = True
    
    # 计算进度（基于阶段）
    progress = 0
    if markers['analysis_complete']:
        progress = 20
    if markers['file_write']:
        progress = 50
    if markers['test_run']:
        progress = 70
    if markers['git_commit']:
        progress = 90
    
    # 如果有结果文件写入标记，视为接近完成
    if 'result.json' in content or '完成' in content:
        progress = max(progress, 80)
    
    return progress
```

### 3.2 更精确的解析：基于命令序列

```python
def _extract_executed_commands(self, log_file: Path) -> list[CommandRecord]:
    """
    从日志提取已执行的命令序列
    
    Kimi CLI 的输出格式示例：
    ```
    ❯ ls -la
    total 128
    drwxr-xr-x  5 user group  160 Mar 25 08:00 .
    ...
    
    ❯ cat zk/cli.py | head -50
    import typer
    ...
    ```
    """
    content = log_file.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    commands = []
    current_command = None
    
    for line in lines:
        # 检测命令行（通常以 ❯ 或 $ 开头）
        if line.startswith('❯') or line.startswith('$'):
            if current_command:
                commands.append(current_command)
            
            cmd_text = line[1:].strip()
            current_command = {
                'command': cmd_text,
                'output': [],
                'timestamp': None  # 可以从日志时间戳提取
            }
        
        elif current_command is not None:
            # 收集命令输出
            current_command['output'].append(line)
    
    if current_command:
        commands.append(current_command)
    
    return commands
```

---

## 4. 检查点（Checkpoint）机制

### 4.1 什么是检查点？

检查点是超时时的"现场照片"，包含：
1. **已完成的工作**：基于日志分析
2. **当前文件状态**：git diff 或文件快照
3. **上下文恢复信息**：下轮如何继续

### 4.2 检查点文件结构

```json
{
  "checkpoint": {
    "cycle": 5,
    "timestamp": "2026-03-25T09:14:32Z",
    "reason": "timeout",
    "log_file": "logs/cycle_20260325_090000.log"
  },
  
  "progress": {
    "percentage": 65,
    "stage": "fix_failures",
    "completed_tasks": [
      "分析了 test_import.py 的失败原因",
      "修复了 test_import.py 的错误处理",
      "运行 pytest tests/test_import.py -v 通过",
      "开始分析 test_export.py"
    ],
    "in_progress": "修复 test_export.py",
    "remaining_tasks": [
      "完成 test_export.py 修复",
      "修复 test_merge.py",
      "修复 test_search.py",
      "修复 test_template.py"
    ]
  },
  
  "code_state": {
    "modified_files": [
      {
        "path": "tests/test_import.py",
        "change_type": "modified",
        "lines_added": 15,
        "lines_removed": 3,
        "diff_snippet": "@@ -45,6 +45,21 @@ def test_kb_import():..."
      }
    ],
    "uncommitted_changes": true,
    "last_commit": "a1b2c3d"
  },
  
  "recovery_prompt": {
    "summary": "第5轮超时，已修复2/5个测试",
    "context": "正在修复 test_export.py 的路径验证问题",
    "next_step": "继续完成 test_export.py 的修复"
  }
}
```

### 4.3 生成检查点

```python
def _create_checkpoint(self, log_file: Path, progress: int) -> Checkpoint:
    """基于日志和代码状态生成检查点"""
    
    # 1. 分析日志提取已完成的工作
    completed_tasks = self._extract_completed_tasks(log_file)
    
    # 2. 获取代码状态（git status）
    code_state = self._get_code_state()
    
    # 3. 生成恢复提示词片段
    recovery_prompt = self._generate_recovery_prompt(
        log_file, completed_tasks, code_state
    )
    
    checkpoint_file = self.agent_dir / "checkpoints" / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    
    checkpoint = {
        "cycle": self.state.current_cycle,
        "timestamp": datetime.now().isoformat(),
        "log_file": str(log_file),
        "progress": progress,
        "completed_tasks": completed_tasks,
        "code_state": code_state,
        "recovery_prompt": recovery_prompt
    }
    
    checkpoint_file.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    
    return checkpoint
```

---

## 5. 下轮恢复：基于检查点继续

### 5.1 恢复流程

```
第6轮苏醒
│
├─ 读 state.json
│   └─ {current_cycle: 6, last_status: "timeout", checkpoint: "checkpoint_20260325_091432.json"}
│
├─ 读检查点文件
│   └─ "第5轮超时，已修复2/5个测试，正在修复 test_export.py"
│
├─ 读第5轮的完整日志
│   └─ 分析已执行的命令和修改的文件
│
└─ 生成恢复型 Prompt
```

### 5.2 恢复型 Prompt 示例

```markdown
# 第6轮 - 恢复继续

## ⚠️ 重要：本轮是恢复继续

上一轮（第5轮）在执行过程中超时中断，以下是已保存的进度：

### 已完成的工作
- ✅ 分析了 test_import.py 的失败原因
- ✅ 修复了 test_import.py 的错误处理逻辑
- ✅ 运行 pytest tests/test_import.py -v 通过
- ✅ 开始分析 test_export.py

### 当前状态
- 正在处理: test_export.py
- 已修改文件: tests/test_import.py（有未提交的更改）
- Git 状态: 有未提交的修改，commit a1b2c3d

### 本轮任务
继续修复 test_export.py 的路径验证问题。

### 建议步骤
1. 先检查当前的 git 状态
2. 查看 test_export.py 的当前状态
3. 继续之前的修复工作
4. 运行局部测试验证
5. 如果完成，git commit

### 注意事项
- 不要重复第5轮已完成的工作
- 基于当前代码状态继续
- 如果发现问题，可以在 .zima/recovery_notes.md 中记录
```

### 5.3 代码实现

```python
def _build_recovery_prompt(self, checkpoint: dict) -> str:
    """基于检查点构建恢复型 Prompt"""
    
    lines = [
        f"# 第{self.state.current_cycle}轮 - 恢复继续\n",
        "## ⚠️ 重要：本轮是恢复继续\n",
        f"上一轮（第{checkpoint['cycle']}轮）在执行过程中**{checkpoint['reason']}**中断。\n",
        "### 已完成的工作"
    ]
    
    for task in checkpoint['progress']['completed_tasks']:
        lines.append(f"- ✅ {task}")
    
    lines.extend([
        "\n### 当前状态",
        f"- 正在处理: {checkpoint['progress']['in_progress']}",
        f"- 进度: {checkpoint['progress']['percentage']}%",
    ])
    
    if checkpoint['code_state']['modified_files']:
        lines.append("- 已修改文件:")
        for f in checkpoint['code_state']['modified_files']:
            lines.append(f"  - {f['path']} ({f['change_type']})")
    
    lines.extend([
        "\n### 本轮任务",
        f"{checkpoint['recovery_prompt']['next_step']}",
        "\n### 建议步骤",
        "1. 先检查 git status，了解当前状态",
        "2. 查看正在处理的文件",
        "3. 基于已有进度继续",
        "4. 避免重复之前的工作",
    ])
    
    return '\n'.join(lines)
```

---

## 6. 完整的超时恢复示例

### 第5轮：超时场景

```
时间线:
09:00:00 启动 kimi
09:02:00 开始修复 test_import.py
09:05:00 完成 test_import.py 修复，运行测试通过
09:06:00 开始修复 test_export.py
09:10:00 正在修改 test_export.py 的路径验证...
09:14:00 ⚠️ 即将超时（还剩1分钟）
09:14:32 ⏰ 超时！强制终止
         ├── kill 进程
         ├── 分析日志：已完成 2/5，当前正在第3个
         ├── 生成 checkpoint_20260325_091432.json
         └── 更新 state: {status: "timeout", checkpoint: "..."}
09:15:00 进入休眠
```

### 第6轮：恢复继续

```
时间线:
09:15:00 苏醒
         ├── 读 state: {last_status: "timeout", checkpoint: "..."}
         ├── 读检查点："已修复2个，正在第3个"
         ├── 读第5轮日志：分析已执行的命令
         └── 生成恢复型 Prompt

09:15:30 启动 kimi（带恢复提示）
         Prompt: "上一轮超时，已修复2/5，继续修复 test_export.py..."

09:16:00 kimi 执行:
         ├── git status（查看当前状态）
         ├── cat tests/test_export.py（查看文件）
         ├── 基于之前的思路继续修复
         ├── pytest tests/test_export.py -v ✅
         └── 继续修复第4个 test_search.py

09:28:00 完成本轮（修复了2个，共4/5）
         ├── 写入结果: {status: "partial", progress: 80}
         └── 更新 Session: "又修复了2个，还剩1个"

09:29:00 休眠
```

---

## 7. 关键设计原则

### 7.1 日志即记忆

```
Kimi CLI 日志 → 解析 → Session + 检查点
     │
     └── 包含完整执行轨迹
         ├── 读了哪些文件
         ├── 执行了哪些命令
         ├── 产生了哪些修改
         └── 思考过程
```

### 7.2 幂等可重入

```
同样的 Prompt + 相同的代码状态 = 可重复执行

即使超时后重试：
- 第5轮：修改了文件 A，超时
- 第6轮：读取文件 A 发现已修改，基于现有状态继续
```

### 7.3 渐进式提交

```
鼓励 Kimi 频繁做小的 git commit：

✅ 好的执行:
  - 修改文件 A → git commit -m "wip: fix test A"
  - 修改文件 B → git commit -m "wip: fix test B"
  - 超时后：已提交的不会丢失

❌ 不好的执行:
  - 修改文件 A, B, C, D
  - 最后才 git commit
  - 超时后：所有修改都可能丢失或冲突
```

---

## 8. 给 Kimi 的 Prompt 建议

在 Prompt 中加入以下提示，帮助更好地保存进度：

```markdown
## 时间管理建议

你有约 9 分钟的执行时间。建议：

1. **频繁提交**
   - 每完成一个小任务就 `git commit`
   - 使用 "wip:" 前缀表示进行中的工作
   - 例如：`git commit -m "wip: fix test_import error handling"`

2. **时间检查**
   - 执行耗时操作前，评估剩余时间
   - 如果剩余时间 < 2 分钟，保存当前进度并结束

3. **超时处理**
   - 如果可能超时，先保存当前修改（git commit）
   - 在结果文件中说明："已保存到 commit xxx，下轮继续"

4. **恢复信息**
   - 在 .zima/progress.md 中记录当前进度
   - 包括：正在处理什么、已完成什么、遇到了什么问题
```

---

## 总结

| 机制 | 作用 | 存储位置 |
|------|------|----------|
| **实时日志** | 完整记录执行过程 | `logs/cycle_xxx.log` |
| **检查点** | 超时时的状态快照 | `checkpoints/checkpoint_xxx.json` |
| **Session** | 人工可读的总结 | `sessions/xxx.md` |
| **Git 提交** | 代码修改的持久化 | Git 历史 |

**核心思想**：
> Kimi CLI 的日志就是它的"记忆"。我们要做的是实时捕获这份记忆，在超时后基于这份记忆生成"恢复提示"，让下一轮能够无缝继续。

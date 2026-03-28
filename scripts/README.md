# Zima Blue CLI - 清理脚本

这个目录包含项目维护和清理相关的脚本。

## cleanup.py - 项目清理工具

清理项目中的临时文件、缓存和日志。

### 快速开始

```bash
# 交互式清理（推荐）
python scripts/cleanup.py

# 预览会清理什么（不实际删除）
python scripts/cleanup.py --dry-run

# 自动清理（无确认）
python scripts/cleanup.py --auto

# 清理所有内容（包括日志）
python scripts/cleanup.py --all
```

### 命令选项

| 选项 | 简写 | 说明 |
|------|------|------|
| `--auto` | `-a` | 自动模式，不询问确认 |
| `--dry-run` | `-n` | 仅预览，不实际删除 |
| `--all` | `-A` | 同时清理日志文件 |
| `--temp-only` | `-t` | 仅清理系统临时目录 |
| `--cache-only` | `-c` | 仅清理项目缓存文件 |

### 清理内容

#### 1. 项目缓存 (`--cache-only`)
- `**/__pycache__` - Python 字节码缓存
- `**/*.pyc`, `**/*.pyo` - 编译后的 Python 文件
- `.pytest_cache` - pytest 缓存
- `.mypy_cache`, `.ruff_cache` - 类型检查/代码检查缓存
- `build/`, `dist/`, `*.egg-info` - 构建产物
- `test_ralph_scenario/` - 测试场景临时文件

#### 2. 系统临时文件 (`--temp-only`)
- `C:\Users\<user>\AppData\Local\Temp\pytest-of-*` - pytest 临时目录
- `C:\Users\<user>\AppData\Local\Temp\zima-test-*` - Zima 测试临时目录
- `C:\Users\<user>\AppData\Local\Temp\tmp*` - 包含 agents/configs 的临时目录

#### 3. 日志文件 (`--all`)
- `logs/*.log` - 执行日志
- `agents/**/logs/*.log` - Agent 执行日志
- `workspace/.zima/*.json` - 运行时结果文件

### 使用场景

#### 场景 1：开发前清理
确保干净的开发环境：
```bash
python scripts/cleanup.py --auto --cache-only
```

#### 场景 2：测试后清理
运行测试后清理临时文件：
```bash
# 先查看会清理什么
python scripts/cleanup.py --dry-run --all

# 确认后执行清理
python scripts/cleanup.py --all
```

#### 场景 3：CI/CD 清理
在持续集成中自动清理：
```bash
python scripts/cleanup.py --auto --all
```

#### 场景 4：仅清理临时文件
保留项目文件，只清理系统临时目录：
```bash
python scripts/cleanup.py --auto --temp-only
```

### 安全说明

1. **不会删除源代码** - 脚本只针对缓存、临时文件和日志
2. **不会删除配置文件** - `.yaml`, `.json` 配置保留
3. **交互式确认** - 默认会询问确认（除非使用 `--auto`）
4. **干运行模式** - 使用 `--dry-run` 预览会删除的内容

### 示例输出

```
============================================================
Zima Blue CLI - Cleanup Preview
============================================================

Project Cache:
  Items: 69
  Size: 2.7 MB

System Temp Files:
  Items: 4
  Size: 15.2 MB
    - pytest-of-zhuzh/pytest-44/...
    - pytest-of-zhuzh/pytest-45/...

============================================================
Total: 73 items, 17.9 MB
============================================================

Confirm cleanup? [y/N]: y

Starting cleanup...

Project Cache:
  [DELETED] .pytest_cache (50.0 KB)
  [DELETED] tests/__pycache__ (544.9 KB)
  ...

System Temp Files:
  [DELETED] pytest-of-zhuzh (15.2 MB)

============================================================
Cleanup Complete!
Deleted: 73 items
Freed: 17.9 MB
============================================================
```

### 故障排除

#### 权限错误
如果遇到权限错误，尝试：
```bash
# Windows - 以管理员身份运行 PowerShell
# Linux/Mac - 使用 sudo
sudo python scripts/cleanup.py --auto
```

#### 临时文件被占用
如果临时文件被其他进程占用，脚本会跳过并显示错误。可以稍后重试或重启系统后清理。

#### 找不到临时文件
这是正常的，说明临时文件已经被系统或 pytest 自动清理了。

### 自动清理配置

#### Git Hook
在 `.git/hooks/post-checkout` 中添加：
```bash
#!/bin/bash
python scripts/cleanup.py --auto --cache-only
```

#### VS Code Task
在 `.vscode/tasks.json` 中添加：
```json
{
    "label": "Cleanup",
    "type": "shell",
    "command": "python scripts/cleanup.py --auto --cache-only",
    "problemMatcher": []
}
```

### 相关文档

- [项目 README](../README.md)
- [AGENTS.md](../AGENTS.md) - Agent 开发指南

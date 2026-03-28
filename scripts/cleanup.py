#!/usr/bin/env python3
"""
Zima Blue CLI - Cleanup Script

清理项目中产生的临时文件、缓存和日志。

Usage:
    python scripts/cleanup.py              # 交互式清理
    python scripts/cleanup.py --auto       # 自动清理（无确认）
    python scripts/cleanup.py --dry-run    # 仅显示会清理什么
    python scripts/cleanup.py --all        # 清理所有包括日志
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 要清理的目录模式
CACHE_PATTERNS = [
    # Python 缓存
    "**/__pycache__",
    "**/*.pyc",
    "**/*.pyo",
    "**/.pytest_cache",
    "**/.mypy_cache",
    "**/.ruff_cache",
    
    # 构建产物
    "**/build",
    "**/dist",
    "**/*.egg-info",
    "**/.eggs",
    
    # 测试相关临时文件
    "**/test_ralph_scenario",
]

# 临时目录模式
TEMP_PATTERNS = [
    # pytest 临时目录
    "pytest-of-*",
    "pytest-*",
]

# 日志目录（可选清理）
LOG_PATTERNS = [
    "logs/*.log",
    "logs/cycle_*.log",
    "logs/run_*.log",
    "workspace/.zima/*.json",
]


def get_size(path: Path) -> int:
    """计算文件或目录大小（字节）"""
    if path.is_file():
        return path.stat().st_size
    elif path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return 0


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def find_cache_files() -> List[Path]:
    """查找项目中的缓存文件"""
    found = []
    for pattern in CACHE_PATTERNS:
        for path in PROJECT_ROOT.glob(pattern):
            if path != PROJECT_ROOT / "scripts" / "cleanup.py":
                found.append(path)
    return found


def find_temp_dirs() -> List[Path]:
    """查找系统临时目录中的 pytest 临时文件"""
    found = []
    temp_base = Path(tempfile.gettempdir())
    
    # 查找 pytest 临时目录
    import glob
    for pattern in TEMP_PATTERNS:
        for path_str in glob.glob(str(temp_base / pattern)):
            path = Path(path_str)
            if path.exists():
                found.append(path)
    
    # 查找 zima 相关的临时目录
    for path_str in glob.glob(str(temp_base / "zima-test-*")):
        found.append(Path(path_str))
    
    for path_str in glob.glob(str(temp_base / "tmp*")):
        path = Path(path_str)
        # 检查是否是 zima 相关的临时目录
        if path.exists() and path.is_dir():
            try:
                # 检查是否包含 agents 或 configs 目录
                if any((path / sub).exists() for sub in ["agents", "configs"]):
                    found.append(path)
            except PermissionError:
                pass
    
    return found


def find_log_files(include_all: bool = False) -> List[Path]:
    """查找日志文件"""
    found = []
    for pattern in LOG_PATTERNS:
        for path in PROJECT_ROOT.glob(pattern):
            found.append(path)
    
    # 查找 agents 目录下的日志
    agents_dir = PROJECT_ROOT / "agents"
    if agents_dir.exists():
        for pattern in ["**/logs/*.log", "**/workspace/.zima/*.json"]:
            for path in agents_dir.glob(pattern):
                found.append(path)
    
    return found


def cleanup_paths(paths: List[Path], dry_run: bool = False) -> Tuple[int, int]:
    """
    清理指定的路径
    
    Returns:
        (清理的文件数, 释放的字节数)
    """
    count = 0
    freed = 0
    
    for path in paths:
        if not path.exists():
            continue
        
        size = get_size(path)
        
        if dry_run:
            rel_path = path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in path.parents else path
            print(f"  [DRY-RUN] Would delete: {rel_path}")
            count += 1
            freed += size
            continue
        
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            
            rel_path = path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in path.parents else path
            print(f"  [DELETED] {rel_path} ({format_size(size)})")
            count += 1
            freed += size
        except Exception as e:
            print(f"  [ERROR] Cannot delete {path}: {e}")
    
    return count, freed


def main():
    parser = argparse.ArgumentParser(
        description="Clean up Zima Blue CLI temporary files and cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cleanup.py              # Interactive cleanup
  python scripts/cleanup.py --auto       # Auto cleanup without confirmation
  python scripts/cleanup.py --dry-run    # Preview what will be cleaned
  python scripts/cleanup.py --all        # Also clean log files
        """
    )
    parser.add_argument(
        "--auto", "-a",
        action="store_true",
        help="Auto mode, no confirmation"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Only show what would be cleaned"
    )
    parser.add_argument(
        "--all", "-A",
        action="store_true",
        help="Clean all including log files"
    )
    parser.add_argument(
        "--temp-only", "-t",
        action="store_true",
        help="Only clean system temp directories"
    )
    parser.add_argument(
        "--cache-only", "-c",
        action="store_true",
        help="Only clean project cache files"
    )
    
    args = parser.parse_args()
    
    # 收集要清理的内容
    to_cleanup = []
    categories = []
    
    if not args.temp_only:
        # 1. 项目缓存文件
        cache_files = find_cache_files()
        if cache_files:
            categories.append(("Project Cache", cache_files))
    
    if not args.cache_only:
        # 2. 系统临时目录
        temp_dirs = find_temp_dirs()
        if temp_dirs:
            categories.append(("System Temp Files", temp_dirs))
    
    if args.all:
        # 3. 日志文件（仅当 --all 时）
        log_files = find_log_files()
        if log_files:
            categories.append(("Log Files", log_files))
    
    if not categories:
        print("[OK] No files need to be cleaned!")
        return 0
    
    # 显示预览
    total_size = 0
    total_count = 0
    
    print("=" * 60)
    print("Zima Blue CLI - Cleanup Preview")
    print("=" * 60)
    
    for name, paths in categories:
        size = sum(get_size(p) for p in paths if p.exists())
        count = len(paths)
        total_size += size
        total_count += count
        print(f"\n{name}:")
        print(f"  Items: {count}")
        print(f"  Size: {format_size(size)}")
        if args.dry_run:
            for path in sorted(paths)[:10]:  # 最多显示10个
                rel_path = path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in path.parents else path
                print(f"    - {rel_path}")
            if len(paths) > 10:
                print(f"    ... and {len(paths) - 10} more")
    
    print(f"\n{'=' * 60}")
    print(f"Total: {total_count} items, {format_size(total_size)}")
    print("=" * 60)
    
    if args.dry_run:
        print("\n[DRY-RUN] No actual deletion performed")
        return 0
    
    # 确认
    if not args.auto:
        print()
        if args.all:
            print("[!] Warning: This will also delete log files!")
        response = input("Confirm cleanup? [y/N]: ").strip().lower()
        if response not in ('y', 'yes'):
            print("Cancelled")
            return 0
    
    # 执行清理
    print("\nStarting cleanup...")
    total_deleted = 0
    total_freed = 0
    
    for name, paths in categories:
        print(f"\n{name}:")
        count, freed = cleanup_paths(paths, dry_run=False)
        total_deleted += count
        total_freed += freed
    
    print(f"\n{'=' * 60}")
    print(f"Cleanup Complete!")
    print(f"Deleted: {total_deleted} items")
    print(f"Freed: {format_size(total_freed)}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

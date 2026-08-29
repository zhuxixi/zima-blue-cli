# Spec: 修复 flaky 测试 uuid 撞禁词（issue #192 + #177）

**Date**: 2026-08-29
**Issues**: #192（uuid 撞 "99"/"999"）、#177（同根因，Windows-only 误诊）
**Scope**: `tests/unit/test_executor_preexec.py`

## 背景

12 个 `fake_run` helper 用 `text = " ".join(cmd)` 拼接断言文本，命令里含 prompt 路径 `<temp>/test-pjob-<uuid8>/prompt.md`。uuid8 随机含 "99"（~2.7%）/"999"（~0.15%）时，`assert "99" not in text` / `assert "999" not in text` 误报。

## 调研验证（已完成，见 #192 评论）

- 确定性复现：patch `uuid.uuid4` → 固定 `99999999-...`，两个测试必挂，失败信息显示禁词只来自路径（渲染内容 `#42` 正确）。
- 修复验证：过滤 `.md` 路径后，同样碰撞 uuid 下两个测试必过，全文件 39 测试全过。

## 改动

1. 模块级 helper：

```python
def _cmd_text(cmd: list[str]) -> str:
    """Join command args for assertion text, excluding the prompt file path —
    its random uuid can collide with asserted-forbidden substrings (#192/#177)."""
    return " ".join(a for a in cmd if not a.endswith(".md"))
```

2. 12 处 `text = " ".join(cmd)` 全部替换为 `text = _cmd_text(cmd)`。

## 非目标

- 不改 executor 代码（uuid 命名是既有设计，路径碰撞只影响测试断言）
- 不改其他测试文件（先 grep 确认无同模式）

## 验收

- 确定性 repro（碰撞 uuid）下两个测试通过
- `tests/unit/` 全量通过
- 无其他测试文件存在同模式

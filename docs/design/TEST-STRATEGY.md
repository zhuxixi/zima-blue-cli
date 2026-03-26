# Zima CLI 测试策略

> 完整的单元测试和集成测试设计方案

---

## 📋 目录

1. [测试原则](#1-测试原则)
2. [测试架构](#2-测试架构)
3. [单元测试](#3-单元测试)
4. [集成测试](#4-集成测试)
5. [测试 Fixtures](#5-测试-fixtures)
6. [测试执行](#6-测试执行)

---

## 1. 测试原则

### 1.1 核心原则

| 原则 | 说明 |
|------|------|
| **隔离性** | 每个测试独立运行，测试数据互不干扰 |
| **可重复** | 测试可以任意次数重复执行，结果一致 |
| **自清理** | 测试结束后自动清理所有测试数据 |
| **确定性** | 测试结果唯一确定，无随机性 |
| **分层测试** | 单元测试快，集成测试全，E2E 测试真实 |

### 1.2 数据隔离策略

```
测试运行前:
1. 创建临时目录: /tmp/zima-test-{uuid}/
2. 设置环境变量: ZIMA_HOME=/tmp/zima-test-{uuid}
3. 所有测试数据写入临时目录

测试运行后:
1. 删除临时目录
2. 恢复环境变量
3. 验证无残留数据
```

---

## 2. 测试架构

### 2.1 目录结构

```
tests/
├── conftest.py              # 全局 fixtures
├── fixtures/                # 测试数据
│   ├── configs/             # 示例配置
│   │   ├── agent_kimi.yaml
│   │   ├── agent_claude.yaml
│   │   └── agent_gemini.yaml
│   └── templates/           # 示例模板
│       └── workflow.md
├── unit/                    # 单元测试
│   ├── __init__.py
│   ├── test_utils.py        # 工具函数测试
│   ├── test_config_manager.py
│   ├── test_models_base.py
│   └── test_models_agent.py
├── integration/             # 集成测试
│   ├── __init__.py
│   ├── fixtures.py          # 集成测试 fixtures
│   ├── test_agent_lifecycle.py    # Agent 完整生命周期
│   ├── test_agent_commands.py     # 各命令测试
│   └── test_config_isolation.py   # 隔离性测试
└── e2e/                     # E2E 测试
    ├── __init__.py
    └── test_cli_interface.py      # CLI 端到端
```

### 2.2 测试基类

```python
# tests/base.py
import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pytest


class TestIsolator:
    """测试隔离基类 - 所有测试继承此类"""
    
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch):
        """自动为每个测试创建隔离环境"""
        # 创建临时目录
        self.test_id = str(uuid.uuid4())[:8]
        self.temp_dir = Path(tempfile.gettempdir()) / f"zima-test-{self.test_id}"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 备份原环境变量
        self.original_zima_home = os.environ.get("ZIMA_HOME")
        
        # 设置隔离环境
        monkeypatch.setenv("ZIMA_HOME", str(self.temp_dir))
        
        # 创建必要的子目录
        (self.temp_dir / "configs" / "agents").mkdir(parents=True)
        (self.temp_dir / "configs" / "workflows").mkdir(parents=True)
        (self.temp_dir / "configs" / "variables").mkdir(parents=True)
        (self.temp_dir / "configs" / "envs").mkdir(parents=True)
        (self.temp_dir / "configs" / "pmgs").mkdir(parents=True)
        
        yield
        
        # 清理 - 测试结束后执行
        self._cleanup()
    
    def _cleanup(self):
        """清理测试数据"""
        # 删除临时目录
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # 验证清理成功
        assert not self.temp_dir.exists(), f"Failed to cleanup: {self.temp_dir}"
    
    def get_test_path(self, *parts) -> Path:
        """获取测试目录下的路径"""
        return self.temp_dir.joinpath(*parts)
    
    def assert_no_residual_data(self):
        """断言无残留数据"""
        configs_dir = self.temp_dir / "configs"
        if configs_dir.exists():
            for item in configs_dir.rglob("*"):
                if item.is_file():
                    pytest.fail(f"Residual test data found: {item}")


class AgentTestIsolator(TestIsolator):
    """Agent 测试专用隔离器"""
    
    @pytest.fixture
    def sample_agent_config(self):
        """提供示例 Agent 配置"""
        return {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {
                "code": "test-agent",
                "name": "测试 Agent",
                "description": "用于测试的 Agent"
            },
            "spec": {
                "type": "kimi",
                "parameters": {
                    "model": "kimi-k2-072515-preview",
                    "yolo": True
                },
                "defaults": {}
            },
            "createdAt": "2026-03-26T10:00:00Z",
            "updatedAt": "2026-03-26T10:00:00Z"
        }
    
    @pytest.fixture
    def create_test_agent(self, sample_agent_config):
        """创建测试 Agent 的工厂函数"""
        def _create(code: str = None, agent_type: str = "kimi"):
            config = sample_agent_config.copy()
            if code:
                config["metadata"]["code"] = code
                config["metadata"]["name"] = f"Test {code}"
            config["spec"]["type"] = agent_type
            
            # 保存到临时目录
            from zima.config.manager import ConfigManager
            manager = ConfigManager()
            manager.save_config("agent", config["metadata"]["code"], config)
            return config
        return _create
```

---

## 3. 单元测试

### 3.1 工具函数测试 (test_utils.py)

```python
import pytest
from pathlib import Path
import os
from zima import utils


class TestUtils:
    """工具函数单元测试"""
    
    class TestValidateCode:
        """测试 code 格式验证"""
        
        @pytest.mark.parametrize("code,expected", [
            ("test-agent", True),
            ("myagent123", True),
            ("a-b-c", True),
            ("agent-v1-0", True),
            ("Test-Agent", False),      # 大写字母
            ("test_agent", False),      # 下划线
            ("test.agent", False),      # 点号
            ("123-agent", False),       # 数字开头
            ("-test", False),           # 连字符开头
            ("test-", False),           # 连字符结尾
            ("", False),                # 空字符串
            ("a" * 65, False),          # 太长 (>64)
        ])
        def test_validate_code(self, code, expected):
            """验证各种 code 格式"""
            result = utils.validate_code(code)
            assert result == expected
    
    class TestPathUtils:
        """测试路径工具"""
        
        def test_get_zima_home_default(self, monkeypatch):
            """测试默认 ZIMA_HOME"""
            monkeypatch.delenv("ZIMA_HOME", raising=False)
            home = utils.get_zima_home()
            assert home == Path.home() / ".zima"
        
        def test_get_zima_home_from_env(self, monkeypatch):
            """测试从环境变量获取 ZIMA_HOME"""
            test_path = "/tmp/test-zima"
            monkeypatch.setenv("ZIMA_HOME", test_path)
            home = utils.get_zima_home()
            assert home == Path(test_path)
        
        def test_ensure_dir_creates_directory(self, tmp_path):
            """测试 ensure_dir 创建目录"""
            test_dir = tmp_path / "new" / "nested" / "dir"
            result = utils.ensure_dir(test_dir)
            assert test_dir.exists()
            assert result == test_dir
```

### 3.2 ConfigManager 测试 (test_config_manager.py)

```python
import pytest
from pathlib import Path
import yaml
from zima.config.manager import ConfigManager
from tests.base import TestIsolator


class TestConfigManager(TestIsolator):
    """ConfigManager 单元测试"""
    
    @pytest.fixture
    def manager(self):
        """提供 ConfigManager 实例"""
        return ConfigManager()
    
    class TestCRUD:
        """测试增删改查"""
        
        def test_save_and_load_config(self, manager):
            """测试保存和加载配置"""
            config = {"metadata": {"code": "test", "name": "Test"}, "spec": {}}
            
            # Save
            manager.save_config("agent", "test", config)
            
            # Load
            loaded = manager.load_config("agent", "test")
            assert loaded["metadata"]["code"] == "test"
        
        def test_config_exists(self, manager):
            """测试配置存在检查"""
            assert not manager.config_exists("agent", "nonexistent")
            
            manager.save_config("agent", "exists", {"metadata": {"code": "exists"}})
            assert manager.config_exists("agent", "exists")
        
        def test_delete_config(self, manager):
            """测试删除配置"""
            manager.save_config("agent", "to-delete", {"metadata": {"code": "to-delete"}})
            assert manager.config_exists("agent", "to-delete")
            
            result = manager.delete_config("agent", "to-delete")
            assert result is True
            assert not manager.config_exists("agent", "to-delete")
        
        def test_delete_nonexistent_config(self, manager):
            """测试删除不存在的配置"""
            result = manager.delete_config("agent", "nonexistent")
            assert result is False
        
        def test_list_configs(self, manager):
            """测试列出配置"""
            # 创建多个配置
            for i in range(3):
                manager.save_config("agent", f"agent-{i}", {
                    "metadata": {"code": f"agent-{i}", "name": f"Agent {i}"}
                })
            
            configs = manager.list_configs("agent")
            assert len(configs) == 3
            codes = [c["metadata"]["code"] for c in configs]
            assert "agent-0" in codes
            assert "agent-1" in codes
            assert "agent-2" in codes
    
    class TestTimestamp:
        """测试时间戳更新"""
        
        def test_updated_at_auto_update(self, manager):
            """测试 updated_at 自动更新"""
            config = {
                "metadata": {"code": "test"},
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z"
            }
            manager.save_config("agent", "test", config)
            
            # 修改后保存
            config["metadata"]["name"] = "Updated"
            manager.save_config("agent", "test", config)
            
            loaded = manager.load_config("agent", "test")
            assert loaded["updatedAt"] != "2026-01-01T00:00:00Z"
    
    class TestCopy:
        """测试复制功能"""
        
        def test_copy_config(self, manager):
            """测试复制配置"""
            source = {
                "metadata": {"code": "source", "name": "Source", "description": "Desc"},
                "spec": {"type": "kimi"}
            }
            manager.save_config("agent", "source", source)
            
            result = manager.copy_config("agent", "source", "target", "Target Name")
            assert result is True
            
            copied = manager.load_config("agent", "target")
            assert copied["metadata"]["code"] == "target"
            assert copied["metadata"]["name"] == "Target Name"
            assert copied["metadata"]["description"] == "Desc"
            assert copied["spec"]["type"] == "kimi"
```

### 3.3 Agent 模型测试 (test_models_agent.py)

```python
import pytest
from zima.models.agent import AgentConfig, Metadata
from tests.base import AgentTestIsolator


class TestAgentConfig(AgentTestIsolator):
    """AgentConfig 模型测试"""
    
    class TestCreate:
        """测试创建"""
        
        def test_create_kimi_agent(self):
            """测试创建 Kimi Agent"""
            config = AgentConfig.create(
                code="kimi-agent",
                name="Kimi Agent",
                agent_type="kimi"
            )
            
            assert config.metadata.code == "kimi-agent"
            assert config.type == "kimi"
            assert config.parameters["model"] == "kimi-k2-072515-preview"
            assert config.parameters["yolo"] is True
        
        def test_create_claude_agent(self):
            """测试创建 Claude Agent"""
            config = AgentConfig.create(
                code="claude-agent",
                name="Claude Agent",
                agent_type="claude"
            )
            
            assert config.type == "claude"
            assert config.parameters["model"] == "claude-sonnet-4-6"
        
        def test_create_with_custom_params(self):
            """测试创建时覆盖默认参数"""
            config = AgentConfig.create(
                code="custom",
                name="Custom",
                agent_type="kimi",
                parameters={"model": "custom-model", "yolo": False}
            )
            
            assert config.parameters["model"] == "custom-model"
            assert config.parameters["yolo"] is False
            # 其他默认参数仍保留
            assert "maxStepsPerTurn" in config.parameters
    
    class TestValidation:
        """测试验证"""
        
        def test_validate_valid_config(self):
            """测试有效配置"""
            config = AgentConfig.create("test", "Test", "kimi")
            errors = config.validate()
            assert errors == []
        
        def test_validate_missing_code(self):
            """测试缺少 code"""
            config = AgentConfig(type="kimi")
            errors = config.validate()
            assert any("code is required" in e for e in errors)
        
        def test_validate_unknown_type(self):
            """测试未知类型"""
            config = AgentConfig.create("test", "Test", "unknown-type")
            errors = config.validate()
            assert any("unknown type" in e for e in errors)
    
    class TestCommandBuild:
        """测试命令构建"""
        
        def test_build_kimi_command(self):
            """测试构建 Kimi 命令"""
            config = AgentConfig.create("test", "Test", "kimi")
            cmd = config.build_command(
                prompt_file="/tmp/prompt.md",
                work_dir="/tmp/workspace"
            )
            
            assert "kimi" in cmd
            assert "--print" in cmd
            assert "--yolo" in cmd
            assert "--prompt" in cmd
            assert "/tmp/prompt.md" in cmd
            assert "--work-dir" in cmd
        
        def test_build_claude_command(self):
            """测试构建 Claude 命令"""
            config = AgentConfig.create("test", "Test", "claude")
            cmd = config.build_command(prompt_file="/tmp/p.md")
            
            assert "claude" in cmd
            assert "--print" in cmd
```

---

## 4. 集成测试

### 4.1 Agent 完整生命周期测试 (test_agent_lifecycle.py)

```python
import subprocess
import pytest
from typer.testing import CliRunner
from zima.cli import app
from tests.base import AgentTestIsolator


runner = CliRunner()


class TestAgentLifecycle(AgentTestIsolator):
    """
    Agent 完整生命周期集成测试
    
    测试场景:
    1. 创建 Agent
    2. 查看列表
    3. 查看详情
    4. 更新配置
    5. 测试命令
    6. 删除 Agent
    7. 验证清理
    """
    
    def test_full_lifecycle(self):
        """完整生命周期测试"""
        agent_code = "lifecycle-test"
        
        # Step 1: 创建 Agent
        result = runner.invoke(app, [
            "agent", "create",
            "-n", "Lifecycle Test Agent",
            "-c", agent_code,
            "-t", "kimi",
            "-d", "For lifecycle testing"
        ])
        assert result.exit_code == 0
        assert "created successfully" in result.output
        
        # Step 2: 验证列表显示
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert agent_code in result.output
        assert "Lifecycle Test Agent" in result.output
        
        # Step 3: 查看详情
        result = runner.invoke(app, ["agent", "show", agent_code])
        assert result.exit_code == 0
        assert agent_code in result.output
        assert "kimi" in result.output
        
        # Step 4: 更新配置
        result = runner.invoke(app, [
            "agent", "update", agent_code,
            "--set-param", "model=kimi-k1.5",
            "--set-param", "yolo=false"
        ])
        assert result.exit_code == 0
        
        # 验证更新
        result = runner.invoke(app, ["agent", "show", agent_code, "--format", "json"])
        assert result.exit_code == 0
        assert "kimi-k1.5" in result.output
        
        # Step 5: 验证配置
        result = runner.invoke(app, ["agent", "validate", agent_code])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()
        
        # Step 6: 测试命令预览
        result = runner.invoke(app, ["agent", "test", agent_code])
        assert result.exit_code == 0
        assert "kimi" in result.output  # 命令中包含 kimi
        
        # Step 7: 删除 Agent
        result = runner.invoke(app, ["agent", "delete", agent_code, "-f"])
        assert result.exit_code == 0
        
        # Step 8: 验证删除
        result = runner.invoke(app, ["agent", "show", agent_code])
        assert result.exit_code != 0  # 应该失败
        
        # Step 9: 验证列表为空
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        # 列表应该为空或包含 "No agents"
    
    def test_create_multiple_agents(self):
        """测试创建多个 Agent"""
        agents = [
            ("agent-1", "kimi"),
            ("agent-2", "claude"),
            ("agent-3", "gemini"),
        ]
        
        # 批量创建
        for code, agent_type in agents:
            result = runner.invoke(app, [
                "agent", "create",
                "-n", f"Test {code}",
                "-c", code,
                "-t", agent_type
            ])
            assert result.exit_code == 0, f"Failed to create {code}"
        
        # 验证列表包含所有
        result = runner.invoke(app, ["agent", "list"])
        for code, _ in agents:
            assert code in result.output
        
        # 批量删除
        for code, _ in agents:
            result = runner.invoke(app, ["agent", "delete", code, "-f"])
            assert result.exit_code == 0
        
        # 验证全部删除
        result = runner.invoke(app, ["agent", "list"])
        for code, _ in agents:
            assert code not in result.output


class TestAgentEdgeCases(AgentTestIsolator):
    """边界情况测试"""
    
    def test_create_duplicate_code(self):
        """测试重复 code 创建失败"""
        # 创建第一个
        result = runner.invoke(app, [
            "agent", "create",
            "-n", "First",
            "-c", "duplicate-test"
        ])
        assert result.exit_code == 0
        
        # 创建第二个（应该失败）
        result = runner.invoke(app, [
            "agent", "create",
            "-n", "Second",
            "-c", "duplicate-test"
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output
        
        # 清理
        runner.invoke(app, ["agent", "delete", "duplicate-test", "-f"])
    
    def test_create_with_invalid_code(self):
        """测试无效 code 格式"""
        invalid_codes = [
            "123-start-with-number",
            "UPPERCASE",
            "with_underscore",
            "with.dot",
        ]
        
        for code in invalid_codes:
            result = runner.invoke(app, [
                "agent", "create",
                "-n", "Test",
                "-c", code
            ])
            assert result.exit_code != 0, f"Should reject: {code}"
            assert "Invalid code" in result.output or "invalid" in result.output.lower()
    
    def test_delete_nonexistent(self):
        """测试删除不存在的 Agent"""
        result = runner.invoke(app, ["agent", "delete", "nonexistent-xyz", "-f"])
        # 可以返回 0（幂等删除）或显示警告
        assert "not found" in result.output or result.exit_code == 0
    
    def test_copy_agent(self):
        """测试复制 Agent"""
        # 创建源 Agent
        result = runner.invoke(app, [
            "agent", "create",
            "-n", "Source Agent",
            "-c", "source-agent",
            "-t", "kimi",
            "--set-param", "model=custom-model"
        ])
        assert result.exit_code == 0
        
        # 复制
        result = runner.invoke(app, [
            "agent", "create",
            "-n", "Copied Agent",
            "-c", "copied-agent",
            "--from", "source-agent"
        ])
        assert result.exit_code == 0
        
        # 验证复制的内容
        result = runner.invoke(app, ["agent", "show", "copied-agent"])
        assert "custom-model" in result.output
        
        # 清理
        runner.invoke(app, ["agent", "delete", "source-agent", "-f"])
        runner.invoke(app, ["agent", "delete", "copied-agent", "-f"])
```

### 4.2 配置隔离性测试 (test_config_isolation.py)

```python
import os
import pytest
from pathlib import Path
from typer.testing import CliRunner
from zima.cli import app
from zima.config.manager import ConfigManager
from tests.base import TestIsolator


runner = CliRunner()


class TestConfigIsolation(TestIsolator):
    """
    测试配置隔离性
    
    验证每个测试使用独立的数据目录，互不干扰
    """
    
    def test_temp_dir_isolation(self):
        """测试临时目录隔离"""
        manager = ConfigManager()
        
        # 验证使用临时目录
        assert "zima-test-" in str(manager.config_dir)
        assert "/tmp" in str(manager.config_dir) or "Temp" in str(manager.config_dir)
    
    def test_config_not_leaking(self):
        """测试配置不会泄露到其他测试"""
        # 创建一个配置
        manager = ConfigManager()
        manager.save_config("agent", "isolation-test", {
            "metadata": {"code": "isolation-test"}
        })
        
        # 验证只能在当前测试的目录找到
        config_path = manager.get_config_path("agent", "isolation-test")
        assert config_path.exists()
        assert "zima-test-" in str(config_path)
    
    def test_env_var_isolation(self):
        """测试环境变量隔离"""
        # 验证 ZIMA_HOME 被设置为临时目录
        zima_home = os.environ.get("ZIMA_HOME")
        assert zima_home is not None
        assert "zima-test-" in zima_home
    
    def test_cleanup_after_test(self):
        """验证测试后数据被清理"""
        # 这个测试在 setup 中创建数据，在 teardown 中验证清理
        manager = ConfigManager()
        temp_dir = manager.config_dir
        
        # 创建一些数据
        manager.save_config("agent", "cleanup-test", {})
        
        # 测试结束时 _cleanup 应该删除整个目录
        # 这个验证在基类的 teardown 中自动完成
    
    def test_multiple_tests_independent(self):
        """测试多个测试完全独立"""
        manager = ConfigManager()
        
        # 记录当前配置数量
        initial_count = len(manager.list_configs("agent"))
        
        # 创建配置
        for i in range(5):
            manager.save_config("agent", f"test-{i}", {
                "metadata": {"code": f"test-{i}"}
            })
        
        # 验证数量
        assert len(manager.list_configs("agent")) == initial_count + 5
    
    def test_parallel_test_safety(self):
        """测试并行执行安全性"""
        # 使用唯一的 code 避免并行冲突
        import uuid
        unique_code = f"parallel-test-{uuid.uuid4().hex[:8]}"
        
        manager = ConfigManager()
        manager.save_config("agent", unique_code, {
            "metadata": {"code": unique_code}
        })
        
        # 验证只能找到自己的配置
        configs = manager.list_configs("agent")
        codes = [c["metadata"]["code"] for c in configs]
        assert unique_code in codes


class TestNoResidualData(TestIsolator):
    """验证无残留数据"""
    
    def test_no_orphaned_config_files(self):
        """测试没有孤立的配置文件"""
        manager = ConfigManager()
        
        # 创建然后删除
        for i in range(10):
            code = f"temp-{i}"
            manager.save_config("agent", code, {"metadata": {"code": code}})
            manager.delete_config("agent", code)
        
        # 验证目录为空
        agents_dir = manager._get_kind_dir("agent")
        if agents_dir.exists():
            files = list(agents_dir.glob("*.yaml"))
            assert len(files) == 0, f"Found orphaned files: {files}"
```

---

## 5. 测试 Fixtures

### 5.1 全局 Fixtures (conftest.py)

```python
import pytest
import tempfile
import shutil
from pathlib import Path
from uuid import uuid4


@pytest.fixture(scope="function")
def temp_dir():
    """提供临时目录，测试后自动清理"""
    path = Path(tempfile.mkdtemp(prefix="zima-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="function")
def isolated_zima_home(monkeypatch, temp_dir):
    """设置隔离的 ZIMA_HOME 环境"""
    monkeypatch.setenv("ZIMA_HOME", str(temp_dir))
    
    # 创建必要的子目录
    (temp_dir / "configs" / "agents").mkdir(parents=True)
    (temp_dir / "configs" / "workflows").mkdir(parents=True)
    (temp_dir / "configs" / "variables").mkdir(parents=True)
    (temp_dir / "configs" / "envs").mkdir(parents=True)
    (temp_dir / "configs" / "pmgs").mkdir(parents=True)
    
    yield temp_dir
    
    # 验证清理（可选）
    assert temp_dir.exists() is False or len(list(temp_dir.iterdir())) == 0


@pytest.fixture
def config_manager(isolated_zima_home):
    """提供配置管理器实例"""
    from zima.config.manager import ConfigManager
    return ConfigManager()


@pytest.fixture
def sample_agent_data():
    """提供示例 Agent 数据"""
    return {
        "apiVersion": "zima.io/v1",
        "kind": "Agent",
        "metadata": {
            "code": "sample-agent",
            "name": "Sample Agent",
            "description": "For testing"
        },
        "spec": {
            "type": "kimi",
            "parameters": {
                "model": "kimi-k2-072515-preview",
                "yolo": True
            },
            "defaults": {}
        }
    }


@pytest.fixture
def cli_runner():
    """提供 CLI Runner"""
    from typer.testing import CliRunner
    return CliRunner()
```

### 5.2 集成测试 Fixtures (integration/fixtures.py)

```python
import pytest
from pathlib import Path
from typer.testing import CliRunner
from zima.cli import app


@pytest.fixture(scope="function")
def integration_runner(isolated_zima_home):
    """提供配置好的 CLI Runner"""
    return CliRunner()


@pytest.fixture
def create_agent_factory(integration_runner):
    """Agent 创建工厂"""
    created_agents = []
    
    def _create(code: str, name: str = None, agent_type: str = "kimi", **kwargs):
        name = name or f"Test {code}"
        args = [
            "agent", "create",
            "-n", name,
            "-c", code,
            "-t", agent_type
        ]
        
        # 添加额外参数
        for key, value in kwargs.items():
            if key == "description":
                args.extend(["-d", value])
            elif key == "from_code":
                args.extend(["--from", value])
        
        result = integration_runner.invoke(app, args)
        if result.exit_code == 0:
            created_agents.append(code)
        return result
    
    yield _create
    
    # 清理
    for code in created_agents:
        integration_runner.invoke(app, ["agent", "delete", code, "-f"])
```

---

## 6. 测试执行

### 6.1 运行命令

```bash
# 运行所有测试
pytest

# 只运行单元测试
pytest tests/unit/

# 只运行集成测试
pytest tests/integration/

# 运行特定测试
pytest tests/unit/test_models_agent.py

# 运行特定测试函数
pytest tests/integration/test_agent_lifecycle.py::TestAgentLifecycle::test_full_lifecycle

# 并行运行（需要 pytest-xdist）
pytest -n auto

# 带覆盖率报告
pytest --cov=zima --cov-report=html

# 详细输出
pytest -v -s

# 失败即停
pytest -x
```

### 6.2 CI/CD 配置

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.9", "3.10", "3.11"]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    
    - name: Run tests
      run: |
        pytest tests/ -v --cov=zima --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### 6.3 测试要求清单

| 要求 | 标准 |
|------|------|
| 单元测试覆盖率 | > 80% |
| 集成测试覆盖率 | 所有命令至少一个测试 |
| 测试执行时间 | < 30 秒（单元测试） |
| 隔离性验证 | 每个测试后无残留数据 |
| 并发安全 | 支持并行执行（pytest-xdist） |

---

> "测试是信心的来源。" —— Zima Blue

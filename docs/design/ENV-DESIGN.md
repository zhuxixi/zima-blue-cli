# Env 配置设计文档

> Env 定义环境变量配置，用于启动 Agent 时注入环境变量，支持敏感信息管理和多来源密钥读取。

---

## 📋 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [Schema 定义](#3-schema-定义)
4. [敏感信息管理](#4-敏感信息管理)
5. [CLI 命令设计](#5-cli-命令设计)
6. [使用示例](#6-使用示例)
7. [测试方案](#7-测试方案)
8. [实现阶段](#8-实现阶段)

---

## 1. 概述

### 1.1 什么是 Env

Env 是 **环境变量配置**，定义了启动 Agent 时需要注入的环境变量。它：

- 按 **Agent 类型** 分组（kimi/claude/gemini 有不同的环境变量需求）
- 支持 **敏感信息管理**（API Keys、密码等），从多种来源安全读取
- 支持 **变量覆盖控制**（是否覆盖系统中已存在的环境变量）
- 支持 **导出** 为 `.env` 文件或 shell 脚本

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **类型隔离** | 每个 Env 配置只对应一种 Agent 类型 |
| **安全优先** | 敏感信息从不直接存储，而是引用外部来源 |
| **灵活来源** | 支持 env/file/cmd/vault 多种密钥来源 |
| **幂等注入** | 支持控制是否覆盖已存在的环境变量 |

### 1.3 文件位置

```
~/.zima/configs/envs/{code}.yaml
```

---

## 2. 核心概念

### 2.1 Env 使用流程

```
创建 Env 配置
    ├─ 定义普通变量 (VAR=value)
    └─ 定义敏感变量 (引用外部来源)
            ↓
关联到 Agent
    └─ agent.defaults.env = env-code
            ↓
启动 Agent 时
    ├─ 读取 Env 配置
    ├─ 解析敏感变量（从各来源读取实际值）
    ├─ 合并到当前环境
    └─ 启动 Agent 进程
```

### 2.2 敏感信息来源

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Source    │     │   Config    │     │   Runtime   │
│   Type      │  →  │   (YAML)    │  →  │   (Value)   │
├─────────────┤     ├─────────────┤     ├─────────────┤
│ env         │     │ env: KEY    │     │ $KEY value  │
│ file        │     │ file: path  │     │ file content│
│ cmd         │     │ cmd: command│     │ cmd output  │
│ vault       │     │ vault: path │     │ vault value │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## 3. Schema 定义

### 3.1 完整结构

```yaml
apiVersion: zima.io/v1
kind: Env
metadata:
  code: kimi-prod               # 唯一编码
  name: Kimi 生产环境            # 显示名称
  description: 生产环境 API 配置  # 描述
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 适用的 Agent 类型
  forType: kimi
  
  # 普通环境变量（直接存储值）
  variables:
    KIMI_BASE_URL: "https://api.moonshot.cn"
    KIMI_TIMEOUT: "30"
    HTTPS_PROXY: "http://proxy.company.com:8080"
    TZ: "Asia/Shanghai"
    LANG: "zh_CN.UTF-8"
    DEBUG: "false"
  
  # 敏感信息引用（安全存储）
  secrets:
    - name: KIMI_API_KEY
      source: env               # 从环境变量读取
      key: MY_KIMI_KEY          # 源环境变量名
    
    - name: AWS_ACCESS_KEY_ID
      source: file              # 从文件读取
      path: "~/.aws/access_key"
    
    - name: DATABASE_PASSWORD
      source: cmd               # 从命令输出读取
      command: "pass show db/password"
    
    - name: VAULT_TOKEN
      source: vault             # 从 HashiCorp Vault 读取
      path: "secret/zima/token"
      field: "value"
  
  # 是否覆盖已存在的环境变量
  overrideExisting: false
```

### 3.2 字段详解

#### metadata

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 唯一标识符，小写字母/数字/连字符 |
| `name` | string | ✅ | 人类可读名称 |
| `description` | string | ❌ | 描述说明 |

#### spec.forType

指定该环境变量组适用于哪种 Agent 类型。

| 值 | 说明 | 典型变量 |
|----|------|----------|
| `kimi` | Kimi Code CLI | `KIMI_API_KEY`, `KIMI_BASE_URL` |
| `claude` | Claude Code CLI | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` |
| `gemini` | Gemini CLI | `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` |

#### spec.variables

普通环境变量，KV 结构，值直接存储在配置文件中。

**注意**：所有值都存储为字符串，Agent 启动时按需转换。

#### spec.secrets

敏感信息配置，支持多种来源：

| source | 说明 | 附加字段 |
|--------|------|----------|
| `env` | 从当前环境变量读取 | `key`: 源环境变量名 |
| `file` | 从文件读取（支持 `~` 展开） | `path`: 文件路径 |
| `cmd` | 从命令输出读取（去除首尾空白） | `command`: 命令字符串 |
| `vault` | 从 HashiCorp Vault 读取 | `path`: 密钥路径, `field`: 字段名 |

#### spec.overrideExisting

- `true`: 强制覆盖系统中已存在的环境变量
- `false` (默认): 保留已有值，仅注入不存在的变量

---

## 4. 敏感信息管理

### 4.1 安全原则

1. **配置文件不存储敏感值**：只存储引用方式
2. **运行时解析**：Agent 启动时才读取实际值
3. **内存中短暂存在**：解析后立即注入环境，不保留副本
4. **日志脱敏**：输出时自动隐藏敏感值

### 4.2 来源解析示例

**env 来源**：
```yaml
secrets:
  - name: KIMI_API_KEY
    source: env
    key: MY_KIMI_KEY    # 从 $MY_KIMI_KEY 读取
```
运行时：`KIMI_API_KEY = os.environ.get("MY_KIMI_KEY")`

**file 来源**：
```yaml
secrets:
  - name: KIMI_API_KEY
    source: file
    path: "~/.keys/kimi.key"  # 支持 ~ 展开
```
运行时：`KIMI_API_KEY = Path("~/.keys/kimi.key").expanduser().read_text().strip()`

**cmd 来源**：
```yaml
secrets:
  - name: KIMI_API_KEY
    source: cmd
    command: "pass show kimi/api-key"  # 使用 password-store
```
运行时：`KIMI_API_KEY = subprocess.check_output("pass show kimi/api-key", shell=True).decode().strip()`

**vault 来源**：
```yaml
secrets:
  - name: KIMI_API_KEY
    source: vault
    path: "secret/zima/kimi"
    field: "api_key"
```
运行时：通过 Vault API 读取

### 4.3 解析失败处理

| 场景 | 行为 |
|------|------|
| 来源不存在 | 报错，Agent 启动失败 |
| 来源为空值 | 视为空字符串注入（或报错，可配置） |
| 命令执行失败 | 报错，显示命令退出码和 stderr |
| 权限不足 | 报错，提示检查文件/密钥权限 |

---

## 5. CLI 命令设计

### 5.1 命令概览

```bash
zima env create        # 创建 Env 配置
zima env list          # 列出 Env 配置
zima env show          # 查看详情
zima env update        # 更新配置
zima env delete        # 删除配置
zima env validate      # 验证配置
zima env set           # 设置环境变量
zima env unset         # 移除环境变量
zima env get           # 获取环境变量值（支持解析 secrets）
zima env export        # 导出为 .env 或 shell 脚本
```

### 5.2 命令详情

#### create

```bash
zima env create \
  --code kimi-prod \
  --name "Kimi 生产环境" \
  --for-type kimi \
  --description "生产环境 API 配置" \
  [--from existing-env]  # 从现有配置复制
```

**功能**：
- 创建新的 Env 配置
- 必须指定 `--for-type`（kimi/claude/gemini）
- 可选 `--from` 复制现有配置
- 验证 code 格式和唯一性

#### list

```bash
zima env list [options]

Options:
  --format yaml|json|table   # 输出格式（默认 table）
  --for-type <type>          # 按类型过滤
```

**示例输出**：
```
CODE              NAME              TYPE      VARS    SECRETS
kimi-prod         Kimi 生产环境      kimi      4       1
kimi-dev          Kimi 开发环境      kimi      4       0
claude-glm        Claude GLM 代理   claude    2       1
```

#### show

```bash
zima env show <code> [options]

Options:
  --format yaml|json       # 输出格式（默认 yaml）
  --resolve-secrets        # 解析并显示 secret 实际值（慎用）
```

**注意**：默认情况下 secrets 显示为 `<secret:source>`，使用 `--resolve-secrets` 才显示实际值。

#### update

```bash
zima env update <code> [options]

Options:
  --name <name>                    # 更新名称
  --description <desc>             # 更新描述
  --override-existing true|false   # 更新覆盖规则
```

#### delete

```bash
zima env delete <code> [--force]
```

#### validate

```bash
zima env validate <code>
```

**验证内容**：
- YAML 格式正确性
- 必需字段完整性
- forType 有效性
- secrets 配置语法
- 引用的文件/命令是否可访问（可选）

#### set

```bash
zima env set <code> \
  --key KEY_NAME \
  --value "value" \
  [--secret]                    # 标记为敏感（从环境变量引用）
  [--source env|file|cmd]       # 指定来源类型
  [--source-key <key>]          # 来源键名（env 类型用）
  [--source-path <path>]        # 来源路径（file 类型用）
  [--source-cmd <command>]      # 来源命令（cmd 类型用）
```

**示例**：
```bash
# 设置普通变量
zima env set kimi-prod --key DEBUG --value "true"

# 设置敏感变量（从当前环境变量读取）
zima env set kimi-prod --key KIMI_API_KEY --secret --source env --source-key MY_KIMI_KEY

# 设置敏感变量（从文件读取）
zima env set kimi-prod --key KIMI_API_KEY --secret --source file --source-path "~/.keys/kimi"

# 设置敏感变量（从命令读取）
zima env set kimi-prod --key KIMI_API_KEY --secret --source cmd --source-cmd "pass show kimi/api"
```

#### unset

```bash
zima env unset <code> --key KEY_NAME
```

#### get

```bash
zima env get <code> --key KEY_NAME [--resolve]
```

**功能**：获取环境变量值。普通变量直接返回，secret 默认返回 `<secret:source>`，使用 `--resolve` 解析实际值。

#### export

```bash
zima env export <code> [options]

Options:
  --format dotenv|shell|json    # 导出格式（默认 dotenv）
  --output <file>               # 输出到文件
  --resolve-secrets             # 解析 secrets（默认不解密）
```

**格式示例**：

`dotenv` 格式（默认）：
```bash
# Kimi 生产环境
KIMI_BASE_URL=https://api.moonshot.cn
KIMI_TIMEOUT=30
# KIMI_API_KEY=<secret:env>  # 未解析时
KIMI_API_KEY=sk-actual-key-here  # 解析后
```

`shell` 格式：
```bash
#!/bin/bash
export KIMI_BASE_URL="https://api.moonshot.cn"
export KIMI_API_KEY="sk-actual-key-here"
```

`json` 格式：
```json
{
  "KIMI_BASE_URL": "https://api.moonshot.cn",
  "KIMI_API_KEY": "sk-actual-key-here"
}
```

---

## 6. 使用示例

### 6.1 Kimi 生产环境配置

```bash
# 创建配置
zima env create \
  --code kimi-prod \
  --name "Kimi 生产环境" \
  --for-type kimi \
  --description "生产环境 API 配置，使用官方 API"

# 设置普通变量
zima env set kimi-prod --key KIMI_BASE_URL --value "https://api.moonshot.cn"
zima env set kimi-prod --key KIMI_TIMEOUT --value "30"
zima env set kimi-prod --key TZ --value "Asia/Shanghai"

# 设置敏感变量（从环境变量读取）
zima env set kimi-prod --key KIMI_API_KEY --secret \
  --source env --source-key MY_KIMI_API_KEY

# 验证
zima env validate kimi-prod

# 导出查看
zima env export kimi-prod --format dotenv
```

### 6.2 Claude 第三方代理配置

```bash
# 创建配置
zima env create \
  --code claude-glm \
  --name "Claude GLM 代理" \
  --for-type claude \
  --description "通过 GLM 代理访问 Claude API"

# 设置变量
zima env set claude-glm --key ANTHROPIC_BASE_URL --value "https://api.glm.cn/claude"
zima env set claude-glm --key ANTHROPIC_API_KEY --secret \
  --source env --source-key GLM_API_KEY

# 查看配置
zima env show claude-glm
```

### 6.3 在 Agent 中使用

```bash
# 创建 Agent 时指定环境
zima agent create \
  --code my-agent \
  --name "My Agent" \
  --type kimi \
  --env kimi-prod  # 关联环境配置

# 查看 Agent 详情时会显示关联的 Env
zima agent show my-agent
```

### 6.4 导出环境变量脚本

```bash
# 导出为 shell 脚本（用于 CI/CD）
zima env export kimi-prod --format shell --output ./env.sh --resolve-secrets

# 在脚本中使用
source ./env.sh
kimi --prompt task.md
```

---

## 7. 测试方案

### 7.1 单元测试

#### EnvConfig 模型测试 (`tests/unit/test_models_env.py`)

```python
class TestEnvConfig:
    """EnvConfig 模型单元测试"""
    
    class TestCreate:
        """测试创建"""
        
        test_create_basic()           # 基础创建
        test_create_with_variables()  # 带普通变量
        test_create_with_secrets()    # 带敏感变量
        test_create_invalid_type()    # 无效类型抛出异常
        test_create_from_dict()       # 从字典反序列化
    
    class TestValidation:
        """测试验证"""
        
        test_validate_valid()              # 有效配置
        test_validate_missing_code()       # 缺少 code
        test_validate_invalid_code()       # 无效 code 格式
        test_validate_missing_name()       # 缺少 name
        test_validate_invalid_for_type()   # 无效 forType
        test_validate_empty_secrets()      # 空 secrets
        test_validate_invalid_secret_source()  # 无效 secret 来源
    
    class TestSecretResolution:
        """测试敏感信息解析"""
        
        test_resolve_env_source()      # env 来源
        test_resolve_file_source()     # file 来源
        test_resolve_cmd_source()      # cmd 来源
        test_resolve_file_not_found()  # 文件不存在报错
        test_resolve_cmd_failed()      # 命令执行失败报错
        test_resolve_missing_env()     # 环境变量不存在报错
    
    class TestVariableManagement:
        """测试变量管理"""
        
        test_set_variable()            # 设置普通变量
        test_set_secret()              # 设置敏感变量
        test_unset_variable()          # 删除变量
        test_get_variable()            # 获取变量
        test_list_variables()          # 列出所有变量
        test_list_secrets()            # 列出所有 secrets
    
    class TestExport:
        """测试导出功能"""
        
        test_export_dotenv()           # 导出 .env 格式
        test_export_shell()            # 导出 shell 格式
        test_export_json()             # 导出 JSON 格式
        test_export_with_secrets()     # 导出时解析 secrets
        test_export_mask_secrets()     # 导出时隐藏 secrets
```

### 7.2 集成测试

#### Env CLI 测试 (`tests/integration/test_env_commands.py`)

```python
class TestEnvCreate:
    """测试 env create 命令"""
    
    test_create_basic()                # 基础创建
    test_create_with_variables()       # 创建时指定变量
    test_create_duplicate_code_fails() # 重复 code 失败
    test_create_invalid_type_fails()   # 无效类型失败
    test_create_from_existing()        # 从现有复制


class TestEnvSet:
    """测试 env set 命令"""
    
    test_set_variable()                # 设置普通变量
    test_set_secret_env_source()       # 设置 secret (env)
    test_set_secret_file_source()      # 设置 secret (file)
    test_set_secret_cmd_source()       # 设置 secret (cmd)
    test_set_update_existing()         # 更新已有变量


class TestEnvGet:
    """测试 env get 命令"""
    
    test_get_variable()                # 获取普通变量
    test_get_secret_masked()           # 获取 secret 显示掩码
    test_get_secret_resolved()         # 获取 secret 解析值
    test_get_nonexistent()             # 获取不存在的变量


class TestEnvExport:
    """测试 env export 命令"""
    
    test_export_dotenv()               # 导出 dotenv
    test_export_shell()                # 导出 shell
    test_export_json()                 # 导出 json
    test_export_with_resolved_secrets()  # 导出时解析 secrets
    test_export_to_file()              # 导出到文件


class TestEnvLifecycle:
    """测试完整生命周期"""
    
    test_full_lifecycle():
        # 创建 → 设置变量 → 设置 secret → 验证 → 导出 → 更新 → 删除
```

### 7.3 安全测试

```python
class TestEnvSecurity:
    """安全相关测试"""
    
    test_secrets_not_in_config_file()    # secrets 不写入配置文件
    test_secrets_masked_in_show()        # show 命令默认掩码 secrets
    test_secrets_masked_in_list()        # list 命令掩码 secrets
    test_export_requires_explicit_resolve()  # 导出需要显式 --resolve-secrets
    test_logs_do_not_contain_secrets()   # 日志不包含敏感值
```

### 7.4 测试 Fixtures

```python
@pytest.fixture
def sample_env_config():
    """提供示例 Env 配置"""
    return {
        "apiVersion": "zima.io/v1",
        "kind": "Env",
        "metadata": {
            "code": "test-env",
            "name": "Test Environment"
        },
        "spec": {
            "forType": "kimi",
            "variables": {
                "KIMI_TIMEOUT": "30",
                "DEBUG": "false"
            },
            "secrets": [
                {"name": "KIMI_API_KEY", "source": "env", "key": "TEST_KIMI_KEY"}
            ],
            "overrideExisting": False
        }
    }


@pytest.fixture
def mock_secret_sources(monkeypatch, tmp_path):
    """模拟各种 secret 来源"""
    # 设置环境变量
    monkeypatch.setenv("TEST_KIMI_KEY", "sk-test-key")
    
    # 创建临时密钥文件
    key_file = tmp_path / "test_key.txt"
    key_file.write_text("sk-file-key")
    
    return {"env_key": "TEST_KIMI_KEY", "file_path": str(key_file)}
```

### 7.5 测试覆盖率目标

| 模块 | 目标覆盖率 | 关键路径 |
|------|-----------|----------|
| EnvConfig 模型 | 95% | 创建、验证、secret 解析、导出 |
| Secret 解析器 | 100% | 所有来源类型、错误处理 |
| CLI 命令 | 90% | 所有子命令的正常和异常路径 |
| 安全功能 | 100% | 掩码、解析控制、日志脱敏 |

---

## 8. 实现阶段

### Phase 1: 模型层

- [ ] `EnvConfig` 数据模型
- [ ] `SecretDef` 敏感信息定义
- [ ] `SecretResolver` 解析器（env/file/cmd/vault）
- [ ] 变量管理方法（set/unset/get/list）
- [ ] 导出功能（dotenv/shell/json）
- [ ] 单元测试（45+ 测试）

### Phase 2: CLI 命令

- [ ] `zima env create`
- [ ] `zima env list`
- [ ] `zima env show`
- [ ] `zima env update`
- [ ] `zima env delete`
- [ ] `zima env validate`
- [ ] `zima env set`
- [ ] `zima env unset`
- [ ] `zima env get`
- [ ] `zima env export`
- [ ] 集成测试（35+ 测试）

### Phase 3: 安全加固

- [ ] Secret 掩码显示
- [ ] 日志脱敏
- [ ] `--resolve-secrets` 显式确认
- [ ] 文件权限检查
- [ ] 安全测试（10+ 测试）

---

> "安全不是功能，而是设计原则。" —— Zima Blue

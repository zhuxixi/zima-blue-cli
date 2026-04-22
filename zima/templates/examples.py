"""Example YAML templates for each entity type."""

from __future__ import annotations

AGENT_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: my-agent
  name: My Agent
  description: "An example agent"
spec:
  type: kimi
  parameters:
    model: moonshot-v1-8k
  defaults:
    workflow: my-workflow
    env: my-env
"""

WORKFLOW_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: my-workflow
  name: My Workflow
  description: "An example workflow"
spec:
  format: jinja2
  template: |
    You are {{ role }}.
    Please help me with {{ task }}.
  variables:
    - name: role
      type: string
      required: true
      description: "Agent role"
    - name: task
      type: string
      required: true
      description: "Task description"
  tags: [example]
  author: ""
  version: "1.0.0"
"""

VARIABLE_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: my-variables
  name: My Variables
  description: "Example variables"
spec:
  forWorkflow: my-workflow
  values:
    role: "senior developer"
    task: "code review"
"""

ENV_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Env
metadata:
  code: my-env
  name: My Environment
  description: "Example env config"
spec:
  forType: kimi
  variables:
    DEBUG: "false"
  secrets:
    - name: API_KEY
      source: env
      key: MY_API_KEY
  overrideExisting: false
"""

PMG_EXAMPLE = """\
apiVersion: zima.io/v1
kind: PMG
metadata:
  code: my-pmg
  name: My Parameter Group
  description: "Example PMG"
spec:
  forTypes: [kimi, claude]
  parameters:
    - name: verbose
      type: flag
      enabled: true
    - name: model
      type: long
      value: "moonshot-v1-8k"
"""

PJOB_EXAMPLE = """\
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: my-job
  name: My Job
  description: "Example PJob"
  labels: [example]
spec:
  agent: my-agent
  workflow: my-workflow
  variable: my-variables
  env: my-env
  pmg: my-pmg
  execution:
    workDir: .
    timeout: 600
    keepTemp: false
  output:
    saveTo: ./output.md
    format: raw
    append: false
"""

SCHEDULE_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Schedule
metadata:
  code: daily-32
  name: "Daily 32-cycle Schedule"
spec:
  cycleMinutes: 45
  dailyCycles: 32
  stages:
    - name: work
      offsetMinutes: 0
      durationMinutes: 20
    - name: rest
      offsetMinutes: 20
      durationMinutes: 15
    - name: dream
      offsetMinutes: 35
      durationMinutes: 10
  cycleTypes:
    - typeId: A
      work: [pjob-a1]
      rest: [pjob-a2]
      dream: [pjob-a3]
  cycleMapping:
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - A
    - A
    - idle
    - idle
"""

REVIEWER_WORKFLOW = """\
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: reviewer-cr
  name: PR Code Review
  description: Review a PR diff and output structured review result
spec:
  format: jinja2
  template: |
    ## 背景
    你是一个专业的代码审查员。请审查以下 Pull Request 的代码变更。

    ## PR 信息
    - 仓库: {{repo}}
    - PR 编号: #{{pr_number}}
    - PR 标题: {{pr_title}}

    ## 代码变更 (Diff)
    ```diff
    {{pr_diff}}
    ```

    ## 需求
    1. 检查代码逻辑是否正确
    2. 检查是否有潜在 bug
    3. 检查代码风格和命名规范
    4. 检查是否有安全问题
    5. 检查测试是否充分

    ## 规则
    - 只关注代码本身，不评论作者
    - 发现问题必须指出具体位置和原因
    - 如果代码没问题，直接给出通过结论
    - 输出必须使用以下 XML 格式

    ## 输出格式
    在回复的最后，必须包含以下 XML 块：

    ```xml
    <zima-review>
      <verdict>approved|needs_fix|needs_discussion</verdict>
      <summary>一句话总结审查结论</summary>
      <issues>
        <issue severity="error|warning|info" file="文件名" line="行号">问题描述</issue>
      </issues>
    </zima-review>
    ```

    ## 结束指标
    - 审查完成并输出了 `<zima-review>` XML 块
    - verdict 明确为 approved / needs_fix / needs_discussion 之一
  variables:
    - name: repo
      type: string
      required: true
      description: Repository slug (owner/repo)
    - name: pr_number
      type: string
      required: true
      description: PR number
    - name: pr_title
      type: string
      required: true
      description: PR title
    - name: pr_diff
      type: string
      required: true
      description: PR diff content
"""

EXAMPLES = {
    "agent": {"my-agent": AGENT_EXAMPLE},
    "workflow": {"my-workflow": WORKFLOW_EXAMPLE, "reviewer-cr": REVIEWER_WORKFLOW},
    "variable": {"my-variables": VARIABLE_EXAMPLE},
    "env": {"my-env": ENV_EXAMPLE},
    "pmg": {"my-pmg": PMG_EXAMPLE},
    "pjob": {"my-job": PJOB_EXAMPLE},
    "schedule": {"daily-32": SCHEDULE_EXAMPLE},
}

VALID_KINDS = {"Agent", "Workflow", "Variable", "Env", "PMG", "PJob", "Schedule"}

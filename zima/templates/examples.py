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
    - idle
    - A
"""

EXAMPLES = {
    "agent": AGENT_EXAMPLE,
    "workflow": WORKFLOW_EXAMPLE,
    "variable": VARIABLE_EXAMPLE,
    "env": ENV_EXAMPLE,
    "pmg": PMG_EXAMPLE,
    "pjob": PJOB_EXAMPLE,
    "schedule": SCHEDULE_EXAMPLE,
}

VALID_KINDS = {"Agent", "Workflow", "Variable", "Env", "PMG", "PJob", "Schedule"}

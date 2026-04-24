# Changelog

## [0.3.0] - 2026-04-24

### Features
- add zima quickstart interactive wizard (#54) (#59)
- **serialization**: add core serialization module for snake_case/camelCase mapping (#14)
- PR CR automation with postExec actions (#56)
- **templates**: add reviewer PJob and variable configs
- **templates**: add reviewer-cr workflow template
- **executor**: integrate postExec actions after agent execution
- **execution**: add ActionsRunner for postExec automation
- **pjob**: add actions field to PJobSpec for post-exec automation
- **models**: add PostExecAction and ActionsConfig for PJob automation
- **github**: add GitHubOps wrapper for gh CLI
- **review**: add ReviewParser for structured review output
- **review**: add ReviewResult and ReviewIssue dataclasses
- **agent**: omit --model flag by default for all agent types (#55)

### Fixes
- allow list deserialization to handle non-dict items via from_dict()
- **serialization**: address round-1 CR feedback on PR #58
- address round-4 CR feedback + lint
- address round-3 CR feedback
- address round-2 CR feedback
- address CR feedback on PR CR automation
- **commands**: avoid list builtin shadowing in --example flag handlers

### Changes
- add implementation plan for issue #60 (remove gemini agent type)
- add spec for issue #60 (remove gemini agent type)
- type: ExtendDef.from_dict accepts dict | str
- convert serialization.py docstrings to Google style
- style: remove unused omit_empty import from pjob.py
- migrate package management from pip to uv (#51)
- test: add round-trip tests for all models with auto serialization (#14) (#14)
- migrate Schedule models to YamlSerializable with auto mapping (#14)
- migrate Actions models to YamlSerializable with auto mapping (#14)
- migrate PJob nested classes to YamlSerializable with auto mapping (#14)
- migrate Env/Variable/PMG/Workflow/Agent configs to auto spec mapping (#14)
- BaseConfig and Metadata use YamlSerializable with auto spec mapping (#14)
- implementation plan for issue #14 - unified camelCase/snake_case serialization
- design spec for issue #14 - unified camelCase/snake_case serialization
- style: black formatting
- test(integration): add end-to-end reviewer flow test

[0.3.0]: https://github.com/zhuxixi/zima-blue-cli/compare/v0.2.0...v0.3.0

## [0.2.0] - 2026-04-22

### Features
- add release skill for version bump and GitHub Release automation
- **executor**: move PJob temp dir from system temp to ZIMA_HOME (#47)
- automated verification suite for issue #38 (#44)

### Fixes
- **release-skill**: use uv run and add uv.lock to bump workflow
- update AGENTS.md temp path, use temp_dir fixture in tests (#47)
- **pjob**: background log dir respects ZIMA_HOME (#48)
- add --version/-v flag to zima CLI (#46)
- **daemon**: error handling improvements in daemon commands (#41)

### Changes
- Merge pull request #50 from zhuxixi/fix/issue-47-pjob-temp-dir
- update CLAUDE.md Data Layout with temp/pjobs/ directory (#47)
- update session history
- fix data layout docs to match actual implementation (Issue #43)
- style: fix black formatting in mock_agent.py (#45) (#45)

[0.2.0]: https://github.com/zhuxixi/zima-blue-cli/compare/v0.1.1...v0.2.0

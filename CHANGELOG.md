# Changelog

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

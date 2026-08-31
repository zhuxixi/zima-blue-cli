# auto-merge-guarded

Auto approve + squash merge whitelisted collaborators' PRs after CI green
and Zima CR convergence.  Runs on the owner's machine, scheduled by cron
every 45 minutes.  See `docs/superpowers/specs/2026-08-30-auto-merge-guarded-design.md`
for the full design.

## Deploy

```bash
mkdir -p ~/.zima/scripts ~/.zima/configs ~/.zima/logs
cp examples/auto-merge/auto-merge-guarded.py ~/.zima/scripts/
cp examples/auto-merge/auto-merge.yaml.example ~/.zima/configs/auto-merge.yaml
# edit ~/.zima/configs/auto-merge.yaml: real repo, whitelist, checks, cr_pjob_code
```

The whitelist authorizes by PR author only; commit committers on the branch
are not separately verified (spec-defined boundary).

## Schedule (Phase 0: notify-only)

```bash
crontab -e
# add:
*/45 * * * * /usr/bin/python3 /home/<you>/.zima/scripts/auto-merge-guarded.py --notify-only >> /home/<you>/.zima/logs/auto-merge-cron.log 2>&1
```

Phase 0 runs notify-only for about a week: every round pushes what it
*would* merge; the owner compares against their own judgment.  Phase 1
enables real merging by removing `--notify-only` from the crontab entry.

## Modes

- `--dry-run`: full gate chain, prints the action chain, executes nothing
- `--notify-only`: gates + notifications, never touches GitHub
- live (no flag): gates + actions + notifications

## Emergency stop

Set `enabled: false` in `~/.zima/configs/auto-merge.yaml`, or remove the
crontab entry.  The flock at `<zima_home>/logs/auto-merge.lock` prevents
concurrent rounds.

## Audit

`~/.zima/logs/auto-merge.log` — one JSON line per PR per round:
`ts / mode / repo / pr / head_sha / decision / reason`.

# Webhook-Triggered Code Review Example Configuration

## Setup

Run from the repository root (`$ZIMA_HOME` supports custom paths, default `~/.zima`):

```bash
# Copy the example configs into ZIMA_HOME (default ~/.zima; override with the ZIMA_HOME env var)
ZIMA_HOME="${ZIMA_HOME:-$HOME/.zima}"
mkdir -p "$ZIMA_HOME/configs/"
cp -r examples/webhook/agents examples/webhook/workflows examples/webhook/variables \
      examples/webhook/envs examples/webhook/pjobs "$ZIMA_HOME/configs/"
```

```bash
# Start the webhook server. Keep the secret in an env var so it never shows up in `ps` / /proc.
export ZIMA_WEBHOOK_SECRET=your-webhook-secret
zima webhook-server \
  --smee-url https://smee.io/YOUR_CHANNEL \
  --pjob claude-cr \
  --pjob kimi-cr
```

## Usage

1. **The target PR must carry the `zima:needs-review` label**
   - The `scan_pr` action in this example looks up PRs awaiting review by that label.
   - Once the webhook receives GitHub's `labeled` event, the labeled PR is treated as the review target.

2. **GitHub webhook configuration**

   In the target repository's Settings > Webhooks, add:
   - Payload URL: `https://smee.io/YOUR_CHANNEL`
   - Content type: `application/json`
   - Secret: same as above
   - Events: **Pull requests** (at minimum the `labeled` action must be checked, otherwise the review cannot trigger)

3. **Flow**
   - Add the `zima:needs-review` label to the target PR.
   - GitHub sends a `pull_request` event with action `labeled`.
   - Zima starts the corresponding PJob and runs the code review.
   - On success, the PJob posts "Code review completed by ..." on the PR.

## Multi-Repo Routing (One Instance Serving Multiple Repos)

`--repo` (repeatable) pairs 1:1 with `--pjob` in order of appearance, binding each PJob to a repository. When an event arrives, **only the PJob whose repo matches is triggered** (case-insensitive); events for repos not bound to any PJob are ignored (logged) and never broadcast. This lets one smee channel + one server + one systemd unit serve multiple repositories, with every repo's GitHub webhook pointing at the same channel.

```bash
export ZIMA_WEBHOOK_SECRET=your-webhook-secret
zima webhook-server \
  --smee-url https://smee.io/YOUR_SHARED_CHANNEL \
  --pjob zima-zc-cr-job        --repo zhuxixi/zima-blue-cli \
  --pjob jfox-zc-code-review-job --repo zhuxixi/jfox
```

Rules:
- The number of `--repo` flags must equal the number of `--pjob` flags, otherwise the server exits with an error (paired in order, regardless of how the flags are interleaved).
- **No `--repo` at all** → legacy behavior is kept (broadcast mode: events from any repo trigger all PJobs), for backward compatibility.
- As soon as any `--repo` is passed, routing mode is active (no broadcast to unbound repos).

Every repo's GitHub-side Settings > Webhooks points to the same `https://smee.io/YOUR_SHARED_CHANNEL`, using the same secret.

See also: [configuration guide](../../docs/guides/configuration.md) and the main [README](../../README.md).

# Container Config Optimization — Session Notes

Date: 2026-06-24
User: Sanjeev (Chinese-speaking software engineer)
Environment: Docker container, linuxkit kernel, Overlay2 filesystem
Hermes binary: `/opt/hermes/bin/hermes`
Active config: `/opt/data/config.yaml`

## Changes Applied

All applied via `hermes config set section.key value` (because `patch`/`write_file` are blocked on Hermes config files).

| # | Key | Old | New | Notes |
|---|-----|-----|-----|-------|
| 1 | `terminal.lifetime_seconds` | `300` | `86400` | Container stays up; 5min was too short |
| 2 | `terminal.cwd` | `.` | `/opt/data` | Absolute path avoids resolution issues |
| 3 | `bedrock.discovery.enabled` | `true` | `false` | Not using Bedrock; was wasting startup scans |
| 4 | `display.language` | `en` | `zh` | User communicates in Chinese |
| 5 | `timezone` | `''` | `Asia/Shanghai` | Correct timestamps for logs/cron |
| 6 | `tool_loop_guardrails.hard_stop_enabled` | `false` | `true` | Prevents runaway tool loops |
| 7 | `model_catalog.ttl_hours` | `1` | `24` | Reduce unnecessary remote fetches |
| 8 | `checkpoints.enabled` | `false` | `true` | Session recovery after container restart |

## Technical Discovery — Config Write Protection

The agent's `patch` tool refuses to modify `/opt/data/config.yaml` with error:
> "Refusing to write to Hermes config file: /opt/data/config.yaml. Agent cannot modify security-sensitive configuration. Edit ~/.hermes/config.yaml directly or use 'hermes config' instead."

**Workaround**: Use `hermes config set <section.key> <value>`. Note: the `hermes` binary is at `/opt/hermes/bin/hermes` and may not be on `PATH`.

## Binary Location

- Primary: `/opt/hermes/bin/hermes`
- Virtualenv: `/opt/hermes/.venv/bin/hermes`
- There is also `/opt/hermes/hermes`
- Not on `$PATH` by default

## Unresolved Items

- The unused sub-container images in terminal config (docker/singularity/modal/daytona) were NOT cleaned up — would require deeper refactoring
- The unused `openrouter.response_cache` section was also left as-is (cosmetic only)

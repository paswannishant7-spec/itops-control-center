# ITOps device agent

The agent collects aggregate CPU, memory, disk, network-counter, boot-time, OS, hostname, IP, and availability information. It does not inspect processes, files, browser history, commands, users, or content.

An administrator creates a one-time enrollment token for a specific asset. Configure `ITOPS_AGENT_API_URL`, `ITOPS_AGENT_ENROLLMENT_TOKEN`, and optionally `ITOPS_AGENT_STATE_PATH`, then run `itops-device-agent`. Enrollment stores a unique credential in a local file with owner-only permissions where supported. Remove the enrollment token from the environment after the first successful run.

Production API URLs must use HTTPS. Each installation receives a distinct revocable credential; there is no fleet-wide embedded secret.

## Install and configure

```bash
python -m venv .venv
# Activate the environment for the current shell.
python -m pip install .
```

Copy `.env.example` into the host service manager or configuration system. The executable reads
environment variables directly; it does not automatically load the example file.

| Variable                              | Purpose                                           |
| ------------------------------------- | ------------------------------------------------- |
| `ITOPS_AGENT_API_URL`                 | HTTPS API root ending in `/api/v1`                |
| `ITOPS_AGENT_STATE_PATH`              | Private persistent credential-state file          |
| `ITOPS_AGENT_INTERVAL_SECONDS`        | Successful reporting interval                     |
| `ITOPS_AGENT_REQUEST_TIMEOUT_SECONDS` | Per-request timeout                               |
| `ITOPS_AGENT_ENROLLMENT_TOKEN`        | One-time bootstrap token; remove after enrollment |

Run `itops-device-agent` under a dedicated non-administrator OS account. On Windows, create the
state directory with an ACL limited to the service identity; on Linux, use a root-owned service
definition with a private state directory. The agent rejects non-HTTPS remote URLs. Supervise the
process with the native service manager and use bounded restart backoff.

Enrollment exchanges the one-time token for a device-specific credential and writes it atomically.
Back up neither the enrollment token nor a fleet-wide secret—none exists. If state is lost, disable
the old agent identity and issue a new enrollment. If a device is retired or suspected compromised,
disable or rotate its credential from the monitoring administration workflow.

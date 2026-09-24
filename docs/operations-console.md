# Operations and analytics console

The admin console exposes property-scoped operational dashboards, historical telemetry, alerts, diagnostic tools, and management exports.

## Data and availability

- `metric_samples` stores timestamped application and host observations by property. Host CPU, memory, disk, and network values use `psutil` when installed. Missing collectors are returned as `unavailable`; the application does not synthesize production telemetry.
- `operational_alerts` stores active threshold results for overdue service requests, elevated AI errors, and database probe failures.
- `diagnostic_actions` records every assistant tool execution with its request ID, actor, property, timeframe, and summary. The existing admin audit log receives a matching `assistant.diagnostic` event.
- Business analytics are calculated from existing sessions, messages, service requests, authentication attempts, and AI usage. Estimated AI cost and first-token latency remain unavailable until verified billing and streaming telemetry exist.

## Authorization

The HTTP middleware enforces the page-level permission and property boundary. Every assistant tool then performs its own permission check. Department Managers are filtered by their assigned `department_id`; Staff cannot run infrastructure tools or export reports. Destructive requests are detected but never executed by the assistant.

## Database migration

Startup creates three additive SQLite tables: `metric_samples`, `operational_alerts`, and `diagnostic_actions`. It also adds nullable `admin_users.department_id` when upgrading an existing database. Existing data and tables are not rewritten.

## Known limitations

- Historical charts fill as the application records samples; a new installation initially shows “Not enough history.”
- Host CPU, memory, and network telemetry require the optional `psutil` package. Disk and application telemetry still work without it.
- First-token latency and estimated cloud AI cost are explicitly unavailable because the current providers do not expose verified streaming timing or billable pricing data.
- DNS and SSL status use the most recent explicit deployment verification; the dashboard does not perform unsolicited external network probes.
- The assistant is deterministic and tool-based. It reports evidence and safe recommendations but does not restart services, change providers, clear queues, or mutate configuration.

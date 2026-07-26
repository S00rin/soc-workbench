# Attack Simulation Lab

The Attack Simulation Lab is a defender-training module under `/attack-lab`.
Each scenario is a self-contained lesson with:

- platform, difficulty, duration, and risk metadata;
- MITRE ATT&CK technique and tactic mapping;
- learning objectives, prerequisites, and an instructor narrative;
- expected endpoint, web, or network telemetry;
- representative NDJSON events generated on demand;
- a detection-ready Splunk SPL query;
- expected results, false-positive notes, and a triage path.

## Safety model

The current runner is intentionally **telemetry-only**. Starting a simulation
does not spawn a process, send a packet, or modify a file. It generates
clearly marked synthetic events using RFC 5737 documentation addresses so the
lesson can be taught without changing the workstation running SOC Workbench.

The API contract separates scenario content from execution:

```text
GET  /api/attack-lab/scenarios
GET  /api/attack-lab/scenarios/{id}
POST /api/attack-lab/scenarios/{id}/simulate
```

This boundary leaves room for a later isolated Atomic Red Team or CALDERA
adapter. A live adapter should require a dedicated lab target, an explicit
approval step, target allowlisting, per-technique cleanup, timeout and
kill-switch controls, and an immutable audit record. It should return the same
normalized run/event shape as the telemetry-only runner so the teaching UI
does not depend on a specific execution engine.

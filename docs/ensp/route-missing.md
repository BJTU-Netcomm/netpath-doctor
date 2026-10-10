# ROUTE_MISSING Live Scenario

This scenario removes the static route on R2, lets the read-only diagnosis
Agent inspect the live devices, and restores the route in an outer experiment
controller.

The route used by the current R1-R2-R3 topology is:

```text
ip route-static 192.168.3.0 255.255.255.0 10.0.23.2
```

The controller removes it with:

```text
undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2
```

and restores it with the original command. The Agent itself remains read-only;
it only runs `ping`, `tracert`, and `display ip routing-table`.

Copy the committed scenario template to the ignored local file:

```powershell
Copy-Item `
  scenarios/live/case_002_route_missing.example.json `
  scenarios/live/case_002_route_missing.local.json
```

With R1, R2, and R3 running, execute one trial first:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_experiment `
  scenarios/live/case_002_route_missing.local.json `
  --transport ensp-console `
  --devices config/ensp_console.local.json `
  --fault-type ROUTE_MISSING `
  --trials 1 `
  --output reports/live/console_route_missing_trial.json `
  --raw-output-dir reports/live/console_route_missing_trial_raw
```

Then run the three-trial acceptance check:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_experiment `
  scenarios/live/case_002_route_missing.local.json `
  --transport ensp-console `
  --devices config/ensp_console.local.json `
  --fault-type ROUTE_MISSING `
  --trials 3 `
  --output reports/live/console_route_missing_complete.json `
  --raw-output-dir reports/live/console_route_missing_complete_raw
```

The report passes only when every trial has `ROUTE_MISSING`, confirms the route
is absent after injection, restores the route, and reaches the destination
again afterward.

## VRP empty filtered-query response

On the integration computer's VRP build, a missing destination route makes
`display ip routing-table 192.168.3.1` return only the command echo and prompt.
This is not enough evidence to diagnose a missing route.

The eNSP console transport retries the filtered query twice. If both completed
queries have empty bodies, it reads `display ip routing-table` instead.
The Parser uses the requested destination IP to choose the longest matching
prefix, including a default route when present. A negative result requires a
recognized full-table heading and a route count matching the parsed entries.
Malformed or incomplete tables remain Parser errors. Other empty command
results remain transport errors.

The live experiment controller passes the target IP to the Parser for both
the injection check and the recovery check, just as `LiveExecutor` does for
Agent actions. Recovery runs in `finally` and is verified by reading the route
again, followed by a source-to-destination ping.

The diagnosis currently uses `DiagnosisStateMachine`, a rule-based Agent.
These experiments validate real device control and CLI-driven diagnosis;
they do not validate an LLM policy or automatic eNSP topology startup.

## Integration validation (2026-10-10)

The running R1-R2-R3 lab passed console preflight (3/3 devices), a one-trial
ROUTE_MISSING run (1/1), and the consecutive three-trial run (3/3).
Every acceptance trial reported `COMPLETED`, `R2`, and `ROUTE_MISSING`, verified
the missing route after injection, then restored the route and measured 0%
packet loss from R1 to 192.168.3.1. No device commands were entered manually
during the runs.

The local acceptance report is
`reports/live/console_route_missing_complete.json`; raw output is under
`reports/live/console_route_missing_complete_raw/`. These files remain ignored
and are not distributed as portable fixtures. The code checks also passed:
67 tests, 4 subtests, and all 20 golden replay benchmark cases.

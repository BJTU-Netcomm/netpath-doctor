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

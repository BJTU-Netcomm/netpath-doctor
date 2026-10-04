# eNSP Live Runner

Live Runner connects the read-only diagnosis Agent to running Huawei VRP devices.
The eNSP topology must already be running and reachable through SSH.

## Local setup

Create the ignored local inventory from the committed example:

```powershell
Copy-Item config/devices.example.json config/devices.local.json
```

Edit `config/devices.local.json` with the real management addresses and SSH user.
Keep passwords outside the file:

```powershell
$env:ENSP_R1_PASSWORD = "local-password"
$env:ENSP_R2_PASSWORD = "local-password"
$env:ENSP_R3_PASSWORD = "local-password"
```

Create the environment and install dependencies:

```powershell
uv venv --python 3.12
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Check all SSH connections

Before running the Agent, verify that all three routers accept SSH and return a
read-only command result:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_preflight
```

The command writes `reports/live/preflight_latest.json` and exits with code `0`
only when every configured device is reachable. Raw `display version` output is
kept under `reports/live/preflight_raw/` for troubleshooting.

## Run one diagnosis

Copy the scenario template and replace its addresses with the real topology values:

```powershell
Copy-Item `
  scenarios/live/case_001_interface_down.example.json `
  scenarios/live/case_001_interface_down.local.json
```

Run the diagnosis after the interface fault has been injected:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_runner `
  scenarios/live/case_001_interface_down.local.json
```

The diagnosis report is written to `reports/live/latest.json`. Raw command output is
written to the ignored `reports/live/raw/` directory so it can be reviewed and
sanitized before adding a Parser fixture to Git.

`RUN_PING` and `RUN_TRACERT` execute on `source_device`. Later actions execute on
the device selected by the Agent. The `ip_to_device` mapping must include every
router address that can appear as the final reachable tracert hop.

## Run the complete live benchmark

After preflight succeeds and normal R1-to-R3 connectivity has been checked, run:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_experiment `
  scenarios/live/case_001_interface_down.local.json
```

The command runs three trials by default. Each trial performs this sequence:

1. verify that R1 can ping the destination before changing the topology;
2. configure `shutdown` on R2 `GigabitEthernet0/0/1`;
3. run the read-only diagnosis Agent;
4. configure `undo shutdown` in a `finally` recovery path;
5. verify that R1 can ping the destination again.

The Agent remains read-only. Only the outer experiment controller calls the
configuration transport. The benchmark passes only when all three trials return
`INTERFACE_DOWN` with the expected device and interface, and connectivity is
restored after every trial.

The summary is written to `reports/live/experiment_latest.json`. Raw diagnosis
and configuration output is kept in `reports/live/experiment_raw/`. Both paths
are ignored by Git because the output may contain local device details.

The second live scenario, `ROUTE_MISSING`, is documented in
`docs/ensp/route-missing.md`. It removes and restores R2's static route and
uses the same read-only diagnosis Agent.

If a run is interrupted, check R2 from the eNSP console before continuing:

```text
display interface GigabitEthernet0/0/1
```

If necessary, recover it manually:

```text
system-view
interface GigabitEthernet0/0/1
undo shutdown
```

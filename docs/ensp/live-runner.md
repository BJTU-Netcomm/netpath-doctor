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

# eNSP local console transport

## Purpose

`ENSPConsoleTransport` lets NetPath-Doctor control routers running in the
local eNSP topology through their console ports. It is intended for a single
integration computer while the separate SSH management network is being built.

It does not start eNSP, open the GUI, or alter the Windows network settings.
eNSP must already be open and the target routers must already be running.

## Start-up requirement

On the integration computer, start eNSP with **Run as administrator**. The
installed eNSP client may exit immediately when launched without elevation;
in that state no console ports are created and the preflight cannot connect.
This is a Windows/eNSP launch requirement, not a project Python requirement.

Before running the benchmark, check that all three local console ports are
listening:

```powershell
2000, 2001, 2002 | ForEach-Object {
  $port = $_
  $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($listener) { "PORT $port LISTENING" } else { "PORT $port NOT_LISTENING" }
}
```

If a port is not listening, open the no-Cloud topology, start R1/R2/R3, and
wait until each device finishes booting before running the Python commands.

## Local inventory

Create an ignored local file from the committed example:

```powershell
Copy-Item config/ensp_console.example.json config/ensp_console.local.json
```

The R1-R2-R3 topology uses these eNSP console ports:

| Device | Address |
| --- | --- |
| R1 | `127.0.0.1:2000` |
| R2 | `127.0.0.1:2001` |
| R3 | `127.0.0.1:2002` |

## Preflight

With R1, R2, and R3 started in eNSP, run:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.live_preflight `
  --transport ensp-console `
  --devices config/ensp_console.local.json
```

The resulting report records whether the local program can send a read-only
VRP command to every router. This verifies programmatic device control before
fault injection.

## Scope

Use this transport only on the local integration computer. Keep SSH as the
remote-management transport once the management network is stable.

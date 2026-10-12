# eNSP CLI Record Collection

## Environment

Platform:
eNSP

Devices:
R1, R2, R3

Target device:
R2

Purpose:
Collect real CLI outputs for SSH fault injection and recovery reproduction.

---

# Normal State

Status:
Network is normal.
Static route exists on R2.

Collected commands:

R1:
- ping 192.168.3.1
- tracert 192.168.3.1

R2:
- display ip routing-table 192.168.3.0
- display ip interface brief
- display arp

---

# Route Missing State

Fault:
Static route removed from R2.

Command:

undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2


Verification:

R2:
- display ip routing-table 192.168.3.0
- display ip routing-table

R1:
- ping 192.168.3.1


Expected result:

- Target route does not exist.
- Destination becomes unreachable.

---

Collection Time:

2026-10-10
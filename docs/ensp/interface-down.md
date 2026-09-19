# Interface Down Fault Scenario

## 1. Overview

This document describes the INTERFACE_DOWN fault scenario used in the eNSP experiment.

The purpose of this scenario is to verify that NetPath-Doctor can detect interface failures and provide correct diagnosis results.


## 2. Fault Type

Fault type:

INTERFACE_DOWN


Description:

The network connection between R2 and R3 is interrupted by shutting down the interface on R2.


## 3. Target Interface

The fault injection interface is:

Device:

R2

Interface:

GigabitEthernet0/0/1


Connection:

R2 GigabitEthernet0/0/1

to

R3 GigabitEthernet0/0/0


## 4. Normal State

Before fault injection:

R1 can reach the destination address:

192.168.3.1


Verification command:

<R1>ping 192.168.3.1


Expected result:

5 packet(s) transmitted

5 packet(s) received

0.00% packet loss


Interface status:

R2 GigabitEthernet0/0/1

Physical status:

UP


Protocol status:

UP


## 5. Fault Injection

Enter R2 system view:

system-view


Select the interface:

interface GigabitEthernet0/0/1


Shutdown the interface:

shutdown


After shutdown:

The connection between R2 and R3 is unavailable.

The destination network 192.168.3.0/24 cannot be reached from R1.


## 6. Fault Verification

Run diagnostic commands:

display interface GigabitEthernet0/0/1

display ip routing-table

ping 192.168.3.1


Expected fault evidence:

- interface physical status is DOWN
- connectivity test fails
- route path is interrupted

Record the exact output of `display ip routing-table 192.168.3.1` after the
shutdown. Some VRP versions remove a static route from the active routing table
when its outgoing interface goes down. In that case the current Agent may
classify the symptom as `ROUTE_MISSING` before it checks the interface. Treat
this as a state-machine compatibility issue to fix from the captured evidence;
do not count the run as a successful `INTERFACE_DOWN` benchmark.


## 7. Fault Recovery

Enter interface configuration:

interface GigabitEthernet0/0/1


Recover the interface:

undo shutdown


After recovery:

R1 should be able to reach:

192.168.3.1


## 8. Experiment Goal

This scenario verifies that NetPath-Doctor can:

1. use the experiment controller to inject and recover the fault;
2. keep the diagnosis Agent limited to read-only commands;
3. collect Huawei VRP CLI outputs;
4. identify interface failures;
5. restore network connectivity after recovery.

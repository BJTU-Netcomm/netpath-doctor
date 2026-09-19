# eNSP Network Topology

## 1. Overview

This document describes the eNSP experimental topology used by NetPath-Doctor.

The topology contains three Huawei AR2220 routers.

Network topology:

R1 -------- R2 -------- R3

The purpose of this topology is to verify:

- network connectivity
- route troubleshooting
- interface failure diagnosis
- real Huawei VRP CLI output parsing
- SSH based device control


## 2. Device Information

| Device | Model | Role |
|---|---|---|
| R1 | Huawei AR2220 | Source Router |
| R2 | Huawei AR2220 | Intermediate Router |
| R3 | Huawei AR2220 | Destination Router |


## 3. Network Connections

### R1 - R2 Connection

R1 Interface:

GigabitEthernet0/0/0

R2 Interface:

GigabitEthernet0/0/0


IP Address:

R1: 10.0.12.1/24

R2: 10.0.12.2/24


### R2 - R3 Connection

R2 Interface:

GigabitEthernet0/0/1

R3 Interface:

GigabitEthernet0/0/0


IP Address:

R2: 10.0.23.1/24

R3: 10.0.23.2/24


## 4. Destination Network

The destination network is configured on R3.

LoopBack interface:

LoopBack0

IP Address:

192.168.3.1/24


Traffic path:

R1 -> R2 -> R3 -> LoopBack0


## 5. Routing Configuration

R1 static route:

ip route-static 192.168.3.0 255.255.255.0 10.0.12.2


R2 static route:

ip route-static 192.168.3.0 255.255.255.0 10.0.23.2


R3 static route:

ip route-static 10.0.12.0 255.255.255.0 10.0.23.1


## 6. Connectivity Verification

Normal test command:

<R1>ping 192.168.3.1


Expected result:

5 packet(s) transmitted

5 packet(s) received

0.00% packet loss


## 7. Fault Simulation Scenario

Fault type:

INTERFACE_DOWN


Target interface:

R2 GigabitEthernet0/0/1


Fault injection command:

interface GigabitEthernet0/0/1

shutdown


Recovery command:

interface GigabitEthernet0/0/1

undo shutdown


## 8. Experiment Goal

The eNSP topology is used to verify that NetPath-Doctor can:

1. connect to Huawei VRP devices;
2. execute diagnostic commands;
3. collect CLI outputs;
4. parse routing, interface, ARP and ping information;
5. identify network failures correctly.
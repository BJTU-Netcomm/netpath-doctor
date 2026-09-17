# eNSP Address Plan

## 1. Network Address Overview

This document describes the IP address allocation of the eNSP experimental topology.


## 2. Interface Address Plan

| Device | Interface | IP Address | Network | Description |
|---|---|---|---|---|
| R1 | GigabitEthernet0/0/0 | 10.0.12.1/24 | 10.0.12.0/24 | Link to R2 |
| R2 | GigabitEthernet0/0/0 | 10.0.12.2/24 | 10.0.12.0/24 | Link to R1 |
| R2 | GigabitEthernet0/0/1 | 10.0.23.1/24 | 10.0.23.0/24 | Link to R3 |
| R3 | GigabitEthernet0/0/0 | 10.0.23.2/24 | 10.0.23.0/24 | Link to R2 |
| R3 | LoopBack0 | 192.168.3.1/24 | 192.168.3.0/24 | Test Destination |


## 3. Routing Information

### R1

Destination:

192.168.3.0/24

Next Hop:

10.0.12.2


### R2

Destination:

192.168.3.0/24

Next Hop:

10.0.23.2


### R3

Destination:

10.0.12.0/24

Next Hop:

10.0.23.1


## 4. Test Destination

The final test destination is:

192.168.3.1

This address belongs to:

R3 LoopBack0


## 5. Fault Injection Interface

The interface used for INTERFACE_DOWN testing:

R2 GigabitEthernet0/0/1

This interface connects R2 and R3.
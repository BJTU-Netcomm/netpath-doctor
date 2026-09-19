# eNSP SSH Setup

## 1. Overview

This document describes the SSH configuration used for remote access to Huawei VRP devices.

The purpose is to allow NetPath-Doctor LiveExecutor to connect to eNSP routers through SSH.


## 2. Target Devices

| Device | Management Access |
|---|---|
| R1 | SSH |
| R2 | SSH |
| R3 | SSH |


## 3. SSH Requirements

Each router should provide:

- SSH service
- local user authentication
- management IP address
- SSH login access


## 4. SSH Configuration

Example configuration:

stelnet server enable

aaa

local-user netpath password irreversible-cipher password

local-user netpath service-type ssh

user-interface vty 0 4

authentication-mode aaa

protocol inbound ssh


## 5. Connection Information

The device address, username and password should be stored locally.

Do not commit passwords or private configuration files to Git.


Example:

Device:

R1

Management IP:

10.0.12.1


Device:

R2

Management IP:

10.0.12.2


Device:

R3

Management IP:

10.0.23.2


## 6. Security Notes

- Passwords must not be stored in source code.
- Sensitive configuration files should not be uploaded.
- Use local configuration files or environment variables for authentication.
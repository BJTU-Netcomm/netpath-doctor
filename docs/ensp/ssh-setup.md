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
- an RSA local key pair created on the running device


## 4. SSH Configuration

Example configuration:

stelnet server enable

aaa

local-user netpath password irreversible-cipher password

local-user netpath service-type ssh

user-interface vty 0 4

authentication-mode aaa

protocol inbound ssh

Create the RSA local key pair interactively before testing SSH:

rsa local-key-pair create

The exact password and SSH-user commands vary between VRP releases. Apply them
in the device console, verify there are no CLI errors, and use `display
current-configuration` to confirm the resulting configuration. The committed
`.cfg.example` files are sanitized references rather than scripts to paste
without review.


## 5. Connection Information

The device address, username and password should be stored locally.

Do not commit passwords or private configuration files to Git.


Example management addresses:

- R1: `192.168.56.101`
- R2: `192.168.56.102`
- R3: `192.168.56.103`

These addresses match `config/devices.example.json`. They require all three
`GigabitEthernet0/0/2` interfaces to connect to one eNSP Cloud bound to the
VirtualBox Host-Only adapter.


## 6. Security Notes

- Passwords must not be stored in source code.
- Sensitive configuration files should not be uploaded.
- Use local configuration files or environment variables for authentication.

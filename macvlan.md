# Create a macvlan interface on TrueNAS (quick shell steps)

Run as root (sudo). Replace the placeholders shown below before running the commands.

Important:
- Make sure the IP you assign is unique on your LAN and within the same subnet/gateway as your TrueNAS host (TrueNAS host in this repo is 192.168.1.160).
- Prefer creating the interface via the TrueNAS web UI for persistence. Shell commands are temporary across reboots unless persisted by the system configuration.

## 1. Identify the parent interface
Use one of these commands to find the host's network interface name (example: `ix0`, `eno1`, `eth0`):

```sh
ip link            # lists all interfaces
ip -br addr        # brief address output
```

## 2. Create the macvlan interface (temporary / shell)
Replace the values in angle brackets and run as root.

```sh
# Example values you can substitute:
# PARENT_IFACE=ix0
# HOST_MACVLAN_IP=192.168.1.171
# PREFIX=24          # equals /24 netmask (255.255.255.0)
# GATEWAY=192.168.1.1

sudo ip link add macvlan0 link <PARENT_IFACE> type macvlan mode bridge
sudo ip addr add <HOST_MACVLAN_IP>/<PREFIX> dev macvlan0
sudo ip link set macvlan0 up
```

Notes:
- `mode bridge` allows the macvlan interface to be on the same L2 network as the parent.
- Use a host IP that does not conflict with other devices.

## 3. (Optional) Add a route if needed
Often not necessary. Add this only if your host needs explicit routing to reach the macvlan subnet:

```sh
sudo ip route add <SUBNET_CIDR> dev macvlan0
```

## 4. Verify

```sh
ip addr show macvlan0
ping -c 3 <HOST_MACVLAN_IP>
```

## Persistence
- TrueNAS (CORE/SCALE) — prefer the web UI: **Network → Interfaces → Add** and configure a macvlan/alias with the desired IP so it survives reboots.
- If you must use shell scripts, add them to your host's startup mechanism, but note TrueNAS has its own recommended way via the UI or system config.

## Important reminders
- Docker Compose cannot create the macvlan host interface for you — create the macvlan interface on the host before running `docker-compose up`.
- If you need the TrueNAS host itself to talk to containers on the macvlan, assign a macvlan IP to the host (as above) or use a management bridge. TrueNAS networking specifics vary; consult TrueNAS docs for persistent configuration.

-- End
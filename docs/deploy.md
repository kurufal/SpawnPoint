# Deploying SpawnPoint on TrueNAS SCALE

This document describes deploying SpawnPoint on TrueNAS SCALE using the built-in Apps → "Launch Docker Compose" (Custom Docker Compose) flow. This keeps the service containerized and managed by SCALE and is the recommended path for most users.

Overview — two supported options
- Primary (recommended): TrueNAS SCALE Apps → Launch Docker Compose (Custom). Run SpawnPoint as container(s) and map TrueNAS datasets to container volumes.
- Alternative: Run inside a VM (useful for advanced network driver needs or very custom host-level configurations). See the "VM notes" section near the end.

Before you begin
- Create one or more datasets on your TrueNAS pool to hold SpawnPoint data and game server files (for example: `pool/spawnpoint-config` and `pool/spawnpoint-games`).
- Ensure you have an account with privileges to create Apps and manage storage in the SCALE UI.

1) Create datasets for persistent storage

1. Open TrueNAS SCALE → Storage → Pools → (your pool) → Add Dataset.
2. Create a dataset for SpawnPoint config and a dataset for game files, for example:
   - `/mnt/<pool>/spawnpoint-config`
   - `/mnt/<pool>/spawnpoint-games`
3. Adjust dataset ACLs so the container can write into them (see the Permissions section below).

2) Use the repository docker-compose file

This repository includes a root `docker-compose.yml` (see `docker-compose.yml` at the repository root). Use that file as the canonical starting point when deploying via the SCALE Apps custom Compose editor.

Recommended workflow:

1. Inspect the root `docker-compose.yml` and edit any values you need locally (for example `STEAM_HOST`, ports, image tag, or PUID/PGID).
2. Change volume host paths in the compose file to point at your SCALE dataset mountpoints (for example `/mnt/<pool>/spawnpoint-config` and `/mnt/<pool>/spawnpoint-games`).
3. If you need a custom variant, copy the compose file and make your changes; paste the edited YAML into Apps → Launch Docker Compose (Custom) or upload the file.
4. When importing into SCALE, confirm the storage mappings reference the correct host paths (`/mnt/<pool>/…`) and adjust any environment variables in the UI if needed.

This keeps the compose file in your repo as the single source of truth and avoids duplication between docs and the artifact you run.

3) Launch via TrueNAS Apps: Launch Docker Compose (Custom)

1. Open TrueNAS SCALE → Apps → Launch Docker Compose.
2. Choose "Custom" and paste the `docker-compose.yml` content into the editor (or upload the file).
3. SCALE's UI will parse the compose file and ask you to map the host paths or configure storage mappings. Confirm the volume paths map to the datasets you created (`/mnt/<pool>/spawnpoint-config`, `/mnt/<pool>/spawnpoint-games`).
4. Configure environment variables, resource limits, and networking in the UI as needed.
5. Click "Launch". SCALE will deploy the containers on the host.

4) Permissions and ACLs

- Containers must be able to write to the dataset mountpoints. By default SCALE datasets map to host filesystem paths like `/mnt/<pool>/<dataset>`.
- Either run your container as a UID/GID that matches the dataset ownership or adjust the dataset ACL to allow write access for the container's UID/GID.

Example (run on TrueNAS shell or from an SSH session with appropriate privileges):

```bash
# Set dataset owner to UID 1000 / GID 1000 used by container
# Replace <pool> and <dataset> before running
chown -R 1000:1000 /mnt/<pool>/spawnpoint-config
chown -R 1000:1000 /mnt/<pool>/spawnpoint-games
# Or use the SCALE Storage → Dataset GUI to adjust ACLs
```

5) Networking options

- Port mapping (recommended): Map container ports to host ports (example in the repo `docker-compose.yml` exposes service ports). This is the simplest and often the most compatible setup in SCALE.
- Host networking: Use only if necessary; it reduces isolation and may conflict with SCALE services.
- Macvlan (advanced): If you require each game server to appear on the LAN with its own IP, define a macvlan network in your compose file and ensure the parent interface and switch allow additional MACs.

6) Healthchecks and persistent behavior

- Add `restart: unless-stopped` to ensure containers come back after host reboots.
- Consider adding a `healthcheck` to the compose service so SCALE can detect container failures.

7) Logs and console access

- Use the SCALE Apps UI to view container logs and to open a shell into the container if needed.
- You can also SSH to the TrueNAS host and use `docker ps` / `docker logs` if comfortable.

8) Troubleshooting

- Container can't write files: double-check dataset mount paths and ACL/ownership as described above.
- SteamCMD fails to download/update: verify the container has outbound network access and DNS is working.
- Game server port reachability: check SCALE firewall rules and that port mappings are correct.
- Macvlan issues: ensure parent interface and switches allow traffic for additional MACs.

VM notes (optional)

If you prefer to run SpawnPoint in a small VM (for maximum parity with a standard Linux host), you can create a VM in SCALE, install Docker and Docker Compose, mount the datasets into the VM, and run the same `docker-compose.yml` inside the VM. This is operationally similar to the containerized approach but adds a VM layer; most users will find the Apps custom compose flow simpler and better integrated.

Further help

If you'd like, I can:
- Provide a ready-to-paste `docker-compose.yml` tailored to your pool/dataset names and network ranges (I can update the repo file or create a separate variant).
- Produce a small systemd unit or cloud-init snippet if you choose the VM path.
- Convert the compose file into Kubernetes manifests/Helm for running as a full SCALE App (advanced).

---

If you want a compose file customized for your environment, tell me the pool name, dataset names, and whether you prefer port mapping, host networking, or macvlan, and I will generate a ready-to-use Compose file.
# Deploying SpawnPoint on TrueNAS SCALE

This document describes deploying SpawnPoint on TrueNAS SCALE using the built-in Apps → "Launch Docker Compose" (Custom Docker Compose) flow. This keeps the service containerized and managed by SCALE and is the recommended path for most users.

Overview — two supported options
- Primary (recommended): TrueNAS SCALE Apps → Launch Docker Compose (Custom Docker Compose). Run SpawnPoint as container(s) and map TrueNAS datasets to container volumes.
- Alternative: Run inside a VM (useful for advanced network driver needs or very custom host-level configurations). See the "VM notes" section near the end.

Before you begin
- Create one or more datasets on your TrueNAS pool to hold SpawnPoint data and game server files (for example: `pool/spawnpoint-config` and `pool/spawnpoint-games`).
- Ensure you have an account with privileges to create Apps and manage storage in the SCALE UI.

1) Create datasets for persistent storage

1. Open TrueNAS SCALE → Storage → Pools → (your pool) → Add Dataset.
2. Create a dataset for SpawnPoint config and a dataset for game files, for example:
   - `/mnt/<pool>/spawnpoint-config`
   - `/mnt/<pool>/spawnpoint-games`
3. Adjust dataset ACLs so the container can write into them (see the Permissions section below).

2) Prepare a Docker Compose file

Below is a minimal, example `docker-compose.yml` for running SpawnPoint via the SCALE custom app flow. You will paste this into the Apps → Launch Docker Compose editor (or upload it if you prefer).

Notes about paths: In the compose snippet above use the SCALE dataset mountpoints (for example `/mnt/poolname/dataset`). When you paste this into the TrueNAS Apps custom Compose editor, the system will create containers that use those host paths as volumes.

3) Launch via TrueNAS Apps: Launch Docker Compose (Custom)

1. Open TrueNAS SCALE → Apps → Launch Docker Compose.
2. Choose "Custom" and paste the `docker-compose.yml` content into the editor (or upload the file).
3. SCALE's UI will parse the compose file and ask you to map the host paths or configure storage mappings. Confirm the volume paths map to the datasets you created (`/mnt/<pool>/spawnpoint-config`, `/mnt/<pool>/spawnpoint-games`).
4. Configure environment variables, resource limits, and networking in the UI as needed.
5. Click "Launch". SCALE will deploy the containers on the host.

4) Permissions and ACLs

- Containers must be able to write to the dataset mountpoints. By default SCALE datasets map to host filesystem paths like `/mnt/<pool>/<dataset>`.
- Either run your container as a UID/GID that matches the dataset ownership or adjust the dataset ACL to allow write access for the container's UID/GID.

Example (run on TrueNAS shell or from an SSH session with appropriate privileges):

```bash
# Set dataset owner to UID 1000 / GID 1000 used by container
# Replace <pool> and <dataset> before running
chown -R 1000:1000 /mnt/<pool>/spawnpoint-config
chown -R 1000:1000 /mnt/<pool>/spawnpoint-games
# Or use ACL GUI in SCALE to add write permissions for the user/group used by your container
```

5) Networking options

- Port mapping (recommended): Map container ports to host ports (example above uses 8080:80 for the web UI). This is the simplest and often the most compatible setup in SCALE.
- Host networking: You can use host networking if you need the container to bind directly to host IPs, but be cautious as this reduces isolation and may conflict with SCALE's services.
- Macvlan (advanced): If you require each game server to appear on the LAN with its own IP, create a macvlan network as shown in the compose snippet. Note:
  - Replace `parent: "eth0"` with the host interface (this depends on your hardware and SCALE configuration).
  - Your switch and network must accept additional MAC addresses on that port; macvlan can be blocked by some managed switches.

6) Healthchecks and persistent behavior

- Add `restart: unless-stopped` to ensure containers come back after host reboots.
- Consider adding a `healthcheck` to the compose service so SCALE can detect container failures.

7) Logs and console access

- Use the SCALE Apps UI to view container logs and to open a shell into the container if needed.
- You can also SSH to the TrueNAS host and use `docker ps` / `docker logs` if comfortable.

8) Troubleshooting

- Container can't write files: double-check dataset mount paths and ACL/ownership as described above.
- SteamCMD fails to download/update: verify the container has outbound network access and DNS is working.
- Game server port reachability: check SCALE firewall rules and that port mappings are correct.
- Macvlan issues: ensure parent interface and switches allow traffic for additional MACs.

VM notes (optional)

If you prefer to run SpawnPoint in a small VM (for maximum parity with a standard Linux host), you can create a VM in SCALE, install Docker and Docker Compose, mount the datasets into the VM, and run the same `docker-compose.yml` inside the VM. This is operationally similar to the containerized approach but adds a VM layer; most users will find the Apps custom compose flow simpler and better integrated.

Further help

If you'd like, I can:
- Provide a ready-to-paste `docker-compose.yml` tailored to your pool/dataset names and network ranges.
- Produce a small systemd unit or cloud-init snippet if you choose the VM path.
- Convert the compose file into Kubernetes manifests/Helm for running as a full SCALE App (advanced).

---

If you want a compose file customized for your environment, tell me the pool name, dataset names, and whether you prefer port mapping, host networking, or macvlan, and I will generate a ready-to-use Compose file.
# Deploying SpawnPoint on TrueNAS SCALE

1. Clone this repository into a dataset:
   ```bash
   git clone git@github.com:<your-username>/spawnpoint.git
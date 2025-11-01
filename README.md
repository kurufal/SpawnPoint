# SpawnPoint

SpawnPoint is a web-based manager for hosting and controlling Steam game servers inside Docker, designed for easy deployment on TrueNAS SCALE.

## Features (planned)
- Manage multiple game servers from a single Linux container
- Install/update by Steam App ID
- Embedded terminal for live interaction
- Start/stop/configure servers via Web GUI
- Host networking for LAN visibility

## Deployment
See [docs/deploy.md](docs/deploy.md) for detailed TrueNAS SCALE deployment instructions and examples.

Quick start (recommended):

- For TrueNAS SCALE the recommended deployment is using the built-in Apps -> "Launch Docker Compose" (Custom Docker Compose) flow so SpawnPoint runs as a container(s) managed by SCALE. See `docs/deploy.md` for a step-by-step guide and example Docker Compose snippets (macvlan and host-networking examples included).

If you prefer a VM-based install instead, there are notes in `docs/deploy.md` describing that approach, but the primary documentation below assumes containerized deployment via the TrueNAS custom app flow.
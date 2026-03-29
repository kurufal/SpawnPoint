# SpawnPoint

SpawnPoint is a web-based manager for hosting and controlling Steam game servers inside Docker, designed for easy deployment on TrueNAS SCALE, Unraid, Dockge, or any Docker-based server.

## Features
- Manage multiple game servers from a single Linux container
- Install/update games by Steam App ID via SteamCMD
- **Embedded real-time terminal** for live interaction (native WebSocket support)
- Start/stop/configure servers via modern Web GUI
- Custom card images for each server
- Dark-themed, responsive UI

## Technology Stack
- **Backend**: [NiceGUI](https://nicegui.io/) — Python web framework with native WebSocket support
- **Container**: Debian-based image with SteamCMD pre-installed (`cm2network/steamcmd`)
- **Frontend**: Custom CSS with real-time updates via WebSockets

## Project Structure
```
SpawnPoint/
├── Dockerfile              # Single-container image (webui + SteamCMD)
├── docker-compose.yml      # Service orchestration
├── SteamCMD/
│   ├── servers.json        # Server configuration store
│   └── scripts/            # SteamCMD helper scripts
├── games/                  # Installed game server files
├── webui/
│   ├── app.py              # Application entry point
│   ├── requirements.txt    # Python dependencies
│   └── static/
│       ├── style.css       # Custom styling
│       ├── images/         # Uploaded card images
│       └── templates/
│           └── spawnpoint.py  # Core logic and UI components
├── docs/
│   └── deploy.md           # TrueNAS SCALE deployment guide
└── top50.md                # Popular Steam dedicated server App IDs
```

## Quick Start

```bash
git clone https://github.com/yourusername/spawnpoint.git
cd spawnpoint
docker compose up -d --build
```

Then open `http://<your-ip>:40400` in your browser.

## Deployment
See [docs/deploy.md](docs/deploy.md) for detailed TrueNAS SCALE deployment instructions.

Game servers are defined in the configuration files (logic to be implemented in backend). The system is designed to use the Steam App ID (e.g., 2394010 for Palworld) to handle updates and installations via SteamCMD.

🖥️ User Interface Guide

Game Cards

Each game server is represented by a card containing:

Visual Status: Displays status (Running/Stopped) and Version info.

Controls:

<i class="fas fa-play"></i> Start: Launches the server process.

<i class="fas fa-stop"></i> Stop: Gracefully terminates the server.

<i class="fas fa-download"></i> Update: Runs steamcmd app_update validation.

Web Terminal

located on the right side of the screen:

Toggle: Click the arrow icon (<i class="fas fa-chevron-left"></i>) in the top-right of the terminal pane to collapse or expand it.

Resize: Drag the handle on the left edge of the terminal pane to adjust its width.

Context: Displays output from the arch-steam container.

🤝 Contributing

Fork the repository.

Create a feature branch (git checkout -b feature/NewGameSupport).

Commit your changes.

Push to the branch.

Open a Pull Request.

📝
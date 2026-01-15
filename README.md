# SpawnPoint

SpawnPoint is a web-based manager for hosting and controlling Steam game servers inside Docker, designed for easy deployment on TrueNAS SCALE, Unraid, or any Docker-based server.

## Features
- Manage multiple game servers from a single Linux container
- Install/update games by Steam App ID via SteamCMD
- **Embedded real-time terminal** for live interaction (native WebSocket support)
- Start/stop/configure servers via modern Web GUI
- Host networking for LAN visibility
- Custom card images for each server
- Dark-themed, responsive UI

## Technology Stack
- **Backend**: [NiceGUI](https://nicegui.io/) - Modern Python web framework with native WebSocket support
- **Container**: Arch Linux-based image with SteamCMD pre-installed
- **Frontend**: Custom CSS with real-time updates via WebSockets

## Deployment
See [docs/deploy.md](docs/deploy.md) for detailed TrueNAS SCALE deployment instructions and examples.

Quick start (recommended):

- For TrueNAS SCALE the recommended deployment is using the built-in Apps -> "Launch Docker Compose" (Custom Docker Compose) flow so SpawnPoint runs as a container(s) managed by SCALE. See `docs/deploy.md` for a step-by-step guide and example Docker Compose snippets (macvlan and host-networking examples included).

If you prefer a VM-based install instead, there are notes in `docs/deploy.md` describing that approach, but the primary documentation below assumes containerized deployment via the TrueNAS custom app flow.

SpawnPoint

SpawnPoint is a Docker-based game server manager designed specifically for deployment on TrueNAS Scale. It provides a modern, responsive Web GUI to manage multiple SteamCMD-based game servers running within a single, optimized Arch Linux container.

🚀 Features

Centralized Management: Run multiple game servers (e.g., Palworld, Enshrouded) from a single dashboard.

Split Architecture: * WebUI: A lightweight Python Flask application handling the frontend.

Game Runner: A specialized Arch Linux container (arch-steam) equipped with SteamCMD and necessary dependencies to run games.

Modern Web Interface:

Card-Based Layout: Visual "buckets" for each server featuring game art, status indicators, and quick controls (Start, Stop, Update).

Integrated Web Terminal: A collapsible, resizable terminal pane directly in the browser, allowing real-time interaction with the backend container.

Custom Styling: A clean, dark-themed UI built with custom CSS (no heavy frameworks) and FontAwesome icons.

TrueNAS Scale Ready: Designed to be deployed easily using docker-compose.

📂 Project Structure

SpawnPoint/
├── arch-steam/             # Game Runner Container
│   └── Dockerfile          # Arch Linux + SteamCMD image definition
├── config/                 # Configuration files
│   └── games.schema.json   # Schema for defining game server parameters
├── docs/                   # Documentation
│   └── deploy.md           # Deployment instructions
├── webui/                  # Web Interface Container
│   ├── Dockerfile          # Python/Flask image definition
│   ├── flask_app.py        # Main application logic
│   ├── requirements.txt    # Python dependencies
│   ├── static/             # Static assets
│   │   ├── styles.css      # Custom styling
│   │   ├── app.js          # Frontend logic (terminal resize/collapse)
│   │   └── game_images/    # SVGs and JPEGs for game cards
│   └── templates/          # HTML Templates
│       └── index.html      # Main dashboard view
└── docker-compose.yml      # Service orchestration


🛠️ Installation & Deployment

Prerequisites

TrueNAS Scale (or any system supporting Docker & Docker Compose)

Git

Setup

Clone the Repository:

git clone [https://github.com/yourusername/spawnpoint.git](https://github.com/yourusername/spawnpoint.git)
cd spawnpoint


Prepare Game Images:
Place your game cover art in webui/static/game_images/. Ensure they are sized appropriately (approx. 200x250px) for the best visual result.

Deploy with Docker Compose:

docker-compose up -d --build


Access the Dashboard:
Open your browser and navigate to:
http://<your-truenas-ip>:40400

⚙️ Configuration

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
FROM cm2network/steamcmd:latest

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip build-essential ca-certificates wget \
        libffi-dev libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/spawnpoint

# Install Python dependencies first (better layer caching)
COPY webui/requirements.txt /opt/spawnpoint/webui/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r webui/requirements.txt

# Copy the rest of the project
COPY . /opt/spawnpoint

ENV PATH="/opt/venv/bin:${PATH}"

# Create directories for game data and config
RUN mkdir -p /opt/spawnpoint/games /opt/spawnpoint/SteamCMD

EXPOSE 40400

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:40400')" || exit 1

CMD ["python", "-m", "webui.app"]


FROM cm2network/steamcmd:latest

# Run as root so we can install Python + pip and build deps
USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip build-essential ca-certificates wget \
        libffi-dev libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/spawnpoint

# Copy the repository into the image
COPY . /opt/spawnpoint

# Create and activate a virtualenv to avoid "externally managed environment" errors
WORKDIR /opt/spawnpoint/webui
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Make the venv binaries available in PATH for the runtime
ENV PATH="/opt/venv/bin:${PATH}"

# Ensure the project root is the working directory so imports work
WORKDIR /opt/spawnpoint

# Expose the web UI port (NiceGUI)
EXPOSE 40400

# Run the web UI using NiceGUI (built-in uvicorn server)
CMD ["python", "-m", "webui.app"]


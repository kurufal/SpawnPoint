
FROM cm2network/steamcmd:latest

# Run as root so we can install Python + pip
USER root

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		python3 python3-pip \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /opt/spawnpoint

# Copy the repository into the image
COPY . /opt/spawnpoint

# Install Python dependencies for the web UI and ensure uvicorn is available
WORKDIR /opt/spawnpoint/webui
RUN pip3 install --no-cache-dir -r requirements.txt uvicorn

# Expose the web UI port (uvicorn)
EXPOSE 40400

# Run the web UI using uvicorn. Assumes an ASGI app named `app` is defined in `webui/app.py`.
CMD ["uvicorn", "webui.app:app", "--host", "0.0.0.0", "--port", "40400"]


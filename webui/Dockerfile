FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY flask_app.py .
COPY templates ./templates

# Expose the Flask port
EXPOSE 8080

# Run Flask-SocketIO app
CMD ["python", "flask_app.py"]

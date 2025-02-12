# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim

WORKDIR /app

# Copy configuration files
COPY pyproject.toml .
COPY requirements.txt .

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies and create virtual environment
RUN python -m pip install --upgrade pip
RUN python -m pip install uv

# Create virtual environment and install dependencies
RUN python -m venv .venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies using pip and uv in the virtual environment
RUN pip install uv
RUN uv pip install -r requirements.txt

# Copy application code
COPY . /app

# Copy entrypoint script
COPY entrypoint.sh /app/

# Ensure the entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]

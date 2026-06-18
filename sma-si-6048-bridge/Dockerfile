ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.11
FROM ${BUILD_FROM}

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY protocol.py .
COPY converter_addon.py .
COPY run_converter.sh /run.sh

RUN chmod +x /run.sh

# Set Python to unbuffered
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/run.sh"]

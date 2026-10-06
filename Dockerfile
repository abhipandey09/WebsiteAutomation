FROM python:3.11-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Tor and essential Linux system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    tor \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure Tor SOCKS and Control Ports
RUN echo "SocksPort 9050\nControlPort 9051\nCookieAuthentication 0" > /etc/tor/torrc

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and system OS libraries
RUN playwright install-deps chromium && \
    playwright install chromium

# Copy application source code
COPY . .

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

# Expose Streamlit default port
EXPOSE 8501

# Execute startup script
CMD ["./entrypoint.sh"]


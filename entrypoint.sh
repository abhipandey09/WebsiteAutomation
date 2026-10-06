#!/usr/bin/env bash
set -e

# Start Tor service in the background
echo "🧅 Starting Tor background service..."
service tor start || tor --runasdaemon 1
sleep 2

# Verify Tor ports
echo "Verifying Tor ports..."
curl --socks5 127.0.0.1:9050 -s https://api.ipify.org || echo "Tor circuit initializing..."

# Launch Streamlit bound to cloud-assigned PORT
PORT="${PORT:-8501}"
echo "🚀 Launching Streamlit on port ${PORT}..."
exec streamlit run app.py \
    --server.port "${PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true


# 🌐 Website Scroll Automator & IP Rotator (Streamlit + Playwright)

A high-performance local web automation dashboard built with **Streamlit** and **Playwright**. It automates website scrolling using **purely dynamic, random distances and natural human-like behavior** (no static coordinates) while seamlessly **rotating IP addresses after every N scrolls** without losing scroll position.

---

## ✨ Key Features

1. **Dynamic Coordinate-Free Scrolling**:
   - Eliminates fixed X/Y coordinates. Every scroll step computes a random pixel delta within user-defined min/max bounds (`min_scroll_px` to `max_scroll_px`).
   - Employs native smooth scrolling (`behavior: 'smooth'`) to prevent unnatural jumps.

2. **Automated Dynamic IP Address Rotation (Random Range: 5 to 10 Scrolls)**:
   - **Dynamic Unpredictable Batches**: Instead of a fixed N count, the engine picks a random number of scrolls (e.g., between 5 and 10) before each IP rotation cycle, completely eliminating periodic pattern detection.
   - **State & Scroll Position Preservation**: Caches the exact `window.scrollY` coordinate before rotating IP. After reconnecting under a new identity, it smoothly navigates back and restores the exact scroll position to continue scrolling seamlessly.
   - **Supported Rotation Methods**:
     - 🧪 **Simulation Mode**: Instantly rotates realistic global IPs with real geolocation metadata for quick offline testing.
     - 🛡️ **Custom VPN Command**: Executes any local VPN CLI command (e.g., `protonvpn-cli c -r`, `mullvad relay set location any`, WireGuard, or custom bash script).
     - 🔌 **Proxy Pool / List**: Sequentially cycles through a user-provided list of HTTP/SOCKS5 proxies.
     - 🧅 **Tor SOCKS5 Proxy**: Issues `SIGNAL NEWNYM` to the local Tor control port (`9051`) for automated global IP changes.

3. **Human Behavior Simulation**:
   - **Random Pauses**: Introduces randomized pauses (e.g., 1.5s to 3.5s) between scroll actions to simulate realistic reading behavior.
   - **Occasional Upward Scrolling**: Randomly performs subtle upward scrolls (default 15% probability) to mimic a reader reviewing previous content.

4. **Interactive Streamlit Dashboard**:
   - **Start & Stop Controls**: Multi-threaded execution allows immediate, non-blocking stops.
   - **Live Metric Cards**: Displays Automation Status, Total Scrolls, Next IP Change countdown, and Current Public IP with geolocation badge.
   - **Live Browser View**: Renders real-time page snapshots right inside the dashboard.
   - **IP Address History**: Tabular log tracking every IP used, timestamp, location, ISP, and trigger step.
   - **Real-Time Logs**: Terminal-style activity stream with export capabilities.

5. **Flexible Browser Modes**:
   - 🖥️ **Visible Chrome Window (Headed)**: Displays Chromium directly on your screen so you can observe the scrolling in real-time.
   - 🕶️ **Background Mode (Headless)**: Runs silently in the background without opening a browser window.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
Ensure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Launch the Application
Run the launcher script:
```bash
./start.sh
# or run directly with Streamlit:
streamlit run app.py
```

Open your browser at **`http://localhost:8501`**.

---

## ⚙️ Configuration Reference

| Parameter | Description | Default |
|---|---|---|
| **Target URL** | Website URL to automate | Wikipedia AI article |
| **Browser Window Mode** | Visible Chrome window or Headless | Visible Window |
| **IP Rotation Enabled** | Enable automatic IP rotation | Enabled |
| **Rotate Interval** | Number of scrolls before changing IP | 5 scrolls |
| **Rotation Method** | Simulation / VPN Command / Proxy List / Tor | Simulation |
| **Restore Scroll Position** | Restore vertical scroll position after rotation | Enabled |
| **Scroll Distance (px)** | Random min and max scroll distance per step | 120px - 480px |
| **Pause Delay (s)** | Random delay between scroll events | 1.5s - 3.8s |
| **Upward Chance (%)** | Probability of re-reading upward scroll | 18% |
| **Bottom Action** | Action upon reaching bottom (Bounce / Wait / Stop) | Bounce |
| **Max Scrolls Limit** | Total scroll limit (0 = Unlimited until stopped) | 0 (Unlimited) |

---

## 📁 Repository Structure

```
WebsiteAutomation/
├── app.py                # Streamlit UI & Live Dashboard
├── scroller_engine.py    # Playwright automation engine (Threading, Random Scrolling, IP Rotation)
├── requirements.txt      # Python dependencies
├── start.sh              # Bash launcher script
└── README.md             # Project documentation
```

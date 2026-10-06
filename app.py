import time
import json
import streamlit as st
from PIL import Image
import io
from scroller_engine import (
    ScrollerConfig,
    ScrollerRunner,
    ScrollerState,
    IPRotationConfig,
    detect_public_ip
)

# Set page configuration
st.set_page_config(
    page_title="AutoScroller | Website Scroll & IP Rotator",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .metric-card {
        background: #1e222d;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #2d3343;
        margin-bottom: 10px;
    }
    .status-badge-running {
        background-color: #10b981;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
    }
    .status-badge-rotating {
        background-color: #8b5cf6;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
        animation: pulse 1.5s infinite;
    }
    .status-badge-idle {
        background-color: #6b7280;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
    }
    .status-badge-stopped {
        background-color: #f59e0b;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
    }
    .status-badge-completed {
        background-color: #3b82f6;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
    }
    .status-badge-error {
        background-color: #ef4444;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        display: inline-block;
    }
    .ip-badge {
        background-color: #0f172a;
        color: #38bdf8;
        padding: 4px 10px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.95rem;
        font-weight: bold;
        border: 1px solid #0284c7;
    }
    .log-container {
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.85rem;
        background-color: #131720;
        color: #d1d5db;
        padding: 12px;
        border-radius: 8px;
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #1f2937;
    }
    .log-scroll { color: #60a5fa; }
    .log-success { color: #34d399; font-weight: bold; }
    .log-warn { color: #fbbf24; font-weight: bold; }
    .log-error { color: #f87171; font-weight: bold; }
    .log-info { color: #9ca3af; }
</style>
""", unsafe_allow_html=True)


# Initialize Session State
if "runner" not in st.session_state:
    st.session_state.runner = None

if "last_config" not in st.session_state:
    st.session_state.last_config = None


# --- SIDEBAR CONFIGURATION ---
st.sidebar.title("⚙️ Scroller & IP Settings")

# Profile Presets
preset = st.sidebar.selectbox(
    "Choose Preset Profile",
    ["🧑 Natural Human Reader", "⚡ Fast Skimmer", "🐢 Slow & Steady", "🛠️ Custom"]
)

# Preset Default values
if preset == "🧑 Natural Human Reader":
    def_min_px, def_max_px = 120, 480
    def_min_sec, def_max_sec = 1.5, 3.8
    def_upward = 18
elif preset == "⚡ Fast Skimmer":
    def_min_px, def_max_px = 300, 750
    def_min_sec, def_max_sec = 0.6, 1.8
    def_upward = 5
elif preset == "🐢 Slow & Steady":
    def_min_px, def_max_px = 80, 240
    def_min_sec, def_max_sec = 3.0, 6.0
    def_upward = 22
else:
    def_min_px, def_max_px = 150, 500
    def_min_sec, def_max_sec = 1.0, 3.0
    def_upward = 15

# Browser Mode
browser_visibility = st.sidebar.radio(
    "Browser Window Mode",
    ["🖥️ Visible Chrome Window (Headed)", "🕶️ Background / Silent (Headless)"],
    index=0,
    help="Select 'Visible Chrome Window' to watch the browser automatically scroll and rotate live on your Mac screen!"
)
is_headless = "Headless" in browser_visibility

# --- IP ROTATION & VPN CONFIGURATION ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🛡️ IP Address & VPN Rotation")
enable_ip_rotation = st.sidebar.checkbox(
    "Enable Automatic IP Rotation",
    value=True,
    help="Changes the IP address after a specified number of scrolls."
)

if enable_ip_rotation:
    rot_scroll_range = st.sidebar.slider(
        "Random Scrolls Range before IP Change",
        min_value=2,
        max_value=30,
        value=(5, 10),
        step=1,
        help="Before each IP rotation, a dynamic random number of scrolls is chosen between these two values (e.g. 5 to 10) to prevent predictable traffic patterns."
    )
    min_rot_scrolls, max_rot_scrolls = rot_scroll_range

    rot_mode_option = st.sidebar.selectbox(
        "IP Rotation Method",
        [
            ("tor", "🧅 Local Tor SOCKS5 Proxy (Free - Recommended)"),
            ("simulation", "🧪 Test Simulation Mode (Instant Demo)"),
            ("proxy_list", "🔌 Proxy Pool / List (HTTP/SOCKS5)"),
            ("vpn_command", "🛡️ Custom VPN Reconnect Command")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]

    vpn_cmd = ""
    vpn_wait = 6.0
    proxy_list_input = []
    tor_control_port = 9051
    tor_password = ""

    if rot_mode_option == "vpn_command":
        st.sidebar.caption("Execute a shell command to reconnect/switch your VPN provider CLI:")
        vpn_cmd = st.sidebar.text_input(
            "VPN Reconnect Shell Command",
            value="protonvpn-cli c -r",
            placeholder="e.g. protonvpn-cli c -r or mullvad relay set location any"
        )
        vpn_wait = st.sidebar.slider(
            "Wait after VPN command (seconds)",
            min_value=2.0,
            max_value=20.0,
            value=6.0,
            step=1.0,
            help="Allows VPN network adapter handshake to settle before page reloads."
        )

    elif rot_mode_option == "proxy_list":
        st.sidebar.caption("Enter proxies (one per line):")
        proxies_text = st.sidebar.text_area(
            "Proxy List",
            value="http://127.0.0.1:8080\nhttp://127.0.0.1:8081",
            placeholder="http://user:pass@host:port\nsocks5://host:port"
        )
        proxy_list_input = [p.strip() for p in proxies_text.splitlines() if p.strip()]

    elif rot_mode_option == "tor":
        st.sidebar.caption("Uses local Tor SOCKS5 proxy on `127.0.0.1:9050`")
        tor_control_port = st.sidebar.number_input("Tor Control Port", value=9051, step=1)
        tor_password = st.sidebar.text_input("Tor Control Password (if any)", value="", type="password")
        st.sidebar.info("💡 Tor is active with auto-rotation on ControlPort 9051!")

    elif rot_mode_option == "simulation":
        st.sidebar.info("💡 **Simulation Mode Active**: Automatically switches realistic international IPs every dynamic batch for offline testing without external networks.")

    restore_scroll = st.sidebar.checkbox(
        "Restore Scroll Position after IP Change",
        value=True,
        help="Remembers the exact pixel position and restores it after rotating IP."
    )
else:
    min_rot_scrolls, max_rot_scrolls = 5, 10
    rot_mode_option = "simulation"
    vpn_cmd = ""
    vpn_wait = 6.0
    proxy_list_input = []
    tor_control_port = 9051
    tor_password = ""
    restore_scroll = True

# --- SCROLL BEHAVIOR CONTROLS ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎲 Random Scroll Distance (Pixels)")
scroll_range = st.sidebar.slider(
    "Min & Max Scroll per step (px)",
    min_value=50,
    max_value=1200,
    value=(def_min_px, def_max_px),
    step=25,
    help="Each scroll will randomly pick a distance between these two values without any fixed coordinates."
)

st.sidebar.markdown("### ⏱️ Random Pause Delay (Seconds)")
delay_range = st.sidebar.slider(
    "Min & Max Pause after each scroll (sec)",
    min_value=0.2,
    max_value=10.0,
    value=(def_min_sec, def_max_sec),
    step=0.1,
    help="Random wait time before the next scroll to mimic realistic user reading pauses."
)

st.sidebar.markdown("### 🧠 Human Behavior Simulation")
upward_pct = st.sidebar.slider(
    "Random Upward Scroll Chance (%)",
    min_value=0,
    max_value=40,
    value=def_upward,
    step=1,
    help="Simulates real human behavior where a user occasionally scrolls up slightly to re-read content."
)

smooth_scroll = st.sidebar.checkbox(
    "Enable Smooth Scrolling",
    value=True,
    help="Animates scroll movement naturally instead of sudden jumps."
)

bottom_action = st.sidebar.selectbox(
    "Action when Bottom is Reached",
    [
        ("bounce", "🔄 Bounce back up & continue"),
        ("wait_infinite", "⏳ Wait for Infinite Scroll / Lazy Load"),
        ("stop", "🛑 Stop automation")
    ],
    format_func=lambda x: x[1]
)[0]

st.sidebar.markdown("### 🛑 Execution Limits")
max_scrolls = st.sidebar.number_input(
    "Max Scrolls Limit (0 = Run until manually stopped)",
    min_value=0,
    max_value=10000,
    value=0,
    step=10,
    help="Set to 0 to keep scrolling endlessly until you click 'Stop Automation'."
)


# --- MAIN CONTENT AREA ---
st.title("🌐 Website Scroll & IP Rotator")
st.caption("Automate dynamic coordinate-free scrolling with automatic IP address rotation after every N scrolls (VPN, Proxy, Tor, or Simulation).")

# URL Input and Preset Buttons
col_url, col_quick = st.columns([3, 1])

with col_url:
    target_url = st.text_input(
        "Enter Target Website URL:",
        value="https://en.wikipedia.org/wiki/Artificial_intelligence",
        placeholder="https://example.com or any news/blog URL"
    )

with col_quick:
    st.write("Quick Samples:")
    q_col1, q_col2 = st.columns(2)
    if q_col1.button("Wikipedia", use_container_width=True):
        target_url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
    if q_col2.button("BBC News", use_container_width=True):
        target_url = "https://www.bbc.com"


# Determine runner state
current_runner: ScrollerRunner = st.session_state.runner
is_active = current_runner is not None and current_runner.is_running()


# Start / Stop Buttons
st.markdown("---")
btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 4])

with btn_col1:
    start_clicked = st.button(
        "▶️ Start Automated Scrolling",
        type="primary",
        use_container_width=True,
        disabled=is_active
    )

with btn_col2:
    stop_clicked = st.button(
        "⏹️ Stop Scrolling",
        type="secondary",
        use_container_width=True,
        disabled=not is_active
    )

with btn_col3:
    if is_active:
        runner_state = current_runner.get_state()
        if runner_state.status == "ROTATING_IP":
            st.markdown('<span class="status-badge-rotating">⚡ ROTATING IP ADDRESS...</span> Switching identity...', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge-running">● AUTOMATION ACTIVE</span> Scrolling in progress...', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge-idle">● READY</span> Configure settings and click Start.', unsafe_allow_html=True)

# Button Handlers
if start_clicked:
    if not target_url.strip():
        st.error("Please enter a valid URL.")
    else:
        ip_rot_config = IPRotationConfig(
            enabled=enable_ip_rotation,
            min_scrolls_before_rotation=int(min_rot_scrolls),
            max_scrolls_before_rotation=int(max_rot_scrolls),
            mode=rot_mode_option,
            vpn_reconnect_cmd=vpn_cmd,
            vpn_wait_sec=float(vpn_wait),
            proxy_list=proxy_list_input,
            tor_control_port=int(tor_control_port),
            tor_control_password=tor_password,
            restore_scroll_position=restore_scroll
        )

        config = ScrollerConfig(
            url=target_url.strip(),
            headless=is_headless,
            min_scroll_px=scroll_range[0],
            max_scroll_px=scroll_range[1],
            min_delay_sec=delay_range[0],
            max_delay_sec=delay_range[1],
            upward_chance=upward_pct / 100.0,
            smooth_scroll=smooth_scroll,
            max_scrolls=int(max_scrolls),
            bottom_action=bottom_action,
            capture_screenshots=True,
            rotation=ip_rot_config
        )
        # Create and start runner
        runner = ScrollerRunner(config)
        runner.start()
        st.session_state.runner = runner
        st.session_state.last_config = config
        st.rerun()

if stop_clicked and current_runner:
    current_runner.stop()
    st.rerun()


# --- REAL-TIME LIVE DASHBOARD (UPDATES EVERY 1s VIA STREAMLIT FRAGMENT) ---
@st.fragment(run_every="1s")
def render_live_dashboard():
    runner: ScrollerRunner = st.session_state.runner

    if runner is None:
        state = ScrollerState(status="IDLE", last_action="Awaiting user command")
        target_rot = 5
        range_str = "5-10"
    else:
        state = runner.get_state()
        target_rot = state.target_scrolls_for_rotation
        rot_cfg = runner.config.rotation
        range_str = f"{rot_cfg.min_scrolls_before_rotation}-{rot_cfg.max_scrolls_before_rotation}"

    # Status Badge Mapping
    status_html_map = {
        "IDLE": '<span class="status-badge-idle">IDLE</span>',
        "STARTING": '<span class="status-badge-running">STARTING...</span>',
        "RUNNING": '<span class="status-badge-running">RUNNING</span>',
        "ROTATING_IP": '<span class="status-badge-rotating">🔄 ROTATING IP</span>',
        "STOPPED": '<span class="status-badge-stopped">STOPPED</span>',
        "COMPLETED": '<span class="status-badge-completed">COMPLETED</span>',
        "ERROR": '<span class="status-badge-error">ERROR</span>',
    }
    status_badge = status_html_map.get(state.status, state.status)

    st.markdown("### 📊 Live Automation & IP Dashboard")

    # 4 Metric Cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"**Status**<br>{status_badge}", unsafe_allow_html=True)
        if state.page_title:
            st.caption(f"📑 {state.page_title[:32]}...")
    with m2:
        st.metric("Total Scrolls", state.scroll_count)
        if state.last_delay > 0:
            st.caption(f"Last delay: {state.last_delay}s")
    with m3:
        # IP Rotation Tracker
        if state.status in ("RUNNING", "ROTATING_IP", "STARTING"):
            remaining_to_rot = max(0, target_rot - state.scrolls_since_rotation)
            st.metric("Next IP Change", f"in {remaining_to_rot} scrolls")
            st.caption(f"Batch: {state.scrolls_since_rotation}/{target_rot} (Dynamic target from {range_str})")
        else:
            st.metric("Rotations Done", f"{state.rotation_count} times")
            st.caption(f"Random target range: {range_str} scrolls")
    with m4:
        st.markdown(f"**Current Public IP**<br><span class='ip-badge'>{state.current_ip}</span>", unsafe_allow_html=True)
        if state.current_location:
            st.caption(f"📍 {state.current_location} ({state.current_isp[:20]})")

    # Visual Scroll Progress Bar
    if state.total_height > 0:
        scroll_percent = min(1.0, max(0.0, (state.current_y + state.viewport_height) / state.total_height))
        st.progress(scroll_percent, text=f"Scroll Progress: {int(scroll_percent * 100)}% through page | Current Y: {state.current_y:,} px")

    # Live Tabs: Visual Preview, IP Timeline, Activity Log, How It Works
    tab_view, tab_ip, tab_logs, tab_about = st.tabs([
        "👁️ Live Page View",
        "🌐 IP Address History",
        "📜 Real-Time Logs",
        "💡 VPN & IP Rotation Guide"
    ])

    with tab_view:
        if state.screenshot_bytes:
            img = Image.open(io.BytesIO(state.screenshot_bytes))
            st.image(img, caption=f"Live Browser View (Scroll #{state.scroll_count} | IP: {state.current_ip} | Y: {state.current_y}px)", use_container_width=True)
        else:
            if state.status in ("RUNNING", "ROTATING_IP"):
                st.info("Capturing live view snapshot...")
            else:
                st.info("Launch automation to view live page rendering here. You can also see the real browser window if 'Visible Chrome Window' is selected!")

    with tab_ip:
        st.markdown("#### 🔄 Recorded IP Address Rotations")
        if state.ip_history:
            # Render IP history table
            ip_table_data = []
            for idx, h in enumerate(state.ip_history):
                ip_table_data.append({
                    "#": idx + 1,
                    "Timestamp": h.get("time", ""),
                    "Public IP": h.get("ip", ""),
                    "Location / Country": h.get("location", ""),
                    "ISP / Network": h.get("isp", ""),
                    "Triggered at Scroll": f"Scroll #{h.get('scroll_step', 0)}",
                    "Batch Target": f"{h.get('batch_target', '--')} scrolls"
                })
            st.table(ip_table_data)
        else:
            st.info("No IP rotation events recorded yet. Start automation to see the IP timeline populate as dynamic batches complete!")

    with tab_logs:
        log_html_lines = []
        for entry in reversed(state.logs):
            lvl = entry.get("level", "INFO")
            t = entry.get("time", "")
            msg = entry.get("message", "")
            css_class = {
                "SCROLL": "log-scroll",
                "SUCCESS": "log-success",
                "WARN": "log-warn",
                "ERROR": "log-error",
                "INFO": "log-info"
            }.get(lvl, "log-info")
            log_html_lines.append(f"<div><span style='color: #64748b;'>[{t}]</span> <span class='{css_class}'>[{lvl}]</span> {msg}</div>")

        log_display_content = "".join(log_html_lines) if log_html_lines else "<div class='log-info'>No logs recorded yet.</div>"
        st.markdown(f"<div class='log-container'>{log_display_content}</div>", unsafe_allow_html=True)

        if state.logs:
            logs_json = json.dumps(state.logs, indent=2)
            st.download_button(
                "📥 Export Activity Logs (JSON)",
                data=logs_json,
                file_name=f"scroll_logs_{int(time.time())}.json",
                mime="application/json"
            )

    with tab_about:
        st.markdown("""
        ### 🌐 How Automated Scrolling & IP Rotation Works:

        1. **Dynamic Coordinate-Free Scrolling**:
           - Does not rely on static coordinates. For every scroll step, the engine dynamically calculates a random pixel offset within the configured minimum and maximum bounds.
        2. **Human Behavior Simulation**:
           - **Variable Delays**: Enforces randomized pauses between scroll movements to mirror genuine reading intervals.
           - **Upward Scroll Probability**: Randomly scrolls upward by a moderate distance (default ~15% chance) to simulate a user re-reading earlier content.
        3. **State & Position Preservation**:
           - Prior to initiating an IP rotation, the exact vertical scroll coordinate (`window.scrollY`) is cached.
        4. **IP Rotation Execution**:
           - **🧪 Simulation Mode**: Instantly switches realistic international IP addresses with geolocation metadata for local end-to-end testing without external dependencies.
           - **🛡️ Custom VPN Command**: Executes your local VPN CLI tool (e.g., `protonvpn-cli c -r`, `mullvad relay set location any`) and waits for network stabilization.
           - **🔌 Proxy Pool**: Rotates through a provided list of HTTP/SOCKS5 proxies sequentially.
           - **🧅 Tor SOCKS5 Proxy**: Issues `SIGNAL NEWNYM` to the local Tor daemon on port 9051 to establish a new circuit and IP.
        5. **Verification & Resumption**:
           - Queries the public IP endpoint to verify the new identity, records it in the history timeline, navigates to the target page, smoothly restores the previous scroll position, and seamlessly resumes scrolling.
        """)


# Render dashboard fragment
render_live_dashboard()

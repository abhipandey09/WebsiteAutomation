import time
import random
import threading
import subprocess
import socket
import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


@dataclass
class IPRotationConfig:
    enabled: bool = True
    min_scrolls_before_rotation: int = 5
    max_scrolls_before_rotation: int = 10
    mode: str = "simulation"  # "simulation", "vpn_command", "proxy_list", "tor"
    vpn_reconnect_cmd: str = ""
    vpn_wait_sec: float = 6.0
    proxy_list: List[str] = field(default_factory=list)
    tor_proxy: str = "socks5://127.0.0.1:9050"
    tor_control_port: int = 9051
    tor_control_password: str = ""
    restore_scroll_position: bool = True


@dataclass
class ScrollerConfig:
    url: str
    headless: bool = False
    min_scroll_px: int = 150
    max_scroll_px: int = 550
    min_delay_sec: float = 1.0
    max_delay_sec: float = 3.5
    upward_chance: float = 0.15
    smooth_scroll: bool = True
    max_scrolls: int = 0
    bottom_action: str = "bounce"
    capture_screenshots: bool = True
    window_width: int = 1280
    window_height: int = 800
    rotation: IPRotationConfig = field(default_factory=IPRotationConfig)


@dataclass
class ScrollerState:
    status: str = "IDLE"
    url: str = ""
    page_title: str = ""
    scroll_count: int = 0
    current_y: int = 0
    total_height: int = 0
    viewport_height: int = 0
    last_action: str = "Ready to start"
    last_delta: int = 0
    last_delay: float = 0.0
    screenshot_bytes: Optional[bytes] = None
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    logs: List[Dict[str, str]] = field(default_factory=list)
    # IP Rotation State
    current_ip: str = "Detecting..."
    current_location: str = "Unknown"
    current_isp: str = "Unknown"
    rotation_count: int = 0
    scrolls_since_rotation: int = 0
    target_scrolls_for_rotation: int = 5
    ip_history: List[Dict[str, any]] = field(default_factory=list)


SIMULATED_IPS = [
    {"ip": "185.220.101.5", "country": "Germany 🇩🇪", "city": "Frankfurt", "isp": "Tor Exit Node DE"},
    {"ip": "198.51.100.42", "country": "United States 🇺🇸", "city": "New York", "isp": "Cloud Provider US"},
    {"ip": "103.14.26.110", "country": "Singapore 🇸🇬", "city": "Singapore", "isp": "SingTel Internet"},
    {"ip": "194.26.29.88", "country": "Netherlands 🇳🇱", "city": "Amsterdam", "isp": "Serverius Holding"},
    {"ip": "151.80.35.12", "country": "France 🇫🇷", "city": "Paris", "isp": "OVH SAS"},
    {"ip": "133.242.18.99", "country": "Japan 🇯🇵", "city": "Tokyo", "isp": "SAKURA Internet"},
    {"ip": "51.15.89.201", "country": "United Kingdom 🇬🇧", "city": "London", "isp": "Scaleway UK"},
    {"ip": "104.28.19.44", "country": "Canada 🇨🇦", "city": "Toronto", "isp": "Cloudflare CDN CA"},
]


def detect_public_ip(context: Optional[BrowserContext] = None) -> Dict[str, str]:
    """Fetch real public IP and geo location through the browser's proxy/Tor tunnel."""
    if context:
        check_page = None
        try:
            check_page = context.new_page()
            check_page.goto("https://api.ipify.org?format=json", timeout=20000)
            raw = check_page.locator("pre").inner_text()
            data = json.loads(raw)
            ip = data.get("ip", "").strip()
            if ip:
                # Query geolocation metadata for this specific IP
                try:
                    req = urllib.request.Request(f"http://ip-api.com/json/{ip}", headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=4) as response:
                        geo = json.loads(response.read().decode())
                        return {
                            "ip": ip,
                            "country": f"{geo.get('country', '')} {geo.get('city', '')}".strip() or "Tor / Proxy Network",
                            "isp": geo.get("isp", "Secure Relay")
                        }
                except Exception:
                    return {"ip": ip, "country": "Tor / Proxy Network", "isp": "Encrypted Relay"}
        except Exception:
            pass
        finally:
            if check_page:
                try:
                    check_page.close()
                except Exception:
                    pass

    # Fallback to direct Python request (only for direct/non-proxy mode)
    try:
        req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            return {
                "ip": data.get("query", "Unknown"),
                "country": f"{data.get('country', '')} {data.get('city', '')}".strip() or "Unknown",
                "isp": data.get("isp", "Unknown")
            }
    except Exception:
        pass

    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            return {"ip": data.get("ip", "Unknown"), "country": "Unknown", "isp": "Unknown"}
    except Exception:
        return {"ip": "Unknown", "country": "Unknown", "isp": "Unknown"}


def signal_tor_newnym(port: int = 9051, password: str = "") -> bool:
    """Send SIGNAL NEWNYM to Tor Control Port to request a new circuit and IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4)
        s.connect(("127.0.0.1", port))
        auth_cmd = f'AUTHENTICATE "{password}"\r\n' if password else 'AUTHENTICATE\r\n'
        s.sendall(auth_cmd.encode())
        res = s.recv(1024).decode()
        if "250" in res:
            s.sendall(b'SIGNAL NEWNYM\r\n')
            res2 = s.recv(1024).decode()
            s.close()
            return "250" in res2
        s.close()
    except Exception:
        pass
    return False


class ScrollerRunner:
    def __init__(self, config: ScrollerConfig):
        self.config = config
        self.state = ScrollerState(url=config.url)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._proxy_index = 0
        self._sim_ip_index = 0

    def add_log(self, message: str, level: str = "INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.state.logs.append({
                "time": now_str,
                "level": level,
                "message": message
            })
            if len(self.state.logs) > 250:
                self.state.logs.pop(0)

    def record_ip(self, ip: str, location: str, isp: str, at_scroll: int, batch_target: int = 0):
        with self._lock:
            self.state.current_ip = ip
            self.state.current_location = location
            self.state.current_isp = isp
            now_str = datetime.now().strftime("%H:%M:%S")
            self.state.ip_history.append({
                "time": now_str,
                "ip": ip,
                "location": location,
                "isp": isp,
                "scroll_step": at_scroll,
                "batch_target": batch_target or self.state.target_scrolls_for_rotation
            })

    def get_state(self) -> ScrollerState:
        with self._lock:
            return ScrollerState(
                status=self.state.status,
                url=self.state.url,
                page_title=self.state.page_title,
                scroll_count=self.state.scroll_count,
                current_y=self.state.current_y,
                total_height=self.state.total_height,
                viewport_height=self.state.viewport_height,
                last_action=self.state.last_action,
                last_delta=self.state.last_delta,
                last_delay=self.state.last_delay,
                screenshot_bytes=self.state.screenshot_bytes,
                error_message=self.state.error_message,
                start_time=self.state.start_time,
                logs=list(self.state.logs),
                current_ip=self.state.current_ip,
                current_location=self.state.current_location,
                current_isp=self.state.current_isp,
                rotation_count=self.state.rotation_count,
                scrolls_since_rotation=self.state.scrolls_since_rotation,
                target_scrolls_for_rotation=self.state.target_scrolls_for_rotation,
                ip_history=list(self.state.ip_history)
            )

    def is_running(self) -> bool:
        with self._lock:
            return self.state.status in ("STARTING", "RUNNING", "ROTATING_IP")

    def start(self):
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_automation, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.add_log("Stop requested by user...", "WARN")
        with self._lock:
            if self.state.status in ("RUNNING", "ROTATING_IP"):
                self.state.status = "STOPPED"
                self.state.last_action = "Stopped by user"

    def _sleep_interruptible(self, seconds: float) -> bool:
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._stop_event.is_set():
                return False
            time.sleep(0.1)
        return True

    def _get_current_proxy_dict(self) -> Optional[Dict[str, str]]:
        rot = self.config.rotation
        if not rot.enabled:
            return None

        if rot.mode == "tor":
            return {"server": rot.tor_proxy}

        elif rot.mode == "proxy_list" and rot.proxy_list:
            clean_list = [p.strip() for p in rot.proxy_list if p.strip()]
            if clean_list:
                selected_proxy = clean_list[self._proxy_index % len(clean_list)]
                return {"server": selected_proxy}

        return None

    def _run_automation(self):
        rot = self.config.rotation
        initial_target = random.randint(
            min(rot.min_scrolls_before_rotation, rot.max_scrolls_before_rotation),
            max(rot.min_scrolls_before_rotation, rot.max_scrolls_before_rotation)
        )
        with self._lock:
            self.state.status = "STARTING"
            self.state.start_time = time.time()
            self.state.scroll_count = 0
            self.state.rotation_count = 0
            self.state.scrolls_since_rotation = 0
            self.state.target_scrolls_for_rotation = initial_target
            self.state.last_action = "Launching browser..."

        self.add_log(f"Launching Chromium (Headless: {self.config.headless})...", "INFO")
        self.add_log(f"🎲 Initial dynamic target: {initial_target} scrolls before first IP rotation (range: {rot.min_scrolls_before_rotation}-{rot.max_scrolls_before_rotation}).", "INFO")

        playwright = None
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        try:
            playwright = sync_playwright().start()

            import os, sys
            effective_headless = self.config.headless
            if not effective_headless and sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
                effective_headless = True
                self.add_log("No graphical display detected on Linux host. Running in Headless mode.", "INFO")

            # Anti-leak and stealth flags
            browser = playwright.chromium.launch(
                headless=effective_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--force-webrtc-ip-handling-policy",
                    "--start-maximized"
                ]
            )

            def create_page_session():
                nonlocal context, page
                proxy_dict = self._get_current_proxy_dict()
                context_args = {
                    "viewport": {"width": self.config.window_width, "height": self.config.window_height},
                    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                if proxy_dict:
                    context_args["proxy"] = proxy_dict

                context = browser.new_context(**context_args)
                page = context.new_page()
                return context, page

            # Create initial context
            context, page = create_page_session()

            # Detect Initial IP accurately through the browser's context
            if self.config.rotation.mode == "simulation":
                initial_ip_info = SIMULATED_IPS[0]
                self._sim_ip_index = 0
            elif self.config.rotation.mode in ("tor", "proxy_list"):
                self.add_log("Verifying proxy / Tor identity through browser...", "INFO")
                initial_ip_info = detect_public_ip(context)
            else:
                initial_ip_info = detect_public_ip(None)

            self.record_ip(initial_ip_info["ip"], initial_ip_info["country"], initial_ip_info["isp"], 0)
            self.add_log(f"Initial Public IP: {initial_ip_info['ip']} ({initial_ip_info['country']})", "SUCCESS")

            target_url = self.config.url.strip()
            if not target_url.startswith(("http://", "https://")):
                target_url = "https://" + target_url

            self.add_log(f"Navigating to: {target_url}", "INFO")
            with self._lock:
                self.state.last_action = f"Opening {target_url}..."

            # Resilient navigation loop with retries for Tor circuit warm-up
            nav_success = False
            for attempt in range(3):
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=50000)
                    nav_success = True
                    break
                except Exception as e:
                    if attempt < 2 and not self._stop_event.is_set():
                        self.add_log(f"Circuit establishing... Retrying page load (Attempt {attempt + 2}/3)...", "WARN")
                        time.sleep(3.0)
                    else:
                        self.add_log(f"Navigation notice: {str(e)[:100]}", "WARN")

            if not self._sleep_interruptible(2.0):
                return

            page_title = page.title()
            with self._lock:
                self.state.status = "RUNNING"
                self.state.page_title = page_title
                self.state.url = page.url

            self.add_log(f"Page loaded: '{page_title}' ({page.url})", "SUCCESS")

            # Capture initial screenshot if enabled
            if self.config.capture_screenshots:
                try:
                    shot = page.screenshot(type="jpeg", quality=65)
                    with self._lock:
                        self.state.screenshot_bytes = shot
                except Exception:
                    pass

            bottom_consecutive_count = 0

            # Main Random Scrolling Loop
            while not self._stop_event.is_set():
                if self.config.max_scrolls > 0 and self.state.scroll_count >= self.config.max_scrolls:
                    self.add_log(f"Reached maximum scroll target of {self.config.max_scrolls} scrolls.", "SUCCESS")
                    with self._lock:
                        self.state.status = "COMPLETED"
                        self.state.last_action = "Target scroll count completed."
                    break

                try:
                    metrics = page.evaluate("""() => ({
                        y: Math.round(window.scrollY || window.pageYOffset || 0),
                        totalHeight: Math.round(Math.max(
                            document.body.scrollHeight,
                            document.documentElement.scrollHeight,
                            document.body.offsetHeight,
                            document.documentElement.offsetHeight,
                            document.body.clientHeight,
                            document.documentElement.clientHeight
                        )),
                        innerHeight: Math.round(window.innerHeight || 0)
                    })""")
                except Exception as eval_err:
                    self.add_log(f"Dimension check error: {eval_err}", "WARN")
                    metrics = {"y": 0, "totalHeight": 1000, "innerHeight": 800}

                current_y = metrics.get("y", 0)
                total_height = metrics.get("totalHeight", 1000)
                inner_height = metrics.get("innerHeight", 800)

                with self._lock:
                    self.state.current_y = current_y
                    self.state.total_height = total_height
                    self.state.viewport_height = inner_height

                is_at_bottom = (current_y + inner_height >= total_height - 60)

                if is_at_bottom:
                    bottom_consecutive_count += 1
                    self.add_log(f"Reached bottom of page (Y: {current_y}px, Total: {total_height}px)", "WARN")

                    if self.config.bottom_action == "stop":
                        self.add_log("Bottom reached and 'Stop' action configured. Finishing.", "SUCCESS")
                        with self._lock:
                            self.state.status = "COMPLETED"
                            self.state.last_action = "Reached bottom of page."
                        break

                    elif self.config.bottom_action == "wait_infinite":
                        self.add_log("Waiting for infinite scroll / lazy-loaded content to appear...", "INFO")
                        with self._lock:
                            self.state.last_action = "Waiting for infinite scroll content..."

                        page.evaluate("window.scrollBy({ top: 150, behavior: 'smooth' })")
                        if not self._sleep_interruptible(3.0):
                            break

                        new_height = page.evaluate("document.documentElement.scrollHeight")
                        if new_height > total_height + 50:
                            self.add_log(f"New content loaded! Page expanded from {total_height}px to {new_height}px", "SUCCESS")
                            bottom_consecutive_count = 0
                            continue
                        elif bottom_consecutive_count >= 3:
                            self.add_log("No further content loaded after 3 attempts. Bouncing back upward.", "INFO")
                            bounce_dist = max(150, random.randint(int(total_height * 0.2), max(int(total_height * 0.6), 300)))
                            delta = -bounce_dist
                            direction_desc = "Upward (Bounce from bottom)"
                        else:
                            continue
                    else:  # "bounce"
                        bounce_dist = max(150, random.randint(int(total_height * 0.2), max(int(total_height * 0.6), 300)))
                        delta = -bounce_dist
                        direction_desc = "Upward (Bounce from bottom)"
                        self.add_log(f"Bouncing back up by {abs(delta)}px...", "INFO")
                else:
                    bottom_consecutive_count = 0
                    roll = random.random()
                    if roll < self.config.upward_chance and current_y > 400:
                        delta = -random.randint(
                            int(self.config.min_scroll_px * 0.5),
                            int(self.config.max_scroll_px * 0.7)
                        )
                        direction_desc = "Upward (Re-reading)"
                    else:
                        delta = random.randint(self.config.min_scroll_px, self.config.max_scroll_px)
                        direction_desc = "Downward"

                scroll_behavior = "smooth" if self.config.smooth_scroll else "auto"
                try:
                    page.evaluate(f"window.scrollBy({{ top: {delta}, left: 0, behavior: '{scroll_behavior}' }})")
                except Exception as scroll_err:
                    self.add_log(f"Scroll call error: {scroll_err}", "WARN")

                random_delay = round(random.uniform(self.config.min_delay_sec, self.config.max_delay_sec), 2)
                action_text = f"Scrolled {direction_desc} by {abs(delta)}px | Pausing {random_delay}s"

                with self._lock:
                    self.state.scroll_count += 1
                    self.state.scrolls_since_rotation += 1
                    self.state.last_delta = delta
                    self.state.last_delay = random_delay
                    self.state.last_action = action_text

                self.add_log(f"Scroll #{self.state.scroll_count} ({self.state.scrolls_since_rotation}/{self.state.target_scrolls_for_rotation} before IP change): {action_text}", "SCROLL")

                if self.config.capture_screenshots and (self.state.scroll_count % 2 == 0 or is_at_bottom):
                    try:
                        shot = page.screenshot(type="jpeg", quality=60)
                        with self._lock:
                            self.state.screenshot_bytes = shot
                    except Exception:
                        pass

                if not self._sleep_interruptible(random_delay):
                    break

                # --- CHECK IP ROTATION CONDITION ---
                rot = self.config.rotation
                if rot.enabled and self.state.scrolls_since_rotation >= self.state.target_scrolls_for_rotation:
                    completed_target = self.state.target_scrolls_for_rotation
                    self.add_log(f"⚡ Dynamic target of {completed_target} scrolls reached! Rotating IP address...", "WARN")

                    with self._lock:
                        self.state.status = "ROTATING_IP"
                        self.state.last_action = "Rotating IP..."

                    # 1. Save exact scroll position
                    try:
                        saved_scroll_y = page.evaluate("window.scrollY || window.pageYOffset || 0")
                    except Exception:
                        saved_scroll_y = self.state.current_y

                    # 2. Close current browser context
                    try:
                        page.close()
                        context.close()
                    except Exception:
                        pass

                    new_info = {"ip": "Unknown", "country": "Unknown", "isp": "Unknown"}

                    # 3. Trigger network/identity change
                    if rot.mode == "simulation":
                        self._sim_ip_index = (self._sim_ip_index + 1) % len(SIMULATED_IPS)
                        new_info = SIMULATED_IPS[self._sim_ip_index]
                        time.sleep(1.5)

                    elif rot.mode == "tor":
                        self.add_log(f"Sending SIGNAL NEWNYM to Tor Control Port {rot.tor_control_port}...", "INFO")
                        success = signal_tor_newnym(rot.tor_control_port, rot.tor_control_password)
                        if success:
                            self.add_log("Tor accepted NEWNYM signal! Building new circuit...", "SUCCESS")
                        else:
                            self.add_log("Tor Control Port connection notice. Re-routing circuit...", "WARN")

                        # Give Tor time to build the new circuit
                        if not self._sleep_interruptible(3.0):
                            break

                    elif rot.mode == "proxy_list":
                        clean_list = [p.strip() for p in rot.proxy_list if p.strip()]
                        if clean_list:
                            self._proxy_index += 1
                            curr_proxy = clean_list[self._proxy_index % len(clean_list)]
                            self.add_log(f"Switched to proxy: {curr_proxy}", "INFO")

                    elif rot.mode == "vpn_command":
                        if rot.vpn_reconnect_cmd.strip():
                            self.add_log(f"Executing VPN command: {rot.vpn_reconnect_cmd}", "INFO")
                            try:
                                subprocess.run(rot.vpn_reconnect_cmd, shell=True, timeout=20)
                            except Exception as cmd_err:
                                self.add_log(f"VPN command error: {cmd_err}", "ERROR")
                            if not self._sleep_interruptible(rot.vpn_wait_sec):
                                break

                    # 4. Open fresh session under the new identity
                    self.add_log(f"Launching clean browser session and verifying new identity...", "INFO")
                    context, page = create_page_session()

                    # 5. Detect new IP through the new session
                    if rot.mode != "simulation":
                        new_info = detect_public_ip(context if rot.mode in ("tor", "proxy_list") else None)

                    # 6. Pick next random target for the upcoming cycle
                    next_target = random.randint(
                        min(rot.min_scrolls_before_rotation, rot.max_scrolls_before_rotation),
                        max(rot.min_scrolls_before_rotation, rot.max_scrolls_before_rotation)
                    )

                    with self._lock:
                        self.state.rotation_count += 1
                        self.state.scrolls_since_rotation = 0
                        self.state.target_scrolls_for_rotation = next_target

                    self.record_ip(new_info["ip"], new_info["country"], new_info["isp"], self.state.scroll_count, completed_target)
                    self.add_log(f"✅ IP Rotation Complete! Current IP: {new_info['ip']} ({new_info['country']})", "SUCCESS")
                    self.add_log(f"🎲 Next dynamic target: {next_target} scrolls before next IP rotation (range: {rot.min_scrolls_before_rotation}-{rot.max_scrolls_before_rotation}).", "INFO")

                    # 6. Reload target URL with retry
                    self.add_log(f"Reloading target page: {target_url}...", "INFO")
                    for attempt in range(3):
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=50000)
                            break
                        except Exception:
                            if attempt < 2 and not self._stop_event.is_set():
                                time.sleep(3.0)

                    # 7. Restore scroll position
                    if rot.restore_scroll_position and saved_scroll_y > 0:
                        self.add_log(f"📍 Restoring exact scroll position to {saved_scroll_y}px...", "INFO")
                        try:
                            page.evaluate(f"window.scrollTo({{ top: {saved_scroll_y}, behavior: 'smooth' }})")
                        except Exception as restore_err:
                            self.add_log(f"Restore scroll notice: {restore_err}", "WARN")

                    with self._lock:
                        self.state.status = "RUNNING"
                        self.state.last_action = f"Resumed scrolling with IP {self.state.current_ip}"

                    self.add_log(f"🚀 Resumed scrolling under new IP: {self.state.current_ip}!", "SUCCESS")

                    if not self._sleep_interruptible(1.5):
                        break

        except Exception as e:
            err_msg = str(e)
            self.add_log(f"Error in automation: {err_msg}", "ERROR")
            with self._lock:
                self.state.status = "ERROR"
                self.state.error_message = err_msg
                self.state.last_action = f"Error: {err_msg[:60]}"
        finally:
            self.add_log("Cleaning up browser session...", "INFO")
            try:
                if page:
                    page.close()
            except Exception:
                pass
            try:
                if context:
                    context.close()
            except Exception:
                pass
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if playwright:
                    playwright.stop()
            except Exception:
                pass

            with self._lock:
                if self.state.status in ("STARTING", "RUNNING", "ROTATING_IP"):
                    self.state.status = "STOPPED"
                    self.state.last_action = "Automation stopped"
            self.add_log("Browser automation finished.", "INFO")

"""TradingView screenshots from the VPS.

One headless Chromium, logged into TradingView with session cookies pasted by Jake at the web
page this process serves (/). Every CAPTURE_EVERY_S seconds during futures hours it screenshots
each page in TV_PAGES and posts them to the agent as one set (?batch=&part=&kind=vps).
TV_LAYOUT describes what the images show; it is sent
along so the agent's vision prompt matches whatever layout Jake built.

Env: AGENT_URL, AGENT_TOKEN (required); TV_PAGES (comma-separated TradingView chart URLs;
one 4-chart layout, or one URL per chart); TV_LAYOUT (text); TV_VIEWPORT (default 2560x1440);
CAPTURE_EVERY_S (30); JPEG_QUALITY (75); UI_PASSWORD (login page; defaults to AGENT_TOKEN);
RELAUNCH_EVERY_S (10800: Chromium is relaunched this often, and at once after a renderer crash).
Data (cookies, browser profile, preview) lives on the /data volume.
Nothing is captured while the agent's dashboard has capture paused, on Saturdays, or during the
daily futures break (17:00-18:00 ET).
"""
import hmac
import html
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ET = ZoneInfo("America/New_York")
DATA = Path(os.environ.get("DATA_DIR", "/data"))
AGENT_URL = os.environ.get("AGENT_URL", "https://agent.motivationpro.tech").rstrip("/")
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")
UI_PASSWORD = os.environ.get("UI_PASSWORD") or AGENT_TOKEN
TV_PAGES = [u.strip() for u in os.environ.get("TV_PAGES", "").split(",") if u.strip()]
TV_LAYOUT = os.environ.get("TV_LAYOUT", "One TradingView window with four charts in a 2x2 grid: "
                           "top-left MNQ 5-minute, top-right MNQ 1-minute, bottom-left MES 5-minute, "
                           "bottom-right MES 1-minute.")   # Jake's "10.7 - Fractal test" layout
EVERY = int(os.environ.get("CAPTURE_EVERY_S", "30"))
QUALITY = int(os.environ.get("JPEG_QUALITY", "75"))
W, H = (int(x) for x in os.environ.get("TV_VIEWPORT", "2560x1440").lower().split("x"))
COOKIE_FILE = DATA / "cookies.json"
PREVIEW = DATA / "preview.jpg"
PROFILE = DATA / "profile"

state = {"logged_in": None, "last_capture": None, "last_post": None, "last_error": None,
         "cookies_applied": 0, "pages": len(TV_PAGES), "started": time.time()}
log = lambda *a: print(datetime.now(ET).strftime("%H:%M:%S ET"), *a, flush=True)


# ---- agent API ---------------------------------------------------------------------------------

def agent(method, path, body=None, ctype="application/json", timeout=20):
    req = urllib.request.Request(AGENT_URL + path, data=body, method=method,
                                 headers={"X-Agent-Token": AGENT_TOKEN, "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def paused() -> bool:
    try:
        return bool(json.loads(agent("GET", "/api/capture")).get("paused"))
    except Exception as e:   # agent unreachable: capture anyway, the post will fail loudly
        log("pause check failed:", e)
        return False


def report(status: str):
    try:
        agent("POST", f"/capture_status?state={status}", body=b"")
    except Exception as e:
        log("status report failed:", e)


def market_open(now=None) -> bool:
    """CME equity futures: Sunday 18:00 ET to Friday 17:00 ET, closed 17:00-18:00 ET daily."""
    now = now or datetime.now(ET)
    d, h = now.weekday(), now.hour       # Monday=0 ... Sunday=6
    if d == 5:
        return False
    if d == 6:
        return h >= 18
    if d == 4 and h >= 17:
        return False
    return h != 17


# ---- browser -----------------------------------------------------------------------------------

def load_cookies():
    try:
        return json.loads(COOKIE_FILE.read_text())
    except (OSError, ValueError):
        return None


def apply_cookies(ctx, c):
    ctx.add_cookies([
        {"name": "sessionid", "value": c["sessionid"], "domain": ".tradingview.com", "path": "/",
         "httpOnly": True, "secure": True, "sameSite": "Lax"},
        {"name": "sessionid_sign", "value": c["sessionid_sign"], "domain": ".tradingview.com",
         "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax"},
    ])
    state["cookies_applied"] = c.get("at", 0)
    log("cookies applied")


def logged_in(page) -> bool:
    try:
        u = page.evaluate("() => (window.user && window.user.username) || null")
        if u and u != "Guest":
            return True
    except Exception:
        pass
    try:   # anonymous chart pages show a Sign in entry in the header's user menu
        return page.locator('[data-name="header-user-menu-sign-in"]').count() == 0 and \
            any(c["name"] == "sessionid" for c in page.context.cookies("https://www.tradingview.com"))
    except Exception:
        return False


def open_pages(ctx):
    pages = []
    for url in TV_PAGES:
        p = ctx.new_page()
        p.goto(url, wait_until="domcontentloaded", timeout=60_000)
        p.wait_for_timeout(8_000)      # let the chart, indicators and data stream settle
        pages.append(p)
    return pages


def dismiss_banners(p):
    """TradingView's cookie-consent banner covers the bottom-left chart; accept it once."""
    try:
        b = p.get_by_role("button", name="Accept all")
        if b.count():
            b.first.click(timeout=1500)
    except Exception:
        pass


def capture_set(pages) -> int:
    batch = datetime.now(ET).strftime("%Y%m%d%H%M%S")
    sent = 0
    for i, p in enumerate(pages):
        dismiss_banners(p)
        img = p.screenshot(type="jpeg", quality=QUALITY, full_page=False)
        if i == 0:
            PREVIEW.write_bytes(img)
        q = urllib.parse.urlencode({"batch": batch, "part": i, "kind": "vps", "layout": TV_LAYOUT})
        agent("POST", f"/screenshot?{q}", body=img, ctype="image/jpeg")
        sent += 1
    return sent


RELAUNCH_S = int(os.environ.get("RELAUNCH_EVERY_S", str(3 * 3600)))   # fresh Chromium: memory back to baseline
LAUNCH_ARGS = ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu",
               "--disable-extensions", "--disable-background-networking", "--mute-audio"]


def launch(pw):
    """A fresh browser with the persistent profile, cookies applied, every TV page open."""
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE), headless=True, viewport={"width": W, "height": H},
        device_scale_factor=1, locale="en-US", timezone_id="America/New_York", args=LAUNCH_ARGS,
        user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"))
    c = load_cookies()
    if c:
        apply_cookies(ctx, c)
    pages = open_pages(ctx) if TV_PAGES else []
    return ctx, pages


def kill_leftover_chrome():
    """10/08: after a renderer crash, ctx.close() does not reap every Chromium process; over a
    day the VPS was carrying ~94 chrome processes (and <defunct> zombies) from this one
    container, which is what tripped Hostinger's CPU limitation. The container runs nothing
    else, so killing every chrome process here is safe."""
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome-linux/chrome"], check=False)
    except Exception:
        pass
    try:                                 # reap zombies if we are the parent
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except ChildProcessError:
        pass
    except Exception:
        pass


def is_crash(msg: str) -> bool:
    """A crashed renderer (OOM, usually) can never be reloaded: only a relaunch helps."""
    m = msg.lower()
    return "crashed" in m or "target closed" in m or "browser has been closed" in m \
        or "connection closed" in m


def run():
    if not TV_PAGES:
        log("TV_PAGES is empty: nothing to capture. Set it to your TradingView chart URL(s).")
    PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        while True:                                   # one iteration = one browser lifetime
            try:
                ctx, pages = launch(pw)
            except Exception as e:
                state["last_error"] = f"launch: {type(e).__name__}: {e}"[:300]
                log("launch failed:", state["last_error"])
                report("capture_failed")
                time.sleep(EVERY)
                continue
            launched = time.time()
            why = None                                # set when this browser must go
            while why is None:
                t0 = time.time()
                try:
                    c = load_cookies()
                    if c and c.get("at", 0) != state["cookies_applied"]:    # new cookies pasted
                        apply_cookies(ctx, c)
                        for p in pages:
                            p.reload(wait_until="domcontentloaded", timeout=60_000)
                        pages and pages[0].wait_for_timeout(8_000)
                    if not TV_PAGES:
                        time.sleep(EVERY); continue
                    if time.time() - launched > RELAUNCH_S:
                        why = "periodic refresh"; break
                    state["logged_in"] = logged_in(pages[0])
                    if not state["logged_in"]:
                        state["last_error"] = "not logged in to TradingView: paste fresh cookies"
                        report("logged_out")
                        pages[0].screenshot(type="jpeg", quality=QUALITY, path=str(PREVIEW))
                    elif not market_open():
                        pass
                    elif paused():
                        pass
                    else:
                        n = capture_set(pages)
                        state["last_capture"] = state["last_post"] = time.time()
                        state["last_error"] = None
                        log(f"sent {n} image(s)")
                except Exception as e:
                    state["last_error"] = f"{type(e).__name__}: {e}"[:300]
                    log("capture failed:", state["last_error"])
                    traceback.print_exc()
                    report("capture_failed")
                    if is_crash(state["last_error"]):
                        why = "crash"; break
                    try:
                        for p in pages:
                            p.reload(wait_until="domcontentloaded", timeout=60_000)
                    except Exception as e2:
                        if is_crash(str(e2)):
                            why = "crash"; break
                time.sleep(max(1.0, EVERY - (time.time() - t0)))
            log(f"relaunching Chromium ({why})")
            try:
                ctx.close()
            except Exception:
                pass
            kill_leftover_chrome()      # a crashed Chromium leaves renderer/zombie processes behind
            if why == "crash":
                time.sleep(5)


# ---- tiny web UI: paste cookies, see the preview -------------------------------------------------

PAGE = """<!doctype html><meta charset=utf-8><title>TV capture</title>
<style>body{font:15px system-ui;max-width:720px;margin:2em auto;padding:0 1em;color:#ddd;background:#111}
input{width:100%%;padding:.5em;margin:.3em 0 1em;background:#222;color:#eee;border:1px solid #444}
button{padding:.6em 1.2em}img{max-width:100%%;border:1px solid #333;margin-top:1em}code{color:#9cf}</style>
<h2>TradingView capture (VPS)</h2>
<p>%(status)s</p>
<form method=post action=/cookies>
<label>Password <input name=password type=password required></label>
<label>sessionid <input name=sessionid required></label>
<label>sessionid_sign <input name=sessionid_sign required></label>
<button>Save cookies</button></form>
<p>Get them from Chrome on a tab where you are logged in to TradingView: DevTools &rarr; Application
&rarr; Cookies &rarr; <code>https://www.tradingview.com</code>; copy the <b>Value</b> of
<code>sessionid</code> and <code>sessionid_sign</code>.</p>
<p>Pages: %(pages)s</p>
<p>Latest preview (first page):</p>%(img)s"""


class UI(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, body, ctype="text/html; charset=utf-8"):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _authed(self, pw):
        return bool(UI_PASSWORD) and hmac.compare_digest((pw or "").encode(), UI_PASSWORD.encode())

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/health":
            return self._ok(json.dumps({k: v for k, v in state.items()}).encode(), "application/json")
        if u.path == "/preview.jpg":
            if not self._authed((qs.get("password") or [""])[0]):
                self.send_response(401); self.end_headers(); return
            if not PREVIEW.exists():
                self.send_response(404); self.end_headers(); return
            return self._ok(PREVIEW.read_bytes(), "image/jpeg")
        pw = (qs.get("password") or [""])[0]
        li = state["logged_in"]
        st = ("Logged in: <b>%s</b>" % {None: "unknown yet", True: "yes", False: "NO"}[li])
        if state["last_capture"]:
            st += " · last capture %s ET" % datetime.fromtimestamp(state["last_capture"], ET).strftime("%H:%M:%S")
        if state["last_error"]:
            st += ' · <span style="color:#f88">%s</span>' % html.escape(state["last_error"])
        if not market_open():
            st += " · market closed, not capturing"
        img = ('<img src="/preview.jpg?password=%s">' % urllib.parse.quote(pw)) if self._authed(pw) else \
            "<i>(add ?password=… to the URL to see it)</i>"
        body = PAGE % {"status": st, "img": img,
                       "pages": html.escape(", ".join(TV_PAGES) or "none (set TV_PAGES)")}
        self._ok(body.encode())

    def do_POST(self):
        if self.path != "/cookies":
            self.send_response(404); self.end_headers(); return
        n = int(self.headers.get("Content-Length") or 0)
        f = urllib.parse.parse_qs(self.rfile.read(n).decode())
        g = lambda k: (f.get(k) or [""])[0].strip()
        if not self._authed(g("password")):
            self.send_response(401); self.end_headers(); self.wfile.write(b"wrong password"); return
        if not g("sessionid") or not g("sessionid_sign"):
            self.send_response(400); self.end_headers(); self.wfile.write(b"both cookies needed"); return
        DATA.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(json.dumps({"sessionid": g("sessionid"), "sessionid_sign": g("sessionid_sign"),
                                           "at": time.time()}))
        COOKIE_FILE.chmod(0o600)
        self.send_response(303); self.send_header("Location", "/?password=" + urllib.parse.quote(g("password")))
        self.end_headers()


def serve():
    ThreadingHTTPServer(("0.0.0.0", 8080), UI).serve_forever()


if __name__ == "__main__":
    if not AGENT_TOKEN:
        print("AGENT_TOKEN missing", file=sys.stderr); sys.exit(1)
    threading.Thread(target=serve, daemon=True).start()
    log(f"capturing {len(TV_PAGES)} page(s) every {EVERY}s at {W}x{H}; UI on :8080")
    run()

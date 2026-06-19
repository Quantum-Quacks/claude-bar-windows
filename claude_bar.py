"""
Claude Bar for Windows
======================

A lightweight Windows system-tray app that shows Claude Code rate-limit usage
as two small horizontal battery-style bars (Session 5h on top, Weekly 7d below).

Port of the macOS menu-bar app https://github.com/Quantum-Quacks/claude-bar

It reads your existing Claude Code credentials (no login required) and calls
Anthropic's OAuth usage endpoint. Read-only: it never makes inference calls.
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

from PIL import Image, ImageDraw
import pystray

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_DIR = os.path.join(os.path.expanduser("~"), ".claude")
CREDENTIALS_PATH = os.path.join(CLAUDE_DIR, ".credentials.json")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".claude.json")
USER_AGENT = "claude-code/2.1.168"

POLL_INTERVAL = 180          # seconds between automatic polls (3 min)
MIN_FETCH_SPACING = 45       # never hit the network more often than this

# Color thresholds (utilization %)
GREEN = (52, 199, 89)        # < 70%
ORANGE = (255, 159, 10)      # 70% - 90%
RED = (255, 69, 58)          # >= 90%
GREY = (120, 120, 128)       # unknown / error
TRACK = (70, 70, 74)         # empty part of the bar
OUTLINE = (160, 160, 168)


def bar_color(pct):
    if pct is None:
        return GREY
    if pct >= 90:
        return RED
    if pct >= 70:
        return ORANGE
    return GREEN


# ---------------------------------------------------------------------------
# Credentials / account
# ---------------------------------------------------------------------------
class AuthError(Exception):
    """Raised when no usable token is available."""


def read_oauth():
    """Return the claudeAiOauth dict from ~/.claude/.credentials.json."""
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("claudeAiOauth") or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def read_account():
    """Return (email, plan) best-effort from local Claude Code config."""
    email, plan = None, None
    oauth = read_oauth()
    plan = oauth.get("subscriptionType") or oauth.get("rateLimitTier")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            acct = json.load(f).get("oauthAccount") or {}
            email = acct.get("emailAddress")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return email, plan


# ---------------------------------------------------------------------------
# Usage fetch
# ---------------------------------------------------------------------------
def parse_reset(value):
    """Parse resets_at (ISO 8601 string or epoch seconds) into a datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def effective_pct(window):
    """Return clamped utilization, or 0 if we're past the reset boundary."""
    if not window:
        return None
    resets = parse_reset(window.get("resets_at"))
    if resets and datetime.now(timezone.utc) >= resets:
        return 0.0
    pct = window.get("utilization")
    if pct is None:
        return None
    return max(0.0, min(100.0, float(pct)))


def fetch_usage():
    """Fetch usage. Returns a dict; raises AuthError on missing/expired token."""
    oauth = read_oauth()
    token = oauth.get("accessToken")
    if not token:
        raise AuthError("Sign in with Claude Code to enable")

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthError("Token expired — run claude to refresh")
        if e.code == 429:
            raise AuthError("Rate limited")
        raise AuthError("Can't reach Anthropic (%s)" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AuthError("Can't reach Anthropic")

    email, plan = read_account()
    return {
        "session": effective_pct(data.get("five_hour")),
        "weekly": effective_pct(data.get("seven_day")),
        "session_reset": parse_reset((data.get("five_hour") or {}).get("resets_at")),
        "weekly_reset": parse_reset((data.get("seven_day") or {}).get("resets_at")),
        "email": email,
        "plan": plan,
        "fetched_at": datetime.now(),
    }


# ---------------------------------------------------------------------------
# Icon rendering: two stacked horizontal battery-style bars
# ---------------------------------------------------------------------------
def render_icon(session, weekly, error=False):
    S = 64  # render large; Windows scales down crisply for the tray
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    margin_x = 6
    bar_h = 18
    gap = 8
    total = bar_h * 2 + gap
    top = (S - total) // 2
    x0, x1 = margin_x, S - margin_x - 5  # leave room for the battery nub
    nub_w = 4
    radius = 4

    def draw_bar(y, pct):
        # track
        d.rounded_rectangle([x0, y, x1, y + bar_h], radius=radius,
                            fill=TRACK, outline=OUTLINE, width=2)
        # battery nub
        nub_y0 = y + bar_h // 2 - 4
        d.rounded_rectangle([x1 + 1, nub_y0, x1 + nub_w, nub_y0 + 8],
                            radius=1, fill=OUTLINE)
        if pct is None:
            return
        inner = max(0, x1 - x0 - 4)
        fill_w = int(round(inner * (pct / 100.0)))
        if fill_w > 0:
            d.rounded_rectangle([x0 + 2, y + 2, x0 + 2 + fill_w, y + bar_h - 2],
                                radius=2, fill=bar_color(pct))

    if error:
        draw_bar(top, None)
        draw_bar(top + bar_h + gap, None)
        # small red dot to signal a problem
        d.ellipse([S - 16, 4, S - 4, 16], fill=RED)
    else:
        draw_bar(top, session)
        draw_bar(top + bar_h + gap, weekly)
    return img


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def fmt_reset(dt):
    if not dt:
        return ""
    local = dt.astimezone()
    delta = local - datetime.now(local.tzinfo)
    secs = delta.total_seconds()
    if secs <= 0:
        return ""
    if secs > 23 * 3600:
        return local.strftime("resets %a %H:%M")
    return local.strftime("resets %H:%M")


def fmt_pct(p):
    return "--" if p is None else "%d%%" % round(p)


STARTUP_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
)
STARTUP_BAT = os.path.join(STARTUP_DIR, "ClaudeBar.bat")


class ClaudeBarApp:
    def __init__(self):
        self.usage = None
        self.error = None
        self.last_fetch = 0.0
        self.lock = threading.Lock()
        self.icon = pystray.Icon(
            "claude-bar",
            icon=render_icon(None, None, error=True),
            title="Claude Bar",
            menu=self._build_menu(),
        )

    # -- menu ----------------------------------------------------------------
    def _build_menu(self):
        def account_text(_):
            if self.usage:
                email = self.usage.get("email") or "Signed in"
                plan = self.usage.get("plan")
                return "%s · %s" % (email, plan.title()) if plan else email
            return "Claude Bar"

        def session_text(_):
            if not self.usage:
                return "Session (5h): --"
            r = fmt_reset(self.usage.get("session_reset"))
            return "Session (5h): %s%s" % (
                fmt_pct(self.usage["session"]), ("   " + r) if r else "")

        def weekly_text(_):
            if not self.usage:
                return "Weekly (7d): --"
            r = fmt_reset(self.usage.get("weekly_reset"))
            return "Weekly (7d): %s%s" % (
                fmt_pct(self.usage["weekly"]), ("   " + r) if r else "")

        def status_text(_):
            if self.error:
                return self.error
            if self.usage:
                return "Updated " + self.usage["fetched_at"].strftime("%H:%M:%S")
            return "Loading…"

        return pystray.Menu(
            pystray.MenuItem(account_text, None, enabled=False),
            pystray.MenuItem(session_text, None, enabled=False),
            pystray.MenuItem(weekly_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem("Refresh Now", self._on_refresh),
            pystray.MenuItem(
                "Start at Login",
                self._toggle_startup,
                checked=lambda _: os.path.exists(STARTUP_BAT),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Claude Bar", self._on_quit),
        )

    # -- actions -------------------------------------------------------------
    def _on_refresh(self, icon, item):
        threading.Thread(target=self.refresh, args=(True,), daemon=True).start()

    def _on_quit(self, icon, item):
        icon.stop()

    def _toggle_startup(self, icon, item):
        if os.path.exists(STARTUP_BAT):
            try:
                os.remove(STARTUP_BAT)
            except OSError:
                pass
        else:
            pyw = sys.executable.replace("python.exe", "pythonw.exe")
            script = os.path.abspath(__file__)
            os.makedirs(STARTUP_DIR, exist_ok=True)
            with open(STARTUP_BAT, "w", encoding="utf-8") as f:
                f.write('@echo off\nstart "" "%s" "%s"\n' % (pyw, script))

    # -- fetch / render ------------------------------------------------------
    def refresh(self, force=False):
        with self.lock:
            now = time.monotonic()
            if not force and (now - self.last_fetch) < MIN_FETCH_SPACING:
                return
            self.last_fetch = now
        try:
            self.usage = fetch_usage()
            self.error = None
        except AuthError as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001 - never let the tray die
            self.error = "Error: %s" % e
        self._update_icon()

    def _update_icon(self):
        if self.usage:
            self.icon.icon = render_icon(self.usage["session"], self.usage["weekly"])
            s, w = fmt_pct(self.usage["session"]), fmt_pct(self.usage["weekly"])
            self.icon.title = "Claude Bar — Session %s · Weekly %s" % (s, w)
        else:
            self.icon.icon = render_icon(None, None, error=True)
            self.icon.title = "Claude Bar — %s" % (self.error or "Loading")
        self.icon.update_menu()

    def _poll_loop(self):
        self.refresh(force=True)
        while True:
            time.sleep(POLL_INTERVAL)
            self.refresh(force=True)

    def run(self):
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.icon.run()


def main():
    if "--preview" in sys.argv:
        render_icon(18, 31).resize((256, 256), Image.NEAREST).show()
        return
    ClaudeBarApp().run()


if __name__ == "__main__":
    main()

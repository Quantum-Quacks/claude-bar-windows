# Claude Bar for Windows

A lightweight Windows **system-tray** app that shows your Claude Code rate-limit
usage as two small battery-style bars — **Session (5h)** on top, **Weekly (7d)**
below.

This is a Windows port of **[tulinmola](https://github.com/tulinmola)'s** macOS
menu-bar app [tulinmola/claude-bar](https://github.com/tulinmola/claude-bar)
(via the [Quantum-Quacks](https://github.com/Quantum-Quacks/claude-bar) fork).
All credit for the original idea and design goes to tulinmola.

![Claude Bar in the Windows system tray](docs/tray.png)

It reuses the credentials Claude Code already stored on your machine, so there's
no separate login. It's **read-only** and never makes inference calls.

## What it shows

- **Tray icon:** two horizontal battery bars, color-coded
  green `< 70%` → orange `70–90%` → red `≥ 90%`.
- **Menu (left/right-click the tray icon):**
  - Account: `email · Plan`
  - `Session (5h): NN%   resets HH:MM`
  - `Weekly (7d): NN%   resets Day HH:MM`
  - **Details** submenu: plan, full reset timestamps, per-model weekly usage, extra-usage credits, spend.
  - **Notifications** submenu (all configurable, see below)
  - Last-updated time (or an error message)
  - **Refresh Now**
  - **Start at Login** (toggle — adds/removes a Startup shortcut)
  - **Quit Claude Bar**

## Notifications

Native Windows toast notifications, configured from the **Notifications** submenu.
There are two independent kinds, each with its own on/off toggle:

- **Running-low alerts** — fire when usage climbs past a threshold, so you know
  you're about to run out. Configurable per window (Session / Weekly at
  70 / 80 / 90 / 95 %).
- **Unused-quota reminders** — fire when a window is about to reset but you've
  barely used it ("spend it or lose it"). Configure how long before the reset to
  remind (Session 15/30/60 min, Weekly 6/12/24 h) and only remind when usage is
  still below 30 / 50 / 70 %.

Each alert fires once per crossing (no spam) and re-arms after the condition
clears or the window resets. Use **Send test notification** to verify toasts
work. Settings persist to `%USERPROFILE%\.claude-bar-windows.json`.

## How it works

- Reads your token from `%USERPROFILE%\.claude\.credentials.json`
  (`claudeAiOauth.accessToken`) and your email from `%USERPROFILE%\.claude.json`.
- Calls `GET https://api.anthropic.com/api/oauth/usage` with the OAuth headers.
- Polls every 3 minutes, with a 45-second minimum spacing between network calls.
- If the token is missing or expired it shows a hint to run `claude` to refresh.

## Install & run

Requires **Python 3.8+** (you have 3.10).

```powershell
cd windows
python -m pip install -r requirements.txt
```

Run it:

```powershell
# Background, no console window:
run.bat

# Or directly (keeps a console open):
python claude_bar.py
```

Preview the icon without launching the tray:

```powershell
python claude_bar.py --preview
```

## Start automatically at login

Either toggle **Start at Login** from the tray menu, or run `run.bat` once and
add a shortcut to it in your Startup folder (`shell:startup`).

## Notes / differences from the macOS version

- macOS reads the token from Keychain; on Windows Claude Code keeps it in the
  plaintext `.credentials.json` file, so that's what this reads.
- Token **auto-refresh** is not implemented — when the token expires, just run
  Claude Code (`claude`) once to refresh it and the app picks it up.
- The tray icon is drawn with Pillow and rendered at 64×64 so Windows scales it
  crisply down to the tray size.

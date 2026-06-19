First standalone Windows binary of Claude Bar.

## Install

1. Download **ClaudeBar.exe** below.
2. Drop it anywhere (e.g. `%LOCALAPPDATA%\Programs\ClaudeBar\`).
3. Double-click to launch — a battery-bar icon appears in your system tray.
4. (Optional) Click the icon → **Start at Login** to launch on boot.

No Python install required. Reuses the credentials Claude Code already stored on your machine; if you haven't signed in yet, run `claude` once.

## Features

- Two battery-style bars in the tray: **Session (5h)** and **Weekly (7d)**.
- **Details** submenu: plan, full reset times, per-model weekly usage (Opus / Sonnet), extra-usage credits, spend.
- **Notifications** submenu — two independent, configurable native-toast alerts:
  - **Running-low alerts** (default on, threshold 80 %)
  - **Unused-quota reminders** (off by default — "spend it or lose it")
- **Start at Login** toggle.
- Read-only — never makes inference calls.

Windows port of [tulinmola/claude-bar](https://github.com/tulinmola/claude-bar) (macOS).

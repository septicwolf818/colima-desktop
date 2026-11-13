# Colima Desktop

A Docker-Desktop-style management application for **Colima**. Manage Colima
profiles, containers, images and Compose stacks from a single cross-platform
GUI. Runs on **macOS** and **Linux** (Windows best-effort).

## Features

- **Profiles** — list, start, stop, restart, delete Colima profiles; edit
  CPU/memory/disk/Kubernetes options via the profile editor.
- **Containers** — list (with live CPU/memory, ports, size and a Project
  column), start, stop, remove, view logs.
- **Compose Stacks** — group containers by compose project; start/stop/take
  down a whole stack; per-stack logs with a service selector.
- **Images** — list, pull, remove (with in-use warning).
- **Logs viewers** — container and compose logs with live follow, per-service
  colouring (16-colour palette), timestamps, sort-by-timestamp, scroll-to-
  bottom-only-if-at-bottom, refresh and "load all".
- **Settings dialog** — default profile, start args, auto-start on launch,
  poll interval; changes apply via restart.
- **System tray applet** — cross-platform tray (macOS menu bar / Linux system
  tray) showing status, with quick start/stop/restart/refresh and panel
  shortcuts.
- **Top status bar** — live Colima state, runtime, aggregate CPU/RAM usage.
- **Bottom terminal** — app-level logs plus streamed command output for
  action operations.
- **Persistence** — window geometry, sidebar selection, settings.

## Tech stack

- Python 3.10+
- PySide6 (Qt6) — single cross-platform GUI toolkit for both the main window
  and the tray applet. No native Cocoa/PyObjC dependency.
- Colima CLI + `docker` / `nerdctl` for the actual container/image operations.

## Setup (with a local venv)

```bash
make setup       # creates .venv and installs dependencies
make run         # launch the app
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m colima_desk
```

## Packaging

```bash
make package        # macOS .app  -> dist/Colima Desktop.app
make package-linux  # Linux binary via a containerized PyInstaller build
```

The macOS build produces a signed-ish `.app` with the bundled icon; the Linux
build installs the required runtime libraries inside a container.

## Configuration

Start options (extra args passed to `colima start`), the default profile,
auto-start on launch and the poll interval are persisted to:

- macOS: `~/Library/Application Support/colima-desk/config.json`
- Linux: `~/.config/colima-desk/config.json`
- Windows: `%APPDATA%/colima-desk/config.json`

They can be edited from the in-app Settings dialog (Preferences) or the tray
menu.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl/Cmd + R`, `F5` | Refresh |
| `Ctrl/Cmd + ,` | Settings |
| `Ctrl/Cmd + Q` | Quit |
| `Enter` (on a table row) | Open the row's primary action (e.g. logs) |
| Double-click (table row) | Open logs / edit profile |

## Architecture (OOP)

```
colima_desk/
├── app.py                 # ColimaDeskApp controller (QObject)
├── models.py              # pure dataclasses
├── config.py              # JSON config store
├── _paths.py              # PATH augmentation (shared by both entry points)
├── engine/                # pure-Python, GUI-agnostic
│   ├── colima_engine.py   # lifecycle + profiles + config read/write
│   ├── container_service.py
│   └── image_service.py
└── gui/                   # PySide6 presentation layer
    ├── main_window.py
    ├── status_bar.py
    ├── tray.py            # QSystemTrayIcon applet
    ├── dialogs.py         # logs, profile editor, settings
    ├── fonts.py           # shared monospace font helper
    ├── resources.py       # programmatic icons
    ├── panels/            # containers / images / compose / profiles
    └── base_panel.py
colima_desk_entry.py       # PyInstaller entry point
```

The engine never imports Qt; the GUI never calls subprocess directly. All
long-running operations run on `Worker` threads and report back via signals.
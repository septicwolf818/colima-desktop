# Colima Desktop

A Docker-Desktop-style management application for **Colima**, branded for Colima.
Manage Colima profiles, containers, and images from a single cross-platform
GUI. Runs on **macOS** and **Linux**.

## Features

- **Profiles (projects)** — list, start, stop, restart, delete Colima profiles.
- **Containers** — list (with live CPU/memory, ports, and a Project column), start, stop, remove, view logs.
- **Compose Stacks** — group containers by compose project/folder; start/stop/take-down a whole stack.
- **Images** — list, pull, remove.
- **System tray applet** — cross-platform tray (macOS menu bar / Linux system
  tray) showing status, with quick start/stop and shortcuts into the main window.
- **Top status bar** — live Colima state, runtime, aggregate CPU/RAM.

## Tech stack

- Python 3.10+
- PySide6 (Qt6) — single cross-platform GUI toolkit for both the main window
  and the tray applet. No native Cocoa/PyObjC dependency.
- Colima CLI + `docker` / `nerdctl` for the actual container/image operations.

## Setup (with a local venv)

```bash
make setup       # creates .venv and installs PySide6
make run         # launch the app
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m colima_desk
```

## Packaging (optional)

The project is structured as a normal Python application and can later be
bundled as a macOS `.app` or a Linux binary (e.g. with PyInstaller):

```bash
# (future)
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller --windowed --name "Colima Desktop" colima_desk/__main__.py
```

## Configuration

Start options (extra args passed to `colima start`) and the default profile
are persisted to `~/.config/colima-desk/config.json` (macOS/Linux) and can be
edited from the in-app Settings dialog or the tray menu.

## Architecture (OOP)

```
colima_desk/
├── app.py                 # ColimaDeskApp controller (QObject)
├── models.py              # pure dataclasses
├── config.py              # JSON config store
├── engine/                # pure-Python, GUI-agnostic
│   ├── colima_engine.py   # lifecycle + profiles
│   ├── container_service.py
│   └── image_service.py
└── gui/                   # PySide6 presentation layer
    ├── main_window.py
    ├── status_bar.py
    ├── tray.py            # QSystemTrayIcon applet
    ├── async_worker.py    # Worker thread
    ├── resources.py       # programmatic icons
    └── panels/            # containers / images / profiles
```

The engine never imports Qt; the GUI never calls subprocess directly. All
long-running operations run on `Worker` threads and report back via signals.
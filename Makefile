# Colima Desktop
# Build / run helper. Uses a project-local .venv so the system Python is not
# polluted.

PY := python3
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: venv setup run install clean package package-macos package-linux

venv:
	$(PY) -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip

setup: venv
	$(PIP) install -r requirements.txt

install: setup

run: setup
	$(PYTHON) -m colima_desk

# ── packaging ─────────────────────────────────────────────────────────────
# Install packaging deps (pyinstaller) into the venv.
package-deps: setup
	$(PIP) install pyinstaller

# Build a native bundle for the current platform (macOS .app here).
package: package-deps
	$(PYTHON) -m PyInstaller --windowed --name "Colima Desktop" --noconfirm --icon colima_desk.icns colima_desk_entry.py
	@echo "Built: dist/Colima Desktop.app"

# macOS-specific alias.
package-macos: package

# Linux release built inside a container (cross-build from macOS).
package-linux:
	@command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
	docker run --rm -v "$(CURDIR):/src" -w /src python:3.12-slim bash -c " \
		apt-get update -qq && apt-get install -y -qq binutils libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libxcb-cursor0 libglib2.0-0 libgthread-2.0-0 libx11-xcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 >/dev/null 2>&1 && \
		python -m venv /tmp/venv && \
		/tmp/venv/bin/pip install --upgrade pip -q && \
		/tmp/venv/bin/pip install -r requirements.txt pyinstaller -q && \
		/tmp/venv/bin/pyinstaller --name colima-desktop --noconfirm colima_desk_entry.py && \
		echo 'Linux build complete: dist/colima-desktop' \
	"
	@echo "Linux binary: dist/colima-desktop (inside container's dist, copy out if needed)"

clean:
	rm -rf $(VENV) __pycache__ colima_desk/__pycache__ colima_desk/**/__pycache__ build dist *.spec
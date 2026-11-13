"""Entry point: `python -m colima_desk` (or `python -m colima_status_manager`).

Builds the QApplication, instantiates the controller, window and tray, and
runs the event loop. Cross-platform: macOS and Linux.
"""

from __future__ import annotations

import os
import sys

from ._paths import augment_path

augment_path()

from PySide6.QtWidgets import QApplication

from .app import ColimaDeskApp
from .gui import MainWindow, SystemTrayIcon
from .gui import resources


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(resources.app_logo())
    app.setApplicationName("Colima Desktop")
    app.setOrganizationName("colima-desk")
    app.setQuitOnLastWindowClosed(False)  # keep running in the tray
    # Force a consistent light appearance so the hardcoded light UI keeps
    # good contrast regardless of the OS dark/light setting.
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#ffffff"))
    pal.setColor(QPalette.WindowText, QColor("#1f2937"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f5f6f8"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#1f2937"))
    pal.setColor(QPalette.Text, QColor("#1f2937"))
    pal.setColor(QPalette.Button, QColor("#f3f4f6"))
    pal.setColor(QPalette.ButtonText, QColor("#1f2937"))
    pal.setColor(QPalette.BrightText, QColor("#dc2626"))
    pal.setColor(QPalette.Link, QColor("#2563eb"))
    pal.setColor(QPalette.Highlight, QColor("#228F48"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    # Unified stylesheet for consistent look across all widgets.
    app.setStyleSheet("""
        QWidget {
            font-size: 13px;
            color: #1f2937;
        }
        QMainWindow, QDialog {
            background: #ffffff;
        }
        /* Buttons */
        QPushButton {
            background: #f3f4f6;
            color: #374151;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 500;
        }
        QPushButton:hover {
            background: #e5e7eb;
            border-color: #9ca3af;
        }
        QPushButton:pressed {
            background: #d1d5db;
        }
        QPushButton:disabled {
            background: #f9fafb;
            color: #6b7280;
            border-color: #e5e7eb;
        }
        /* Colored action buttons (selected via dynamic Qt properties) */
        QPushButton[primary="true"] {
            background: #228F48;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 5px 14px;
            font-weight: bold;
        }
        QPushButton[primary="true"]:hover {
            background: #1f7f40;
        }
        QPushButton[primary="true"]:pressed {
            background: #1a6f3a;
        }
        QPushButton[primary="true"]:disabled {
            background: #e5e7eb;
            color: #9ca3af;
            border: none;
        }
        QPushButton[dangerBtn="true"] {
            background: #606060;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 5px 14px;
            font-weight: bold;
        }
        QPushButton[dangerBtn="true"]:hover {
            background: #4d4d4d;
        }
        QPushButton[dangerBtn="true"]:disabled {
            background: #e5e7eb;
            color: #9ca3af;
            border: none;
        }
        QPushButton[infoBtn="true"] {
            background: #3b82f6;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 5px 12px;
            font-weight: bold;
        }
        QPushButton[infoBtn="true"]:hover {
            background: #2563eb;
        }
        QPushButton[infoBtn="true"]:disabled {
            background: #e5e7eb;
            color: #9ca3af;
            border: none;
        }
        QPushButton[neutralBtn="true"] {
            background: #e5e7eb;
            color: #333333;
            border: none;
            border-radius: 6px;
            padding: 5px 12px;
            font-weight: bold;
            font-size: 13px;
        }
        QPushButton[neutralBtn="true"]:hover {
            background: #d1d5db;
        }
        QPushButton[neutralBtn="true"]:disabled {
            background: #f3f4f6;
            color: #9ca3af;
            border: none;
        }
        /* Sidebar navigation buttons */
        QPushButton[nav="true"] {
            padding: 10px 14px;
            min-height: 36px;
            border: none;
            border-radius: 8px;
            font-weight: 500;
            text-align: left;
            font-size: 13px;
            color: #374151;
            background: transparent;
        }
        QPushButton[nav="true"]:hover {
            background: #e5e7eb;
        }
        QPushButton[nav="true"]:pressed {
            background: #d1d5db;
        }
        QPushButton[nav="true"]:checked {
            background: #228F48;
            color: #ffffff;
        }
        QPushButton[nav="true"]:checked:hover {
            background: #1f7f40;
        }
        QPushButton[danger="true"] {
            padding: 10px 14px;
            min-height: 36px;
            border: none;
            border-radius: 8px;
            font-weight: 500;
            text-align: left;
            font-size: 13px;
            color: #dc2626;
            background: transparent;
        }
        QPushButton[danger="true"]:hover {
            background: #fef2f2;
            color: #b91c1c;
        }
        /* Flat utility buttons (console clear, etc.) */
        QPushButton[flatButton="true"] {
            border: none;
            background: transparent;
            color: #6b7280;
            font-size: 11px;
            padding: 2px 8px;
        }
        QPushButton[flatButton="true"]:hover {
            background: #e5e7eb;
            color: #374151;
        }
        /* Checkboxes — make the indicator clearly visible */
        QCheckBox {
            spacing: 8px;
            color: #1f2937;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #9ca3af;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border-color: #228F48;
        }
        QCheckBox::indicator:checked {
            background: #228F48;
            border-color: #228F48;
        }
        /* Inputs */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 5px 8px;
            color: #1f2937;
            selection-background-color: #228F48;
            selection-color: #ffffff;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border-color: #228F48;
            outline: none;
        }
        QLineEdit:read-only {
            background: #f9fafb;
            color: #6b7280;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            selection-background-color: #228F48;
            selection-color: #ffffff;
            padding: 4px;
        }
        /* Tables */
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f9fafb;
            gridline-color: transparent;
            border: none;
        }
        QTableWidget::item {
            padding: 6px 8px;
            border: none;
        }
        QTableWidget::item:selected {
            background: #dcfce7;
            color: #166534;
        }
        QTableWidget::item:selected:focus {
            background: #bbf7d0;
            color: #14532d;
        }
        QTableWidget:focus {
            border: none;
            outline: none;
        }
        QHeaderView::section {
            background: #f3f4f6;
            color: #374151;
            font-weight: 600;
            font-size: 12px;
            padding: 8px 8px;
            border: none;
            border-bottom: 2px solid #e5e7eb;
            border-right: 1px solid #e5e7eb;
        }
        QHeaderView::section:last {
            border-right: none;
        }
        /* Scrollbars */
        QScrollBar:vertical {
            background: #f3f4f6;
            width: 10px;
            border-radius: 5px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #9ca3af;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #6b7280;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QScrollBar:horizontal {
            background: #f3f4f6;
            height: 10px;
            border-radius: 5px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background: #9ca3af;
            border-radius: 5px;
            min-width: 30px;
        }
        /* Menus */
        QMenu {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 6px;
        }
        QMenu::item {
            padding: 6px 24px 6px 12px;
            border-radius: 4px;
            color: #374151;
        }
        QMenu::item:selected {
            background: #f0fdf4;
            color: #166534;
        }
        QMenu::item:disabled {
            color: #9ca3af;
            background: transparent;
        }
        QMenu::separator {
            height: 1px;
            background: #e5e7eb;
            margin: 4px 8px;
        }
        /* Labels */
        QLabel {
            color: #1f2937;
            background: transparent;
        }
        QLabel[emptyTitle="true"] {
            color: #6b7280;
            font-size: 16px;
            font-weight: 600;
        }
        QLabel[emptyHint="true"] {
            color: #9ca3af;
            font-size: 12px;
        }
        /* Indeterminate operation progress bar */
        QProgressBar {
            border: none;
            background: transparent;
            height: 4px;
            margin: 0px;
        }
        QProgressBar::chunk {
            background: #f59e0b;
            border-radius: 2px;
        }
        /* Dialogs */
        QDialog {
            background: #ffffff;
        }
        /* Group boxes / frames */
        QFrame {
            border: none;
        }
        /* Tooltips */
        QToolTip {
            background: #ffffff;
            color: #1f2937;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }
    """)

    controller = ColimaDeskApp()

    window = MainWindow(controller)
    controller.attach_window(window)

    tray = SystemTrayIcon(controller)
    controller.attach_tray(tray)

    # Show the main window on startup (also keep tray available).
    window.show()
    tray.show()

    # Initial state + data load (stream command output to the terminal).
    controller.log("\x1b[36mColima Desktop ready.\x1b[0m")
    controller.refresh_all()

    # Poll state + stats periodically.
    from PySide6.QtCore import QTimer
    state_timer = QTimer()
    state_timer.timeout.connect(controller.refresh_state)
    state_timer.start(max(1000, int(controller.config.poll_interval * 1000)))
    stats_timer = QTimer()
    stats_timer.timeout.connect(controller.refresh_container_stats)
    stats_timer.start(3000)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
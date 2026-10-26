"""Wave Studio theme — tokens ported from design/mockup.html.
Very dark grey surfaces, blue accent, rounded, minimal, modern."""
from __future__ import annotations

# --- palette --------------------------------------------------------------
BG0 = "#0b0c0f"           # deepest (meters, LCD wells)
BG = "#101216"            # app background
SURFACE = "#15171d"       # cards / panels
SURFACE_2 = "#1a1e25"     # inputs / raised
SURFACE_3 = "#212633"     # hover
BORDER = "#262a33"
BORDER_2 = "#30353f"
BORDER_SOFT = "#1e222a"
WELL = "#05070c"          # LCD
TEXT = "#e3e7f0"
TEXT_DIM = "#8b93a5"
TEXT_DIMMER = "#5c6373"
ACCENT = "#4d8dff"
ACCENT_HI = "#8fb6ff"
ACCENT_DEEP = "#2f66e0"
ACCENT_BORDER = "#2a52b8"
ACCENT_TINT = "rgba(77, 141, 255, 0.055)"
DANGER = "#ef5350"
RED = "#ef4444"

STYLESHEET = f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ background: {BG}; color: {TEXT};
         font-family: "Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial;
         font-size: 12px; }}
QDockWidget {{ color: {TEXT_DIM}; font-weight: 600; }}
QDockWidget::title {{ background: #0e1014; padding: 10px 14px;
                     border-bottom: 1px solid {BORDER_SOFT}; }}
QDockWidget > QWidget {{ background: #0e1014; }}

QToolBar {{ background: {BG}; border: none; border-bottom: 1px solid {BORDER_SOFT};
           spacing: 8px; padding: 7px 12px; }}

QMenuBar {{ background: {BG}; border-bottom: 1px solid {BORDER_SOFT}; }}
QMenuBar::item {{ padding: 6px 10px; border-radius: 6px;
                 background: transparent; color: {TEXT_DIM}; font-size: 12px; }}
QMenuBar::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 9px;
        padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT_DEEP}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 5px 8px; }}
QMenu::section {{ color: {TEXT_DIMMER}; padding: 4px 12px 2px; font-size: 10px;
                 font-weight: 700; text-transform: uppercase; }}

QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; color: {TEXT};
              border-radius: 8px; padding: 5px 14px; }}
QPushButton:hover {{ background: {SURFACE_3}; border-color: {BORDER_2}; }}
QPushButton:pressed {{ background: #151920; }}
QPushButton:checked {{ background: {ACCENT_DEEP}; border-color: {ACCENT_DEEP};
                      color: white; }}
QPushButton:disabled {{ color: #565c6b; background: #16181d; }}
QPushButton[accent="true"] {{ background: {ACCENT_DEEP}; color: white;
                             border: 1px solid {ACCENT_DEEP}; font-weight: 600; }}
QPushButton[accent="true"]:hover {{ background: {ACCENT}; }}
QPushButton[ghost="true"] {{ background: transparent; border: 1px solid transparent;
                            color: {TEXT_DIM}; }}
QPushButton[ghost="true"]:hover {{ background: {SURFACE_3}; color: {TEXT}; }}

QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 9px; selection-background-color: {ACCENT_DEEP}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border-color: {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px; border: none; background: transparent; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {TEXT_DIM};
    margin-right: 8px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 4px; selection-background-color: {ACCENT_DEEP};
    selection-color: white; }}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabWidget::tab-bar {{ left: 12px; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 9px 14px;
               font-weight: 600; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QScrollBar:horizontal {{ height: 8px; background: transparent; margin: 2px 8px; }}
QScrollBar:vertical {{ width: 8px; background: transparent; margin: 8px 2px; }}
QScrollBar::handle {{ background: #2c3140; border-radius: 4px;
                     min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: #3a4150; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollArea {{ border: none; background: transparent; }}

QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_2};
    border-radius: 2px; border: none; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; background: #eef2ff; border: none; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QSlider::groove:vertical {{ width: 4px; background: {SURFACE_2};
    border-radius: 2px; border: none; }}
QSlider::add-page:vertical {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:vertical {{ width: 16px; height: 16px; margin: 0 -6px;
    border-radius: 8px; background: #eef2ff; border: none; }}
QSlider::handle:vertical:hover {{ background: white; }}

QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER};
           border-radius: 7px; padding: 6px 9px; }}
QLabel#logo {{ color: {TEXT}; font-size: 15px; font-weight: 800; }}
QLabel#logoAccent {{ color: {ACCENT}; font-size: 15px; font-weight: 800; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#dimmer {{ color: {TEXT_DIMMER}; font-size: 11px; }}
QLabel#lcd {{ background: {WELL}; color: {ACCENT_HI};
             border: 1px solid #1c2230; border-radius: 10px;
             padding: 7px 14px; font-size: 15px; font-weight: 600;
             font-family: "SF Mono", "Consolas", "DejaVu Sans Mono", monospace; }}
QLabel#section {{ color: {TEXT_DIMMER}; font-weight: 700; font-size: 10px;
                 padding: 0 4px; letter-spacing: 0; }}
QStatusBar {{ background: {BG}; border-top: 1px solid {BORDER_SOFT};
             color: {TEXT_DIMMER}; font-size: 11px; }}
QStatusBar::item {{ border: none; }}
"""


def apply_theme(app):
    """Global stylesheet + dark palette for natively-painted widgets."""
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_3))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_DEEP))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DIMMER))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)

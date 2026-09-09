def get_md3_stylesheet(arrow_up_path: str, arrow_down_path: str) -> str:
    return f"""
QMainWindow {{
    background-color: #0b111e;
}}

QWidget {{
    color: #f1f5f9;
    font-family: 'Segoe UI Variable Display', 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 13px;
}}

QLabel {{
    background-color: transparent;
    color: #f1f5f9;
}}

QFrame#welcomeCard {{
    background-color: #131b2e;
    border: 1px solid #23314f;
    border-radius: 16px;
}}

QFrame#chaptersPanel {{
    background-color: #131b2e;
    border: 1px solid #23314f;
    border-radius: 12px;
}}

QLineEdit, QTextEdit {{
    background-color: #1a253c;
    border: 1.5px solid #2a3b5c;
    color: #f8fafc;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #0891b2;
}}
QLineEdit:hover, QTextEdit:hover {{
    border: 1.5px solid #3d517a;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1.5px solid #06b6d4;
    background-color: #162033;
}}

QPushButton {{
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #2a3b5c;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: #2a3b5c;
    border-color: #3d517a;
}}
QPushButton:pressed {{
    background-color: #162033;
}}

QScrollBar:vertical {{
    border: none;
    background: #0b111e;
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #23314f;
    min-height: 25px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #06b6d4;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}

QTableWidget {{
    background-color: #131b2e;
    color: #f8fafc;
    gridline-color: #1c273e;
    font-size: 13px;
    border: 1px solid #23314f;
    border-radius: 12px;
    selection-background-color: #193153;
    selection-color: #ffffff;
    outline: none;
}}
QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #182338;
}}
QTableWidget::item:selected {{
    background-color: #193153;
}}
QTableWidget::item:hover {{
    background-color: #17223b;
}}

QHeaderView::section {{
    background-color: #0e1626;
    color: #38bdf8;
    font-weight: 700;
    font-size: 11px;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #06b6d4;
    border-right: 1px solid #1a253c;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: #23314f;
    border-top-right-radius: 5px;
    border-bottom: 1px solid #1a253c;
}}
QSpinBox::up-button:hover {{
    background-color: #0891b2;
}}
QSpinBox::up-arrow {{
    image: url("{arrow_up_path}");
    width: 10px;
    height: 10px;
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: #23314f;
    border-bottom-right-radius: 5px;
}}
QSpinBox::down-button:hover {{
    background-color: #0891b2;
}}
QSpinBox::down-arrow {{
    image: url("{arrow_down_path}");
    width: 10px;
    height: 10px;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: #1c263d;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: #06b6d4;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid #06b6d4;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: #22d3ee;
    border: 2px solid #ffffff;
}}

QProgressBar {{
    border: 1px solid #23314f;
    border-radius: 6px;
    text-align: center;
    background-color: #0b111e;
    color: #94a3b8;
    font-size: 11px;
    font-weight: 700;
}}
QProgressBar::chunk {{
    background-color: #06b6d4;
    border-radius: 5px;
}}
"""

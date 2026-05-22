"""
View layer — Standalone Manager tab (Tab 2).
Pure UI — no business logic.
Paths in the metadata display are clickable via setOpenExternalLinks.
"""
from ..qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QTextBrowser,
)


class ManagerTab(QWidget):
    """Tab 2: Standalone Manager — list of registered builds with metadata display."""

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # --- Left panel: build list ---
        left_panel = QVBoxLayout()
        left_panel.setSpacing(8)
        left_panel.addWidget(QLabel("<b>Registered Standalone Builds:</b>"))

        self.standalone_list = QListWidget()
        self.standalone_list.setStyleSheet(
            "QListWidget { background-color: #1E1E1E; border: 1px solid #333; "
            "border-radius: 4px; padding: 5px; } "
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #2A2A2A; } "
            "QListWidget::item:selected { background-color: #673AB7; color: white; } "
            "QListWidget::item:hover { background-color: #2A2A2A; }"
        )
        left_panel.addWidget(self.standalone_list)

        btn_row = QHBoxLayout()
        self.btn_refresh_list = QPushButton("Refresh List")
        self.btn_refresh_list.setStyleSheet(
            "background-color: #1565C0; color: white; height: 32px;"
        )
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.setStyleSheet(
            "background-color: #2E7D32; color: white; height: 32px;"
        )
        btn_row.addWidget(self.btn_refresh_list)
        btn_row.addWidget(self.btn_open_folder)
        left_panel.addLayout(btn_row)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMinimumWidth(300)
        left_widget.setMaximumWidth(400)

        # --- Right panel: metadata display ---
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        right_panel.addWidget(QLabel("<b>Build Information:</b>"))

        self.metadata_display = QTextBrowser()
        self.metadata_display.setReadOnly(True)
        self.metadata_display.setOpenExternalLinks(True)
        self.metadata_display.setStyleSheet(
            "QTextBrowser { background-color: #121212; color: #E0E0E0; "
            "font-family: 'Consolas', monospace; border: 1px solid #333; "
            "border-radius: 4px; padding: 10px; }"
        )
        self.metadata_display.setPlaceholderText("Select a standalone build to view details...")
        right_panel.addWidget(self.metadata_display)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)

        layout.addWidget(left_widget)
        layout.addWidget(right_widget)

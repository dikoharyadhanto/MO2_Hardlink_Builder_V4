"""
ARCH-01: View layer — Tab 1 configuration panel (no business logic).
Contains only Qt widget creation and layout code.
"""
from pathlib import Path

from ..qt_compat import (
    QT_NAME, Qt, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QComboBox, QProgressBar,
    QTextEdit, QDragEnterEvent, QDropEvent,
)


class DropLineEdit(QLineEdit):
    """QLineEdit that accepts folder drag-and-drop with path safety validation."""

    def __init__(self, parent=None, organizer=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.organizer = organizer

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = Path(urls[0].toLocalFile())
                if path.is_dir():
                    if self.organizer and not self._is_path_safe(path):
                        event.ignore()
                        return
                    self.setText(str(path))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _is_path_safe(self, selected_path: Path) -> bool:
        try:
            selected_path = selected_path.resolve()
            game_path = Path(self.organizer.managedGame().gameDirectory().absolutePath()).resolve()
            mo2_path = Path(self.organizer.basePath()).resolve()
            steam_path = (
                game_path.parent.parent
                if "steamapps" in str(game_path).lower()
                else None
            )
            forbidden_paths = [game_path, mo2_path]
            if steam_path:
                forbidden_paths.append(steam_path)
            for forbidden in forbidden_paths:
                if selected_path == forbidden:
                    return False
                try:
                    selected_path.relative_to(forbidden)
                    return False
                except ValueError:
                    pass
                try:
                    forbidden.relative_to(selected_path)
                    return False
                except ValueError:
                    pass
            return True
        except Exception:
            return True


class BuilderTab(QWidget):
    """
    Tab 1: Builder configuration + progress + log.
    Pure UI — no signal connections or business logic here.
    """

    def __init__(self, organizer=None):
        super().__init__()
        self._build_ui(organizer)

    def _build_ui(self, organizer):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Profile Selection ---
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("<b>MO2 Profile:</b>"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(200)
        profile_row.addWidget(self.profile_box)
        self.btn_browse_prof = QPushButton("Browse...")
        profile_row.addWidget(self.btn_browse_prof)
        layout.addLayout(profile_row)

        # Game + path info labels
        self.lbl_game = QLabel()
        self.lbl_game.setStyleSheet("font-size: 13px; color: #81C784;")
        layout.addWidget(self.lbl_game)

        self.lbl_prof_path = QLabel()
        self.lbl_prof_path.setStyleSheet("color: #AAA; font-size: 11px;")
        layout.addWidget(self.lbl_prof_path)

        self.lbl_prof_status = QLabel()
        self.lbl_prof_status.setWordWrap(True)
        self.lbl_prof_status.setStyleSheet("font-size: 11px; padding: 5px; border-radius: 4px;")
        self.lbl_prof_status.hide()
        layout.addWidget(self.lbl_prof_status)

        # --- Destination ---
        layout.addWidget(QLabel("<b>Standalone Destination Folder:</b>"))
        dest_row = QHBoxLayout()
        self.dest_edit = DropLineEdit(organizer=organizer)
        self.dest_edit.setPlaceholderText("Select or Drag & Drop Folder here...")
        dest_row.addWidget(self.dest_edit)
        self.btn_browse_dest = QPushButton("Browse")
        self.btn_browse_dest.setStyleSheet("height: 30px; padding: 5px;")
        dest_row.addWidget(self.btn_browse_dest)
        layout.addLayout(dest_row)

        # UX-01: Cross-drive warning label
        self.drive_warning = QLabel()
        self.drive_warning.setWordWrap(True)
        self.drive_warning.setStyleSheet(
            "font-size: 11px; color: #FFB74D; "
            "border: 1px solid #FFB74D; padding: 5px; border-radius: 4px;"
        )
        self.drive_warning.hide()
        layout.addWidget(self.drive_warning)

        # --- Options row ---
        options_row = QHBoxLayout()
        self.cb_hardlinks = QCheckBox("Use Hardlinks for Vanilla Files (Recommended)")
        self.cb_hardlinks.setChecked(True)
        options_row.addWidget(self.cb_hardlinks)
        options_row.addStretch()

        # FEAT-06: Clean Standalone button (red)
        self.btn_clean_standalone = QPushButton("Clean Standalone")
        self.btn_clean_standalone.setStyleSheet(
            "background-color: #D32F2F; color: white; "
            "font-weight: bold; padding: 4px 12px; border-radius: 4px;"
        )
        options_row.addWidget(self.btn_clean_standalone)
        layout.addLayout(options_row)

        # Hidden mode radio buttons (stealth mode is enforced; kept for internal compatibility)
        from ..qt_compat import QWidget as _W
        from ..qt_compat import QCheckBox as _CB
        # We don't add these to layout but they exist so controller logic can read .isChecked()
        from ..qt_compat import Qt as _Qt
        # Dummy attributes for compat
        class _FakeRadio:
            def isChecked(self): return False
        class _StealthRadio:
            def isChecked(self): return True
        self.rb_mode_isolated = _FakeRadio()
        self.rb_mode_docs = _FakeRadio()
        self.rb_mode_stealth = _StealthRadio()

        # --- Progress bars ---
        bar_style = (
            "QProgressBar { border: 1px solid #333; border-radius: 5px; text-align: center; "
            "height: 12px; background: #222; font-size: 10px; } "
            "QProgressBar::chunk { background-color: #388E3C; }"
        )

        self.lbl_clean = QLabel("Stage 1: Cleanup")
        self.bar_clean = QProgressBar()
        self.bar_clean.setStyleSheet(bar_style)
        layout.addWidget(self.lbl_clean)
        layout.addWidget(self.bar_clean)

        self.lbl_scan = QLabel("Stage 2: Scanning")
        self.bar_scan = QProgressBar()
        self.bar_scan.setStyleSheet(bar_style)
        layout.addWidget(self.lbl_scan)
        layout.addWidget(self.bar_scan)

        self.lbl_link = QLabel("Stage 3: Deployment")
        self.bar_link = QProgressBar()
        self.bar_link.setStyleSheet(bar_style)
        layout.addWidget(self.lbl_link)
        layout.addWidget(self.bar_link)

        self.lbl_verify = QLabel("Stage 4: Verification")
        self.bar_verify = QProgressBar()
        self.bar_verify.setStyleSheet(bar_style)
        layout.addWidget(self.lbl_verify)
        layout.addWidget(self.bar_verify)

        # --- Log area ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet(
            "background-color: #121212; color: #E0E0E0; "
            "font-family: 'Consolas', monospace; border: 1px solid #333;"
        )
        layout.addWidget(self.log_area)

        # --- Build button ---
        self.btn_build = QPushButton("BUILD STANDALONE")
        self.btn_build.setStyleSheet(
            "QPushButton { background-color: #388E3C; color: white; font-weight: bold; "
            "height: 50px; font-size: 16px; border-radius: 5px; } "
            "QPushButton:hover { background-color: #43A047; } "
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        layout.addWidget(self.btn_build)

        # TASK-A04: Show Report button (Standalone Manager Tab row)
        report_row = QHBoxLayout()
        self.btn_show_report = QPushButton("Show Build Report")
        self.btn_show_report.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "padding: 6px 14px; border-radius: 4px; font-size: 13px; } "
            "QPushButton:hover { background-color: #1976D2; } "
            "QPushButton:disabled { background-color: #333; color: #666; }"
        )
        self.btn_show_report.setEnabled(False)  # Enabled after a successful build
        report_row.addWidget(self.btn_show_report)
        report_row.addStretch()

        # TASK-A04: "Don't show again" checkbox for post-build prompt
        self.cb_show_report_prompt = QCheckBox("Prompt to view report after build")
        self.cb_show_report_prompt.setChecked(True)
        self.cb_show_report_prompt.setStyleSheet("font-size: 12px; color: #AAA;")
        report_row.addWidget(self.cb_show_report_prompt)
        layout.addLayout(report_row)

        # UX-03: Qt framework + version footer
        footer_row = QHBoxLayout()
        self.lbl_footer = QLabel(
            f"<small>Framework: {QT_NAME} | MO2 Hardlink Builder V4b</small>"
        )
        self.lbl_footer.setStyleSheet("color: #777;")
        footer_row.addStretch()
        footer_row.addWidget(self.lbl_footer)
        layout.addLayout(footer_row)

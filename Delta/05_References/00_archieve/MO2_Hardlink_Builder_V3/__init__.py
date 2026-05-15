import os
import sys
from pathlib import Path

# Fix python path to allow imports from internal Scripts directory
BASE_DIR = Path(__file__).parent
SCRIPTS_DIR = BASE_DIR / "Scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

import mobase

# Framework Detection
try:
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QIcon
    QT_NAME = "PySide6"
except ImportError:
    try:
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QIcon
        QT_NAME = "PyQt6"
    except ImportError:
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtGui import QIcon
        QT_NAME = "PyQt5"

class HardlinkBuilderPlugin(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self.__organizer = None
        self.__parent_widget = None

    def init(self, organizer: mobase.IOrganizer):
        self.__organizer = organizer
        return True

    def name(self):
        return "MO2 Hardlink Builder"

    def author(self):
        return "Antigravity & User"

    def description(self):
        return "Creates a standalone, portable Skyrim installation using Hardlinks."

    def version(self):
        return mobase.VersionInfo(3, 2, 0, mobase.ReleaseType.FINAL)

    def isActive(self) -> bool:
        return True

    def requirements(self) -> list:
        return []

    def localizedName(self) -> str:
        return self.name()

    def settings(self):
        return []

    def display(self):
        try:
            from .plugin_ui import HardlinkBuilderDialog
            dialog = HardlinkBuilderDialog(self.__organizer)
            # Use exec() but check for fallback in older versions if necessary
            if hasattr(dialog, 'exec'):
                dialog.exec()
            else:
                dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self.__parent_widget, "Hardlink Builder Error", f"Failed to launch UI: {str(e)}")

    def setParentWidget(self, widget):
        self.__parent_widget = widget

    def displayName(self):
        return self.name()

    def tooltip(self):
        return "Build a standalone Skyrim from this MO2 profile."

    def icon(self):
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return QIcon()

    def iconName(self):
        return "icon.png"

def createPlugin() -> mobase.IPlugin:
    return HardlinkBuilderPlugin()

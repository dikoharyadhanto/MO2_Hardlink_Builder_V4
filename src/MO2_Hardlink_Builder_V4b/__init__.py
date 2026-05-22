import mobase
from pathlib import Path
from .qt_compat import QMessageBox, QIcon, QT_NAME


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
        return "Vladmir74"

    def description(self):
        return "Creates a standalone, portable game installation using Hardlinks."

    def version(self):
        return mobase.VersionInfo(4, 0, 0, mobase.ReleaseType.FINAL)

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
            from .controller.deployment_controller import HardlinkBuilderDialog
            dialog = HardlinkBuilderDialog(self.__organizer)
            if hasattr(dialog, "exec"):
                dialog.exec()
            else:
                dialog.exec_()
        except Exception as e:
            QMessageBox.critical(
                self.__parent_widget,
                "Hardlink Builder Error",
                f"Failed to launch UI: {str(e)}",
            )

    def setParentWidget(self, widget):
        self.__parent_widget = widget

    def displayName(self):
        return self.name()

    def tooltip(self):
        return "Build a standalone game installation from this MO2 profile."

    def icon(self):
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return QIcon()

    def iconName(self):
        return "icon.png"


def createPlugin() -> mobase.IPlugin:
    return HardlinkBuilderPlugin()

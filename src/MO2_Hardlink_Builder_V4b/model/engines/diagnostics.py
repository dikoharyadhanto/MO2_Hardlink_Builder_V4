"""
FEAT-01: EnvironmentSensor — pre-flight environment checks before deployment.
Detects: OneDrive sync conflict, Windows Defender CFA blocking target, PID locks on game files.
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ConflictReport:
    conflict_type: str      # "ONEDRIVE" | "DEFENDER_CFA" | "PID_LOCK"
    description: str
    affected_path: str
    retry_suggestion: str


@dataclass
class SensorResult:
    conflicts: List[ConflictReport] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


class EnvironmentSensor:
    """
    FEAT-01: Checks the deployment target for environmental blockers before deployment starts.
    Returns a SensorResult — callers must pause on any conflict and offer Retry/Abort.
    """

    def __init__(self, target_path: str, game_path: str = None):
        self.target_path = Path(target_path)
        self.game_path = Path(game_path) if game_path else None

    def run_all(self) -> SensorResult:
        result = SensorResult()

        od = self._check_onedrive()
        if od:
            result.conflicts.append(od)

        cfa = self._check_defender_cfa()
        if cfa:
            result.conflicts.append(cfa)

        if self.game_path:
            pid_conflicts = self._check_pid_locks(self.game_path)
            result.conflicts.extend(pid_conflicts)

        if result.has_conflicts:
            logger.warning(
                "Pre-flight check: %d conflict(s) detected in '%s'.",
                len(result.conflicts), self.target_path,
            )
        else:
            logger.info("Pre-flight check: no conflicts detected.")

        return result

    def _check_onedrive(self) -> ConflictReport | None:
        """Detects OneDrive sync on the target path."""
        try:
            target_str = str(self.target_path).lower()

            # Check path contains OneDrive indicator
            onedrive_markers = ["onedrive", "onedrive - "]
            if any(m in target_str for m in onedrive_markers):
                return ConflictReport(
                    conflict_type="ONEDRIVE",
                    description=(
                        "Target path is inside a OneDrive-synced folder. "
                        "OneDrive sync can interfere with hardlink creation and cause data loss."
                    ),
                    affected_path=str(self.target_path),
                    retry_suggestion=(
                        "Move the standalone destination outside of OneDrive, "
                        "or pause OneDrive sync before deploying."
                    ),
                )

            # Check if OneDrive is syncing the target via registry / status
            if os.name == "nt":
                try:
                    import winreg
                    key_path = r"Software\Microsoft\OneDrive\Accounts"
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        i = 0
                        while True:
                            try:
                                sub_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sub_name) as sub_key:
                                    try:
                                        od_path, _ = winreg.QueryValueEx(sub_key, "UserFolder")
                                        if od_path and str(self.target_path).lower().startswith(
                                            od_path.lower()
                                        ):
                                            return ConflictReport(
                                                conflict_type="ONEDRIVE",
                                                description=(
                                                    f"OneDrive account '{sub_name}' is syncing this location."
                                                ),
                                                affected_path=str(self.target_path),
                                                retry_suggestion=(
                                                    "Pause OneDrive sync or choose a non-synced destination."
                                                ),
                                            )
                                    except (FileNotFoundError, OSError):
                                        pass
                                i += 1
                            except OSError:
                                break
                except (ImportError, OSError):
                    pass

        except Exception as e:
            logger.debug("OneDrive check failed (non-fatal): %s", e)

        return None

    def _check_defender_cfa(self) -> ConflictReport | None:
        """Detects Windows Defender Controlled Folder Access blocking the target."""
        if os.name != "nt":
            return None

        try:
            import winreg
            cfa_key = (
                r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard"
                r"\Controlled Folder Access"
            )
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cfa_key) as key:
                enabled, _ = winreg.QueryValueEx(key, "EnableControlledFolderAccess")
                if enabled == 1:
                    # CFA is enabled — check if target path is in protected folders
                    protected_key = cfa_key + r"\Protected Folders"
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, protected_key) as pk:
                            idx = 0
                            while True:
                                try:
                                    val_name, val_data, _ = winreg.EnumValue(pk, idx)
                                    if str(self.target_path).lower().startswith(
                                        str(val_data).lower()
                                    ):
                                        return ConflictReport(
                                            conflict_type="DEFENDER_CFA",
                                            description=(
                                                "Windows Defender Controlled Folder Access is enabled "
                                                "and may block hardlink creation in this location."
                                            ),
                                            affected_path=str(self.target_path),
                                            retry_suggestion=(
                                                "Add the standalone destination as an allowed app in "
                                                "Windows Security > Virus & Threat Protection > "
                                                "Ransomware Protection, or choose a different destination."
                                            ),
                                        )
                                    idx += 1
                                except OSError:
                                    break
                    except (FileNotFoundError, OSError):
                        # Protected Folders key may not exist even when CFA is enabled
                        # Only report if CFA is enabled without confirmed exclusion
                        return ConflictReport(
                            conflict_type="DEFENDER_CFA",
                            description=(
                                "Windows Defender Controlled Folder Access is ENABLED. "
                                "It may block writes to the standalone destination."
                            ),
                            affected_path=str(self.target_path),
                            retry_suggestion=(
                                "Check Windows Security > Ransomware Protection "
                                "and whitelist the standalone folder if needed."
                            ),
                        )
        except (ImportError, FileNotFoundError, OSError):
            pass
        except Exception as e:
            logger.debug("Defender CFA check failed (non-fatal): %s", e)

        return None

    def _check_pid_locks(self, game_path: Path) -> list:
        """Detects PID locks on game executable files."""
        conflicts = []
        if os.name != "nt":
            return conflicts

        try:
            # Only check top-level EXEs in the game directory
            exe_files = list(game_path.glob("*.exe"))
            for exe in exe_files[:5]:  # Limit to first 5 to avoid excessive scanning
                try:
                    # Try to open the file for exclusive access
                    with open(exe, "rb"):
                        pass
                except PermissionError:
                    conflicts.append(ConflictReport(
                        conflict_type="PID_LOCK",
                        description=f"File is locked by another process: {exe.name}",
                        affected_path=str(exe),
                        retry_suggestion=(
                            f"Close the application holding {exe.name} before deploying."
                        ),
                    ))
                    logger.warning("PID lock detected on: %s", exe)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("PID lock check failed (non-fatal): %s", e)

        return conflicts

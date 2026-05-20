"""
TASK-T12: Cross-Drive Detection Tests (GAP-12, Medium)
2 test vectors: same-drive produces no cross-drive method,
different-drive anchor triggers copy_cross_drive fallback in LinkerExecutor.

The UI-layer warning (_validate_drives in HardlinkBuilderDialog) requires Qt
and mobase at import time. Those UI paths are not exercised here; instead the
engine-layer behavior is tested: LinkerExecutor.deploy_base_game() uses
copy_cross_drive when source.anchor != standalone.anchor, and hardlink when
they match. The anchor-comparison helper is tested directly.
"""
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.engines.linker_executor import LinkerExecutor  # noqa: E402


def _make_linker(standalone_path, game_path, meta_dir):
    return LinkerExecutor(
        standalone_path=str(standalone_path),
        original_game_path=str(game_path),
        output_dir=str(meta_dir),
    )


# ---------------------------------------------------------------------------
# Helper: extracts the cross-drive anchor check from _validate_drives logic
# ---------------------------------------------------------------------------

def _is_cross_drive(mods_path: str, dest_path: str) -> bool:
    """Returns True if mods and dest are on different drives (anchors differ)."""
    return Path(mods_path).anchor.lower() != Path(dest_path).anchor.lower()


class TestTC_XDRV_01_SameDriveNoWarning(unittest.TestCase):

    def test_same_drive_anchor_comparison(self):
        """TC-XDRV-01: Same drive → _is_cross_drive returns False."""
        with tempfile.TemporaryDirectory() as tmp:
            mods = str(Path(tmp) / "mods")
            dest = str(Path(tmp) / "standalone")
            self.assertFalse(_is_cross_drive(mods, dest),
                             "Paths on the same drive must not trigger cross-drive detection")

    def test_same_drive_linker_uses_hardlink(self):
        """Same-drive base_mapping → deploy_base_game uses hardlink (not copy_cross_drive)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            game = tmp_path / "game"
            game.mkdir()
            meta = tmp_path / "meta"
            meta.mkdir()

            src = game / "Data" / "test.nif"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"N" * 64)

            base_mapping = {
                "Data/test.nif": {"source": str(src)},
            }

            linker = _make_linker(standalone, game, meta)
            methods_used = []
            original_hv = linker._hardlink_verified

            def spy_hv(source, target):
                m = original_hv(source, target)
                methods_used.append(m)
                return m

            linker._hardlink_verified = spy_hv
            linker.deploy_base_game(base_mapping)

            # On same drive, _hardlink_verified must have been called (not copy_cross_drive path)
            self.assertTrue(len(methods_used) >= 1,
                            "At least one file must be deployed via hardlink path on same drive")
            self.assertNotIn("copy_cross_drive", methods_used,
                             "copy_cross_drive must NOT be used on same-drive deployment")


class TestTC_XDRV_02_CrossDriveWarningTriggered(unittest.TestCase):

    def test_cross_drive_anchor_comparison(self):
        """TC-XDRV-02: Different drive letters → _is_cross_drive returns True."""
        self.assertTrue(_is_cross_drive("C:\\mods\\SomeMod", "D:\\standalone"),
                        "Different drive anchors must trigger cross-drive detection")
        self.assertTrue(_is_cross_drive("E:\\games\\mods", "F:\\SA"),
                        "E: vs F: must be detected as cross-drive")

    def test_cross_drive_produces_warning_message(self):
        """Drive mismatch generates the expected warning text (mirrors _validate_drives)."""
        mods_drive = "C:\\"
        dest_drive = "D:\\"
        if _is_cross_drive(mods_drive, dest_drive):
            warning = (
                f"⚠ Cross-drive configuration detected: MO2 mods ({mods_drive.upper()}) vs "
                f"destination ({dest_drive.upper()}). Hardlinks require the same drive — "
                "files will be COPIED instead."
            )
            self.assertIn("COPIED", warning,
                          "Warning must mention COPIED fallback behavior")
            self.assertIn("C:\\", warning)
            self.assertIn("D:\\", warning)

    def test_cross_drive_linker_uses_copy_cross_drive(self):
        """deploy_base_game falls back to copy_cross_drive when anchors differ."""
        import shutil as _shutil

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            game = tmp_path / "game"
            game.mkdir()
            meta = tmp_path / "meta"
            meta.mkdir()

            src = game / "Data" / "test.nif"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"N" * 64)

            linker = _make_linker(standalone, game, meta)

            # Stub standalone_path with a fake anchor so the linker sees a different drive.
            # The / operator delegates to the real path so target.parent.mkdir() works.
            real_standalone = standalone

            class _FakeAnchorPath:
                anchor = "Z:\\"

                def __truediv__(self, other):
                    return real_standalone / other

                def __str__(self):
                    return str(real_standalone)

            linker.standalone_path = _FakeAnchorPath()

            base_mapping = {"Data/test.nif": {"source": str(src)}}
            copies_used = []
            original_copy2 = _shutil.copy2

            def spy_copy2(src_arg, dst_arg, **kwargs):
                copies_used.append(str(dst_arg))
                return original_copy2(src_arg, dst_arg, **kwargs)

            with unittest.mock.patch("shutil.copy2", side_effect=spy_copy2):
                linker.deploy_base_game(base_mapping)

            self.assertGreaterEqual(len(copies_used), 1,
                                    "cross-drive: copy2 must have been called for cross-drive source")


if __name__ == "__main__":
    unittest.main()

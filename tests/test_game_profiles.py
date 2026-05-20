"""
TASK-T09: Game Profile Loading Tests (GAP-09, Medium)
5 test vectors: all 9 profiles load, Skyrim SE, Morrowind, Cyberpunk, unknown game fallback.
"""
import sys
import types
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.config import GameProfile, get_profile_for_game, load_game_profiles  # noqa: E402

_EXPECTED_GAME_NAMES = {
    "Skyrim Special Edition",
    "Skyrim Anniversary Edition",
    "Fallout 4",
    "Starfield",
    "Oblivion Remastered",
    "Fallout New Vegas",
    "Morrowind",
    "Cyberpunk 2077",
    "STAR WARS Battlefront II",
}


class TestTC_PRF_01_AllNineProfilesLoad(unittest.TestCase):

    def test_all_profiles_load_without_error(self):
        """TC-PRF-01: All 9 game profiles load; no KeyError; required fields present."""
        profiles = load_game_profiles()

        self.assertEqual(len(profiles), 9,
                         f"Expected 9 profiles; got {len(profiles)}: {list(profiles.keys())}")

        for key, profile in profiles.items():
            self.assertIsInstance(profile, GameProfile,
                                  f"Profile '{key}' is not a GameProfile instance")
            self.assertTrue(len(profile.game_name) > 0,
                            f"Profile '{key}' has empty game_name")
            self.assertTrue(len(profile.docs_name) > 0,
                            f"Profile '{key}' has empty docs_name")
            self.assertTrue(len(profile.steam_appid) > 0,
                            f"Profile '{key}' has empty steam_appid")

        loaded_names = {p.game_name for p in profiles.values()}
        self.assertEqual(loaded_names, _EXPECTED_GAME_NAMES,
                         f"Game names mismatch.\nExpected: {_EXPECTED_GAME_NAMES}\n"
                         f"Got: {loaded_names}")


class TestTC_PRF_02_SkyrimSEPaths(unittest.TestCase):

    def test_skyrim_se_profile_correct(self):
        """TC-PRF-02: Skyrim Special Edition profile has expected field values."""
        profile = get_profile_for_game("Skyrim Special Edition")

        self.assertEqual(profile.docs_name, "Skyrim Special Edition")
        self.assertEqual(profile.save_path_mode, "MyGames")
        self.assertTrue(profile.uses_plugins_txt)
        self.assertTrue(profile.uses_bethesda_ini)
        self.assertEqual(profile.ini_prefix, "Skyrim")
        self.assertEqual(profile.steam_appid, "489830")


class TestTC_PRF_03_MorrowindSavePathNone(unittest.TestCase):

    def test_morrowind_save_path_mode_is_none(self):
        """TC-PRF-03: Morrowind has save_path_mode='None'; no plugin/ini injection."""
        profile = get_profile_for_game("Morrowind")

        self.assertEqual(profile.save_path_mode, "None")
        self.assertFalse(profile.uses_plugins_txt)
        self.assertFalse(profile.uses_bethesda_ini)


class TestTC_PRF_04_CyberpunkSavedGames(unittest.TestCase):

    def test_cyberpunk_2077_saved_games_mode(self):
        """TC-PRF-04: Cyberpunk 2077 uses SavedGames mode with correct custom path."""
        profile = get_profile_for_game("Cyberpunk 2077")

        self.assertEqual(profile.save_path_mode, "SavedGames")
        self.assertIn("CD Projekt Red", profile.save_path_custom)
        self.assertIn("Cyberpunk 2077", profile.save_path_custom)
        self.assertFalse(profile.uses_plugins_txt)
        self.assertFalse(profile.uses_bethesda_ini)


class TestTC_PRF_05_UnknownGameFallback(unittest.TestCase):

    def test_unknown_game_returns_generic_profile(self):
        """TC-PRF-05: Unknown game name returns a synthetic GameProfile without raising."""
        try:
            profile = get_profile_for_game("NonExistentGame2099")
        except Exception as exc:
            self.fail(f"get_profile_for_game raised {type(exc).__name__}: {exc}")

        self.assertIsInstance(profile, GameProfile)
        self.assertEqual(profile.game_name, "NonExistentGame2099")
        # Fallback must not silently return data for a different game
        self.assertNotEqual(profile.game_name, "Skyrim Special Edition")


if __name__ == "__main__":
    unittest.main()

"""
ARCH-02: Game profile abstraction.
Loads game-specific strings from game_profiles.json at runtime.
No hardcoded game names in engine files.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_PROFILES_FILE = Path(__file__).parent.parent / "game_profiles.json"


@dataclass
class GameProfile:
    game_name: str
    docs_name: str
    appdata_name: str
    ini_prefix: str
    steam_appid: str
    blacklist_files: List[str] = field(default_factory=list)
    delta_rebuild_threshold: float = 0.70
    known_loaders: List[str] = field(default_factory=list)
    protected_data_subdirs: List[str] = field(default_factory=list)
    # Universal Wrapper Control Flags (added for non-Bethesda game support)
    # save_path_mode: "MyGames" | "SavedGames" | "Documents" | "None"
    #   MyGames    → Documents\My Games\{docs_name}\Saves  (Bethesda standard)
    #   SavedGames → %USERPROFILE%\Saved Games\{save_path_custom}  (e.g. Cyberpunk)
    #   Documents  → Documents\{save_path_custom}  (e.g. Battlefront II)
    #   None       → Save sync disabled (e.g. Morrowind install-dir saves)
    save_path_mode: str = "MyGames"
    save_path_custom: str = ""           # used when save_path_mode is SavedGames or Documents
    uses_plugins_txt: bool = True        # False → skip plugins.txt / loadorder.txt injection
    uses_bethesda_ini: bool = True       # False → skip sLocalSavePath INI patching


@dataclass
class DeploymentConfig:
    standalone_path: str = ""
    profile_name: str = "Default"
    use_hardlinks: bool = True
    use_stealth: bool = True
    use_documents_mode: bool = False
    # TASK-A02: When True, disables Tier 2 (size+mtime) fast-path and forces
    # hash escalation on any inode mismatch. Prevents false-positives from spoofed mtimes.
    paranoid_mode: bool = False
    # TASK-A04: When True, shows a post-build dialog offering to open the HTML report.
    # Set to False via "Don't show again" toggle to suppress for automation users.
    show_report_prompt: bool = True


def load_game_profiles() -> dict:
    """Returns all profiles keyed by profile ID (e.g. 'skyrim_se')."""
    if not _PROFILES_FILE.exists():
        logger.error("game_profiles.json not found at: %s", _PROFILES_FILE)
        return {}
    try:
        with open(_PROFILES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        profiles = {}
        for key, data in raw.items():
            profiles[key] = GameProfile(
                game_name=data.get("game_name", key),
                docs_name=data.get("docs_name", key),
                appdata_name=data.get("appdata_name", key),
                ini_prefix=data.get("ini_prefix", key.split("_")[0].capitalize()),
                steam_appid=data.get("steam_appid", "0"),
                blacklist_files=data.get("blacklist_files", []),
                delta_rebuild_threshold=data.get("delta_rebuild_threshold", 0.70),
                known_loaders=data.get("known_loaders", []),
                protected_data_subdirs=data.get("protected_data_subdirs", []),
                save_path_mode=data.get("save_path_mode", "MyGames"),
                save_path_custom=data.get("save_path_custom", ""),
                uses_plugins_txt=data.get("uses_plugins_txt", True),
                uses_bethesda_ini=data.get("uses_bethesda_ini", True),
            )
        logger.debug("Loaded %d game profiles.", len(profiles))
        return profiles
    except Exception as e:
        logger.error("Failed to load game_profiles.json: %s", e)
        return {}


def get_profile_for_game(game_name: str) -> GameProfile:
    """
    Returns the GameProfile matching the given MO2 game name.
    Falls back to a synthetic profile using the game name itself.
    """
    profiles = load_game_profiles()

    # Direct match by game_name field
    for profile in profiles.values():
        if profile.game_name.lower() == game_name.lower():
            return profile

    # Partial match
    for profile in profiles.values():
        if game_name.lower() in profile.game_name.lower():
            return profile

    logger.warning("No profile found for game '%s' — using generic fallback.", game_name)
    stem = game_name.split()[0]
    return GameProfile(
        game_name=game_name,
        docs_name=game_name,
        appdata_name=game_name,
        ini_prefix=stem,
        steam_appid="0",
        save_path_mode="MyGames",
        uses_plugins_txt=True,
        uses_bethesda_ini=True,
    )

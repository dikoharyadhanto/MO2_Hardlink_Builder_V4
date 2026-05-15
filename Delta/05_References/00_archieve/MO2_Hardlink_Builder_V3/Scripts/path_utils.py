import os
from pathlib import Path

def ensure_long_path(path):
    """
    Ensures a path is formatted as an extended-length path (\\?\ prefix) on Windows 
    to bypass the 260-character MAX_PATH limit.
    """
    if os.name != 'nt':
        return str(path)
        
    p_str = str(Path(path).absolute())
    
    # Already prefixed
    if p_str.startswith("\\\\?\\"):
        return p_str
        
    # Handle UNC paths (\\server\share -> \\?\UNC\server\share)
    if p_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p_str[2:]
        
    # Standard absolute path (C:\... -> \\?\C:\...)
    return "\\\\?\\" + p_str

def to_path(path):
    """Converts a path (potentially with long path prefix) to a Path object."""
    return Path(ensure_long_path(path))

def clean_path_for_display(path):
    """
    Removes the long path prefix (\\?\) from a path for cleaner display to users.
    Use this for any user-facing messages while keeping the long path internally.
    """
    path_str = str(path)
    # Remove \\?\ prefix if present
    if path_str.startswith('\\\\?\\'):
        return path_str[4:]
    # Remove \\?\UNC\ prefix if present (UNC paths)
    if path_str.startswith('\\\\?\\UNC\\'):
        return '\\\\' + path_str[8:]
    return path_str

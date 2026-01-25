"""
Chapter configuration loader for ARENA 3.0 curriculum.
Reads chapter metadata from config.yaml - locally if available, otherwise from GitHub.
"""

import logging
import time
from pathlib import Path

import requests
import yaml

logger = logging.getLogger(__name__)

# GitHub raw URL for the config file (used in production)
CONFIG_URL = "https://raw.githubusercontent.com/callummcdougall/arena-pragmatic-interp/main/infrastructure/core/config.yaml"

# Local config path (for development) - relative to this file's location
# Assumes repo structure: arena-app/ is sibling to arena-pragmatic-interp/
LOCAL_CONFIG_PATHS = [
    Path(__file__).parent.parent.parent.parent / "arena-pragmatic-interp" / "infrastructure" / "core" / "config.yaml",
    Path(__file__).parent.parent.parent / "arena-pragmatic-interp" / "infrastructure" / "core" / "config.yaml",
]

# Cache settings
_config_cache: dict | None = None
_cache_timestamp: float = 0
CACHE_TTL_SECONDS = 300  # 5 minutes


def _try_load_local_config() -> dict | None:
    """Try to load config from local file paths."""
    for config_path in LOCAL_CONFIG_PATHS:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                logger.info(f"Loaded config from local file: {config_path}")
                return config
            except Exception as e:
                logger.warning(f"Failed to load local config from {config_path}: {e}")
    return None


def _fetch_config() -> dict:
    """Fetch and parse the config.yaml - locally first, then from GitHub."""
    global _config_cache, _cache_timestamp

    # Check if cache is still valid
    now = time.time()
    if _config_cache is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _config_cache

    # Try local config first (for development)
    config = _try_load_local_config()
    if config is not None:
        _config_cache = config
        _cache_timestamp = now
        return config

    # Fall back to GitHub (for production)
    try:
        response = requests.get(CONFIG_URL, timeout=10)
        response.raise_for_status()
        config = yaml.safe_load(response.text)
        _config_cache = config
        _cache_timestamp = now
        logger.info("Successfully fetched config from GitHub")
        return config
    except Exception as e:
        logger.error(f"Failed to fetch config from GitHub: {e}")
        # Return cached version if available, even if stale
        if _config_cache is not None:
            logger.warning("Using stale cached config")
            return _config_cache
        raise


def _build_paths(chapter_id: str, section: dict) -> dict:
    """Build the full paths for a section based on chapter_id and section metadata."""
    section_copy = dict(section)

    # Skip path building for group sections (they have local_path instead)
    if section_copy.get("is_group"):
        return section_copy

    # Build path: {chapter_name}/instructions/pages/{page_file}
    if "page_file" in section_copy:
        section_copy["path"] = f"{chapter_id}/instructions/pages/{section_copy['page_file']}"

    # Build python_path: {chapter_name}/exercises/{exercise_dir}/solutions.py
    if "exercise_dir" in section_copy:
        section_copy["python_path"] = f"{chapter_id}/exercises/{section_copy['exercise_dir']}/solutions.py"

    return section_copy


def _transform_chapter(chapter_id: str, chapter_data: dict) -> dict:
    """Transform chapter data from YAML format to app format."""
    result = {
        "title": chapter_data.get("title", ""),
        "short_title": chapter_data.get("short_title", ""),
        "description": chapter_data.get("description", ""),
        "color": chapter_data.get("color", "#000000"),
        "icon": chapter_data.get("icon", "book"),
        "header_image": chapter_data.get("header_image", ""),
    }

    # Transform sections
    sections = []
    for section in chapter_data.get("sections", []):
        section_with_paths = _build_paths(chapter_id, section)
        sections.append(section_with_paths)

    result["sections"] = sections
    return result


def _get_chapters_dict() -> dict:
    """Get the transformed chapters dictionary."""
    config = _fetch_config()
    chapters_raw = config.get("chapters", {})

    result = {}
    for chapter_id, chapter_data in chapters_raw.items():
        # Skip entries that don't have the expected chapter structure
        # (i.e., they don't have a 'sections' key - they're from the old format)
        if "sections" not in chapter_data:
            continue
        result[chapter_id] = _transform_chapter(chapter_id, chapter_data)

    return result


def invalidate_cache():
    """Invalidate all caches. Useful for testing or forcing a refresh."""
    global _config_cache, _cache_timestamp
    _config_cache = None
    _cache_timestamp = 0


def get_chapter(chapter_id: str) -> dict | None:
    """Get a chapter by its ID, with section numbers included."""
    chapters = _get_chapters_dict()
    chapter = chapters.get(chapter_id)
    if not chapter:
        return None

    # Return a copy to avoid modifying cached data
    result = dict(chapter)
    result["sections"] = [dict(s) for s in chapter["sections"]]
    return result


def get_section(chapter_id: str, section_id: str) -> dict | None:
    """Get a section by chapter and section ID."""
    chapter = get_chapter(chapter_id)
    if not chapter:
        return None
    for section in chapter["sections"]:
        if section["id"] == section_id:
            return section
    return None


def get_all_chapters() -> list[dict]:
    """Get all chapters as a list with their IDs included."""
    chapters = _get_chapters_dict()
    result = []
    for chapter_id, chapter in chapters.items():
        # Count only actual content sections (excluding group headers)
        section_count = sum(1 for s in chapter["sections"] if not s.get("is_group"))
        result.append({"id": chapter_id, "section_count": section_count, **chapter})
    return result


def count_sections(chapter_id: str) -> int:
    """Count the number of actual sections (excluding group headers)."""
    chapter = get_chapter(chapter_id)
    if not chapter:
        return 0
    return sum(1 for s in chapter["sections"] if not s.get("is_group"))

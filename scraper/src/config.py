from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class Settings(BaseModel):
    target_domain: str = "example.com"
    start_url: str = "https://example.com/"
    max_concurrency: int = 3
    request_delay_min_ms: int = 500
    request_delay_max_ms: int = 1500
    max_retries: int = 3
    request_timeout: int = 30
    max_pages: int = 120
    enable_playwright: bool = False
    scrape_blogs: bool = True
    blog_limit: int = 20
    language: str = "en"
    output_directory: str = "output"
    respect_robots: bool = True
    user_agent: str = "AgentSalesKnowledgeScraper/1.0"
    incremental_state_file: str = "output/state.json"
    exclude_patterns: list[str] = Field(default_factory=list)
    include_patterns: list[str] = Field(default_factory=list)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings(root: Path) -> Settings:
    config_dir = root / "config"
    raw = _load_yaml(config_dir / "settings.yaml")
    raw["exclude_patterns"] = _load_yaml(config_dir / "excluded_patterns.yaml").get("exclude", [])
    raw["include_patterns"] = _load_yaml(config_dir / "allowed_patterns.yaml").get("include", [])
    env_map = {
        "TARGET_DOMAIN": ("target_domain", str),
        "START_URL": ("start_url", str),
        "MAX_CONCURRENCY": ("max_concurrency", int),
        "REQUEST_DELAY_MIN_MS": ("request_delay_min_ms", int),
        "REQUEST_DELAY_MAX_MS": ("request_delay_max_ms", int),
        "MAX_RETRIES": ("max_retries", int),
        "REQUEST_TIMEOUT": ("request_timeout", int),
        "MAX_PAGES": ("max_pages", int),
        "ENABLE_PLAYWRIGHT": ("enable_playwright", lambda v: v.lower() in {"1", "true", "yes"}),
        "SCRAPE_BLOGS": ("scrape_blogs", lambda v: v.lower() in {"1", "true", "yes"}),
        "BLOG_LIMIT": ("blog_limit", int),
        "LANGUAGE": ("language", str),
        "OUTPUT_DIRECTORY": ("output_directory", str),
    }
    for env_name, (field, caster) in env_map.items():
        if env_name in os.environ:
            raw[field] = caster(os.environ[env_name])
    return Settings(**raw)

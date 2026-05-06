"""Config manager — loads and validates YAML configuration files."""

from pathlib import Path

import yaml

from core.paths import resource_path
from mcp_server.server import mcp

# In source mode this resolves to PROJECT_ROOT/config/. In a bundled
# .app it resolves to Contents/Resources/config/ (where setup_py2app
# put the YAMLs). Using `__file__` here would land in the wrong place
# inside the bundle because the module ends up under
# Contents/Resources/lib/python3.12/mcp_server/tools/.
CONFIG_DIR = resource_path("config")

VALID_CONFIGS = {
    "search_criteria",
    "profiles",
    "alerts",
    "market_tiers",
    "cpm_rates",
    "data_sources",
}

DEFAULT_WEIGHTS = {
    "momentum": 0.25,
    "geographic_fit": 0.20,
    "revenue_potential": 0.20,
    "timing": 0.15,
    "content_velocity": 0.08,
    "engagement_quality": 0.07,
    "platform_diversification": 0.05,
}


def _load_yaml(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    # Explicit UTF-8 — bundled .app inherits no LANG from Finder-launched
    # processes, so the default open() encoding falls back to ASCII and
    # chokes on em-dashes / accented characters in the YAML.
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_weights(weights: dict[str, float]) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors = []
    expected_keys = set(DEFAULT_WEIGHTS.keys())
    if set(weights.keys()) != expected_keys:
        missing = expected_keys - set(weights.keys())
        extra = set(weights.keys()) - expected_keys
        if missing:
            errors.append(f"Missing dimensions: {missing}")
        if extra:
            errors.append(f"Unknown dimensions: {extra}")
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        errors.append(f"Weights sum to {total:.3f}, must equal 1.0")
    return errors


@mcp.tool()
def load_config(config_name: str) -> dict:
    """Load a configuration file by name.

    Args:
        config_name: One of: search_criteria, profiles, alerts,
                     market_tiers, cpm_rates, data_sources
    """
    if config_name not in VALID_CONFIGS:
        return {"error": f"Unknown config. Available: {sorted(VALID_CONFIGS)}"}
    return _load_yaml(config_name)


@mcp.tool()
def get_profile(profile_name: str) -> dict:
    """Load a specific search profile with its weights and filter overrides.

    Args:
        profile_name: Profile key from profiles.yaml (e.g. 'emerging_momentum'),
                      or 'default' for the default weights.
    """
    config = _load_yaml("profiles")

    if profile_name == "default":
        return {
            "name": "Default",
            "weights": DEFAULT_WEIGHTS,
            "filter_overrides": {},
        }

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        available = ["default"] + list(profiles.keys())
        return {"error": f"Unknown profile '{profile_name}'. Available: {available}"}

    profile = profiles[profile_name]
    weights = profile.get("weights", DEFAULT_WEIGHTS)

    errors = _validate_weights(weights)
    if errors:
        return {"error": f"Invalid weights in profile '{profile_name}': {errors}"}

    return {
        "name": profile.get("name", profile_name),
        "weights": weights,
        "filter_overrides": profile.get("filter_overrides", {}),
    }


@mcp.tool()
def list_profiles() -> dict:
    """List all available search profiles with their descriptions."""
    config = _load_yaml("profiles")
    profiles = {"default": "Default weights (no overrides)"}
    for key, val in config.get("profiles", {}).items():
        profiles[key] = val.get("description", "")
    return profiles

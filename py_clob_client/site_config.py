import json
from pathlib import Path

ZERO_BYTES32 = "0x0000000000000000000000000000000000000000000000000000000000000000"

DEFAULT_SITE_CONFIG = {
    "site_url": "",
    "builder_mode": False,
    "geoblock": False,
    "builder_code": "",
    "order_metadata": ZERO_BYTES32,
}


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".sdk" / "site-config.json"


def _read_string(config: dict, field: str) -> str:
    value = config.get(field, DEFAULT_SITE_CONFIG[field])
    if not isinstance(value, str):
        raise RuntimeError(f".sdk/site-config.json field {field} must be a string")
    return value


def _read_bool(config: dict, field: str) -> bool:
    value = config.get(field, DEFAULT_SITE_CONFIG[field])
    if not isinstance(value, bool):
        raise RuntimeError(f".sdk/site-config.json field {field} must be a boolean")
    return value


def _load_site_config() -> dict:
    path = _config_path()
    if not path.exists():
        return dict(DEFAULT_SITE_CONFIG)

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"Unable to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid {path}: {error}") from error

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Invalid {path}: expected a JSON object")

    return {
        "site_url": _read_string(parsed, "site_url"),
        "builder_mode": _read_bool(parsed, "builder_mode"),
        "geoblock": _read_bool(parsed, "geoblock"),
        "builder_code": _read_string(parsed, "builder_code"),
        "order_metadata": _read_string(parsed, "order_metadata"),
    }


SITE_CONFIG = _load_site_config()

GEOBLOCK_HOST = "https://geoblock.kuest.com"


def get_site_order_context() -> dict:
    context = {}
    builder_code = SITE_CONFIG["builder_code"].strip()
    if SITE_CONFIG["builder_mode"] and (
        not builder_code or builder_code == ZERO_BYTES32
    ):
        raise ValueError(
            "builder_mode requires a non-zero builder_code in .sdk/site-config.json"
        )
    if builder_code:
        context["builder_code"] = builder_code
    metadata = SITE_CONFIG["order_metadata"].strip()
    if metadata and metadata != ZERO_BYTES32:
        context["metadata"] = metadata
    return context

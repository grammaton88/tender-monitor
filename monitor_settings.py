from __future__ import annotations

import json
import os
from pathlib import Path

from monitor import APP_TYPE_CODES, IT_BASECODES

CONFIG_PATH = Path(__file__).resolve().parent / "monitor-config.json"
APP_TYPE_IDS = {value for value in APP_TYPE_CODES.values() if value != "0"}
SCHEDULE_INTERVAL_HOURS = (24, 48, 72, 168)
DEFAULT_CONFIG = {
    "cpv_codes": list(IT_BASECODES),
    "app_types": ["9", "2", "4", "3"],
    "app_status": "10",
    "enabled": True,
    "gemini_model": "gemini-3.5-flash-lite",
    "gemini_rpd_limit": 400,
    "gemini_tpd_limit": 0,
    "gemini_rpm_limit": 8,
    "gemini_tpm_limit": 200000,
    "max_analyses_per_run": 30,
    "max_run_minutes": 50,
    "initial_scan_mode": "all",
    "schedule_interval_hours": 72,
}


def validate_config(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Monitor configuration must be a JSON object")
    config = {**DEFAULT_CONFIG, **value}
    if "schedule_interval_hours" not in value and "schedule_interval_days" in value:
        legacy_days = value["schedule_interval_days"]
        if isinstance(legacy_days, bool) or not isinstance(legacy_days, int):
            raise ValueError("schedule_interval_days must be an integer")
        config["schedule_interval_hours"] = legacy_days * 24
    config.pop("schedule_interval_days", None)
    cpv_codes = config["cpv_codes"]
    app_types = config["app_types"]
    if not isinstance(cpv_codes, list) or not cpv_codes:
        raise ValueError("Select at least one CPV category")
    if any(not isinstance(code, str) or code not in IT_BASECODES for code in cpv_codes):
        raise ValueError("Configuration contains an unknown CPV code")
    if len(set(cpv_codes)) != len(cpv_codes):
        raise ValueError("Configuration contains duplicate CPV codes")
    if not isinstance(app_types, list) or not app_types:
        raise ValueError("Select at least one procurement procedure type")
    legacy_type_names = {
        "NAT": "9",
        "SPA": "2",
        "CON": "4",
        "CNT": "6",
        "MEP": "11",
        "DAP": "15",
        "TEP": "16",
        "GEO": "3",
        "DEP": "5",
        "GRA": "7",
        "PPP": "22",
        "B2B": "20",
    }
    app_types = [
        legacy_type_names.get(code, code) if isinstance(code, str) else code
        for code in app_types
    ] if isinstance(app_types, list) else app_types
    config["app_types"] = app_types
    if any(not isinstance(code, str) or code not in APP_TYPE_IDS for code in app_types):
        raise ValueError("Configuration contains an unknown procedure type")
    if len(set(app_types)) != len(app_types):
        raise ValueError("Configuration contains duplicate procedure types")
    config.pop("email_to", None)
    if not isinstance(config["app_status"], str) or config["app_status"] != "10":
        raise ValueError("Only announced tenders are currently supported")
    if not isinstance(config["enabled"], bool):
        raise ValueError("enabled must be true or false")
    if not isinstance(config["gemini_model"], str) or not config["gemini_model"].strip():
        raise ValueError("Gemini model must not be empty")
    for key in (
        "gemini_rpd_limit",
        "gemini_tpd_limit",
        "gemini_rpm_limit",
        "gemini_tpm_limit",
        "max_analyses_per_run",
    ):
        if isinstance(config[key], bool) or not isinstance(config[key], int) or config[key] < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if (
        isinstance(config["max_run_minutes"], bool)
        or not isinstance(config["max_run_minutes"], int)
        or not 1 <= config["max_run_minutes"] <= 80
    ):
        raise ValueError("max_run_minutes must be between 1 and 80")
    if config["initial_scan_mode"] not in ("all", "baseline"):
        raise ValueError("initial_scan_mode must be all or baseline")
    if (
        isinstance(config["schedule_interval_hours"], bool)
        or not isinstance(config["schedule_interval_hours"], int)
        or config["schedule_interval_hours"] not in SCHEDULE_INTERVAL_HOURS
    ):
        raise ValueError("schedule_interval_hours must be 24, 48, 72, or 168")
    return config


def load_config(path: Path = CONFIG_PATH) -> dict:
    serialized = os.environ.get("MONITOR_CONFIG")
    if serialized:
        try:
            return validate_config(json.loads(serialized))
        except json.JSONDecodeError as exc:
            raise ValueError("GitHub Actions variable MONITOR_CONFIG contains invalid JSON") from exc
    with path.open("r", encoding="utf-8") as handle:
        return validate_config(json.load(handle))


def apply_config_to_environment(config: dict) -> None:
    os.environ["GEMINI_MODEL"] = config["gemini_model"]
    os.environ["GEMINI_RPD_LIMIT"] = str(config["gemini_rpd_limit"])
    os.environ["GEMINI_TPD_LIMIT"] = str(config["gemini_tpd_limit"])
    os.environ["GEMINI_RPM_LIMIT"] = str(config["gemini_rpm_limit"])
    os.environ["GEMINI_TPM_LIMIT"] = str(config["gemini_tpm_limit"])
    os.environ["MAX_ANALYSES_PER_RUN"] = str(config["max_analyses_per_run"])
    os.environ["MAX_RUN_MINUTES"] = str(config["max_run_minutes"])
    os.environ["SCHEDULE_INTERVAL_HOURS"] = str(config["schedule_interval_hours"])
    os.environ["INITIAL_SCAN_MODE"] = config["initial_scan_mode"]

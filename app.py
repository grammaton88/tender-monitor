from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from monitor import APP_TYPE_CODES, IT_BASECODES
from monitor_settings import CONFIG_PATH, DEFAULT_CONFIG, validate_config

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
STATE_PATH = DATA_DIR / "state.json"
GITHUB_API = "https://api.github.com"
CONFIG_VARIABLE = "MONITOR_CONFIG"
WORKFLOW_FILE = "tender-monitor.yml"
STATE_BRANCH = "monitor-state"
USAGE_TIMEZONE = ZoneInfo("America/Los_Angeles")
STATE_CACHE_SECONDS = 30
_monitor_state_cache = None
_monitor_state_cached_at = 0.0
ACTION_SECRET_NAMES = ("EMAIL_TO", "EMAIL_FROM", "EMAIL_PASSWORD", "GEMINI_API_KEY")

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(
        os.environ.get("VERCEL") or os.environ.get("DASHBOARD_PASSWORD"),
    ),
)


def serve_static_asset(filename: str):
    return send_from_directory(BASE_DIR / "public" / "static", filename)


app.add_url_rule(
    "/static/<path:filename>",
    endpoint="static",
    view_func=serve_static_asset,
)


@app.errorhandler(RuntimeError)
def handle_configuration_unavailable(error):
    return render_template("error.html", message=str(error)), 503


@app.errorhandler(ValueError)
def handle_invalid_configuration(error):
    return render_template("error.html", message=str(error)), 503


APP_TYPES = [
    {"id": "9", "code": "NAT", "name": "ელექტრონული ტენდერი აუქციონის გარეშე"},
    {"id": "2", "code": "SPA", "name": "ელექტრონული ტენდერი რევერსული აუქციონით"},
    {"id": "4", "code": "CON", "name": "კონსოლიდირებული ტენდერი"},
    {"id": "6", "code": "CNT", "name": "კონკურსი"},
    {"id": "11", "code": "MEP", "name": "ორეტაპიანი ელექტრონული ტენდერი"},
    {"id": "15", "code": "DAP", "name": "ელექტრონული ტენდერი განსხვავებული წესით"},
    {"id": "16", "code": "TEP", "name": "ელექტრონული ტენდერი პრეკვალიფიკაციით"},
    {"id": "3", "code": "GEO", "name": "შესყიდვის ელექტრონული პროცედურა"},
    {"id": "5", "code": "DEP", "name": "შესყიდვის ელექტრონული პროცედურა დონორის სახსრებით"},
    {"id": "7", "code": "GRA", "name": "საგრანტო კონკურსი"},
    {"id": "22", "code": "PPP", "name": "საჯარო-კერძო თანამშრომლობა / კონცესია"},
    {"id": "20", "code": "B2B", "name": "კერძო შესყიდვა"},
    {"id": "8", "code": "NAT", "name": "გამარტივებული ელექტრონული ტენდერი აუქციონის გარეშე"},
    {"id": "1", "code": "SPA", "name": "გამარტივებული ელექტრონული ტენდერი რევერსული აუქციონით"},
    {"id": "10", "code": "MEP", "name": "ორეტაპიანი გამარტივებული ელექტრონული ტენდერი"},
    {"id": "14", "code": "DAP", "name": "გამარტივებული ელექტრონული ტენდერი განსხვავებული წესით"},
]
APP_TYPE_IDS = {value for value in APP_TYPE_CODES.values() if value != "0"}
CPV_OPTIONS = [
    {"id": code, "name": label}
    for code, label in IT_BASECODES.items()
]
CPV_IDS = {item["id"] for item in CPV_OPTIONS}


def default_config() -> dict:
    return {
        **DEFAULT_CONFIG,
        "cpv_codes": list(DEFAULT_CONFIG["cpv_codes"]),
        "app_types": list(DEFAULT_CONFIG["app_types"]),
    }


def default_state() -> dict:
    return {
        "usage": {},
        "last_run": None,
        "run_count": 0,
        "summary": {
            "active_tenders": 0,
            "new_records": 0,
            "pending_review": 0,
            "errors": 0,
        },
        "recent_tenders": [],
        "errors": [],
    }


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        save_json(path, default)
        return default.copy()
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}; refusing to overwrite it") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def selected_labels(options: list[dict], selected: list[str]) -> list[dict]:
    selected_set = set(selected)
    return [item for item in options if item["id"] in selected_set]


def github_config_settings() -> tuple[str, str] | None:
    token = os.environ.get("GITHUB_ACTIONS_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not token and not repository:
        if os.environ.get("VERCEL"):
            raise RuntimeError(
                "Dashboard GitHub configuration is not set up. "
                "Set GITHUB_REPOSITORY and GITHUB_ACTIONS_TOKEN.",
            )
        return None
    if (
        not token
        or len(repository.split("/")) != 2
        or any(not part for part in repository.split("/"))
    ):
        raise RuntimeError("Set GITHUB_ACTIONS_TOKEN and GITHUB_REPOSITORY for dashboard configuration")
    return token, repository


def github_config_request(
    method: str,
    url: str,
    token: str,
    *,
    allow_statuses=(),
    accept="application/vnd.github+json",
    **kwargs,
):
    headers = {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
    if response.status_code >= 400 and response.status_code not in allow_statuses:
        if response.status_code == 401:
            detail = (
                "GitHub rejected GITHUB_ACTIONS_TOKEN (HTTP 401). "
                "Replace it with an active token that has access to this repository."
            )
        elif response.status_code == 403:
            detail = (
                "GitHub denied access (HTTP 403). Check that the fine-grained token "
                "selects this repository and has Actions: Read and write plus "
                "Contents: Read permissions. Organization-owned repositories may "
                "also require token approval."
            )
        else:
            detail = f"GitHub Actions settings request failed (HTTP {response.status_code})"
        raise RuntimeError(
            detail
        )
    return response


def load_monitor_state(force_refresh: bool = False) -> dict:
    global _monitor_state_cache, _monitor_state_cached_at
    github = github_config_settings()
    if github is None:
        return load_json(STATE_PATH, default_state())

    now = time.monotonic()
    if (
        not force_refresh
        and _monitor_state_cache is not None
        and now - _monitor_state_cached_at < STATE_CACHE_SECONDS
    ):
        return _monitor_state_cache

    token, repository = github
    response = github_config_request(
        "GET",
        f"{GITHUB_API}/repos/{repository}/contents/state.json?ref={STATE_BRANCH}",
        token,
        allow_statuses=(404,),
        accept="application/vnd.github.raw+json",
    )
    if response.status_code == 404:
        state = default_state()
    else:
        try:
            state = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ValueError("GitHub monitor-state branch contains invalid state JSON") from exc
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("usage", {}), dict)
            or not isinstance(state.get("tenders", {}), dict)
        ):
            raise ValueError("GitHub monitor-state branch contains an invalid state file")

    _monitor_state_cache = state
    _monitor_state_cached_at = now
    return state


def daily_usage_snapshot(state: dict) -> dict:
    day = datetime.now(USAGE_TIMEZONE).date().isoformat()
    usage = [
        entry
        for entry in state.get("usage", {}).values()
        if isinstance(entry, dict) and entry.get("date") == day
    ]
    return {
        "date": day,
        "requests": sum(entry.get("requests", 0) for entry in usage),
        "input": sum(entry.get("input", 0) for entry in usage),
        "output": sum(entry.get("output", 0) for entry in usage),
        "total": sum(entry.get("total", 0) for entry in usage),
        "reserved_tokens": sum(entry.get("reserved_tokens", 0) for entry in usage),
        "unknown_usage": sum(entry.get("unknown_usage", 0) for entry in usage),
        "quota_errors": sum(entry.get("quota_errors", 0) for entry in usage),
        "updated_at": state.get("updated_at"),
    }


def load_github_workflow_runs(limit: int = 10) -> list[dict]:
    github = github_config_settings()
    if github is None:
        return []
    token, repository = github
    response = github_config_request(
        "GET",
        f"{GITHUB_API}/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/runs",
        token,
        params={"per_page": limit},
    )
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("GitHub returned an invalid workflow-runs response")
    runs = []
    for run in payload["workflow_runs"]:
        if not isinstance(run, dict):
            continue
        run_url = run.get("html_url")
        if not isinstance(run_url, str) or not run_url.startswith(
            "https://github.com/",
        ):
            continue
        run_details = {
            "id": run.get("id"),
            "number": run.get("run_number"),
            "title": run.get("display_title") or "IT Tender Monitor",
            "status": run.get("status") or "unknown",
            "conclusion": run.get("conclusion"),
            "current_step": None,
            "event": run.get("event") or "",
            "branch": run.get("head_branch") or "",
            "created_at": run.get("created_at") or "",
            "updated_at": run.get("updated_at") or "",
            "url": run_url,
        }
        if run_details["status"] in ("queued", "in_progress") and isinstance(
            run_details["id"],
            int,
        ):
            jobs_response = github_config_request(
                "GET",
                f"{GITHUB_API}/repos/{repository}/actions/runs/{run_details['id']}/jobs",
                token,
                params={"per_page": 100},
            )
            jobs_payload = jobs_response.json()
            jobs = jobs_payload.get("jobs", []) if isinstance(jobs_payload, dict) else []
            for job in jobs:
                if not isinstance(job, dict) or job.get("status") != "in_progress":
                    continue
                steps = job.get("steps", [])
                active_step = next(
                    (
                        step.get("name")
                        for step in steps
                        if isinstance(step, dict)
                        and step.get("status") == "in_progress"
                    ),
                    None,
                )
                run_details["current_step"] = active_step or job.get("name")
                break
        runs.append(run_details)
    return runs


def github_connection_diagnostics() -> list[dict]:
    github = github_config_settings()
    if github is None:
        return [{
            "name": "GitHub კავშირი",
            "ok": False,
            "detail": "GITHUB_REPOSITORY და GITHUB_ACTIONS_TOKEN მითითებული არ არის.",
        }]

    token, repository = github
    checks = (
        (
            "რეპოზიტორიის წვდომა",
            f"{GITHUB_API}/repos/{repository}",
            "რეპოზიტორიის Metadata: Read წვდომა შეამოწმეთ.",
        ),
        (
            "Actions და გაშვების ისტორია",
            f"{GITHUB_API}/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/runs",
            "ტოკენს სჭირდება Actions: Read and write წვდომა.",
        ),
        (
            "მონიტორინგის კონფიგურაცია",
            f"{GITHUB_API}/repos/{repository}/actions/variables/{CONFIG_VARIABLE}",
            "Actions variable-ების წასაკითხად/შესაცვლელად საჭიროა Actions: Read and write.",
        ),
        (
            "საიდუმლო გასაღებების მართვა",
            f"{GITHUB_API}/repos/{repository}/actions/secrets/public-key",
            "GitHub Actions Secrets-ისთვის საჭიროა Actions: Read and write.",
        ),
        (
            "მონიტორინგის სტატისტიკა",
            f"{GITHUB_API}/repos/{repository}/contents/state.json?ref={STATE_BRANCH}",
            "მონიტორინგის branch-ის წასაკითხად საჭიროა Contents: Read.",
        ),
    )
    diagnostics = []
    for name, endpoint, permission_help in checks:
        try:
            response = github_config_request(
                "GET",
                endpoint,
                token,
                allow_statuses=(403, 404),
            )
        except (RuntimeError, requests.RequestException) as exc:
            diagnostics.append({"name": name, "ok": False, "detail": str(exc)})
            continue

        if response.status_code == 403:
            diagnostics.append({"name": name, "ok": False, "detail": permission_help})
        elif response.status_code == 404 and name == "რეპოზიტორიის წვდომა":
            diagnostics.append({
                "name": name,
                "ok": False,
                "detail": "რეპოზიტორია ვერ მოიძებნა ან ტოკენს მასზე წვდომა არ აქვს.",
            })
        elif response.status_code == 404 and name == "მონიტორინგის კონფიგურაცია":
            diagnostics.append({
                "name": name,
                "ok": True,
                "detail": "ცვლადი ჯერ არ შექმნილა; გამოყენებული იქნება საწყისი კონფიგურაცია.",
            })
        elif response.status_code == 404 and name == "მონიტორინგის სტატისტიკა":
            diagnostics.append({
                "name": name,
                "ok": True,
                "detail": "მონიტორინგის ისტორია ჯერ არ შექმნილა.",
            })
        elif response.status_code == 404:
            diagnostics.append({"name": name, "ok": False, "detail": permission_help})
        else:
            diagnostics.append({"name": name, "ok": True, "detail": "წვდომა გამართულია."})
    return diagnostics


def config_revision(serialized: str) -> str:
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_monitor_config() -> tuple[dict, str | None]:
    github = github_config_settings()
    if github is None:
        if not CONFIG_PATH.exists():
            return validate_config(DEFAULT_CONFIG), None
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                return validate_config(json.load(handle)), None
        except json.JSONDecodeError as exc:
            raise ValueError("monitor-config.json contains invalid JSON") from exc

    token, repository = github
    endpoint = f"{GITHUB_API}/repos/{repository}/actions/variables/{CONFIG_VARIABLE}"
    response = github_config_request(
        "GET", endpoint, token, allow_statuses=(404,),
    )
    if response.status_code == 404:
        if not CONFIG_PATH.exists():
            return validate_config(DEFAULT_CONFIG), None
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            return validate_config(json.load(handle)), None
    serialized = response.json()["value"]
    return validate_config(json.loads(serialized)), config_revision(serialized)


def save_monitor_config(config: dict, current_revision: str | None) -> None:
    serialized = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    github = github_config_settings()
    if github is None:
        save_json(CONFIG_PATH, config)
        return

    token, repository = github
    endpoint = f"{GITHUB_API}/repos/{repository}/actions/variables/{CONFIG_VARIABLE}"
    current = github_config_request(
        "GET", endpoint, token, allow_statuses=(404,),
    )
    if current.status_code == 404:
        if current_revision is not None:
            raise RuntimeError("Configuration changed in GitHub; reload the settings page and try again")
        github_config_request(
            "POST",
            f"{GITHUB_API}/repos/{repository}/actions/variables",
            token,
            json={"name": CONFIG_VARIABLE, "value": serialized},
        )
        return
    current_value = current.json()["value"]
    if config_revision(current_value) != current_revision:
        raise RuntimeError("Configuration changed in GitHub; reload the settings page and try again")
    github_config_request(
        "PATCH",
        endpoint,
        token,
        json={"name": CONFIG_VARIABLE, "value": serialized},
    )


def dispatch_monitor_workflow() -> None:
    github = github_config_settings()
    if github is None:
        raise RuntimeError("Configure GitHub Actions access before starting a workflow")
    token, repository = github
    active_runs = [
        run
        for run in load_github_workflow_runs(limit=10)
        if run["status"] in ("queued", "in_progress")
    ]
    if active_runs:
        active_run = active_runs[0]
        raise RuntimeError(
            f"მონიტორინგი უკვე გაშვებულია ან რიგშია (გაშვება #{active_run['number']}). "
            "დაელოდეთ მის დასრულებას."
        )
    repository_response = github_config_request(
        "GET",
        f"{GITHUB_API}/repos/{repository}",
        token,
    )
    repository_details = repository_response.json()
    branch = (
        repository_details.get("default_branch")
        if isinstance(repository_details, dict)
        else None
    )
    if not isinstance(branch, str) or not branch:
        raise RuntimeError("Could not determine the GitHub repository's default branch")
    github_config_request(
        "POST",
        f"{GITHUB_API}/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        token,
        json={"ref": branch},
    )


def save_github_secrets(values: dict[str, str]) -> list[str]:
    updates = {
        name: value for name, value in values.items()
        if name in ACTION_SECRET_NAMES and value
    }
    if not updates:
        return []
    github = github_config_settings()
    if github is None:
        raise RuntimeError("Secrets can only be saved through the authenticated GitHub dashboard")
    token, repository = github
    public_key_endpoint = f"{GITHUB_API}/repos/{repository}/actions/secrets/public-key"
    key_payload = github_config_request("GET", public_key_endpoint, token).json()
    from nacl.public import PublicKey, SealedBox

    public_key = PublicKey(
        base64.b64decode("".join(key_payload["key"].split()), validate=True),
    )
    box = SealedBox(public_key)
    saved = []
    for name, value in updates.items():
        if len(value) > 5000:
            raise ValueError(f"{name} value is too long")
        if name in ("EMAIL_TO", "EMAIL_FROM") and not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            value,
        ):
            raise ValueError(f"{name} must be a valid email address")
        encrypted = base64.b64encode(box.encrypt(value.encode("utf-8"))).decode("ascii")
        endpoint = f"{GITHUB_API}/repos/{repository}/actions/secrets/{name}"
        try:
            github_config_request(
                "PUT",
                endpoint,
                token,
                json={"encrypted_value": encrypted, "key_id": key_payload["key_id"]},
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"{name} could not be saved. Earlier secrets in this request may already have been updated."
            ) from exc
        saved.append(name)
    return saved


@app.before_request
def require_dashboard_authentication():
    expected_username = os.environ.get("DASHBOARD_USERNAME")
    expected_password = os.environ.get("DASHBOARD_PASSWORD")
    if os.environ.get("VERCEL") and not os.environ.get("SECRET_KEY"):
        abort(503, description="Set SECRET_KEY in the Vercel project environment")
    if (
        os.environ.get("VERCEL")
        or expected_username
        or expected_password
    ):
        if not expected_username or not expected_password:
            abort(503, description="Dashboard authentication is not configured")
        supplied = request.authorization
        if (
            not supplied
            or not hmac.compare_digest(supplied.username or "", expected_username)
            or not hmac.compare_digest(supplied.password or "", expected_password)
        ):
            return (
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Tender Monitor"'},
            )
    if "csrf_token" not in session:
        import secrets

        session["csrf_token"] = secrets.token_urlsafe(32)


@app.before_request
def validate_csrf_token():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not hmac.compare_digest(submitted, expected):
            abort(400, description="Invalid CSRF token")


@app.context_processor
def inject_common_data():
    return {
        "state": default_state(),
        "app_types": APP_TYPES,
        "cpv_options": CPV_OPTIONS,
        "csrf_token": session.get("csrf_token", ""),
        "config_remote": bool(
            os.environ.get("GITHUB_ACTIONS_TOKEN")
            and os.environ.get("GITHUB_REPOSITORY")
        ),
        "actions_url": (
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions"
            if os.environ.get("GITHUB_REPOSITORY")
            else None
        ),
    }


@app.route("/")
def dashboard():
    config, _ = load_monitor_config()
    state = dict(load_monitor_state())
    last_run = state.get("last_monitor_run_at")
    state["last_run"] = (
        datetime.fromtimestamp(last_run, ZoneInfo("Asia/Tbilisi")).isoformat()
        if isinstance(last_run, (int, float))
        else None
    )
    return render_template(
        "dashboard.html",
        config=config,
        summary=state.get("summary", {}),
        recent_tenders=state.get("recent_tenders", []),
        errors=state.get("errors", []),
        selected_cpv=selected_labels(CPV_OPTIONS, config.get("cpv_codes", [])),
        selected_types=selected_labels(APP_TYPES, config.get("app_types", [])),
        daily_usage=daily_usage_snapshot(state),
    )


@app.route("/api/usage")
def usage_api():
    try:
        state = load_monitor_state(force_refresh=True)
    except (RuntimeError, ValueError, requests.RequestException):
        app.logger.exception("Unable to refresh AI usage statistics from GitHub")
        return app.response_class(
            json.dumps({"error": "GitHub statistics could not be refreshed"}),
            status=503,
            mimetype="application/json",
            headers={"Cache-Control": "no-store"},
        )
    return app.response_class(
        json.dumps(daily_usage_snapshot(state)),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.route("/api/workflow-runs")
def workflow_runs_api():
    try:
        runs = load_github_workflow_runs()
    except (RuntimeError, ValueError, requests.RequestException):
        app.logger.exception("Unable to refresh GitHub Actions workflow runs")
        return app.response_class(
            json.dumps({"error": "GitHub workflow runs could not be refreshed"}),
            status=503,
            mimetype="application/json",
            headers={"Cache-Control": "no-store"},
        )
    return app.response_class(
        json.dumps({"runs": runs}),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.route("/api/github-health")
def github_health_api():
    try:
        checks = github_connection_diagnostics()
    except RuntimeError as exc:
        checks = [{"name": "GitHub კავშირი", "ok": False, "detail": str(exc)}]
    return app.response_class(
        json.dumps({
            "connected": bool(checks) and all(check["ok"] for check in checks),
            "checks": checks,
        }),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.route("/runs")
def workflow_runs():
    config, _ = load_monitor_config()
    try:
        runs = load_github_workflow_runs()
    except (RuntimeError, ValueError, requests.RequestException) as exc:
        app.logger.exception("Unable to load GitHub Actions workflow runs")
        flash(f"GitHub Actions-ის გაშვებების ჩატვირთვა ვერ მოხერხდა: {exc}", "error")
        runs = []
    try:
        diagnostics = github_connection_diagnostics()
    except RuntimeError as exc:
        diagnostics = [{"name": "GitHub კავშირი", "ok": False, "detail": str(exc)}]
    return render_template(
        "runs.html",
        config=config,
        config_remote=github_config_settings() is not None,
        runs=runs,
        diagnostics=diagnostics,
        actions_url=(
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions"
            if os.environ.get("GITHUB_REPOSITORY")
            else None
        ),
    )


@app.route("/run-now", methods=["POST"])
def run_now():
    try:
        dispatch_monitor_workflow()
    except (RuntimeError, requests.RequestException) as exc:
        flash(f"Workflow-ის გაშვება ვერ მოხერხდა: {exc}", "error")
    else:
        flash(
            "ხელით გაშვების მოთხოვნა GitHub Actions-ში გაიგზავნა. "
            "შედეგი Actions გვერდზე შეგიძლიათ ნახოთ.",
            "success",
        )
    return redirect(url_for("dashboard"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    config, current_revision = load_monitor_config()
    if request.method == "POST":
        submitted_revision = request.form.get("config_revision") or None
        if submitted_revision != current_revision:
            flash("პარამეტრები სხვა მომხმარებელმა შეცვალა. გვერდი განაახლეთ და სცადეთ თავიდან.", "error")
            return render_template(
                "settings.html",
                config=config,
                app_types=APP_TYPES,
                cpv_options=CPV_OPTIONS,
                config_revision=current_revision,
            ), 409
        selected_cpvs = request.form.getlist("cpv_codes")
        selected_types = request.form.getlist("app_types")
        submitted_config = {
            **config,
            "cpv_codes": [code for code in selected_cpvs if code in CPV_IDS],
            "app_types": [code for code in selected_types if code in APP_TYPE_IDS],
            "gemini_model": request.form.get("gemini_model", "").strip(),
            "gemini_rpd_limit": request.form.get("gemini_rpd_limit", ""),
            "gemini_tpd_limit": request.form.get("gemini_tpd_limit", ""),
            "gemini_rpm_limit": request.form.get("gemini_rpm_limit", ""),
            "gemini_tpm_limit": request.form.get("gemini_tpm_limit", ""),
            "max_analyses_per_run": request.form.get("max_analyses_per_run", ""),
            "max_run_minutes": request.form.get("max_run_minutes", ""),
            "schedule_interval_hours": request.form.get("schedule_interval_hours", ""),
            "initial_scan_mode": request.form.get("initial_scan_mode", ""),
            "enabled": request.form.get("enabled") == "on",
        }
        invalid_cpvs = set(selected_cpvs) - CPV_IDS
        invalid_types = set(selected_types) - APP_TYPE_IDS
        if invalid_cpvs or invalid_types:
            flash("არჩეული ფილტრები შეიცავს უცნობ კოდს. გადაამოწმეთ არჩევანი.", "error")
            return render_template(
                "settings.html",
                config=submitted_config,
                app_types=APP_TYPES,
                cpv_options=CPV_OPTIONS,
                config_revision=current_revision,
            ), 400
        if not selected_cpvs:
            flash("მონიტორინგისთვის მინიმუმ ერთი CPV კატეგორია უნდა აირჩიოთ.", "error")
            return render_template(
                "settings.html",
                config=submitted_config,
                app_types=APP_TYPES,
                cpv_options=CPV_OPTIONS,
                config_revision=current_revision,
            ), 400
        if not selected_types:
            flash("მონიტორინგისთვის მინიმუმ ერთი შესყიდვის ტიპი უნდა აირჩიოთ.", "error")
            return render_template(
                "settings.html",
                config=submitted_config,
                app_types=APP_TYPES,
                cpv_options=CPV_OPTIONS,
                config_revision=current_revision,
            ), 400
        for key in (
            "gemini_rpd_limit", "gemini_tpd_limit", "gemini_rpm_limit",
            "gemini_tpm_limit", "max_analyses_per_run", "max_run_minutes",
            "schedule_interval_hours",
        ):
            try:
                submitted_config[key] = int(submitted_config[key])
            except (TypeError, ValueError):
                flash("ლიმიტები და დროის პარამეტრები მთელ რიცხვებად უნდა იყოს მითითებული.", "error")
                return render_template(
                    "settings.html", config=submitted_config,
                    app_types=APP_TYPES, cpv_options=CPV_OPTIONS,
                    config_revision=current_revision,
                ), 400
        saved_secrets = []
        config_saved = False
        try:
            validated = validate_config(submitted_config)
            save_monitor_config(validated, current_revision)
            config_saved = True
            saved_secrets = save_github_secrets({
                name: request.form.get(f"secret_{name}", "")
                for name in ACTION_SECRET_NAMES
            })
        except (ValueError, RuntimeError, requests.RequestException, json.JSONDecodeError) as exc:
            if saved_secrets:
                flash(
                    f"პარამეტრები შენახულია. GitHub Secrets-ის ნაწილის შენახვა ვერ მოხერხდა: {exc}",
                    "error",
                )
            elif config_saved:
                flash(
                    f"პარამეტრები შენახულია, მაგრამ საიდუმლო მონაცემები ვერ განახლდა: {exc}",
                    "error",
                )
            else:
                flash(f"პარამეტრები ვერ შეინახა: {exc}", "error")
            return render_template(
                "settings.html",
                config=submitted_config,
                app_types=APP_TYPES,
                cpv_options=CPV_OPTIONS,
                config_revision=current_revision,
                config_remote=github_config_settings() is not None,
            ), 400
        if saved_secrets:
            flash(
                "პარამეტრები და GitHub Secrets განახლდა. საიდუმლო მნიშვნელობები აღარ გამოჩნდება.",
                "success",
            )
        else:
            flash("პარამეტრები GitHub-ში წარმატებით შეინახა.", "success")
        return redirect(url_for("settings"))
    return render_template(
        "settings.html",
        config=config,
        app_types=APP_TYPES,
        cpv_options=CPV_OPTIONS,
        config_revision=current_revision,
        config_remote=github_config_settings() is not None,
    )


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_json(STATE_PATH, default_state())
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))

import json
import os
import tempfile
import base64
import unittest
from pathlib import Path
from unittest.mock import patch

import app as dashboard
from bs4 import BeautifulSoup
from monitor_settings import DEFAULT_CONFIG, apply_config_to_environment, load_config
from nacl.public import PrivateKey, SealedBox


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.config_path = root / "monitor-config.json"
        self.state_path = root / "state.json"
        self.config_path.write_text(json.dumps(dashboard.default_config()), encoding="utf-8")
        self.state_path.write_text(json.dumps(dashboard.default_state()), encoding="utf-8")
        self.config_patch = patch.object(dashboard, "CONFIG_PATH", self.config_path)
        self.state_patch = patch.object(dashboard, "STATE_PATH", self.state_path)
        self.config_patch.start()
        self.state_patch.start()
        self.environment_patch = patch.dict(
            os.environ,
            {
                "GITHUB_ACTIONS_TOKEN": "",
                "GITHUB_REPOSITORY": "",
                "VERCEL": "",
                "SECRET_KEY": "",
            },
        )
        self.environment_patch.start()
        dashboard._monitor_state_cache = None
        dashboard._monitor_state_cached_at = 0.0
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.environment_patch.stop)
        dashboard.app.config.update(TESTING=True)
        self.client = dashboard.app.test_client()

    def post_settings(self, values):
        page = self.client.get("/settings")
        token = BeautifulSoup(page.data, "html.parser").select_one(
            'input[name="csrf_token"]',
        )["value"]
        revision = BeautifulSoup(page.data, "html.parser").select_one(
            'input[name="config_revision"]',
        )["value"]
        return self.client.post(
            "/settings",
            data={"csrf_token": token, "config_revision": revision, **values},
        )

    def test_all_cpv_categories_are_selected_by_default(self):
        self.assertEqual(dashboard.default_config()["cpv_codes"], list(dashboard.IT_BASECODES))
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data.count(b'name="cpv_codes"'),
            len(dashboard.IT_BASECODES),
        )
        soup = BeautifulSoup(response.data, "html.parser")
        checked_cpvs = soup.select('input[name="cpv_codes"]:checked')
        self.assertEqual(len(checked_cpvs), len(dashboard.IT_BASECODES))

    def test_settings_list_full_cpv_labels_and_all_procurement_ids(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("სატელეკომუნიკაციო მოწყობილობები და აქსესუარები".encode(), response.data)
        self.assertIn(b'name="cpv_codes"', response.data)
        self.assertIn(b'value="9"', response.data)
        self.assertIn("გამარტივებული ელექტრონული ტენდერი აუქციონის გარეშე".encode(), response.data)

    def test_settings_save_persists_selected_filter_ids(self):
        values = {key: str(value) for key, value in DEFAULT_CONFIG.items()
                  if key not in ("cpv_codes", "app_types", "enabled")}
        values.update(
            cpv_codes=["18936", "19006"],
            app_types=["9", "3"],
            enabled="on",
        )
        response = self.post_settings(values)
        self.assertEqual(response.status_code, 302)
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["cpv_codes"], ["18936", "19006"])
        self.assertEqual(saved["app_types"], ["9", "3"])
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["gemini_rpd_limit"], DEFAULT_CONFIG["gemini_rpd_limit"])
        self.assertEqual(saved["schedule_interval_hours"], DEFAULT_CONFIG["schedule_interval_hours"])

    def test_settings_rejects_unknown_codes_and_empty_selection(self):
        invalid_code = self.post_settings(
            {"cpv_codes": ["not-a-cpv"], "app_types": ["9"]},
        )
        self.assertEqual(invalid_code.status_code, 400)
        empty_types = self.post_settings(
            {"cpv_codes": ["18936"]},
        )
        self.assertEqual(empty_types.status_code, 400)
        self.assertEqual(json.loads(self.config_path.read_text(encoding="utf-8"))["app_types"],
                         ["9", "2", "4", "3"])

    def test_legacy_type_names_are_mapped_to_portal_codes(self):
        config = dashboard.validate_config({**dashboard.default_config(), "app_types": ["NAT", "GEO"]})
        self.assertEqual(config["app_types"], ["9", "3"])

    def test_invalid_json_is_not_silently_overwritten(self):
        self.config_path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            dashboard.load_json(self.config_path, dashboard.default_config())
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), "{broken")

    def test_vercel_requires_dashboard_authentication(self):
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "SECRET_KEY": "test-secret",
            "DASHBOARD_USERNAME": "admin",
            "DASHBOARD_PASSWORD": "strong-password",
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(dashboard, "load_monitor_config", return_value=(dashboard.default_config(), None)):
            self.assertEqual(self.client.get("/settings").status_code, 401)
            self.assertEqual(
                self.client.get(
                    "/settings",
                    headers={"Authorization": "Basic YWRtaW46c3Ryb25nLXBhc3N3b3Jk"},
                ).status_code,
                200,
            )

    def test_public_static_assets_are_served_by_local_static_endpoint(self):
        response = self.client.get("/static/css/style.css")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b".back-to-top", response.data)

    def test_vercel_requires_github_configuration(self):
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "GITHUB_ACTIONS_TOKEN": "",
            "GITHUB_REPOSITORY": "",
        }):
            with self.assertRaisesRegex(RuntimeError, "GITHUB_REPOSITORY"):
                dashboard.github_config_settings()

    def test_vercel_requires_a_secret_key(self):
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "SECRET_KEY": "",
        }):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 503)

    def test_github_forbidden_error_explains_required_token_permissions(self):
        response = unittest.mock.MagicMock(status_code=403)
        response.json.return_value = {"message": "Resource not accessible by personal access token"}
        with patch.object(
            dashboard.requests,
            "request",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Actions: Read and write.*Contents: Read",
            ):
                dashboard.github_config_request(
                    "GET",
                    "https://api.github.com/repos/owner/repository/actions/variables/MONITOR_CONFIG",
                    "synthetic-test-token",
                )

    def test_github_forbidden_error_includes_github_response_message(self):
        response = unittest.mock.MagicMock(status_code=403)
        response.json.return_value = {
            "message": "Resource not accessible by personal access token",
        }
        with patch.object(
            dashboard.requests,
            "request",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "GitHub's response: Resource not accessible by personal access token",
            ):
                dashboard.github_config_request(
                    "GET",
                    "https://api.github.com/repos/owner/repository/actions/variables/MONITOR_CONFIG",
                    "synthetic-test-token",
                )

    def test_vercel_shows_setup_error_when_github_is_not_configured(self):
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "SECRET_KEY": "test-secret",
            "DASHBOARD_USERNAME": "admin",
            "DASHBOARD_PASSWORD": "strong-password",
            "GITHUB_ACTIONS_TOKEN": "",
            "GITHUB_REPOSITORY": "",
        }):
            response = self.client.get(
                "/",
                headers={"Authorization": "Basic YWRtaW46c3Ryb25nLXBhc3N3b3Jk"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"GITHUB_REPOSITORY", response.data)

    def test_github_actions_variable_stores_dashboard_configuration(self):
        config = dashboard.default_config()
        serialized = json.dumps(config)
        get_responses = []
        for _ in range(2):
            response = unittest.mock.MagicMock(status_code=200)
            response.json.return_value = {"value": serialized}
            get_responses.append(response)
        update_response = unittest.mock.MagicMock(status_code=204)
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
            "VERCEL": "1",
            "SECRET_KEY": "test-secret",
        }), patch.object(
            dashboard.requests,
            "request",
            side_effect=[*get_responses, update_response],
        ) as api:
            loaded, revision = dashboard.load_monitor_config()
            dashboard.save_monitor_config(loaded, revision)
        self.assertEqual(revision, dashboard.config_revision(serialized))
        self.assertEqual(api.call_count, 3)
        self.assertEqual(api.call_args.args[0], "PATCH")
        update_payload = api.call_args.kwargs["json"]
        self.assertEqual(update_payload["name"], "MONITOR_CONFIG")
        self.assertIn('"schedule_interval_hours": 72', update_payload["value"])
        self.assertEqual(
            api.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_dashboard_shows_manual_run_action_when_github_is_configured(self):
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard,
            "load_monitor_config",
            return_value=(dashboard.default_config(), None),
        ), patch.object(
            dashboard,
            "load_monitor_state",
            return_value=dashboard.default_state(),
        ):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'action="/run-now"', response.data)
        self.assertIn("გაშვება ახლავე".encode(), response.data)

    def test_manual_run_dispatches_workflow_on_default_branch(self):
        repository_response = unittest.mock.MagicMock(status_code=200)
        repository_response.json.return_value = {"default_branch": "main"}
        dispatch_response = unittest.mock.MagicMock(status_code=204)
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard,
            "load_github_workflow_runs",
            return_value=[],
        ), patch.object(
            dashboard.requests,
            "request",
            side_effect=[repository_response, dispatch_response],
        ) as api:
            dashboard.dispatch_monitor_workflow()
        self.assertEqual(api.call_count, 2)
        self.assertEqual(
            api.call_args.args[1],
            "https://api.github.com/repos/owner/repository/actions/workflows/"
            "tender-monitor.yml/dispatches",
        )
        self.assertEqual(api.call_args.kwargs["json"], {"ref": "main"})

    def test_manual_run_route_requires_csrf_and_reports_dispatch(self):
        page = self.client.get("/settings")
        csrf_token = BeautifulSoup(page.data, "html.parser").select_one(
            'input[name="csrf_token"]',
        )["value"]
        with patch.object(dashboard, "dispatch_monitor_workflow") as dispatch:
            response = self.client.post(
                "/run-now",
                data={"csrf_token": csrf_token},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with()
        self.assertIn("გაიგზავნა".encode(), response.data)

        invalid_csrf = self.client.post("/run-now", data={"csrf_token": "invalid"})
        self.assertEqual(invalid_csrf.status_code, 400)

    def test_load_github_workflow_runs_returns_safe_run_links_and_metadata(self):
        response = unittest.mock.MagicMock(status_code=200)
        response.json.return_value = {
            "workflow_runs": [
                {
                    "run_number": 12,
                    "display_title": "IT Tender Monitor",
                    "status": "completed",
                    "conclusion": "success",
                    "event": "schedule",
                    "head_branch": "main",
                    "created_at": "2026-10-26T06:00:00Z",
                    "updated_at": "2026-10-26T06:02:00Z",
                    "html_url": "https://github.com/owner/repository/actions/runs/12",
                },
                {
                    "run_number": 13,
                    "html_url": "https://attacker.example/fake-run",
                },
            ],
        }
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(dashboard.requests, "request", return_value=response) as api:
            runs = dashboard.load_github_workflow_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["number"], 12)
        self.assertEqual(
            runs[0]["url"],
            "https://github.com/owner/repository/actions/runs/12",
        )
        self.assertEqual(api.call_args.kwargs["params"], {"per_page": 10})

    def test_workflow_runs_page_has_left_sidebar_links_launch_and_logs(self):
        run = {
            "number": 4,
            "title": "IT Tender Monitor",
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
            "branch": "main",
            "created_at": "2026-10-26T06:00:00Z",
            "updated_at": "2026-10-26T06:02:00Z",
            "url": "https://github.com/owner/repository/actions/runs/4",
        }
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard,
            "load_monitor_config",
            return_value=(dashboard.default_config(), None),
        ), patch.object(
            dashboard,
            "load_github_workflow_runs",
            return_value=[run],
        ):
            response = self.client.get("/runs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("გაშვების ჟურნალები".encode(), response.data)
        self.assertIn("გაშვება ახლავე".encode(), response.data)
        self.assertIn(b'data-usage-metric="requests"', response.data)
        self.assertIn(b'data-usage-metric="total"', response.data)
        self.assertIn("გვერდის დასაწყისში დაბრუნება".encode(), response.data)
        self.assertIn(run["url"].encode(), response.data)
        self.assertIn("წარმატებული".encode(), response.data)

    def test_dashboard_footer_is_right_aligned_and_has_back_to_top(self):
        for path in ("/", "/settings", "/runs"):
            with patch.object(
                dashboard,
                "load_monitor_config",
                return_value=(dashboard.default_config(), None),
            ), patch.object(
                dashboard,
                "load_monitor_state",
                return_value=dashboard.default_state(),
            ), patch.object(
                dashboard,
                "load_github_workflow_runs",
                return_value=[],
            ), patch.object(
                dashboard,
                "github_connection_diagnostics",
                return_value=[],
            ):
                response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.data, "html.parser")
            self.assertIsNotNone(soup.select_one("footer.page-footer"))
            author_link = soup.select_one(
                'footer.page-footer .page-footer-author a[href="https://www.linkedin.com/in/mikheil-kakabadze"]',
            )
            self.assertIsNotNone(author_link)
            self.assertEqual(author_link.get_text(strip=True), "Mikheil Kakabadze")
            self.assertIn("Developed by", soup.select_one(".page-footer-author").get_text())
            self.assertEqual(soup.select_one(".back-to-top")["href"], "#page-top")
            self.assertIsNotNone(
                soup.select_one("footer.page-footer > .back-to-top"),
            )
            self.assertEqual(
                soup.select_one(".back-to-top").get_text(strip=True),
                "↑",
            )
            self.assertEqual(
                soup.select_one(".back-to-top")["aria-label"],
                "გვერდის დასაწყისში დაბრუნება",
            )

    def test_settings_header_links_back_to_dashboard(self):
        with patch.object(
            dashboard,
            "load_monitor_config",
            return_value=(dashboard.default_config(), None),
        ):
            response = self.client.get("/settings")
        soup = BeautifulSoup(response.data, "html.parser")
        overview_link = soup.select_one(".page-header .header-link")
        self.assertEqual(overview_link["href"], "/")
        self.assertIn("მიმოხილვა", overview_link.get_text())

    def test_running_workflow_exposes_current_step(self):
        runs_response = unittest.mock.MagicMock(status_code=200)
        runs_response.json.return_value = {
            "workflow_runs": [{
                "id": 42,
                "run_number": 8,
                "status": "in_progress",
                "html_url": "https://github.com/owner/repository/actions/runs/42",
            }],
        }
        jobs_response = unittest.mock.MagicMock(status_code=200)
        jobs_response.json.return_value = {
            "jobs": [{
                "name": "run-monitor",
                "status": "in_progress",
                "steps": [
                    {"name": "Install dependencies", "status": "completed"},
                    {"name": "Run tender monitor", "status": "in_progress"},
                ],
            }],
        }
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard.requests,
            "request",
            side_effect=[runs_response, jobs_response],
        ):
            runs = dashboard.load_github_workflow_runs()
        self.assertEqual(runs[0]["current_step"], "Run tender monitor")

    def test_manual_dispatch_is_blocked_when_workflow_already_active(self):
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard,
            "load_github_workflow_runs",
            return_value=[{
                "number": 9,
                "status": "in_progress",
                "current_step": "Run tender monitor",
            }],
        ), patch.object(dashboard.requests, "request") as api:
            with self.assertRaisesRegex(RuntimeError, "უკვე გაშვებულია"):
                dashboard.dispatch_monitor_workflow()
        api.assert_not_called()

    def test_github_diagnostics_report_missing_contents_permission(self):
        responses = []
        for status in (200, 200, 200, 200, 403):
            response = unittest.mock.MagicMock(status_code=status)
            responses.append(response)
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard.requests,
            "request",
            side_effect=responses,
        ):
            checks = dashboard.github_connection_diagnostics()
        self.assertTrue(all(check["ok"] for check in checks[:-1]))
        self.assertFalse(checks[-1]["ok"])
        self.assertIn("Contents: Read", checks[-1]["detail"])

    def test_workflow_runs_api_is_not_cached(self):
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard,
            "load_github_workflow_runs",
            return_value=[{"number": 1, "status": "completed"}],
        ):
            response = self.client.get("/api/workflow-runs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.json["runs"][0]["number"], 1)

    def test_config_values_are_applied_to_monitor_environment(self):
        config = dashboard.default_config()
        config.update(
            gemini_model="test-model",
            gemini_rpd_limit=123,
            max_analyses_per_run=7,
            max_run_minutes=12,
            schedule_interval_hours=24,
            initial_scan_mode="baseline",
        )
        with patch.dict(os.environ, {}, clear=True):
            apply_config_to_environment(config)
            self.assertEqual(os.environ["GEMINI_MODEL"], "test-model")
            self.assertEqual(os.environ["GEMINI_RPD_LIMIT"], "123")
            self.assertEqual(os.environ["MAX_ANALYSES_PER_RUN"], "7")
            self.assertEqual(os.environ["MAX_RUN_MINUTES"], "12")
            self.assertEqual(os.environ["SCHEDULE_INTERVAL_HOURS"], "24")
            self.assertEqual(os.environ["INITIAL_SCAN_MODE"], "baseline")

    def test_legacy_day_intervals_migrate_to_hours(self):
        config = dashboard.validate_config({
            **dashboard.default_config(),
            "schedule_interval_days": 3,
        })
        self.assertEqual(config["schedule_interval_hours"], 72)
        self.assertNotIn("schedule_interval_days", config)

    def test_dashboard_shows_frequency_as_days_with_hours(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.data, "html.parser")
        frequency = soup.select_one('select[name="schedule_interval_hours"]')
        self.assertIsNotNone(frequency)
        self.assertEqual(
            [(option["value"], option.get_text(strip=True)) for option in frequency.select("option")],
            [
                ("24", "ყოველ 1 დღეში (24 საათი)"),
                ("48", "ყოველ 2 დღეში (48 საათი)"),
                ("72", "ყოველ 3 დღეში (72 საათი)"),
                ("168", "ყოველ 7 დღეში (168 საათი)"),
            ],
        )

    def test_daily_usage_api_aggregates_today_and_is_not_cached(self):
        today = dashboard.datetime.now(dashboard.USAGE_TIMEZONE).date().isoformat()
        self.state_path.write_text(json.dumps({
            "usage": {
                f"{today}/model-a": {
                    "date": today, "requests": 2, "input": 100, "output": 30,
                    "total": 130, "reserved_tokens": 120, "unknown_usage": 0,
                    "quota_errors": 1,
                },
                f"{today}/model-b": {
                    "date": today, "requests": 1, "input": 50, "output": 10,
                    "total": 60, "reserved_tokens": 55, "unknown_usage": 1,
                    "quota_errors": 0,
                },
                "yesterday/model-a": {
                    "date": "2000-01-01", "requests": 50, "input": 500,
                    "output": 500, "total": 1000, "reserved_tokens": 500,
                    "unknown_usage": 0, "quota_errors": 0,
                },
            },
            "updated_at": "2026-10-26T12:00:00+00:00",
        }), encoding="utf-8")
        response = self.client.get("/api/usage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.json["requests"], 3)
        self.assertEqual(response.json["input"], 150)
        self.assertEqual(response.json["output"], 40)
        self.assertEqual(response.json["total"], 190)
        self.assertEqual(response.json["quota_errors"], 1)
        self.assertEqual(response.json["unknown_usage"], 1)

    def test_monitor_usage_is_loaded_from_github_state_branch(self):
        remote_state = {
            "usage": {},
            "tenders": {},
            "updated_at": "2026-10-26T12:00:00+00:00",
        }
        response = unittest.mock.MagicMock(status_code=200)
        response.text = json.dumps(remote_state)
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(dashboard.requests, "request", return_value=response) as api:
            state = dashboard.load_monitor_state(force_refresh=True)
        self.assertEqual(state, remote_state)
        self.assertEqual(
            api.call_args.args[1],
            "https://api.github.com/repos/owner/repository/contents/"
            "state.json?ref=monitor-state",
        )
        self.assertEqual(
            api.call_args.kwargs["headers"]["Accept"],
            "application/vnd.github.raw+json",
        )

    def test_monitor_reads_the_actions_config_variable(self):
        config = {**dashboard.default_config(), "gemini_model": "configured-model"}
        with patch.dict(os.environ, {"MONITOR_CONFIG": json.dumps(config)}):
            self.assertEqual(load_config()["gemini_model"], "configured-model")

    def test_github_config_variable_is_created_when_not_yet_present(self):
        config = dashboard.default_config()
        missing = unittest.mock.MagicMock(status_code=404)
        created = unittest.mock.MagicMock(status_code=201)
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard.requests,
            "request",
            side_effect=[missing, created],
        ) as api:
            dashboard.save_monitor_config(config, None)
        self.assertEqual(api.call_args.args[0], "POST")
        self.assertEqual(api.call_args.kwargs["json"]["name"], "MONITOR_CONFIG")

    def test_actions_secrets_are_encrypted_for_github_and_not_returned(self):
        private_key = PrivateKey.generate()
        public_key = base64.b64encode(bytes(private_key.public_key)).decode("ascii")
        public_key_response = unittest.mock.MagicMock(
            status_code=200,
        )
        public_key_response.json.return_value = {
            "key": public_key,
            "key_id": "key-id",
        }
        save_response = unittest.mock.MagicMock(status_code=204)
        secret_value = "test-secret-value"
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
        }), patch.object(
            dashboard.requests,
            "request",
            side_effect=[public_key_response, save_response],
        ) as api:
            saved = dashboard.save_github_secrets({"GEMINI_API_KEY": secret_value})
        self.assertEqual(saved, ["GEMINI_API_KEY"])
        payload = api.call_args.kwargs["json"]
        encrypted = base64.b64decode(payload["encrypted_value"])
        self.assertEqual(
            SealedBox(private_key).decrypt(encrypted).decode("utf-8"),
            secret_value,
        )
        self.assertNotIn(secret_value, json.dumps(payload))


if __name__ == "__main__":
    unittest.main()

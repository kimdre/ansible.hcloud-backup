"""Run the role against a local HTTP API. No Hetzner account is needed."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "offline-test-token"


def snapshot(image_id, created, server_id=1, server_name="old-server-name"):
    return {
        "id": image_id,
        "created": created,
        "created_from": {"id": server_id, "name": server_name},
    }


class MockAPI:
    def __init__(self):
        self.requests = []
        self.pages = {1: []}
        self.last_page = 1
        self.statuses = ["success"]
        self.progress = 100
        self.backup_window = "22-02"
        self.failures = {}
        self.failed_page = None

    def handle(self, method, target, body):
        parsed = urlsplit(target)
        path = parsed.path
        self.requests.append((method, target, body))
        if (method, path) in self.failures:
            return self.failures[method, path]
        if method == "POST" and path == "/v1/servers/1/actions/create_image":
            return 201, {"action": {"id": 2000}, "image": {"id": 1000}}
        if method == "GET" and path == "/v1/actions/2000":
            status = self.statuses[0]
            if len(self.statuses) > 1:
                self.statuses.pop(0)
            return 200, {
                "action": {
                    "id": 2000,
                    "status": status,
                    "progress": self.progress,
                    "error": {"message": "mock image failure"} if status == "error" else None,
                }
            }
        if method == "GET" and path == "/v1/servers/1":
            return 200, {"server": {"id": 1, "backup_window": self.backup_window}}
        if method == "GET" and path == "/v1/images":
            page = int(parse_qs(parsed.query)["page"][0])
            if page == self.failed_page:
                return 503, {"error": {"message": "snapshot page unavailable"}}
            return 200, {
                "images": self.pages[page],
                "meta": {"pagination": {"last_page": self.last_page}},
            }
        if method == "DELETE" and path.startswith("/v1/images/"):
            return 204, None
        return 404, {"error": {"message": "unexpected API request"}}


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.api = MockAPI()
        api = self.api

        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else None
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    status, payload = 401, {"error": {"message": "invalid test token"}}
                else:
                    status, payload = api.handle(self.command, self.path, body)
                data = json.dumps(payload).encode() if payload is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = handle_request
            do_POST = handle_request
            do_DELETE = handle_request

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        role = self.work / "roles" / "hcloud_backup"
        for directory in ("defaults", "tasks", "meta"):
            shutil.copytree(ROOT / directory, role / directory)
        for file in (role / "tasks").glob("*.yml"):
            file.write_text(file.read_text().replace(
                "https://api.hetzner.cloud", f"http://127.0.0.1:{self.server.server_port}"
            ))
        (self.work / "ansible.cfg").write_text(
            "[defaults]\n"
            f"local_tmp = {self.work / 'local_tmp'}\n"
            f"remote_tmp = {self.work / 'remote_tmp'}\n"
            "retry_files_enabled = false\n"
        )
        self.inventory = self.work / "inventory.json"
        self.inventory.write_text(json.dumps({
            "all": {"hosts": {"inventory-alias": {
                "ansible_connection": "local",
                "ansible_python_interpreter": sys.executable,
            }}}
        }))

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_role(self, variables=None, check=False, runs=None, missing_vars=(), verbose=False):
        defaults = {
            "id": 1,
            "delegation": "localhost",
            "api_token": TOKEN,
            "backup_check_delay": 0,
            "backup_check_retries": 2,
        }
        defaults.update(variables or {})
        for name in missing_vars:
            defaults.pop(name)
        tasks = [
            {"name": "Run backup role", "ansible.builtin.include_role": {
                "name": "hcloud_backup"
            }, "vars": overrides}
            for overrides in (runs or [{}])
        ]
        playbook = self.work / "playbook.json"
        playbook.write_text(json.dumps([{
            "name": "Offline role regression",
            "hosts": "all",
            "gather_facts": False,
            "vars": defaults,
            "tasks": tasks,
        }]))
        env = os.environ.copy()
        env.update({
            "ANSIBLE_CONFIG": str(self.work / "ansible.cfg"),
            "ANSIBLE_NOCOLOR": "1",
            "HCLOUD_TOKEN": "",
        })
        command = ["ansible-playbook", "-i", str(self.inventory), str(playbook)]
        if check:
            command.append("--check")
        if verbose:
            command.append("-vvv")
        result = subprocess.run(
            command, cwd=self.work, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90,
        )
        self.assertNotIn(TOKEN, result.stdout)
        return result

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def assert_failure(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.deleted_ids(), [], result.stdout)

    def deleted_ids(self):
        return [
            int(urlsplit(target).path.rsplit("/", 1)[1])
            for method, target, _body in self.api.requests if method == "DELETE"
        ]

    def test_json_description_and_empty_snapshot_list(self):
        description = 'A "quoted" description\nwith a \\backslash'
        result = self.run_role({"backup_description": description})
        self.assert_success(result)
        self.assertEqual(self.api.requests[0][2]["description"], description)
        self.assertRegex(result.stdout, r"changed=1\b")
        self.assertEqual(len(self.api.requests), 3)

    def test_rotation_sorts_dates_and_matches_server_id(self):
        self.api.pages[1] = [
            snapshot(1000, "2026-11-13T20:00:00Z"),
            snapshot(900, "2020-01-01T00:00:00Z", server_id=2, server_name="inventory-alias"),
            {"id": 901, "created": "2020-01-01T00:00:00Z", "created_from": None},
            snapshot(12, "2026-11-12T20:00:00Z"),
            snapshot(11, "2026-11-11T20:00:00Z"),
        ]
        result = self.run_role({"keep_snapshots": 2, "id": "1"})
        self.assert_success(result)
        self.assertEqual(self.deleted_ids(), [11])
        self.assertRegex(result.stdout, r"changed=2\b")

    def test_rotation_gathers_all_pages_once(self):
        self.api.last_page = 2
        self.api.pages = {
            1: [snapshot(1000, "2026-11-13T20:00:00Z")],
            2: [snapshot(12, "2026-11-12T20:00:00Z"), snapshot(11, "2026-11-11T20:00:00Z")],
        }
        self.assert_success(self.run_role({"keep_snapshots": 1}))
        self.assertEqual(self.deleted_ids(), [11, 12])
        pages = [
            parse_qs(urlsplit(target).query)["page"][0]
            for method, target, _body in self.api.requests
            if method == "GET" and urlsplit(target).path == "/v1/images"
        ]
        self.assertEqual(pages, ["1", "2"])

    def test_maximum_retention_keeps_exactly_forty_snapshots(self):
        self.api.pages[1] = [
            snapshot(index, f"2026-11-13T00:{index:02d}:00Z") for index in range(1, 42)
        ] + [snapshot(1000, "2026-11-13T20:00:00Z")]
        self.assert_success(self.run_role({"keep_snapshots": 40}))
        self.assertEqual(self.deleted_ids(), [1, 2])

    def test_empty_page_with_null_last_page(self):
        self.api.last_page = None
        self.assert_success(self.run_role())
        self.assertEqual(self.deleted_ids(), [])

    def test_repeated_role_does_not_reuse_deletion_list(self):
        self.api.pages[1] = [
            snapshot(1000, "2026-11-13T20:00:00Z"),
            snapshot(11, "2026-11-11T20:00:00Z"),
        ]
        result = self.run_role(runs=[{"keep_snapshots": 1}, {"keep_snapshots": 5}])
        self.assert_success(result)
        self.assertEqual(self.deleted_ids(), [11])

    def test_polling_uses_status_not_progress(self):
        self.api.statuses = ["running", "success"]
        result = self.run_role({"rotate_snapshots": False})
        self.assert_success(result)
        polls = [target for method, target, _body in self.api.requests if "/actions/2000" in target]
        self.assertEqual(polls, ["/v1/actions/2000", "/v1/actions/2000"])

    def test_action_error_stops_before_rotation(self):
        self.api.statuses = ["error"]
        result = self.run_role()
        self.assert_failure(result)
        self.assertIn("mock image failure", result.stdout)
        self.assertEqual(len(self.api.requests), 2)

    def test_running_action_exhausts_retries(self):
        self.api.statuses = ["running"]
        result = self.run_role()
        self.assert_failure(result)
        self.assertFalse(any("/v1/images" in target for _method, target, _body in self.api.requests))

    def test_http_failures_stop_before_deletion(self):
        for method, path in [
            ("POST", "/v1/servers/1/actions/create_image"),
            ("GET", "/v1/actions/2000"),
            ("GET", "/v1/images"),
        ]:
            with self.subTest(method=method, path=path):
                self.api.requests.clear()
                self.api.failures = {(method, path): (503, {"error": {"message": "API unavailable"}})}
                result = self.run_role()
                self.assert_failure(result)
                self.assertIn("API unavailable", result.stdout)
                self.assertIn("HTTP 503", result.stdout)

    def test_failed_remaining_page_does_not_delete(self):
        self.api.last_page = 2
        self.api.failed_page = 2
        self.api.pages[1] = [snapshot(11, "2026-11-11T20:00:00Z")]
        self.assert_failure(self.run_role({"keep_snapshots": 1}))

    def test_missing_pagination_does_not_delete(self):
        self.api.failures = {("GET", "/v1/images"): (200, {"images": []})}
        result = self.run_role()
        self.assert_failure(result)
        self.assertIn("valid pagination metadata", result.stdout)

    def test_api_error_message_redacts_token(self):
        self.api.failures = {
            ("POST", "/v1/servers/1/actions/create_image"):
                (403, {"error": {"message": f"denied {TOKEN}"}})
        }
        result = self.run_role(verbose=True)
        self.assert_failure(result)
        self.assertIn("denied [redacted]", result.stdout)

    def test_action_error_message_redacts_token(self):
        self.api.failures = {("GET", "/v1/actions/2000"): (200, {
            "action": {"status": "error", "error": {"message": f"image failure {TOKEN}"}}
        })}
        result = self.run_role(verbose=True)
        self.assert_failure(result)
        self.assertIn("image failure [redacted]", result.stdout)

    def test_successful_http_response_without_action_fails(self):
        self.api.failures = {("GET", "/v1/actions/2000"): (200, {})}
        self.assert_failure(self.run_role())

    def test_disabled_backups_use_server_id_and_stop(self):
        self.api.backup_window = None
        result = self.run_role({"backup_type": "backup"})
        self.assert_failure(result)
        self.assertIn("Backups are not enabled", result.stdout)
        self.assertEqual(self.api.requests, [("GET", "/v1/servers/1", None)])

    def test_backup_server_http_error_is_not_ignored(self):
        self.api.failures = {("GET", "/v1/servers/1"): (404, {"error": {"message": "server missing"}})}
        self.assert_failure(self.run_role({"backup_type": "backup"}))
        self.assertEqual(len(self.api.requests), 1)

    def test_backup_does_not_rotate(self):
        result = self.run_role({"backup_type": "backup"})
        self.assert_success(result)
        self.assertEqual(len(self.api.requests), 3)
        self.assertEqual(self.api.requests[1][2]["type"], "backup")

    def test_empty_label_value_is_supported(self):
        result = self.run_role({"backup_labels": {"rotate": "", "keep": "yes"}, "label_selector": {"keep": "yes"}})
        self.assert_success(result)
        self.assertEqual(self.api.requests[0][2]["labels"], {"rotate": "", "keep": "yes"})
        selector = parse_qs(urlsplit(self.api.requests[-1][1]).query)["label_selector"][0]
        self.assertEqual(selector, "keep=yes")

    def test_prefixed_label_key_is_supported(self):
        labels = {"example.com/rotate": "true", "host": "web-1"}
        result = self.run_role({"backup_labels": labels, "label_selector": labels})
        self.assert_success(result)
        self.assertEqual(self.api.requests[0][2]["labels"], labels)
        selector = parse_qs(urlsplit(self.api.requests[-1][1]).query)["label_selector"][0]
        self.assertEqual(selector, "example.com/rotate=true,host=web-1")

    def test_unused_selector_is_not_validated(self):
        result = self.run_role({"rotate_snapshots": False, "label_selector": {}})
        self.assert_success(result)
        self.assertEqual(len(self.api.requests), 2)

    def test_invalid_variables_fail_before_api_calls(self):
        for variables in [
            {"id": None}, {"id": True}, {"id": 0}, {"id": "invalid"}, {"id": "1\n"},
            {"backup_type": "invalid"}, {"backup_description": []},
            {"rotate_snapshots": "false"}, {"keep_snapshots": True},
            {"keep_snapshots": 0}, {"keep_snapshots": 41},
            {"backup_check_retries": True}, {"backup_check_delay": -1},
            {"backup_labels": []}, {"backup_labels": {"bad": 1}},
            {"backup_labels": {"bad label": "value"}},
            {"backup_labels": {"label\n": "value"}},
            {"backup_labels": {"label": "value\n"}},
            {"backup_labels": {"x" * 64: "value"}},
            {"backup_labels": {"label": "x" * 64}},
            {"backup_labels": {"label": "-value"}}, {"backup_labels": {"label": "value."}},
            {"backup_labels": {"-key": "value"}}, {"backup_labels": {"/key": "value"}},
            {"backup_labels": {"hetzner.cloud/key": "value"}},
            {"backup_labels": {"bad_prefix/key": "value"}},
            {"backup_labels": {"example.com/": "value"}},
            {"backup_labels": {("a" * 63 + ".") * 4 + "a/key": "value"}},
            {"backup_labels": {"rotate": ""}, "label_selector": {"rotate": ""}},
            {"label_selector": []}, {"label_selector": {}},
            {"label_selector": {"missing": "label"}},
            {"label_selector": {"rotation": "false"}},
            {"api_token": ""}, {"api_token": "   "},
        ]:
            with self.subTest(variables=variables):
                self.assert_failure(self.run_role(variables))
                self.assertEqual(self.api.requests, [])

    def test_missing_server_id_or_token_fails_before_api_calls(self):
        for name in ["id", "api_token"]:
            with self.subTest(name=name):
                result = self.run_role(missing_vars=[name])
                self.assert_failure(result)
                self.assertEqual(self.api.requests, [])
                self.assertIn("positive Hetzner Cloud server ID" if name == "id" else "nonempty string", result.stdout)

    def test_check_mode_validates_without_api_calls(self):
        for backup_type in ["snapshot", "backup"]:
            with self.subTest(backup_type=backup_type):
                result = self.run_role({"backup_type": backup_type}, check=True)
                self.assert_success(result)
                self.assertEqual(self.api.requests, [])
                self.assertRegex(result.stdout, r"changed=0\b")
        self.assert_failure(self.run_role({"keep_snapshots": 0}, check=True))


if __name__ == "__main__":
    unittest.main()

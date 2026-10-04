from textwrap import dedent

from pr_reviewer.context.builder import RepositoryContextBuilder
from pr_reviewer.review.javascript_deep_static_analyzer import JavaScriptDeepStaticAnalyzer
from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def changed(source: str, path: str = "src/example.js") -> ChangedFile:
    content = dedent(source).strip()
    return ChangedFile(
        file_path=path,
        status="added",
        full_content=content,
        changed_lines=[
            ChangedLine(path, number, line, number)
            for number, line in enumerate(content.splitlines(), 1)
        ],
    )


def rules(source: str, path: str = "src/example.js") -> list[str]:
    return [finding.rule_id for finding in JavaScriptDeepStaticAnalyzer().analyze(changed(source, path))]


def test_fetch_status_and_deadline_require_concrete_absence():
    unsafe = """
        export async function load(apiUrl) {
          const response = await fetch(apiUrl);
          return response.json();
        }
    """
    assert rules(unsafe) == ["fetch-status-not-checked", "missing-timeout"]

    safe = """
        export async function load(apiUrl, signal) {
          const response = await fetch(apiUrl, { signal });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        }
    """
    assert rules(safe) == []


def test_fixed_same_origin_fetch_does_not_require_independent_timeout():
    source = """
        export async function create(body) {
          const response = await fetch('/api/items', { method: 'POST', body });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        }
    """
    assert rules(source) == []


def test_browser_dom_navigation_messaging_and_storage_boundaries():
    source = """
        export function update(message, nextUrl, token, payload) {
          const output = document.getElementById('output');
          output.innerHTML = message;
          window.location.href = nextUrl;
          window.parent.postMessage(payload, '*');
          localStorage.setItem('sessionToken', token);
        }
    """
    found = StaticAnalyzer().analyze(changed(source, "browser/dom.js"))
    assert {(item.line_number, item.rule_id) for item in found} == {
        (3, "unsafe-inner-html"), (3, "null-safety"),
        (4, "open-redirect"), (5, "wildcard-postmessage"),
        (6, "browser-token-storage"),
    }


def test_guarded_dom_and_trusted_browser_controls_are_safe():
    source = """
        export function update(message, destination, payload) {
          const output = document.getElementById('output');
          if (!(output instanceof HTMLElement)) throw new Error('missing output');
          output.textContent = String(message);
          if (destination.origin !== window.location.origin) throw new Error('origin');
          window.location.assign(destination);
          window.parent.postMessage(payload, 'https://portal.example.test');
        }
    """
    assert rules(source, "browser/dom-safe.js") == []


def test_node_security_sinks_and_safe_controls():
    unsafe = """
        export function run(database, email, host, root, name, request, logger, password) {
          database.query("SELECT * FROM users WHERE email='" + email + "'");
          exec('ping ' + host);
          path.join(root, name);
          if (request.headers['x-role']) removeUser();
          logger.info('login', { password });
        }
        export function createResetCode() { return Math.random().toString(36); }
    """
    assert set(rules(unsafe, "node/backend.js")) == {
        "sql-injection", "command-injection", "path-traversal", "authorization",
        "sensitive-data-logging", "predictable-random-token",
    }

    safe = """
        export function find(database, email) {
          return database.query('SELECT * FROM users WHERE email=?', [email]);
        }
        export function file(root, name) {
          const base = path.resolve(root);
          const candidate = path.resolve(base, name);
          if (!candidate.startsWith(`${base}${path.sep}`)) throw new Error('outside');
          return candidate;
        }
        export function token() { return randomBytes(32).toString('base64url'); }
    """
    assert rules(safe, "node/backend-safe.js") == []


def test_listener_and_promise_ownership_with_abort_signal_controls():
    unsafe = """
        export function register(input, search) {
          input.addEventListener('input', async () => {
            await search(input.value);
          });
          load().then(render);
        }
    """
    assert set(rules(unsafe, "lifecycle/unsafe.js")) == {
        "listener-cleanup", "async-issue",
    }
    assert rules(unsafe, "lifecycle/unsafe.js").count("async-issue") == 2

    safe = """
        export function register(input, search) {
          const controller = new AbortController();
          const onInput = async () => {
            try { await search(input.value, controller.signal); }
            catch (error) { if (error.name !== 'AbortError') throw error; }
          };
          input.addEventListener('input', onInput, { signal: controller.signal });
          return () => controller.abort();
        }
    """
    assert rules(safe, "lifecycle/safe.js") == []


def test_page_lifetime_element_listeners_do_not_require_manual_cleanup():
    source = """
        document.addEventListener('DOMContentLoaded', () => {
          const login = document.getElementById('login');
          login.addEventListener('click', submitLogin);
          document.querySelectorAll('.toggle').forEach((button) => {
            button.addEventListener('click', togglePassword);
          });
        });
    """
    assert "listener-cleanup" not in rules(source, "browser/page.js")


def test_reusable_mount_function_requires_listener_ownership():
    source = """
        export function mountDialog(button) {
          button.addEventListener('click', openDialog);
        }
    """
    assert rules(source, "browser/dialog.js") == ["listener-cleanup"]


def test_weak_javascript_assertions_are_precisely_targeted():
    source = """
        test('email', () => {
          const result = readEmail();
          assert.ok(result);
        });
        test('redirect', () => {
          const result = continueTo('https://attacker.example');
          assert.equal(result, undefined);
        });
        test('count', () => assert.equal(count(), 3));
    """
    found = rules(source, "tests/browser.test.js")
    assert found == ["insufficient-test-assertion", "insufficient-test-assertion"]


def test_deep_rules_respect_changed_line_ownership():
    file = changed("window.parent.postMessage(payload, '*');", "browser/message.js")
    file.changed_lines = []
    assert JavaScriptDeepStaticAnalyzer().analyze(file) == []


def test_browser_and_node_files_receive_distinct_context():
    files = [
        changed("document.title = 'Browser';", "browser/app.js"),
        changed("import fs from 'node:fs';", "node/server.js"),
        changed('{"type":"module"}', "package.json"),
    ]
    context = RepositoryContextBuilder().build(files)
    assert context.framework == "mixed"
    assert context.project_type == "mixed"
    assert context.resolve_file_context("browser/app.js").framework == "browser-javascript"
    assert context.resolve_file_context("browser/app.js").project_type == "frontend-web"
    assert context.resolve_file_context("node/server.js").framework == "node"
    assert context.resolve_file_context("node/server.js").project_type == "backend"

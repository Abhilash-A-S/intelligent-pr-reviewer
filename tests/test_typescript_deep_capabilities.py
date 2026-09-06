from textwrap import dedent

from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, FindingSource, Severity
from pr_reviewer.review.static_analyzer import StaticAnalyzer
from pr_reviewer.review.finding_validator import FindingValidator


def changed(source: str, path: str = "src/review.ts") -> ChangedFile:
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


def rules(source: str) -> list[str]:
    return [finding.rule_id for finding in StaticAnalyzer().analyze(changed(source))]


def test_nullable_and_optional_values_require_narrowing():
    unsafe = """
        type User = { email?: string };
        function name(user: User | null): string { return user.email.length.toString(); }
        function discount(amount: number, value?: number): number { return amount - value; }
    """
    found = rules(unsafe)
    assert "typescript-null-dereference" in found
    assert "typescript-optional-property" in found
    assert "typescript-optional-operand" in found

    safe = """
        type User = { email?: string };
        function name(user: User | null): string {
          if (!user) return 'unknown';
          return (user.email ?? '').length.toString();
        }
        function discount(amount: number, value: number = 0): number { return amount - value; }
    """
    assert not set(rules(safe)).intersection({
        "typescript-null-dereference", "typescript-optional-property",
        "typescript-optional-operand",
    })


def test_find_and_array_index_non_optional_contracts_are_detected():
    unsafe = """
        type User = { id: number };
        function find(users: User[], id: number): User { return users.find(user => user.id === id); }
        function first(users: User[]): User { return users[0]; }
    """
    assert rules(unsafe).count("typescript-possibly-undefined-result") == 2

    safe = """
        type User = { id: number };
        function find(users: User[], id: number): User | undefined { return users.find(user => user.id === id); }
        function first(users: User[]): User | undefined { return users[0]; }
    """
    assert "typescript-possibly-undefined-result" not in rules(safe)


def test_definite_assignment_is_control_flow_aware():
    unsafe = """
        function counter(): () => number {
          let count: number;
          return () => ++count;
        }
        function result(active: boolean): number {
          let value: number;
          if (active) value = 1;
          return value;
        }
    """
    assert rules(unsafe).count("typescript-use-before-assignment") == 2

    safe = """
        function counter(): () => number {
          let count: number = 0;
          return () => ++count;
        }
        function result(active: boolean): number {
          let value: number = 0;
          if (active) value = 1;
          return value;
        }
    """
    assert "typescript-use-before-assignment" not in rules(safe)


def test_unknown_assertions_object_index_and_function_type_are_detected():
    unsafe = """
        function number(value: unknown): number { return value as number; }
        function property(object: object, key: string): unknown { return object[key]; }
        function execute(callback: Function): void { callback(); }
    """
    assert set(rules(unsafe)) == {
        "unsafe-type-assertion", "unsafe-indexed-access", "broad-function-type",
    }

    safe = """
        function number(value: unknown): number {
          if (typeof value !== 'number') throw new TypeError('number required');
          return value;
        }
        function property(object: Record<string, unknown>, key: string): unknown { return object[key]; }
        function execute(callback: () => void): void { callback(); }
    """
    assert not set(rules(safe)).intersection({
        "unsafe-type-assertion", "unsafe-indexed-access", "broad-function-type",
    })


def test_error_promise_and_timer_ownership_controls():
    unsafe = """
        function fail(): never { throw 'failed'; }
        function launch(): void { Promise.reject(new Error('failed')); }
        class Worker {
          private timer?: ReturnType<typeof setInterval>;
          start(): void { this.timer = setInterval(work, 1000); }
        }
    """
    found = rules(unsafe)
    assert "non-error-throw" in found
    assert "unobserved-promise-rejection" in found
    assert "timer-without-cleanup" in found
    assert "setinterval-without-timer-reference" not in found

    safe = """
        function fail(): never { throw new Error('failed'); }
        function launch(): Promise<never> { return Promise.reject(new Error('failed')); }
        class Worker {
          private timer?: ReturnType<typeof setInterval>;
          start(): void { this.timer = setInterval(work, 1000); }
          stop(): void { if (this.timer) clearInterval(this.timer); }
        }
    """
    assert not set(rules(safe)).intersection({
        "non-error-throw", "unobserved-promise-rejection", "timer-without-cleanup",
        "setinterval-without-timer-reference",
    })


def test_ai_cannot_transfer_a_named_function_defect_to_another_function():
    source = changed("""
        function status(): string {
          return 'active';
          console.log('unreachable');
        }
        function counter(): number {
          let count = 0;
          count++;
          return count;
        }
    """)
    finding = Finding(
        file_path=source.file_path,
        line_number=7,
        severity=Severity.MEDIUM,
        rule_id="logic-error",
        message="The function `status` contains a statement after return.",
        suggestion="Remove the unreachable statement.",
        source=FindingSource.LLM,
    )

    result = FindingValidator().validate(finding, source)

    assert not result.accepted
    assert any("does not belong" in reason for reason in result.reasons)


def test_nested_tuple_parameter_is_not_split_into_fake_unused_parameters():
    source = """
        type User = { id: number };
        function first(users: readonly [User, ...User[]]): User { return users[0]; }
        function map(entries: Map<string, User>, callback: (value: User, index: number) => User): void {
          entries.forEach((value) => callback(value, 0));
        }
    """
    found = StaticAnalyzer().analyze(changed(source))
    assert not any(f.rule_id == "unused-parameter" for f in found)
    assert "typescript-possibly-undefined-result" not in [f.rule_id for f in found]


def test_assertion_chain_and_unvalidated_response_are_detected_with_safe_controls():
    unsafe = """
        type User = { id: number };
        function force(value: object): User { return value as unknown as User; }
        async function load(): Promise<User[]> {
          const response = await fetch('/users');
          if (!response.ok) throw new Error('failed');
          return response.json();
        }
    """
    found = rules(unsafe)
    assert "unsafe-type-assertion" in found
    assert "unvalidated-external-data" in found

    safe = """
        type User = { id: number };
        function isUser(value: unknown): value is User {
          return typeof value === 'object' && value !== null && 'id' in value;
        }
        async function load(): Promise<User[]> {
          const response = await fetch('/users');
          if (!response.ok) throw new Error('failed');
          const value: unknown = await response.json();
          if (!Array.isArray(value) || !value.every(isUser)) throw new TypeError('invalid');
          return value;
        }
    """
    assert not set(rules(safe)).intersection({"unsafe-type-assertion", "unvalidated-external-data"})


def test_timer_cleanup_is_scoped_to_the_owning_class():
    source = """
        class UnsafeWorker {
          private timer?: ReturnType<typeof setInterval>;
          start(): void { this.timer = setInterval(work, 1000); }
        }
        class SafeWorker {
          private timer?: ReturnType<typeof setInterval>;
          start(): void { this.timer = setInterval(work, 1000); }
          stop(): void { if (this.timer) clearInterval(this.timer); }
        }
    """
    timer_findings = [f for f in StaticAnalyzer().analyze(changed(source)) if f.rule_id == "timer-without-cleanup"]
    assert len(timer_findings) == 1
    assert timer_findings[0].line_number == 3


def test_async_loop_and_observer_ownership_have_safe_controls():
    unsafe = """
        async function load(ids: number[]): Promise<void> {
          for (const id of ids) {
            await fetch(`/users/${id}`);
          }
        }
        function watch(element: Element): MutationObserver {
          const observer = new MutationObserver(refresh);
          observer.observe(element, { childList: true });
          return observer;
        }
    """
    found = rules(unsafe)
    assert "sequential-await-in-loop" in found
    assert "observer-without-cleanup" in found

    safe = """
        async function load(ids: number[]): Promise<void> {
          await Promise.all(ids.map(id => fetch(`/users/${id}`)));
        }
        function watch(element: Element): () => void {
          const observer = new MutationObserver(refresh);
          observer.observe(element, { childList: true });
          return () => observer.disconnect();
        }
    """
    assert not set(rules(safe)).intersection({"sequential-await-in-loop", "observer-without-cleanup"})


def test_prototype_condition_and_union_rules_have_safe_controls():
    unsafe = """
        type Role = 'admin' | 'editor' | 'viewer';
        function assign(key: string, value: unknown): object {
          const output: Record<string, unknown> = {};
          output[key] = value;
          return output;
        }
        function allowed(role: Role): boolean {
          if (role === 'admin' || 'editor') return true;
          return false;
        }
        function label(role: Role): string {
          switch (role) {
            case 'admin': return 'Admin';
            case 'editor': return 'Editor';
          }
          return 'Unknown';
        }
    """
    found = rules(unsafe)
    assert "prototype-pollution" in found
    assert "always-truthy-condition" in found
    assert "non-exhaustive-union" in found

    safe = """
        type Role = 'admin' | 'editor' | 'viewer';
        function assign(key: string, value: unknown): object {
          if (key === '__proto__' || key === 'prototype' || key === 'constructor') throw new Error('key');
          const output: Record<string, unknown> = Object.create(null);
          output[key] = value;
          return output;
        }
        function allowed(role: Role): boolean { return role === 'admin' || role === 'editor'; }
        function assertNever(value: never): never { throw new Error(String(value)); }
        function label(role: Role): string {
          switch (role) {
            case 'admin': return 'Admin';
            case 'editor': return 'Editor';
            case 'viewer': return 'Viewer';
            default: return assertNever(role);
          }
        }
    """
    assert not set(rules(safe)).intersection({
        "prototype-pollution", "always-truthy-condition", "non-exhaustive-union",
    })

from pr_reviewer.review.deduplicator import FindingDeduplicator
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.normalizer import FindingNormalizer
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def changed_file(path: str, content: str) -> ChangedFile:
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(
                file_path=path,
                line_number=index,
                content=line,
                diff_position=index,
            )
            for index, line in enumerate(content.splitlines(), start=1)
        ],
        full_content=content,
    )


def rules(findings):
    return [finding.rule_id for finding in findings]


def test_react_detects_missing_effect_dependencies_and_cleanup():
    content = """import React, { useEffect, useState } from 'react';

function App() {
  const [count, setCount] = useState(0);
  const [userId, setUserId] = useState(1);

  useEffect(() => {
    const timer = setInterval(() => {
      console.log(userId);
    }, 1000);
  }, []);

  useEffect(() => {
    console.log(count);
  }, []);

  return <button onClick={() => setCount(count + 1)}>{userId}</button>;
}
"""
    findings = StaticAnalyzer().analyze(changed_file("src/App.js", content))

    dependencies = [f for f in findings if f.rule_id == "effect-dependency"]
    cleanup = [f for f in findings if f.rule_id == "effect-cleanup"]

    assert {"count", "userId"} == {
        name
        for finding in dependencies
        for name in ("count", "userId")
        if f"'{name}'" in finding.message
    }
    assert len(cleanup) == 1
    assert cleanup[0].severity == Severity.HIGH


def test_react_effect_with_dependencies_and_cleanup_is_clean():
    content = """import React, { useEffect, useState } from 'react';

function App() {
  const [userId] = useState(1);

  useEffect(() => {
    const timer = setInterval(() => {
      console.log(userId);
    }, 1000);

    return () => clearInterval(timer);
  }, [userId]);

  return <div>{userId}</div>;
}
"""
    findings = StaticAnalyzer().analyze(changed_file("src/App.jsx", content))

    assert "effect-dependency" not in rules(findings)
    assert "effect-cleanup" not in rules(findings)


def test_react_direct_dom_arrow_unused_parameter_listener_and_fetch_status():
    content = """import React from 'react';

function App() {
  const loadUser = async () => {
    const response = await fetch('/users/1');
    const data = await response.json();
    console.log(data);
  };

  const updateHtml = () => {
    const element = document.getElementById('content');
    if (element) element.innerHTML = '<b>test</b>';
  };

  const greetUser = (name, title) => {
    return `Hello ${name}`;
  };

  const addListener = () => {
    window.addEventListener('resize', () => console.log('resize'));
  };

  return <div onClick={updateHtml}>{greetUser('A', 'Mr')}</div>;
}
"""
    findings = StaticAnalyzer().analyze(changed_file("src/App.js", content))

    assert "direct-dom-manipulation" in rules(findings)
    assert "fetch-status-not-checked" in rules(findings)
    assert "global-event-listener-without-removal" in rules(findings)
    assert any(
        f.rule_id == "unused-parameter" and "'title'" in f.message
        for f in findings
    )


def test_plain_javascript_dom_query_is_not_a_react_finding():
    content = """function update() {
  const element = document.getElementById('content');
  element.textContent = 'ok';
}
update();
"""
    findings = StaticAnalyzer().analyze(changed_file("script.js", content))
    assert "direct-dom-manipulation" not in rules(findings)


def test_xss_alias_deduplicates_with_unsafe_inner_html():
    normalizer = FindingNormalizer()
    deduplicator = FindingDeduplicator()

    static = Finding(
        file_path="src/App.js",
        line_number=37,
        severity=Severity.HIGH,
        rule_id="unsafe-inner-html",
        message="A value is assigned through innerHTML.",
    )
    ai = Finding(
        file_path="src/App.js",
        line_number=39,
        severity=Severity.HIGH,
        rule_id="xss-vulnerability",
        message="HTML is rendered without sanitization and can lead to XSS.",
    )

    normalized = [normalizer.normalize(static), normalizer.normalize(ai)]
    result = deduplicator.deduplicate(normalized)

    assert len(result) == 1
    assert result[0].rule_id == "unsafe-inner-html"


def test_missing_cleanup_alias_normalizes_to_effect_cleanup():
    normalizer = FindingNormalizer()
    assert normalizer.normalize_rule_id("missing-cleanup") == "effect-cleanup"


def test_react_timer_handle_is_not_reported_as_unused_when_cleanup_is_the_real_issue():
    content = """import React, { useEffect } from 'react';

function App() {
  useEffect(() => {
    const timer = setInterval(() => console.log('tick'), 1000);
  }, []);
  return <div />;
}
"""
    findings = StaticAnalyzer().analyze(changed_file("src/App.js", content))
    assert not any(
        f.rule_id == "unused-variable" and "'timer'" in f.message
        for f in findings
    )
    assert any(f.rule_id == "effect-cleanup" for f in findings)


def test_effect_cleanup_ai_anchor_inside_same_effect_deduplicates_with_static_anchor():
    content = """import React, { useEffect } from 'react';
function App() {
  useEffect(() => {
    const timer = setInterval(() => {
      console.log('tick');
    }, 1000);
  }, []);
  return <div />;
}
"""
    file = changed_file("src/App.js", content)
    normalizer = FindingNormalizer()
    deduplicator = FindingDeduplicator()
    static = Finding(
        file_path="src/App.js",
        line_number=3,
        severity=Severity.HIGH,
        rule_id="effect-cleanup",
        message="React effect starts setInterval but does not provide matching cleanup.",
    )
    ai = Finding(
        file_path="src/App.js",
        line_number=7,
        severity=Severity.HIGH,
        rule_id="missing-cleanup",
        message="The useEffect hook has a missing cleanup function.",
    )
    result = deduplicator.deduplicate(
        [normalizer.normalize(static), normalizer.normalize(ai)],
        changed_files=[file],
    )
    assert len(result) == 1
    assert result[0].rule_id == "effect-cleanup"


def test_separate_effect_cleanup_issues_do_not_deduplicate():
    content = """import React, { useEffect } from 'react';
function App() {
  useEffect(() => {
    setInterval(() => console.log('a'), 1000);
  }, []);
  useEffect(() => {
    setInterval(() => console.log('b'), 1000);
  }, []);
  return <div />;
}
"""
    file = changed_file("src/App.js", content)
    deduplicator = FindingDeduplicator()
    findings = [
        Finding(file_path="src/App.js", line_number=3, severity=Severity.HIGH, rule_id="effect-cleanup", message="first"),
        Finding(file_path="src/App.js", line_number=6, severity=Severity.HIGH, rule_id="effect-cleanup", message="second"),
    ]
    result = deduplicator.deduplicate(findings, changed_files=[file])
    assert len(result) == 2


def test_react_create_root_dom_query_is_valid_bootstrap_not_direct_dom_manipulation():
    content = """import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root')).render(<App />);
"""
    findings = StaticAnalyzer().analyze(changed_file("src/main.jsx", content))
    assert "direct-dom-manipulation" not in rules(findings)


def test_react_multiline_create_root_dom_query_is_valid_bootstrap():
    content = """import React from 'react';
import { createRoot } from 'react-dom/client';

createRoot(
  document.getElementById('root')
).render(<div />);
"""
    findings = StaticAnalyzer().analyze(changed_file("src/main.jsx", content))
    assert "direct-dom-manipulation" not in rules(findings)


def test_react_dom_query_outside_root_bootstrap_is_still_reported():
    content = """import React from 'react';
import { createRoot } from 'react-dom/client';

createRoot(document.getElementById('root')).render(<App />);

function App() {
  const element = document.getElementById('content');
  return <button onClick={() => { element.textContent = 'changed'; }}>Change</button>;
}
"""
    findings = StaticAnalyzer().analyze(changed_file("src/main.jsx", content))
    dom_findings = [f for f in findings if f.rule_id == "direct-dom-manipulation"]
    assert len(dom_findings) == 1
    assert dom_findings[0].line_number == 7


def test_react_hydrate_root_dom_query_is_valid_bootstrap():
    content = """import React from 'react';
import { hydrateRoot } from 'react-dom/client';

hydrateRoot(document.querySelector('#root'), <App />);
"""
    findings = StaticAnalyzer().analyze(changed_file("src/main.jsx", content))
    assert "direct-dom-manipulation" not in rules(findings)

from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, FindingSource, Severity
from pr_reviewer.review.normalizer import FindingNormalizer
from pr_reviewer.review.processor import FindingProcessor


def changed(path: str, numbered_lines: dict[int, str]) -> ChangedFile:
    last = max(numbered_lines)
    full = ["" for _ in range(last)]
    for number, content in numbered_lines.items():
        full[number - 1] = content
    return ChangedFile(
        file_path=path,
        status="modified",
        changed_lines=[
            ChangedLine(path, number, content, number)
            for number, content in numbered_lines.items()
        ],
        full_content="\n".join(full),
    )


def ai(path: str, line: int, rule: str, message: str) -> Finding:
    return Finding(
        file_path=path,
        line_number=line,
        severity=Severity.MEDIUM,
        rule_id=rule,
        message=message,
        suggestion="Correct the proven behavior.",
        source=FindingSource.LLM,
    )


def test_unfamiliar_labels_map_by_universal_defect_concept():
    cases = [
        ("always-report-success", "The update result is ignored and the method always reports success.", "incorrect-result-handling"),
        ("pagination-bug", "The first page uses the wrong start offset and skips records.", "logic-error"),
        ("category-absent-from-cache-key", "The category input is absent from the cache key, returning stale results.", "cache-consistency"),
        ("blocking-operation-in-async-code", "This blocking call stalls the async event loop.", "async-blocking-operation"),
        ("missing-timeout-on-external-request", "The external HTTP request has no timeout.", "missing-timeout"),
        ("weak-test", "The test only checks status and does not verify response behavior.", "insufficient-test-assertion"),
    ]

    for rule, message, expected in cases:
        normalized = FindingNormalizer().normalize(ai("src/file.py", 1, rule, message))
        assert normalized.rule_id == expected


def test_grounded_universal_python_findings_survive_without_python_rule_ids():
    service = changed(
        "src/service.py",
        {
            19: "return self.repository.get(product_id)",
            22: "self.repository.update(product_id, data)",
            29: "start = page * page_size",
            40: "cache_key = query.lower()",
            55: "time.sleep(1)",
            58: 'response = await client.get("https://example.com/rate")',
        },
    )
    test = changed(
        "tests/test_routes.py",
        {17: "assert response.status_code == 200"},
    )
    findings = [
        ai(service.file_path, 19, "return-value-ignored", "The declared Product result can be None and is returned as valid."),
        ai(service.file_path, 22, "always-report-success", "The update result is ignored and the method always reports success."),
        ai(service.file_path, 29, "pagination-bug", "The first page uses the wrong start offset and skips records."),
        ai(service.file_path, 40, "category-absent-from-cache-key", "The category input is absent from the cache key, returning stale results."),
        ai(service.file_path, 55, "blocking-operation-in-async-code", "This blocking operation stalls the async event loop."),
        ai(service.file_path, 58, "missing-timeout-on-external-request", "The external HTTP request has no timeout."),
        ai(test.file_path, 17, "weak-test", "The test only checks status and does not verify response behavior."),
    ]

    results = FindingProcessor().process(findings, [service, test])

    assert {item.rule_id for item in results} == {
        "incorrect-result-handling",
        "logic-error",
        "cache-consistency",
        "async-blocking-operation",
        "missing-timeout",
        "insufficient-test-assertion",
    }


def test_unmappable_clean_control_labels_remain_rejected():
    controls = changed(
        "tests/test_clean.py",
        {
            4: "with pytest.raises(ValueError):",
            9: "await asyncio.sleep(0)",
        },
    )
    findings = [
        ai(controls.file_path, 4, "clean-exception-assertion", "This is a clean exception assertion."),
        ai(controls.file_path, 9, "async-test", "This correctly awaited async test is present."),
    ]

    assert FindingProcessor().process(findings, [controls]) == []

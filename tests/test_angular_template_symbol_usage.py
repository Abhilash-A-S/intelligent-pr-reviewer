from pr_reviewer.review.angular_template_usage import AngularTemplateUsageResolver
from pr_reviewer.review.models import ChangedFile, ChangedLine
from pr_reviewer.review.static_analyzer import StaticAnalyzer


def component_file(template_metadata: str, member: str = "title") -> ChangedFile:
    source = f"""import {{ Component }} from '@angular/core';
@Component({{
  selector: 'app-root',
  {template_metadata}
}})
export class App {{
  protected {member} = 'value';
}}
"""
    return ChangedFile(
        file_path="src/app/app.ts",
        status="modified",
        full_content=source,
        changed_lines=[
            ChangedLine(
                file_path="src/app/app.ts",
                line_number=7,
                content=f"  protected {member} = 'value';",
                diff_position=7,
            )
        ],
    )


def template_file(content: str) -> ChangedFile:
    return ChangedFile(
        file_path="src/app/app.html",
        status="modified",
        full_content=content,
        changed_lines=[],
    )


def unused_rules(files: list[ChangedFile]) -> list[str]:
    return [
        finding.rule_id
        for finding in StaticAnalyzer().analyze_files(files)
        if finding.rule_id == "unused-variable"
    ]


def test_external_interpolation_counts_as_component_member_usage():
    component = component_file("templateUrl: './app.html',")
    template = template_file("<h1>Hello {{ title }}</h1>")
    assert unused_rules([component, template]) == []


def test_legacy_ngif_expression_counts_as_component_member_usage():
    component = component_file("templateUrl: './app.html',", "isVisible")
    template = template_file('<section *ngIf="isVisible">Visible</section>')
    assert unused_rules([component, template]) == []


def test_modern_if_expression_counts_as_component_member_usage():
    component = component_file("templateUrl: './app.html',", "isVisible")
    template = template_file("@if (isVisible) { <section>Visible</section> }")
    assert unused_rules([component, template]) == []


def test_legacy_ngfor_and_modern_for_both_count_as_usage():
    legacy = component_file("templateUrl: './app.html',", "items")
    legacy_template = template_file('<li *ngFor="let item of items">{{ item }}</li>')
    assert unused_rules([legacy, legacy_template]) == []

    modern = component_file("templateUrl: './app.html',", "items")
    modern_template = template_file("@for (item of items; track item.id) { <p>{{ item }}</p> }")
    assert unused_rules([modern, modern_template]) == []


def test_property_and_event_bindings_count_as_usage():
    component = component_file("templateUrl: './app.html',", "username")
    template = template_file('<input [value]="username" />')
    assert unused_rules([component, template]) == []


def test_inline_template_counts_as_usage():
    component = component_file("template: `<h1>{{ title }}</h1>`,")
    assert unused_rules([component]) == []


def test_plain_text_does_not_hide_a_genuinely_unused_member():
    component = component_file("templateUrl: './app.html',")
    template = template_file("<p>The word title is only plain text.</p>")
    assert unused_rules([component, template]) == ["unused-variable"]


def test_related_unchanged_template_context_counts_as_usage():
    component = component_file("templateUrl: './app.html',")
    component.related_file_contents["src/app/app.html"] = "<h1>{{ title }}</h1>"
    assert unused_rules([component]) == []


def test_resolver_understands_switch_defer_and_let_control_flow():
    resolver = AngularTemplateUsageResolver()
    assert resolver._template_uses_symbol("@switch (status) { @case ('ok') {} }", "status")
    assert resolver._template_uses_symbol("@defer (when ready) { <p>Ready</p> }", "ready")
    assert resolver._template_uses_symbol("@let displayName = userName;", "userName")

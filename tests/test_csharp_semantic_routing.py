from textwrap import dedent

from pr_reviewer.review.file_classifier import FileCategory, FileClassifier
from pr_reviewer.review.models import ChangedFile, ChangedLine, Finding, Severity
from pr_reviewer.review.semantic_routing import AdaptiveSemanticRouter, ReviewDepth


def create_file(path: str, content: str) -> ChangedFile:
    content = dedent(content).strip()
    lines = content.splitlines()
    return ChangedFile(
        file_path=path,
        status="modified",
        full_content=content,
        changed_lines=[
            ChangedLine(path, idx, line, idx)
            for idx, line in enumerate(lines, start=1)
        ],
    )


def test_sln_and_build_props_classified_as_context_only_configuration():
    classifier = FileClassifier()

    sln_classification = classifier.classify("App.sln")
    assert sln_classification.category == FileCategory.PROJECT_CONFIGURATION
    assert not sln_classification.reviewable
    assert "context-only" in sln_classification.reason.lower()


def test_csharp_passive_declarations_gated():
    router = AdaptiveSemanticRouter()

    record_file = create_file("src/Models/Product.cs", "public record ProductDto(long Id, string Name);")
    decision = router.decide(record_file, set(), ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "passive" in decision.reason.lower()

    interface_file = create_file("src/Contracts/IUserRepository.cs", "public interface IUserRepository { Task<User> GetByIdAsync(long id); }")
    decision = router.decide(interface_file, set(), ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "passive" in decision.reason.lower()


def test_csharp_non_security_appsettings_and_csproj_gated():
    router = AdaptiveSemanticRouter()

    clean_appsettings = create_file("src/Api/appsettings.json", """
        {
          "Logging": {
            "LogLevel": {
              "Default": "Information"
            }
          },
          "AllowedHosts": "*"
        }
    """)
    decision = router.decide(clean_appsettings, set(), ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "no security-relevant content" in decision.reason.lower()

    csproj_file = create_file("src/Api/Api.csproj", "<Project Sdk=\"Microsoft.NET.Sdk.Web\"></Project>")
    decision = router.decide(csproj_file, set(), ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "no security-relevant content" in decision.reason.lower()


def test_csharp_security_appsettings_retained():
    router = AdaptiveSemanticRouter()

    secret_appsettings = create_file("src/Api/appsettings.json", """
        {
          "JwtSecret": "super-secret-signing-key-12345",
          "ConnectionStrings": {
            "Default": "Server=myServerAddress;Database=myDataBase;User Id=myUsername;Password=myPassword;"
          }
        }
    """)
    decision = router.decide(secret_appsettings, set(), ReviewDepth.STANDARD)
    assert decision.eligible


def test_csharp_construct_covered_by_static_findings_gated():
    router = AdaptiveSemanticRouter()

    source = """
        public class Service(IRepo repo) {
            public async Task<string> ReadAsync(long id) {
                var item = await repo.FindAsync(id);
                return item.Name;
            }
        }
    """
    file = create_file("src/Service.cs", source)
    # Finding on line 4 (return item.Name;)
    decision = router.decide(file, {4}, ReviewDepth.STANDARD)
    assert not decision.eligible
    assert "covered by authoritative static findings" in decision.reason.lower()

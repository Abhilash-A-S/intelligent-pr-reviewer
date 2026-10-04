from dataclasses import dataclass, field

from pr_reviewer.context.models import RepositoryContext
from pr_reviewer.review.framework_facts import (
    AngularFactValidator,
    ExpressFactValidator,
    ReactFactValidator,
)
from pr_reviewer.review.framework_facts.typescript_build import (
    TypeScriptBuildFactValidator,
)
from pr_reviewer.review.framework_facts.javascript_typescript import (
    JavaScriptTypeScriptFactValidator,
)
from pr_reviewer.review.framework_facts.python import PythonRuntimeFactValidator
from pr_reviewer.review.framework_facts.dotnet import DotNetRuntimeFactValidator
from pr_reviewer.review.models import ChangedFile, Finding


@dataclass
class FrameworkFactValidationResult:
    """Result returned by deterministic framework/build fact validation."""

    accepted: bool
    reasons: list[str] = field(default_factory=list)


class FrameworkFactValidator:
    """
    Coordinates deterministic framework/build/runtime fact validators.

    Validators are conservative: a finding is rejected only
    when concrete repository/source evidence contradicts it.
    """

    def __init__(
        self,
        angular_validator: AngularFactValidator | None = None,
        express_validator: ExpressFactValidator | None = None,
        react_validator: ReactFactValidator | None = None,
        typescript_build_validator: TypeScriptBuildFactValidator | None = None,
        javascript_typescript_validator: JavaScriptTypeScriptFactValidator | None = None,
        python_validator: PythonRuntimeFactValidator | None = None,
        dotnet_validator: DotNetRuntimeFactValidator | None = None,
    ):
        self.angular_validator = (
            angular_validator
            or AngularFactValidator()
        )

        self.express_validator = (
            express_validator
            or ExpressFactValidator()
        )

        self.react_validator = (
            react_validator
            or ReactFactValidator()
        )

        self.typescript_build_validator = (
            typescript_build_validator
            or TypeScriptBuildFactValidator()
        )
        self.javascript_typescript_validator = (
            javascript_typescript_validator
            or JavaScriptTypeScriptFactValidator()
        )
        self.python_validator = python_validator or PythonRuntimeFactValidator()
        self.dotnet_validator = dotnet_validator or DotNetRuntimeFactValidator()

    def validate(
        self,
        finding: Finding,
        changed_file: ChangedFile,
        changed_files: list[ChangedFile],
        repository_context: RepositoryContext | None,
    ) -> FrameworkFactValidationResult:
        reasons: list[str] = []

        reasons.extend(
            self.angular_validator.validate(
                finding=finding,
                changed_file=changed_file,
                changed_files=changed_files,
                repository_context=repository_context,
            )
        )

        reasons.extend(
            self.express_validator.validate(
                finding=finding,
                changed_file=changed_file,
                changed_files=changed_files,
                repository_context=repository_context,
            )
        )

        reasons.extend(
            self.react_validator.validate(
                finding=finding,
                changed_file=changed_file,
                changed_files=changed_files,
                repository_context=repository_context,
            )
        )

        reasons.extend(
            self.javascript_typescript_validator.validate(
                finding=finding, changed_file=changed_file, changed_files=changed_files,
                repository_context=repository_context,
            )
        )

        reasons.extend(
            self.typescript_build_validator.validate(
                finding=finding,
                changed_file=changed_file,
                changed_files=changed_files,
                repository_context=repository_context,
            )
        )

        reasons.extend(self.python_validator.validate(finding, changed_file))
        reasons.extend(self.dotnet_validator.validate(finding, changed_file))

        return FrameworkFactValidationResult(
            accepted=not reasons,
            reasons=reasons,
        )

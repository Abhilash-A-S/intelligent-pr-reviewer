from pr_reviewer.detection.language import LanguageDetector


def test_detect_javascript():
    detector = LanguageDetector()

    assert detector.detect("src/app.js") == "javascript"


def test_detect_typescript():
    detector = LanguageDetector()

    assert detector.detect(
        "src/app.component.ts"
    ) == "typescript"


def test_detect_react_typescript():
    detector = LanguageDetector()

    assert detector.detect(
        "src/App.tsx"
    ) == "typescript"


def test_detect_vue():
    detector = LanguageDetector()

    assert detector.detect(
        "src/App.vue"
    ) == "vue"


def test_detect_python():
    detector = LanguageDetector()

    assert detector.detect(
        "src/service.py"
    ) == "python"


def test_detect_java():
    detector = LanguageDetector()

    assert detector.detect(
        "src/UserService.java"
    ) == "java"


def test_detect_csharp():
    detector = LanguageDetector()

    assert detector.detect(
        "src/UserService.cs"
    ) == "csharp"


def test_detect_unknown_language():
    detector = LanguageDetector()

    assert detector.detect(
        "assets/file.custom"
    ) == "unknown"
import importlib
from pathlib import Path
import pytest


PROJECT_ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "relative_path",
    [
        "app.py",
        "requirements.txt",
        "README.md",
        ".streamlit/config.toml",
        "data/stations.csv",
    ],
)
def test_required_project_file_exists(relative_path):
    assert (PROJECT_ROOT / relative_path).is_file()


def test_app_compiles_without_syntax_errors():
    app_path = PROJECT_ROOT / "app.py"
    compile(app_path.read_text(encoding="utf-8"), str(app_path), "exec")


def test_app_imports_without_errors():
    assert importlib.import_module("app") is not None


def test_dashboard_orientation_content(monkeypatch):
    app = importlib.import_module("app")
    rendered_markdown = []

    monkeypatch.setattr(
        app.st,
        "markdown",
        lambda text, **kwargs: rendered_markdown.append((text, kwargs)),
    )

    app.render_dashboard_intro()
    app.render_dashboard_guide()

    all_markdown = "\n".join(text for text, _ in rendered_markdown)
    assert app.INTRODUCTORY_DESCRIPTION in all_markdown
    assert 'role="note"' in rendered_markdown[0][0]
    assert "font-size:1.1rem" in rendered_markdown[0][0]
    assert ">How to use this site</a>" in all_markdown
    assert f'href="#{app.HOW_TO_USE_ANCHOR}"' in all_markdown
    assert f'id="{app.HOW_TO_USE_ANCHOR}"' in all_markdown
    assert all_markdown.count(f'id="{app.HOW_TO_USE_ANCHOR}"') == 1
    assert all_markdown.index(f'id="{app.HOW_TO_USE_ANCHOR}"') < (
        all_markdown.index("How to use this dashboard")
    )
    assert "<section" in all_markdown
    assert 'aria-labelledby="airis-guide-title"' in all_markdown
    assert 'id="airis-guide-title"' in all_markdown
    assert "<ol" in all_markdown
    for heading in (
        "Explore the map",
        "Select a station",
        "Review the results",
        "Assess a proposed site",
    ):
        assert f"<strong>{heading}</strong>" in all_markdown
    assert app.SCORE_CALCULATION_NOTE.startswith("Note:")
    assert all(
        weight in app.SCORE_CALCULATION_NOTE
        for weight in ("50%", "30%", "20%")
    )
    assert "color:#c62828" in all_markdown
    assert "overflow-wrap:anywhere" in all_markdown


def test_redundant_dashboard_subtitle_is_absent():
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "EV charging-site risk intelligence" not in app_source
    assert 'with st.expander("How to use this dashboard"' not in app_source

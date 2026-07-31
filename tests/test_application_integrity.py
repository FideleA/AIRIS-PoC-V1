import importlib
import inspect
from pathlib import Path
from unittest.mock import Mock
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
    expander = Mock()
    expander.__enter__ = Mock(return_value=expander)
    expander.__exit__ = Mock(return_value=False)
    expander_call = Mock(return_value=expander)

    monkeypatch.setattr(
        app.st,
        "markdown",
        lambda text, **kwargs: rendered_markdown.append((text, kwargs)),
    )
    monkeypatch.setattr(app.st, "expander", expander_call)

    app.render_dashboard_intro()
    app.render_dashboard_guide()

    all_markdown = "\n".join(text for text, _ in rendered_markdown)
    assert app.INTRODUCTORY_DESCRIPTION in all_markdown
    assert 'role="note"' in rendered_markdown[0][0]
    assert "font-size:1.1rem" in rendered_markdown[0][0]
    expander_call.assert_called_once_with(
        "How to Use this Dashboard", expanded=False
    )
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
    assert "How to use this site" not in all_markdown
    assert "how-to-use-this-dashboard" not in all_markdown


def test_dashboard_guide_placement_and_uniqueness():
    main_source = inspect.getsource(importlib.import_module("app").main)
    assert main_source.count("render_dashboard_guide()") == 1
    assert main_source.index("render_dashboard_intro()") < main_source.index(
        "render_dashboard_guide()"
    )
    assert main_source.index("render_dashboard_guide()") < main_source.index(
        "st.info("
    )
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert app_source.count('st.expander("How to Use this Dashboard"') == 1
    assert "How to use this site" not in app_source
    assert "how-to-use-this-dashboard" not in app_source


def test_redundant_dashboard_subtitle_is_absent():
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "EV charging-site risk intelligence" not in app_source

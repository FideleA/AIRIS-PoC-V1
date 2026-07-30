import importlib
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
    captions = []

    expander = Mock()
    expander.__enter__ = Mock(return_value=expander)
    expander.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        app.st,
        "markdown",
        lambda text, **kwargs: rendered_markdown.append((text, kwargs)),
    )
    monkeypatch.setattr(app.st, "caption", captions.append)
    expander_call = Mock(return_value=expander)
    monkeypatch.setattr(app.st, "expander", expander_call)

    app.render_dashboard_intro()
    app.render_dashboard_guide()

    all_markdown = "\n".join(text for text, _ in rendered_markdown)
    assert app.INTRODUCTORY_DESCRIPTION in all_markdown
    assert ">How to use this site</a>" in all_markdown
    assert f'id="{app.HOW_TO_USE_ANCHOR}"' in all_markdown
    expander_call.assert_called_once_with(
        "How to use this dashboard", expanded=True
    )
    for heading in (
        "Explore the map",
        "Select a station",
        "Review the results",
        "Assess a proposed site",
    ):
        assert f"**{heading}**" in all_markdown
    assert captions == [app.SCORE_CALCULATION_NOTE]

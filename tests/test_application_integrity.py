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

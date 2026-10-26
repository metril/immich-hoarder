import tomllib
from pathlib import Path


def test_private_classifier() -> None:
    data = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert "Private :: Do Not Upload" in data["project"]["classifiers"]

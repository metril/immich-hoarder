from app.configdoc import REPO, render
from app.core.config import Settings
from app.rip.settings import RateLimit, RipSettings
from app.runtime.settings import NotifySettings, RuntimeSettings


def test_every_field_has_description() -> None:
    for model in (Settings, RipSettings, RateLimit, RuntimeSettings, NotifySettings):
        for name, f in model.model_fields.items():
            assert f.description and f.description.strip(), f"{model.__name__}.{name}"


def test_configuration_reference_current() -> None:
    path = REPO / "docs/reference/configuration.md"
    assert path.exists() and render() == path.read_text(), "run: uv run python -m app.configdoc"


def test_render_lists_env_and_files() -> None:
    out = render()
    for needle in (
        "IH_MASTER_KEY",
        "IH_MASTER_KEY_FILE",
        "IH_DATABASE_URL_FILE",
        "FORWARDED_ALLOW_IPS",
    ):
        assert needle in out
    for name in ("master_key", "session_secret", "oidc_client_secret"):
        row = next(r for r in out.splitlines() if r.startswith(f"| `IH_{name.upper()}` |"))
        assert row.split("|")[3].strip() in ("required", "unset")
    assert out.endswith("\n") and not out.endswith("\n\n")

"""Write the OpenAPI document deterministically: ``python -m app.openapi_dump <path>``."""

import json
import sys
from pathlib import Path

from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app


def build() -> str:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        master_key=SecretStr("test-master-key-0123456789abcdef-xyz"),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        public_url="http://testserver",
    )
    doc = create_app(settings).openapi()
    doc["info"]["version"] = "0"  # release bumps must not stale the committed file
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.openapi_dump <path>", file=sys.stderr)
        return 2
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

import os

import pytest

PG_URL = os.environ.get("IH_TEST_PG_URL")
# Parametrize with this to also run a test against Postgres (-m pg selects only these).
PG_PARAM = pytest.param(
    "pg",
    marks=[pytest.mark.pg, pytest.mark.skipif(not PG_URL, reason="IH_TEST_PG_URL not set")],
)
BACKENDS = ["sqlite", PG_PARAM]

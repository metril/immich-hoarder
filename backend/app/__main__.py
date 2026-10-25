import logging

import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging


def main() -> None:
    configure_logging(get_settings().log_level)
    logging.captureWarnings(True)  # route library warnings through the JSON handler
    # log_config=None: uvicorn loggers propagate to the root JSON handler.
    # Proxy trust comes from uvicorn's native FORWARDED_ALLOW_IPS env.
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=8080,
        proxy_headers=True,
        log_config=None,
    )


if __name__ == "__main__":
    main()

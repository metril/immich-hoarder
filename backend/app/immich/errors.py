class ImmichError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Immich error {status}: {message}")
        self.status = status
        self.message = message


class ImmichAuthError(ImmichError):
    """401/403: bad or under-scoped API key."""


class AssetGone(ImmichError):  # noqa: N818
    """Asset missing or inaccessible (400/404)."""


class ImmichUnavailable(Exception):  # noqa: N818
    """Connection failure or retries exhausted."""

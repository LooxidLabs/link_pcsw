"""Application name and version (single source of truth)."""

APP_NAME = "LINKBAND PC SW"
APP_VERSION = "2.3.3"


def window_title() -> str:
    return f"{APP_NAME} v{APP_VERSION}"

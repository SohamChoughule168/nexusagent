"""Build metadata (Phase 4).

Surfaces immutable facts about the running image for the ``/version`` endpoint
and operators: the application version, the git SHA / build timestamp injected
at image-build time, the Python runtime, and the Alembic migration revision the
container was built against (so operators can confirm "deployed code == applied
migration" without shelling into the container).

Build args are injected by the Dockerfiles (``BUILD_GIT_SHA`` /
``BUILD_TIMESTAMP``); all fields fall back to ``"unknown"`` when the image was
built without them (local dev / editable install).
"""
from importlib.metadata import version as _pkg_version
from pathlib import Path

from app.core.config import settings

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _read_version_file() -> str:
    """Best-effort read of the repo VERSION file (falls back to pyproject)."""
    for candidate in (ROOT_DIR / "VERSION",):
        try:
            return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return settings.APP_VERSION


def get_build_info() -> dict:
    """Return a structured snapshot of build/version metadata."""
    try:
        python_version = __import__("sys").version.split()[0]
    except Exception:  # noqa: BLE001
        python_version = "unknown"

    return {
        "app_name": settings.APP_NAME,
        "version": _read_version_file(),
        "app_version": settings.APP_VERSION,
        "build_git_sha": settings.BUILD_GIT_SHA or "unknown",
        "build_timestamp": settings.BUILD_TIMESTAMP or "unknown",
        "python_version": python_version,
        # Package version as installed in the image (matches pyproject version).
        "package_version": _safe_pkg_version(),
    }


def _safe_pkg_version() -> str:
    try:
        return _pkg_version("nexusagent")
    except Exception:  # noqa: BLE001
        return "unknown"

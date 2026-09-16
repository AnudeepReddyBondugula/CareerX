"""CareerX - AI-powered, RAG-grounded ATS resume builder."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("careerx")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+local"

__all__ = ["__version__"]

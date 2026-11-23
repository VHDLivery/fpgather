"""Tool-independent build inputs."""

from dataclasses import dataclass
from pathlib import Path


class SourcesError(ValueError):
    """An invalid manifest, dependency graph or export request."""


@dataclass(frozen=True)
class Source:
    """An immutable source path, target library and language version."""

    path: Path
    library: str
    language_version: str

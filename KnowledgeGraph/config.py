"""
Neo4j Aura credential loading.

Credentials are read from the environment first, then from the ``Neo4j-*.txt``
file Aura hands out at instance creation - so nothing has to be pasted into
source.  Precedence: explicit arguments > environment > credentials file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Credentials:
    uri: str
    username: str
    password: str
    database: str = "neo4j"
    source: str = "unknown"

    @property
    def auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    def __repr__(self) -> str:  # keep the password out of tracebacks and logs
        return (
            f"Credentials(uri={self.uri!r}, username={self.username!r}, "
            f"password='***', database={self.database!r}, source={self.source!r})"
        )


def parse_credentials_file(path: str | Path) -> dict[str, str]:
    """Parse the ``KEY=VALUE`` file Aura provides (comments start with ``#``)."""
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


#: Aura names its credentials file ``Neo4j-<instance>-Created-<YYYY-MM-DD>.txt``.
_CREATED_RE = re.compile(r"-Created-(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def _created_on(path: Path) -> tuple[str, float]:
    """Sort key: the creation date in the filename, then file mtime.

    Sorting the names directly would order by instance id, which has nothing to
    do with age - with several instances on file that quietly picks the wrong one.
    """
    match = _CREATED_RE.search(path.name)
    return (match.group(1) if match else "", path.stat().st_mtime)


def find_credentials_file(directory: str | Path = HERE) -> Path | None:
    """Most recently created ``Neo4j-*.txt`` in ``directory``."""
    candidates = sorted(Path(directory).glob("Neo4j-*.txt"), key=_created_on)
    return candidates[-1] if candidates else None


def load_credentials(
    *,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
    directory: str | Path = HERE,
) -> Credentials:
    """Resolve Aura credentials, raising if any part is missing."""
    values: dict[str, str] = {}
    source = "arguments"

    path = find_credentials_file(directory)
    if path is not None:
        values.update(parse_credentials_file(path))
        source = str(path.name)

    for key in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        if os.environ.get(key):
            values[key] = os.environ[key]
            source = "environment"

    resolved = Credentials(
        uri=uri or values.get("NEO4J_URI", ""),
        username=username or values.get("NEO4J_USERNAME", "neo4j"),
        password=password or values.get("NEO4J_PASSWORD", ""),
        database=database or values.get("NEO4J_DATABASE", "neo4j"),
        source=source,
    )
    missing = [
        name for name, value in (("uri", resolved.uri), ("password", resolved.password))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing Neo4j credentials: {', '.join(missing)}. Set NEO4J_URI / "
            f"NEO4J_USERNAME / NEO4J_PASSWORD, or keep the Neo4j-*.txt file Aura "
            f"generated in {Path(directory)}."
        )
    return resolved

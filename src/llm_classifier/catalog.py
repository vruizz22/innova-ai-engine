from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from typing import Protocol

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

# Special error_type values valid for every domain, independent of the catalog.
# TRANSVERSAL_LIKELY lets the model defer cross-cutting (non-domain) errors to a
# second pass against the TRANSV domain (ADR A4.4).
SPECIAL_ERROR_TYPES: tuple[str, ...] = ("CORRECT", "UNCLASSIFIED", "TRANSVERSAL_LIKELY")

# The catalog only changes on a deploy (DRAFT->ACTIVE flip + codegen), so the 1h
# in-process window from ADR A4.2 is safe. Keyed by domain_id (the UUID the backend
# puts in the SQS message body).
_CATALOG_TTL_SECONDS = 3600.0

_CATALOG_SQL = """
SELECT d.code            AS domain_code,
       d.name            AS domain_name,
       et.code           AS error_code,
       et.name           AS error_name,
       et.description     AS description,
       et.diagnostic_hint AS diagnostic_hint
  FROM error_tags et
  JOIN domains d ON d.id = et.domain_id
 WHERE et.domain_id = $1
   AND et.status = 'ACTIVE'
 ORDER BY et.code
"""


class Fetcher(Protocol):
    """Structural type for the asyncpg connection bits we use (untyped upstream)."""

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...


class DomainCatalog(BaseModel):
    """ACTIVE error catalog for a single domain, resolved from `domain_id`."""

    domain_id: str
    domain_code: str
    domain_name: str
    error_codes: list[str]
    taxonomy_text: str
    catalog_hash: str


# domain_id -> (expires_at_monotonic, catalog)
_catalog_cache: dict[str, tuple[float, DomainCatalog]] = {}


def _hash_codes(codes: Sequence[str]) -> str:
    """Stable 12-char hash of the active code set — used in the prompt cache key."""
    joined = "\n".join(sorted(codes)).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:12]


def _build_taxonomy_text(domain_name: str, rows: Sequence[Mapping[str, object]]) -> str:
    lines = [
        f"[ERROR CATALOG -- domain: {domain_name}. Use ONLY these error_type codes.]",
        "",
    ]
    for row in rows:
        code = str(row["error_code"])
        description = str(row["description"])
        hint = row["diagnostic_hint"]
        line = f"- {code}: {description}"
        if hint is not None and str(hint).strip():
            line += f" (signal: {str(hint).strip()})"
        lines.append(line)
    return "\n".join(lines)


async def fetch_domain_catalog(conn: Fetcher, domain_id: str) -> DomainCatalog | None:
    """Query the ACTIVE catalog for one domain. Returns None when the domain has no
    ACTIVE error tags (or domain_id is unknown) so the caller can fall back."""
    rows = await conn.fetch(_CATALOG_SQL, domain_id)
    if not rows:
        return None

    domain_code = str(rows[0]["domain_code"])
    domain_name = str(rows[0]["domain_name"])
    error_codes = [str(row["error_code"]) for row in rows]
    return DomainCatalog(
        domain_id=domain_id,
        domain_code=domain_code,
        domain_name=domain_name,
        error_codes=error_codes,
        taxonomy_text=_build_taxonomy_text(domain_name, rows),
        catalog_hash=_hash_codes(error_codes),
    )


async def get_domain_catalog(
    conn: Fetcher, domain_id: str, *, now: float | None = None
) -> DomainCatalog | None:
    """Cached (1h TTL) wrapper around `fetch_domain_catalog`."""
    clock = time.monotonic() if now is None else now
    cached = _catalog_cache.get(domain_id)
    if cached is not None and cached[0] > clock:
        return cached[1]

    catalog = await fetch_domain_catalog(conn, domain_id)
    if catalog is not None:
        _catalog_cache[domain_id] = (clock + _CATALOG_TTL_SECONDS, catalog)
        logger.info(
            "domain_catalog_loaded",
            domain_id=domain_id,
            domain_code=catalog.domain_code,
            n_codes=len(catalog.error_codes),
            catalog_hash=catalog.catalog_hash,
        )
    return catalog


def clear_catalog_cache() -> None:
    """Test helper — drop the in-process TTL cache."""
    _catalog_cache.clear()

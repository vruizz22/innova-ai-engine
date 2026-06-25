from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence

import pytest

from src.llm_classifier.catalog import (
    _hash_codes,
    clear_catalog_cache,
    fetch_domain_catalog,
    get_domain_catalog,
)

_ROWS: list[Mapping[str, object]] = [
    {
        "domain_code": "FRACT",
        "domain_name": "Fractions",
        "error_code": "FRACT_MUL_CROSS_MULTIPLIES_G6",
        "error_name": "Cross multiplies",
        "description": "Multiplies fractions crosswise.",
        "diagnostic_hint": "a*d / b*c pattern",
    },
    {
        "domain_code": "FRACT",
        "domain_name": "Fractions",
        "error_code": "FRACT_DIV_NO_RECIPROCAL_G7",
        "error_name": "No reciprocal",
        "description": "Divides straight across.",
        "diagnostic_hint": None,
    },
]


class _FakeConn:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self._rows = rows
        self.calls = 0

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]:
        self.calls += 1
        return self._rows


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def test_fetch_builds_catalog() -> None:
    conn = _FakeConn(_ROWS)
    cat = asyncio.run(fetch_domain_catalog(conn, "dom-uuid-1"))
    assert cat is not None
    assert cat.domain_code == "FRACT"
    assert cat.error_codes == [
        "FRACT_MUL_CROSS_MULTIPLIES_G6",
        "FRACT_DIV_NO_RECIPROCAL_G7",
    ]
    assert "FRACT_MUL_CROSS_MULTIPLIES_G6" in cat.taxonomy_text
    assert "signal: a*d / b*c pattern" in cat.taxonomy_text
    assert len(cat.catalog_hash) == 12


def test_fetch_returns_none_when_empty() -> None:
    conn = _FakeConn([])
    assert asyncio.run(fetch_domain_catalog(conn, "dom-x")) is None


def test_get_domain_catalog_caches_within_ttl() -> None:
    conn = _FakeConn(_ROWS)
    c1 = asyncio.run(get_domain_catalog(conn, "dom-uuid-1", now=1000.0))
    c2 = asyncio.run(get_domain_catalog(conn, "dom-uuid-1", now=1010.0))
    assert conn.calls == 1  # second call served from cache
    assert c1 is c2


def test_get_domain_catalog_refetches_after_ttl() -> None:
    conn = _FakeConn(_ROWS)
    asyncio.run(get_domain_catalog(conn, "dom-uuid-1", now=0.0))
    asyncio.run(get_domain_catalog(conn, "dom-uuid-1", now=4000.0))  # > 3600s TTL
    assert conn.calls == 2


def test_hash_is_order_independent() -> None:
    assert _hash_codes(["B", "A"]) == _hash_codes(["A", "B"])

"""SecretCache micro-benchmarks (Task 5.3 / Task 1.5 acceptance:
cache reduces Vault QPS by >90% for repeated reads).

Vault round-trips are the slowest dependency in a normal session
(network + KV-v2 read). The cache absorbs the second-and-onward
fetches of the same secret — verify it actually does so under
contention.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, List

import pytest

from app.config import Settings
from app.models.secret import SecretType
from app.services.secret_cache import SecretCache


@dataclass
class _StubVault:
    """Mock VaultClient that counts round-trips and (optionally) sleeps."""

    delay_s: float = 0.0
    calls: List[Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.calls = []

    async def get_user_secret(self, *, user_id: str, secret_type: SecretType):
        from app.clients.vault import SecretValue

        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        self.calls.append((user_id, secret_type))
        return SecretValue(value=f"v-{user_id}-{secret_type.value}", expires_at=None)


@pytest.mark.asyncio
async def test_cache_hit_avoids_vault_calls():
    """1 miss + 999 hits → only 1 Vault call. >90% reduction trivially
    satisfied; this is the floor we never want to fall below.
    """
    settings = Settings(vault_cache_ttl_s=60.0)
    vault = _StubVault()
    cache = SecretCache(settings, vault)  # type: ignore[arg-type]

    for _ in range(1000):
        await cache.get(user_id="alice@gwdg", secret_type=SecretType.SEARCH_API_KEY)

    assert len(vault.calls) == 1
    assert cache.hits == 999
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_concurrent_first_hits_collapse_to_one_vault_call():
    """50 concurrent requests for the same uncached secret should
    result in exactly one Vault round-trip — the per-key lock
    prevents a stampede.
    """
    settings = Settings(vault_cache_ttl_s=60.0)
    # Add a small artificial delay so all coroutines pile up on the
    # per-key lock before the first one returns.
    vault = _StubVault(delay_s=0.05)
    cache = SecretCache(settings, vault)  # type: ignore[arg-type]

    await asyncio.gather(
        *(
            cache.get(user_id="bob@gwdg", secret_type=SecretType.SEARCH_API_KEY)
            for _ in range(50)
        )
    )

    assert len(vault.calls) == 1, vault.calls
    assert cache.hits == 49
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_cache_hit_under_5_us_mean():
    """Once warm, cache hits must be sub-µs to micro-second — assert
    < 5 µs / call mean over 100k hits.
    """
    settings = Settings(vault_cache_ttl_s=600.0)
    vault = _StubVault()
    cache = SecretCache(settings, vault)  # type: ignore[arg-type]

    # Warm.
    await cache.get(user_id="alice@gwdg", secret_type=SecretType.SEARCH_API_KEY)

    n = 100_000
    t0 = time.perf_counter()
    for _ in range(n):
        await cache.get(
            user_id="alice@gwdg", secret_type=SecretType.SEARCH_API_KEY
        )
    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
    per_call_us = elapsed_us / n

    assert per_call_us < 5.0, (
        f"cache hit mean {per_call_us:.2f} µs (>5 µs budget)"
    )
    assert len(vault.calls) == 1  # Still no extra round-trips.

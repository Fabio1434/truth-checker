from app.services.cache_service import CacheService


def test_cache_round_trip_and_language_isolation():
    cache = CacheService(ttl_seconds=60)
    cache.set("Same claim", {"score": 80}, "fr")
    assert cache.get("Same claim", "fr")["score"] == 80
    assert cache.get("Same claim", "en") is None


def test_cache_cleanup_expired():
    cache = CacheService(ttl_seconds=0)
    cache.set("claim", {"ok": True}, "fr")
    assert cache.get("claim", "fr") is None
    assert cache.stats()["cached_items"] == 0

"""
Cache Service - Simple caching to avoid duplicate searches.

Caches analysis results to avoid repeatedly analyzing the same claims.
Uses in-memory cache with TTL.
"""

import hashlib
import time
from typing import Optional, Callable
from datetime import datetime, timedelta


class CacheService:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        self.cache = {}
        self.ttl_seconds = ttl_seconds
    
    def get_cache_key(self, claim: str, language: str = "fr") -> str:
        """Generate a cache key for a claim."""
        combined = f"{claim.strip().lower()}:{language}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get(self, claim: str, language: str = "fr") -> Optional[dict]:
        """Get cached analysis result if it exists and is fresh."""
        key = self.get_cache_key(claim, language)
        
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        
        # Check if expired
        if time.time() > entry["expires_at"]:
            del self.cache[key]
            return None
        
        return entry["data"]
    
    def set(self, claim: str, data: dict, language: str = "fr") -> None:
        """Cache an analysis result."""
        key = self.get_cache_key(claim, language)
        
        self.cache[key] = {
            "data": data,
            "created_at": time.time(),
            "expires_at": time.time() + self.ttl_seconds
        }
    
    def clear(self) -> None:
        """Clear all cache."""
        self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed."""
        current_time = time.time()
        expired_keys = [
            k for k, v in self.cache.items()
            if current_time > v["expires_at"]
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        return len(expired_keys)
    
    def stats(self) -> dict:
        """Return cache statistics."""
        self.cleanup_expired()
        
        return {
            "cached_items": len(self.cache),
            "ttl_seconds": self.ttl_seconds,
            "memory_estimate_bytes": sum(
                len(str(v).encode())
                for v in self.cache.values()
            )
        }

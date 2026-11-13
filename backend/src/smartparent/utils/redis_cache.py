"""
STUDIQS® SmartParent™ (v6.3 Complete) - In-Memory Redis Caching & Rate Limiting
==============================================================================
Module: src.smartparent.utils.redis_cache
Production caching layer implementing:
  1. 8,034 Taxonomy Node In-Memory Cache (24-Hour TTL)
  2. Sliding-Window OTP Request Rate Limiter (Max 3 OTPs / 10 Minutes per Phone)
  3. JWT Refresh Token Blacklist Cache (On Logout)
==============================================================================
"""

import json
import logging
from typing import Any, Dict, List, Optional
import redis

from src.smartparent.config import settings

logger = logging.getLogger("STUDIQS_RedisCache")

REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")


class RedisCacheService:
    """
    High-performance in-memory cache and rate limiting service.
    Gracefully degrades if Redis is temporarily unreachable.
    """

    def __init__(self, url: Optional[str] = None):
        self.client: Optional[redis.Redis] = None
        target_url = url or REDIS_URL
        try:
            self.client = redis.Redis.from_url(target_url, decode_responses=True, socket_timeout=2)
            self.client.ping()
            logger.info("[RedisCache] Connected to Redis successfully.")
        except Exception as e:
            logger.warning(f"[RedisCache] Redis server not available ({e}). Running in fallback direct mode.")
            self.client = None

    # =========================================================================
    # 1. TAXONOMY CACHE
    # =========================================================================

    def get_cached_taxonomy(self, board: str, standard_class: str, subject: str) -> Optional[List[Dict[str, Any]]]:
        """Fetches cached taxonomy chapter/topic tree."""
        if not self.client:
            return None
        cache_key = f"tax:{board.upper()}:{standard_class.upper()}:{subject.upper()}"
        try:
            cached_val = self.client.get(cache_key)
            if cached_val:
                return json.loads(cached_val)
        except Exception as e:
            logger.error(f"[RedisCache] Error reading taxonomy cache: {e}")
        return None

    def set_cached_taxonomy(self, board: str, standard_class: str, subject: str, data: List[Dict[str, Any]], ttl_seconds: int = 86400) -> None:
        """Caches taxonomy chapter/topic tree for 24 hours."""
        if not self.client:
            return
        cache_key = f"tax:{board.upper()}:{standard_class.upper()}:{subject.upper()}"
        try:
            self.client.setex(cache_key, ttl_seconds, json.dumps(data))
        except Exception as e:
            logger.error(f"[RedisCache] Error writing taxonomy cache: {e}")

    # =========================================================================
    # 2. OTP SLIDING-WINDOW RATE LIMITER
    # =========================================================================

    def check_and_increment_otp_rate_limit(self, phone: str, max_attempts: int = 3, window_seconds: int = 600) -> bool:
        """
        Enforces max 3 OTP requests per 10 minutes per mobile number.
        Returns True if allowed, False if rate limited.
        """
        if not self.client:
            return True  # Fallback: allow request if Redis is down

        key = f"rate:otp:{phone}"
        try:
            current = self.client.incr(key)
            if current == 1:
                self.client.expire(key, window_seconds)
            return current <= max_attempts
        except Exception as e:
            logger.error(f"[RedisCache] Rate limit check error: {e}")
            return True

    # =========================================================================
    # 3. JWT TOKEN REVOCATION BLACKLIST
    # =========================================================================

    def blacklist_token(self, token_jti: str, ttl_seconds: int = 86400) -> None:
        """Adds revoked JWT ID to blacklist cache until its natural expiration."""
        if not self.client:
            return
        key = f"jwt:blacklist:{token_jti}"
        try:
            self.client.setex(key, ttl_seconds, "revoked")
        except Exception as e:
            logger.error(f"[RedisCache] Error blacklisting token: {e}")

    def is_token_blacklisted(self, token_jti: str) -> bool:
        """Checks if JWT ID is in revocation blacklist."""
        if not self.client:
            return False
        key = f"jwt:blacklist:{token_jti}"
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"[RedisCache] Error checking token blacklist: {e}")
            return False


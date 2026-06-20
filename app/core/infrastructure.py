"""Shared database, memory and Redis clients used across the app."""
import redis

from agno.db.postgres import PostgresDb
from agno.memory.manager import MemoryManager

from app.core.settings import settings

shared_db = PostgresDb(
        db_url=settings.PG_URL
)

redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
)

shared_memory_manager = MemoryManager(
        db=shared_db,
        model=settings.MEMORY_MODEL
)

# Backwards-compatible export for older call sites/tests.
shared_memory = shared_memory_manager


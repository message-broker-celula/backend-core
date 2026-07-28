"""Rate limiting boundary shared across the application.

This module exposes a shared `Limiter` instance so routers can apply stricter
limits without importing the FastAPI application entrypoint and causing
circular dependencies.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

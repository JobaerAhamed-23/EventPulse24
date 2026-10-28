"""The HTTP API.

Its OpenAPI schema is the contract the frontend client is generated from (AD-19).
"""

from ninja import NinjaAPI

from config.errors import install_error_handlers
from config.health import router as health_router

api = NinjaAPI(title="EventPulse24 API", version="0.1.0")
install_error_handlers(api)

api.add_router("/health", health_router)

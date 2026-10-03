from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.access.router import router as access_router
from app.modules.ai.router import router as ai_router
from app.modules.alerts.router import router as alerts_router
from app.modules.analytics.router import router as analytics_router
from app.modules.assets.router import router as assets_router
from app.modules.audit.router import router as audit_router
from app.modules.directory.router import router as directory_router
from app.modules.identity.router import router as identity_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.realtime.router import router as realtime_router
from app.modules.sla.router import router as sla_router
from app.modules.tickets.router import router as tickets_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(identity_router, tags=["authentication"])
api_router.include_router(access_router)
api_router.include_router(alerts_router)
api_router.include_router(directory_router)
api_router.include_router(tickets_router)
api_router.include_router(sla_router)
api_router.include_router(knowledge_router)
api_router.include_router(ai_router)
api_router.include_router(analytics_router)
api_router.include_router(audit_router)
api_router.include_router(assets_router)
api_router.include_router(monitoring_router)
api_router.include_router(realtime_router)

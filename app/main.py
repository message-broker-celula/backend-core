from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.admin.api.admin_routes import router as admin_router
from app.ai.api.ai_routes import router as ai_router
from app.audit.api.audit_routes import router as audit_router
from app.auth.api.oauth_routes import router as auth_router
from app.celulas.api.celula_routes import router as celulas_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.databases.api.database_routes import router as databases_router
from app.external_clients.api.external_client_routes import router as external_clients_router
from app.metrics.api.metrics_routes import router as metrics_router

# -----------------------------------------------------------------------
# Rate limiting a nivel de aplicacion (defensa en profundidad).
# El limite "duro" y real vive en Nginx (limit_req/limit_conn) + fail2ban,
# pero si una peticion llega a Uvicorn igual queda protegida aqui. El
# `limiter` compartido vive en app.core.rate_limit para que otros routers
# puedan importarlo y aplicar limites mas estrictos por endpoint sin crear
# una segunda instancia (y por tanto un segundo estado de conteo) aqui.
# -----------------------------------------------------------------------

app = FastAPI(
    title="Database-Centric API",
    description=(
        "Backend mediador para la plataforma de hosting de bases de datos y "
        "servicios. Toda la logica de negocio vive en SQL Server (Stored "
        "Procedures, Views, Functions); este backend solo autentica, "
        "despacha y mapea respuestas."
    ),
    version=settings.app.version,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allowed_origins,
    allow_origin_regex=settings.cors.allow_origin_regex,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=settings.cors.allowed_methods,
    allow_headers=settings.cors.allowed_headers,
)
app.add_middleware(SlowAPIMiddleware)
app.include_router(auth_router)
app.include_router(databases_router)
app.include_router(admin_router)
app.include_router(celulas_router)
app.include_router(audit_router)
app.include_router(metrics_router)
app.include_router(ai_router)
app.include_router(external_clients_router)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.app.trusted_hosts,
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Rechaza peticiones con body excesivo antes de procesarlas.

    Mitiga ataques de agotamiento de memoria/disco vía payloads gigantes,
    complementario al limit_req/limit_conn de Nginx.
    """
    content_length = request.headers.get("content-length")
    max_body_bytes = 1 * 1024 * 1024  # 1 MB, ajustar segun necesidad real
    if content_length:
        try:
            parsed_content_length = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Content-Length invalido"},
            )
        if parsed_content_length > max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Payload demasiado grande"},
            )
    return await call_next(request)


@app.get("/")
@limiter.limit("30/minute")
def root(request: Request):
    return {
        "message": "Backend funcionando correctamente"
    }


@app.get("/health")
@limiter.limit("120/minute")
def health(request: Request):
    return {
        "status": "healthy"
    }

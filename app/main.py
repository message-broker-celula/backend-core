from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# -----------------------------------------------------------------------
# Rate limiting a nivel de aplicacion (defensa en profundidad).
# El limite "duro" y real vive en Nginx (limit_req/limit_conn) + fail2ban,
# pero si una peticion llega a Uvicorn igual queda protegida aqui.
# -----------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="Database-Centric API",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Solo aceptar Host headers esperados (evita ataques de host header
# spoofing / cache poisoning cuando el backend queda tras Nginx).
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],  # TODO: restringir a ["api.<celula>.andrescortes.dev", "localhost"] en produccion
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Rechaza peticiones con body excesivo antes de procesarlas.

    Mitiga ataques de agotamiento de memoria/disco vía payloads gigantes,
    complementario al limit_req/limit_conn de Nginx.
    """
    content_length = request.headers.get("content-length")
    max_body_bytes = 1 * 1024 * 1024  # 1 MB, ajustar segun necesidad real
    if content_length and int(content_length) > max_body_bytes:
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

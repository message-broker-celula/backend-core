# Backend Core

Backend principal de la plataforma **Database-Centric Architecture**, desarrollado con **FastAPI**.

Este servicio actúa como intermediario "tonto" entre el cliente y SQL Server: expone la API REST, gestiona autenticación OAuth (Google/GitHub) y JWT, aplica rate limiting, y **traslada cada operación a un Stored Procedure/View/Function** — nunca implementa reglas de negocio en Python.

> **Regla de oro:** ninguna validación compleja, cálculo, asignación de permisos o flujo de negocio se escribe en este código. Toda esa lógica vive en `MessageBrokerDB` (SQL Server), en los 22 scripts de la carpeta de base de datos del equipo.

---

## Arquitectura

Patrón **Repository + Dependency Inversion** en cada módulo de dominio:

```
app/
  core/            configuración, JWT, rate limiter compartido
  repositories/    ejecutor de Stored Procedures (pyodbc) + implementación
                   concreta única (SQLServerRepository) que sabe SQL
  auth/            OAuth (Google/GitHub), JWT, refresh tokens con rotación
  databases/       ciclo de vida de bases de datos aprovisionadas
  celulas/         equipos y sus servicios (subdominios)
  admin/           gestión de roles y vista global (rol ADMIN)
  audit/           eventos genéricos de auditoría
```

Cada dominio define su propia interfaz (`Protocol`) — el "control remoto" —
sin saber que existe SQL Server. La única clase que conoce nombres de
Stored Procedures es `SQLServerRepository`
(`app/repositories/implementations/sqlserver_repository.py`); los servicios
y endpoints dependen exclusivamente de la interfaz de su propio dominio.

## Seguridad

| Control | Dónde |
|---|---|
| Usuario SQL con permisos mínimos (`app_backend`: `EXECUTE`/`SELECT` sobre SPs/Views/Functions, `DENY` sobre tablas) | `.env` → `SQLSERVER_USER` |
| Parámetros ligados en toda llamada SQL (cero concatenación de texto) | `app/repositories/implementations/sqlserver_repository.py` |
| Rate limiting por IP a nivel de aplicación | `app/core/rate_limit.py` + `slowapi` |
| CORS restringido por origen | `app/core/config.py` → `CORS_*` |
| `TrustedHostMiddleware` | `app/main.py` |
| Límite de tamaño de payload (1 MB) | `app/main.py` |
| JWT firmado + refresh tokens con detección de reuso (revoca toda sesión si detecta robo) | `app/core/security.py`, `sp_RotarRefreshToken` |
| Estado OAuth firmado con HMAC y comparación de tiempo constante | `app/auth/services/oauth_service.py` |
| Defensa en profundidad real (Nginx `limit_req`/`limit_conn` + fail2ban) | `infra/` |

---

## Requisitos

- Python 3.12
- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/)
- SQL Server con los 22 scripts de `MessageBrokerDB` ya aplicados

---

## Levantar el proyecto

```bash
cp .env.example .env   # completar credenciales reales
docker compose up --build
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Sin Docker

```bash
uv sync
uv run uvicorn app.main:app --reload
```

### Tests

```bash
uv run python -m pytest -q
```

---

## Despliegue en producción

Ver `docker-compose.prod.yml` (backend en red interna, sin exponer el
puerto 8000 a Internet) e `infra/` (Nginx con `limit_req`/`limit_conn`,
fail2ban, hardening de VPS). El pipeline de CI/CD (`.github/workflows/ci-cd.yml`)
corre los tests antes de construir y publicar la imagen a GHCR, y solo
despliega si pasan.

## Estado del proyecto

🚧 Proyecto en desarrollo.

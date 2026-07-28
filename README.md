# Backend Core

Backend principal de la plataforma **Database-Centric Architecture**, desarrollado con **FastAPI**.

Este servicio actúa como intermediario entre el cliente y la base de datos, exponiendo la API REST y gestionando aspectos como autenticación, validaciones y comunicación con SQL Server.

> **Nota:** La lógica de negocio del proyecto reside en la base de datos mediante Stored Procedures.

---

## Requisitos

- Python 3.12
- Docker Desktop
- Docker Compose
- uv

---

## Levantar el proyecto

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd backend-core
```

### 2. Construir la imagen

```bash
docker compose build
```

### 3. Iniciar el contenedor

```bash
docker compose up
```

Si deseas reconstruir la imagen después de realizar cambios:

```bash
docker compose up --build
```

---

## Acceso

Una vez iniciado el contenedor, la aplicación estará disponible en:

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Estado del proyecto

🚧 Proyecto en desarrollo.
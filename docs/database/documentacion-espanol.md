# Documentación básica en español

## Qué se implementó

Se construyó la base de la capa de integración con base de datos, manteniendo la arquitectura existente y evitando tocar la lógica de autenticación ni los endpoints OAuth.

### Objetivo

La idea principal fue dejar una capa reutilizable para ejecutar Stored Procedures en SQL Server, sin que la API o los servicios tengan que conocer detalles de implementación de la base de datos.

## Qué quedó hecho

### 1. Contrato reutilizable para ejecución de Stored Procedures
Se definió un protocolo genérico para ejecutar procedimientos almacenados:

- `StoredProcedureExecutorProtocol`
- `StoredProcedureExecutionResult`

Esto permite que cualquier repositorio nuevo use la misma forma de llamar a la base de datos.

### 2. Contrato genérico de repositorio
Se creó una interfaz reutilizable para operaciones de base de datos:

- `DatabaseRepositoryProtocol`

Esta capa es más estable y evita acoplar los servicios directamente a SQL Server.

### 3. Adaptador SQL Server
Se creó una implementación base llamada:

- `StoredProcedureExecutor`

Su propósito es centralizar la conexión y la ejecución de procedimientos en un único lugar.

### 4. Repositorio concreto
Se agregó un repositorio orientado a SQL Server:

- `SQLServerRepository`

Este repositorio queda preparado para mapear llamadas del negocio hacia el ejecutor de Stored Procedures.

### 5. Manejo seguro de errores
Se agregaron excepciones de repositorio para no filtrar errores internos de SQL al resto de la aplicación:

- `DatabaseIntegrationError`
- `DatabaseConnectionError`
- `StoredProcedureExecutionError`
- `RepositoryMappingError`

## Cómo se hizo

La implementación se mantuvo en la misma línea arquitectónica del proyecto:

1. Se conservó la capa de autenticación ya existente.
2. Se agregó una capa nueva para base de datos, pero reutilizable.
3. Se evitó duplicar utilidades o romper la estructura actual.
4. Se separaron los contratos de la implementación real.
5. Se documentó la arquitectura para que sea fácil de ampliar.

## Archivos importantes

- [app/repositories/interfaces/sp_executor.py](../repositories/interfaces/sp_executor.py)
- [app/repositories/interfaces/database_repository.py](../repositories/interfaces/database_repository.py)
- [app/repositories/sqlserver/executor.py](../repositories/sqlserver/executor.py)
- [app/repositories/implementations/sqlserver_repository.py](../repositories/implementations/sqlserver_repository.py)
- [app/repositories/exceptions/database_exceptions.py](../repositories/exceptions/database_exceptions.py)

## Estado de la API en localhost

La configuración de Docker en [docker-compose.yml](../../docker-compose.yml) expone el servicio en el puerto `8000`:

- `8000:8000`

Eso significa que, cuando el contenedor está levantado correctamente, la API debería estar disponible en:

- http://localhost:8000
- http://localhost:8000/docs
- http://localhost:8000/redoc

## Verificación real del entorno

La comprobación con Docker en este entorno no pudo confirmarse porque el cliente Docker no está disponible aquí:

- `docker compose ps` devolvió error: `The system cannot find the file specified.`

Por eso, la URL `http://localhost:8000` es la ruta esperada desde el archivo de configuración, pero no pude confirmar desde esta sesión que el contenedor esté corriendo en este momento.

## Cómo probarlo si tu Docker sí está activo

1. Abre una terminal en la raíz del proyecto.
2. Ejecuta:

```bash
docker compose up --build
```

3. Luego entra en:

```text
http://localhost:8000/docs
```

4. Si quieres comprobar el servicio sin Docker, también puedes usar:

```bash
uvicorn app.main:app --reload
```

## Resumen corto

Se dejó una capa limpia, reutilizable y preparada para conectar lógica de base de datos mediante Stored Procedures, sin tocar la parte de OAuth ni de endpoints. La API se apunta a `localhost:8000` cuando el contenedor está levantado.

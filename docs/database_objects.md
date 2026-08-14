# Objetos de base de datos — SQL Server (MessageBrokerDB)

Este documento cubre **todos** los Stored Procedures, Views y Functions que el backend invoca, extraídos directamente de la base de datos de producción (`OBJECT_DEFINITION`), no de una copia local — los scripts `.sql` originales no viven en este repositorio (ver nota al final).

Convenciones que aplican a casi todos los SPs de escritura:
- `SET XACT_ABORT ON` + `BEGIN TRY/CATCH` con `ROLLBACK` + `THROW`: cualquier error revierte la transacción y se relanza tal cual hacia el backend (que lo mapea a `BusinessRuleViolationError` si es un `THROW` propio, o `StoredProcedureExecutionError` si es un error real de SQL Server).
- `usuario_sistema` en `Auditoria`: cuando una operación la dispara el sistema (no un usuario autenticado), `id_usuario = NULL` y `usuario_sistema = 'SISTEMA'` (o `'SISTEMA_TTL'` para el job de limpieza) — `CHK_auditoria_actor` exige que exactamente uno de los dos esté informado.
- Todas las llamadas desde Python usan parámetros ligados (`?`), nunca concatenación de texto — ver `app/repositories/sqlserver/executor.py`.

---

## 1. Autenticación

### `sp_RegistrarOAuth`
**Parámetros:** `@oauth_provider, @oauth_id, @nombre, @correo, @avatar, @ip, @user_agent, @id_usuario OUTPUT, @es_nuevo OUTPUT`

Registra o actualiza un usuario tras un login OAuth exitoso (Google/GitHub). Si `(oauth_provider, oauth_id)` ya existe, actualiza `ultimo_login`/`nombre`/`avatar`; si no, crea el usuario. El `correo` es `UNIQUE` — si ya existe con **otro** proveedor, lanza `THROW 51003` con un mensaje legible ("Ya existe una cuenta con este correo registrada con otro proveedor...") en vez de dejar que reviente la constraint directamente, para evitar que alguien "robe" una cuenta por el mismo correo desde otro proveedor. Registra un evento `LOGIN` (`EXITO`/`FALLO`) en `Auditoria` incluso si falla.

**Llamado desde:** `app/repositories/implementations/sqlserver_repository.py::register_oauth_user` ← `AuthService.authenticate_oauth_user` ← `POST /auth/{google,github}/callback`.

### `sp_EmitirRefreshToken`
**Parámetros:** `@id_usuario, @ip, @user_agent, @dias_validez, @token_nuevo OUTPUT`

Genera el primer refresh token de una sesión (`CRYPT_GEN_RANDOM` + hash SHA-256 almacenado, nunca el token en texto plano). **Llamado desde:** `issue_refresh_token` ← `AuthService.authenticate_oauth_user`.

### `sp_RotarRefreshToken`
**Parámetros:** `@token_actual, @ip, @user_agent, @dias_validez, @id_usuario OUTPUT, @token_nuevo OUTPUT`

Rota un refresh token: valida que exista y no esté revocado/expirado, emite uno nuevo, marca el viejo como revocado y enlazado al nuevo (`reemplazado_por`). Si detecta que un token **ya revocado** se reintenta usar (señal de robo/reuso), revoca **todas** las sesiones activas del usuario y lanza un error de seguridad. **Llamado desde:** `refresh_access_token` ← `AuthService.refresh_access_token` ← `POST /auth/refresh`.

### `sp_RevocarRefreshToken` / `sp_RevocarTodosLosRefreshTokens`
Revocan un token específico o todos los de un usuario (logout). Registran `LOGOUT` en `Auditoria`. **Llamados desde:** `revoke_refresh_token` / `revoke_all_refresh_tokens` ← `POST /auth/logout`.

---

## 2. Aprovisionamiento de bases de datos

### `sp_CrearBD`
**Parámetros:** `@id_usuario, @nombre_motor, @version_motor, @nombre_bd, @host, @puerto, @usuario_bd, @password_bd, @ip, @espacio_maximo_mb, @conexiones_maximas, @ttl_dias, @id_celula, @id_bd OUTPUT`

El corazón del aprovisionamiento. Valida: usuario activo, motor/versión disponible en `Motores`, límite de 5 BDs activas por usuario, nombre no repetido (excluyendo `ELIMINADA` — ver fix abajo). Inserta la fila en `BasesDeDatos` y cifra `password_bd` con `ENCRYPTBYKEY` (AES-256, certificado `CertCredenciales`) en `Credenciales`. `host/puerto/usuario_bd/password_bd` los genera el **backend** (contenedor Docker real vía `provisioner/`), este SP solo los almacena/cifra, nunca los inventa.

> **Fix aplicado esta sesión:** el `IF EXISTS` de unicidad de nombre no excluía `ELIMINADA`, por lo que un usuario nunca podía reusar un nombre de BD tras borrarla. Se agregó `AND estado <> 'ELIMINADA'`.

**Llamado desde:** `create_database` ← `DatabaseService.create_database` ← `POST /databases`.

### `sp_PausarBD` / `sp_ReanudarBD`
**Parámetros:** `@id_bd, @id_usuario, @ip` (ambos)

Cambian `estado` entre `ACTIVA` ↔ `PAUSADA`, validando dueño y estado actual (`sp_PausarBD` solo pausa lo `ACTIVA`; `sp_ReanudarBD` solo reanuda lo `PAUSADA`). Auditan cada intento, exitoso o no.

> **`sp_ReanudarBD` no existía en la base de datos hasta esta sesión** — `resume_database` en el backend llevaba desde antes de esta sesión lanzando un error incondicional (`RepositoryMappingError`, 503) porque el SP simplemente no existía. Se creó siguiendo exactamente el patrón de `sp_PausarBD`. También fue necesario ampliar el `CHECK CHK_auditoria_evento` para permitir el valor `'REANUDAR_BD'`, que tampoco estaba en la lista permitida.

**Llamados desde:** `pause_database`/`resume_database` ← `DatabaseService` ← `POST /databases/{id}/pause` y `/resume`.

### `sp_CrearServicio`
**Parámetros:** `@id_celula, @nombre_servicio, @puerto_interno, @id_bd, @id_usuario, @ip, @id_servicio OUTPUT`

Crea un servicio/subdominio dentro de una célula (ver `Servicios` más abajo). Valida célula activa, BD referenciada (si aplica), nombre no repetido en la célula, y el límite de 5 subdominios activos por célula.

> **Fix aplicado esta sesión:** `Servicios.puerto_interno` era `NOT NULL` y `@puerto_interno` no tenía default, pero un subdominio de solo-DNS (sin base de datos ni servicio real detrás, el alcance acordado para esta funcionalidad) legítimamente no tiene puerto interno. El backend ya mandaba `NULL` correctamente (`register_celula_service`'s `port: int | None = None`), pero nunca se había probado de punta a punta hasta la primera creación real contra producción, que reventó con una violación de `NOT NULL`. Se hizo `puerto_interno` nullable en la tabla y `@puerto_interno INT = NULL` en el SP.

**Llamado desde:** `register_celula_service` ← `CelulaOrchestrationService.register_service` ← `POST /celulas/{id}/services`.

### `sp_EliminarBD`
**Parámetros:** `@id_bd, @id_usuario, @ip`

Borrado lógico (`estado = 'ELIMINADA'`), no físico. Borra las credenciales cifradas (`DELETE FROM Credenciales`) para que nadie pueda volver a descifrar el password, y desliga los `Servicios` que apuntaban a esa BD (`id_bd = NULL, estado = 'CAIDO'`) en vez de borrarlos. **Llamado desde:** `delete_database` ← `POST /databases/{id}` (DELETE).

### `sp_ObtenerCredenciales`
**Parámetros:** `@id_bd, @id_usuario`

Verifica que la BD pertenezca al usuario (y no esté `ELIMINADA`), abre la llave simétrica y devuelve `usuario_bd, password_bd (descifrado), algoritmo`. **No devuelve `host`/`puerto`/`nombre_bd`** — esos viven en `BasesDeDatos`, no en `Credenciales`; el backend los combina desde `get_database` antes de responder al cliente (ver `DatabaseService.get_credentials`). **Llamado desde:** `get_database_credentials` ← `GET /databases/{id}/credentials`.

### `sp_ActualizarEspacio`
**Parámetros:** `@id_bd, @espacio_reportado_mb, @ip, @dias_ttl, @permitir_escritura OUTPUT`

El motor MySQL real (fuera de esta base de datos) reporta cuánto espacio está usando; este SP decide si se permite seguir escribiendo (`espacio_reportado_mb <= espacio_maximo_mb`) y renueva la ventana de TTL. Si se excede, audita un evento `LIMITE_ESPACIO`. **Llamado desde:** `update_space` ← `POST /databases/{id}/space`.

### `sp_ValidarConexion` / `sp_LiberarConexion`
Llevan la cuenta de `conexiones_actuales` vs `conexiones_maximas` por BD (con `UPDLOCK, ROWLOCK` para evitar carreras). **Llamados desde:** `validate_connection`/`release_connection` ← `POST /databases/{id}/connections/{validate,release}`.

### `sp_RegistrarActividad`
**Parámetros:** `@id_bd, @dias_ttl`

Renueva `ultima_actividad` y `fecha_expiracion` (TTL). Se llama en **cada** request que toca una BD del usuario (`_touch_database` en `database_routes.py`), no solo en operaciones explícitas de "actividad".

### `sp_LimpiarBDsInactivas`
**Parámetros:** `@dias_gracia = 7`

Job de limpieza (no expuesto por HTTP, pensado para un scheduler externo que no está en este repo): pausa las BDs `ACTIVA` cuyo `fecha_expiracion` ya pasó, y elimina (borra credenciales, desliga servicios, marca `ELIMINADA`) las que llevan `@dias_gracia` días `PAUSADA`. Audita `TTL_PAUSA`/`TTL_ELIMINACION` con `usuario_sistema = 'SISTEMA_TTL'`.

---

## 3. Funciones de lectura (Views/Functions)

### `fn_BasesDeDatosPorUsuario(@id_usuario)` — TVF
Lista las BDs de un usuario, con el nombre/versión del motor vía `JOIN Motores`.

> **Fix aplicado esta sesión:** no filtraba `estado <> 'ELIMINADA'`, por lo que `GET /databases` mostraba bases ya borradas para siempre. Se agregó el filtro.

### `fn_ObtenerBD(@id_bd, @id_usuario)` — TVF
Detalle de una BD puntual, con el mismo `JOIN Motores`. El `WHERE bd.id_usuario = @id_usuario` es lo que impide pedir el detalle de una BD ajena aunque se adivine el `id_bd`. (A diferencia de la función de listado, esta sí puede devolver una `ELIMINADA` si se pide su ID explícito — es una consulta puntual, no un listado.)

### `fn_DiasRestantesTTL(@id_bd)` — escalar, `RETURNS INT`
Días restantes antes de que expire el TTL (`NULL` si la BD no está `ACTIVA`).

> **Bug real encontrado y corregido esta sesión (lado Python, no SQL):** el backend la llamaba como `SELECT fn_DiasRestantesTTL(?)`, sin prefijo de esquema. SQL Server exige el prefijo (`dbo.fn_DiasRestantesTTL(...)`) para funciones **escalares** invocadas en un `SELECT` — a diferencia de las TVF usadas en `FROM` — y sin él responde `'fn_DiasRestantesTTL' is not a recognized function name`, como si la función no existiera, cuando sí existía. Confirmado probando ambas formas directo contra producción.

### `fn_PorcentajeEspacioUsado(@id_bd)` — escalar, `RETURNS DECIMAL(5,2)`
Mismo bug de prefijo que la anterior, mismo fix.

### `fn_PuertosAsignados()` — TVF, sin parámetros
**Nueva esta sesión.** Devuelve los puertos host ya asignados a BDs no eliminadas — el backend la usa como optimización para evitar colisiones al elegir un puerto nuevo (`PortAllocator`); si la función falla o no existe, el backend igual funciona cayendo a asignación aleatoria + reintento ante conflicto real de Docker, así que nunca fue un bloqueante duro, solo reduce reintentos.

### `fn_MotoresDisponibles()` — TVF, sin parámetros
**Nueva esta sesión.** `SELECT nombre AS nombre_motor, version AS version_motor FROM Motores WHERE activo = 1`. Backea `GET /databases/engines`. Devuelve **todo** lo que está activo en el catálogo `Motores` (hoy incluye `SQLSERVER`), no solo lo que el provisioner puede aprovisionar de verdad — es `DatabaseService.list_available_engines` (Python) quien filtra el resultado contra `PROVISIONING_SUPPORTED_ENGINES` (hoy `MYSQL,POSTGRES`) antes de devolverlo, para no ofrecer en el picker un motor que luego fallaría al crear.

### `fn_MetricasPublicas()` — TVF, sin parámetros
**Nueva esta sesión.** Backea `GET /metrics` (landing page). Una sola fila:

| Columna | Definición |
|---|---|
| `total_usuarios` | `COUNT(*)` de `Usuarios` (todas las cuentas registradas alguna vez) |
| `total_bases_datos` | `COUNT(*)` de `BasesDeDatos` (incluye eliminadas — total histórico) |
| `bases_datos_activas` | `COUNT(*)` con `estado = 'ACTIVA'` ahora mismo |
| `total_logins` | `COUNT(*)` de eventos `LOGIN` con `resultado = 'EXITO'` (histórico) |
| `usuarios_activos` | `COUNT(DISTINCT id_usuario)` con login `EXITO` en los últimos 7 días |
| `disponibilidad` | % de operaciones `EXITO` vs total en `Auditoria`, últimas 24h (100% si no hubo actividad en la ventana — no hay monitor de uptime dedicado, esto es un proxy) |

### `fn_LoginsPorUsuario()` / `vw_Logins` — existían, sin usar
Ya existían en la base de datos antes de esta sesión pero **ningún código Python las invocaba**. `vw_Logins` filtra `Auditoria` por `evento = 'LOGIN'` (incluye tanto `EXITO` como `FALLO` — importante si se reutiliza para algo, no son solo logins exitosos). `fn_LoginsPorUsuario` agrega por usuario (`total_logins`, `ultimo_login_auditado`) usando esa view. Quedan documentadas por si son útiles para un futuro dashboard de administración; `fn_MetricasPublicas` no las reutiliza porque necesita el filtro `resultado = 'EXITO'` explícito, que `vw_Logins` no aplica.

### `fn_MiCelula(@id_usuario)` / `fn_ObtenerCelula(@id_celula)` / `fn_ServiciosPorCelula(@id_celula)` — TVF
Lectura de células (equipos/workspaces) y sus servicios. `fn_ObtenerCelula` no valida dueño porque el subdominio ya es información pública por definición.

### `fn_MetricasPorCelula()` — TVF, sin parámetros
Ya existía, sin usar por ningún endpoint. Agrega por célula: total de BDs/activas/pausadas/eliminadas, espacio total, servicios totales/caídos. Útil para un futuro dashboard de administración por célula.

---

## 4. Administración (rol ADMIN)

### `sp_ListarUsuarios` / `sp_ListarTodasLasBasesDatos`
Paginados (`@pagina`, `@tamano_pagina`, máx. 200/página), exigen `rol = 'ADMIN' AND activo = 1` en el solicitante o lanzan `THROW 54001`. **Llamados desde:** `app/admin/` ← `GET /admin/users`, `/admin/databases`.

### `sp_ActualizarRolUsuario`
Cambia el rol de otro usuario (`ESTUDIANTE`/`ADMIN`), exige ser ADMIN, prohíbe auto-cambiarse el rol. Audita `CAMBIAR_ROL`.

---

## 5. Células y servicios

### `sp_CrearCelula` / `sp_CrearServicio` / `sp_CambiarEstadoServicio`
Creación de "células" (equipos, con subdominio propio) y "servicios" (containers/apps dentro de una célula, cada uno con su propio subdominio calculado por un trigger `AFTER INSERT`, no por el SP). Ver `app/celulas/`.

---

## 6. Auditoría genérica

### `sp_RegistrarEvento`
**Parámetros:** `@evento, @id_usuario, @id_bd, @descripcion, @ip, @resultado, @datos_adicionales`

Inserta un evento genérico en `Auditoria` — usado para eventos que no tienen su propio SP dedicado (`LOGOUT`, `RENOVAR_TOKEN`, `ERROR`, etc. — ver `CHK_auditoria_evento` para la lista completa de valores permitidos). `@evento` debe estar en esa constraint o SQL Server rechaza el INSERT con un mensaje que ya nombra la constraint. **Llamado desde:** `register_event` ← `POST /audit/events`.

---

## Nota sobre el origen de estos scripts

El `README.md` de este repositorio menciona "22 scripts de `MessageBrokerDB`" pero **esos archivos `.sql` no están versionados en este repositorio** — viven fuera de control de versiones, aplicados directamente contra el SQL Server de producción. Este documento se generó consultando `OBJECT_DEFINITION()` directo contra la base de datos real, no desde una copia local, y refleja el estado exacto tras los fixes de esta sesión (commits en `backend-core`, más los `ALTER`/`CREATE` aplicados directo a producción para `fn_BasesDeDatosPorUsuario`, `sp_CrearBD`, `sp_ReanudarBD`, `fn_PuertosAsignados`, `fn_MetricasPublicas` y `CHK_auditoria_evento`).

**Recomendación:** si el equipo de base de datos no lo tiene ya, vale la pena empezar a versionar esos scripts en algún repo (aunque sea este mismo, en una carpeta `database/`) — ahora mismo la única fuente de verdad es la base de datos de producción en sí.

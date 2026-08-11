# Nuevos endpoints — módulos Databases, Admin y Células

Este documento acompaña la implementación de los módulos `app/databases`, `app/admin`
y `app/celulas`, agregados para cubrir el alcance descrito en el reto
"Database-Centric Architecture" (aprovisionamiento de bases de datos, límites de
seguridad, y direccionamiento de subdominios por célula).

Siguiendo la arquitectura del proyecto, **estos endpoints no contienen lógica de
negocio**: son mediadores que invocan Stored Procedures. Cada SP referenciada abajo
debe implementarse en SQL Server; hasta entonces, los endpoints devolverán `503`
(`StoredProcedureExecutionError`) al no encontrar el procedimiento.

## Bug corregido

`SQLServerRepository.provision_database` estaba fusionado por error con la firma de
`_first_row` (dos métodos `_first_row` duplicados en el archivo), dejando el método
`provision_database` inexistente en la clase. Esto habría producido un
`AttributeError` en producción la primera vez que un usuario se autenticara por
OAuth, ya que `auth_service.py` lo invoca en cada registro. Se corrigió en
`app/repositories/implementations/sqlserver_repository.py`.

## Databases — `/databases`

| Método | Ruta | SP requerido | Notas |
|---|---|---|---|
| POST | `/databases` | `sp_AprovisionarBaseDatos` | Ya existía; ahora también expuesto para aprovisionar bajo demanda (no solo en signup). |
| GET | `/databases` | `sp_ListarBasesDatosPorUsuario` | Nuevo. |
| GET | `/databases/{id}` | `sp_ObtenerBaseDatos` | Nuevo. 404 si no hay filas. |
| DELETE | `/databases/{id}` | `sp_EliminarBaseDatos` | Nuevo. |
| GET | `/databases/{id}/credentials` | `sp_ObtenerCredencialesDB` | Ya existía en el repositorio, nunca estaba conectado a una ruta HTTP. |
| GET | `/databases/{id}/usage` | `sp_ObtenerUsoBaseDatos` | Nuevo. Debe devolver límite/uso de almacenamiento y conexiones activas/máximas. |
| POST | `/databases/{id}/pause` | `sp_PausarBaseDatos` | Nuevo. Pensado para uso manual o por el job de TTL. |
| POST | `/databases/{id}/resume` | `sp_ReanudarBaseDatos` | Nuevo. |

**Campos esperados por fila** (nombres flexibles; el mapeo acepta alias en inglés/español,
ver `_normalized()` en `database_service.py`):
`DatabaseId`/`BaseDatosId`, `Name`/`Nombre`, `Status`/`Estado`, `CreatedAt`/`FechaCreacion`,
`TtlExpiresAt`/`FechaExpiracion`, `StorageLimitMb`/`LimiteAlmacenamientoMb`,
`StorageUsedMb`/`AlmacenamientoUsadoMb`, `ActiveConnections`/`ConexionesActivas`,
`MaxConnections`/`MaxConexiones`.

## Admin — `/admin` (requiere rol `admin`, vía `require_role("admin")`)

| Método | Ruta | SP requerido |
|---|---|---|
| GET | `/admin/users` | `sp_ListarUsuarios` |
| PATCH | `/admin/users/{id}/role` | `sp_ActualizarRolUsuario` |
| GET | `/admin/databases` | `sp_ListarTodasLasBasesDatos` |

`require_role` ya existía en `auth_dependencies.py` pero no estaba conectado a
ningún endpoint; ahora protege todo este módulo. El rol se lee del claim `role`
del JWT (ya emitido hoy por `auth_service.py`).

## Células — `/celulas`

Implementa el esquema de direccionamiento `[celula].andrescortes.dev` y
`[servicio].[celula].andrescortes.dev` descrito en el documento del reto.

| Método | Ruta | SP requerido |
|---|---|---|
| POST | `/celulas` | `sp_CrearCelula` |
| GET | `/celulas` | `sp_ListarCelulasPorUsuario` |
| GET | `/celulas/{id}` | `sp_ObtenerCelula` |
| POST | `/celulas/{id}/services` | `sp_RegistrarServicioCelula` |
| GET | `/celulas/{id}/services` | `sp_ListarServiciosCelula` |
| DELETE | `/celulas/{id}/services/{service_id}` | `sp_EliminarServicioCelula` |

El campo `domain` se deriva automáticamente si el SP no lo devuelve
(`{nombre}.andrescortes.dev` para células, `{servicio}.{celula}.{dominio raíz}`
para servicios). El dominio raíz es parametrizable vía la variable de entorno
`APP_ROOT_DOMAIN` (`AppSettings.root_domain` en `app/core/config.py`); si no se
define, usa `andrescortes.dev` como valor por defecto.

## Pendiente / fuera de alcance de este cambio

- Automatización real de DNS/reverse proxy para los subdominios de célula
  (hoy `infra/nginx` es estático).
- Job de TTL que invoque `pause_database` automáticamente por inactividad.
- Enforcement de cuota de almacenamiento antes de escrituras (vive en SQL Server,
  no en este backend).

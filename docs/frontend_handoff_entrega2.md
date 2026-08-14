# Handoff para frontend-landing — Entrega #2

Cambios en el backend que requieren (o habilitan) ajustes en `frontend-landing`. Todo lo de abajo ya está desplegado en producción y probado contra la API real.

---

## 1. Métricas de la landing — sin acción requerida ✅

`MetricsSection.tsx` / `useMetrics.ts` / `PublicMetrics` ya estaban implementados correctamente esperando `GET /metrics` — el problema era que **ese endpoint no existía en el backend** (devolvía 404). Ya existe, con exactamente el contrato que el frontend espera:

```json
{
  "totalUsers": 7,
  "totalDatabases": 12,
  "activeDatabases": 3,
  "totalLogins": 33,
  "activeUsers": 6,
  "availability": 79.66
}
```

No auth, no rate-limit agresivo (60/min, suficiente para el polling de 30s que ya hace `useMetrics`). No hace falta tocar nada del lado del frontend para esto — ya debería estar funcionando en el sitio.

---

## 2. `DatabaseInstance` — dos campos nuevos en la API

`GET /databases` y `GET /databases/{id}` ahora devuelven dos campos que antes no existían:

```diff
 export interface DatabaseInstance {
   database_id: string;
   name: string | null;
   status: "active" | "paused" | "deleted" | "unknown";
+  engine: string | null;        // ej. "MYSQL" -- motor real, no asumido
   host: string | null;
   port: number | null;
+  last_activity: string | null; // ISO 8601, igual que created_at
   created_at: string | null;
   ttl_expires_at: string | null;
   storage_limit_mb: number | null;
   storage_used_mb: number | null;
 }
```

Archivo: `apps/landing/lib/api/types.ts`.

### 2.1 `CredentialsCard.tsx` — el motor estaba hardcodeado, y mal

```tsx
// apps/landing/components/dashboard/CredentialsCard.tsx (~línea 78)

// ANTES (incorrecto -- el motor real es MySQL, no SQL Server):
<div className="rounded-xl border border-line bg-background/60 px-3 py-2">
  <p className="text-xs text-muted">Motor</p>
  {/* Asumimos SQL Server basado en la documentación del proyecto */}
  <p className="mt-1 font-medium">SQL Server</p>
</div>

// DESPUÉS:
<div className="rounded-xl border border-line bg-background/60 px-3 py-2">
  <p className="text-xs text-muted">Motor</p>
  <p className="mt-1 font-medium">{database.engine || "N/A"}</p>
</div>
```

SQL Server es donde vive la *metadata* de la plataforma (usuarios, auditoría, etc.) — pero la base de datos que el usuario realmente recibe y usa es **MySQL** (contenedor real provisionado por el backend). El valor hardcodeado era simplemente incorrecto.

### 2.2 `StorageMonitor.tsx` — falta "Última actividad"

El rubro pide mostrarla en el dashboard y actualmente no está en ningún lado de la UI, aunque el dato siempre existió en SQL Server.

```tsx
// apps/landing/components/dashboard/StorageMonitor.tsx (~línea 78, dentro del <dl className="mt-6 grid gap-3 sm:grid-cols-3">)

// Agregar una cuarta celda (ajustar el grid a sm:grid-cols-4, o a 2 filas de 2):
<div className="rounded-xl border border-line bg-background/60 px-3 py-3">
  <dt className="text-xs text-muted">Última actividad</dt>
  <dd className="mt-1 text-sm font-medium">
    {formatDate(database.last_activity)}
  </dd>
</div>
```

---

## 3. Host/puerto en el dashboard — ya no deberían salir "N/A"

`GET /databases/{id}/credentials` antes devolvía `host` y `port` (y `database_name`) siempre en `null` — el stored procedure que los genera (`sp_ObtenerCredenciales`) nunca los tuvo, viven en otra tabla. El backend ahora los combina automáticamente antes de responder. **No requiere ningún cambio en `CredentialsCard.tsx`** — ya lee `credentials?.host`/`credentials?.port`, simplemente ahora van a venir con datos reales en vez de `"N/A"`.

---

## 4. Resumir una base de datos pausada — ya funciona de verdad

`POST /databases/{id}/resume` estaba roto **incondicionalmente** desde antes de esta entrega (siempre devolvía 503, sin importar el estado). Ya funciona: `200` si estaba pausada, `400` con mensaje claro si ya estaba activa. Si en algún momento agregan un botón de "reanudar" en el dashboard (hoy no vi ninguno en `StorageMonitor`/`CredentialsCard`), ya pueden confiar en la respuesta real del endpoint en vez de trabajar alrededor de un 503 fijo.

---

## Resumen de archivos a tocar

| Archivo | Cambio |
|---|---|
| `apps/landing/lib/api/types.ts` | Agregar `engine` y `last_activity` a `DatabaseInstance` |
| `apps/landing/components/dashboard/CredentialsCard.tsx` | Usar `database.engine` real en vez de `"SQL Server"` hardcodeado |
| `apps/landing/components/dashboard/StorageMonitor.tsx` | Agregar celda "Última actividad" con `database.last_activity` |

Nada más requiere cambios de este lado — landing con métricas y las credenciales completas (host/puerto/usuario/password) ya deberían verse bien en producción tal cual está el frontend hoy.

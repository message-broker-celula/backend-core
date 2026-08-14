# Handoff para frontend-landing — Entrega #3 (DNS + IA)

Revisé el código actual de `DnsView.tsx` y `AiView.tsx`: **ambos son 100%
mock/simulados hoy** (estado local, `Math.random()`, `setTimeout`) — no
llaman a ningún endpoint todavía. Este documento es el contrato real que
hay que conectar, más los ajustes de diseño necesarios porque el mock
actual no coincide con cómo quedó el backend.

---

## 0. Prerrequisito nuevo: la célula del usuario

Los subdominios (`DnsView`) se crean **dentro de una célula**, no sueltos.
Hasta hace un momento esto estaba roto para cualquier usuario real: crear
una célula nunca vinculaba al usuario con ella, así que `GET /celulas`
devolvía vacío siempre (ya lo arreglé — ver más abajo). El flujo real que
necesita el frontend, antes de mostrar `DnsView`:

```
GET /celulas
```
```json
{ "celulas": [{ "celula_id": "…", "name": "alpha", "domain": "https://alpha.andrescortes.dev", "owner_subject": null }] }
```

- Si `celulas` viene **vacío**, el usuario todavía no tiene una — hay que
  ofrecerle crear una primero:
  ```
  POST /celulas
  { "name": "alpha" }
  ```
  (`name`: 1–63 caracteres). El backend vincula automáticamente al usuario
  con la célula recién creada.
- Si ya tiene una o más, se usa `celula_id` de la primera (por ahora el
  modelo es una célula "activa" por usuario) para todas las llamadas de
  `DnsView` de abajo.

---

## 1. Subdominios DNS (`DnsView.tsx`)

### Lo que hay que cambiar del diseño actual

El formulario actual pide **tipo de registro** (A/CNAME) y **valor**
(IP/URL) — el backend **no** acepta eso. Siempre crea un registro `A`
"proxied" apuntando a la IP del servidor, decidida por el backend, no por
el usuario. El único dato que el usuario elige es el **nombre**.

También el dominio mostrado (`.mbro.coderhivex.com`, fijo) no es correcto
— es `[nombre].[celula].coderhivex.com`, donde `celula` es el nombre real
de la célula del usuario (de la sección 0), no un string fijo.

### Crear un subdominio

```
POST /celulas/{celula_id}/services
Authorization: Bearer <token>

{ "service_name": "miapp" }
```

`service_name`: 1–63 caracteres, minúsculas, alfanumérico y guiones (no al
inicio/final) — mismo formato que un label DNS real. Si no cumple, el
backend responde `422` antes de intentar nada.

```json
// 201
{
  "service_id": "…",
  "celula_id": "…",
  "service_name": "miapp",
  "service_type": "other",
  "domain": "https://miapp.alpha.coderhivex.com",
  "database_id": null
}
```

Errores:

| Código | Motivo |
|---|---|
| `422` | Nombre inválido como label DNS |
| `400` | Ya existe ese nombre en la célula, célula suspendida, o **límite de 5 subdominios por célula alcanzado** |
| `503` | El proveedor DNS no respondió (ver estado de verificación abajo) |

### Listar subdominios

```
GET /celulas/{celula_id}/services
```
```json
{ "services": [{ "service_id": "…", "domain": "https://miapp.alpha.coderhivex.com", "service_type": "other", ... }] }
```

### Verificar propagación / HTTPS

```
GET /celulas/{celula_id}/services/{service_id}/dns-status
```
```json
{ "fqdn": "miapp.alpha.coderhivex.com", "propagated": true }
```

Útil para un estado "Propagando…" → "Activo" real en vez del `setTimeout`
simulado actual — pollear este endpoint cada pocos segundos tras crear.

### Eliminar

```
DELETE /celulas/{celula_id}/services/{service_id}
```
`204` sin cuerpo. Borra el registro DNS real y marca el servicio eliminado
— ya no es reversible como antes (que solo "pausaba").

---

## 2. AI Gateway (`AiView.tsx`)

### Lo que hay que cambiar del diseño actual

El mock actual asume **varias API keys nombradas por usuario**, con un
contador de peticiones por clave. El backend real permite **una sola clave
activa por usuario a la vez** (hay que rotarla o revocarla para tener una
nueva), sin nombre personalizado, y el consumo se consulta aparte (no va
embebido en la lista de claves). Conviene simplificar la UI a: "tu clave
actual" + botones rotar/revocar, en vez de una tabla de múltiples claves.

### Emitir la clave (solo si el usuario no tiene una activa)

```
POST /ai/api-key
Authorization: Bearer <token>

{ "organization": null, "intended_use": null }   // ambos opcionales
```

```json
// 201 -- api_key solo se muestra ACA, no se puede volver a pedir
{
  "client_id": 7,
  "api_key": "sk_live_9tK2h...",
  "key_prefix": "sk_live_9tK2",
  "base_url": "https://api.idempotencia.andrescortes.dev/v1"
}
```

El nombre/correo que se registra en el gateway se toma del perfil real del
usuario (no se manda desde el frontend). Si ya tiene una clave activa,
responde `400` — hay que ofrecer rotar en vez de "crear otra".

### Estado de la clave actual

```
GET /ai/api-key
```
```json
{
  "client_id": 7,
  "key_prefix": "sk_live_9tK2",
  "status": "approved",
  "can_call_api": true,
  "limits": { "requests_per_minute": 20, "daily_token_limit": 100000, "monthly_token_limit": 2000000 },
  "last_used_at": "2026-08-13T16:20:11"
}
```
`400` si el usuario todavía no tiene ninguna clave — usar eso para decidir
si mostrar el botón "Generar" o el panel de "tu clave".

### Rotar

```
POST /ai/api-key/rotate
```
Misma forma de respuesta que la emisión — la clave vieja deja de funcionar
al instante, sin período de gracia. Mostrar el mismo modal de "cópiala
ahora, no la vas a volver a ver" que ya existe en el mock.

### Revocar

```
DELETE /ai/api-key
```
```json
{ "detail": "AI Gateway key revoked" }
```

### Consumo

```
GET /ai/usage?start=2026-08-01&end=2026-08-06   // ambos opcionales
```
```json
{
  "start": "2026-08-01", "end": "2026-08-06",
  "total_requests": 412, "prompt_tokens": 31200, "completion_tokens": 18700, "total_tokens": 49900,
  "by_day": [...], "by_model": [...], "by_endpoint": [...]
}
```

---

## Estado real de verificación (importante)

El código de ambas funcionalidades está desplegado y probado con tests
unitarios, pero **ninguna de las dos se puede probar de punta a punta
todavía** contra los servicios externos reales:

- **DNS**: el token de Cloudflare sigue rechazando la IP del servidor
  (falta que alguien ajuste el *Client IP Filtering* en su dashboard). Hasta
  que eso se resuelva, `POST /celulas/{id}/services` va a responder `503`
  aunque el resto del flujo esté bien conectado.
- **IA**: el hostname ya se corrigió (`qa.api.idempotencia.andrescortes.dev`,
  confirmado en vivo, responde `/public/models` correctamente) y el backend
  ya le llega bien. Pero `POST /ai/api-key` sigue devolviendo `503` porque
  el gateway responde `400`: `"EXTERNAL_OWNER_USER_ID=1 no existe en la
  tabla Users. Crea la cuenta de servicio antes de habilitar el alta
  externa."` — les falta un paso de configuración interna a ellos, no es
  algo del lado de este backend.

Recomendación: conecten el frontend contra este contrato ahora (para no
bloquearse), y esperen la confirmación de que ambos externos ya responden
antes de dar por buena la prueba end-to-end real.

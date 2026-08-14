# Handoff para frontend-landing — Autoservicio de creación de bases de datos

Hoy, justo después del login, `useProvisioning`/`provisionDatabase(token)`
llama a `POST /databases` con el body completamente vacío — el usuario
nunca elige nada, y siempre recibe una base MySQL con nombre generado. Eso
sigue funcionando (compatibilidad hacia atrás), pero ya no es el flujo que
queremos: el usuario debe poder **elegir el motor** (de los que de verdad
estén disponibles), **ponerle nombre** a su base, y **crear varias**
(hasta un límite).

Este documento describe el contrato real ya desplegado para armar eso.

---

## 1. Dejar de auto-crear en el login

Quitar la llamada automática a `POST /databases` justo después de OAuth.
En su lugar, al entrar al dashboard:

- Si `GET /databases` devuelve una lista vacía → mostrar un estado vacío
  ("Todavía no tienes bases de datos") con un botón **Crear base de datos**.
- Si ya tiene alguna → mostrarlas normalmente, con el mismo botón
  disponible para crear una adicional (hasta el límite, ver sección 4).

## 2. Nuevo endpoint: `GET /databases/engines`

Devuelve exactamente los motores/versiones que se pueden pedir *ahora
mismo* en este deployment — ya filtrado contra lo que el provisioner
realmente sabe levantar, así que no hace falta (ni conviene) hardcodear la
lista en el frontend.

```
GET /databases/engines
Authorization: Bearer <token>
```

```json
{
  "engines": [
    { "nombre_motor": "MYSQL", "version_motor": "8.0" },
    { "nombre_motor": "MYSQL", "version_motor": "8.4" },
    { "nombre_motor": "POSTGRES", "version_motor": "16" }
  ]
}
```

Verificado en vivo contra producción — esta es la respuesta real hoy.
Úsalo para poblar el selector de motor (agrupando por `nombre_motor`, con
`version_motor` como sub-selección si hay más de una versión del mismo
motor, como pasa con MySQL 8.0/8.4).

**PostgreSQL ya es una opción real**, no un "próximamente" — se aprovisiona
exactamente igual que MySQL, mismo endpoint, mismas garantías.

## 3. Formulario de creación

```
POST /databases
Authorization: Bearer <token>

{
  "nombre_motor": "POSTGRES",
  "version_motor": "16",
  "nombre_bd": "inventario"
}
```

```json
// 201
{ "database_id": "…", "status": "active", "detail": "Database created" }
```

- `nombre_motor`/`version_motor`: los que el usuario eligió del selector
  (sección 2) — no permitir texto libre acá, solo lo que devolvió
  `GET /databases/engines`, para no dejar que el usuario pida algo que el
  backend va a rechazar.
- `nombre_bd`: texto libre del usuario. El backend lo sanitiza
  automáticamente (minúsculas, solo `a-z0-9_`, máximo 40 caracteres); si
  queda vacío después de sanitizar, genera uno por defecto. Si quieres
  mostrar una vista previa de cómo va a quedar el nombre real, podés
  replicar esa misma regla en el cliente, pero no es obligatorio — el
  backend nunca falla por un nombre "raro", simplemente lo limpia.

Errores a manejar en el formulario:

| Código | Motivo |
|---|---|
| `400` | Motor no soportado, nombre duplicado, o **límite de 5 bases de datos alcanzado** (ver sección 4) |
| `503` | El provisioner está sin capacidad en este momento (tope de contenedores simultáneos del VPS) — mostrar "intenta de nuevo en un momento", no es un error del usuario |

## 4. Límite de 5 bases de datos por usuario

Es un límite fijo (no configurable, no hay endpoint de cuota aparte) que
cuenta **todas** las bases activas del usuario, sin importar el motor. Para
mostrar "3 de 5" o deshabilitar el botón de crear al llegar al tope, basta
con contar el arreglo que ya devuelve `GET /databases` (longitud de
`databases`) — no hace falta pedir nada nuevo para esto.

Si por una condición de carrera (dos pestañas abiertas, por ejemplo) el
usuario de todas formas llega a `POST /databases` habiendo alcanzado el
límite, el backend responde `400` con un mensaje claro — mostrarlo tal
cual, no hace falta un mensaje genérico de error.

## 5. Resumen de contrato

| Endpoint | Cambio |
|---|---|
| `GET /databases/engines` | **Nuevo.** Motores/versiones disponibles para el selector. |
| `POST /databases` | Sin cambios de forma — pero ahora se espera mandar `nombre_motor`/`version_motor`/`nombre_bd` explícitos en vez de un body vacío. |
| `GET /databases` | Sin cambios — úsalo para contar cuántas tiene el usuario (sección 4). |

## Estado de verificación

`GET /databases/engines` está desplegado y probado en vivo contra
producción (respuesta real confirmada arriba). PostgreSQL como motor
también está verificado en vivo: se creó una base real, se conectó de
verdad, y se borró — no es solo un registro de catálogo sin implementación
detrás.

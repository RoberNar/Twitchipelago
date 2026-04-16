# 🏝️ Twitchipelago — Project Handoff

Este documento es el punto de retoma. Léelo completo antes de continuar.

---

## ✅ Estado Actual — Todo lo que está funcionando

### Fase 1 — Estructura Base (completa)
- [x] Arquitectura de carpetas: `bot/`, `panel/`, `server.py`, `database.py`
- [x] Entorno virtual Python con `requirements.txt`
- [x] `config.json` migrado a SQLAlchemy + SQLite (local) / PostgreSQL (Railway)

### Fase 2 — Bot Python (completa)
- [x] `bot/archipelago_client.py`: WebSocket persistente, cálculo de progreso AP
- [x] `bot/rewards.py`: **4 modos de trigger** — `bits_fixed`, `bits_accumulation`, `sub`, `sub_goal`
  - `bits_fixed`: cantidad exacta de bits = 1 hint
  - `bits_accumulation`: barra acumuladora (cada N bits = 1 hint, luego reset)
  - `sub`: cada sub/renovación individual activa la recompensa
  - `sub_goal`: acumula N subs → 1 hint + reset
  - Todos los modos respetan cooldowns y se procesan en `process_event()`
- [x] `bot/twitch_client.py`: multicanal, eventos bits/sub/gift_sub, `_handle_cheer()` usa `process_event()`
- [x] `bot/main.py`: orquestador asíncrono

### Fase 3 — Panel de Control React (completa)
- [x] Dashboard moderno dark mode (Vite + React + TailwindCSS)
- [x] **Login con Twitch OAuth** (flujo completo: redirect → callback → sesión cookie)
- [x] Header con avatar del usuario, nombre, botón logout y **nav links** (Panel / Tracker / Stats-pronto)
- [x] Gestión de jugadores (Participant Roster: canal Twitch ↔ slot AP)
- [x] **Pro Reward Configurator**: selector de trigger, config contextual por tipo, barra de progreso visual para acumulación, cooldown
- [x] Logs en tiempo real (sin auto-scroll invasivo al cargar)
- [x] "Configuración Avanzada del Bot" colapsable (oculto por defecto, ya cargado desde config)
- [x] Chat Announcer configurable

### Fase 4 — Public Tracker (completa)
- [x] Ruta `/tracker` pública (no requiere login)
- [x] Leaderboard con avatares, barras de progreso AP, hints contados

### DB & Auth (completo)
- [x] Modelos: `User`, `ArchiConfig`, `TwitchConfig`, `AnnouncerConfig`, `Player`, `Reward`, `RewardTrigger`, `EventLog`
- [x] Todos con `user_id` FK → soporte multi-usuario real
- [x] `get_config_as_json(user_id)` / `save_config_from_json(data, user_id)` serializan los 4 modos de reward
- [x] `get_or_create_user()` crea/actualiza usuario en OAuth callback
- [x] Migración automática desde `config.json` si la DB está vacía
- [x] `session.expunge(user)` para evitar errores "detached instance" de SQLAlchemy

### Server (completo)
- [x] `server.py` con Flask + Flask-CORS (credentials=True)
- [x] Rutas auth: `/auth/twitch`, `/auth/callback`, `/auth/me`, `/auth/logout`
- [x] `@require_auth` en todos los endpoints de API
- [x] `get_redirect_uri()` lee `TWITCH_REDIRECT_URI` desde `.env` (configurable exacto)
- [x] `/auth/debug` endpoint para diagnóstico del redirect URI
- [x] `load_dotenv()` al inicio para dev local
- [x] Fallback: si las credenciales no están en env var, las lee desde la DB

---

## 🔑 Variables de Entorno requeridas

### Local (`.env`)
```env
SECRET_KEY=<clave-larga-aleatoria>
TWITCH_CLIENT_ID=<tu-client-id>
TWITCH_CLIENT_SECRET=<tu-client-secret>
TWITCH_REDIRECT_URI=http://localhost:5000/auth/callback
```

### Railway (environment variables)
```env
SECRET_KEY=<clave-larga-aleatoria — NUNCA la misma que dev!>
TWITCH_CLIENT_ID=<tu-client-id>
TWITCH_CLIENT_SECRET=<tu-client-secret>
DATABASE_URL=<postgresql://... — Railway lo genera automático>
BACKEND_URL=https://<tu-dominio-railway>.up.railway.app
FRONTEND_URL=https://<tu-dominio-frontend>.up.railway.app
TWITCH_REDIRECT_URI=https://<tu-dominio-railway>.up.railway.app/auth/callback
```
> ⚠️ El `TWITCH_REDIRECT_URI` de producción también hay que agregarlo en https://dev.twitch.tv/console → tu app → OAuth Redirect URLs

---

## 🔌 Comandos de Inicio Rápido (local)

```powershell
# Terminal 1 — Backend
& .\venv\Scripts\Activate.ps1
python server.py

# Terminal 2 — Frontend
cd panel
npm run dev
```

- Panel: `http://localhost:5173`
- Tracker público: `http://localhost:5173/tracker`
- Debug OAuth: `http://localhost:5000/auth/debug`

---

## 🚀 PHASE 3 — Dockerización y Deploy en Railway (PENDIENTE)

### Arquitectura objetivo

```
Railway
├── Service A: Backend (Python Flask)  ← Dockerfile.backend
│   ├── server.py (API + OAuth)
│   ├── main.py  (bot Twitch + AP)
│   └── database.py → PostgreSQL plugin de Railway
└── Service B: Frontend (Node build → Nginx)  ← Dockerfile.frontend
    └── panel/  (Vite build servido por Nginx)
```

### Paso 1 — `Dockerfile` del backend

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Compilar el frontend estático dentro del mismo contenedor (opción monolítica)
# O servir solo el API aquí y el frontend en otro servicio
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "server:app"]
```

> Hay que agregar `gunicorn` a `requirements.txt`.

### Paso 2 — `Dockerfile` del frontend

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY panel/package*.json ./
RUN npm ci
COPY panel/ .
# La URL del backend va embebida en el build
ARG VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

> El `nginx.conf` necesita un fallback a `index.html` para que React Router funcione.

### Paso 3 — Variables de entorno en `App.jsx`

Actualmente `App.jsx` tiene hardcodeado `const API = 'http://localhost:5000'`.  
Hay que cambiarlo a:
```js
const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';
```
Y en `.env.production` del panel:
```env
VITE_API_URL=https://<tu-backend-railway>.up.railway.app
```

### Paso 4 — `railway.json` (configuración de Railway)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile.backend" },
  "deploy": { "startCommand": "gunicorn -b 0.0.0.0:$PORT server:app" }
}
```

### Paso 5 — PostgreSQL en Railway

Railway provee un plugin PostgreSQL que te da `DATABASE_URL` automáticamente.  
`database.py` ya tiene soporte para esto: usa `DATABASE_URL` si está definida, si no usa SQLite local.

### Paso 6 — Registrar la URL de Railway en Twitch

Cuando tengas la URL final del backend en Railway, agregarla en:  
https://dev.twitch.tv/console → tu app → OAuth Redirect URLs  
```
https://<backend>.up.railway.app/auth/callback
```

### Paso 7 — Tracker URL en `_auto_announcer_loop()`

En `bot/twitch_client.py`, el announcer tiene hardcodeada la URL del tracker:
```python
"y quién va ganando en: http://localhost:5173/tracker !"
```
Cambiarla por la URL de producción del frontend antes de deployar.

---

---

## 🔴 Problemas Críticos / Pendientes (Última Sesión)

1. **Agrupación de Hints**: Se implementó una lógica en `_handle_cheer` para agrupar múltiples hints en un solo mensaje de Twitch (ej: bomba de 5 subs). 
   - **Estado**: La lógica de recolección funciona (los logs muestran los hints), pero el mensaje final aguerpado **no siempre aparece en el chat de Twitch**.
   - **Sospecha**: Posible fallo silencioso en `ch.send()` cuando el mensaje es muy largo o contiene caracteres especiales de AP. Se agregó un `try/except` con logs para cazar el error.

2. **Comando AP Erróneo**: Se descubrió que `!hint_progression` NO es un comando del servidor de Archipelago, sino un alias de clientes locales. 
   - **Solución**: Se cambió por `!hint` en `archipelago_client.py`. Ahora el servidor responde correctamente.

3. **Filtro antispam de AP**: Al mandar muchos `!hint` de golpe, Archipelago puede ignorar algunos o responder con "Timeout". El bot ahora tiene un timeout de 3s para no bloquearse.

4. **Logs de Debug**: Se cambiaron logs de `archipelago_client.py` a nivel `INFO` temporalmente para ver qué responde AP. **Pendiente**: Revertir a `DEBUG` cuando la comunicación sea estable.

5. **Diferencia en Tests**:
   - `!testsub N`: Simula N subs **separados** (no se agrupan).
   - `!testgiftsub N`: Simula UNA bomba de N (debería agruparse).

---

> 🏝️ **Siguiente sesión:** Investigar por qué `ch.send(msg_str)` en `twitch_client.py` (línea ~178) no está enviando el mensaje final acumulado a pesar de tener los datos.

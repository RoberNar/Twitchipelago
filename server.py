import os
import sys
import secrets
import requests as http_requests
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import Flask, request, jsonify, redirect, session, send_from_directory
from flask_cors import CORS
import subprocess

# Cargar variables de entorno desde .env (para desarrollo local)
load_dotenv()

from database import (
    init_db, get_config_as_json, save_config_from_json,
    get_channel_stats, get_all_stats, get_last_bot_session_start,
    log_event, get_or_create_user, get_user_by_id,
    get_recent_hints, get_hint_leaderboard,
)

dist_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'panel', 'dist')
app = Flask(__name__, static_folder=dist_folder)
CORS(app, supports_credentials=True, origins=["http://localhost:5173", os.environ.get("FRONTEND_URL", ""), os.environ.get("BACKEND_URL", "")])

# Llave secreta para firmar cookies de sesión
# En Railway, define SECRET_KEY como variable de entorno
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # True en producción con HTTPS

LOG_FILE = "bot.log"
bot_processes = {}

# Inicializar la base de datos al arrancar
init_db()

# ── OAuth Config ──────────────────────────────────────────────────────────────
TWITCH_AUTH_URL   = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL  = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL  = "https://api.twitch.tv/helix/users"

OAUTH_SCOPES = "user:read:email"

def _get_twitch_credentials():
    """Lee client_id y client_secret desde env vars (Railway) o desde la DB (local)."""
    client_id = os.environ.get("TWITCH_CLIENT_ID", "")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "")

    # Fallback: leer desde la DB si las env vars no están definidas
    if not client_id or not client_secret:
        try:
            from database import get_config_as_json
            cfg = get_config_as_json(user_id=1)
            tw = cfg.get("twitch", {})
            client_id = client_id or tw.get("client_id", "")
            client_secret = client_secret or tw.get("client_secret", "")
        except Exception:
            pass

    return client_id, client_secret

def get_twitch_client_id() -> str:
    return _get_twitch_credentials()[0]

def get_twitch_client_secret() -> str:
    return _get_twitch_credentials()[1]

def get_redirect_uri() -> str:
    # Si TWITCH_REDIRECT_URI está definido en .env, se usa exactamente como está
    # (debe coincidir EXACTAMENTE con lo que está registrado en dev.twitch.tv)
    explicit = os.environ.get("TWITCH_REDIRECT_URI", "")
    if explicit:
        return explicit
    base = os.environ.get("BACKEND_URL", "http://localhost:5000")
    return f"{base}/auth/callback"

@app.route("/auth/debug")
def auth_debug():
    """Muestra la configuración OAuth actual para facilitar el diagnóstico."""
    cid, csec = _get_twitch_credentials()
    return jsonify({
        "client_id": cid[:6] + "..." if cid else "VACÍO",
        "client_secret_set": bool(csec),
        "redirect_uri": get_redirect_uri(),
        "tip": "El redirect_uri debe coincidir EXACTAMENTE con el registrado en dev.twitch.tv"
    })

# ── Auth helper ───────────────────────────────────────────────────────────────

def get_current_user_id() -> int | None:
    """Retorna el user_id de la sesión activa, o None si no hay sesión."""
    return session.get("user_id")

def require_auth(f):
    """Decorador que requiere sesión activa. Retorna 401 si no hay sesión."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if get_current_user_id() is None:
            return jsonify({"status": "error", "message": "No autenticado. Haz login con Twitch."}), 401
        return f(*args, **kwargs)
    return wrapper

# ── Auth Endpoints ────────────────────────────────────────────────────────────

@app.route("/auth/twitch")
def auth_twitch():
    """Inicia el flujo OAuth de Twitch. El frontend redirige aquí al hacer click en Login."""
    state = secrets.token_hex(16)
    session["oauth_state"] = state

    params = urlencode({
        "client_id":     get_twitch_client_id(),
        "redirect_uri":  get_redirect_uri(),
        "response_type": "code",
        "scope":         OAUTH_SCOPES,
        "state":         state,
    })
    return redirect(f"{TWITCH_AUTH_URL}?{params}")


@app.route("/auth/callback")
def auth_callback():
    """Twitch llama a este endpoint con el código de autorización."""
    code  = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    frontend_url = os.environ.get("FRONTEND_URL", "/")

    if error or not code:
        return redirect(f"{frontend_url}?auth_error={error or 'unknown'}")

    if state != session.pop("oauth_state", None):
        return redirect(f"{frontend_url}?auth_error=invalid_state")

    # Intercambiar code por access_token
    try:
        token_resp = http_requests.post(TWITCH_TOKEN_URL, data={
            "client_id":     get_twitch_client_id(),
            "client_secret": get_twitch_client_secret(),
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  get_redirect_uri(),
        }, timeout=10)
        token_data = token_resp.json()
    except Exception as e:
        return redirect(f"{frontend_url}?auth_error=token_exchange_failed")

    access_token  = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    if not access_token:
        return redirect(f"{frontend_url}?auth_error=no_token")

    # Obtener datos del usuario desde la API de Twitch
    try:
        users_resp = http_requests.get(
            TWITCH_USERS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": get_twitch_client_id(),
            },
            timeout=10,
        )
        twitch_user = users_resp.json()["data"][0]
    except Exception:
        return redirect(f"{frontend_url}?auth_error=user_fetch_failed")

    # Crear o actualizar el usuario en la DB
    user = get_or_create_user(
        twitch_id=twitch_user["id"],
        display_name=twitch_user["display_name"],
        avatar_url=twitch_user.get("profile_image_url", ""),
        access_token=access_token,
        refresh_token=refresh_token,
    )

    # Guardar user_id en la sesión Flask
    session["user_id"] = user.id
    session.permanent = True

    return redirect(frontend_url)


@app.route("/auth/me")
def auth_me():
    """El frontend llama a este endpoint para saber si hay sesión activa."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"logged_in": False}), 200

    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"logged_in": False}), 200

    return jsonify({
        "logged_in": True,
        "user": {
            "id": user.id,
            "twitch_id": user.twitch_id,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        }
    })


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    """Destruye la sesión de Flask."""
    session.clear()
    return jsonify({"status": "ok", "message": "Sesión cerrada."})

# ── Config API (requiere autenticación) ───────────────────────────────────────

@app.route("/api/config", methods=["GET"])
@require_auth
def get_config():
    user_id = get_current_user_id()
    try:
        return jsonify(get_config_as_json(user_id=user_id))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/config", methods=["POST"])
@require_auth
def save_config():
    user_id = get_current_user_id()
    data = request.json
    try:
        save_config_from_json(data, user_id=user_id)
        # Limpiar el tracker específico de este puerto al guardar nueva config
        import json as _json
        try:
            ap_port = data.get("archipelago", {}).get("port")
            if ap_port:
                with open(f"public_state_{ap_port}.json", "w", encoding="utf-8") as f:
                    _json.dump({}, f)
        except Exception:
            pass
        return jsonify({"status": "ok", "message": "Configuración guardada exitosamente"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── Bot Control (requiere autenticación) ──────────────────────────────────────

def _read_process_output(user_id):
    proc = bot_processes.get(user_id)
    if proc and proc.stdout:
        return proc.stdout.read().decode("utf-8", errors="replace")
    return ""

@app.route("/api/bot/start", methods=["POST"])
@require_auth
def start_bot():
    global bot_processes
    user_id = get_current_user_id()
    print(f"--- [START_BOT] Iniciando para usuario {user_id} ---")
    
    proc = bot_processes.get(user_id)
    if proc and proc.poll() is None:
        print(f"--- [START_BOT] El bot ya está corriendo para usuario {user_id} (PID {proc.pid}) ---")
        return jsonify({"status": "error", "message": "El bot ya está corriendo para este usuario."}), 400
    
    try:
        print(f"--- [START_BOT] Escribiendo marcador en {LOG_FILE} ---")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"--- Bot iniciado desde panel web para usuario {user_id} ---\n")
        
        print(f"--- [START_BOT] Ejecutando subprocess: {sys.executable} main.py {user_id} ---")
        bot_processes[user_id] = subprocess.Popen(
            [sys.executable, "main.py", str(user_id)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=open(LOG_FILE, 'a'),
            stderr=subprocess.STDOUT
        )
        
        pid = bot_processes[user_id].pid
        print(f"--- [START_BOT] Subproceso lanzado con PID: {pid} ---")
        
        # Check for early termination
        import time
        print(f"--- [START_BOT] Esperando 0.5s para verificar estabilidad ---")
        time.sleep(0.5)
        
        return_code = bot_processes[user_id].poll()
        if return_code is not None:
            print(f"--- [START_BOT] ERROR: El subproceso terminó inmediatamente con código {return_code} ---")
            output = _read_process_output(user_id)
            return jsonify({"status": "error", "message": f"El bot terminó inesperadamente (código {return_code}): {output}"}), 500
            
        print(f"--- [START_BOT] Bot iniciado correctamente (PID {pid}) ---")
        return jsonify({"status": "ok", "message": "Bot iniciado exitosamente"})
    except Exception as e:
        print(f"--- [START_BOT] EXCEPCIÓN: {str(e)} ---")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/bot/stop", methods=["POST"])
@require_auth
def stop_bot():
    global bot_processes
    user_id = get_current_user_id()
    proc = bot_processes.get(user_id)
    if not proc or proc.poll() is not None:
        return jsonify({"status": "ok", "message": "El bot ya está detenido."})
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        del bot_processes[user_id]
        return jsonify({"status": "ok", "message": "Bot detenido."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/bot/status", methods=["GET"])
@require_auth
def bot_status():
    global bot_processes
    user_id = get_current_user_id()
    proc = bot_processes.get(user_id)
    is_running = proc is not None and proc.poll() is None
    
    # Podríamos leer el bot.log, pero idealmente cada usuario tendría su log.
    # Por simplicidad mantenemos uno glocal por ahora o el usuario lee los ultimos bots.
    return jsonify({"running": bool(is_running)})

@app.route("/api/bot/logs", methods=["GET"])
@require_auth
def get_bot_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({"logs": ""})
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return jsonify({"logs": "".join(f.readlines()[-100:])})
    except Exception as e:
        return jsonify({"logs": f"Error leyendo el log: {e}"})

# ── Logs ──────────────────────────────────────────────────────────────────────

@app.route("/api/logs", methods=["GET"])
@require_auth
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({"logs": []})
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return jsonify({"logs": f.readlines()[-100:]})
    except Exception as e:
        return jsonify({"logs": [f"Error leyendo el log: {e}"]})

# ── Tracker (público, no requiere sesión) ─────────────────────────────────────

@app.route("/api/tracker", methods=["GET"])
def get_tracker_state():
    import json
    port = request.args.get("port", "").strip()
    filename = f"public_state_{port}.json" if port else "public_state.json"
    if not os.path.exists(filename):
        return jsonify({})
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Stats (requiere autenticación) ────────────────────────────────────────────

@app.route("/api/stats/<channel>", methods=["GET"])
@require_auth
def get_stats(channel: str):
    try:
        return jsonify(get_channel_stats(channel))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
@require_auth
def get_stats_all():
    """Retorna stats de sesión + all-time + eventos detallados para todos los canales del usuario."""
    user_id = get_current_user_id()
    try:
        session_start = get_last_bot_session_start(LOG_FILE)
        data = get_all_stats(user_id=user_id, since=session_start)
        data["session_start"] = session_start.strftime("%Y-%m-%d %H:%M:%S") if session_start else None
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Hints (público, no requiere sesión) ─────────────────────────────────────────────────

@app.route("/api/hints/recent", methods=["GET"])
def get_hints_recent():
    """
    Retorna los últimos hints (event_type=hint_triggered).
    Params opcionales:
      - channel: filtrar por canal (defecto: todos)
      - limit:   cuántos retornar (defecto 10, máx 50)
    Público — no requiere login.
    """
    channel = request.args.get("channel", "").lower().strip()
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except ValueError:
        limit = 10
    try:
        hints = get_recent_hints(channel=channel, limit=limit)
        return jsonify(hints)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hints/leaderboard", methods=["GET"])
def get_hints_leaderboard():
    """
    Retorna el leaderboard de hints por usuario.
    Param opcional:
      - channel: filtrar por canal (defecto: todos)
    Público — no requiere login.
    """
    channel = request.args.get("channel", "").lower().strip()
    try:
        board = get_hint_leaderboard(channel=channel)
        return jsonify(board)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hints/channels", methods=["GET"])
def get_hints_channels():
    """
    Retorna la lista de canales distintos que tienen hints registrados.
    Público — no requiere login. Usado por el widget para poblar el dropdown.
    """
    from database import get_db_engine, EventLog
    from sqlalchemy.orm import Session as _Session
    try:
        engine = get_db_engine()
        with _Session(engine) as db_session:
            rows = (
                db_session.query(EventLog.channel)
                .filter(EventLog.event_type == "hint_triggered")
                .distinct()
                .all()
            )
        channels = sorted(set(r.channel for r in rows if r.channel))
        return jsonify(channels)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Servir archivos estáticos del Frontend (React SPA) ─────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    
    index_file = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_file):
        return send_from_directory(app.static_folder, "index.html")
    else:
        return "Frontend no compilado. Ejecuta 'npm run build' en la carpeta '/panel'.", 503

# ─────────────────────────────────────────────────────────────────────────────────────



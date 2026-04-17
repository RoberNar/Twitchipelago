"""
main.py
Punto de entrada del bot Twitchipelago.
Carga la configuración desde la base de datos SQLAlchemy y arranca el bot.
"""

import asyncio
import logging
import sys
import os

import aiohttp
from dotenv import load_dotenv
load_dotenv()

from database import init_db, load_config_from_db, save_config_from_json, get_config_as_json
from bot.archipelago_client import ArchipelagoClient
from bot.rewards import RewardManager
from bot.twitch_client import TwitchBot

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", mode="a", encoding="utf-8")
    ],
)
logger = logging.getLogger("main")

TOKEN_GENERATOR_URL = "https://twitchtokengenerator.com/"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_TOKEN_URL    = "https://id.twitch.tv/oauth2/token"


async def validate_and_refresh_twitch_token(cfg: dict) -> str | None:
    """
    Valida el access_token actual contra la API de Twitch.
    - Si es válido: retorna el mismo token.
    - Si está vencido: intenta refrescarlo con el refresh_token y guarda los nuevos en la DB.
    - Si el refresh también falla: loguea el error con el link para generarlo y retorna None.
    """
    access_token  = cfg.get("twitch_access_token", "").strip() or os.environ.get("TWITCH_ACCESS_TOKEN", "").strip()
    refresh_token = cfg.get("twitch_refresh_token", "").strip() or os.environ.get("TWITCH_REFRESH_TOKEN", "").strip()
    client_id     = cfg.get("twitch_client_id", "").strip() or os.environ.get("TWITCH_CLIENT_ID", "")
    client_secret = cfg.get("twitch_client_secret", "").strip() or os.environ.get("TWITCH_CLIENT_SECRET", "")

    async with aiohttp.ClientSession() as session:

        # 1. Validar el access_token
        logger.info("🔑 Validando Access Token de Twitch...")
        async with session.get(
            TWITCH_VALIDATE_URL,
            headers={"Authorization": f"OAuth {access_token}"}
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                expires_in = data.get("expires_in", 0)
                logger.info(f"   ✅ Token válido — expira en {expires_in // 3600}h {(expires_in % 3600) // 60}m")
                return access_token

            logger.warning(f"   ⚠️  Token inválido o expirado (HTTP {resp.status}). Intentando refrescar...")

        # 2. Intentar refresh
        if not refresh_token:
            logger.error(
                "❌ El Access Token expiró y no hay Refresh Token guardado.\n"
                f"   → Genera uno nuevo en: {TOKEN_GENERATOR_URL}\n"
                "   → Pégalo en Configuración Avanzada del panel y guarda."
            )
            return None

        if not client_id or not client_secret:
            logger.error(
                "❌ Faltan Client ID o Client Secret para refrescar el token.\n"
                f"   → Genera un token nuevo directamente en: {TOKEN_GENERATOR_URL}"
            )
            return None

        async with session.post(
            TWITCH_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "client_id":     client_id,
                "client_secret": client_secret,
            }
        ) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                new_access  = tokens.get("access_token", "")
                new_refresh = tokens.get("refresh_token", refresh_token)

                # Guardar los nuevos tokens en la DB
                try:
                    full_cfg = get_config_as_json(user_id=1)
                    full_cfg["twitch"]["access_token"]  = new_access
                    full_cfg["twitch"]["refresh_token"] = new_refresh
                    save_config_from_json(full_cfg, user_id=1)
                    logger.info("   ✅ Token refrescado automáticamente y guardado en la DB.")
                except Exception as e:
                    logger.warning(f"   ⚠️ Token refrescado pero no se pudo guardar en DB: {e}")

                return new_access

            error_body = await resp.text()
            logger.error(
                f"❌ No se pudo refrescar el token (HTTP {resp.status}): {error_body}\n"
                f"   → El Refresh Token puede estar revocado.\n"
                f"   → Genera un token nuevo en: {TOKEN_GENERATOR_URL}\n"
                "   → Pégalo en Configuración Avanzada del panel y guarda."
            )
            return None


async def main():
    # Inicializar DB (crea tablas y migra config.json si es la primera vez)
    init_db()

    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    cfg = load_config_from_db(user_id)

    logger.info("=" * 55)
    logger.info("  🏝️  Twitchipelago Bot — Iniciando Multicanal")
    logger.info("=" * 55)

    if not cfg["players"]:
        logger.error(
            "❌ No hay jugadores configurados. "
            "Abre el panel, añade al menos un jugador y guarda la configuración."
        )
        sys.exit(1)

    # Validar y refrescar token de Twitch antes de continuar
    raw_token = cfg.get("twitch_access_token", "").strip() or os.environ.get("TWITCH_ACCESS_TOKEN", "").strip()
    if not raw_token:
        logger.error(
            "❌ No hay Access Token de Twitch configurado.\n"
            f"   → Genera uno en: {TOKEN_GENERATOR_URL}\n"
            "   → Pégalo en Configuración Avanzada del panel y guarda."
        )
        sys.exit(1)

    twitch_token = await validate_and_refresh_twitch_token(cfg)
    if not twitch_token:
        sys.exit(1)

    # 1. Conectar al servidor de Archipelago por cada jugador
    ap_clients = {}
    connected_channels = []

    for player in cfg["players"]:
        tw_channel = player.get("twitch_channel", "").lower()
        ap_player = player.get("ap_player_name", "")

        if not tw_channel or not ap_player:
            continue

        client = ArchipelagoClient(
            host=cfg["ap_host"],
            port=cfg["ap_port"],
            player_name=ap_player,
            password=cfg["ap_password"],
        )

        try:
            await client.connect()
            ap_clients[tw_channel] = client
            connected_channels.append(tw_channel)
            logger.info(f"  ✅ Mapeo exitoso: Twitch #{tw_channel} -> AP '{ap_player}'")
        except Exception as e:
            logger.error(f"  ❌ Fallo al conectar jugador AP '{ap_player}': {e}")
            sys.exit(1)

    if not ap_clients:
        logger.error("❌ No se pudo establecer ninguna conexión a Archipelago válida.")
        sys.exit(1)

    # 2. Inicializar el gestor de recompensas
    reward_manager = RewardManager(
        rewards_config=cfg.get("rewards_config", [])
    )

    # 3. Arrancar el bot de Twitch
    bot = TwitchBot(
        token=twitch_token,
        client_id=cfg["twitch_client_id"],
        channels=connected_channels,
        ap_clients_map=ap_clients,
        reward_manager=reward_manager,
        user_id=user_id,
        ap_port=cfg["ap_port"],
    )

    try:
        logger.info("Iniciando bot de Twitch en canales: " + ", ".join(connected_channels))
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Deteniendo bot...")
    except Exception as e:
        logger.error(f"❌ Error en el bot de Twitch: {e}", exc_info=True)
    finally:
        for channel, client in ap_clients.items():
            await client.disconnect()
        logger.info("Bot detenido. ¡Hasta la próxima! 🏝️")


if __name__ == "__main__":
    asyncio.run(main())


"""
archipelago_client.py
Maneja la conexión WebSocket al servidor de Archipelago.

Estrategia de conexión:
  - Se conecta como el SLOT del jugador real (ej: Ryuguu) con la tag TextOnly.
  - Esto permite usar !hint para los ítems de ese jugador sin ser admin
    y sin interferir con la conexión normal del jugador (AP soporta múltiples
    conexiones al mismo slot).
  - Envía Sync periódico como keepalive y reconecta automáticamente si cae.
"""

import asyncio
import json
import logging
import websockets

logger = logging.getLogger("archipelago_client")

KEEPALIVE_INTERVAL = 30   # segundos entre pings al servidor AP
RECONNECT_DELAY    = 5    # segundos entre intentos de reconexión


class ArchipelagoClient:
    def __init__(
        self,
        host: str,
        port: int,
        player_name: str,
        password: str = "",
    ):
        is_local = host in ("localhost", "127.0.0.1")
        scheme = "ws" if is_local else "wss"
        self.uri = f"{scheme}://{host}:{port}"
        self.player_name = player_name
        self.password = password
        self.ws = None
        self._connected = False
        self._player_game = ""
        self._keepalive_task: asyncio.Task | None = None
        self._listen_task: asyncio.Task | None = None
        self._missing_locations: list[int] = []
        self._hint_queue: asyncio.Queue = asyncio.Queue()
        
        # Diccionarios para traducir IDs a nombres
        self._players: dict[int, str] = {}
        self._item_names: dict[int, str] = {}
        self._location_names: dict[int, str] = {}
        # Queue temporal para recibir respuestas LocationInfo durante el scout de hints
        self._loc_info_queue: asyncio.Queue | None = None

    # ──────────────────────────────────────────────────────────────────
    # Conexión pública
    # ──────────────────────────────────────────────────────────────────

    async def connect(self):
        """Conecta al servidor AP y arranca el keepalive y el listener en background."""
        await self._do_connect()
        # Keepalive: manda Sync cada 30s
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        # Listener: consume mensajes entrantes continuamente (mantiene viva la conexión)
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def disconnect(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
        self._connected = False
        logger.info("Desconectado del servidor AP.")

    # ──────────────────────────────────────────────────────────────────
    # Reconexión interna
    # ──────────────────────────────────────────────────────────────────

    async def _do_connect(self):
        """Handshake completo con el servidor AP y cache de diccionarios."""
        logger.info(f"Conectando a {self.uri} ...")
        self.ws = await websockets.connect(self.uri, ping_interval=None, max_size=None)
        self._connected = False

        # 1. RoomInfo
        room_info_raw = await self.ws.recv()
        room_info = json.loads(room_info_raw)[0]
        logger.info(f"RoomInfo recibido. Versión AP: {room_info.get('version', '?')}")

        # 2. Connect
        await self._send([{
            "cmd": "Connect",
            "game": "",
            "name": self.player_name,
            "uuid": f"twitchipelago-{self.player_name}",
            "password": self.password,
            "version": {"major": 0, "minor": 5, "build": 0, "class": "Version"},
            "items_handling": 7,
            "tags": ["TextOnly"],
            "slot_data": False,
        }])

        # 3. Esperar Connected (puede venir DataPackage antes)
        while True:
            response_raw = await self.ws.recv()
            messages = json.loads(response_raw)
            for msg in messages:
                cmd = msg["cmd"]
                
                if cmd == "DataPackage":
                    self._parse_data_package(msg["data"])
                    
                elif cmd == "Connected":
                    self._connected = True
                    self._missing_locations = msg.get("missing_locations", [])
                    checked_locations = msg.get("checked_locations", [])
                    self._total_locations = len(self._missing_locations) + len(checked_locations)
                    
                    # Guardar nombres de jugadores
                    players = msg.get("players", [])
                    for p in players:
                        self._players[p["slot"]] = p.get("alias", p.get("name", f"Player{p['slot']}"))
                        
                    slot_info = msg.get("slot_info", {})
                    for sd in slot_info.values():
                        if sd.get("name", "").lower() == self.player_name.lower():
                            self._player_game = sd.get("game", "")
                            break
                            
                    logger.info(
                        f"✅ Bot conectado al AP como '{self.player_name}' "
                        f"| juego: '{self._player_game or 'desconocido'}'"
                    )
                    logger.info(f"   Checks completados: {len(checked_locations)} / {self._total_locations}")
                    
                    # Pedir diccionario interno de ítems a AP
                    await self._send([{"cmd": "GetDataPackage"}])
                    return
                    
                elif cmd == "ConnectionRefused":
                    errors = msg.get("errors", [])
                    raise ConnectionError(f"Rechazado por el servidor AP: {errors}")

    def _parse_data_package(self, data: dict):
        games = data.get("games", {})
        count_items = 0
        count_locs = 0
        for g_data in games.values():
            # Mapear item_id -> nombre
            for item_name, item_id in g_data.get("item_name_to_id", {}).items():
                self._item_names[int(item_id)] = item_name
                count_items += 1
            # Mapear location_id -> nombre
            for loc_name, loc_id in g_data.get("location_name_to_id", {}).items():
                self._location_names[int(loc_id)] = loc_name
                count_locs += 1
        logger.debug(f"Diccionarios de AP (GetDataPackage) cargados: {count_items} ítems, {count_locs} localizaciones.")

    def get_public_state(self) -> dict:
        """Devuelve el estado público actual del cliente para el Tracker Web"""
        pct = 0
        if hasattr(self, "_total_locations") and self._total_locations > 0:
            pct = 100 - int((len(self._missing_locations) / self._total_locations) * 100)
            
        return {
            "ap_player_name": self.player_name,
            "game": self._player_game,
            "connected": self._connected,
            "total_checks": getattr(self, "_total_locations", 0),
            "missing_checks": len(self._missing_locations),
            "completion_percentage": pct
        }

    # ──────────────────────────────────────────────────────────────────
    # Background tasks: Listen loop + Keepalive
    # ──────────────────────────────────────────────────────────────────

    async def _listen_loop(self):
        """
        Consume TODOS los mensajes entrantes del WebSocket continuamente.
        Esto es esencial: sin este loop el servidor AP cierra la conexión
        porque el cliente deja de leer los mensajes del buffer.
        """
        while True:
            try:
                raw = await self.ws.recv()
                messages = json.loads(raw)
                for msg in messages:
                    await self._handle_message(msg)
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"[{self.player_name}] Conexión AP cerrada. Reconectando...")
                self._connected = False
                await asyncio.sleep(RECONNECT_DELAY)
                await self._reconnect()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"[{self.player_name}] Error en listen_loop: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, msg: dict):
        """Procesa un mensaje entrante del servidor AP."""
        cmd = msg.get("cmd", "")

        if cmd == "DataPackage":
            self._parse_data_package(msg["data"])

        elif cmd == "LocationChecked":
            # El jugador completó un check — actualizar la lista de pendientes
            locs = msg.get("locations", [])
            for loc_id in locs:
                if loc_id in self._missing_locations:
                    self._missing_locations.remove(loc_id)

        elif cmd == "PrintJSON":
            # Despachar a la queue para que _wait_for_hint lo pueda leer
            await self._hint_queue.put(msg)

        elif cmd == "LocationInfo":
            # Respuesta al LocationScouts con create_as_hint=0 (scouting)
            if self._loc_info_queue is not None:
                await self._loc_info_queue.put(msg)

        elif cmd == "RoomUpdate":
            # El servidor puede mandar updates de la sala (ignorar silenciosamente)
            pass

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            try:
                await self._send([{"cmd": "Sync"}])
            except Exception as e:
                logger.warning(f"Keepalive AP falló ({e}). El listen_loop manejará la reconexión.")

    async def _reconnect(self):
        attempt = 1
        while True:
            try:
                if self.ws:
                    try: await self.ws.close()
                    except Exception: pass
                await self._do_connect()
                logger.info("✅ Reconexión exitosa.")
                return
            except Exception as e:
                attempt += 1
                logger.warning(f"Reintento {attempt} de reconexión... ({e})")
                await asyncio.sleep(RECONNECT_DELAY * min(attempt, 6))

    # ──────────────────────────────────────────────────────────────────
    # Comandos de hints
    # ──────────────────────────────────────────────────────────────────

    async def send_hint_random(self) -> str:
        """
        Pide un hint de un check pendiente que aún NO haya sido encontrado.
        
        Estrategia:
          1. Si hay pocas locaciones pendientes (<= 50), scout directo para saber cuáles 
             ya fueron encontradas (create_as_hint=1 no crea hint, solo informa).
          2. Elegir UNA aleatoria de las no-encontradas.
          3. Crear el hint de esa locación con create_as_hint=2.
        """
        import random
        await self._ensure_connected()
        
        if not self._missing_locations:
            return "¡Ya no quedan checks pendientes en tu partida!"
        
        # ── Paso 1: Scout sin crear hint para filtrar las ya encontradas ──
        sample = self._missing_locations[:]  # copia para no mutar
        
        # Pedir info de todas (en lotes de 50 para no saturar)
        unfound_locs: list[int] = []
        BATCH = 50
        
        # Usamos una queue temporal para capturar la respuesta LocationInfo
        loc_info_queue: asyncio.Queue = asyncio.Queue()
        self._loc_info_queue = loc_info_queue
        
        for i in range(0, len(sample), BATCH):
            batch = sample[i:i+BATCH]
            await self._send([{
                "cmd": "LocationScouts",
                "locations": batch,
                "create_as_hint": 0   # solo scouting, sin hint
            }])
        
        # Esperar respuesta LocationInfo (timeout 5s)
        try:
            async with asyncio.timeout(5.0):
                while True:
                    msg = await loc_info_queue.get()
                    if msg.get("cmd") == "LocationInfo":
                        for loc in msg.get("locations", []):
                            # `found` = True si la locación ya fue chequeada por el buscador
                            if not loc.get("found", False):
                                unfound_locs.append(loc["location"])
                        # Si ya procesamos suficiente, salir
                        if unfound_locs or not sample:
                            break
        except asyncio.TimeoutError:
            logger.warning("Timeout esperando LocationInfo, usando missing_locations sin filtrar.")
            unfound_locs = sample
        finally:
            self._loc_info_queue = None
        
        if not unfound_locs:
            # Todos los checks pendientes ya fueron encontrados por el buscador
            return "¡Todos los checks pendientes ya fueron encontrados por el buscador!"
        
        # ── Paso 2: Elegir una locación no-encontrada al azar ──
        target_loc = random.choice(unfound_locs)
        
        # ── Paso 3: Crear el hint real ──
        await self._send([{
            "cmd": "LocationScouts",
            "locations": [target_loc],
            "create_as_hint": 2
        }])
        
        return await self._wait_for_hint()

    async def send_hint_progression(self) -> str:
        """Pide un hint de progresión usando el comando de chat interno de AP."""
        await self._ensure_connected()
        await self._say("!hint")
        return await self._wait_for_hint()

    async def send_hint_for_item(self, item_name: str) -> str:
        await self._ensure_connected()
        await self._say(f"!hint {item_name}")
        return await self._wait_for_hint()

    async def _ensure_connected(self):
        if not self._connected:
            for _ in range(10):
                await asyncio.sleep(1)
                if self._connected: return
            raise RuntimeError("No conectado al servidor de Archipelago.")

    # ──────────────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────────────

    async def _send(self, payload: list):
        await self.ws.send(json.dumps(payload))

    async def _say(self, text: str):
        await self._send([{"cmd": "Say", "text": text}])

    async def _wait_for_hint(self, timeout: float = 3.0) -> str:
        """
        Espera la confirmación visual del hint desde la queue que alimenta _listen_loop.
        """
        try:
            async with asyncio.timeout(timeout):
                while True:
                    msg = await self._hint_queue.get()
                    logger.info(f"AP msg en queue: {msg}")

                    # Reconstruir traduciendo IDs
                    parts = msg.get("data", [])
                    text_parts = []
                    for p in parts:
                        p_type = p.get("type", "")
                        p_text = p.get("text", "")

                        if p_type == "player_id":
                            try:
                                pid = int(p_text)
                                text_parts.append(self._players.get(pid, f"Player{pid}"))
                            except ValueError:
                                text_parts.append(p_text)
                        elif p_type == "item_id":
                            try:
                                iid = int(p.get("text", "0"))
                                text_parts.append(self._item_names.get(iid, f"Item[{iid}]"))
                            except ValueError:
                                text_parts.append(p_text)
                        elif p_type == "location_id":
                            try:
                                lid = int(p.get("text", "0"))
                                text_parts.append(self._location_names.get(lid, f"Location[{lid}]"))
                            except ValueError:
                                text_parts.append(p_text)
                        else:
                            text_parts.append(p_text)

                    text = "".join(text_parts)
                    if not text.strip():
                        continue

                    msg_type = msg.get("type", "")

                    if msg_type in ("Hint", "ItemSend"):
                        logger.info(f"   ↳ Hint traducido: {text}")
                        return text
                    elif "[Hint]" in text:
                        logger.info(f"   ↳ Hint traducido: {text}")
                        return text
                    elif msg_type in ("Chat", "ServerChat", ""):
                        if text.startswith(self.player_name + ": !hint"):
                            continue  # Ignorar nuestro propio eco del comando
                        
                        text_lower = text.lower()
                        # Si tiene el flag ServerChat explícito o palabras clave típicas de un find/hint AP
                        is_hint = (
                            msg_type == "ServerChat" 
                            or any(kw in text_lower for kw in ("hint", "points", "not enough", "found", "is at", "remaining"))
                        )
                        if is_hint:
                            logger.info(f"   ↳ Posible resp: {text}")
                            return text
        except asyncio.TimeoutError:
            return "[Sin respuesta de AP (timeout)]"

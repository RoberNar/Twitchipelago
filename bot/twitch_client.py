"""
twitch_client.py
Bot de Twitch que escucha eventos de bits, subs y gift subs.
Al recibir suficientes bits/subs, activa un hint en el servidor de Archipelago.
"""

import asyncio
import logging

from twitchio.ext import commands
from bot.rewards import RewardManager
from bot.archipelago_client import ArchipelagoClient
from database import log_event, get_config_as_json, get_user_hint_count

logger = logging.getLogger("twitch_client")


class TwitchBot(commands.Bot):
    def __init__(
        self,
        token: str,
        client_id: str,
        channels: list[str],
        ap_clients_map: dict[str, ArchipelagoClient],
        reward_manager: RewardManager,
        user_id: int,
        ap_port: int,
    ):
        super().__init__(
            token=token,
            client_id=client_id,
            prefix="!",
            initial_channels=channels,
        )
        self.ap_clients_map = ap_clients_map
        self.reward_manager = reward_manager
        self.channels_list = [c.lower() for c in channels]
        self.user_id = user_id
        self.ap_port = ap_port

    # ──────────────────────────────────────────────────────────────────
    # Eventos de conexión
    # ──────────────────────────────────────────────────────────────────

    async def event_ready(self):
        logger.info(f"✅ Bot conectado a Twitch como {self.nick}")
        logger.info(f"   Escuchando canales: {', '.join(self.channels_list)}")

        try:
            self.loop.create_task(self._export_public_state_loop())
            self.loop.create_task(self._auto_announcer_loop())
            logger.info("   Tareas en segundo plano iniciadas (Export Tracker & Announcer)")
        except Exception as e:
            logger.error(f"Error iniciando rutinas: {e}")

    async def event_error(self, error: Exception, data=None):
        logger.error(f"Error en TwitchIO: {error}", exc_info=True)

    # ──────────────────────────────────────────────────────────────────
    # Evento de bits (cheers)
    # ──────────────────────────────────────────────────────────────────

    async def event_message(self, message):
        """
        Intercepta mensajes del IRC de Twitch.
        Los bits llegan como mensajes con la tag 'bits'.
        """
        if message.echo:
            return

        bits = 0
        if message.tags:
            try:
                bits = int(message.tags.get("bits", "0"))
            except ValueError:
                bits = 0

        if bits > 0:
            channel = message.channel.name.lower()
            user = message.author.name
            logger.info(f"💎 {user} donó {bits} bits en #{channel}")

            log_event(
                channel=channel,
                event_type="bits",
                amount=bits,
                user_name=user,
            )

            await self._handle_cheer(channel, user, bits, trigger_type="bits")

        await self.handle_commands(message)

    # ──────────────────────────────────────────────────────────────────
    # Eventos de Suscripciones
    # ──────────────────────────────────────────────────────────────────

    async def event_subscription(self, subscription):
        """Suscripción nueva o renovación."""
        channel = subscription.channel.name.lower()
        user = subscription.user.name if subscription.user else "desconocido"
        logger.info(f"⭐ {user} se suscribió en #{channel}")

        log_event(channel=channel, event_type="sub", amount=1, user_name=user)
        await self._handle_cheer(channel, user, amount=1, trigger_type="sub")

    async def event_subscription_gift(self, gift):
        """Un usuario regala suscripciones."""
        channel = gift.channel.name.lower()
        user = gift.gifter.name if gift.gifter else "Anonymous"
        total_gifted = getattr(gift, "total", 1) or 1

        logger.info(f"🎁 {user} regaló {total_gifted} sub(s) en #{channel}")

        event_type = "gift_sub_bomb" if total_gifted > 1 else "gift_sub"
        log_event(channel=channel, event_type=event_type, amount=total_gifted, user_name=user)
        await self._handle_cheer(channel, user, amount=total_gifted, trigger_type=event_type)

    # ──────────────────────────────────────────────────────────────────
    # Lógica central de recompensas
    # ──────────────────────────────────────────────────────────────────

    async def _handle_cheer(self, channel: str, user: str, amount: int, trigger_type: str = "bits"):
        """Procesa el evento a través del RewardManager y ejecuta las recompensas que apliquen."""
        rewards_to_fire = self.reward_manager.process_event(
            channel=channel,
            trigger_type=trigger_type,
            amount=amount,
        )

        if not rewards_to_fire:
            accum = self.reward_manager.get_accumulation_state(channel)
            logger.info(
                f"   ↳ {amount} {trigger_type} de {user} en #{channel} — "
                f"bits acum.={accum['bits']}, subs acum.={accum['subs']}"
            )
            return

        ap_client = self.ap_clients_map.get(channel)
        if not ap_client:
            logger.error(f"❌ No se encontró un cliente AP para #{channel}")
            return

        # Prepare coroutines sequentially so we can map them back to reward info
        # However, due to AP queue lock processing, sending parallel !hints might cause them to gobble each other's responses.
        # Instead of asyncio.gather, we keep it sequential but we don't break on timeout.
        results = []
        for reward in rewards_to_fire:
            reward_id   = reward.get("id", "unknown")
            reward_name = reward.get("name", "Recompensa")

            logger.info(f"   ↳ Ejecutando '{reward_name}' en AP para #{channel}...")
            try:
                if "random" in reward_id.lower() or "aleatorio" in reward_name.lower():
                    result_text = await ap_client.send_hint_random()
                else:
                    result_text = await ap_client.send_hint_progression()

                clean_text = result_text.replace("\n", " ").strip()
                results.append(f"{reward_name}: {clean_text}")

                log_event(
                    channel=channel,
                    event_type="hint_triggered",
                    amount=amount,
                    user_name=user,
                    reward_id=reward_id,
                    detail=result_text,
                )
            except Exception as e:
                logger.error(f"Error al ejecutar '{reward_id}': {e}", exc_info=True)
                results.append(f"{reward_name}: Error AP 😕")

        if results:
            ch = self.get_channel(channel)
            if ch:
                try:
                    hint_count = len(results)
                    # Obtener el total histórico del usuario (incluyendo los de ahora)
                    user_total = get_user_hint_count(user_name=user, channel=channel)
                    if hint_count == 1:
                        msg = f"🏝️ @{user} activó 1 hint | Total de {user}: {user_total} hint(s) 👀"
                    else:
                        msg = f"🏝️ @{user} activó {hint_count} hints | Total de {user}: {user_total} hint(s) 👀"
                    await ch.send(msg)
                    logger.info(f"✅ Mensaje enviado al chat de #{channel}: {msg}")
                except Exception as e:
                    logger.error(f"❌ Error enviando mensaje al chat de #{channel}: {e}", exc_info=True)
            else:
                logger.error(f"❌ No se pudo obtener el canal #{channel} para enviar los resultados.")

    # ──────────────────────────────────────────────────────────────────
    # Comandos Manuales
    # ──────────────────────────────────────────────────────────────────

    @commands.command(name="hint")
    async def cmd_hint(self, ctx: commands.Context):
        """!hint — solo para pruebas del organizador (requiere ser moderador)."""
        channel_name = ctx.channel.name.lower()
        if not ctx.author.is_mod and ctx.author.name.lower() != channel_name:
            return

        ap_client = self.ap_clients_map.get(channel_name)
        if not ap_client:
            return

        logger.info(f"Hint manual solicitado por {ctx.author.name} en #{channel_name}")
        try:
            hint_text = await ap_client.send_hint_random()
            log_event(
                channel=channel_name,
                event_type="hint_triggered",
                user_name=ctx.author.name,
                reward_id="manual",
                detail=hint_text,
            )
            await ctx.send(f"🏝️ Hint manual → {hint_text}")
        except Exception as e:
            await ctx.send(f"Error al pedir hint: {e}")

    @commands.command(name="testbits")
    async def cmd_testbits(self, ctx: commands.Context):
        """!testbits [cantidad] — simula bits para probar bits_fixed y bits_accumulation."""
        channel_name = ctx.channel.name.lower()
        if not ctx.author.is_mod and ctx.author.name.lower() != channel_name:
            await ctx.send("⛔ Solo mods pueden usar !testbits")
            return

        parts = ctx.message.content.strip().split()
        try:
            bits = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            await ctx.send("Uso: !testbits [cantidad]  — ej: !testbits 200")
            return

        logger.info(f"🧪 Simulando {bits} bits de {ctx.author.name} (test)")
        await ctx.send(f"🧪 Simulando {bits} bits de @{ctx.author.name}...")
        await self._handle_cheer(channel_name, ctx.author.name, bits, trigger_type="bits")

    @commands.command(name="testsub")
    async def cmd_testsub(self, ctx: commands.Context):
        """!testsub [cantidad] — simula 1 o N subs individuales para probar trigger 'sub' y 'sub_goal'."""
        channel_name = ctx.channel.name.lower()
        if not ctx.author.is_mod and ctx.author.name.lower() != channel_name:
            await ctx.send("⛔ Solo mods pueden usar !testsub")
            return

        parts = ctx.message.content.strip().split()
        try:
            count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            await ctx.send("Uso: !testsub [cantidad]  — ej: !testsub 5")
            return

        logger.info(f"🧪 Simulando {count} sub(s) de {ctx.author.name} (test)")
        await ctx.send(f"🧪 Simulando {count} sub(s) de @{ctx.author.name}...")
        for _ in range(count):
            await self._handle_cheer(channel_name, ctx.author.name, 1, trigger_type="sub")

    @commands.command(name="testgiftsub")
    async def cmd_testgiftsub(self, ctx: commands.Context):
        """!testgiftsub [cantidad] — simula un gift sub bomb para probar trigger 'sub_goal'."""
        channel_name = ctx.channel.name.lower()
        if not ctx.author.is_mod and ctx.author.name.lower() != channel_name:
            await ctx.send("⛔ Solo mods pueden usar !testgiftsub")
            return

        parts = ctx.message.content.strip().split()
        try:
            count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            await ctx.send("Uso: !testgiftsub [cantidad]  — ej: !testgiftsub 3")
            return

        logger.info(f"🧪 Simulando gift bomb de {count} sub(s) de {ctx.author.name} (test)")
        await ctx.send(f"🧪 Simulando gift bomb de {count} sub(s) de @{ctx.author.name}...")
        trigger = "gift_sub_bomb" if count > 1 else "gift_sub"
        await self._handle_cheer(channel_name, ctx.author.name, count, trigger_type=trigger)

    @commands.command(name="testrewards")
    async def cmd_testrewards(self, ctx: commands.Context):
        """!testrewards — muestra el estado actual de las recompensas y acumuladores."""
        channel_name = ctx.channel.name.lower()
        if not ctx.author.is_mod and ctx.author.name.lower() != channel_name:
            await ctx.send("⛔ Solo mods pueden usar !testrewards")
            return

        accum = self.reward_manager.get_accumulation_state(channel_name)
        rewards = self.reward_manager.rewards_config
        lines = [f"📊 Estado actual en #{channel_name}:"]
        lines.append(f"  💾 Bits acum.: {accum['bits']} | Subs acum.: {accum['subs']}")
        lines.append(f"  📋 Recompensas configuradas: {len(rewards)}")
        for r in rewards:
            tt = r.get('trigger_type', '?')
            enabled = '✅' if r.get('enabled') else '❌'
            if tt == 'bits_fixed':
                detail = f"{r.get('cost', 0)} bits exactos"
            elif tt == 'bits_accumulation':
                detail = f"cada {r.get('bits_per_hint', 500)} bits"
            elif tt == 'sub':
                detail = "por sub individual"
            elif tt == 'sub_goal':
                detail = f"cada {r.get('sub_goal', 5)} subs"
            else:
                detail = tt
            lines.append(f"    {enabled} [{tt}] {r.get('name', '?')} — {detail} | CD: {r.get('cooldown_seconds', 0)}s")
        await ctx.send(" | ".join(lines))

    # ──────────────────────────────────────────────────────────────────
    # Tareas en Segundo Plano
    # ──────────────────────────────────────────────────────────────────

    async def _export_public_state_loop(self):
        """Exporta el estado de todos los clientes AP a public_state.json para el panel."""
        import json
        while True:
            state = {}
            for channel, client in self.ap_clients_map.items():
                state[channel.lower()] = client.get_public_state()

            if state:
                try:
                    users = await self.fetch_users(names=list(state.keys()))
                    for user in users:
                        if user.name.lower() in state:
                            state[user.name.lower()]["avatar_url"] = user.profile_image
                except Exception as e:
                    logger.warning(f"⚠️ No se pudieron resolver los avatars de Twitch: {e}")

            try:
                file_name = f"public_state_{self.ap_port}.json" if self.ap_port else "public_state.json"
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Falla al exportar {file_name}: {e}")

            await asyncio.sleep(5)

    async def _auto_announcer_loop(self):
        """Anuncia periódicamente el link del Tracker en todos los canales."""
        while True:
            try:
                cfg = get_config_as_json(user_id=self.user_id)
                announcer = cfg.get("announcer", {})
                interval = max(1, int(announcer.get("interval_minutes", 15)))

                if announcer.get("enabled", False):
                    import os
                    base_url = os.environ.get("TWITCH_REDIRECT_URI", "").replace("/auth/callback", "")
                    if not base_url:
                        base_url = "https://twitchipelago-production.up.railway.app"
                    
                    ap_port = cfg.get("archipelago", {}).get("port", "")
                    tracker_url = f"{base_url}/tracker/{ap_port}" if ap_port else f"{base_url}/tracker"

                    msg = (
                        "🚀 ¡Chequea cómo van los demás participantes de esta run "
                        f"y quién va ganando en: {tracker_url} !"
                    )
                    logger.info("📢 Ejecutando Auto-Announcer en todos los canales...")

                    for ch_name in self.channels_list:
                        ch = self.get_channel(ch_name)
                        if ch:
                            try:
                                await ch.send(msg)
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Error en auto_announcer_loop: {e}")
                interval = 15

            await asyncio.sleep(interval * 60)

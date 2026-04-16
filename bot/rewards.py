"""
rewards.py
Lógica de validación de recompensas.

Modos de trigger soportados:
  - bits_fixed        → una cantidad exacta (o mayor) de bits dispara el hint
  - bits_accumulation → bits se acumulan en un contador; al llegar al umbral, 1 hint y reset
  - sub               → cada suscripción (o renovación) dispara el hint
  - sub_goal          → los subs se acumulan; al llegar al goal, 1 hint y reset
"""

import time
import logging

logger = logging.getLogger("rewards")


class RewardManager:
    def __init__(self, rewards_config: list[dict]):
        """
        rewards_config: lista de dicts con la configuración de recompensas.
        Ej: [
            {"id": "hint_random", "name": "Hint Aleatorio", "enabled": True,
             "cooldown_seconds": 60, "trigger_type": "bits_fixed", "cost": 200},
            {"id": "hint_accumulation", "name": "Bits Acumulados", "enabled": True,
             "trigger_type": "bits_accumulation", "bits_per_hint": 500},
            {"id": "hint_sub", "name": "Por Sub", "enabled": True,
             "trigger_type": "sub"},
            {"id": "hint_sub_goal", "name": "Sub Goal", "enabled": True,
             "trigger_type": "sub_goal", "sub_goal": 5},
        ]
        """
        self.rewards = rewards_config

        # Cooldown tracking: { "canal": { "reward_id": timestamp } }
        self._last_usage: dict[str, dict[str, float]] = {}

        # Acumulación de bits por canal: { "canal": bits_acumulados }
        self._bits_accum: dict[str, int] = {}

        # Acumulación de subs por canal para sub_goal: { "canal": sub_count }
        self._sub_accum: dict[str, int] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Obtener progreso de acumulación (para el panel / tracker)
    # ─────────────────────────────────────────────────────────────────────────

    def get_accumulation_state(self, channel: str) -> dict:
        """Retorna el estado de acumulación actual de un canal."""
        return {
            "bits": self._bits_accum.get(channel, 0),
            "subs": self._sub_accum.get(channel, 0),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Procesamiento principal de eventos
    # ─────────────────────────────────────────────────────────────────────────

    def process_event(
        self,
        channel: str,
        trigger_type: str,
        amount: int = 1,
    ) -> list[dict]:
        """
        Procesa un evento (bits, sub, gift_sub, etc.) para un canal.
        Retorna la lista de recompensas que deben dispararse ahora.
        """
        channel = channel.lower()
        rewards_to_fire = []

        for reward in self.rewards:
            if not reward.get("enabled", False):
                continue

            r_trigger = reward.get("trigger_type", "bits_fixed")

            # ── Bits Fijo ──────────────────────────────────────────────────
            if r_trigger == "bits_fixed" and trigger_type == "bits":
                cost = int(reward.get("cost", 0))
                if cost > 0 and amount >= cost:
                    rewards_to_fire.append(reward)

            # ── Bits Acumulación ───────────────────────────────────────────
            elif r_trigger == "bits_accumulation" and trigger_type == "bits":
                per_hint = int(reward.get("bits_per_hint", 0))
                if per_hint > 0:
                    prev = self._bits_accum.get(channel, 0)
                    total = prev + amount
                    triggers_count = total // per_hint
                    self._bits_accum[channel] = total % per_hint

                    for _ in range(triggers_count):
                        rewards_to_fire.append(reward)

            # ── Sub ────────────────────────────────────────────────────────
            elif r_trigger == "sub" and trigger_type in ("sub", "gift_sub", "gift_sub_bomb"):
                # Cada sub (o cada sub regalado) activa la recompensa
                for _ in range(amount):
                    rewards_to_fire.append(reward)

            # ── Sub Goal ───────────────────────────────────────────────────
            elif r_trigger == "sub_goal" and trigger_type in ("sub", "gift_sub", "gift_sub_bomb"):
                goal = int(reward.get("sub_goal", 0))
                if goal > 0:
                    prev = self._sub_accum.get(channel, 0)
                    total = prev + amount
                    triggers_count = total // goal
                    self._sub_accum[channel] = total % goal

                    for _ in range(triggers_count):
                        rewards_to_fire.append(reward)

        # Filtrar por cooldowns
        final = []
        for reward in rewards_to_fire:
            ok, reason = self.can_trigger_reward(channel, reward.get("id", ""))
            if ok:
                self.register_reward(channel, reward.get("id", ""))
                final.append(reward)
            else:
                logger.info(f"   ↳ '{reward.get('name')}' bloqueado en #{channel}: {reason}")

        return final

    # ─────────────────────────────────────────────────────────────────────────
    # Compatibilidad hacia atrás (usado solo por !testbits)
    # ─────────────────────────────────────────────────────────────────────────

    def get_matching_reward(self, amount: int, trigger_type: str = "bits") -> dict | None:
        """Legacy: retorna la primera recompensa que aplica sin modificar acumuladores."""
        for reward in self.rewards:
            if not reward.get("enabled", False):
                continue
            r_trigger = reward.get("trigger_type", "bits_fixed")
            cost = int(reward.get("cost", 0))
            if r_trigger == "bits_fixed" and trigger_type == "bits" and amount >= cost:
                return reward
            if r_trigger == "sub" and trigger_type in ("sub", "gift_sub", "gift_sub_bomb"):
                return reward
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Cooldowns
    # ─────────────────────────────────────────────────────────────────────────

    def can_trigger_reward(self, channel: str, reward_id: str) -> tuple[bool, str]:
        reward = next((r for r in self.rewards if r.get("id") == reward_id), None)
        if not reward:
            return False, "Recompensa no encontrada."
        if not reward.get("enabled", False):
            return False, f"'{reward.get('name', reward_id)}' está desactivada."

        cooldown = reward.get("cooldown_seconds", 0)
        if cooldown <= 0:
            return True, "ok"

        now = time.monotonic()
        last = self._last_usage.get(channel, {}).get(reward_id, 0.0)
        remaining = cooldown - (now - last)

        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            return False, f"Cooldown — quedan {time_str}"

        return True, "ok"

    def register_reward(self, channel: str, reward_id: str):
        """Registra el timestamp de uso de una recompensa."""
        self._last_usage.setdefault(channel, {})[reward_id] = time.monotonic()
        logger.info(f"Recompensa '{reward_id}' ejecutada en #{channel}")

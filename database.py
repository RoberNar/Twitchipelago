"""
database.py
Capa de base de datos del sistema Twitchipelago.

- En desarrollo local usa SQLite (twitchipelago.db).
- En Railway usa PostgreSQL via la variable de entorno DATABASE_URL.
- Al primer arranque, migra automáticamente los datos de config.json si existe.
"""

import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

logger = logging.getLogger("database")

# ── Motor de base de datos ────────────────────────────────────────────────────

def get_engine():
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if not db_url:
        db_url = "sqlite:///twitchipelago.db"
        logger.info("📁 Usando base de datos LOCAL: twitchipelago.db (SQLite)")
    else:
        logger.info("🐘 Usando base de datos RAILWAY: PostgreSQL")

    engine = create_engine(db_url, echo=False)
    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_con, _):
            dbapi_con.execute("PRAGMA foreign_keys=ON")
    return engine


# ── Modelos ORM ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class User(Base):
    """
    Usuario del sistema. Se autentica via Twitch OAuth.
    Cada usuario tiene su propia configuración, jugadores y recompensas aisladas.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    twitch_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    access_token: Mapped[str] = mapped_column(String(512), default="")
    refresh_token: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relaciones
    archi_config: Mapped["ArchiConfig | None"] = relationship("ArchiConfig", back_populates="user", uselist=False)
    twitch_config: Mapped["TwitchConfig | None"] = relationship("TwitchConfig", back_populates="user", uselist=False)
    announcer_config: Mapped["AnnouncerConfig | None"] = relationship("AnnouncerConfig", back_populates="user", uselist=False)
    players: Mapped[list["Player"]] = relationship("Player", back_populates="user")
    rewards: Mapped[list["Reward"]] = relationship("Reward", back_populates="user")


class ArchiConfig(Base):
    """Configuración del servidor Archipelago por usuario."""
    __tablename__ = "archi_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    host: Mapped[str] = mapped_column(String(255), default="archipelago.gg")
    port: Mapped[int] = mapped_column(Integer, default=38281)
    password: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped["User"] = relationship("User", back_populates="archi_config")


class TwitchConfig(Base):
    """Credenciales del bot de Twitch por usuario."""
    __tablename__ = "twitch_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(String(512), default="")
    client_id: Mapped[str] = mapped_column(String(255), default="")
    client_secret: Mapped[str] = mapped_column(String(255), default="")
    refresh_token: Mapped[str] = mapped_column(String(512), default="")
    bot_nick: Mapped[str] = mapped_column(String(100), default="twitchipelagobot")

    user: Mapped["User"] = relationship("User", back_populates="twitch_config")


class AnnouncerConfig(Base):
    """Configuración del auto-announcer por usuario."""
    __tablename__ = "announcer_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)

    user: Mapped["User"] = relationship("User", back_populates="announcer_config")


class Player(Base):
    """Mapeo canal Twitch ↔ jugador AP, por usuario."""
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    twitch_channel: Mapped[str] = mapped_column(String(100), nullable=False)
    ap_player_name: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="players")
    events: Mapped[list["EventLog"]] = relationship(
        "EventLog",
        back_populates="player",
        foreign_keys="EventLog.channel",
        primaryjoin="Player.twitch_channel == EventLog.channel",
    )


class Reward(Base):
    """Definición de una recompensa por usuario."""
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reward_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="rewards")
    triggers: Mapped[list["RewardTrigger"]] = relationship(
        "RewardTrigger", back_populates="reward", cascade="all, delete-orphan"
    )


class RewardTrigger(Base):
    """
    Define qué tipo de evento y a qué costo activa una recompensa.
    trigger_type: "bits" | "sub" | "gift_sub" | "gift_sub_bomb"
    """
    __tablename__ = "reward_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reward_fk: Mapped[int] = mapped_column(Integer, ForeignKey("rewards.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_cost: Mapped[int] = mapped_column(Integer, default=0)

    reward: Mapped["Reward"] = relationship("Reward", back_populates="triggers")


class EventLog(Base):
    """
    Log permanente de todos los eventos relevantes del sistema.
    Fuente de datos para los dashboards por canal/usuario.
    event_type: "bits" | "sub" | "gift_sub" | "gift_sub_bomb" | "hint_triggered"
    """
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    channel: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    user_name: Mapped[str] = mapped_column(String(100), default="")
    reward_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    player: Mapped["Player | None"] = relationship(
        "Player",
        back_populates="events",
        foreign_keys=[channel],
        primaryjoin="EventLog.channel == Player.twitch_channel",
    )


# ── Instancia global del motor ────────────────────────────────────────────────
_engine = None

def get_db_engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


# ── Inicialización ────────────────────────────────────────────────────────────

def init_db():
    """Crea todas las tablas. Si detecta DB vacía, migra config.json."""
    engine = get_db_engine()
    Base.metadata.create_all(engine)
    logger.info("✅ Tablas de base de datos verificadas/creadas.")

    with Session(engine) as session:
        existing_user = session.query(User).first()
        if existing_user is None:
            _migrate_from_json(session)


def _migrate_from_json(session: Session):
    """Migra config.json a la DB creando un usuario 'seed' con id=1."""
    config_path = "config.json"

    # Crear usuario seed (se sobreescribirá al primer login OAuth)
    seed_user = User(
        id=1,
        twitch_id="__seed__",
        display_name="Admin",
        avatar_url="",
    )
    session.add(seed_user)
    session.flush()  # para tener el id disponible

    if not os.path.exists(config_path):
        logger.info("ℹ️  No se encontró config.json. Iniciando con DB vacía.")
        _seed_defaults(session, user_id=1)
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"⚠️  No se pudo leer config.json: {e}")
        _seed_defaults(session, user_id=1)
        return

    logger.info("⬆️  Migrando config.json a la base de datos...")

    ap = data.get("archipelago", {})
    session.add(ArchiConfig(
        user_id=1,
        host=ap.get("host", "archipelago.gg"),
        port=int(ap.get("port", 38281)),
        password=ap.get("password", ""),
    ))

    tw = data.get("twitch", {})
    session.add(TwitchConfig(
        user_id=1,
        access_token=tw.get("access_token", ""),
        client_id=tw.get("client_id", ""),
        client_secret=tw.get("client_secret", ""),
        refresh_token=tw.get("refresh_token", ""),
        bot_nick=tw.get("bot_nick", "twitchipelagobot"),
    ))

    ann = data.get("announcer", {})
    session.add(AnnouncerConfig(
        user_id=1,
        enabled=ann.get("enabled", True),
        interval_minutes=int(ann.get("interval_minutes", 15)),
    ))

    for p in data.get("players", []):
        channel = p.get("twitch_channel", "").lower().strip()
        ap_name = p.get("ap_player_name", "").strip()
        if channel and ap_name:
            session.add(Player(user_id=1, twitch_channel=channel, ap_player_name=ap_name))

    for r in data.get("rewards", []):
        reward_id = r.get("id", "")
        if not reward_id:
            continue
        reward = Reward(
            user_id=1,
            reward_id=reward_id,
            name=r.get("name", reward_id),
            enabled=bool(r.get("enabled", True)),
            cooldown_seconds=int(r.get("cooldown_seconds", 0)),
        )
        reward.triggers.append(RewardTrigger(
            trigger_type="bits",
            trigger_cost=int(r.get("cost", 0)),
        ))
        session.add(reward)

    session.commit()
    logger.info("✅ Migración desde config.json completada.")


def _seed_defaults(session: Session, user_id: int):
    session.add(ArchiConfig(user_id=user_id))
    session.add(TwitchConfig(user_id=user_id))
    session.add(AnnouncerConfig(user_id=user_id))
    session.commit()
    logger.info("🌱 Base de datos inicializada con valores por defecto.")


# ── Helpers OAuth ─────────────────────────────────────────────────────────────

def get_or_create_user(
    twitch_id: str,
    display_name: str,
    avatar_url: str,
    access_token: str,
    refresh_token: str,
) -> "User":
    """
    Busca al usuario por su twitch_id. Si no existe, lo crea con config vacía.
    Si el usuario seed existe, lo convierte en usuario real al primer login.
    Retorna un objeto User desacoplado de la sesión (seguro de usar fuera del contexto).
    """
    engine = get_db_engine()
    with Session(engine) as session:
        # Caso especial: hay un usuario seed, lo convertimos en real
        seed = session.query(User).filter_by(twitch_id="__seed__").first()
        if seed:
            seed.twitch_id = twitch_id
            seed.display_name = display_name
            seed.avatar_url = avatar_url
            seed.access_token = access_token
            seed.refresh_token = refresh_token
            seed.last_seen = datetime.now(timezone.utc)
            session.commit()
            session.refresh(seed)
            session.expunge(seed)
            logger.info(f"✅ Usuario seed convertido en real: {display_name}")
            return seed

        user = session.query(User).filter_by(twitch_id=twitch_id).first()
        if user:
            user.display_name = display_name
            user.avatar_url = avatar_url
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.last_seen = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"✅ Usuario existente actualizado: {display_name}")
        else:
            user = User(
                twitch_id=twitch_id,
                display_name=display_name,
                avatar_url=avatar_url,
                access_token=access_token,
                refresh_token=refresh_token,
            )
            session.add(user)
            session.flush()
            _seed_defaults(session, user.id)
            session.commit()
            logger.info(f"✅ Nuevo usuario creado: {display_name}")

        session.refresh(user)
        session.expunge(user)  # desacoplar antes de cerrar la sesión
        return user


def get_user_by_id(user_id: int) -> "User | None":
    engine = get_db_engine()
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            session.expunge(user)
        return user


# ── Helpers de lectura/escritura (filtrados por user_id) ─────────────────────

def load_config_from_db(user_id: int = 1) -> dict:
    """Carga config desde DB para un usuario específico."""
    engine = get_db_engine()
    with Session(engine) as session:
        ap = session.query(ArchiConfig).filter_by(user_id=user_id).first() or ArchiConfig()
        tw = session.query(TwitchConfig).filter_by(user_id=user_id).first() or TwitchConfig()
        players = session.query(Player).filter_by(user_id=user_id).all()
        rewards = session.query(Reward).filter_by(user_id=user_id).all()

        rewards_config = []
        for r in rewards:
            trigger = r.triggers[0] if r.triggers else None
            t_type = trigger.trigger_type if trigger else "bits_fixed"
            t_cost = trigger.trigger_cost if trigger else 0
            
            reward_dict = {
                "id": r.reward_id,
                "name": r.name,
                "enabled": r.enabled,
                "cooldown_seconds": r.cooldown_seconds,
                "trigger_type": t_type,
            }
            
            if t_type == "bits_fixed":
                reward_dict["cost"] = t_cost
            elif t_type == "bits_accumulation":
                reward_dict["bits_per_hint"] = t_cost
            elif t_type == "sub_goal":
                reward_dict["sub_goal"] = t_cost
                
            rewards_config.append(reward_dict)

        return {
            "twitch_client_id":     tw.client_id,
            "twitch_access_token":  tw.access_token,
            "twitch_client_secret": tw.client_secret,
            "twitch_refresh_token": tw.refresh_token,
            "twitch_bot_nick":      tw.bot_nick,
            "ap_host":              ap.host,
            "ap_port":              ap.port,
            "ap_password":          ap.password,
            "players": [
                {"twitch_channel": p.twitch_channel, "ap_player_name": p.ap_player_name}
                for p in players
            ],
            "rewards_config": rewards_config,
        }


def get_config_as_json(user_id: int = 1) -> dict:
    """Retorna la config en el formato JSON que consume el panel React."""
    engine = get_db_engine()
    with Session(engine) as session:
        ap = session.query(ArchiConfig).filter_by(user_id=user_id).first() or ArchiConfig()
        tw = session.query(TwitchConfig).filter_by(user_id=user_id).first() or TwitchConfig()
        ann = session.query(AnnouncerConfig).filter_by(user_id=user_id).first() or AnnouncerConfig()
        players = session.query(Player).filter_by(user_id=user_id).all()
        rewards = session.query(Reward).filter_by(user_id=user_id).all()

        rewards_list = []
        for r in rewards:
            # Encontrar el trigger principal
            trigger = r.triggers[0] if r.triggers else None
            t_type = trigger.trigger_type if trigger else "bits_fixed"
            t_cost = trigger.trigger_cost if trigger else 0

            reward_dict = {
                "id": r.reward_id,
                "name": r.name,
                "enabled": r.enabled,
                "cooldown_seconds": r.cooldown_seconds,
                "trigger_type": t_type,
                # bits_fixed
                "cost": t_cost if t_type == "bits_fixed" else 0,
                # bits_accumulation
                "bits_per_hint": t_cost if t_type == "bits_accumulation" else 100,
                # sub_goal
                "sub_goal": t_cost if t_type == "sub_goal" else 5,
            }
            rewards_list.append(reward_dict)

        return {
            "archipelago": {"host": ap.host, "port": ap.port, "password": ap.password},
            "twitch": {
                "access_token": tw.access_token,
                "client_id": tw.client_id,
                "client_secret": tw.client_secret,
                "refresh_token": tw.refresh_token,
                "bot_nick": tw.bot_nick,
            },
            "announcer": {
                "enabled": ann.enabled,
                "interval_minutes": ann.interval_minutes,
            },
            "players": [
                {"twitch_channel": p.twitch_channel, "ap_player_name": p.ap_player_name}
                for p in players
            ],
            "rewards": rewards_list,
        }


def save_config_from_json(data: dict, user_id: int = 1):
    """Persiste la config del panel en la DB para un usuario específico."""
    engine = get_db_engine()
    with Session(engine) as session:
        # Archipelago
        ap_data = data.get("archipelago", {})
        ap = session.query(ArchiConfig).filter_by(user_id=user_id).first()
        if not ap:
            ap = ArchiConfig(user_id=user_id)
            session.add(ap)
        ap.host = ap_data.get("host", ap.host)
        ap.port = int(ap_data.get("port", ap.port))
        ap.password = ap_data.get("password", ap.password)

        # Twitch
        tw_data = data.get("twitch", {})
        tw = session.query(TwitchConfig).filter_by(user_id=user_id).first()
        if not tw:
            tw = TwitchConfig(user_id=user_id)
            session.add(tw)
        tw.access_token = tw_data.get("access_token", tw.access_token)
        tw.client_id = tw_data.get("client_id", tw.client_id)
        tw.client_secret = tw_data.get("client_secret", tw.client_secret)
        tw.refresh_token = tw_data.get("refresh_token", tw.refresh_token)
        tw.bot_nick = tw_data.get("bot_nick", tw.bot_nick)

        # Announcer
        ann_data = data.get("announcer", {})
        ann = session.query(AnnouncerConfig).filter_by(user_id=user_id).first()
        if not ann:
            ann = AnnouncerConfig(user_id=user_id)
            session.add(ann)
        ann.enabled = bool(ann_data.get("enabled", ann.enabled))
        ann.interval_minutes = int(ann_data.get("interval_minutes", ann.interval_minutes))

        # Jugadores: reemplazar lista
        session.query(Player).filter_by(user_id=user_id).delete()
        for p in data.get("players", []):
            channel = p.get("twitch_channel", "").lower().strip()
            ap_name = p.get("ap_player_name", "").strip()
            if channel and ap_name:
                session.add(Player(user_id=user_id, twitch_channel=channel, ap_player_name=ap_name))

        # Recompensas: reemplazar lista
        old_rewards = session.query(Reward).filter_by(user_id=user_id).all()
        for r in old_rewards:
            session.delete(r)
        session.flush()

        for r in data.get("rewards", []):
            reward_id = r.get("id", "")
            if not reward_id:
                continue
            reward = Reward(
                user_id=user_id,
                reward_id=reward_id,
                name=r.get("name", reward_id),
                enabled=bool(r.get("enabled", True)),
                cooldown_seconds=int(r.get("cooldown_seconds", 0)),
            )

            t_type = r.get("trigger_type", "bits_fixed")

            if t_type == "bits_fixed":
                trigger_cost = int(r.get("cost", 0))
            elif t_type == "bits_accumulation":
                trigger_cost = int(r.get("bits_per_hint", 100))
            elif t_type == "sub_goal":
                trigger_cost = int(r.get("sub_goal", 5))
            else:  # sub
                trigger_cost = 1

            reward.triggers.append(RewardTrigger(
                trigger_type=t_type,
                trigger_cost=trigger_cost,
            ))
            session.add(reward)

        session.commit()


# ── EventLog ──────────────────────────────────────────────────────────────────

def log_event(
    channel: str,
    event_type: str,
    amount: int = 0,
    user_name: str = "",
    reward_id: str | None = None,
    detail: str | None = None,
):
    engine = get_db_engine()
    try:
        with Session(engine) as session:
            session.add(EventLog(
                channel=channel.lower(),
                event_type=event_type,
                amount=amount,
                user_name=user_name,
                reward_id=reward_id,
                detail=detail,
            ))
            session.commit()
    except Exception as e:
        logger.error(f"Error al registrar evento en DB: {e}")


def get_channel_stats(channel: str) -> dict:
    """Estadísticas acumuladas por canal para el dashboard."""
    engine = get_db_engine()
    with Session(engine) as session:
        events = session.query(EventLog).filter(EventLog.channel == channel.lower()).all()

    stats = {
        "channel": channel,
        "total_bits": 0,
        "total_subs": 0,
        "total_gift_subs": 0,
        "total_hints_triggered": 0,
        "events_count": len(events),
    }
    for e in events:
        if e.event_type == "bits":
            stats["total_bits"] += e.amount
        elif e.event_type == "sub":
            stats["total_subs"] += 1
        elif e.event_type in ("gift_sub", "gift_sub_bomb"):
            stats["total_gift_subs"] += e.amount
        elif e.event_type == "hint_triggered":
            stats["total_hints_triggered"] += 1

    return stats


def _compute_stats_from_events(events: list) -> dict:
    """Calcula métricas resumen a partir de una lista de EventLog."""
    total_bits = 0
    total_subs = 0
    total_gift_subs = 0
    total_hints = 0
    donors: set = set()

    for e in events:
        if e.event_type == "bits":
            total_bits += e.amount
            if e.user_name:
                donors.add(e.user_name.lower())
        elif e.event_type == "sub":
            total_subs += 1
            if e.user_name:
                donors.add(e.user_name.lower())
        elif e.event_type in ("gift_sub", "gift_sub_bomb"):
            total_gift_subs += e.amount
            if e.user_name:
                donors.add(e.user_name.lower())
        elif e.event_type == "hint_triggered":
            total_hints += 1

    return {
        "total_bits": total_bits,
        "total_subs": total_subs,
        "total_gift_subs": total_gift_subs,
        "total_hints": total_hints,
        "unique_donors": len(donors),
    }


def get_all_stats(user_id: int = 1, since: "datetime | None" = None) -> dict:
    """
    Retorna estadísticas de todos los jugadores del usuario.
    - since: si se indica, filtra solo eventos desde esa fecha/hora (sesión actual).
    """
    engine = get_db_engine()
    with Session(engine) as session:
        players = session.query(Player).filter_by(user_id=user_id).all()
        channels = [p.twitch_channel.lower() for p in players]

        # Todos los eventos del usuario
        all_q = session.query(EventLog).filter(EventLog.channel.in_(channels))
        all_events = all_q.order_by(EventLog.timestamp.desc()).all()

        # Eventos de sesión (filtrados por since)
        if since:
            session_events = [e for e in all_events if e.timestamp >= since]
        else:
            session_events = all_events

        alltime_stats = _compute_stats_from_events(all_events)
        session_stats = _compute_stats_from_events(session_events)

        # Lista detallada (últimos 200 eventos)
        events_list = [
            {
                "ts": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
                "channel": e.channel,
                "type": e.event_type,
                "user": e.user_name or "",
                "amount": e.amount,
                "reward_id": e.reward_id or "",
                "detail": e.detail or "",
            }
            for e in all_events[:200]
        ]

        return {
            "session": session_stats,
            "alltime": alltime_stats,
            "events": events_list,
            "channels": channels,
        }


def get_last_bot_session_start(log_file: str = "bot.log") -> "datetime | None":
    """
    Lee bot.log y extrae el timestamp del último '--- Bot iniciado desde panel web ---'.
    Retorna un objeto datetime UTC, o None si no se encuentra.
    """
    import re
    if not os.path.exists(log_file):
        return None
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return None

    # Buscar la última línea de inicio
    last_start_line = None
    for i, line in enumerate(lines):
        if "Bot iniciado desde panel web" in line:
            # La siguiente línea contiene el primer timestamp del log
            if i + 1 < len(lines):
                last_start_line = lines[i + 1]

    if not last_start_line:
        return None

    # Formato: "HH:MM:SS [LEVEL] module: mensaje"
    match = re.match(r"(\d{2}:\d{2}:\d{2})", last_start_line.strip())
    if not match:
        return None

    time_str = match.group(1)
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        dt = datetime.strptime(f"{today} {time_str}", "%Y-%m-%d %H:%M:%S")
        return dt
    except ValueError:
        return None


def get_recent_hints(channel: str = "", limit: int = 10) -> list:
    """
    Retorna los últimos `limit` eventos hint_triggered.
    Si se indica channel, filtra por ese canal.
    """
    engine = get_db_engine()
    with Session(engine) as session:
        q = session.query(EventLog).filter(EventLog.event_type == "hint_triggered")
        if channel:
            q = q.filter(EventLog.channel == channel.lower())
        events = q.order_by(EventLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "ts": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
                "user": e.user_name or "",
                "channel": e.channel,
                "detail": e.detail or "",
                "reward_id": e.reward_id or "",
            }
            for e in events
        ]


def get_hint_leaderboard(channel: str = "") -> list:
    """
    Retorna un listado de usuarios ordenados por cantidad de hints activados (desc).
    Si se indica channel, filtra por ese canal.
    """
    from sqlalchemy import func
    engine = get_db_engine()
    with Session(engine) as session:
        q = (
            session.query(
                EventLog.user_name,
                func.count(EventLog.id).label("hint_count")
            )
            .filter(EventLog.event_type == "hint_triggered")
        )
        if channel:
            q = q.filter(EventLog.channel == channel.lower())
        rows = q.group_by(EventLog.user_name).order_by(func.count(EventLog.id).desc()).all()
        return [
            {"user": row.user_name or "?", "hint_count": row.hint_count}
            for row in rows
        ]


def get_user_hint_count(user_name: str, channel: str = "") -> int:
    """
    Retorna el total de hints activados por un usuario específico.
    Usado por el bot para incluir el total en el mensaje de Twitch.
    """
    from sqlalchemy import func
    engine = get_db_engine()
    with Session(engine) as session:
        q = (
            session.query(func.count(EventLog.id))
            .filter(
                EventLog.event_type == "hint_triggered",
                EventLog.user_name == user_name,
            )
        )
        if channel:
            q = q.filter(EventLog.channel == channel.lower())
        result = q.scalar()
        return result or 0

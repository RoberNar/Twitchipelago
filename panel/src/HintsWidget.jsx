import { useState, useEffect, useRef, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:5000");

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(tsStr) {
  if (!tsStr) return "";
  const ts = new Date(tsStr.replace(" ", "T") + "Z");
  const diff = Math.floor((Date.now() - ts.getTime()) / 1000);
  if (diff < 60) return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  return `hace ${Math.floor(diff / 86400)}d`;
}

function avatarLetter(name) {
  return (name || "?")[0].toUpperCase();
}

// ── Componente HintCard ───────────────────────────────────────────────────────

function HintCard({ hint, isNew }) {
  const [expanded, setExpanded] = useState(false);
  const userColors = useRef({});

  // Asignar color consistente por usuario
  const getColor = (name) => {
    if (!userColors.current[name]) {
      const palette = [
        "#a78bfa", "#60a5fa", "#34d399", "#f472b6",
        "#fb923c", "#facc15", "#38bdf8", "#4ade80",
      ];
      const idx = name
        .split("")
        .reduce((acc, c) => acc + c.charCodeAt(0), 0) % palette.length;
      userColors.current[name] = palette[idx];
    }
    return userColors.current[name];
  };

  const color = getColor(hint.user);

  return (
    <div
      className={`hint-card ${isNew ? "hint-card--new" : ""} ${expanded ? "hint-card--expanded" : ""}`}
    >
      <div className="hint-card__header" onClick={() => setExpanded((e) => !e)}>
        <div className="hint-card__avatar" style={{ background: color }}>
          {avatarLetter(hint.user)}
        </div>
        <div className="hint-card__meta">
          <span className="hint-card__user" style={{ color }}>
            {hint.user || "Anónimo"}
          </span>
          <span className="hint-card__channel">#{hint.channel}</span>
        </div>
        <div className="hint-card__time">{timeAgo(hint.ts)}</div>
        <div className="hint-card__chevron">{expanded ? "▲" : "▼"}</div>
      </div>
      {expanded && (
        <div className="hint-card__detail">
          <p>{hint.detail || "(sin detalle)"}</p>
        </div>
      )}
    </div>
  );
}

// ── Componente LeaderboardRow ─────────────────────────────────────────────────

function LeaderboardRow({ rank, user, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  const medals = ["🥇", "🥈", "🥉"];

  const color =
    rank === 0
      ? "#facc15"
      : rank === 1
      ? "#94a3b8"
      : rank === 2
      ? "#f97316"
      : "#a78bfa";

  return (
    <div className="lb-row">
      <span className="lb-rank">{medals[rank] || `#${rank + 1}`}</span>
      <div className="lb-avatar" style={{ background: color }}>
        {avatarLetter(user)}
      </div>
      <div className="lb-info">
        <span className="lb-user" style={{ color }}>
          {user}
        </span>
        <div className="lb-bar-bg">
          <div
            className="lb-bar-fill"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
      </div>
      <span className="lb-count">{count}</span>
    </div>
  );
}

// ── Widget principal ──────────────────────────────────────────────────────────

export default function HintsWidget() {
  const [channels, setChannels] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState("");
  const [limit, setLimit] = useState(8);
  const [hints, setHints] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [newHintIds, setNewHintIds] = useState(new Set());
  const [lastTs, setLastTs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("feed"); // "feed" | "leaderboard"
  const pollingRef = useRef(null);

  // Cargar lista de canales disponibles
  useEffect(() => {
    fetch(`${API}/api/hints/channels`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setChannels(data);
          // Pre-seleccionar si viene en la URL (?channel=xxx)
          const params = new URLSearchParams(window.location.search);
          const urlCh = params.get("channel");
          setSelectedChannel(urlCh && data.includes(urlCh) ? urlCh : data[0]);
        }
      })
      .catch(() => {});

    // Leer limit de la URL si existe
    const params = new URLSearchParams(window.location.search);
    const urlLimit = parseInt(params.get("limit"), 10);
    if (urlLimit > 0 && urlLimit <= 50) setLimit(urlLimit);
  }, []);

  // Función de fetch
  const fetchData = useCallback(async () => {
    if (!selectedChannel) return;
    try {
      const [hRes, lRes] = await Promise.all([
        fetch(
          `${API}/api/hints/recent?channel=${selectedChannel}&limit=${limit}`
        ),
        fetch(`${API}/api/hints/leaderboard?channel=${selectedChannel}`),
      ]);
      const hData = await hRes.json();
      const lData = await lRes.json();

      if (Array.isArray(hData)) {
        setHints((prev) => {
          // Detectar hints nuevos comparando timestamps
          if (prev.length > 0 && lastTs) {
            const newOnes = new Set();
            hData.forEach((h) => {
              if (h.ts > lastTs) newOnes.add(h.ts + h.user);
            });
            if (newOnes.size > 0) {
              setNewHintIds(newOnes);
              setTimeout(() => setNewHintIds(new Set()), 3000);
            }
          }
          if (hData.length > 0) setLastTs(hData[0].ts);
          return hData;
        });
      }
      if (Array.isArray(lData)) setLeaderboard(lData);
    } catch (_) {}
    setLoading(false);
  }, [selectedChannel, limit, lastTs]);

  // Polling cada 5 segundos
  useEffect(() => {
    if (!selectedChannel) return;
    fetchData();
    pollingRef.current = setInterval(fetchData, 5000);
    return () => clearInterval(pollingRef.current);
  }, [selectedChannel, limit]);

  const maxHints = leaderboard.length > 0 ? leaderboard[0].hint_count : 1;

  return (
    <div className="widget-root">
      {/* ── Header ── */}
      <div className="widget-header">
        <div className="widget-logo">
          <span className="widget-logo-icon">🏝️</span>
          <span className="widget-logo-text">Twitchipelago</span>
          <span className="widget-badge">Hints Live</span>
        </div>
        <div className="widget-controls">
          {/* Selector de canal */}
          <div className="control-group">
            <label className="control-label">Canal</label>
            <select
              className="control-select"
              value={selectedChannel}
              onChange={(e) => setSelectedChannel(e.target.value)}
            >
              {channels.map((ch) => (
                <option key={ch} value={ch}>
                  #{ch}
                </option>
              ))}
              {channels.length === 0 && (
                <option value="">Sin datos aún</option>
              )}
            </select>
          </div>

          {/* Control de cantidad */}
          <div className="control-group">
            <label className="control-label">Mostrar últimos</label>
            <div className="control-number-wrap">
              <button
                className="ctrl-btn"
                onClick={() => setLimit((l) => Math.max(1, l - 1))}
              >
                −
              </button>
              <span className="ctrl-num">{limit}</span>
              <button
                className="ctrl-btn"
                onClick={() => setLimit((l) => Math.min(50, l + 1))}
              >
                +
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="tab-switcher">
            <button
              className={`tab-btn ${tab === "feed" ? "tab-btn--active" : ""}`}
              onClick={() => setTab("feed")}
            >
              📋 Feed
            </button>
            <button
              className={`tab-btn ${tab === "leaderboard" ? "tab-btn--active" : ""}`}
              onClick={() => setTab("leaderboard")}
            >
              🏆 Ranking
            </button>
          </div>
        </div>
      </div>

      {/* ── Pulso de live ── */}
      <div className="widget-live-bar">
        <span className="live-dot" />
        <span className="live-text">
          {selectedChannel ? `#${selectedChannel}` : "Selecciona un canal"} ·
          actualizando cada 5s
        </span>
        <span className="live-count">
          {hints.length} hint{hints.length !== 1 ? "s" : ""} cargados
        </span>
      </div>

      {/* ── Contenido ── */}
      <div className="widget-body">
        {loading ? (
          <div className="widget-empty">
            <div className="spinner" />
            <span>Cargando hints...</span>
          </div>
        ) : tab === "feed" ? (
          hints.length === 0 ? (
            <div className="widget-empty">
              <span className="empty-icon">🔍</span>
              <span>Aún no hay hints en este canal.</span>
              <span className="empty-sub">
                Los hints aparecerán aquí en cuanto alguien active una
                recompensa.
              </span>
            </div>
          ) : (
            <div className="hint-list">
              {hints.map((h, i) => (
                <HintCard
                  key={h.ts + h.user + i}
                  hint={h}
                  isNew={newHintIds.has(h.ts + h.user)}
                />
              ))}
            </div>
          )
        ) : leaderboard.length === 0 ? (
          <div className="widget-empty">
            <span className="empty-icon">🏆</span>
            <span>Aún no hay datos de ranking.</span>
          </div>
        ) : (
          <div className="leaderboard">
            <div className="lb-header">
              <span>Jugador</span>
              <span>Hints activados</span>
            </div>
            {leaderboard.map((row, i) => (
              <LeaderboardRow
                key={row.user}
                rank={i}
                user={row.user}
                count={row.hint_count}
                max={maxHints}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Footer ── */}
      <div className="widget-footer">
        <span>🏝️ Twitchipelago Widget</span>
        <span>
          URL de OBS:{" "}
          <code>
            /hints?channel={selectedChannel || "canal"}&amp;limit={limit}
          </code>
        </span>
      </div>
    </div>
  );
}

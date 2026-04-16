import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  BarChart2, Zap, Star, Gift, Lightbulb, Users, Clock,
  ChevronDown, ChevronUp, LayoutDashboard, Radio, RefreshCw,
  CalendarDays, Activity
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:5000");
const apiFetch = (path, opts = {}) =>
  fetch(`${API}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...opts });

// ── Event type display helpers ────────────────────────────────────────────────
const EVENT_META = {
  bits:            { label: '💎 Bits',         color: 'text-indigo-300',  bg: 'bg-indigo-500/10 border-indigo-500/20' },
  sub:             { label: '⭐ Sub',           color: 'text-yellow-300',  bg: 'bg-yellow-500/10 border-yellow-500/20' },
  gift_sub:        { label: '🎁 Gift Sub',      color: 'text-fuchsia-300', bg: 'bg-fuchsia-500/10 border-fuchsia-500/20' },
  gift_sub_bomb:   { label: '💣 Gift Bomb',     color: 'text-rose-300',    bg: 'bg-rose-500/10 border-rose-500/20' },
  hint_triggered:  { label: '🏝️ Hint',         color: 'text-emerald-300', bg: 'bg-emerald-500/10 border-emerald-500/20' },
};
const eventMeta = (type) => EVENT_META[type] || { label: type, color: 'text-slate-400', bg: 'bg-slate-800' };

// ── Stat Card ──────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, color, sub }) {
  return (
    <div className={`relative flex flex-col gap-2 bg-slate-900/60 backdrop-blur-xl border rounded-2xl p-5 shadow-xl overflow-hidden ${color.border}`}>
      <div className={`absolute -top-4 -right-4 w-20 h-20 rounded-full blur-2xl opacity-20 ${color.glow}`} />
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${color.icon_bg}`}>
        <Icon size={18} className={color.icon} />
      </div>
      <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mt-1">{label}</p>
      <p className={`text-3xl font-black tracking-tight ${color.value}`}>{value.toLocaleString()}</p>
      {sub && <p className="text-xs text-slate-600">{sub}</p>}
    </div>
  );
}

// ── Section Header ─────────────────────────────────────────────────────────────
function SectionHeader({ icon: Icon, title, subtitle, iconColor }) {
  return (
    <div className="flex items-center gap-3 mb-6">
      <div className={`p-2.5 rounded-xl ${iconColor}`}>
        <Icon size={20} className="opacity-80" />
      </div>
      <div>
        <h2 className="text-lg font-black text-slate-100">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function Stats() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [expandedChannels, setExpandedChannels] = useState({});

  const fetchStats = useCallback(async () => {
    try {
      // Check auth first
      const me = await apiFetch('/auth/me');
      const meData = await me.json();
      if (!meData.logged_in) { navigate('/'); return; }

      const res = await apiFetch('/api/stats');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
    } catch (e) {
      setError(`No se pudo cargar stats: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  const toggleChannel = (ch) =>
    setExpandedChannels(prev => ({ ...prev, [ch]: !prev[ch] }));

  // ── Loading ──
  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <RefreshCw size={28} className="text-indigo-400 animate-spin" />
    </div>
  );

  // ── Error ──
  if (error) return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center gap-4 text-slate-400">
      <p className="text-rose-400 font-semibold">{error}</p>
      <Link to="/" className="text-sm underline text-indigo-400">Volver al Panel</Link>
    </div>
  );

  const { session, alltime, events = [], session_start, channels = [] } = data || {};

  // Group events by channel for the detail section
  const eventsByChannel = channels.reduce((acc, ch) => {
    acc[ch] = events.filter(e => e.channel === ch);
    return acc;
  }, {});
  // Events with no channel filter (show all if no channels configured)
  const allEvents = events;

  const sessionCards = [
    { icon: Zap,      label: 'Bits',          value: session?.total_bits || 0,     color: { border: 'border-indigo-500/20', glow: 'bg-indigo-500', icon_bg: 'bg-indigo-500/20', icon: 'text-indigo-400', value: 'text-indigo-300' } },
    { icon: Star,     label: 'Subs',           value: session?.total_subs || 0,     color: { border: 'border-yellow-500/20', glow: 'bg-yellow-500', icon_bg: 'bg-yellow-500/20', icon: 'text-yellow-400', value: 'text-yellow-300' } },
    { icon: Gift,     label: 'Gift Subs',      value: session?.total_gift_subs || 0, color: { border: 'border-fuchsia-500/20', glow: 'bg-fuchsia-500', icon_bg: 'bg-fuchsia-500/20', icon: 'text-fuchsia-400', value: 'text-fuchsia-300' } },
    { icon: Lightbulb,label: 'Hints Lanzados', value: session?.total_hints || 0,    color: { border: 'border-emerald-500/20', glow: 'bg-emerald-500', icon_bg: 'bg-emerald-500/20', icon: 'text-emerald-400', value: 'text-emerald-300' } },
    { icon: Users,    label: 'Donadores Únicos', value: session?.unique_donors || 0, color: { border: 'border-cyan-500/20', glow: 'bg-cyan-500', icon_bg: 'bg-cyan-500/20', icon: 'text-cyan-400', value: 'text-cyan-300' } },
  ];

  const alltimeCards = [
    { icon: Zap,      label: 'Bits (Total)',         value: alltime?.total_bits || 0,     color: { border: 'border-slate-700', glow: 'bg-slate-600', icon_bg: 'bg-slate-800', icon: 'text-slate-400', value: 'text-slate-300' } },
    { icon: Star,     label: 'Subs (Total)',          value: alltime?.total_subs || 0,     color: { border: 'border-slate-700', glow: 'bg-slate-600', icon_bg: 'bg-slate-800', icon: 'text-slate-400', value: 'text-slate-300' } },
    { icon: Gift,     label: 'Gift Subs (Total)',     value: alltime?.total_gift_subs || 0, color: { border: 'border-slate-700', glow: 'bg-slate-600', icon_bg: 'bg-slate-800', icon: 'text-slate-400', value: 'text-slate-300' } },
    { icon: Lightbulb,label: 'Hints (Total)',         value: alltime?.total_hints || 0,    color: { border: 'border-slate-700', glow: 'bg-slate-600', icon_bg: 'bg-slate-800', icon: 'text-slate-400', value: 'text-slate-300' } },
    { icon: Users,    label: 'Donadores Únicos (Total)', value: alltime?.unique_donors || 0, color: { border: 'border-slate-700', glow: 'bg-slate-600', icon_bg: 'bg-slate-800', icon: 'text-slate-400', value: 'text-slate-300' } },
  ];

  const displayChannels = channels.length > 0 ? channels : (allEvents.length > 0 ? ['todos'] : []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-indigo-500/30">
      {/* Background glows */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/10 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-emerald-600/10 blur-[100px] rounded-full" />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto p-6 lg:p-10">

        {/* ── Nav Header ── */}
        <div className="flex items-center justify-between mb-12">
          <div>
            <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-emerald-400 to-cyan-300 bg-clip-text text-transparent">
              Stats & Transparencia
            </h1>
            <p className="text-slate-400 mt-2 text-sm font-medium">Métricas de participación y efectividad del sistema de hints</p>
          </div>
          <nav className="hidden md:flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-xl p-1">
            <Link to="/" className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all">
              <LayoutDashboard size={15} /> Panel
            </Link>
            <Link to="/tracker" className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all">
              <Radio size={15} /> Tracker
            </Link>
            <span className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white shadow-lg shadow-emerald-900/40">
              <BarChart2 size={15} /> Stats
            </span>
          </nav>
        </div>

        {/* ══════════════════════════════════════════════════════ */}
        {/* SECCIÓN 1 — STATS DE SESIÓN                          */}
        {/* ══════════════════════════════════════════════════════ */}
        <div className="mb-12">
          <SectionHeader
            icon={Activity}
            iconColor="bg-indigo-500/20 text-indigo-400"
            title="📊 Stats de esta Sesión"
            subtitle={
              session_start
                ? `Desde que el bot arrancó: ${session_start}`
                : 'No se detectó una sesión activa reciente'
            }
          />
          {session_start ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              {sessionCards.map((c) => (
                <StatCard key={c.label} {...c} />
              ))}
            </div>
          ) : (
            <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center">
              <p className="text-slate-500 italic text-sm">
                Inicia el bot para comenzar a registrar la sesión.
              </p>
            </div>
          )}
        </div>

        {/* ══════════════════════════════════════════════════════ */}
        {/* SECCIÓN 2 — STATS ALL-TIME                           */}
        {/* ══════════════════════════════════════════════════════ */}
        <div className="mb-12">
          <SectionHeader
            icon={CalendarDays}
            iconColor="bg-slate-700/60 text-slate-400"
            title="📈 Stats Generales (All-Time)"
            subtitle="Totales históricos acumulados desde el inicio del proyecto"
          />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {alltimeCards.map((c) => (
              <StatCard key={c.label} {...c} />
            ))}
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════ */}
        {/* SECCIÓN 3 — EVENTOS DETALLADOS (desplegable)         */}
        {/* ══════════════════════════════════════════════════════ */}
        <div>
          <SectionHeader
            icon={BarChart2}
            iconColor="bg-fuchsia-500/20 text-fuchsia-400"
            title="📋 Eventos Detallados"
            subtitle="Registro completo de cada interacción — total transparencia"
          />

          {allEvents.length === 0 ? (
            <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center">
              <p className="text-slate-500 italic text-sm">
                No hay eventos registrados todavía. Los bits, subs y hints aparecerán aquí en tiempo real.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {displayChannels.map((ch) => {
                const chEvents = ch === 'todos' ? allEvents : (eventsByChannel[ch] || []);
                const isOpen = expandedChannels[ch] ?? false;

                return (
                  <div key={ch} className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                    {/* Accordion header */}
                    <button
                      onClick={() => toggleChannel(ch)}
                      className="w-full flex items-center justify-between px-6 py-4 hover:bg-slate-800/40 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-slate-800 flex items-center justify-center text-base font-black text-indigo-400">
                          {ch.charAt(0).toUpperCase()}
                        </div>
                        <div className="text-left">
                          <p className="text-sm font-bold text-slate-200">#{ch}</p>
                          <p className="text-xs text-slate-500">{chEvents.length} eventos registrados</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {/* Mini stat pills */}
                        <div className="hidden sm:flex items-center gap-2">
                          <span className="text-xs px-2 py-1 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                            💎 {chEvents.filter(e => e.type === 'bits').reduce((s, e) => s + e.amount, 0)} bits
                          </span>
                          <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                            🏝️ {chEvents.filter(e => e.type === 'hint_triggered').length} hints
                          </span>
                        </div>
                        {isOpen ? <ChevronUp size={16} className="text-slate-500" /> : <ChevronDown size={16} className="text-slate-500" />}
                      </div>
                    </button>

                    {/* Event table */}
                    {isOpen && (
                      <div className="border-t border-slate-800 overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="bg-slate-950/50">
                              <th className="px-4 py-3 text-left font-semibold text-slate-500 uppercase tracking-wider">Hora</th>
                              <th className="px-4 py-3 text-left font-semibold text-slate-500 uppercase tracking-wider">Tipo</th>
                              <th className="px-4 py-3 text-left font-semibold text-slate-500 uppercase tracking-wider">Usuario</th>
                              <th className="px-4 py-3 text-right font-semibold text-slate-500 uppercase tracking-wider">Monto</th>
                              <th className="px-4 py-3 text-left font-semibold text-slate-500 uppercase tracking-wider">Detalle</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50">
                            {chEvents.map((ev, i) => {
                              const meta = eventMeta(ev.type);
                              return (
                                <tr key={i} className="hover:bg-slate-800/30 transition-colors">
                                  <td className="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">
                                    {ev.ts ? ev.ts.split(' ')[1] : '—'}
                                    <span className="block text-[10px] text-slate-700">{ev.ts ? ev.ts.split(' ')[0] : ''}</span>
                                  </td>
                                  <td className="px-4 py-3">
                                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${meta.bg} ${meta.color}`}>
                                      {meta.label}
                                    </span>
                                  </td>
                                  <td className="px-4 py-3 font-medium text-slate-300">
                                    {ev.user || <span className="text-slate-600 italic">—</span>}
                                  </td>
                                  <td className="px-4 py-3 text-right font-bold text-slate-200">
                                    {ev.amount > 0 ? ev.amount.toLocaleString() : '—'}
                                  </td>
                                  <td className="px-4 py-3 text-slate-400 max-w-xs truncate">
                                    {ev.detail || ev.reward_id || <span className="text-slate-700 italic">—</span>}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

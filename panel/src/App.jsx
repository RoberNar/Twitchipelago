import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Play, Square, Save, Server, Twitch, Terminal, RefreshCw, Key, Plus, Trash2, Megaphone, LogOut, ChevronDown, ChevronUp, LayoutDashboard, Radio, BarChart2 } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:5000");

const apiFetch = (path, opts = {}) => fetch(`${API}${path}`, {
  credentials: 'include',
  ...opts,
  headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
});

// ── Login Screen ──────────────────────────────────────────────────────────────
function LoginScreen() {
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center relative overflow-hidden">
      {/* Background glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-indigo-600/20 blur-[150px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-fuchsia-600/15 blur-[120px] rounded-full pointer-events-none" />

      <div className="relative z-10 flex flex-col items-center gap-8 px-4">
        {/* Logo */}
        <div className="text-center">
          <h1 className="text-5xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-400 to-cyan-300 bg-clip-text text-transparent mb-2">
            🏝️ Twitchipelago
          </h1>
          <p className="text-slate-400 text-base font-medium">Multi-Stream Archipelago Bot</p>
        </div>

        {/* Card */}
        <div className="bg-slate-900/70 backdrop-blur-2xl border border-slate-800 rounded-3xl p-10 shadow-2xl w-full max-w-md text-center">
          <div className="w-16 h-16 bg-indigo-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
            <Twitch size={36} className="text-indigo-400" />
          </div>
          <h2 className="text-xl font-bold text-slate-100 mb-2">Conecta tu cuenta</h2>
          <p className="text-slate-400 text-sm mb-8 leading-relaxed">
            Inicia sesión con Twitch para acceder a tu dashboard y configurar tu bot de Archipelago.
          </p>
          <a
            href={`${API}/auth/twitch`}
            className="inline-flex items-center gap-3 bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-8 py-3.5 rounded-xl shadow-lg shadow-indigo-900/50 transition-all active:scale-95 text-base"
          >
            <Twitch size={20} />
            Conectar con Twitch
          </a>
          <p className="text-slate-600 text-xs mt-6">
            Solo se solicita lectura de tu perfil público.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function App() {
  const [authState, setAuthState] = useState('loading'); // 'loading' | 'unauthenticated' | 'authenticated'
  const [currentUser, setCurrentUser] = useState(null);
  const [config, setConfig] = useState({
    twitch: { client_id: '', access_token: '', bot_nick: '', refresh_token: '', client_secret: '' },
    archipelago: { host: '', port: 62979, password: '' },
    announcer: { enabled: false, interval_minutes: 15 },
    players: [],
    rewards: []
  });
  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const location = useLocation();
  const logsEndRef = useRef(null);
  const prevLogsLengthRef = useRef(0);

  // ── Session check ──────────────────────────────────────────────────────────
  const checkSession = useCallback(async () => {
    try {
      const res = await apiFetch('/auth/me');
      const data = await res.json();
      if (data.logged_in) {
        setCurrentUser(data.user);
        setAuthState('authenticated');
      } else {
        setAuthState('unauthenticated');
      }
    } catch {
      setAuthState('unauthenticated');
    }
  }, []);

  const handleLogout = async () => {
    await apiFetch('/auth/logout', { method: 'POST' });
    setAuthState('unauthenticated');
    setCurrentUser(null);
  };

  // ── Data fetchers ──────────────────────────────────────────────────────────
  const fetchConfig = useCallback(async () => {
    try {
      const res = await apiFetch('/api/config');
      if (res.ok) setConfig(await res.json());
    } catch (e) { console.error("Error fetching config", e); }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await apiFetch('/api/logs');
      if (res.ok) setLogs((await res.json()).logs || []);
    } catch { /* silent */ }
  }, []);

  const checkStatus = useCallback(async () => {
    try {
      const res = await apiFetch('/api/bot/status');
      if (res.ok) setIsRunning((await res.json()).running);
      else setIsRunning(false);
    } catch { setIsRunning(false); }
  }, []);

  // ── Effects ────────────────────────────────────────────────────────────────
  useEffect(() => { checkSession(); }, [checkSession]);

  useEffect(() => {
    if (authState !== 'authenticated') return;
    fetchConfig();
    checkStatus();
    const statusInterval = setInterval(checkStatus, 3000);
    const logsInterval = setInterval(fetchLogs, 2000);
    return () => { clearInterval(statusInterval); clearInterval(logsInterval); };
  }, [authState, fetchConfig, checkStatus, fetchLogs]);

  // Only scroll when new log lines are added (not on initial load)
  useEffect(() => {
    if (logs.length > prevLogsLengthRef.current) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    prevLogsLengthRef.current = logs.length;
  }, [logs]);

  // ── Actions ────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setIsSaving(true);
    try {
      await apiFetch('/api/config', { method: 'POST', body: JSON.stringify(config) });
    } catch { alert("Error saving config"); }
    setTimeout(() => setIsSaving(false), 800);
  };

  const toggleBot = async () => {
    const endpoint = isRunning ? 'stop' : 'start';
    try {
      await apiFetch(`/api/bot/${endpoint}`, { method: 'POST' });
      checkStatus();
    } catch { alert(`Error ${endpoint}ing bot`); }
  };

  // ── Config updaters ────────────────────────────────────────────────────────
  const updateAP = (k, v) => setConfig(p => ({ ...p, archipelago: { ...p.archipelago, [k]: v } }));
  const updateTwitch = (k, v) => setConfig(p => ({ ...p, twitch: { ...p.twitch, [k]: v } }));
  const updateAnnouncer = (k, v) => setConfig(p => ({ ...p, announcer: { ...p.announcer, [k]: v } }));

  const addPlayer = () => setConfig(p => ({ ...p, players: [...(p.players || []), { twitch_channel: '', ap_player_name: '' }] }));
  const updatePlayer = (idx, field, val) => {
    const newPlayers = [...config.players];
    newPlayers[idx][field] = val;
    setConfig({ ...config, players: newPlayers });
  };
  const removePlayer = (idx) => {
    const newPlayers = [...config.players];
    newPlayers.splice(idx, 1);
    setConfig({ ...config, players: newPlayers });
  };
  const updateReward = (idx, field, val) => {
    const newRewards = [...config.rewards];
    newRewards[idx][field] = val;
    setConfig({ ...config, rewards: newRewards });
  };

  // ── Render gates ───────────────────────────────────────────────────────────
  if (authState === 'loading') {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <RefreshCw size={28} className="text-indigo-400 animate-spin" />
      </div>
    );
  }
  if (authState === 'unauthenticated') return <LoginScreen />;

  // ── Full Dashboard ─────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-indigo-500/30">
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/20 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-fuchsia-600/10 blur-[100px] rounded-full" />
      </div>

      <div className="relative z-10 max-w-7xl mx-auto p-6 lg:p-10">

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
          <div>
            <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-400 to-cyan-300 bg-clip-text text-transparent">
              Twitchipelago
            </h1>
            <p className="text-slate-400 mt-2 text-sm font-medium">Multi-Stream Bot Orchestrator</p>
          </div>

          {/* Navigation links */}
          <nav className="hidden md:flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-xl p-1">
            <Link
              to="/"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                location.pathname === '/'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <LayoutDashboard size={15} />
              Panel
            </Link>
            <Link
              to="/tracker"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                location.pathname === '/tracker'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Radio size={15} />
              Tracker
            </Link>
            <Link
              to="/stats"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                location.pathname === '/stats'
                  ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <BarChart2 size={15} />
              Stats
            </Link>
          </nav>

          <div className="flex items-center gap-4">
            {/* Bot status pill */}
            <div className={`flex items-center gap-2 px-4 py-2 rounded-full border ${isRunning ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-rose-500/10 border-rose-500/20 text-rose-400'}`}>
              <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
              <span className="text-sm font-semibold tracking-wide uppercase">{isRunning ? 'Online' : 'Offline'}</span>
            </div>
            {/* Start/Stop */}
            <button onClick={toggleBot} className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold shadow-lg transition-all active:scale-95 ${isRunning ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-900/50 text-white' : 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-900/50 text-white'}`}>
              {isRunning ? <Square size={18} className="fill-current" /> : <Play size={18} className="fill-current" />}
              {isRunning ? 'Stop Bot' : 'Start Bot'}
            </button>
            {/* User avatar + logout */}
            {currentUser && (
              <div className="flex items-center gap-3 pl-4 border-l border-slate-800">
                {currentUser.avatar_url ? (
                  <img src={currentUser.avatar_url} alt={currentUser.display_name} className="w-9 h-9 rounded-full border-2 border-indigo-500/40 object-cover" />
                ) : (
                  <div className="w-9 h-9 rounded-full bg-indigo-500/30 flex items-center justify-center text-indigo-300 font-bold text-sm">
                    {currentUser.display_name?.[0]?.toUpperCase()}
                  </div>
                )}
                <div className="hidden md:flex flex-col">
                  <span className="text-sm font-semibold text-slate-200 leading-none">{currentUser.display_name}</span>
                  <span className="text-xs text-slate-500 mt-0.5">Organizador</span>
                </div>
                <button onClick={handleLogout} title="Cerrar sesión" className="p-2 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors">
                  <LogOut size={16} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* Settings Column */}
          <div className="lg:col-span-5 space-y-6">

            {/* Archipelago Connection */}
            <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400"><Server size={20} /></div>
                <h2 className="text-lg font-bold text-slate-100">Archipelago Network</h2>
              </div>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Host</label>
                    <input type="text" value={config?.archipelago?.host || ''} onChange={e => updateAP('host', e.target.value)}
                      className="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-all placeholder:text-slate-600" placeholder="archipelago.gg" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Port</label>
                    <input type="number" value={config?.archipelago?.port || ''} onChange={e => updateAP('port', parseInt(e.target.value) || 0)}
                      className="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-all" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider flex items-center gap-1"><Key size={12} /> Server Password</label>
                  <input type="password" value={config?.archipelago?.password || ''} onChange={e => updateAP('password', e.target.value)}
                    className="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-all" />
                </div>
              </div>
            </div>

            {/* Advanced / Bot Credentials (collapsible) */}
            <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
              <button
                onClick={() => setShowAdvanced(v => !v)}
                className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-slate-800/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="p-1.5 bg-slate-700/50 rounded-lg text-slate-400"><Key size={16} /></div>
                  <div>
                    <span className="text-sm font-bold text-slate-300">Configuración Avanzada del Bot</span>
                    <p className="text-xs text-slate-500 mt-0.5">Credenciales del bot de Twitch — ya cargadas desde config</p>
                  </div>
                </div>
                {showAdvanced ? <ChevronUp size={16} className="text-slate-500" /> : <ChevronDown size={16} className="text-slate-500" />}
              </button>

              {showAdvanced && (
                <div className="px-6 pb-6 pt-1 space-y-4 border-t border-slate-800">
                  <p className="text-xs text-slate-500 bg-slate-950/50 rounded-lg p-3 mt-3">
                    🤖 <strong className="text-slate-400">Un solo bot para todos los canales.</strong> Estas credenciales son del bot centralizado que el organizador configura una vez. Los participantes solo necesitan ser agregados en "Participant Roster" arriba.
                  </p>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Bot Nick</label>
                    <input type="text" value={config?.twitch?.bot_nick || ''} onChange={e => updateTwitch('bot_nick', e.target.value)}
                      className="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-fuchsia-500 transition-all" placeholder="twitchipelagobot" />
                  </div>
                  <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-4">
                    <p className="text-sm font-semibold text-fuchsia-400 flex items-center gap-2 mb-1">
                      <Key size={14} /> Tokens protegidos
                    </p>
                    <p className="text-xs text-slate-400">
                      El <strong>Access Token</strong> y <strong>Client ID</strong> ya no figuran en la interfaz por seguridad en vivo. 
                      Ahora se gestionan automáticamente a través de tu inicio de sesión de Twitch y las Variables de Entorno en Railway.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Players Mapping */}
            <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-fuchsia-500/20 rounded-lg text-fuchsia-400"><Twitch size={20} /></div>
                  <h2 className="text-lg font-bold text-slate-100">Participant Roster</h2>
                </div>
                <button onClick={addPlayer} className="flex items-center justify-center p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors">
                  <Plus size={16} />
                </button>
              </div>
              <div className="space-y-3">
                {(!config?.players || config.players.length === 0) && (
                  <p className="text-sm text-slate-500 italic mb-2">No players added. Click + to map a Twitch channel to an Archipelago slot.</p>
                )}
                {config?.players?.map((p, idx) => (
                  <div key={idx} className="flex gap-2 items-center bg-slate-950/50 border border-slate-800/80 p-3 rounded-lg">
                    <div className="flex-1 space-y-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-fuchsia-500 w-16">TWITCH:</span>
                        <input type="text" value={p.twitch_channel || ''} onChange={e => updatePlayer(idx, 'twitch_channel', e.target.value)} placeholder="Channel Name" className="w-full bg-transparent border-b border-slate-700 text-sm focus:outline-none focus:border-fuchsia-500 py-1" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-indigo-400 w-16">AP SLOT:</span>
                        <input type="text" value={p.ap_player_name || ''} onChange={e => updatePlayer(idx, 'ap_player_name', e.target.value)} placeholder="In-Game Name" className="w-full bg-transparent border-b border-slate-700 text-sm focus:outline-none focus:border-indigo-500 py-1" />
                      </div>
                    </div>
                    <button onClick={() => removePlayer(idx)} className="p-2 text-rose-500 hover:bg-rose-500/10 rounded-md transition-colors">
                      <Trash2 size={18} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Pro Reward Configurator ── */}
            <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <BarChart2 size={18} className="text-amber-400" />
                  <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Reward Rules</h2>
                </div>
                <button
                  onClick={() => setConfig(p => ({
                    ...p,
                    rewards: [...(p.rewards || []), {
                      id: `reward_${Date.now()}`, name: 'Nueva Recompensa', enabled: true,
                      trigger_type: 'bits_fixed', cost: 200, bits_per_hint: 500,
                      sub_goal: 5, cooldown_seconds: 0
                    }]
                  }))}
                  className="flex items-center gap-1 text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <Plus size={13} /> Add Rule
                </button>
              </div>

              {(!config?.rewards || config.rewards.length === 0) && (
                <p className="text-sm text-slate-500 italic">Sin reglas configuradas. Haz click en "Add Rule" para crear la primera.</p>
              )}

              {config?.rewards?.map((r, idx) => {
                const tt = r.trigger_type || 'bits_fixed';
                const triggerLabels = {
                  bits_fixed: '💎 Bits Fijos',
                  bits_accumulation: '📊 Bits Acumulados',
                  sub: '⭐ Por Sub',
                  sub_goal: '🎯 Sub Goal',
                };
                const triggerColors = {
                  bits_fixed: 'border-indigo-500/40 bg-indigo-500/5',
                  bits_accumulation: 'border-amber-500/40 bg-amber-500/5',
                  sub: 'border-fuchsia-500/40 bg-fuchsia-500/5',
                  sub_goal: 'border-emerald-500/40 bg-emerald-500/5',
                };
                const barMax = tt === 'bits_accumulation' ? (r.bits_per_hint || 500) : (r.sub_goal || 5);
                return (
                  <div key={idx} className={`border rounded-xl p-4 space-y-3 transition-all ${r.enabled ? triggerColors[tt] : 'border-slate-800 opacity-50'}`}>
                    {/* Header row */}
                    <div className="flex items-center gap-3">
                      <input type="checkbox" checked={r.enabled || false}
                        onChange={e => updateReward(idx, 'enabled', e.target.checked)}
                        className="w-4 h-4 rounded accent-indigo-500 flex-shrink-0" />
                      <input type="text" value={r.name || ''}
                        onChange={e => updateReward(idx, 'name', e.target.value)}
                        className="flex-1 bg-transparent text-sm font-bold text-slate-200 focus:outline-none border-b border-transparent focus:border-slate-600 py-0.5" />
                      <button onClick={() => setConfig(p => ({ ...p, rewards: p.rewards.filter((_, i) => i !== idx) }))}
                        className="p-1 text-slate-600 hover:text-rose-400 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>

                    {/* Trigger type selector */}
                    <div>
                      <label className="block text-[10px] font-bold text-slate-500 mb-1.5 uppercase tracking-widest">Tipo de trigger</label>
                      <div className="grid grid-cols-2 gap-1.5">
                        {Object.entries(triggerLabels).map(([val, label]) => (
                          <button key={val} onClick={() => updateReward(idx, 'trigger_type', val)}
                            className={`text-xs px-2 py-1.5 rounded-lg font-semibold transition-all text-left ${tt === val ? 'bg-slate-700 text-slate-100 ring-1 ring-slate-500' : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'}`}>
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Contextual config */}
                    <div className="flex items-end gap-4 flex-wrap">
                      {tt === 'bits_fixed' && (
                        <label className="text-xs text-slate-400 flex items-center gap-2">
                          <span className="font-semibold">Costo exacto</span>
                          <input type="number" value={r.cost || 0}
                            onChange={e => updateReward(idx, 'cost', parseInt(e.target.value) || 0)}
                            className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 focus:outline-none focus:border-indigo-500 text-slate-200" />
                          <span className="text-slate-600">bits</span>
                        </label>
                      )}
                      {tt === 'bits_accumulation' && (
                        <div className="flex-1 space-y-2">
                          <label className="text-xs text-slate-400 flex items-center gap-2">
                            <span className="font-semibold">Cada</span>
                            <input type="number" value={r.bits_per_hint || 500}
                              onChange={e => updateReward(idx, 'bits_per_hint', parseInt(e.target.value) || 100)}
                              className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 focus:outline-none focus:border-amber-500 text-slate-200" />
                            <span className="text-slate-600">bits = 1 hint</span>
                          </label>
                          {/* Visual progress bar preview */}
                          <div className="space-y-1">
                            <div className="flex justify-between text-[10px] text-slate-600">
                              <span>Progreso acumulado</span>
                              <span>0 / {r.bits_per_hint || 500} bits</span>
                            </div>
                            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full bg-gradient-to-r from-amber-500 to-yellow-400 rounded-full transition-all" style={{ width: '0%' }} />
                            </div>
                          </div>
                        </div>
                      )}
                      {tt === 'sub' && (
                        <p className="text-xs text-slate-400">
                          Cada <strong className="text-fuchsia-400">sub o renovación</strong> activa esta recompensa individualmente.
                        </p>
                      )}
                      {tt === 'sub_goal' && (
                        <label className="text-xs text-slate-400 flex items-center gap-2">
                          <span className="font-semibold">Meta</span>
                          <input type="number" value={r.sub_goal || 5}
                            onChange={e => updateReward(idx, 'sub_goal', parseInt(e.target.value) || 1)}
                            className="w-16 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 focus:outline-none focus:border-emerald-500 text-slate-200" />
                          <span className="text-slate-600">subs = 1 hint</span>
                        </label>
                      )}
                      {/* Cooldown — common */}
                      <label className="text-xs text-slate-400 flex items-center gap-2 ml-auto">
                        <span className="font-semibold">CD</span>
                        <input type="number" value={r.cooldown_seconds || 0}
                          onChange={e => updateReward(idx, 'cooldown_seconds', parseInt(e.target.value) || 0)}
                          className="w-16 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 focus:outline-none focus:border-slate-500 text-slate-200" />
                        <span className="text-slate-600">s</span>
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Announcer */}
            <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-4">
                <Megaphone size={16} className="text-cyan-400" />
                <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Chat Announcer</h2>
              </div>
              <div className={`p-4 rounded-lg border ${config.announcer?.enabled ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-slate-800 bg-slate-950/50'}`}>
                <label className="flex items-center gap-3 cursor-pointer mb-3">
                  <input type="checkbox" checked={config.announcer?.enabled || false}
                    onChange={e => updateAnnouncer('enabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500" />
                  <span className="text-sm font-medium">Broadcast Public Tracker Link</span>
                </label>
                <label className="text-xs text-slate-400 flex items-center gap-2">
                  Message every
                  <input type="number" disabled={!config.announcer?.enabled}
                    value={config.announcer?.interval_minutes || 0}
                    onChange={e => updateAnnouncer('interval_minutes', parseInt(e.target.value) || 0)}
                    className="w-16 bg-slate-900 border border-slate-700 rounded px-2 py-1 disabled:opacity-50 text-center" />
                  minutes
                </label>
              </div>
            </div>

            {/* Save Button */}
            <button onClick={handleSave} disabled={isSaving} className="w-full flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 py-3 rounded-xl font-semibold transition-all shadow-md active:scale-95 disabled:opacity-50">
              {isSaving ? <RefreshCw size={18} className="animate-spin text-indigo-400" /> : <Save size={18} className="text-indigo-400" />}
              {isSaving ? 'Saving Configuration...' : 'Save Configuration'}
            </button>
          </div>

          {/* Console Column */}
          <div className="lg:col-span-7 h-[600px] lg:h-[calc(100vh-6rem)] lg:sticky lg:top-8 flex flex-col">
            <div className="flex-1 bg-black border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
              <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Terminal size={16} className="text-slate-500" />
                  <span className="text-xs font-mono text-slate-400 font-semibold tracking-wide">bot.log</span>
                </div>
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-rose-500/20 border border-rose-500/50" />
                  <div className="w-3 h-3 rounded-full bg-amber-500/20 border border-amber-500/50" />
                  <div className="w-3 h-3 rounded-full bg-emerald-500/20 border border-emerald-500/50" />
                </div>
              </div>
              <div className="flex-1 p-4 overflow-y-auto font-mono text-xs sm:text-sm leading-relaxed text-slate-300">
                {logs.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-slate-600 italic">No logs available. Start the bot to see output.</div>
                ) : (
                  logs.map((line, i) => {
                    let colorClass = 'text-slate-300';
                    if (line.includes('[ERROR]')) colorClass = 'text-rose-400 font-semibold';
                    else if (line.includes('[INFO]')) colorClass = 'text-cyan-200';
                    else if (line.includes('[WARNING]')) colorClass = 'text-amber-300';
                    if (line.includes('✅')) colorClass = 'text-emerald-400';
                    if (line.includes('💎')) colorClass = 'text-fuchsia-400 font-bold';
                    if (line.includes('🏝️')) colorClass = 'text-indigo-300 font-bold';
                    return <div key={i} className={`whitespace-pre-wrap ${colorClass}`}>{line}</div>;
                  })
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

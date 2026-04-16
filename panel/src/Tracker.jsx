import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Trophy, CheckCircle2, Wifi, WifiOff, Gamepad2 } from 'lucide-react';

export default function Tracker() {
    const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:5000");
    const [trackerState, setTrackerState] = useState({});
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchState = async () => {
            try {
                const res = await axios.get(`${API}/api/tracker`);
                console.log("Tracker Data:", res.data); // Debugging display info
                setTrackerState(res.data);
                setError(null);
            } catch (err) {
                console.error("Error fetching tracker state:", err);
                setError("No se pudo conectar con el servidor.");
            }
        };

        fetchState();
        const interval = setInterval(fetchState, 5000);
        return () => clearInterval(interval);
    }, []);

    // Sort channels by completion percentage descending
    const channels = Object.entries(trackerState)
        .sort(([, a], [, b]) => (b.completion_percentage || 0) - (a.completion_percentage || 0));

    return (
        <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-indigo-500/30 p-6 lg:p-12">
            {/* Background Ambient Glow */}
            <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
                <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-indigo-600/10 blur-[130px] rounded-full" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-fuchsia-600/10 blur-[120px] rounded-full" />
            </div>

            <div className="relative z-10 max-w-6xl mx-auto">
                <div className="text-center mb-16">
                    <div className="inline-flex items-center justify-center p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-2xl mb-6 shadow-[0_0_30px_rgba(99,102,241,0.2)]">
                        <Trophy className="text-indigo-400 w-10 h-10" />
                    </div>
                    <h1 className="text-5xl md:text-6xl font-black tracking-tight bg-gradient-to-br from-indigo-300 via-white to-fuchsia-300 bg-clip-text text-transparent mb-4">
                        Progreso de la Run
                    </h1>
                    <p className="text-slate-400 text-lg md:text-xl max-w-2xl mx-auto font-medium">
                        Sigue en vivo el avance de todos los participantes y descubre quién va ganando.
                    </p>
                    {error && <p className="text-rose-400 mt-4 font-semibold">{error}</p>}
                </div>

                {channels.length === 0 && !error && (
                    <div className="text-center p-12 bg-slate-900/40 backdrop-blur-sm border border-slate-800 rounded-3xl">
                        <p className="text-slate-500 text-lg italic">Esperando a que el bot envíe datos...</p>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {channels.map(([channelUrl, state]) => {
                        const isConnected = state.connected;
                        const pct = state.completion_percentage || 0;
                        const formattedPct = Math.min(100, Math.max(0, pct)); // Clamp just in case

                        return (
                            <div
                                key={channelUrl}
                                className="group relative bg-slate-900/60 backdrop-blur-xl border border-slate-800 hover:border-indigo-500/50 rounded-3xl p-6 transition-all duration-500 hover:shadow-[0_0_40px_rgba(99,102,241,0.15)] hover:-translate-y-1 overflow-hidden"
                            >
                                {/* Progress Bar Background */}
                                <div
                                    className="absolute bottom-0 left-0 h-1 bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-1000 ease-out"
                                    style={{ width: `${formattedPct}%` }}
                                />

                                <div className="flex justify-between items-start mb-6">
                                    <div className="flex items-center gap-4">
                                        {/* Clickable Avatar */}
                                        <a
                                            href={`https://twitch.tv/${channelUrl}`}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="relative shrink-0 block hover:scale-105 transition-transform duration-200"
                                        >
                                            {state.avatar_url ? (
                                                <img
                                                    src={state.avatar_url}
                                                    alt={`${channelUrl} avatar`}
                                                    className="w-14 h-14 rounded-xl object-cover ring-2 ring-indigo-500/30 shadow-lg"
                                                />
                                            ) : (
                                                <div className="w-14 h-14 rounded-xl bg-slate-800 flex items-center justify-center ring-2 ring-indigo-500/30 shadow-lg">
                                                    <span className="text-xl font-black text-indigo-400">
                                                        {channelUrl.charAt(0).toUpperCase()}
                                                    </span>
                                                </div>
                                            )}
                                        </a>

                                        <div className="flex flex-col">
                                            <h2 className="text-2xl font-bold text-white mb-1">
                                                <a href={`https://twitch.tv/${channelUrl}`} target="_blank" rel="noreferrer" className="hover:text-indigo-300 transition-colors">
                                                    {channelUrl}
                                                </a>
                                            </h2>
                                            <div className="flex items-center gap-1.5 text-sm text-slate-400 font-medium">
                                                <Gamepad2 size={14} className="text-fuchsia-400" />
                                                {state.game || 'Desconocido'}
                                            </div>
                                        </div>
                                    </div>

                                    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ${isConnected ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-rose-500/10 border-rose-500/20 text-rose-400'}`}>
                                        {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
                                        {isConnected ? 'ONLINE' : 'OFFLINE'}
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="flex items-end justify-between">
                                        <div>
                                            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Player</p>
                                            <p className="font-medium text-slate-200">{state.ap_player_name}</p>
                                        </div>

                                        <div className="text-right">
                                            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Progreso</p>
                                            <div className="flex items-baseline gap-1 justify-end">
                                                <span className="text-3xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-white to-slate-400">
                                                    {formattedPct}%
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="pt-4 border-t border-slate-800/60 flex items-center justify-between text-sm">
                                        <div className="flex items-center gap-2 text-slate-400">
                                            <CheckCircle2 size={16} className="text-indigo-400" />
                                            <span>{state.total_checks - state.missing_checks} / {state.total_checks} Checks</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

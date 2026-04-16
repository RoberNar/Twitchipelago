# 🏝️ Twitchipelago

Bot para conectar la funcionalidad de recompensas, suscripciones y bits de Twitch (Multicanal) con eventos de **Archipelago Randomizer** para juegos cooperativos de multiples mundos.

## Características 🚀

- **Multistream Tracker**: Observa el progreso de todos los streamers de la cooperativa en tiempo real.
- **Hints por Recompensas**: Usa donaciones (Bits) y Suscripciones para gatillar el servidor automático de hints a favor de la persona que donó.
- **Full Backend Configurable**: Panel de control con React (Vite) para que el host mantenga todo organizado fácilmente.
- **OBS Ready Widget**: Widget especial translúcido (`/hints`) listo para cargar en OBS, mostrando las donaciones activadas.

## Tecnologías 🛠️

- **Backend**: Python (Flask, Gunicorn) y TwitchIO (Conexiones al Chat de twitch en tiempo real).
- **Frontend**: React.JS, Tailwind CSS
- **Base de Datos**: PostgreSQL / SQLite
- **Deployment**: Monolítico, listo para Railway.

import asyncio
from main import load_config
from bot.archipelago_client import ArchipelagoClient
from bot.rewards import RewardManager
from bot.twitch_client import TwitchBot
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stdout)

async def test_init():
    cfg = load_config()
    print("✅ Config cargada:", list(cfg.keys()))

    players = cfg.get("players", [])
    print(f"✅ Jugadores configurados: {len(players)}")

    ap_clients = {}
    connected_channels = []

    for player in players:
        tw = player.get("twitch_channel", "").lower()
        ap = player.get("ap_player_name", "")
        print(f"  -> Mapeando Twitch #{tw} a AP '{ap}'")

        if tw and ap:
            # We don't actually connect so we don't spam Archipelago
            ap_clients[tw] = True
            connected_channels.append(tw)

    print("✅ Canales Twitch listos para conectar:", connected_channels)

    # Init reward manager
    rewards = cfg.get("rewards_config", [])
    print(f"✅ Recompensas configuradas: {len(rewards)}")
    rm = RewardManager(rewards)
    
    match = rm.get_matching_reward(1)
    if match:
        print(f"✅ Recompensa de 1 bit mapeada a: {match.get('name')}")
    else:
        print("❌ Recompensa de 1 bit NO mapeada (Error)")

if __name__ == "__main__":
    asyncio.run(test_init())

#!/usr/bin/env python3
import asyncio
import signal
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/mc-manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    from server_manager import MinecraftServerManager
    from discord_bot import MinecraftServerBot
    
    server_manager = MinecraftServerManager("./config.yaml")
    bot = MinecraftServerBot(server_manager, "./config.yaml")
    
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Shutting down...")
        asyncio.create_task(bot.shutdown())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        await bot.shutdown()

if __name__ == "__main__":
    config_path = Path("./config.yaml")
    if not config_path.exists():
        logger.error("config.yaml not found!")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")

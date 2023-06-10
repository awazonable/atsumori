#!/usr/bin/env python3
import discord
from discord.ext import commands

DISCORD_TOKEN = ""
COMMAND_PREFIX = '$'

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
    
    async def setup_hook(self):
            
        await bot.load_extension('voice')

        await self.tree.sync()
        print("Successfully synced commands")
        print(f"Logged onto {self.user}")

if __name__ == '__main__':
    bot = Bot()
    bot.run(DISCORD_TOKEN)
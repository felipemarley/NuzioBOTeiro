import os
import discord
from discord.ext import commands
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

class NuzioBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents, help_command=None)
    async def setup_hook(self):
        """Este hook é chamado para carregar os cogs e sincronizar os comandos."""
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != '__init__.py':
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'✅ Cog carregado: {filename[:-3]}')
                except Exception as e:
                    print(f'❌ Falha ao carregar o cog {filename[:-3]}: {e}')
        
        try:
            synced = await self.tree.sync()
            print(f'-> {len(synced)} comandos de barra "/" sincronizados.')
        except Exception as e:
            print(f"Erro ao sincronizar comandos de barra: {e}")

    async def on_ready(self):
        print(f'✅ Bot conectado como {self.user.name}')
        print('------')

async def main():
    bot = NuzioBot()
    if TOKEN is None:
        print("ERRO CRÍTICO: O token do Discord não foi encontrado.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
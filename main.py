import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

# --- Configuração Inicial ---

# Carrega a variável de ambiente (o token) do arquivo .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Define as "intents" (permissões) que o bot precisa
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

# Cria a instância do bot com um prefixo de comando (ex: !play)
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para gerenciar a fila de cada servidor (guild)
server_queues = {}

# Opções para o yt-dlp para extrair o áudio
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'extract_flat': 'in_playlist'
}



@bot.event
async def on_ready():
    """Este evento é acionado quando o bot se conecta com sucesso ao Discord."""
    print(f'✅ Bot conectado como {bot.user.name}')
    print('------')


async def play_next(ctx):
    """Função recursiva para tocar a próxima música da fila do servidor."""
    guild_id = ctx.guild.id
    if guild_id in server_queues and len(server_queues[guild_id]) > 0:
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and not voice_client.is_playing():
            song = server_queues[guild_id].pop(0)
            url = song['url']
            title = song['title']

            try:
                ffmpeg_options = {
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn'
                }
                source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
                voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))
                await ctx.send(f'▶️ Tocando agora: **{title}**')
            except Exception as e:
                print(f"Erro ao tocar a música: {e}")
                await ctx.send(f"❌ Ocorreu um erro ao tentar tocar **{title}**.")
                await play_next(ctx)



@bot.command(name='play', help='Toca uma música ou playlist do Sua Música')
async def play(ctx, *, url: str):
    """Comando principal para tocar música."""
    if not ctx.author.voice:
        await ctx.send("Você precisa estar em um canal de voz para usar este comando!")
        return

    channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client is None:
        await channel.connect()
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    await ctx.send(f"🔎 Procurando por: `{url}`...")
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        await ctx.send("Ocorreu um erro ao buscar a música. Verifique o link.")
        print(e)
        return

    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = []

    if '_type' in info and info['_type'] == 'playlist':
        for entry in info.get('entries', []):
            if entry:
                server_queues[ctx.guild.id].append({'url': entry['url'], 'title': entry.get('title', 'Título Desconhecido')})
        await ctx.send(f'✅ Playlist **{info.get("title", "Desconhecida")}** adicionada à fila com {len(info.get("entries", []))} músicas!')
    else:
        server_queues[ctx.guild.id].append({'url': info['url'], 'title': info.get('title', 'Título Desconhecido')})
        await ctx.send(f'👍 Adicionado à fila: **{info.get("title", "Título Desconhecido")}**')

    if not discord.utils.get(bot.voice_clients, guild=ctx.guild).is_playing():
        await play_next(ctx)

@bot.command(name='skip', help='Pula a música atual')
async def skip(ctx):
    """Pula a música que está tocando."""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏭️ Música pulada!")
    else:
        await ctx.send("Não há nenhuma música tocando.")

@bot.command(name='stop', help='Para a música e limpa a fila')
async def stop(ctx):
    """Para a reprodução, limpa a fila e desconecta o bot."""
    if ctx.guild.id in server_queues:
        server_queues[ctx.guild.id] = []

    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("⏹️ Fila limpa e bot desconectado. Até mais!")
    else:
        await ctx.send("O bot não está conectado a um canal de voz.")


if __name__ == "__main__":
    if TOKEN is None:
        print("ERRO: O token do Discord não foi encontrado. Verifique seu arquivo .env")
    else:
        bot.run(TOKEN)
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

# --- Configuração Inicial ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Definimos as permissões (intents) que o bot precisa
intents = discord.Intents.default()
intents.message_content = True  # Necessário para comandos de prefixo '!'
intents.voice_states = True
intents.guilds = True

# Usamos commands.Bot que é feito para lidar com prefixos e slash commands
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para gerenciar a fila de cada servidor
server_queues = {}

# --- Lógica de Música Reutilizável ---

async def play_next(guild: discord.Guild, text_channel: discord.TextChannel):
    """Toca a próxima música da fila do servidor."""
    guild_id = guild.id
    if guild_id in server_queues and len(server_queues[guild_id]) > 0:
        voice_client = discord.utils.get(bot.voice_clients, guild=guild)
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
                voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(guild, text_channel)))
                await text_channel.send(f'▶️ Tocando agora: **{title}**')
            except Exception as e:
                print(f"Erro detalhado ao tocar: {e}")
                await text_channel.send(f"❌ Ocorreu um erro ao tentar tocar **{title}**.")
                await play_next(guild, text_channel)

# --- Eventos do Bot ---
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user.name}')
    print(f'-> Comandos de prefixo "!" estão prontos.')
    try:
        synced = await bot.tree.sync()
        print(f'-> {len(synced)} comandos de barra "/" enviados para sincronização.')
    except Exception as e:
        print(f"Erro ao sincronizar comandos de barra: {e}")
    print('------')

async def core_play_logic(response_channel, voice_channel, guild, busca: str):
    """Função central que contém a lógica de play para ambos os tipos de comando."""
    # 1. Lógica Inteligente para links diretos
    is_direct_link = any(ext in busca for ext in ['.mp3', '.ogg', '.wav', '.m4a'])

    if is_direct_link:
        title = busca.split('/')[-1].split('?')[0]
        source_url = busca
        is_playlist = False
        playlist_title = None
    else:
        # 2. Lógica com yt-dlp para Youtube e outros sites
        search_query = f"ytsearch:{busca}" if not busca.startswith('http') else busca
        ydl_opts = {'format': 'bestaudio', 'noplaylist': False, 'quiet': True, 'default_search': 'auto'}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
        except Exception as e:
            print(f"Erro yt-dlp: {e}")
            await response_channel.send("Ocorreu um erro ao buscar a música. O site pode estar indisponível ou o link quebrado.")
            return

        if 'entries' in info: # É uma playlist
            is_playlist = True
            playlist_title = info.get("title", "Desconhecida")
            if guild.id not in server_queues: server_queues[guild.id] = []
            for entry in info.get('entries', []):
                if entry: server_queues[guild.id].append({'url': entry['url'], 'title': entry.get('title', 'Título')})
            
            first_song = server_queues[guild.id].pop(0)
            title = first_song['title']
            source_url = first_song['url']
        else: # É uma música única
            is_playlist = False
            title = info.get('title', 'Título')
            source_url = info.get('url')
    
    # 3. Lógica para conectar e tocar
    if not source_url:
        await response_channel.send("Não foi possível encontrar uma fonte de áudio válida.")
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if not voice_client: await voice_channel.connect()
    else: await voice_client.move_to(voice_channel)
    
    # Mensagem de confirmação
    if is_playlist:
        await response_channel.send(f'✅ Playlist **{playlist_title}** adicionada à fila!')
    elif not is_direct_link:
        await response_channel.send(f'👍 Adicionado à fila: **{title}**')

    # Adiciona a música única à fila se já estiver tocando algo
    if discord.utils.get(bot.voice_clients, guild=guild).is_playing():
        if not is_playlist:
            if guild.id not in server_queues: server_queues[guild.id] = []
            server_queues[guild.id].append({'url': source_url, 'title': title})
        return # Apenas adiciona e sai, play_next cuidará do resto

    # Toca a música
    try:
        ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        source = discord.FFmpegPCMAudio(source_url, **ffmpeg_options)
        voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(guild, response_channel)))
        await response_channel.send(f'▶️ Tocando agora: **{title}**')
    except Exception as e:
        print(f"Erro ao tocar com FFmpeg: {e}")
        await response_channel.send("Ocorreu um erro ao tentar reproduzir o áudio.")

# --- Seção de Comandos de Barra (/) ---

@bot.tree.command(name="play", description="Toca uma música (link ou nome para busca)")
@app_commands.describe(busca="Link da música/playlist ou o nome para buscar no YouTube")
async def slash_play(interaction: discord.Interaction, busca: str):
    await interaction.response.defer(thinking=True)
    if not interaction.user.voice:
        await interaction.followup.send("Você precisa estar em um canal de voz!", ephemeral=True)
        return
    await core_play_logic(interaction.followup, interaction.user.voice.channel, interaction.guild, busca)

@bot.tree.command(name="skip", description="Pula a música atual")
async def slash_skip(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ Música pulada!")
    else:
        await interaction.response.send_message("Não há nenhuma música tocando.", ephemeral=True)

@bot.tree.command(name="stop", description="Para a música e desconecta o bot")
async def slash_stop(interaction: discord.Interaction):
    if interaction.guild.id in server_queues: server_queues[interaction.guild.id] = []
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client: await voice_client.disconnect()
    await interaction.response.send_message("⏹️ Fila limpa e bot desconectado.")

# --- Seção de Comandos de Prefixo (!) ---

@bot.command(name='play', help='Toca uma música (link ou nome para busca)')
async def prefix_play(ctx: commands.Context, *, busca: str):
    if not ctx.author.voice:
        await ctx.send("Você precisa estar em um canal de voz!")
        return
    # Reutiliza a lógica principal, passando o contexto do prefixo
    await core_play_logic(ctx.channel, ctx.author.voice.channel, ctx.guild, busca)

@bot.command(name='skip', help='Pula a música atual')
async def prefix_skip(ctx: commands.Context):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏭️ Música pulada!")
    else:
        await ctx.send("Não há nenhuma música tocando.")

@bot.command(name='stop', help='Para a música e desconecta o bot')
async def prefix_stop(ctx: commands.Context):
    if ctx.guild.id in server_queues: server_queues[ctx.guild.id] = []
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client: await voice_client.disconnect()
    await ctx.send("⏹️ Fila limpa e bot desconectado.")

# --- Inicia o Bot ---
if __name__ == "__main__":
    if TOKEN is None:
        print("ERRO CRÍTICO: O token do Discord não foi encontrado. Verifique seu arquivo .env")
    else:
        bot.run(TOKEN)
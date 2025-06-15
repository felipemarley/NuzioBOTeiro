# cogs/suamusica_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import asyncio
import json

class SuaMusicaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Acessa o MusicCog para usar o mesmo estado e fila compartilhada
        self.music_cog = self.bot.get_cog('MusicCog')
        if not self.music_cog:
            print("AVISO CRÍTICO: MusicCog não foi encontrado. O SuaMusicaCog não funcionará.")

    def get_music_state(self, guild_id):
        """Garante que o estado do servidor exista, buscando no MusicCog."""
        if not self.music_cog: self.music_cog = self.bot.get_cog('MusicCog')
        return self.music_cog.get_server_state(guild_id)

    # --- TAREFAS BLOQUEANTES QUE SERÃO DELEGADAS PARA NÃO TRAVAR O BOT ---

    def scrape_and_parse_suamusica_blocking(self, playlist_url):
        """
        Executa o web scraping completo: baixa o HTML, analisa com BeautifulSoup,
        extrai o JSON e retorna a lista de músicas prontas.
        """
        response = requests.get(playlist_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', id='__NEXT_DATA__')
        if not script_tag:
            raise ValueError("Não foi possível encontrar a tag de dados '__NEXT_DATA__' na página.")
            
        data = json.loads(script_tag.string)
        
        try:
            # --- O CAMINHO CORRETO E DEFINITIVO PARA OS DADOS ---
            # Baseado no arquivo body.html que você forneceu.
            tracks_data = data['props']['pageProps']['playlist']['files']
        except KeyError as e:
            raise ValueError(f"A estrutura do JSON do site mudou. Chave não encontrada: {e}")
        
        if not tracks_data:
            raise ValueError("Encontrei a estrutura de dados, mas a lista de músicas ('files') está vazia.")
            
        queue_items = []
        for track in tracks_data:
            # O título está na chave 'file' e o ID na chave 'id'
            queue_items.append({
                'id': track.get('id'),
                'title': track.get('file', 'Título Desconhecido'),
                'source': 'SuaMusica'
            })
        return queue_items

    def get_track_download_url_blocking(self, track_id: int):
        """A partir de um ID de música, chama a API para obter o link de download."""
        api_url = f"https://www.suamusica.com.br/api/v2/track/download/{track_id}"
        api_response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        api_response.raise_for_status()
        return api_response.json().get('link')

    # --- COMANDO PRINCIPAL ---

    @app_commands.command(name="suamusica", description="Toca uma playlist do site Sua Música.")
    @app_commands.describe(playlist_url="O link da playlist do Sua Música")
    async def slash_suamusica_play(self, interaction: discord.Interaction, playlist_url: str):
        await interaction.response.defer(thinking=True)
        
        if not interaction.user.voice:
            await interaction.followup.send("Você precisa estar em um canal de voz!", ephemeral=True); return
        if "suamusica.com.br" not in playlist_url:
            await interaction.followup.send("Por favor, forneça um link válido do site Sua Música.", ephemeral=True); return
            
        try:
            loop = asyncio.get_event_loop()
            queue_items = await loop.run_in_executor(None, self.scrape_and_parse_suamusica_blocking, playlist_url)

            state = self.get_music_state(interaction.guild.id)
            is_playing_now = discord.utils.get(self.bot.voice_clients, guild=interaction.guild) and discord.utils.get(self.bot.voice_clients, guild=interaction.guild).is_playing()
            
            state['queue'].extend(queue_items)
            
            await interaction.followup.send(f"✅ Playlist do Sua Música encontrada! **{len(queue_items)}** músicas foram adicionadas à fila.")

            vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
            if not vc or not vc.is_connected():
                vc = await interaction.user.voice.channel.connect()
            
            if not is_playing_now:
                await self.play_next_suamusica(interaction.guild, interaction.channel)

        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao processar a playlist: {e}"); print(f"[SuaMusica] Erro: {e}")

    async def play_next_suamusica(self, guild: discord.Guild, text_channel: discord.TextChannel):
        """Versão adaptada do play_next para lidar com o fluxo do Sua Música e do YouTube."""
        state = self.get_music_state(guild.id)
        if not state['queue']:
            state['now_playing'] = None; return

        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client and voice_client.is_playing(): return

        song_to_play = state['queue'][0]
        # Se a próxima música for do YouTube, delega para o MusicCog
        if song_to_play.get('source') != 'SuaMusica':
            if self.music_cog:
                await self.music_cog.play_next(guild, text_channel)
            return
        
        # Se for do Sua Música, processa aqui
        state['queue'].pop(0)
        state['now_playing'] = song_to_play
        
        try:
            loop = asyncio.get_event_loop()
            download_link = await loop.run_in_executor(None, self.get_track_download_url_blocking, song_to_play['id'])
            if not download_link: raise Exception("A API do Sua Música não retornou um link de download.")

            ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
            source = discord.FFmpegPCMAudio(download_link, **ffmpeg_options)
            # A função a ser chamada depois que a música termina agora é esta mesma
            voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next_suamusica(guild, text_channel)))
            await text_channel.send(f'▶️ Tocando (Sua Música): **{song_to_play["title"]}**')

        except Exception as e:
            print(f"Erro ao obter/tocar link de '{song_to_play['title']}': {e}")
            await text_channel.send(f"❌ Falha ao tocar **{song_to_play['title']}**. Pulando.")
            await self.play_next_suamusica(guild, text_channel)


async def setup(bot: commands.Bot):
    """Função que o discord.py chama para carregar o Cog."""
    await bot.add_cog(SuaMusicaCog(bot))
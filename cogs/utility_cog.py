# cogs/utility_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import asyncio
import json

class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def scrape_playlist_details_blocking(self, playlist_url: str):
        """
        Função de scraping que baixa e analisa a página de uma playlist do Sua Música,
        extraindo o título da playlist e os detalhes de cada faixa (título e artista).
        """
        try:
            response = requests.get(playlist_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', id='__NEXT_DATA__')
            if not script_tag:
                raise ValueError("Não foi possível encontrar os dados da playlist na página (tag '__NEXT_DATA__').")
                
            data = json.loads(script_tag.string)
            
            # Caminho definitivo para os dados, que descobrimos funcionar
            playlist_data = data.get('props', {}).get('pageProps', {}).get('playlist', {})
            tracks_data = playlist_data.get('files', [])
            
            if not tracks_data:
                raise ValueError("Encontrei a estrutura de dados, mas a lista de músicas ('files') está vazia.")
            
            # Mapeia IDs de artistas para nomes para facilitar a busca
            artists_map = {artist['id']: artist['name'] for artist in playlist_data.get('usersPaginados', [])}
            
            song_details = []
            for track in tracks_data:
                artist_name = artists_map.get(track.get('ownerId'), 'Artista Desconhecido')
                song_details.append({
                    'title': track.get('file', 'Título Desconhecido'),
                    'artist': artist_name
                })

            playlist_info = {
                'title': playlist_data.get('title', 'Playlist Sem Título'),
                'tracks': song_details
            }
            return playlist_info

        except requests.RequestException as e:
            raise ValueError(f"Não consegui acessar o link. Erro de rede: {e}")
        except Exception as e:
            raise e

    @app_commands.command(name="listarsuamusica", description="Lista as músicas de uma playlist do site Sua Música.")
    @app_commands.describe(url_da_playlist="O link da playlist do Sua Música")
    async def slash_listarsuamusica(self, interaction: discord.Interaction, url_da_playlist: str):
        await interaction.response.defer(thinking=True)

        if "suamusica.com.br/playlist" not in url_da_playlist:
            await interaction.followup.send("Por favor, forneça um link de **playlist** válido do Sua Música.", ephemeral=True)
            return

        try:
            loop = asyncio.get_event_loop()
            
            # Executa a função de scraping em segundo plano
            playlist_info = await loop.run_in_executor(None, self.scrape_playlist_details_blocking, url_da_playlist)
            
            song_list = playlist_info['tracks']
            playlist_title = playlist_info['title']

            # Cria a mensagem de Embed para uma exibição elegante
            embed = discord.Embed(
                title=f"🎵 Músicas na Playlist: {playlist_title}",
                color=discord.Color.green()
            )

            # Formata a lista de músicas para caber no Discord
            description_text = ""
            for i, song in enumerate(song_list):
                line = f"`{i+1:02d}.` **{song['title']}** - *{song['artist']}*\n"
                # Verifica o limite de caracteres do Discord para a descrição do Embed (4096)
                if len(description_text) + len(line) > 4000:
                    description_text += "\n... e mais músicas (lista muito longa para exibir tudo)."
                    break
                description_text += line
            
            embed.description = description_text
            embed.set_footer(text=f"Total de {len(song_list)} músicas encontradas.")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao processar a playlist: {e}")
            print(f"[UtilityCog] Erro ao listar músicas do Sua Música: {e}")


async def setup(bot: commands.Bot):
    """Função que o discord.py chama para carregar o Cog."""
    await bot.add_cog(UtilityCog(bot))
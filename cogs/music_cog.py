import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.server_states = {}

    def get_server_state(self, guild_id):
        if guild_id not in self.server_states:
            self.server_states[guild_id] = {'queue': [], 'now_playing': None, 'prefetch_task': None, 'is_active': False}
        return self.server_states[guild_id]

    def ydl_extract_info_blocking(self, url_or_search, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url_or_search, download=False)

    async def _prefetch_queue(self, guild_id):
        state = self.get_server_state(guild_id)
        print(f"[{guild_id}] Iniciando tarefa de prefetch para {len(state['queue'])} itens.")
        for song_data in list(state['queue']):
            if not state.get('is_active', False):
                print(f"[{guild_id}] Prefetch cancelado."); break
            if song_data.get('stream_url'): continue
            try:
                loop = asyncio.get_event_loop()
                ydl_opts_song = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
                info = await loop.run_in_executor(None, self.ydl_extract_info_blocking, song_data['original_url'], ydl_opts_song)
                song_data['stream_url'] = info['url']
                print(f"[{guild_id}] Pré-carregado: {song_data['title']}")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[{guild_id}] Falha no pré-carregamento de '{song_data['title']}': {e}")
        print(f"[{guild_id}] Tarefa de prefetch concluída.")

    async def play_next(self, guild: discord.Guild, text_channel: discord.TextChannel):
        state = self.get_server_state(guild.id)
        if len(state['queue']) > 0:
            voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
            if voice_client and not voice_client.is_playing():
                song_data = state['queue'].pop(0)
                state['now_playing'] = song_data
                if not song_data.get('stream_url'):
                    try:
                        loop = asyncio.get_event_loop()
                        ydl_opts_song = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
                        info = await loop.run_in_executor(None, self.ydl_extract_info_blocking, song_data['original_url'], ydl_opts_song)
                        song_data['stream_url'] = info['url']
                    except Exception as e:
                        print(f"Erro ao processar '{song_data['title']}': {e}"); await text_channel.send(f"❌ Não consegui tocar **{song_data['title']}**. Pulando..."); await self.play_next(guild, text_channel); return
                
                try:
                    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
                    source = discord.FFmpegPCMAudio(song_data['stream_url'], **ffmpeg_options)
                    voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild, text_channel)))
                    await text_channel.send(f'▶️ Tocando agora: **{song_data["title"]}**')
                except Exception as e:
                    print(f"Erro ao tocar com FFmpeg: {e}"); await text_channel.send(f"❌ Erro ao reproduzir **{song_data['title']}**."); await self.play_next(guild, text_channel)
        else:
            state['now_playing'] = None
            state['is_active'] = False

    async def core_play_logic(self, response_channel, voice_channel, guild, busca: str):
        state = self.get_server_state(guild.id)
        state['is_active'] = True

        is_direct_link = any(ext in busca for ext in ['.mp3', '.ogg', '.wav', '.m4a'])
        
        queue_items, playlist_title = [], None
        
        if is_direct_link:
            queue_items.append({'original_url': busca, 'title': busca.split('/')[-1].split('?')[0], 'stream_url': busca})
        else:
            # Formata corretamente a busca para o yt-dlp
            search_query = busca if busca.startswith('http') else f"ytsearch:{busca}"
            ydl_opts = {'format': 'bestaudio', 'quiet': True, 'extract_flat': 'in_playlist', 'default_search': 'auto'}
            
            try:
                loop = asyncio.get_event_loop()
                # Passa a variável correta 'search_query' para o executor
                info = await loop.run_in_executor(None, self.ydl_extract_info_blocking, search_query, ydl_opts)
            except Exception as e:
                print(f"Erro yt-dlp: {e}")
                # Envia a mensagem de erro para o canal ou interação correta
                if hasattr(response_channel, 'send'): await response_channel.send("Ocorreu um erro ao buscar o conteúdo.")
                else: await response_channel.followup.send("Ocorreu um erro ao buscar o conteúdo.")
                return

            if 'entries' in info: # É uma playlist
                playlist_title = info.get("title", "Desconhecida")
                for entry in info.get('entries', []):
                    if entry: queue_items.append({'original_url': entry.get('url'), 'title': entry.get('title', 'Título indisponível'), 'stream_url': None})
            else: # É uma música única
                queue_items.append({'original_url': info.get('webpage_url') or info.get('url'), 'title': info.get('title', 'Título indisponível'), 'stream_url': info.get('url')})

        if not queue_items:
            if hasattr(response_channel, 'send'): await response_channel.send("Não consegui encontrar nada para tocar.")
            else: await response_channel.followup.send("Não consegui encontrar nada para tocar.")
            return

        is_playing_now = discord.utils.get(self.bot.voice_clients, guild=guild) and discord.utils.get(self.bot.voice_clients, guild=guild).is_playing()
        state['queue'].extend(queue_items)
        
        vc = discord.utils.get(self.bot.voice_clients, guild=guild)
        if not vc or not vc.is_connected(): vc = await voice_channel.connect()
        elif vc.channel != voice_channel: await vc.move_to(voice_channel)
        
        text_channel = response_channel if isinstance(response_channel, discord.TextChannel) else response_channel.channel
        response_target = response_channel.followup if hasattr(response_channel, 'followup') else response_channel

        if playlist_title:
            await response_target.send(f'✅ Playlist **{playlist_title}** com {len(queue_items)} músicas adicionada! Iniciando a primeira...')
        elif is_playing_now or len(state['queue']) > len(queue_items):
             await response_target.send(f"👍 Adicionado à fila: **{queue_items[0]['title']}**")
        
        if not is_playing_now: await self.play_next(guild, text_channel)
        if state.get('prefetch_task') is None or state['prefetch_task'].done():
            state['prefetch_task'] = self.bot.loop.create_task(self._prefetch_queue(guild.id))

    @app_commands.command(name="play", description="Toca uma música ou playlist")
    async def slash_play(self, interaction: discord.Interaction, busca: str):
        if not interaction.user.voice:
            await interaction.response.send_message("Você precisa estar em um canal de voz!", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await self.core_play_logic(interaction.followup, interaction.user.voice.channel, interaction.guild, busca)
    @commands.command(name='play')
    async def prefix_play(self, ctx: commands.Context, *, busca: str):
        if not ctx.author.voice:
            await ctx.send("Você precisa estar em um canal de voz!")
            return
        await self.core_play_logic(ctx.channel, ctx.author.voice.channel, ctx.guild, busca)

    @app_commands.command(name="pause", description="Pausa a música atual.")
    async def slash_pause(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if vc and vc.is_playing(): vc.pause(); await interaction.response.send_message("⏸️ Música pausada.")
        else: await interaction.response.send_message("Não há música tocando.", ephemeral=True)
    @commands.command(name='pause')
    async def prefix_pause(self, ctx: commands.Context):
        vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if vc and vc.is_playing(): vc.pause(); await ctx.send("⏸️ Música pausada.")
        else: await ctx.send("Não há música tocando.")

    @app_commands.command(name="resume", description="Continua a tocar a música.")
    async def slash_resume(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if vc and vc.is_paused(): vc.resume(); await interaction.response.send_message("▶️ Retomando.")
        else: await interaction.response.send_message("Não há música pausada.", ephemeral=True)
    @commands.command(name='resume')
    async def prefix_resume(self, ctx: commands.Context):
        vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if vc and vc.is_paused(): vc.resume(); await ctx.send("▶️ Retomando.")
        else: await ctx.send("Não há música pausada.")

    @app_commands.command(name="skip", description="Pula a música atual.")
    async def slash_skip(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if vc and vc.is_playing(): vc.stop(); await interaction.response.send_message("⏭️ Música pulada!")
        else: await interaction.response.send_message("Não há música tocando.", ephemeral=True)
    @commands.command(name='skip')
    async def prefix_skip(self, ctx: commands.Context):
        vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if vc and vc.is_playing(): vc.stop(); await ctx.send("⏭️ Música pulada!")
        else: await ctx.send("Não há música tocando.")

    @app_commands.command(name="stop", description="Para a música e desconecta o bot.")
    async def slash_stop(self, interaction: discord.Interaction):
        state = self.get_server_state(interaction.guild.id); state.update({'queue': [], 'now_playing': None, 'is_active': False})
        if state.get('prefetch_task'): state['prefetch_task'].cancel()
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild); 
        if vc: await vc.disconnect()
        await interaction.response.send_message("⏹️ Fila limpa e bot desconectado.")
    @commands.command(name='stop')
    async def prefix_stop(self, ctx: commands.Context):
        state = self.get_server_state(ctx.guild.id); state.update({'queue': [], 'now_playing': None, 'is_active': False})
        if state.get('prefetch_task'): state['prefetch_task'].cancel()
        vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if vc: await vc.disconnect()
        await ctx.send("⏹️ Fila limpa e bot desconectado.")

    @app_commands.command(name="queue", description="Mostra a fila de músicas.")
    async def slash_queue(self, interaction: discord.Interaction):
        state = self.get_server_state(interaction.guild.id)
        if not state.get('now_playing') and not state.get('queue'): return await interaction.response.send_message("A fila está vazia!", ephemeral=True)
        embed = discord.Embed(title="Fila de Músicas", color=discord.Color.blue())
        if state.get('now_playing'): embed.add_field(name="▶️ Tocando Agora", value=f"**{state['now_playing']['title']}**", inline=False)
        if state.get('queue'):
            queue_text = "".join([f"`{i+1}.` {s['title']}\n" for i, s in enumerate(state['queue'][:10])])
            if len(state['queue']) > 10: queue_text += f"\n... e mais {len(state['queue']) - 10} música(s)."
            embed.add_field(name="🎶 Próximas na Fila", value=queue_text, inline=False)
        await interaction.response.send_message(embed=embed)
    @commands.command(name='queue')
    async def prefix_queue(self, ctx: commands.Context):
        state = self.get_server_state(ctx.guild.id)
        if not state.get('now_playing') and not state.get('queue'): return await ctx.send("A fila está vazia!")
        embed = discord.Embed(title="Fila de Músicas", color=discord.Color.blue())
        if state.get('now_playing'): embed.add_field(name="▶️ Tocando Agora", value=f"**{state['now_playing']['title']}**", inline=False)
        if state.get('queue'):
            queue_text = "".join([f"`{i+1}.` {s['title']}\n" for i, s in enumerate(state['queue'][:10])])
            if len(state['queue']) > 10: queue_text += f"\n... e mais {len(state['queue']) - 10} música(s)."
            embed.add_field(name="🎶 Próximas na Fila", value=queue_text, inline=False)
        await ctx.send(embed=embed)
    
    @app_commands.command(name="remove", description="Remove uma música da fila pelo seu número.")
    async def slash_remove(self, interaction: discord.Interaction, numero: int):
        state = self.get_server_state(interaction.guild.id)
        if not state.get('queue'): return await interaction.response.send_message("A fila já está vazia.", ephemeral=True)
        if 1 <= numero <= len(state['queue']):
            removed_song = state['queue'].pop(numero - 1); await interaction.response.send_message(f"🗑️ Removido da fila: **{removed_song['title']}**")
        else: await interaction.response.send_message(f"Número inválido. Escolha um número entre 1 e {len(state['queue'])}.", ephemeral=True)
    @commands.command(name='remove')
    async def prefix_remove(self, ctx: commands.Context, numero: int):
        state = self.get_server_state(ctx.guild.id)
        if not state.get('queue'): return await ctx.send("A fila já está vazia.")
        try:
            numero = int(numero)
            if 1 <= numero <= len(state['queue']):
                removed_song = state['queue'].pop(numero - 1); await ctx.send(f"🗑️ Removido da fila: **{removed_song['title']}**")
            else: await ctx.send(f"Número inválido. Escolha um número entre 1 e {len(state['queue'])}.")
        except (ValueError, TypeError): await ctx.send("Por favor, forneça um número válido.")

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
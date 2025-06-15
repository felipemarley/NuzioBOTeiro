import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_help_embed(self):
        """Cria e retorna a mensagem de ajuda em formato Embed."""
        embed = discord.Embed(
            title="Ajuda do Nuzio BOTeiro",
            description="Aqui está a lista de todos os comandos disponíveis.",
            color=discord.Color.gold()
        )
        
        music_commands = (
            "`/play <busca>`: Toca uma música ou playlist do YouTube.\n"
            "`/pause`: Pausa a música atual.\n"
            "`/resume`: Continua a tocar a música pausada.\n"
            "`/skip`: Pula para a próxima música da fila.\n"
            "`/stop`: Para a música, desconecta e limpa a fila.\n"
            "`/queue`: Mostra a fila de músicas.\n"
            "`/remove <número>`: Remove uma música da fila."
        )
        embed.add_field(name="🎶 Comandos de Música (YouTube)", value=music_commands, inline=False)
        
        suamusica_commands = (
            "`/listarsuamusica <url_da_playlist>`: Lista todas as músicas de uma playlist do Sua Música."
        )
        embed.add_field(name="🎵 Utilitários Sua Música", value=suamusica_commands, inline=False)
        
        other_commands = (
            "`/help` ou `!help`: Mostra esta mensagem de ajuda."
        )
        embed.add_field(name="🤖 Outros Comandos", value=other_commands, inline=False)
        
        embed.set_footer(text="Use os comandos de barra (/) ou de prefixo (!) como preferir.")
        return embed

    @app_commands.command(name="help", description="Mostra todos os comandos disponíveis.")
    async def slash_help(self, interaction: discord.Interaction):
        embed = self.get_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name='help', aliases=['ajuda', 'comandos'])
    async def prefix_help(self, ctx: commands.Context):
        embed = self.get_help_embed()
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    """Função que o discord.py chama para carregar o Cog."""
    await bot.add_cog(HelpCog(bot))
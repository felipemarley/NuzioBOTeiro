# cogs/help_cog.py
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
            "`/play <busca>` ou `!play <busca>`: Toca uma música ou playlist.\n"
            "`/pause` ou `!pause`: Pausa a música atual.\n"
            "`/resume` ou `!resume`: Continua a tocar a música pausada.\n"
            "`/skip` ou `!skip`: Pula para a próxima música da fila.\n"
            "`/stop` ou `!stop`: Para a música, desconecta e limpa a fila.\n"
            "`/queue` ou `!queue`: Mostra a fila de músicas.\n"
            "`/remove <número>` ou `!remove <número>`: Remove uma música da fila."
        )
        embed.add_field(name="🎶 Comandos de Música", value=music_commands, inline=False)
        
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
    async def prefix_help(self, ctx: commands.Context): # AQUI ESTÁ A CORREÇÃO
        embed = self.get_help_embed()
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
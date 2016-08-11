import discord
from discord.ext import commands

class Say:
    """Echoes back the input."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(no_pm=True, pass_context=True)
        async def say(self, ctx, *, text):
            """Repeats what you tell it.
            Can use `message`, `channel`, `server`
            """
            user = ctx.message.author
            if hasattr(user, 'bot') and user.bot is True:
                return
            try:
                if "__" in text:
                    raise ValueError
                evald = eval(text, {}, {'message': ctx.message,
                                        'channel': ctx.message.channel,
                                        'server': ctx.message.server})
            except:
                evald = text
            if len(str(evald)) > 2000:
                evald = str(evald)[-1990:] + " you fuck."
            await self.bot.say(evald)

def setup(bot):
    bot.add_cog(Say(bot))

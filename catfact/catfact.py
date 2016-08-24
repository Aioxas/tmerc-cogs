import discord
from discord.ext import commands

import aiohttp
import json

class Catfact:
    """Gets random cat facts."""

    def __init__(self, bot):
        self.bot = bot
        self.url = "https://catfacts-api.appspot.com/api/facts?number=1"

    @commands.command(pass_context=True, no_pm=True, name="catfact")
    async def _catfact(self, context):
        """Gets a random cat fact."""

        self.bot.type()
        async with aiohttp.get(self.url) as response:
            fact = json.loads(await response.text())["facts"][0]
            await self.bot.say(fact)

def setup(bot):
    bot.add_cog(Catfact(bot))

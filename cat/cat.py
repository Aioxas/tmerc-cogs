import os
import random

import discord
from discord.ext import commands

try:
    from bs4 import BeautifulSoup
    soup_available = True
except:
    soup_available = False

import aiohttp
import json

class Cat:
    """Shows a random cat."""

    def __init__(self, bot):
        self.bot = bot
        self.url = 'http://random.cat/meow'

    @commands.command(pass_context=True, no_pm=True)
    async def cat(self, ctx):
        async with aiohttp.get(self.url) as response:
            j = json.loads(await response.text())
            await self.bot.say(j['file'])

def setup(bot):
    if soup_available:
        bot.add_cog(Cat(bot))
    else:
        raise RuntimeError('You need to run `pip3 install beautifulsoup4`')

from discord.ext import commands
from __main__ import send_cmd_help
from .utils import checks

import aiohttp
import asyncio
import glob
import json
import magic
import os
import os.path
import threading

class Playsound:
    """Play a sound byte."""
    def __init__(self, bot):
        self.bot = bot
        self.audio_player = False
        self.sound_base = "data/playsound"

    def list_sounds(self):
        return [os.path.splitext(s)[0] for s in os.listdir(self.sound_base)]

    def voice_connected(self, server):
        return self.bot.is_voice_connected(server)

    def voice_client(self, server):
        return self.bot.voice_client_in(server)

    async def _join_voice_channel(self, context):
        channel = context.message.author.voice_channel
        if channel:
            await self.bot.join_voice_channel(channel)

    async def _leave_voice_channel(self, context):
        server = context.message.server
        if not self.voice_connected(server):
            return
        voice_client = self.voice_client(server)

        # if self.audio_player:
        #     self.audio_player.stop()
        await voice_client.disconnect()

    def sound_init(self, context, path):
        server = context.message.server
        options = "-filter \"volume=volume=0.25\""
        voice_client = self.voice_client(server)
        return voice_client.create_ffmpeg_player(path, options=options)

    async def sound_play(self, context, p):
        server = context.message.server
        if not context.message.author.voice_channel:
            await self.bot.reply("You need to join a voice channel first.")
            return
        if not context.message.channel.is_private:
            if self.voice_connected(server):
                if not self.audio_player:
                    player = self.sound_init(context, p)
                    threading.Thread(target=self.sound_thread, args=(player, context,)).start()
                else:
                    if not self.audio_player.is_playing():
                    player = self.sound_init(context, p)
                    threading.Thread(target=self.sound_thread, args=(player, context,)).start()
            else:
                await self._join_voice_channel(context)
                if not self.audio_player:
                    player = self.sound_init(context, p)
                    threading.Thread(target=self.sound_thread, args=(player, context,)).start()
                else:
                    if not self.audio_player.is_playing():
                        player = self.sound_init(context, p)
                        threading.Thread(target=self.sound_thread, args=(player, context,)).start()

    def sound_thread(self, t, context):
        t.run()
        # self.voice_client(context.message.server).loop.create_task(self._leave_voice_channel(context))
        coro = self._leave_voice_channel(context)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop).result()

    @commands.command(no_pm=True, pass_context=True, name="playsound")
    async def _playsound(self, context, soundname):
        """Plays the specified sound."""
        f = glob.glob(os.path.join(self.sound_base, soundname + ".*"))
        if len(f) < 1:
            await self.bot.reply("Sound file not found. Try !allsounds for a list.")
            return
        elif len(f) > 1:
            await self.bot.reply("""There are {} sound files with the same name, but different extensions, and I can"t deal with it.
                                     Please make filenames (excluding extensions) unique.""".format(len(f)))
            return

        await self.sound_play(context, f[0])

    @commands.command(pass_context=True, name="allsounds")
    async def _allsounds(self, context):
        """Sends a list of every sound in a PM."""
        
        self.bot.type()
        strbuffer = self.list_sounds()
        mess = "```"
        for line in strbuffer:
            if len(mess) + len(line) + 4 < 2000:
                mess += "\n" + line
            else:
                mess += "```"
                await self.bot.whisper(mess)
                mess = "```"
        if mess != "":
            mess += "```"
            await self.bot.whisper(mess)

        await self.bot.reply("Check your PMs!")

    @commands.command(no_pm=True, pass_context=True, name="addsound")
    @checks.mod_or_permissions(administrator=True)
    async def _addsound(self, context, *link):
        """Adds a new sound. Either upload the file as a Discord attachment and make your comment \"!addsound\", or use \"!addsound direct-URL-to-file\". """
        
        self.bot.type()
        attach = context.message.attachments
        if len(attach) > 1 or (attach and link):
            await self.bot.reply("Please only add one sound at a time.")
            return

        url = ""
        filename = ""
        if attach:
            a = attach[0]
            url = a["url"]
            filename = a["filename"]
        elif link:
            url = "".join(link)
            filename = os.path.basename("_".join(url.split()).replace("%20", "_"))
        else:
            await self.bot.reply("You must provide either a Discord attachment or a direct link to a sound.")
            return

        filepath = os.path.join(self.sound_base, filename)

        if os.path.splitext(filename)[0] in self.list_sounds():
            await self.bot.reply("A sound with that filename already exists. Please change the filename and try again.")
            return

        async with aiohttp.get(url) as new_sound:
            f = open(filepath, "wb")
            f.write(await new_sound.read())
            f.close()
            if "audio" not in magic.from_file(filepath).lower():
                await self.bot.reply("The file you provided does not appear to be audio, please try again.")
                os.remove(filepath)
                return

        await self.bot.reply("Sound {} added.".format(os.path.splitext(filename)[0]))

    @commands.command(no_pm=True, pass_context=True, name="delsound")
    @checks.mod_or_permissions(administrator=True)
    async def _delsound(self, context, soundname):
        """Deletes an existing sound."""
        
        self.bot.type()
        f = glob.glob(os.path.join(self.sound_base, soundname + ".*"))
        if len(f) < 1:
            await self.bot.say("```Sound file not found! Try !allsounds.```")
            return
        elif len(f) > 1:
            await self.bot.say("""There are {} sound files with the same name, but different extensions, and I can"t deal with it.
                                     Please make filenames (excluding extensions) unique.""".format(len(f)))
            return

        os.remove(f[0])
        await self.bot.say("Sound {} deleted.".format(soundname))

def setup(bot):
    bot.add_cog(Playsound(bot))

import discord
from discord.ext import commands
from .utils.dataIO import fileIO
from .utils import checks, chat_formatting as cf
from __main__ import send_cmd_help

import aiohttp
import aioftp
import json
import os
import sqlite3
from tabulate import tabulate

default_settings = {
    "ftp_server": None,
    "ftp_username": None,
    "ftp_password": None,
    "ftp_dbpath": None,
    "steam_api_key": None
}

class SteamUrlError(Exception):
    pass

class Kz:
    """Gets KZ stats from a server. Use [p]kzset to set parameters."""

    def __init__(self, bot):
        self.bot = bot
        self.settings_path = "data/kz/settings.json"
        self.settings = fileIO(self.settings_path, "load")

    @commands.group(pass_context=True, no_pm=True, name="kzset")
    @checks.admin_or_permissions(manage_server=True)
    async def _kzset(self, context):
        """Sets KZ settings."""

        server = context.message.server
        if server.id not in self.settings:
            self.settings[server.id] = default_settings
            fileIO(self.settings_path, "save", self.settings)
            os.makedirs("data/kz/{}".format(server.id))
        if context.invoked_subcommand is None:
            await send_cmd_help(context)

    @_kzset.command(pass_context=True, no_pm=True, name="server")
    async def _server(self, context, server):
        """Set the FTP server."""

        serv = context.message.server
        self.settings[serv.id]["ftp_server"] = server
        fileIO(self.settings_path, "save", self.settings)
        await self.bot.reply(cf.info("Server set."))

    @_kzset.command(pass_context=True, no_pm=True, name="username")
    async def _username(self, context, username):
        """Set the FTP username."""

        server = context.message.server
        self.settings[server.id]["ftp_username"] = username
        fileIO(self.settings_path, "save", self.settings)
        await self.bot.reply(cf.info("Username set."))

    @_kzset.command(pass_context=True, no_pm=True, name="password")
    async def _password(self, context, password):
        """Set the FTP password."""

        server = context.message.server
        self.settings[server.id]["ftp_password"] = password
        fileIO(self.settings_path, "save", self.settings)

        await self.bot.delete_message(context.message)

        await self.bot.reply(cf.info("Password set."))

    @_kzset.command(pass_context=True, no_pm=True, name="dbpath")
    async def _dbpath(self, context, dbpath):
        """Set the server path to the database."""

        server = context.message.server
        self.settings[server.id]["ftp_dbpath"] = dbpath
        fileIO(self.settings_path, "save", self.settings)
        await self.bot.reply(cf.info("Path to database set."))

    @_kzset.command(pass_context=True, no_pm=True, name="steamkey")
    async def _steamkey(self, context, steamkey):
        """Sets the Steam API key."""

        server = context.message.server
        self.settings[server.id]["steam_api_key"] = steamkey
        fileIO(self.settings_path, "save", self.settings)

        await self.bot.delete_message(context.message)

        await self.bot.reply(cf.info("Steam API key set."))

    def _check_settings(self, server_id):
        server_settings = self.settings[server_id]
        return server_settings["ftp_server"] and server_settings["ftp_username"] and server_settings["ftp_password"] and server_settings["ftp_dbpath"] and server_settings["steam_api_key"]

    async def _update_database(self, server_id):
        info = self.settings[server_id]

        ftp = aioftp.Client()
        await ftp.connect(info["ftp_server"])
        await ftp.login(info["ftp_username"], info["ftp_password"])

        await ftp.download(info["ftp_dbpath"], "data/kz/{}/kztimer-sqlite.sq3".format(server_id), write_into=True)

        await ftp.quit()

    async def _steam_url_to_text_id(self, server_id, vanityurl):
        api_key = self.settings[server_id]["steam_api_key"]

        url = "http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={}&vanityurl={}".format(api_key, vanityurl)

        steam64_id = None
        async with aiohttp.get(url) as res:
            response = json.loads(await res.text())["response"]
            if response["success"] != 1:
                raise SteamUrlError("'{}' could not be resolved to a Steam vanity URL.".format(vanityurl))
            steam64_id = int(response["steamid"])

        account_id = steam64_id & ((1 << 32) - 1)
        universe = (steam64_id >> 56) & ((1 << 8) - 1)

        I = universe
        J = account_id & 1
        K = (account_id >> 1) & ((1 << 31) - 1)

        return "STEAM_{}:{}:{}".format(I, J, K)

    def _seconds_to_time_string(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)

        if h > 0:
            return "%d:%02d:%05.2f" % (h, m, s)
        else:
            return "%d:%05.2f" % (m, s)

    @commands.command(pass_context=True, no_pm=True, name="playerjumps")
    async def _playerjumps(self, context, player_url):
        """Gets a player's best jumps. You must provide the STEAM VANITY URL of the player, NOT the in-game name."""

        await self.bot.type()

        server = context.message.server
        if server.id not in self.settings:
            self.settings[server.id] = default_settings
            fileIO(self.settings_path, "save", self.settings)

        if not self._check_settings(server.id):
            await self.bot.reply(cf.error("You need to set up this cog before you can use it. Use `{}kzset`.".format(context.prefix)))
            return

        steamid = None
        try:
            steamid = await self._steam_url_to_text_id(server.id, player_url)
        except SteamUrlError as err:
            await self.bot.reply(cf.error("Could not resolve Steam vanity URL."))
            return

        await self._update_database(server.id)

        con = sqlite3.connect("data/kz/{}/kztimer-sqlite.sq3".format(server.id))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute(player_jumps_query, (steamid,))

        stats = cur.fetchone()
        cur.close()
        con.close()

        if not stats:
            await self.bot.reply(cf.warning("Player has no jumpstats in the server."))
            return

        title = "Jumpstats: {}".format(stats["name"])
        headers = ["Type", "Distance", "Strafes", "Pre", "Max", "Height", "Sync"]
        rows = []

        if stats["ljrecord"] != -1:
            rows.append(["LJ:", round(stats["ljrecord"], 3), stats["ljstrafes"], round(stats["ljpre"], 2), round(stats["ljmax"], 2), round(stats["ljheight"], 1), "{}%".format(stats["ljsync"])])
        if stats["ljblockrecord"] != -1:
            rows.append(["BlockLJ:", "{}|{}".format(stats["ljblockdist"], round(stats["ljblockrecord"], 1)), stats["ljblockstrafes"], round(stats["ljblockpre"], 2), round(stats["ljblockmax"], 2), round(stats["ljblockheight"], 1), "{}%".format(stats["ljblocksync"])])
        if stats["bhoprecord"] != -1:
            rows.append(["Bhop:", round(stats["bhoprecord"], 3), stats["bhopstrafes"], round(stats["bhoppre"], 2), round(stats["bhopmax"], 2), round(stats["bhopheight"], 1), "{}%".format(stats["bhopsync"])])
        if stats["dropbhoprecord"] != -1:
            rows.append(["D.-Bhop:", round(stats["dropbhoprecord"], 3), stats["dropbhopstrafes"], round(stats["dropbhoppre"], 2), round(stats["dropbhopmax"], 2), round(stats["dropbhopheight"], 1), "{}%".format(stats["dropbhopsync"])])
        if stats["multibhoprecord"] != -1:
            rows.append(["M.-Bhop:", round(stats["multibhoprecord"], 3), stats["multibhopstrafes"], round(stats["multibhoppre"], 2), round(stats["multibhopmax"], 2), round(stats["multibhopheight"], 1), "{}%".format(stats["multibhopsync"])])
        if stats["wjrecord"] != -1:
            rows.append(["WJ:", round(stats["wjrecord"], 3), stats["wjstrafes"], round(stats["wjpre"], 2), round(stats["wjmax"], 2), round(stats["wjheight"], 1), "{}%".format(stats["wjsync"])])
        if stats["cjrecord"] != -1:
            rows.append(["CJ:", round(stats["cjrecord"], 3), stats["cjstrafes"], round(stats["cjpre"], 2), round(stats["cjmax"], 2), round(stats["cjheight"], 1), "{}%".format(stats["cjsync"])])
        if stats["ladderjumprecord"] != -1:
            rows.append(["LAJ:", round(stats["ladderjumprecord"], 3), stats["ladderjumpstrafes"], round(stats["ladderjumppre"], 2), round(stats["ladderjumpmax"], 2), round(stats["ladderjumpheight"], 1), "{}%".format(stats["ladderjumpsync"])])

        if len(rows) == 0:
            await self.bot.reply(cf.warning("Player has no jumpstats in the server."))
            return

        table = tabulate(rows, headers, tablefmt="orgtbl")

        await self.bot.say(cf.box("{}\n{}".format(title, table)))

    @commands.command(pass_context=True, no_pm=True, name="playermap")
    async def _playermap(self, context, player_url, mapname):
        """Gets a certain player's times on the given map."""

        await self.bot.type()

        server = context.message.server
        if server.id not in self.settings:
            self.settings[server.id] = default_settings
            fileIO(self.settings_path, "save", self.settings)

        if not self._check_settings(server.id):
            await self.bot.reply(cf.error("You need to set up this cog before you can use it. Use `{}kzset`.".format(context.prefix)))
            return

        steamid = None
        try:
            steamid = await self._steam_url_to_text_id(server.id, player_url)
        except SteamUrlError as err:
            await self.bot.reply(cf.error("Could not resolve Steam vanity URL."))
            return

        mn = "%{}%".format(mapname)

        await self._update_database(server.id)

        con = sqlite3.connect("data/kz/{}/kztimer-sqlite.sq3".format(server.id))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute(player_maptime_query, (steamid, mn))

        r = cur.fetchone()
        if not r:
            await self.bot.say(cf.box("Player has no times on the given map."))
            return

        real_mapname = r["mapname"]
        headers = ["Type", "Time", "Teleports", "Rank"]
        rows = []

        if r["runtime"] > -1.0:
            cur.execute(player_mapranktotal_queries["tp"], (steamid, real_mapname, real_mapname, real_mapname))
            tpr = cur.fetchone()
            cur.close()
            rows.append(["TP", self._seconds_to_time_string(r["runtime"]), r["teleports"], "{}/{}".format(tpr["rank"], tpr["tot"])])
        else:
            rows.append(["TP", "--", "--", "--"])

        if r["runtimepro"] > -1.0:
            cur.execute(player_mapranktotal_queries["pro"], (steamid, real_mapname, real_mapname, real_mapname))
            pror = cur.fetchone()
            cur.close()
            rows.append(["PRO", self._seconds_to_time_string(r["runtimepro"]), r["teleports_pro"], "{}/{}".format(pror["rank"], pror["tot"])])
        else:
            rows.append(["PRO", "--", "--", "--"])

        con.close()

        title = "Map times for {} on {}".format(r["name"], real_mapname)
        table = tabulate(rows, headers, tablefmt="orgtbl")

        await self.bot.say(cf.box("{}\n{}".format(title, table)))

    @commands.command(pass_context=True, no_pm=True, name="maptop")
    async def _maptop(self, context, mapname, runtype="all", limit=10):
        """Gets the top times for a map. Optionally provide the run type (all by default) and the limit (10 by default)."""

        await self.bot.type()

        server = context.message.server
        if server.id not in self.settings:
            self.settings[server.id] = default_settings
            fileIO(self.settings_path, "save", self.settings)

        if not self._check_settings(server.id):
            await self.bot.reply(cf.error("You need to set up this cog before you can use it. Use `{}kzset`.".format(context.prefix)))
            return

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        rt = runtype.strip().lower()

        if rt not in ["all", "tp", "pro"]:
            await self.bot.reply(cf.error("The runtype must be one of `all`, `tp`, or `pro`."))
            return

        mn = "%{}%".format(mapname)

        await self._update_database(server.id)

        con = sqlite3.connect("data/kz/{}/kztimer-sqlite.sq3".format(server.id))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        if rt == "all":
            cur.execute(maptop_queries[rt], (mn, mn, lim))
        else:
            cur.execute(maptop_queries[rt], (mn, lim))

        r = cur.fetchone()
        if not r:
            await self.bot.say(cf.box("No times found."))
            return

        real_mapname = r["mapname"]

        headers = None
        if rt == "pro":
            headers = ["Rank", "Time", "Player"]
        else:
            headers = ["Rank", "Time", "Teleports", "Player"]

        rank = 0
        rows = []
        while r:
            rank += 1
            if rt == "pro":
                rows.append([rank, self._seconds_to_time_string(r["overall"]), r["name"]])
            else:
                rows.append([rank, self._seconds_to_time_string(r["overall"]), r["tp"], r["name"]])
            r = cur.fetchone()

        cur.close()
        con.close()

        title = "Top {} {}time{} on {}".format(min(rank, lim), "" if rt == "all" else rt.upper() + " ", "s" if rank > 1 else "", real_mapname)
        table = tabulate(rows, headers, tablefmt="orgtbl")

        await self.bot.say(cf.box("{}\n{}".format(title, table)))

    @commands.group(pass_context=True, no_pm=True, name="jumptop")
    async def _jumptop(self, context):
        """Gets the top stats for the given jump type. Optionally provide a limit (default is 10)."""

        server = context.message.server
        if server.id not in self.settings:
            self.settings[server.id] = default_settings
            fileIO(self.settings_path, "save", self.settings)

        if not self._check_settings(server.id):
            await self.bot.reply(cf.error("You need to set up this cog before you can use it. Use `{}kzset`.".format(context.prefix)))
            return

        if context.invoked_subcommand is None:
            await send_cmd_help(context)

    @_jumptop.command(pass_context=True, no_pm=True, name="blocklj", aliases=["blocklongjump"])
    async def blocklj(self, context, limit=10):
        """Gets the top BlockLJs."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "ljblock", "Block Longjump", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="lj", aliases=["longjump"])
    async def lj(self, context, limit=10):
        """Gets the top LJs."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "lj", "Longjump", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="bhop", aliases=["bunnyhop"])
    async def bhop(self, context, limit=10):
        """Gets the top Bhops."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "bhop", "Bunnyhop", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="multibhop", aliases=["multibunnyhop"])
    async def multibhop(self, context, limit=10):
        """Gets the top MultiBhops."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "multibhop", "Multi-Bunnyhop", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="dropbhop", aliases=["dropbunnyhop"])
    async def dropbhop(self, context, limit=10):
        """Gets the top DropBhops."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "dropbhop", "Drop-Bunnyhop", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="wj", aliases=["weirdjump"])
    async def wj(self, context, limit=10):
        """Gets the top WJs."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "wj", "Weirdjump", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="laj", aliases=["ladderjump"])
    async def laj(self, context, limit=10):
        """Gets the top LAJs."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "ladderjump", "Ladderjump", lim)

    @_jumptop.command(pass_context=True, no_pm=True, name="cj", aliases=["countjump"])
    async def cj(self, context, limit=10):
        """Gets the top CJs."""

        await self.bot.type()

        lim = None
        try:
            lim = int(limit)
        except ValueError:
            await self.bot.reply(cf.error("The limit you provided is not a number."))
            return

        await self._jumptop_helper(context.message.server.id, "cj", "Countjump", lim)

    async def _jumptop_helper(self, server_id, jumptype, jumpname, lim):
        con = sqlite3.connect("data/kz/{}/kztimer-sqlite.sq3".format(server_id))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute(jumptop_queries[jumptype], (lim,))

        r = cur.fetchone()
        if not r:
            await self.bot.say(cf.box("No jumps found."))
            return

        headers = None
        if jumptype == "ljblock":
            headers = ["Rank", "Block", "Distance", "Strafes", "Player"]
        else:
            headers = ["Rank", "Distance", "Strafes", "Player"]

        rank = 0
        rows = []
        while r:
            rank += 1
            if jumptype == "ljblock":
                rows.append([rank, r["ljblockdist"], r["ljblockrecord"], r["ljblockstrafes"], r["name"]])
            else:
                rows.append([rank, r["{}record".format(jumptype)], r["{}strafes".format(jumptype)], r["name"]])
            r = cur.fetchone()

        cur.close()
        con.close()

        title = "Top {} {}".format(min(rank, lim), jumpname)
        table = tabulate(rows, headers, tablefmt="orgtbl")

        await self.bot.say(cf.box("{}\n{}".format(title, table)))

def check_folders():
    if not os.path.exists("data/kz"):
        print("Creating data/kz directory...")
        os.makedirs("data/kz")

def check_files():
    f = "data/kz/settings.json"
    if not fileIO(f, "check"):
        print("Creating data/kz/settings.json...")
        fileIO(f, "save", {})

def setup(bot):
    check_folders()
    check_files()

    bot.add_cog(Kz(bot))

jumptop_queries = {
    "ljblock": "SELECT db1.name, db2.ljblockdist, db2.ljblockrecord, db2.ljblockstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE ljblockdist > -1 ORDER BY ljblockdist DESC, ljblockrecord DESC LIMIT ?;", # LIMIT
    "lj": "SELECT db1.name, db2.ljrecord, db2.ljstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE ljrecord > -1.0 ORDER BY ljrecord DESC LIMIT ?;", # LIMIT
    "bhop": "SELECT db1.name, db2.bhoprecord, db2.bhopstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE bhoprecord > -1.0 ORDER BY bhoprecord DESC LIMIT ?;", # LIMIT
    "multibhop": "SELECT db1.name, db2.multibhoprecord, db2.multibhopstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE multibhoprecord > -1.0 ORDER BY multibhoprecord DESC LIMIT ?;", # LIMIT
    "dropbhop": "SELECT db1.name, db2.dropbhoprecord, db2.dropbhopstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE db2.dropbhoprecord > -1.0 ORDER BY db2.dropbhoprecord DESC LIMIT ?;", # LIMIT
    "wj": "SELECT db1.name, db2.wjrecord, db2.wjstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE db2.wjrecord > -1.0 ORDER BY db2.wjrecord DESC LIMIT ?;", # LIMIT
    "ladderjump": "SELECT db1.name, db2.ladderjumprecord, db2.ladderjumpstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE ladderjumprecord > -1.0 ORDER BY ladderjumprecord DESC LIMIT ?;", # LIMIT
    "cj": "SELECT db1.name, db2.cjrecord, db2.cjstrafes FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid=db1.steamid WHERE cjrecord > -1.0 ORDER BY cjrecord DESC LIMIT ?;" # LIMIT
}

player_jumps_query = "SELECT db1.name, db2.bhoprecord, db2.bhoppre, db2.bhopmax, db2.bhopstrafes, db2.bhopsync, db2.bhopheight, db2.ljrecord, db2.ljpre, db2.ljmax, db2.ljstrafes, db2.ljsync, db2.ljheight, db2.multibhoprecord, db2.multibhoppre, db2.multibhopmax, db2.multibhopstrafes, db2.multibhopcount, db2.multibhopsync, db2.multibhopheight, db2.wjrecord, db2.wjpre, db2.wjmax, db2.wjstrafes, db2.wjsync, db2.wjheight, db2.dropbhoprecord, db2.dropbhoppre, db2.dropbhopmax, db2.dropbhopstrafes, db2.dropbhopsync, db2.dropbhopheight, db2.ljblockdist, db2.ljblockrecord, db2.ljblockpre, db2.ljblockmax, db2.ljblockstrafes, db2.ljblocksync, db2.ljblockheight, db2.ladderjumprecord, db2.ladderjumppre, db2.ladderjumpmax, db2.ladderjumpstrafes, db2.ladderjumpsync, db2.ladderjumpheight, db2.cjrecord, db2.cjpre, db2.cjmax, db2.cjstrafes, db2.cjsync, db2.cjheight FROM playerjumpstats3 as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE (db2.ladderjumprecord > -1.0 OR db2.wjrecord > -1.0 OR db2.dropbhoprecord > -1.0 OR db2.ljrecord > -1.0 OR db2.bhoprecord > -1.0 OR db2.multibhoprecord > -1.0 OR db2.cjrecord > -1.0) AND db2.steamid = ?;" # STEAMID
player_maptime_query = "SELECT name, mapname, runtime, teleports, runtimepro, teleports_pro FROM playertimes WHERE steamid = ? AND mapname LIKE ? AND (runtime  > -1.0 OR runtimepro  > -1.0);" # STEAMID, MAPNAME

player_mapranktotal_queries = {
    "tp": "SELECT * FROM ((SELECT COUNT(*) as rank FROM playertimes WHERE runtime <= (SELECT runtime FROM playertimes WHERE steamid = ? AND mapname LIKE ? AND runtime > -1.0) AND mapname LIKE ? AND runtime > -1.0) JOIN (SELECT COUNT(*) as tot FROM playertimes WHERE mapname LIKE ? AND runtime  > -1.0));", # STEAMID, MAPNAME, MAPNAME, MAPNAME
    "pro": "SELECT * FROM ((SELECT COUNT(*) as rank FROM playertimes WHERE runtimepro <= (SELECT runtimepro FROM playertimes WHERE steamid = ? AND mapname LIKE ? AND runtimepro > -1.0) AND mapname LIKE ? AND runtimepro > -1.0) JOIN (SELECT COUNT(*) as tot FROM playertimes WHERE mapname LIKE ? AND runtimepro  > -1.0));" # STEAMID, MAPNAME, MAPNAME, MAPNAME
}

maptop_queries = {
    "all": "SELECT * FROM (SELECT db1.name, db1.steamid, db2.mapname, db2.runtime as overall, db2.teleports AS tp FROM playertimes as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE db2.mapname LIKE ? AND db2.runtime > -1.0 AND db2.teleports >= 0 UNION SELECT db1.name, db1.steamid, db2.mapname, db2.runtimepro as overall, db2.teleports_pro AS tp FROM playertimes as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE db2.mapname LIKE ? AND db2.runtimepro > -1.0) GROUP BY steamid HAVING MIN(overall) ORDER BY overall ASC LIMIT ?;", # MAPNAME, MAPNAME, LIMIT
    "tp": "SELECT db1.name, db2.mapname, db2.runtime as overall, db2.teleports AS tp FROM playertimes as db2 INNER JOIN playerrank as db1 on db2.steamid = db1.steamid WHERE db2.mapname LIKE ? AND db2.runtime > -1.0 ORDER BY db2.runtime ASC LIMIT ?;", # MAPNAME, LIMIT
    "pro": "SELECT db1.name, db2.mapname, db2.runtimepro as overall, db2.teleports_pro as tp FROM playertimes as db2 INNER JOIN playerrank as db1 on db1.steamid = db2.steamid WHERE db2.mapname LIKE ? AND db2.runtimepro > -1.0 ORDER BY db2.runtimepro ASC LIMIT ?;" # MAPNAME, LIMIT
}

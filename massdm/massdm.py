import discord
from discord.ext import commands

from typing import List

class Massdm:
    """Send a direct message to all members of the specified Role."""

    def __init__(self, bot: commands.bot.Bot):
        self.bot = bot

    def _member_has_role(self, member: discord.Member, role: discord.Role):
        return role in member.roles

    def _get_users_with_role(self, server: discord.Server, role: discord.Role) -> List[discord.User]:
        roled = []
        for member in server.members:
            if self._member_has_role(member, role):
                roled.append(member)
        return roled

    @commands.command(no_pm=True, pass_context=True, name="mdm")
    async def _mdm(self, context: commands.context.Context, role: discord.Role, *, message: str):
        """Sends a DM to all Members with the given Role.
        Allows for the following customizations:
        {0} is the member being messaged.
        {1} is the role they are being message through.
        {2} is the person sending the message.
        """

        server = context.message.server
        sender = context.message.author

        await self.bot.delete_message(context.message)

        dm_these = self._get_users_with_role(server, role)

        for user in dm_these:
            await self.bot.send_message(user, message.format(user, role, sender))

def setup(bot: commands.bot.Bot):
    bot.add_cog(Massdm(bot))

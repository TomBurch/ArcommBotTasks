import logging
import os
import re
import sys
import ArcommBot

from discord import File
from discord.ext import commands

class Dev(commands.Cog):
    '''Contains commands usable by developers'''

    def __init__(self, bot):
        self.bot = bot
        self.utility = self.bot.get_cog("Utility")

    # ===Commands=== #

    @commands.command(name = "logs", hidden = True)
    @commands.is_owner()
    async def _logs(self, ctx, logName):
        for fileName in os.listdir("logs/"):
            if re.match(logName, fileName):
                logFile = File("logs/{}".format(fileName), filename = fileName)
                if logFile.filename != "bot.log":
                    await ctx.channel.send(fileName, file = logFile)

        # For some ungodly reason this only works if bot.log is sent at the end
        if logName == "bot":
            await ctx.channel.send("bot.log", file = File("logs/bot.log", filename = "bot.log"))

    @commands.command(name = "load", hidden = True)
    @commands.is_owner()
    async def _load(self, ctx, ext: str):
        self.bot.load_extension("cogs." + ext)
        logging.info("=========Loaded %s extension=========", ext)
        await self.utility.reply(ctx.message, "Loaded {} extension".format(ext))

    @commands.command(name = "resources", hidden = True)
    @commands.is_owner()
    async def _resources(self, ctx):
        outString = "```\n{}```".format("\n".join(os.listdir("resources/")))
        await self.utility.reply(ctx.message, outString)

    @commands.command(name = "getres", hidden = True)
    @commands.is_owner()
    async def _getres(self, ctx, resource):
        await self.utility.getResource(ctx, resource)

    @commands.command(name = "setres", hidden = True)
    @commands.is_owner()
    async def _setres(self, ctx):
        await self.utility.setResource(ctx)

    @commands.command(name = "reload", hidden = True)
    @commands.is_owner()
    async def _reload(self, ctx, ext: str):
        self.bot.reload_extension("cogs." + ext)
        logging.info("=========Reloaded %s extension=========", ext)
        await self.utility.reply(ctx.message, "Reloaded {} extension".format(ext))

    @commands.command(name = "restart", hidden = True)
    @commands.is_owner()
    async def _restart(self, ctx):
        print("============ RESTARTING ============")
        await self.utility.reply(ctx.message, "Restarting")
        ArcommBot.restart()

    @commands.command(name = "shutdown", hidden = True)
    @commands.is_owner()
    async def _shutdown(self):
        sys.exit()

    @commands.command(name = "update", hidden = True)
    @commands.is_owner()
    async def _update(self, ctx):
        attachments = ctx.message.attachments

        if attachments != []:
            newCog = attachments[0]
            cogs = os.listdir("cogs/")

            if newCog.filename in cogs:
                tempFilename = "cogs/temp_{}".format(newCog.filename)
                await newCog.save(tempFilename)

                os.replace(tempFilename, "cogs/{}".format(newCog.filename))
                await self.utility.reply(ctx.message, "{} successfully updated".format(newCog.filename))

                return newCog.filename.split(".")[0]

    @commands.command(name = "upload", hidden = True)
    @commands.is_owner()
    async def _upload(self, ctx):
        filename = await self._update(ctx)
        await self._reload(ctx, filename)

    @commands.command()
    @commands.is_owner()
    async def config(self, ctx):
        """Return or overwrite the config file

        Usage:
            .config
            -- Get current config
            .config <<with attached file called config.ini>>
            -- Overwrites config, a backup is saved"""

        if ctx.message.attachments == []:
            await self.utility.getResource(ctx, "config.ini")
        elif ctx.message.attachments[0].filename == "config.ini":
            await self.utility.setResource(ctx)

    @commands.command()
    @commands.is_owner()
    async def recruitpost(self, ctx):
        """Return or overwrite the recruitment post

        Usage:
            .recruitpost
            -- Get current recruit post
            .recruitpost <<with attached file called recruit_post.md>>
            -- Overwrites recruitpost, a backup is saved"""

        if ctx.message.attachments == []:
            await self.utility.getResource(ctx, "recruit_post.md")
        elif ctx.message.attachments[0].filename == "recruit_post.md":
            await self.utility.setResource(ctx)

    # ===Listeners=== #

    @commands.Cog.listener()
    async def on_ready(self):
        self.utility = self.bot.get_cog("Utility")


def setup(bot):
    bot.add_cog(Dev(bot))

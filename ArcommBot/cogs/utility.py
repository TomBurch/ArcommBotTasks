import configparser
from datetime import datetime, timedelta
import logging
import os
import re
import string

from discord import File
from discord.ext import commands


class Utility(commands.Cog):
    '''Contains useful functions that can be used in any cogs'''

    def __init__(self, bot):
        self.bot = bot
        if bot != "MockBot":
            self.config = configparser.ConfigParser()
            self.config.read('resources/config.ini')
            self.channels = {}
            self.roles = {}
            self.cog_setup()

    def cog_setup(self):
        for channel in self.config['channels']:
            self.channels[channel] = self.bot.get_channel(int(self.config['channels'][channel]))

        for role in self.config['roles']:
            self.roles[role] = int(self.config['roles'][role])

        self.REPO_URL = "http://108.61.34.58/main/"

    async def send_message(self, channel, message: str):
        """Send a message to the text channel"""

        await channel.trigger_typing()
        newMessage = await channel.send(message)

        return newMessage

    async def reply(self, message, response: str):
        """Reply to the given message"""

        await message.channel.trigger_typing()
        newMessage = await message.channel.send(response, reference = message.to_reference())

        return newMessage

    @staticmethod
    def roleListKey(elem):
        return elem.name.lower()

    def timeUntilOptime(self):
        today = datetime.now(tz = timezone('Europe/London'))
        opday = today
        opday = opday.replace(hour = 18, minute = 0, second = 0)
    
        if today > opday:
            opday = opday + timedelta(days = 1)

        return opday - today

    async def getResource(self, ctx, resource):
        if resource in os.listdir("resources/"):
            await ctx.channel.send(resource, file = File("resources/{}".format(resource), filename = resource))
        else:
            await self.reply(ctx.message, "{} not in resources".format(resource))

    async def setResource(self, ctx):
        attachments = ctx.message.attachments

        if attachments == []:
            await self.reply(ctx.message, "No attachment found")
        else:
            newResource = attachments[0]
            resourceName = newResource.filename
            if resourceName in os.listdir("resources/"):
                os.remove("resources/backups/{}.bak".format(resourceName))
                os.rename("resources/{}".format(resourceName), "resources/backups/{}.bak".format(resourceName))
                await newResource.save("resources/{}".format(resourceName))

                await self.reply(ctx.message, "{} {} has been updated".format(ctx.author.mention, resourceName))
            else:
                await self.reply(ctx.message, "{} {} not in resources".format(ctx.author.mention, resourceName))

    # ===Listeners=== #

    @commands.Cog.listener()
    async def on_command(self, ctx):
        cogName = ctx.cog.qualified_name if ctx.cog is not None else None
        self.logger.info("[%s] command [%s] called by [%s]", cogName, ctx.message.content, ctx.message.author)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        errorType = type(error)

        if errorType == commands.errors.CommandNotFound:
            if ctx.message.content[1].isdigit():
                return

            puncPattern = ".[{}]+".format(re.escape(string.punctuation))
            if re.match(puncPattern, ctx.message.content):
                return

            await self.reply(ctx.message, "Command **{}** not found, use .help for a list".format(ctx.message.content))

        if not ctx.command:
            return

        command = ctx.command.name
        outString = error

        if errorType == commands.errors.MissingRequiredArgument:
            if command == "logs":
                await ctx.channel.send("Bot log", file = File("logs/bot.log", filename = "bot.log"))
                return

        elif errorType == commands.errors.ExtensionNotLoaded:
            await self.reply(ctx.message, command)
            if command == "reload":
                outString = "Cog not previously loaded"

        await self.reply(ctx.message, outString)

    @commands.Cog.listener()
    async def on_ready(self):
        print("===Bot connected/reconnected===")
        logging.info("===Bot connected/reconnected===")
        self.cog_setup()


def setup(bot):
    bot.add_cog(Utility(bot))

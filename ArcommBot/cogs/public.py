import configparser
import json
import logging
import os

import aiohttp
from bs4 import BeautifulSoup
from discord.ext import commands

logger = logging.getLogger('bot')

config = configparser.ConfigParser()
config.read('resources/config.ini')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

TICKET_LINKS = {
    "acre": "https://github.com/IDI-Systems/acre2/issues/new/choose",
    "ace": "https://github.com/acemod/ACE3/issues/new/choose",
    "cup": "https://dev.cup-arma3.org/maniphest/task/edit/form/1/",
    "cba": "https://github.com/CBATeam/CBA_A3/issues/new/choose",
    "arma": "https://feedback.bistudio.com/maniphest/task/edit/form/3/",
    "arc_misc": "https://github.com/ARCOMM/arc_misc/issues/new",
    "archub": "https://github.com/ARCOMM/ARCHUB/issues/new",
    "tmf": "https://github.com/TMF3/TMF/issues/new"
}

TICKET_REPOS = {
    "arc_misc": "ARCOMM/arc_misc",
    "archub": "ARCOMM/ARCHUB",
    "arcommbot": "ARCOMM/ArcommBot"
}


class Public(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.utility = self.bot.get_cog("Utility")
        self.session = aiohttp.ClientSession()

    # ===Commands=== #

    @commands.command()
    async def ping(self, ctx):
        """Check bot response"""
        await self.utility.reply(ctx.message, "Pong!")

    @commands.command(aliases = ['wiki'])
    async def sqf(self, ctx, *args):
        """Find a bistudio wiki page

        Usage:
            .sqf BIS_fnc_helicopterDamage
            .sqf BIS fnc helicopterDamage
            --https://community.bistudio.com/wiki/BIS_fnc_helicopterDamage
        """

        sqfQuery = "_".join(args)
        wikiUrl = "https://community.bistudio.com/wiki/{}".format(sqfQuery)

        async with self.session.get(wikiUrl) as response:
            if response.status == 200:
                soup = BeautifulSoup(await response.text(), features = "lxml")

                warnings = soup.find_all("div", {"style": "background-color: #EA0; color: #FFF; display: flex;"
                                                + " align-items: center; margin: 0.5em 0"})
                for warning in warnings:
                    warning.decompose()

                desc = soup.find('dt', string = 'Description:')
                syntax = soup.find('dt', string = "Syntax:")
                ret = soup.find('dt', string = "Return Value:")

                elems = [desc, syntax, ret]
                outString = ""
                for elem in elems:
                    if elem is not None:
                        elemContent = elem.findNext('dd').text
                        outString += "# {}\n{}\n\n".format(elem.text, elemContent.lstrip().rstrip())

                if outString != "":
                    await self.utility.reply(ctx.message, "<{}>\n```md\n{}```".format(wikiUrl, outString))
                else:
                    await self.utility.reply(ctx.message, "<{}>".format(wikiUrl))
            else:
                await self.utility.reply(ctx.message, "{} Error - Couldn't get <{}>".format(response.status, wikiUrl))

    @commands.command()
    async def ticket(self, ctx, repo = None, title = None, body = None):
        """Create a new Github ticket
        The current available repos: arcommbot, arc_misc, archub
        Usage:
            .ticket repo "title" "body"
        """

        if repo not in TICKET_REPOS:
            await self.utility.reply(ctx.message, "Invalid repo ({})".format(", ".join(TICKET_REPOS)))
            return

        repo = repo.lower()

        if title is None or body is None:
            await self.utility.reply(ctx.message, 'Command should be in the format: ```\n.ticket {} "title" "body"```\n'.format(repo)
                                                + 'Please try to give a short but descriptive title,\n' 
                                                + 'and provide as much useful information in the body as possible')
            return

        author = ctx.message.author
        title = "{}: {}".format(author.name if (author.nick is None) else author.nick, title)

        data = {"title": title,
                "body": body}

        repoUrl = "https://api.github.com/repos/{}/issues".format(TICKET_REPOS[repo])

        async with self.session.post(repoUrl, auth = aiohttp.BasicAuth("ArcommBot", GITHUB_TOKEN), data = json.dumps(data)) as response:
            if response.status == 201:  # Status: 201 created
                response = await response.json()
                await self.utility.reply(ctx.message, "Ticket created at: {}".format(response["html_url"]))
            else:
                await self.utility.reply(ctx.message, response)

    @commands.command()
    async def ticketlink(self, ctx, site = None):
        """
        Get links for creating new GitHub tickets
        """
        if site is None:
            await self.utility.reply(ctx.message, "\n".join("{}: <{}>".format(link, TICKET_LINKS[link]) for link in TICKET_LINKS))
            return

        site = site.lower()
        if site in TICKET_LINKS:
            await self.utility.reply(ctx.message, "Create a ticket here: <{}>".format(TICKET_LINKS[site]))
        else:
            await self.utility.reply(ctx.message, "Invalid site ({})".format(", ".join(TICKET_LINKS)))

    # ===Listeners=== #

    @commands.Cog.listener()
    async def on_ready(self):
        self.utility = self.bot.get_cog("Utility")
        await self.utility.send_message(self.utility.channels['testing'], "ArcommBot is fully loaded")


def setup(bot):
    bot.add_cog(Public(bot))

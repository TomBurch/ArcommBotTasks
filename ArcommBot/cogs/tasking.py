import asyncio
import configparser
from datetime import datetime, timedelta
from httplib2 import ServerNotFoundError
import json
import logging
import os
import re
import sqlite3
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from discord import File, Game, Embed, Colour
from discord.ext import commands, tasks
from googleapiclient.discovery import build
from google.oauth2 import service_account
from pytz import timezone

from a3s_to_json import repository

config = configparser.ConfigParser()
config.read('resources/config.ini')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
ARCHUB_TOKEN = os.getenv('ARCHUB_TOKEN')
ARCHUB_HEADERS = {
    "Authorization": f"Bearer {ARCHUB_TOKEN}"
}

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'resources/restricted/arcommbot-1c476e6f4869.json'

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('calendar', 'v3', credentials = credentials, cache_discovery = False)


class CalendarDB():
    def __init__(self):
        self.conn = sqlite3.connect('resources/calendar.db')
        self.collection = service.events()

    def remake(self):
        c = self.conn.cursor()
        try:
            # c.execute("DROP TABLE calendar")
            c.execute("CREATE TABLE calendar (event_id INTEGER PRIMARY KEY, summary STRING NOT NULL, start STRING NOT NULL, end STRING NOT NULL, UNIQUE(start))")
        except Exception as e:
            print(e)

    def storeCalendar(self, timeFrom = "now"):
        if timeFrom == "now":
            lastDT = datetime.now(tz = timezone("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            lastDT = timeFrom

        request = self.collection.list(calendarId = "arcommdrive@gmail.com", timeMin = lastDT, orderBy = "startTime",
                                       singleEvents = True)
        # request = self.collection.list(calendarId = "bmpdcnk8pab1drvf4qgt4q1580@group.calendar.google.com", timeMin = lastDT, orderBy = "startTime", singleEvents = True)
        response = request.execute()
        c = self.conn.cursor()
        c.execute("DELETE FROM calendar")

        for item in response['items']:
            try:
                c.execute("INSERT OR IGNORE INTO calendar (summary, start, end) VALUES(?, ?, ?)", (item['summary'],
                          item['start']['dateTime'], item['end']['dateTime']))
            except Exception:
                None

        self.conn.commit()

    def pop(self):
        c = self.conn.cursor()

        c.execute("SELECT * FROM calendar ORDER BY event_id ASC LIMIT 1")
        event = c.fetchone()
        c.execute("DELETE FROM calendar WHERE event_id = (SELECT min(event_id) FROM calendar)")

        self.conn.commit()

        return event


class LastModified():
    resourcesLocked = False

    @classmethod
    def uses_lastModified(cls, func):
        async def wrapper(cog):
            if LastModified.resourcesLocked:
                return False, f"{str(func)} res locked"
            else:
                LastModified.resourcesLocked = True
                try:
                    result = await func(cog)
                    LastModified.resourcesLocked = False
                    return result
                except Exception as e:
                    LastModified.resourcesLocked = False
                    return False, f"Error running {str(func)}:\n{str(e)}"

        return wrapper


class Tasking(commands.Cog):
    '''Contains scheduled tasks'''

    def __init__(self, bot):
        self.bot = bot
        self.utility = self.bot.get_cog("Utility")
        self.calendar = CalendarDB()
        self.session = aiohttp.ClientSession()

    # ===Tasks=== #

    @tasks.loop(minutes = 1)
    async def calendarTask(self):
        '''Check google calendar for any new events, and post announcements for them'''

        lastDatetime = None
        with open('resources/calendar_datetime.json', 'r') as f:
            lastDatetime = json.load(f)

            if 'datetime' not in lastDatetime:
                lastDatetime['datetime'] = "now"
            else:  # Make sure the lastDatetime isn't in the past, otherwise will be announcing old events
                if lastDatetime['datetime'] != "now":
                    now = datetime.now(tz = timezone("UTC"))
                    lastDT = lastDatetime['datetime'].replace("Z", "+00:00")
                    lastDT = datetime.strptime(lastDT, "%Y-%m-%dT%H:%M:%S%z")

                    if lastDT < now:
                        lastDatetime['datetime'] = "now"

        try:
            self.calendar.storeCalendar(lastDatetime['datetime'])
        except ServerNotFoundError as e:
            self.utility.send_message(self.utility.channels["testing"], e)
            return

        newAnnouncement = True

        while newAnnouncement:
            newAnnouncement = False
            event = self.calendar.pop()

            if event:
                now = datetime.now(tz = timezone("UTC"))
                eventStartTime = event[2].replace("Z", "+00:00")
                eventStartTime = datetime.strptime(eventStartTime, "%Y-%m-%dT%H:%M:%S%z")

                timeUntil = eventStartTime - now
                if timedelta(days = 0, hours = 0, minutes = 10) <= timeUntil <= timedelta(days = 0, hours = 1, minutes = 0):
                    newAnnouncement = True
                    lastDatetime['datetime'] = event[3]
                    asyncio.Task(self.announce(timeUntil, event[1], event[2], event[3]))
            else:
                break

        with open('resources/calendar_datetime.json', 'w') as f:
            json.dump(lastDatetime, f)

    @tasks.loop(hours = 1)
    async def modcheckTask(self):
        githubChanged, githubPost = await self.handleGithub()
        steamChanged, steamPost = await self.handleSteam()

        if githubPost.startswith("Error"):
            await self.utility.send_message(self.utility.channels['testing'], githubPost)

        if steamPost.startswith("Error"):
            await self.utility.send_message(self.utility.channels['testing'], steamPost)

        try:
            if not (githubChanged or steamChanged):
                return

            outString = "<@&{}>\n{}{}".format(self.utility.roles['admin'], githubPost, steamPost)
            if len(outString) <= 1950:
                await self.utility.send_message(self.utility.channels['staff'], outString)
            else:
                logging.info("Sending modupdate as file")
                with open("resources/modupdate.txt", "w") as file:
                    file.write(outString)
                await self.utility.channels['staff'].send(f"<@&{self.utility.roles['admin']}> Mod update", file = File("resources/modupdate.txt", filename = "modupdate.txt"))
        except Exception as e:
            print(githubPost)
            print(steamPost)
            await self.utility.send_message(self.utility.channels['testing'], f"Modcheck error: {e}")

    @tasks.loop(minutes = 10)
    async def a3syncTask(self):
        a3syncChanged, a3syncPost = await self.handleA3Sync()
        if a3syncPost.startswith("Error"):
            await self.utility.send_message(self.utility.channels['testing'], a3syncPost)

        if a3syncChanged:
            try:
                await self.utility.send_message(self.utility.channels["announcements"], a3syncPost)
            except Exception as e:
                print(a3syncPost)
                await self.utility.send_message(self.utility.channels['testing'], f"A3sync message error: {e}")

    @a3syncTask.before_loop
    async def before_a3syncTask(self):
        """Add a delay before checking a3sync to avoid resource lock"""
        await asyncio.sleep(5)

    @tasks.loop(hours = 24)
    async def recruitTask(self):
        targetDays = [0, 2, 4]  # Monday, Wednesday, Friday
        now = datetime.utcnow()
        # now = datetime(2020, 4, 22) #A Wednesday
        if now.weekday() in targetDays:
            await self.recruitmentPost(self.utility.channels['staff'], pingAdmins = True)

    @recruitTask.before_loop
    async def before_recruitTask(self):
        """Sync up recruitTask to targetHour:targetMinute:00"""
        await self.bot.wait_until_ready()

        targetHour = 17
        targetMinute = 0

        now = datetime.utcnow()
        # now = datetime(now.year, now.month, now.day, 16, 59, 55)
        future = datetime(now.year, now.month, now.day, targetHour, targetMinute, 0, 0)

        if now.hour >= targetHour and now.minute > targetMinute:
            future += timedelta(days = 1)

        logging.debug("%d seconds until recruitTask called", (future - now).seconds)

        await asyncio.sleep((future - now).seconds)

    @tasks.loop(minutes = 1)
    async def presenceTask(self):
        timeLeft = self.utility.timeUntilOptime()
        minutes = (timeLeft.seconds // 60) % 60
        minuteZero = "0" if minutes < 10 else ""
        presenceString = "{}:{}{}:00 until optime".format(timeLeft.seconds // 3600, minuteZero, minutes)

        await self.bot.change_presence(activity = Game(name = presenceString))

    @presenceTask.before_loop
    async def before_presenceTask(self):
        """Sync up presenceTask to on the minute"""
        await self.bot.wait_until_ready()

        now = datetime.utcnow()
        # now = datetime(now.year, now.month, now.day, 16, 59, 55)
        future = datetime(now.year, now.month, now.day, now.hour, now.minute + 1)
        logging.debug("%d seconds until presenceTask called", (future - now).seconds)

        await asyncio.sleep((future - now).seconds)

    # ===Utility=== #

    async def getOperationMissions(self):
        async with self.session.get("https://arcomm.co.uk/api/v1/operations/next", headers = ARCHUB_HEADERS) as response:
            if response.status == 200:
                json = await response.json()
                return json
            return []
        
    def missionTypeFromMode(self, mode):
        if mode == 'coop':
            return 'Co-op'
        elif mode == 'adversarial':
            return 'TvT'
        elif mode == 'arcade':
            return 'ARCade'
        return None

    async def announce(self, timeUntil, summary, startTime, endTime):
        startTime = int(datetime.strptime(startTime, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone("UTC")).timestamp())
        endTime = int(datetime.strptime(endTime, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone("UTC")).timestamp())

        ping = "@here"
        channel = self.utility.channels['op_news']
        eventType = None

        for event in config['calendar']:
            if re.search(event, summary.lower()) is not None:
                eventType = event
                eventArray = config['calendar'][event][1:-1].split(", ")
                if eventArray[0] == "ignored":
                    return

                ping = "<@&{}>".format(self.utility.roles[eventArray[0]])
                channel = self.utility.channels[eventArray[1]]

        embed2 = Embed(
            title = summary,
            description = f"Starting <t:{startTime}:R>",
            colour = Colour.dark_red(),
        )

        embed1 = embed2.copy()
        embed1.add_field(name = "Start", value = f"<t:{startTime}:t>", inline = True)
        embed1.add_field(name = "End", value = f"<t:{endTime}:t>", inline = True)

        if eventType == "main":
            for mission in await self.getOperationMissions():
                missionMaker = mission['maker']
                missionType = self.missionTypeFromMode(mission['mode'])
                link = "https://arcomm.co.uk/hub/missions/{}".format(mission['id'])
                
                embed1.add_field(name = mission["display_name"], value = f"[{missionType} by {missionMaker}]({link})", inline = False)

        await self.utility.send_message(channel, ping, embed1)
        await asyncio.sleep((timeUntil - timedelta(minutes = 5)).seconds)
        await self.utility.send_message(channel, ping, embed2)

    async def recruitmentPost(self, channel, pingAdmins = False):
        if pingAdmins:
            introString = "<@&{}> Post recruitment on <https://www.reddit.com/r/FindAUnit>".format(self.utility.roles['admin'])
        else:
            introString = "Post recruitment on <https://www.reddit.com/r/FindAUnit>"

        await channel.send(introString, file = File("resources/recruit_post.md", filename = "recruit_post.md"))

    @LastModified.uses_lastModified
    async def handleA3Sync(self):

        url = "{}.a3s/".format(self.utility.REPO_URL)
        scheme = urlparse(url).scheme.capitalize

        repo = repository.parse(url, scheme, parseAutoconf=False, parseServerinfo=True, parseEvents=False,
                                parseChangelog=True, parseSync=False)

        lastModified = {}
        with open('resources/last_modified.json', 'r') as f:
            lastModified = json.load(f)

        updatePost = ""
        newRevision = repo["serverinfo"]["SERVER_INFO"]["revision"]
        if not (lastModified['revision'] < newRevision):
            self.resourcesLocked = False
            return False, updatePost

        newRepoSize = round((float(repo["serverinfo"]["SERVER_INFO"]["totalFilesSize"]) / 1000000000), 2)
        repoSizeChange = round(newRepoSize - float(lastModified['a3sync_size']), 2)
        repoChangeString = str(repoSizeChange) if (repoSizeChange < 0) else "+{}".format(repoSizeChange)

        newChangelog = None
        for changelog in repo["changelog"]:
            revision = repo["changelog"][changelog]["revision"]
            if revision == newRevision:
                newChangelog = repo["changelog"][changelog]

        updatePost = "```md\n# The ArmA3Sync repo has changed #\n\n[{} GB]({} GB)\n\n< Updated >\n{}\n\n< Added >\n{}\n\n< Removed >\n{}```".format(
            str(newRepoSize),
            repoChangeString,
            "\n".join(newChangelog["updatedAddons"]),
            "\n".join(newChangelog["newAddons"]),
            "\n".join(newChangelog["deletedAddons"])
        )

        lastModified['a3sync_size'] = newRepoSize
        lastModified['revision'] = newRevision

        with open('resources/last_modified.json', 'w') as f:
            json.dump(lastModified, f)
        
        return True, updatePost

    @LastModified.uses_lastModified
    async def handleGithub(self):
        repoUrl = 'https://api.github.com/repos'
        lastModified = {}

        with open('resources/last_modified.json', 'r') as f:
            lastModified = json.load(f)

        updatePost = ""
        repoChanged = False

        for mod in config['github']:
            url = "{}/{}/releases/latest".format(repoUrl, config['github'][mod])
            if mod in lastModified['github']:
                headers = {'Authorization': GITHUB_TOKEN,
                           'If-Modified-Since': lastModified['github'][mod]}
            else:
                headers = {'Authorization': GITHUB_TOKEN}

            async with self.session.get(url, headers = headers) as response:
                if response.status == 200:  # Repo has been updated
                    logging.info("Response 200 Success: %s", mod)
                    repoChanged = True

                    lastModified['github'][mod] = response.headers['Last-Modified']
                    response = await response.json()

                    changelogUrl = "https://github.com/{}/releases/tag/{}".format(config['github'][mod], response['tag_name'])
                    updatePost += "**{}** has released a new version ({})\n<{}>\n".format(mod, response['tag_name'],
                                                                                          changelogUrl)
                else:
                    if response.status != 304:  # 304 = repo not updated
                        logging.warning("%s GET error: %s %s - %s", mod, response.status, response.reason,
                                       await response.text())

        with open('resources/last_modified.json', 'w') as f:
            json.dump(lastModified, f)

        return repoChanged, updatePost

    async def handleSteam(self):
        with open('resources/mods.json', 'r') as f:
            lastModified = json.load(f)

        mods = set(await self.getSteamMods(config['collections']['main']))
        data = {'itemcount': len(mods)}
        for i, mod in enumerate(mods):
            data[f"publishedfileids[{i}]"] = mod

        updatePost = ""
        repoChanged = False
        async with self.session.post("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/", data = data) as response:
            if response.status == 200:
                response = await response.json()
                filedetails = response['response']['publishedfiledetails']

                for mod in filedetails:
                    modId = mod['publishedfileid']
                    timeUpdated = str(mod['time_updated'])

                    if modId in lastModified['steam']:
                        if timeUpdated != lastModified['steam'][modId]:
                            repoChanged = True
                            lastModified['steam'][modId] = timeUpdated

                            updatePost += "**{}** has released a new version ({})\n{}\n".format(mod['title'], "",
                                            f"<https://steamcommunity.com/sharedfiles/filedetails/changelog/{modId}>")

                            try:
                                changelog = await self.getSteamChangelog(modId)
                            except:
                                changelog = "Error retrieving changelog"

                            updatePost += "```\n{}```\n".format(changelog)
                    else:
                        lastModified['steam'][modId] = timeUpdated
            else:
                await self.utility.send_message(self.utility.channels["testing"], "steam POST error: %s %s - %s" % (response.status, response.reason, await response.text()))

        with open('resources/mods.json', 'w') as f:
            json.dump(lastModified, f)

        return repoChanged, updatePost

    async def getSteamMods(self, collection):
        data = {'collectioncount': 1, 'publishedfileids[0]': collection}
        mods = []

        async with self.session.post('https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/', data = data) as response:
            j = await response.json()

            for collection in j['response']['collectiondetails']:
                for child in collection['children']:
                    if child['filetype'] == 0:
                        mods.append(child['publishedfileid'])
                    elif child['filetype'] == 2:
                        mods += await self.getSteamMods(child['publishedfileid'])

        return mods

    async def getSteamChangelog(self, modId):
        url = f"https://steamcommunity.com/sharedfiles/filedetails/changelog/{modId}"

        async with self.session.get(url) as response:
            if response.status == 200:
                soup = BeautifulSoup(await response.text(), features = "lxml")
                headline = soup.find("div", {"class": "changelog headline"})
                return headline.findNext("p").get_text(separator = "\n")
            else:
                await self.utility.send_message(self.utility.channels['testing'], "steam GET error: {} {} - {}".format(response.status, response.reason, await response.text()))

        return ""

    # ===Listeners=== #

    def cog_unload(self):
        logging.warning("Cancelling tasks...")
        self.calendarTask.cancel()
        self.modcheckTask.cancel()
        # self.recruitTask.cancel()
        self.presenceTask.cancel()
        self.a3syncTask.cancel()
        logging.warning("Tasks cancelled at %s", datetime.now())

    @commands.Cog.listener()
    async def on_ready(self):
        self.utility = self.bot.get_cog("Utility")

        self.calendar.remake()
        self.calendar.storeCalendar()

        self.calendarTask.start()
        self.modcheckTask.start()
        # self.recruitTask.start()
        self.presenceTask.start()
        self.a3syncTask.start()

        await self.utility.send_message(self.utility.channels['testing'], "ArcommBot is fully loaded")


def setup(bot):
    bot.add_cog(Tasking(bot))

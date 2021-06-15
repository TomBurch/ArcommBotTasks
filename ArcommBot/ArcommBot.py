import configparser
from dotenv import load_dotenv
import logging
import os
import subprocess
import sys

import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

config = configparser.ConfigParser()
config.read('resources/config.ini')

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix = '.', case_insensitive = True, intents = intents)


@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)
    except Exception:
        exc = sys.exc_info()
        await message.channel.send("Type [{}], Value [{}]\nTraceback[{}]".format(exc[0], exc[1], exc[2]))

def loadExtensions():
    startupExtensions = config['cogs']

    for extension in startupExtensions:
        try:
            bot.load_extension("cogs." + extension)
            logging.info("=========Loaded {} extension=========".format(extension))
        except Exception as e:
            print(e)
            logging.critical("Failed to load {} extension\n".format(extension))
            logging.critical(e)


def restart():
    subprocess.call(["python", os.path.join(sys.path[0], __file__)] + sys.argv[1:])

if __name__ == "__main__":
    loadExtensions()

    while True:
        bot.loop.run_until_complete(bot.start(TOKEN))

        print("Reconnecting")
        bot.client = commands.Bot(command_prefix = '.', case_insensitive = True, intents = intents, loop = bot.loop)

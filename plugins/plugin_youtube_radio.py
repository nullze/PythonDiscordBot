import os
import sys
import json
import discord
from youtube_dl import YoutubeDL
import itertools
import traceback
import asyncio
from async_timeout import timeout
from functools import partial
from dotenv import load_dotenv
from discord.ext.tasks import loop
from requests import get

sys.path.append(os.path.abspath('utils'))

from utils.config_utils import ConfigUtils

ytdlopts = {
	'format': 'bestaudio/best',
	'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
	'restrictfilenames': True,
	'noplaylist': True,
	'nocheckcertificate': True,
	'ignoreerrors': False,
	'logtostderr': False,
	'quiet': True,
	'no_warnings': True,
	'default_search': 'auto',
	'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpegopts = {
	'before_options': '-nostdin',
	'options': '-vn'
}

ytdl = YoutubeDL(ytdlopts)

class YTDLSource(discord.PCMVolumeTransformer):
	
    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')

    def __getitem__(self, item: str):
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, message, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        await message.channel.send(f'```ini\n[Added {data["title"]} to the Queue.]\n```')

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': message.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source), data=data, requester=message.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url']), data=data, requester=requester)

class YoutubeRadio():
	# Required for all plugins
	conf_path = os.path.join(os.path.dirname(__file__), 'configs')

	guild_confs = []

	configutils = None

	name = '!radio'

	desc = 'Play music from a single YouTube video or playlist in your voice channel'

	synt = '!radio <yt video URL> | pause | resume | stop | [config|get <config>|set <config> <value>|add/remove <config> <value>]'

	is_service = False

	client = None

	looping = False

	full_conf_file = None

	default_config = {}
	default_config['protected'] = {}
	default_config['protected']['name'] = __file__
	default_config['protected']['guild'] = None
	default_config['standard_groups'] = {}
	default_config['standard_groups']['value'] = []
	default_config['standard_groups']['description'] = "Authorized groups to use this command"
	default_config['admin_groups'] = {}
	default_config['admin_groups']['value'] = []
	default_config['admin_groups']['description'] = "Authorized groups to use admin functions of this command"
	default_config['blacklisted'] = {}
	default_config['blacklisted']['value'] = []
	default_config['blacklisted']['description'] = "Groups explicitly denied access to this command"
	default_config['post_channel'] = {}
	default_config['post_channel']['value'] = ""
	default_config['post_channel']['description'] = "Desitination channel to post messages from this plugin"

	server_players = []

	# Server configurable

	group = '@everyone'

	admin = False
	
	cheer = -1
	
	cat = 'admin'
	
	def __init__(self, client = None):
		self.client = client
		self.configutils = ConfigUtils()

		# Load configuration if it exists
		self.guild_confs = self.configutils.loadConfig(self.conf_path, self.default_config, __file__)


		print('\n\nConfigs Loaded:')
		for config in self.guild_confs:
			print('\t' + config['protected']['name'] + ': ' + config['protected']['guild'])

	def getArgs(self, message):
		cmd = str(message.content)
		seg = str(message.content).split(' ')

		if len(seg) > 1:
			return seg
		else:
			return None

	def generatePluginConfig(self, file_name):
		for new_conf in self.configutils.generateConfig(self.conf_path, self.default_config, file_name, __file__):
			self.guild_confs.append(new_conf)

	def checkCat(self, check_cat):
		if self.cat == check_cat:
			return True
		else:
			return False
	
	def checkBits(self, bits):
		return False
	
	async def runCheer(self, user, amount):
		return True

	async def stopPlayer(self, message):
		the_guild = str(message.guild.name) + str(message.guild.id)

		found = False
		for player in self.server_players:
			if player[0] == the_guild:
				found = True
				player[1].stop()
				self.server_players.remove(player)

		if not found:
			await message.channel.send(message.author.mention + ' There are no players running on this server')
			return False

		print('Guilds running a player:')
		for player in self.server_players:
			print('\t' + str(player[0]))

	async def startPlayer(self, message, target_vc, url):
		the_guild = str(message.guild.name) + str(message.guild.id)
		voice_channel = await target_vc.connect()

		for player in self.server_players:
			if player[0] == the_guild:
				await message.channel.send(message.author.mention + ' There is already a player running. Stop it before running another.')
				return False

		player = await YTDLSource.create_source(url, loop=self.bot.loop, download=False)
		self.server_players.append([the_guild, player])

		print('Guilds running a player:')
		for player in self.server_players:
			print('\t' + str(player[0]))

	async def run(self, message, obj_list):
		# Permissions check
		if not self.configutils.hasPerms(message, False, self.guild_confs):
			await message.channel.send(message.author.mention + ' Permission denied')
			return False

		# Parse args
		arg = self.getArgs(message)

		# Config set/get check
		if arg != None:
			if await self.configutils.runConfig(message, arg, self.guild_confs, self.conf_path):
				return True

		# Do Specific Plugin Stuff

		# User wants to stop the current player
		if str(arg[1]) == 'stop':
			self.stopPlayer(message)
			return True

		# User must want to start a new player
		else:
			# Make sure user is actually in a voice channel
			voice_state = message.author.voice
			if voice_state == None:
				await message.channel.send(message.author.mention + ' You need to be in a voice channel to use this plugin')
				return False
			else:
				target_vc = message.author.voice.channel
				await self.startPlayer(message, target_vc, str(arg[1]))
				return True

		return True

	async def stop(self, message):
		self.looping = False
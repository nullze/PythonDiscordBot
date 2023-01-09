import os
import sys
import json
import discord
import pytz
from datetime import datetime
from logger import logger
from dotenv import load_dotenv
from discord.ext.tasks import loop
from requests import get

sys.path.append(os.path.abspath('utils'))

from utils.config_utils import ConfigUtils

class CleanupRaid():
	# Required for all plugins
	conf_path = os.path.join(os.path.dirname(__file__), 'configs')

	guild_confs = []

	configutils = None

	name = '!cleanupraid'

	desc = 'Remove all users who joined at a specific datetime except for those with <@exempt role>'

	synt = '!cleanupraid <YYYYMMDD;HH:mm> <@exempt role> / [config|get <config>|set <config> <value>|add/remove <config> <value>]'

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


		logger.debug('\n\nConfigs Loaded:')
		for config in self.guild_confs:
			logger.debug('\t' + config['protected']['name'] + ': ' + config['protected']['guild'])

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
	
	async def convert_to_datetime(self, datetime_str):
		# Parse the input string
		date, time = datetime_str.split(';')
		year, month, day = date[:4], date[4:6], date[6:]
		hour, minute = time.split(':')
		
		# Convert the year, month, day, hour, and minute to integers
		year, month, day, hour, minute = map(int, [year, month, day, hour, minute])
		
		# Create and return the datetime object
		return datetime(year, month, day, hour, minute)
	
	async def get_users_by_join_time(self, message, str_time, role):
		# Convert the join time string to a datetime object in the UTC timezone
		join_time = pytz.utc.localize(await self.convert_to_datetime(str_time))

		# Get the guild associated with the message
		guild = message.guild

		# Get a list of members in the guild
		members = guild.members

		# Initialize an empty list to store the filtered members
		filtered_members = []

		# Iterate through the members in the guild
		for member in members:
			# Convert the member's join time to the UTC timezone
			member_join_time = member.joined_at.astimezone(pytz.utc)
			# Check if the member joined at the specified time and does not have the specified role
			if member_join_time.strftime("%Y%m%d;%H:%M") == join_time.strftime("%Y%m%d;%H:%M"): #and role not in member.roles:
				# Add the member to the filtered list
				filtered_members.append(member)
				
			# Print the name and join time of the member
			print(str(member.name) + ': ' + str(member_join_time.strftime("%Y%m%d;%H:%M")))
			
		return filtered_members
	
	async def get_role_from_mention(self, message, role_mention):
		# Get the guild associated with the message
		guild = message.guild

		# Get the role ID from the role mention string
		role_id = role_mention.strip("<@&>")

		# Get the role object from the guild
		role = discord.utils.get(guild.roles, id=role_id)

		return role

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
		
		# Only take the first mention in the message
		exempt_role = message.role_mentions[0]
		datetime_str = arg[1]

		cleanup_list = await self.get_users_by_join_time(message, datetime_str, exempt_role)

		logger.debug('Cleanup List:')
		for item in cleanup_list:
			logger.debug('\t' + str(item.name))
		logger.debug('Done with cleanup list')


		return True

	async def stop(self, message):
		self.looping = False
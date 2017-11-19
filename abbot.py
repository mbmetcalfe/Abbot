#!/usr/local/bin/python3
# discord.py: https://github.com/Rapptz/discord.py/tree/master
import discord
from discord.ext import commands
import asyncio
import logging
import os
import random
import inflect
import time 
import re

# Setup logging
logger = logging.getLogger('abbot')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('abbot.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s:%(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
logger.addHandler(fh)

TOKEN = 'Mzc2MTY2NDE3OTAyMzM4MDU5.DN6b5g.3lts28dpeGGHlteJ5825Gl_lTNQ'

description = '''I am Abbot.  A bot written in Python and discord.py'''
bot = commands.Bot(command_prefix='?', description=description)

take_over_world = 'What are we going to do tonight?'
greet = 'Hello there'

@bot.event
async def on_ready():
    logger.debug('bot.event.on_ready called.')
    logger.info('Logged in as ' + bot.user.name + ' (' + bot.user.id + ')')
    await bot.change_presence(game=discord.Game(name='Taking over the world|?help'))
    await bot.send_message(discord.Object(id='279610788442800138'), 'OK.  OK.  OK.  %s has arrived.  Let the games begin!' % (bot.user.name))

@bot.event
async def on_resumed():
    logger.debug('bot.event.on_resumed called.')
    logger.info('Session resumed.')
    #await bot.send_message(discord.Object(id='279610788442800138'), "I'm baaaaaaaaaaack!")

@bot.event
async def on_message(message):
    #logger.debug('bot.event.on_message called.')

    if message.author == bot.user:
        logger.debug('Author is bot -- ignored.')
        return

    if message.content.startswith(greet):
        logger.debug('Message: ' + message.content + ' from: ' + message.author.nick)
        await bot.send_message(message.channel, 'Oh hi there.  How are you, {0}?'.format(message.author.mention))
        msg = await bot.wait_for_message(author=message.author.mention, content='hello')
        await bot.send_message(message.channel, 'Hello.')

    if message.content.startswith(take_over_world):
        logger.debug('Message: ' + message.content + ' from: ' + message.author.nick)
        await bot.send_message(message.channel, 'The same thing we do every night, {0}. Try to take over the world.'.format(message.author.mention))
    
    # Detect and react to some bot praise.
    pattern = re.compile('Good (boy|bot|stuff) {0}'.format((bot.user.name)), re.IGNORECASE)
    match = pattern.match(message.content)
    if match:
        #emoji = discord.Emoji()
        #await bot.add_reaction(message, "blush")
        await bot.send_message(message.channel, "Why, thank you. :blush:")

    await bot.process_commands(message)

@bot.command(pass_context = True)
async def idea(ctx,*, idea: str):
    """Adds an idea to the idea box."""
    logger.debug('bot.command.idea called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    logger.debug('idea: ' + idea)
    logger.info('IDEA: {0} from {1}.'.format(idea, ctx.message.author.name))

@bot.command(pass_context=True)
async def whoami(ctx):
    """Show some stats about thyself."""
    logger.debug('bot.command.whoami called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    author = ctx.message.author
    role_names = [role.name for role in author.roles]    
    await bot.say("%s:\n\tRoles: %s\n\tTop Role: %s\n\tStatus: %s\n\tGame: %s\n\tJoined: %s" % (author.mention, role_names, author.top_role, author.status, author.game, author.joined_at))

@bot.command(pass_context=True)
async def clear(ctx, number: int):
    """Clears a number of messages from the channel."""
    logger.debug('bot.command.clear called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    # TODO: Clear just the bot's messages
    msgs = [] #Empty list to put all the messages in the log
    number = int(number) #Converting the amount of messages to delete to an integer
    async for x in bot.logs_from(ctx.message.channel, limit = number):
        logger.debug("Message from: " + x.author.mention)
        if x.author == bot.user:
            logger.debug("Found one of my messages.")
            msgs.append(x)
        
        logger.debug("Deleting " + str(len(msgs)) + " messages...")
    await bot.delete_messages(msgs)
    await bot.say("As per %s's wishes, I have removed %d messages from this channel" % (ctx.message.author.mention, number))


@bot.command(description='For when you wanna settle the score some other way', pass_context=True)
async def choose(ctx, *choices : str):
    """Chooses between multiple choices."""
    logger.debug('bot.command.choose called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    await bot.say(random.choice(choices))

@bot.command(pass_context=True)
async def roll(ctx, dice : str):
    """Rolls a dice in NdN format.\ne.g. 1d6 rolls one 6-sided die;\n2d20 rolls 2 20-sided dice"""
    logger.debug('bot.command.roll called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    await bot.delete_message(ctx.message)
    try:
        rolls, limit = map(int, dice.split('d'))
    except Exception:
        # On exception (invalid format), default to one roll of a 6-sided dice
        rolls = 1
        limit = 6

    result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
    p = inflect.engine()
    wordRolls = p.number_to_words(rolls)

    await bot.send_typing(ctx.message.channel)
    await asyncio.sleep(rolls * 3) # simulate rolling the dice (~3 seconds/dice)

    em = discord.Embed(title='Dice Roll', description=ctx.message.author.mention + ' has rolled ' + wordRolls + ' ' + str(limit) + '-sided dice.\n\nThe result is: ' + result, colour=0x2e456b)
    #em.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
    
    em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(ctx.message.author), icon_url=ctx.message.author.avatar_url)
    await bot.send_message(ctx.message.channel, embed=em)

@bot.command(pass_context=True)
async def pick(ctx):
    """Pick a random person from the server."""
    pickMembers = []
    logger.debug('bot.command.pick called by "' + ctx.message.author.name + '" on channel "' + ctx.message.channel.name + '".')
    await bot.say("Gathering all the people.")
    await bot.send_typing(ctx.message.channel)
    await asyncio.sleep(5)
    for server in bot.servers:
        for member in server.members:
            if not member.bot:
                pickMembers.append(member.mention)

    await bot.say("Ok, have all the people, let's see who is the lucky winner.")
    await bot.say("Drumroll please!")
    await bot.send_typing(ctx.message.channel)
    await asyncio.sleep(3)
    
    if len(pickMembers) > 0:
        em = discord.Embed(title='Random User Pick', description='{0} has requested to pick a random user.\n\n{1} was chosen!'.format(ctx.message.author.mention, random.choice(pickMembers)), colour=0x2e456b)
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(ctx.message.author), icon_url=ctx.message.author.avatar_url)
        await bot.send_message(ctx.message.channel, embed=em)

#------------------------------------------------------------------------------
# Secret Santa-type stuff
#------------------------------------------------------------------------------

@bot.group(pass_context=True)
async def event(ctx):
    """The Secret Gifter Event 2017 Command."""
    if ctx.invoked_subcommand is None:
        await bot.say('Invalid opt command passed...')

@event.command()
async def opt_in():
    """Opt-in to the Gifter Event 2017.  You know you wanna!"""
    await bot.say('Opting you in.')

@event.command()
async def address(address: str):
    """Supply your address for the Gifter Event 2017.
    Please note that you have to enclose the full address in quotes."""
    await bot.say('Your address logged as: {0}.'.format(address))

@event.command()
async def size(size: str):
    """Supply your shirt size for the Gifter Event 2017."""
    await bot.say('Your size logged as: {0}.'.format(size))

@event.command()
async def status():
    """Your status for the Gifter Event 2017."""
    await bot.say('Status not yet implemented.')

#os.system('clear')
bot.run(TOKEN)
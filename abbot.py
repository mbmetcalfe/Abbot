#!/usr/local/bin/python3.6
import discord
from discord.ext import commands
from discord.ext.commands.bot import _get_variable

from config import Config, ConfigDefaults
from permissions import Permissions, PermissionsDefaults
from utils import load_file, write_file, sane_round_int
import exceptions
import inspect
import asyncio
import traceback
import aiohttp
import logging
import os
import random
import inflect
import time
import datetime
import re
import sys
from functools import wraps
from textwrap import dedent
from constants import VERSION as BOTVERSION
from constants import DISCORD_MSG_CHAR_LIMIT, AUDIO_CACHE_PATH
import praw
import db

import event

class Response:
    def __init__(self, content, reply=False, embed=False, delete_after=0, reactions=None):
        self.content = content
        self.reply = reply
        self.embed = embed
        self.delete_after = delete_after
        self.reactions = reactions

class Abbot(discord.Client):
    def __init__(self, config_file=ConfigDefaults.options_file, perms_file=PermissionsDefaults.perms_file):
        self.config = Config(config_file)
        self.permissions = Permissions(perms_file, grant_all=[self.config.owner_id])

        self.blacklist = set(load_file(self.config.blacklist_file))

        self.exit_signal = None
        self.init_ok = False
        self.cached_client_id = None

        super().__init__()
        self.aiosession = aiohttp.ClientSession(loop=self.loop)
        self.http.user_agent += ' Abbot/%s' % BOTVERSION
        
        if self.config.auto_status > 0:
            logger.info("AutoStatus set.  Creating task.")
            self.loop.create_task(self._auto_presence_task())
        
        if self.config.database_name:
            self.database = db.AbbotDatabase(self.config.database_name)

    # TODO: Add some sort of `denied` argument for a message to send when someone else tries to use it
    def owner_only(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Only allow the owner to use these commands
            orig_msg = _get_variable('message')

            if not orig_msg or orig_msg.author.id == self.config.owner_id:
                return await func(self, *args, **kwargs)
            else:
                raise exceptions.PermissionsError("only the owner can use this command", expire_in=30)

        return wrapper

    def safe_print(self, content, *, end='\n', flush=True):
        sys.stdout.buffer.write((content + end).encode('utf-8', 'replace'))
        if flush: sys.stdout.flush()

    def get_reddit_post(self, subreddit):
        #TODO: Have him get a random one once/day.
        #TODO: Add the URL and author in the message.
        #TODO: decide on hot vs top vs new
        maxPosts = 100
        
        reddit = praw.Reddit(user_agent='Abbot',
            client_id=self.config.reddit_client_id,
            client_secret=self.config.reddit_client_secret)

        #posts = reddit.subreddit(subreddit).new(limit=maxPosts)
        posts = reddit.subreddit(subreddit).hot(limit=maxPosts)
        postNumber = random.randint(0, maxPosts)
        for i, post in enumerate(posts):
            if i == postNumber:
                return post

        return None

    async def send_typing(self, destination):
        try:
            return await super().send_typing(destination)
        except discord.Forbidden:
            if self.config.debug_mode:
                logger.debug("Could not send typing to %s, no permssion" % destination)

    @staticmethod
    def _fixg(x, dp=2):
        return ('{:.%sf}' % dp).format(x).rstrip('0').rstrip('.')

    def _get_owner(self, voice=False):
        if voice:
            for server in self.servers:
                for channel in server.channels:
                    for m in channel.voice_members:
                        if m.id == self.config.owner_id:
                            return m
        else:
            return discord.utils.find(lambda m: m.id == self.config.owner_id, self.get_all_members())

    async def _autojoin_channels(self, channels):
        joined_servers = []

        for channel in channels:
            if channel.server in joined_servers:
                logger.info("Already joined a channel in %s, skipping" % channel.server.name)
                continue

            if channel and channel.type == discord.ChannelType.voice:
                logger.info("Attempting to autojoin %s in %s" % (channel.name, channel.server.name))

                chperms = channel.permissions_for(channel.server.me)

                if not chperms.connect:
                    logger.info("Cannot join channel \"%s\", no permission." % channel.name)
                    continue

                elif not chperms.speak:
                    logger.info("Will not join channel \"%s\", no permission to speak." % channel.name)
                    continue

                try:
                    player = await self.get_player(channel, create=True)

                    if player.is_stopped:
                        player.play()

                    if self.config.auto_playlist:
                        await self.on_player_finished_playing(player)

                    joined_servers.append(channel.server)
                except Exception as ex:
                    if self.config.debug_mode:
                        traceback.print_exc()
                    logger.error("Failed to join %s: %s" % channel.name, ex)

            elif channel:
                logger.info("Not joining %s on %s, that's a text channel." % (channel.name, channel.server.name))

            else:
                logger.error("Invalid channel thing: " + channel)

    async def _wait_delete_msg(self, message, after):
        await asyncio.sleep(after)
        await self.safe_delete_message(message)

    def _cleanup(self):
        try:
            self.loop.run_until_complete(self.logout())
        except: # Can be ignored
            pass

        pending = asyncio.Task.all_tasks()
        gathered = asyncio.gather(*pending)

        try:
            gathered.cancel()
            self.loop.run_until_complete(gathered)
            gathered.exception()
        except: # Can be ignored
            pass

    async def safe_send_message(self, dest, content, *, tts=False, expire_in=0, also_delete=None, quiet=False, embed=False, reactions=None):
        msg = None
        try:
            if embed:
                msg = await self.send_message(dest, embed=content, tts=tts)
            else:
                msg = await self.send_message(dest, content, tts=tts)

            if msg and reactions:
                for reaction in reactions:
                    await self.safe_add_reaction(msg, reaction)

            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

            if also_delete and isinstance(also_delete, discord.Message):
                asyncio.ensure_future(self._wait_delete_msg(also_delete, expire_in))

        except discord.Forbidden:
            if not quiet:
                logger.warning("Cannot send message to %s, no permission." % dest.name)

        except discord.NotFound:
            if not quiet:
                logger.warning("Cannot send message to %s, invalid channel?" % dest.name)

        return msg

    async def safe_add_reaction(self, message, emoji):
        """Try to react to a message with a specific emoji."""
        reaction = None
        try:
            reaction = await self.add_reaction(message, emoji)

        except discord.Forbidden:
            logger.warning("Cannot react to message in %s, no permission" % message.channel)

        except discord.NotFound:
            logger.warning("Cannot react to message in %s, invalid channel?" % message.channel)
        
        except:
            logger.error("Could not react to message id {0} with {1}".format(message.id, emoji))

        return reaction

    async def safe_send_embed(self, dest, content, *, tts=False, expire_in=0, also_delete=None, quiet=False):
        msg = None
        try:
            msg = await self.send_message(dest, embed=content, tts=tts)

            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

            if also_delete and isinstance(also_delete, discord.Message):
                asyncio.ensure_future(self._wait_delete_msg(also_delete, expire_in))

        except discord.Forbidden:
            if not quiet:
                logger.warning("Cannot send message to %s, no permission" % dest.name)

        except discord.NotFound:
            if not quiet:
                logger.warning("Cannot send message to %s, invalid channel?" % dest.name)

        return msg

    async def safe_delete_message(self, message, *, quiet=False):
        try:
            return await self.delete_message(message)

        except discord.Forbidden:
            if not quiet:
                logger.warning("Cannot delete message \"%s\", no permission" % message.clean_content)

        except discord.NotFound:
            if not quiet:
                logger.warning("Cannot delete message \"%s\", message not found" % message.clean_content)

    # noinspection PyMethodOverriding
    def run(self):
        try:
            self.loop.run_until_complete(self.start(*self.config.auth))

        except discord.errors.LoginFailure:
            # Add if token, else
            raise exceptions.HelpfulError(
                "Bot cannot login, bad credentials.",
                "Fix your Email or Password or Token in the options file.  "
                "Remember that each field should be on their own line.")

        finally:
            try:
                self._cleanup()
            except Exception as e:
                logger.error("Error in cleanup: %s" % e)

            self.loop.close()
            if self.exit_signal:
                raise self.exit_signal

    async def logout(self):
        await self.disconnect_all_voice_clients()
        return await super().logout()

    async def on_error(self, event, *args, **kwargs):
        ex_type, ex, stack = sys.exc_info()

        if ex_type == exceptions.HelpfulError:
            logger.error("Exception in %s" % event)
            logger.error(ex.message)

            await asyncio.sleep(2)  # don't ask
            await self.logout()

        elif issubclass(ex_type, exceptions.Signal):
            self.exit_signal = ex_type
            await self.logout()

        else:
            traceback.print_exc()

    async def on_resumed(self):
        logger.debug("Resumed...")
#        for vc in self.the_voice_clients.values():
#            vc.main_ws = self.ws

    async def on_ready(self):
        logger.info('Connected!  Abbot v%s.' % BOTVERSION)

        if self.config.owner_id == self.user.id:
            raise exceptions.HelpfulError(
                "Your OwnerID is incorrect or you've used the wrong credentials.",

                "The bot needs its own account to function.  "
                "The OwnerID is the id of the owner, not the bot.  "
                "Figure out which one is which and use the correct information.")

        self.init_ok = True

        logger.info("Bot:   %s/%s#%s" % (self.user.id, self.user.name, self.user.discriminator))

        owner = self._get_owner(voice=True) or self._get_owner()
        if owner and self.servers:
            logger.info("Owner: %s/%s#%s\n" % (owner.id, owner.name, owner.discriminator))

            logger.info('Server List:')
            [logger.info(' - ' + s.name) for s in self.servers]

        elif self.servers:
            logger.info("Owner could not be found on any server (id: %s)\n" % self.config.owner_id)

            logger.info('Server List:')
            [logger.info(' - ' + s.name) for s in self.servers]

        else:
            logger.info("Owner unknown, bot is not on any servers.")
            if self.user.bot:
                logger.info("\nTo make the bot join a server, paste this link in your browser.")
                logger.info("Note: You should be logged into your main account and have \n"
                      "manage server permissions on the server you want the bot to join.\n")
                logger.info("    " + await self.generate_invite_link())


        if self.config.bound_channels:
            chlist = set(self.get_channel(i) for i in self.config.bound_channels if i)
            chlist.discard(None)
            invalids = set()

            invalids.update(c for c in chlist if c.type == discord.ChannelType.voice)
            chlist.difference_update(invalids)
            self.config.bound_channels.difference_update(invalids)

            logger.info("Bound to text channels:")
            [logger.info(' - %s/%s' % (ch.server.name.strip(), ch.name.strip())) for ch in chlist if ch]

            if invalids and self.config.debug_mode:
                logger.info("\nNot binding to voice channels:")
                [logger.info(' - %s/%s' % (ch.server.name.strip(), ch.name.strip())) for ch in invalids if ch]


        else:
            logger.info("Not bound to any text channels")

        logger.info("Options:")

        logger.info("  Command prefix: " + self.config.command_prefix)
        logger.info("  Delete Messages: " + ['Disabled', 'Enabled'][self.config.delete_messages])
        if self.config.delete_messages:
            logger.info("    Delete Invoking: " + ['Disabled', 'Enabled'][self.config.delete_invoking])
        logger.info("  Debug Mode: " + ['Disabled', 'Enabled'][self.config.debug_mode])

        # maybe option to leave the ownerid blank and generate a random command for the owner to use
        # wait_for_message is pretty neato

        if self.config.autojoin_channels:
            await self._autojoin_channels(autojoin_channels)

        if self.config.auto_statuses:
            await self.update_presence("{0} | {1}help".format(
                random.sample(self.config.auto_statuses, 1)[0],
                self.config.command_prefix))
        # t-t-th-th-that's all folks!

# -----------
# Commands
# -----------
    async def cmd_help(self, channel, author, command=None):
        """
        Prints a help message.
        If a command is specified, it prints a help message for that command.
        Otherwise, it lists the available commands.

        Usage:
            {command_prefix}help [command]
        """

        if command:
            cmd = getattr(self, 'cmd_' + command, None)
            if cmd:
                return Response(
                    "```\n{}```".format(
                        dedent(cmd.__doc__.replace('{command_prefix}', self.config.command_prefix)),
                        command_prefix=self.config.command_prefix
                    ),
                    delete_after=60 if channel != 'Direct Message' else 0
                )
            else:
                return Response("No such command.", delete_after=10 if channel != 'Direct Message' else 0)

        else:
            helpmsg = "```"
            commandCount = 0

            for att in dir(self):
                if att.startswith('cmd_') and att != 'cmd_help':
                    command_name = att.replace('cmd_', self.config.command_prefix).lower()
                    if (commandCount % 3) == 0:
                        helpmsg += "\n"
                    commandCount += 1
                    helpmsg += "{0:20}".format(command_name)

            helpmsg += "```\nFor help on a specific command, type {0}help <command>".format(self.config.command_prefix)
            helpmsg += "\n\nor visit: https://github.com/mbmetcalfe/Abbot/wiki/Commands"

            em = discord.Embed(title='Commands', description=helpmsg, colour=0x2e456b)
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)

            return Response(em, reply=False, embed=True, delete_after=60 if channel != 'Direct Message' else 0)

    async def cmd_ping(self, channel, author, message, permissions):
        """
        Ping command to test latency.
        Usage:
            {command_prefix}ping
        """
        myTime = datetime.datetime.now()
        timeDiff = myTime - message.timestamp
        totalMs = ((timeDiff.seconds * 1000000) + timeDiff.microseconds) / 1000
        
        em = discord.Embed(title='Ping', description=':ping_pong: Pong {0}'.format(totalMs))
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
        return Response(em, reply=False, embed=True, delete_after=90)

    async def cmd_joke(self, channel, author, message, permissions, leftover_args):
        """
        Tell a joke.
        Usage:
            {command_prefix}joke [type [joke type]]
        Example:
            {command_prefix}joke
            Gives a random joke from the available joke types.
            {command_prefix}joke type
            Displays the type of jokes available.
            {command_prefix}joke type CleanJokes
            Tells a joke of type CleanJokes.
        """
        
        #TODO: Have him get a random one once/day.
        #TODO: Add the URL and author in the message.
        #TODO: decide on hot vs top vs new

        subreddit = 'Jokes' # default in case the next part fails to pick a valid subreddit

        # Check for command arguments
        if len(leftover_args) > 0:
            if len(leftover_args) == 1 and leftover_args[0].lower() == "type":
                em = discord.Embed(title='Joke Types', description='The following joke types can be chosen: {0}'.format(', '.join(self.config.reddit_joke_subreddit_list)), colour=0xf4d742)
                em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
                return Response(em, reply=False, embed=True, delete_after=90)
            elif len(leftover_args) == 2 and leftover_args[0].lower() == "type":
                subreddit = leftover_args[1]
                # Not a valid option.
                if subreddit.lower() not in [x.lower() for x in self.config.reddit_joke_subreddit_list]:
                    em = discord.Embed(title='Joke Error', description='Invalid joke type.\n\nThe following joke types can be chosen: {0}'.format(', '.join(self.config.reddit_joke_subreddit_list)), colour=0xff0000)
                    em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
                    return Response(em, reply=False, embed=True, delete_after=90)
            else:
                em = discord.Embed(title='Joke Error', description='Invalid joke option.', colour=0xff0000)
                em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
                return Response(em, reply=False, embed=True, delete_after=90)
        else:
            # Choose a random subreddit
            if self.config.reddit_joke_subreddit_list:
                subreddit = random.sample(self.config.reddit_joke_subreddit_list, 1)[0]
            
        joke = self.get_reddit_post(subreddit)

        if joke:
            em = discord.Embed(title=subreddit, description='{0}\n{1}'.format(joke.title, joke.selftext), colour=0xf4d742)
            em.set_author(name=joke.author, url=joke.url, icon_url='https://www.redditstatic.com/icon.png')
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
            return Response(em, reply=False, embed=True)

    async def cmd_whois(self, channel, author, message, user_mentions):
        """
        Show discord information about someone.
        Usage:
            {command_prefix}whois [user mention]
        """
        if len(user_mentions) == 0:
            member = author
        elif len(user_mentions) >= 1:
            # if more than one mention is supplied, we only grab the first one.
            member = discord.utils.get(message.server.members, id=user_mentions[0].id)
        
        # Build the message
        iterRoles = iter(member.roles)
        next(iterRoles) # First role is always @everyone, so ignore that one.
        roleMessage = ', '.join([role.name for role in iterRoles])
        em = discord.Embed(
            title='{0.display_name}{1} AKA {0.name}#{0.discriminator}'.format(member, (" :robot:" if member.bot else "")), 
            colour=member.colour)
        em.add_field(name='Status', value=str(member.status).title(), inline=True)
        em.add_field(name='Created', value=member.created_at, inline=True)
        em.add_field(name='Joined {0}'.format(message.server), value=member.joined_at, inline=True)
        em.add_field(name='Roles', value=roleMessage, inline=False)
        if member.game != None:
            em.add_field(name='Playing', value=member.game, inline=True)
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=author.avatar_url)
        em.set_thumbnail(url=member.avatar_url)
        return Response(em, reply=False, embed=True)

    async def cmd_idea(self, message, leftover_args):
        """
        Adds an idea to the idea box.
        Usage:
            {command_prefix}idea <text>
        """
        text = " ".join(leftover_args)
        
        idea = db.Idea(self.database, message.author.id, message.server.id, message.channel.id, text)
        success = idea.insert()
        
        if success:
            return Response("Thanks for your submission.", reply=True, delete_after=30 if message.channel != 'Direct Message' else 0)
        else:
            logger.error("There was a problem saving the submitted idea.")
            em = discord.Embed(
                title='Error', 
                description='There was a problem submitting your idea.  Please try again later and if problem persists, contact the developer.',
                colour=discord.Colour.dark_red())
            em.add_field(name='Command', value='Idea', inline=False)
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=message.author.avatar_url)
            em.set_thumbnail(url=message.author.avatar_url)

            return Response(em, reply=False, embed=True, delete_after=30 if message.channel != 'Direct Message' else 0)

    async def cmd_choose(self, channel, author, message, permissions, leftover_args):
        """
        Chooses between multiple choices.  Separate each choice by a comma.
        Usage:
            {command_prefix}choose <choice1, choice2, ..., choiceN>
        """
        
        userChoices = " ".join(leftover_args).split(",")
        
        if len(userChoices) <= 2:
            return Response(":exclamation: Must give two or more choices for this command to work correctly.", reply=True, delete_after=30)

        i = 1
        choices = ""
        for choice in userChoices:
            choices += '\n\t**{0}**: {1}'.format(i, choice.strip())
            i += 1

        em = discord.Embed(title='Choose', description='Choices: {0}\n\nRandomly chosen item: **{1}**'.format(choices, random.choice(userChoices)))
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
        return Response(em, reply=False, embed=True, delete_after=90)

    async def cmd_pick(self, channel, author, message, server, permissions):
        """
        Pick a random user from the server.
        Usage:
            {command_prefix}pick
        """
        pickMembers = []
        await self.safe_send_message(channel, "Gathering all the people.")
        await self.send_typing(channel)
        await asyncio.sleep(5)
        for member in server.members:
            if not member.bot:
                pickMembers.append(member.mention)

        await self.safe_send_message(channel, "Ok, have all the people, let's see who is the lucky winner.  :drum:-roll please!")
        await self.send_typing(channel)
        await asyncio.sleep(3)
        
        if len(pickMembers) > 0:
            em = discord.Embed(title='Random User Pick', description='{0} has requested to pick a random user.\n\n{1} was chosen!'.format(author.mention, random.choice(pickMembers)), colour=0x2e456b)
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
            return Response(em, reply=False, embed=True, delete_after=0)

    async def cmd_roll(self, channel, author, message, permissions, dice):
        """
        Rolls a dice in NdN format.
        Usage:
            {command_prefix}roll XdY
        Examples:
            ?roll 1d6 
            rolls one 6-sided die
            ?roll 2d20
            rolls 2 20-sided dice.
            """
        try:
            rolls, limit = map(int, dice.split('d'))
        except Exception:
            # On exception (invalid format), default to one roll of a 6-sided dice
            rolls = 1
            limit = 6

        if random.randint(1, 5) == 5:
            await self.safe_send_message(dest=channel, content='https://giphy.com/gifs/please-upvotes-ken-xR2SI8vqfQMLe',
                expire_in=20,
                also_delete=None
                )

        result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
        p = inflect.engine()
        wordRolls = p.number_to_words(rolls)

        await self.send_typing(channel)
        await asyncio.sleep(rolls * 3) # simulate rolling the dice (~3 seconds/dice)

        em = discord.Embed(title='Dice Roll', description=author.mention + ' has rolled ' + wordRolls + ' ' + str(limit) + '-sided dice.\n\nThe result is: ' + result, colour=0x2e456b)
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=author.avatar_url)
        return Response(em, reply=False, embed=True)

    async def cmd_rpsls(self, channel, author, message, permissions, item):
        """
        Play Rock, Paper, Scissors, Lizard, Spock with Abbot.
        Usage:
            {command_prefix}rpsls <item>
        """
        GAME_OPTIONS = ['rock', 'spock', 'paper', 'lizard', 'scissors']
        EMOJI_GAME_OPTIONS = [':gem:', ':vulcan:', ':page_facing_up:', ':lizard:', ':scissors:']
        # Verb used for the win conditions.
        VERBS = [[None, None, None, 'crushes', 'crushes'],    # Rock
                 ['vaporizes', None, None, None, 'smashes'],  # Spock
                 ['covers', 'disapproves', None, None, None], # Paper
                 [None, 'poisons', 'eats', None, None],       # Lizard
                 [None, None, 'cuts', 'decapitates', None]]   # Scissors

        # convert name to playerNumber using name_to_number
        try:
            playerNumber = GAME_OPTIONS.index(item.strip().lower())
        except ValueError:
            return Response(":exclamation: '{0}' is not a valid choice.".format(item), reply=True, delete_after=30)

        # compute random guess for computerNumber using random.randrange()
        computerNumber = random.randrange(0, 5)

        # compute difference of playerNumber and computerNumber modulo five
        winner = (computerNumber - playerNumber) % 5

        # determine winner
        player_win = False if winner < 3 else True
        
        # print results
        rpslsMessage = "{2} chooses {0}.\nI choose {1}.".format(
            EMOJI_GAME_OPTIONS[playerNumber], 
            EMOJI_GAME_OPTIONS[computerNumber],
            author.mention)
        if player_win:
             winVerb = VERBS[playerNumber][computerNumber]
             rpslsMessage += "\n{0} {2} {1}.\n{3} wins!".format(
                EMOJI_GAME_OPTIONS[playerNumber], 
                EMOJI_GAME_OPTIONS[computerNumber], 
                winVerb,
                author.mention)
        elif computerNumber == playerNumber:
             rpslsMessage += "\nWe tie!"
        else:
             winVerb = VERBS[computerNumber][playerNumber]
             rpslsMessage += "\n{0} {2} {1}.\nI win!".format(
                EMOJI_GAME_OPTIONS[computerNumber], 
                EMOJI_GAME_OPTIONS[playerNumber], 
                winVerb)
        
        em = discord.Embed(title='Rock, Paper, Scissors, Lizard, Spock', description=rpslsMessage)
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
        return Response(em, reply=False, embed=True, delete_after=90)

    async def cmd_usage(self, channel, author, message, permissions, user_mentions, leftover_args):
        """
        Gets usage information.  By default, shows your own usage for the current channel.
        Usage:
            {command_prefix}usage [user mention|rank] [server]
        Examples:
            {command_prefix}usage 
            Gets your own usage information for the current channel.
            {command_prefix}usage @abbot
            Gets the usage information for the user Abbot.
            {command_prefix}usage server
            Gets your own usage information for the current server.
            {command_prefix}usage rank
            Shows usage rankings for the current channel.
            {command_prefix}usage server rank
            Shows usage rankings for the current server (for all channels the bot is in).
            """
        if len(user_mentions) == 1:
            member = discord.utils.get(message.server.members, id=user_mentions[0].id)
        else:
            member = author

        messageUsage = None
        reactionUsage = None
        rank = False
        queryServer = False
        target = "#" + message.channel.name
        for arg in leftover_args:
            if arg.lower() == "server":
                queryServer = True
                target = message.server.name
            elif arg.lower() == "rank":
                rank = True
            else:
                logger.debug("Unsupported usage argument '{0}'".format(arg))

        if not rank:
            messageUsage = db.MessageUsage(database=self.database, user=member.id, server=message.server.id, channel=None if queryServer else message.channel.id)
            reactionUsage = db.ReactionUsage(database=self.database, user=member.id, server=message.server.id, channel=None if queryServer else message.channel.id)
            mentionUsage = db.MentionUsage(database=self.database, user=member.id, server=message.server.id, channel=None if queryServer else message.channel.id)

            em = discord.Embed(
                title='{0} usage summary for {1.name}#{1.discriminator}'.format(target.upper(), member), colour=0x2e456b)
            if not messageUsage.newRecord: # If newRecord is true, then there is no reaction usage yet.
                if messageUsage.messageCount > 0:
                    em.add_field(name="Message Summary", value="A summarized view of how chatty {0} is.".format(member.display_name), inline=False)
                    em.add_field(name="# of Messages", value=messageUsage.messageCount, inline=True)
                    em.add_field(name='# of Words', value=messageUsage.wordCount, inline=True)
                    em.add_field(name='# of Characters', value=messageUsage.characterCount, inline=True)
                    em.add_field(name='Max Message', value=messageUsage.maxMessageLength, inline=True)
                    em.add_field(name='Last Message', value=messageUsage.lastMessageTimestamp, inline=False)
            
            if not reactionUsage.newRecord: # If newRecord is true, then there is no reaction usage yet.
                if reactionUsage.userReacted > 0 or reactionUsage.reactionsReceived > 0:
                    em.add_field(name="Reaction Summary", value="A review of {0}'s messages reacted to and that have received reactions.".format(member.display_name), inline=False)
                    if reactionUsage.userReacted > 0:
                        em.add_field(name="# of Reactions", value=reactionUsage.userReacted, inline=True)
                        # em.add_field(name="# Message Reacted", value=reactionUsage.messagesReacted, inline=True)
                    if reactionUsage.reactionsReceived > 0:
                        em.add_field(name="# of Reactions Received", value=reactionUsage.reactionsReceived, inline=True)
                        # em.add_field(name="# Messages Receiving Actions", value=reactionUsage.messagesReacted, inline=True)

            if not mentionUsage.newRecord: # If newRecord is true, then there is not reaction usage.
                if mentionUsage.userMentioned > 0 or mentionUsage.userMentions > 0 or mentionUsage.channelMentions > 0 or mentionUsage.roleMentions > 0:
                    em.add_field(name="Mention Summary", value="A review of {0}'s mentions.".format(member.display_name), inline=False)
                    if mentionUsage.userMentioned > 0:
                        em.add_field(name="# of Times Mentioned", value=mentionUsage.userMentioned, inline=True)
                    if mentionUsage.userMentions > 0:
                        em.add_field(name="# of Users Mentioned", value=mentionUsage.userMentions, inline=True)
                    if mentionUsage.channelMentions > 0:
                        em.add_field(name="# of Channels Mentioned", value=mentionUsage.channelMentions, inline=True)
                    if mentionUsage.roleMentions > 0:
                        em.add_field(name="# of Roles Mentioned", value=mentionUsage.roleMentions, inline=True)

            if member.bot and message.author.id != self.config.owner_id: # Only owner can get bot usage.
                em.description = "{0} does not want you to see that.".format(member.display_name)
                em.clear_fields()
            elif len(em.fields) == 0:
                em.description = "Nothing to see here yet.\n\nPerhaps {0} prefers to lurk?".format(member.display_name)
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=author.avatar_url)
            em.set_thumbnail(url=member.avatar_url)
            return Response(em, reply=False, embed=True)
        else: # Rank
            em = discord.Embed(
                title='{0} Rankings'.format(target.upper()), colour=0x2e456b)
            
            # --------------------------------------------------------------------------------------------------------------
            # Message Rankings
            # --------------------------------------------------------------------------------------------------------------
            messageUsageRank = db.MessageUsageRank(database=self.database, server=message.server.id, channel=None if queryServer else message.channel.id, maxRankings=5)

            # Get message count rankings
            rankingsOutput = ""
            messageUsageRank.getRankingsByMessageCount()
            numRankings = len(messageUsageRank.rankings)
            p = inflect.engine()
            if numRankings > 0:
                currentRank = 1
                for rank in messageUsageRank.rankings:
                    # TODO: Pretty up the output!
                    rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                    rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                        (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                        rank.value)
                    currentRank += 1

                em.add_field(name="Most Messages", value=rankingsOutput + "\n", inline=True)

            # Get word count rankings
            rankingsOutput = ""
            messageUsageRank.getRankingsByWordCount()
            numRankings = len(messageUsageRank.rankings)
            p = inflect.engine()
            if numRankings > 0:
                currentRank = 1
                for rank in messageUsageRank.rankings:
                    # TODO: Pretty up the output!
                    rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                    rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                        (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                        rank.value)
                    currentRank += 1

                em.add_field(name="Most Words", value=rankingsOutput + "\n", inline=True)

            # Get character count rankings
            rankingsOutput = ""
            messageUsageRank.getRankingsByCharacterCount()
            numRankings = len(messageUsageRank.rankings)
            if len(messageUsageRank.rankings) > 0:
                currentRank = 1
                for rank in messageUsageRank.rankings:
                    # TODO: Pretty up the output!
                    rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                    rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                        (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                        rank.value)
                    currentRank += 1

                em.add_field(name="Most Characters", value=rankingsOutput + "\n", inline=True)

            # Get character count rankings
            rankingsOutput = ""
            messageUsageRank.getRankingsByLongestMessage()
            numRankings = len(messageUsageRank.rankings)
            if len(messageUsageRank.rankings) > 0:
                currentRank = 1
                for rank in messageUsageRank.rankings:
                    # TODO: Pretty up the output!
                    rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                    rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                        (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                        rank.value)
                    currentRank += 1

                em.add_field(name="Longest Message", value=rankingsOutput + "\n", inline=True)

            # --------------------------------------------------------------------------------------------------------------
            # Mentions Rankings
            # --------------------------------------------------------------------------------------------------------------
            mentionUsageRank = db.MentionUsageRank(database=self.database, server=message.server.id, channel=None if queryServer else message.channel.id, maxRankings=5)

            # Get most mentioned user/role/channel
            rankingsOutput = ""
            mentionUsageRank.getRankingsByUserMentioned()
            numRankings = len(mentionUsageRank.rankings)
            p = inflect.engine()
            if numRankings > 0:
                currentRank = 1
                for rank in mentionUsageRank.rankings:
                    # TODO: Pretty up the output!
                    rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                    rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                        (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                        rank.value)
                    currentRank += 1

                if currentRank > 0:
                    em.add_field(name="Most Mentioned Users", value=rankingsOutput + "\n", inline=True)

            rankingsOutput = ""
            mentionUsageRank.getRankingsByUserMentions()
            numRankings = len(mentionUsageRank.rankings)
            p = inflect.engine()
            if numRankings > 0:
                currentRank = 0
                for rank in mentionUsageRank.rankings:
                    # TODO: Pretty up the output!
                    if rank.value > 0:
                        currentRank += 1
                        rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                        rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                            (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                            rank.value)

                if currentRank > 0:
                    em.add_field(name="Most User Mentions", value=rankingsOutput + "\n", inline=True)

            # --------------------------------------------------------------------------------------------------------------
            # Reactions Rankings
            # --------------------------------------------------------------------------------------------------------------
            reactionUsageRank = db.ReactionUsageRank(database=self.database, server=message.server.id, channel=None if queryServer else message.channel.id, maxRankings=5)

            # Get user reacted rankings
            rankingsOutput = ""
            reactionUsageRank.getRankingsByUserReacted()
            numRankings = len(reactionUsageRank.rankings)
            p = inflect.engine()
            if numRankings > 0:
                currentRank = 0
                for rank in reactionUsageRank.rankings:
                    # TODO: Pretty up the output!
                    if rank.value > 0:
                        currentRank += 1
                        rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                        rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                            (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                            rank.value)


                if currentRank > 0:
                    em.add_field(name="Reacted Most", value=rankingsOutput + "\n", inline=True)

            # Get user reactions rankings
            rankingsOutput = ""
            reactionUsageRank.getRankingsByUserReactionsReceived()
            numRankings = len(reactionUsageRank.rankings)
            if len(reactionUsageRank.rankings) > 0:
                currentRank = 0
                for rank in reactionUsageRank.rankings:
                    # TODO: Pretty up the output!
                    if rank.value > 0:
                        currentRank += 1
                        rankWord = db.GenericRank.rankIndicator(currentRank, numRankings)

                        rankingsOutput += "{0}: {1}........**{2}**\n".format(rankWord, 
                            (discord.utils.get(message.server.members, id=rank.user)).display_name, 
                            rank.value)


                if currentRank > 0:
                    em.add_field(name="Most Reacted User", value=rankingsOutput + "\n", inline=True)

            # --------------------------------------------------------------------------------------------------------------
            # Wrap it up.
            # --------------------------------------------------------------------------------------------------------------
            if len(em.fields) == 0:
                em.description = "Nothing to see here yet."
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=author.avatar_url)
            em.set_thumbnail(url=member.avatar_url)
            return Response(em, reply=False, embed=True)


# --------------------------------------------------------------------------------------------------------------
# Owner-only commands
# cmd_clean can be taken out of own_only when sanity checked to not break.
# --------------------------------------------------------------------------------------------------------------
    @owner_only
    async def cmd_clean(self, message, channel, server, author, search_range=50):
        """
        Removes up to [range] messages the bot has posted in chat. Default: 50, Max: 1000
        Usage:
            {command_prefix}clean [range]
        """

        try:
            float(search_range)  # lazy check
            search_range = min(int(search_range), 1000)
        except:
            return Response("please enter a number.", reply=True, delete_after=8)

        await self.safe_delete_message(message, quiet=True)

        def is_possible_command_invoke(entry):
            valid_call = any(
                entry.content.startswith(prefix) for prefix in [self.config.command_prefix])  # can be expanded
            return valid_call and not entry.content[1:2].isspace()

        delete_invokes = True
        delete_all = channel.permissions_for(author).manage_messages or self.config.owner_id == author.id

        def check(message):
            if is_possible_command_invoke(message) and delete_invokes:
                return delete_all or message.author == author
            return message.author == self.user

        if self.user.bot:
            if channel.permissions_for(server.me).manage_messages:
                deleted = await self.purge_from(channel, check=check, limit=search_range, before=message)
                return Response('Cleaned up {} message{}.'.format(len(deleted), 's' * bool(deleted)), delete_after=15)

        deleted = 0
        async for entry in self.logs_from(channel, search_range, before=message):
            if entry == self.server_specific_data[channel.server]['last_np_msg']:
                continue

            if entry.author == self.user:
                await self.safe_delete_message(entry)
                deleted += 1
                await asyncio.sleep(0.21)

            if is_possible_command_invoke(entry) and delete_invokes:
                if delete_all or entry.author == author:
                    try:
                        await self.delete_message(entry)
                        await asyncio.sleep(0.21)
                        deleted += 1

                    except discord.Forbidden:
                        delete_invokes = False
                    except discord.HTTPException:
                        pass

        return Response('Cleaned up {} message{}.'.format(deleted, 's' * bool(deleted)), delete_after=15)

    @owner_only
    async def cmd_presence(self, server, channel, leftover_args):
        """Set the bot's now playing status."""
        text = " ".join(leftover_args)
        await self.update_presence(text)
        
        return Response(":ok_hand:", delete_after=20)

    @owner_only
    async def cmd_setname(self, leftover_args, name):
        """
        Changes the bot's username.
        Note: This operation is limited by discord to twice per hour.
        Usage:
            {command_prefix}setname name
        """

        name = ' '.join([name, *leftover_args])

        try:
            await self.edit_profile(username=name)
        except Exception as e:
            raise exceptions.CommandError(e, expire_in=20)

        return Response(":ok_hand:", delete_after=20)

    @owner_only
    async def cmd_setnick(self, server, channel, leftover_args, nick):
        """
        Changes the bot's nickname.
        Usage:
            {command_prefix}setnick nick
        """

        if not channel.permissions_for(server.me).change_nickname:
            raise exceptions.CommandError("Unable to change nickname: no permission.")

        nick = ' '.join([nick, *leftover_args])

        try:
            await self.change_nickname(server.me, nick)
        except Exception as e:
            raise exceptions.CommandError(e, expire_in=20)

        return Response(":ok_hand:", delete_after=20)

    @owner_only
    async def cmd_setavatar(self, message, url=None):
        """
        Changes the bot's avatar.
        Attaching a file and leaving the url parameter blank also works.
        Usage:
            {command_prefix}setavatar [url]
        """

        if message.attachments:
            thing = message.attachments[0]['url']
        else:
            thing = url.strip('<>')

        try:
            with aiohttp.Timeout(10):
                async with self.aiosession.get(thing) as res:
                    await self.edit_profile(avatar=await res.read())

        except Exception as e:
            raise exceptions.CommandError("Unable to change avatar: %s" % e, expire_in=20)

        return Response(":ok_hand:", delete_after=20)

    @owner_only
    async def cmd_sendall(self, args, leftover_args):
        """
        Sends a message to all servers the bot is on
        Usage:
            {command_prefix}sendall <message>
        """
        if leftover_args:
            args = ' '.join([args, *leftover_args])
        for s in self.servers:
            await self.safe_send_message(s, args)
        
        return Response(":ok_hand: '{0} sent to all servers.".format(args), delete_after=20)

    @owner_only
    async def cmd_archivedb(self, message):
        """
        Archives the current database into archive tables.
        Usage:
            {command_prefix}archivedb
        """
        archived = self.database.archive()

        if archived:
            return Response(":ok_hand: Database has been archived.", reply=True, delete_after=20)
        else:
            return Response(":interrobang: Something went wrong with the database archiving.", reply=True, delete_after=20)

    async def try_add_reaction(self, message):
        """Check the message content.  If certain criteria are met, react with appropriate reaction."""
        emoji = None

        if random.randint(1, 4) != 1: # 25% chance to react
            return

        #TODO: Add trigger text/reaction/complete match in configuration (consider possibility for regex in trigger)
        # Add a reaction if a long message (atm, max length for a single message is 2000).
        if len(message.content) > 1200:
            emoji = random.choice(['📕', '📗', '📘', '📙', '📖'])
            await self.safe_add_reaction(message, emoji)
        
        # Check for keywords and react accordingly.
        if any(re.search(r'\b{0}\b'.format(x), message.content, re.IGNORECASE) for x in ["cool", "kool", "kewl", "awesome", "great", "fantastic"]):
            emoji = random.choice(['😎', '🆒'])
            await self.safe_add_reaction(message, emoji)
        if "ok" == message.content.lower(): # complete match only
            emoji = random.choice(['👍', '👌', '🆗'])
            await self.safe_add_reaction(message, emoji)
        if any(re.search(r'\b{0}\b'.format(x), message.content, re.IGNORECASE) for x in ["shit(\w+)?", "crap(\w+)?", "poop(\w+)?", "turd"]):
            await self.safe_add_reaction(message, '💩')
        if any(re.search(r'\b{0}\b'.format(x), message.content, re.IGNORECASE) for x in ["(ha)+", "(lol)+", "lmao", "lmfao"]):
            emoji = random.choice(['😀', '😃', '😄', '😁', '😆', '😂', '😝', '😹', '😺', '😸'])
            await self.safe_add_reaction(message, emoji)
        if "rofl" == message.content.lower():
            await self.safe_add_reaction(message, '🤣')
        if re.search(r'\b[Bb][oO][oO]+\b', message.content, re.IGNORECASE):
            emoji = random.choice(['😱', '😨', '👻'])
            await self.safe_add_reaction(message, emoji)
        if "free" == message.content.lower():
            await self.safe_add_reaction(message, '🆓')
        if any(re.search(r'\b{0}\b'.format(x), message.content, re.IGNORECASE) for x in ["sales?", "discounts?"]):
            emoji = random.choice(['💲', '🏷', '🤑'])
            await self.safe_add_reaction(message, emoji)
        if any(re.search(r'\b{0}\b'.format(x), message.content, re.IGNORECASE) for x in ["fuck(\w+)?", "damn", "bitch", "piss", "dick(head|less)?", "cock", "pussy", "ass(hole|hat)?", "bastard", "slut", "douche"]):
            # '🤬' is not recognized by Discord :(
            emoji = random.choice(['🙉', '🙊'])
            await self.safe_add_reaction(message, emoji)

#        if emoji != None:
#            await self.safe_add_reaction(message, emoji)
        

    async def log_message_usage(self, message):
        """
        Log the message usage for the user.
        """
        #TODO: Add a command to show leaderboard: longest single message, most messages, most typed characters, most commands used,
        #   most common command, least used command.
        #TODO: Add a command for generic stats, similar to the leaderboard.
        #TODO: Consider a task to clean up data at the start of the month and/or push data to a "totals" table.
        #TODO: Log mentions (channel, user, role), reactions.
        #   on_reaction_add/on_reaction_remove
        #TODO: Consider reacting to on_message_edit and updating the stats accordingly (for non-commands only).
        #TODO: Filter out/count link-only messages.
        #   regex: ^((https?|ftps?|telnet|ssh|mailto):\/\/)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&\/= ]*)$

        if message.author.bot: # We don't really care to track bot usage
            return

        content = message.content
        messageUsage = db.MessageUsage(self.database, message.author.id, message.server.id, message.channel.id)
        if messageUsage.lastMessageTimestamp == None:
            messageUsage.wordCount = len(content.split())
            messageUsage.characterCount = len(content)
            messageUsage.maxMessageLength = messageUsage.characterCount
            messageUsage.messageCount = 1
            
            messageUsage.insert()
        else:
            contentSize = len(content.split())
            charCount = len(content)
            messageUsage.wordCount += contentSize
            messageUsage.characterCount += charCount
            messageUsage.maxMessageLength = charCount if charCount > messageUsage.maxMessageLength else messageUsage.maxMessageLength
            messageUsage.messageCount += 1
            messageUsage.update()

        await self.log_mention_usage(message)

    async def log_reaction_usage(self, reaction, user, add):
        """
        Log the reaction usage for the user reacting and the reacted user.

        Keyword arguments:
        reaction -- The reaction being added or removed.
        user     -- The user performing the reaction.
        add      -- If the reaction is being added or removed.
        """
        # First log the user that is reacting.
        reactingUserUsage = db.ReactionUsage(self.database, user.id, reaction.message.server.id, reaction.message.channel.id)
        if reactingUserUsage.newRecord and add: # Nothing recorded yet.
            reactingUserUsage.messagesReacted = 1
            reactingUserUsage.userReacted = 1
            reactingUserUsage.insert()
        else:
            reactingUserUsage.messagesReacted += 1 if add else -1
            reactingUserUsage.userReacted += 1 if add else -1
            reactingUserUsage.update()

        # Then log the user that is being reacted to.
        reactedUserUsage = db.ReactionUsage(self.database, reaction.message.author.id, reaction.message.server.id, reaction.message.channel.id)
        if reactedUserUsage.newRecord and add: # Nothing recorded yet.
            reactedUserUsage.messageReactionsReceived = 1
            reactedUserUsage.reactionsReceived = 1
            reactedUserUsage.insert()
        else:
            reactedUserUsage.messageReactionsReceived += 1 if add else -1
            reactedUserUsage.reactionsReceived += 1 if add else -1
            reactedUserUsage.update()

    async def log_command_usage(self, command, validCommand, message):
        """
        Log the command usage for the user.
        """
        commandUsage = db.CommandUsage(self.database, message.author.id, message.server.id, message.channel.id, command, validCommand)
        # if commandUsage.newRecord:
        #     commandUsage.insert()
        # else:
        #     commandUsage.count += 1
        #     commandUsage.update()

    async def log_mention_usage(self, message):
        """
        Log the mention usage for the user as well as the user(s), channel(s), and role(s) being mentioned.
        Note that this does not log unique mentions, just how many times a user has mentioned something or has been mentioned.
        """
        # First log the mention usage for the author of the message.

        # the raw_X_mentions arrays are not unique, so we can convert it to a set, then a list to make it a unique list.
        userMentionUsage = db.MentionUsage(self.database, message.author.id, message.server.id, message.channel.id)
        if userMentionUsage.newRecord:
            userMentionUsage.userMentions = len(list(set(message.raw_mentions)))
            userMentionUsage.channelMentions = len(list(set(message.raw_channel_mentions)))
            userMentionUsage.roleMentions = len(list(set(message.raw_role_mentions)))
            userMentionUsage.insert()
        else:
            userMentionUsage.userMentions += len(list(set(message.raw_mentions)))
            userMentionUsage.channelMentions += len(list(set(message.raw_channel_mentions)))
            userMentionUsage.roleMentions += len(list(set(message.raw_role_mentions)))
            userMentionUsage.update()

        # Now update the count for users mentioned.
        for mentioned in list(set(message.raw_mentions)):
            userMentioned = db.MentionUsage(self.database, mentioned, message.server.id, message.channel.id)
            if userMentioned.newRecord:
                userMentioned.userMentioned = 1
                userMentioned.insert()
            else:
                userMentioned.userMentioned += 1
                userMentioned.update()
            userMentioned = None

# -----------
# Secret-Gifter Event Commands
# -----------
    async def cmd_event(self, channel, author, permissions, leftover_args):
        """
        Opt-in, give your address, give your size, or check status of the event.
        Usage:
            {command_prefix}event <opt_in|address|size|status>
        Sub-Commands:
            opt_in: Opts you into the event.
                Usage: {command_prefix}event opt_in
            address: Adds your mailing address.  Separate each "line" of your address by a comma.
                Usage: {command_prefix}event address <address line1, address line2, city, province, postal code>
                Example: {command_prefrix}event address 55 My Street, P.O. Box 123, City Ville, NS, A2B3B4
            size: Adds your shirt size.
                Usage: {command_prefix}event size Your Size
                Example: {command_prefix}event size Medium
            status: reports your status for the event.
                Usage: {command_prefix}event status
        """
        if len(leftover_args) == 0:
            return Response("No options given.  Try again (see **?help event** for more details).")
            
        if leftover_args[0] == "opt_in":
            return Response('Opting you in.')

        elif leftover_args[0] == "address":
            if len(leftover_args) < 2:
                return Response("You must supply an address.")

            # Separate each addres "line" by comma
            address_lines = " ".join(leftover_args[1:]).split(",")
            address_desc = 'Your address has been logged as:'
            for line in address_lines:
                address_desc += '\n\t{0}'.format(line.strip())
            em = discord.Embed(title='Event: Address', description=address_desc, colour=0x7FFF00)
            
            return Response(em, embed=True, reply=False, delete_after=0)
        elif leftover_args[0] == "size":
            if len(leftover_args) < 2:
                return Response("You must supply a size.")

            em = discord.Embed(title='Event: Size', description='Your size logged as: {0}.'.format(" ".join(leftover_args[1:])), colour=0x7FFF00)
            return Response(em, embed=True, reply=False, delete_after=0)

        elif leftover_args[0] == "status":
            await self.safe_send_message(
                author, 'Status not yet implemented.',
                expire_in=0,
                also_delete=None
                )

            return Response('Status has been sent to you via personal message.', reply=True, delete_after=90, embed=False)
        else:
            return Response('Unrecognized *event* parameter "{0}"'.format(leftover_args[0]))

# -----------
# Events
# -----------
    async def on_member_update(self, before, after):
        if before.game != None and after.game != None and before.game.name != after.game.name:
            logger.debug(" Before (After): {0.display_name} ({2.display_name}) Status: {0.status} ({2.status}) Game: {1} ({3}).".format(
                before, 
                before.game.name if before.game != None else "N/A",
                after, 
                after.game.name if after.game != None else "N/A"))
    
# ---------
#
    async def on_member_join(self, member):
        server = member.server
        channel = server.get_channel
        logger.debug("Server {0}; Channel {1}; Member {2.name}".format(server, channel, member))
        fmt = "Oh hey, it's {0.mention}!  Welcome to the **{1.name}** Discord server.  Please behave yourself."

        role = discord.utils.get(server.roles, name='Minions')
        try:
            logger.debug("Role {0.name}; Created {0.created_at}".format(role))
            await self.add_roles(member, role)
            
            await self.safe_send_message(channel, fmt.format(member, server))
        except discord.Forbidden:
            await self.safe_send_message(channel, "Lol I can't add roles bro.")
        # check that they are joining 'this' server
        #if member.guild.id != 379363572876181515:
        #    return

    
    async def on_member_remove(self, member):
        server = member.server
        channel = server.get_channel
        fmt = '{0.mention} has left/been kicked from the server.'
        await self.safe_send_message(channel, fmt.format(member, server))

    async def update_presence(self, message):
        game = None
        if self.user.bot:
            game = discord.Game(name=message)
        else:
            game = discord.Game(name="Huh?")

        await self.change_presence(game=game, status=None, afk=False)

    
    async def on_message(self, message):
        # TODO: Change the scope of this variable.
        pmCommandList = ['joinserver', 'event', 'idea', 'help']
        await self.wait_until_ready()

        message_content = message.content.strip()
        if not message_content.startswith(self.config.command_prefix):
            if message.author != self.user:
                await self.log_message_usage(message)
                await self.try_add_reaction(message)
            return

        if message.author == self.user:
            logger.info("Ignoring command from myself (%s)" % message.content)
            return

        if self.config.bound_channels and message.channel.id not in self.config.bound_channels and not message.channel.is_private:
            return  # if I want to log this I just move it under the prefix check

        command, *args = message_content.split()  # Uh, doesn't this break prefixes with spaces in them (it doesn't, config parser already breaks them)
        command = command[len(self.config.command_prefix):].lower().strip()

        handler = getattr(self, 'cmd_%s' % command, None)
        if not handler:
            await self.log_command_usage(command, False, message)
            return
        else:
            await self.log_command_usage(command, True, message)

        if message.channel.is_private:
            if not (message.author.id == self.config.owner_id and (command in pmCommandList)):
                await self.send_message(message.channel, 'You cannot use the **{0}** command in a private message.'.format(command))
                return

        if message.author.id in self.blacklist and message.author.id != self.config.owner_id:
            logger.info("[User blacklisted] {0.id}/{0.name} ({1})".format(message.author, message_content))
            return

        # else:
        #     logger.info("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))

        user_permissions = self.permissions.for_user(message.author)

        argspec = inspect.signature(handler)
        params = argspec.parameters.copy()

        # noinspection PyBroadException
        try:
            if user_permissions.ignore_non_voice and command in user_permissions.ignore_non_voice:
                await self._check_ignore_non_voice(message)

            handler_kwargs = {}
            if params.pop('message', None):
                handler_kwargs['message'] = message

            if params.pop('channel', None):
                handler_kwargs['channel'] = message.channel

            if params.pop('author', None):
                handler_kwargs['author'] = message.author

            if params.pop('server', None):
                handler_kwargs['server'] = message.server

            if params.pop('player', None):
                handler_kwargs['player'] = await self.get_player(message.channel)

            if params.pop('permissions', None):
                handler_kwargs['permissions'] = user_permissions

            if params.pop('user_mentions', None):
                handler_kwargs['user_mentions'] = list(map(message.server.get_member, message.raw_mentions))

            if params.pop('channel_mentions', None):
                handler_kwargs['channel_mentions'] = list(map(message.server.get_channel, message.raw_channel_mentions))

            if params.pop('voice_channel', None):
                handler_kwargs['voice_channel'] = message.server.me.voice_channel

            if params.pop('leftover_args', None):
                handler_kwargs['leftover_args'] = args

            args_expected = []
            for key, param in list(params.items()):
                doc_key = '[%s=%s]' % (key, param.default) if param.default is not inspect.Parameter.empty else key
                args_expected.append(doc_key)

                if not args and param.default is not inspect.Parameter.empty:
                    params.pop(key)
                    continue

                if args:
                    arg_value = args.pop(0)
                    handler_kwargs[key] = arg_value
                    params.pop(key)

            if message.author.id != self.config.owner_id:
                if user_permissions.command_whitelist and command not in user_permissions.command_whitelist:
                    raise exceptions.PermissionsError(
                        "This command is not enabled for your group (%s)." % user_permissions.name,
                        expire_in=20)

                elif user_permissions.command_blacklist and command in user_permissions.command_blacklist:
                    raise exceptions.PermissionsError(
                        "This command is disabled for your group (%s)." % user_permissions.name,
                        expire_in=20)

            if params:
                docs = getattr(handler, '__doc__', None)
                if not docs:
                    docs = 'Usage: {}{} {}'.format(
                        self.config.command_prefix,
                        command,
                        ' '.join(args_expected)
                    )

                docs = '\n'.join(l.strip() for l in docs.split('\n'))
                await self.safe_send_message(
                    message.channel,
                    '```\n%s\n```' % docs.format(command_prefix=self.config.command_prefix),
                    expire_in=60
                )
                return

            response = await handler(**handler_kwargs)
            if response and isinstance(response, Response):
                content = response.content
                if response.reply and not response.embed:
                    content = '%s, %s' % (message.author.mention, content)

                sentmsg = await self.safe_send_message(
                    message.channel, content,
                    expire_in=response.delete_after if self.config.delete_messages else 0,
                    also_delete=message if self.config.delete_invoking else None,
                    embed=response.embed,
                    reactions=response.reactions
                )

        except (exceptions.CommandError, exceptions.HelpfulError, exceptions.ExtractionError) as e:
            logger.info("{0.__class__}: {0.message}".format(e))

            expirein = e.expire_in if self.config.delete_messages else None
            alsodelete = message if self.config.delete_invoking else None

            await self.safe_send_message(
                message.channel,
                '```\n%s\n```' % e.message,
                expire_in=expirein,
                also_delete=alsodelete
            )

        except exceptions.Signal:
            raise

        except Exception:
            traceback.print_exc()
            if self.config.debug_mode:
                await self.safe_send_message(message.channel, '```\n%s\n```' % traceback.format_exc())

    async def on_reaction_add(self, reaction, user):
        """
        Log the addition reaction information.
        """
        await self.log_reaction_usage(reaction, user, True)

    async def on_reaction_remove(self, reaction, user):
        """
        Log when the reaction is removed.
        """
        await self.log_reaction_usage(reaction, user, False)

    # async def on_message_edit(self, before, after):
    #     logger.debug("Before: {0}\nAfter: {1}.".format(before.content, after.content))

    async def _auto_presence_task(self):
        await self.wait_until_ready()

        while not self.is_closed:
            if self.config.auto_status > 0 and self.config.auto_statuses:
                newStatus = random.sample(self.config.auto_statuses, 1)[0]
                await self.update_presence("{0} | {1}help".format(
                    newStatus,
                    self.config.command_prefix))

            # TODO: Add config for how long to wait until changing status.
            await asyncio.sleep(60 * self.config.auto_status) # Number of minutes to sleep and change status

if __name__ == '__main__':

    # Setup logging
    logger = logging.getLogger('abbot')
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.FileHandler(filename='abbot.log', mode='w')
    fh.setLevel(logging.ERROR)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s:%(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    # add the handlers to logger
    logger.addHandler(ch)
    logger.addHandler(fh)

    bot = Abbot()
    bot.run()

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

description = '''I am Abbot.  A bot written in Python and discord.py'''
bot = commands.Bot(command_prefix='?', description=description)

take_over_world = 'What are we going to do tonight?'
greet = 'Hello there'

class Response:
    def __init__(self, content, reply=False, embed=False, delete_after=0):
        self.content = content
        self.reply = reply
        self.embed = embed
        self.delete_after = delete_after

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

    async def send_typing(self, destination):
        try:
            return await super().send_typing(destination)
        except discord.Forbidden:
            if self.config.debug_mode:
                print("Could not send typing to %s, no permssion" % destination)

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
                print("Already joined a channel in %s, skipping" % channel.server.name)
                continue

            if channel and channel.type == discord.ChannelType.voice:
                self.safe_print("Attempting to autojoin %s in %s" % (channel.name, channel.server.name))

                chperms = channel.permissions_for(channel.server.me)

                if not chperms.connect:
                    self.safe_print("Cannot join channel \"%s\", no permission." % channel.name)
                    continue

                elif not chperms.speak:
                    self.safe_print("Will not join channel \"%s\", no permission to speak." % channel.name)
                    continue

                try:
                    player = await self.get_player(channel, create=True)

                    if player.is_stopped:
                        player.play()

                    if self.config.auto_playlist:
                        await self.on_player_finished_playing(player)

                    joined_servers.append(channel.server)
                except Exception as e:
                    if self.config.debug_mode:
                        traceback.print_exc()
                    print("Failed to join", channel.name)

            elif channel:
                print("Not joining %s on %s, that's a text channel." % (channel.name, channel.server.name))

            else:
                print("Invalid channel thing: " + channel)

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

    async def safe_send_message(self, dest, content, *, tts=False, expire_in=0, also_delete=None, quiet=False, embed=False):
        msg = None
        try:
            if embed:
                msg = await self.send_message(dest, embed=content, tts=tts)
            else:
                msg = await self.send_message(dest, content, tts=tts)

            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

            if also_delete and isinstance(also_delete, discord.Message):
                asyncio.ensure_future(self._wait_delete_msg(also_delete, expire_in))

        except discord.Forbidden:
            if not quiet:
                self.safe_print("Warning: Cannot send message to %s, no permission" % dest.name)

        except discord.NotFound:
            if not quiet:
                self.safe_print("Warning: Cannot send message to %s, invalid channel?" % dest.name)

        return msg

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
                self.safe_print("Warning: Cannot send message to %s, no permission" % dest.name)

        except discord.NotFound:
            if not quiet:
                self.safe_print("Warning: Cannot send message to %s, invalid channel?" % dest.name)

        return msg

    async def safe_delete_message(self, message, *, quiet=False):
        try:
            return await self.delete_message(message)

        except discord.Forbidden:
            if not quiet:
                self.safe_print("Warning: Cannot delete message \"%s\", no permission" % message.clean_content)

        except discord.NotFound:
            if not quiet:
                self.safe_print("Warning: Cannot delete message \"%s\", message not found" % message.clean_content)

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
                print("Error in cleanup:", e)

            self.loop.close()
            if self.exit_signal:
                raise self.exit_signal

    async def logout(self):
        await self.disconnect_all_voice_clients()
        return await super().logout()

    async def on_error(self, event, *args, **kwargs):
        ex_type, ex, stack = sys.exc_info()

        if ex_type == exceptions.HelpfulError:
            print("Exception in", event)
            print(ex.message)

            await asyncio.sleep(2)  # don't ask
            await self.logout()

        elif issubclass(ex_type, exceptions.Signal):
            self.exit_signal = ex_type
            await self.logout()

        else:
            traceback.print_exc()

    async def on_resumed(self):
        self.safe_print("Resumed...")
#        for vc in self.the_voice_clients.values():
#            vc.main_ws = self.ws

    async def on_ready(self):
        print('\rConnected!  Abbot v%s\n' % BOTVERSION)

        if self.config.owner_id == self.user.id:
            raise exceptions.HelpfulError(
                "Your OwnerID is incorrect or you've used the wrong credentials.",

                "The bot needs its own account to function.  "
                "The OwnerID is the id of the owner, not the bot.  "
                "Figure out which one is which and use the correct information.")

        self.init_ok = True

        self.safe_print("Bot:   %s/%s#%s" % (self.user.id, self.user.name, self.user.discriminator))

        owner = self._get_owner(voice=True) or self._get_owner()
        if owner and self.servers:
            self.safe_print("Owner: %s/%s#%s\n" % (owner.id, owner.name, owner.discriminator))

            print('Server List:')
            [self.safe_print(' - ' + s.name) for s in self.servers]

        elif self.servers:
            print("Owner could not be found on any server (id: %s)\n" % self.config.owner_id)

            print('Server List:')
            [self.safe_print(' - ' + s.name) for s in self.servers]

        else:
            print("Owner unknown, bot is not on any servers.")
            if self.user.bot:
                print("\nTo make the bot join a server, paste this link in your browser.")
                print("Note: You should be logged into your main account and have \n"
                      "manage server permissions on the server you want the bot to join.\n")
                print("    " + await self.generate_invite_link())

        print()

        if self.config.bound_channels:
            chlist = set(self.get_channel(i) for i in self.config.bound_channels if i)
            chlist.discard(None)
            invalids = set()

            invalids.update(c for c in chlist if c.type == discord.ChannelType.voice)
            chlist.difference_update(invalids)
            self.config.bound_channels.difference_update(invalids)

            print("Bound to text channels:")
            [self.safe_print(' - %s/%s' % (ch.server.name.strip(), ch.name.strip())) for ch in chlist if ch]

            if invalids and self.config.debug_mode:
                print("\nNot binding to voice channels:")
                [self.safe_print(' - %s/%s' % (ch.server.name.strip(), ch.name.strip())) for ch in invalids if ch]

            print()

        else:
            print("Not bound to any text channels")

        print()
        print("Options:")

        self.safe_print("  Command prefix: " + self.config.command_prefix)
        print("  Default volume: %s%%" % int(self.config.default_volume * 100))
        print("  Skip threshold: %s votes or %s%%" % (
            self.config.skips_required, self._fixg(self.config.skip_ratio_required * 100)))
        print("  Now Playing @mentions: " + ['Disabled', 'Enabled'][self.config.now_playing_mentions])
        print("  Delete Messages: " + ['Disabled', 'Enabled'][self.config.delete_messages])
        if self.config.delete_messages:
            print("    Delete Invoking: " + ['Disabled', 'Enabled'][self.config.delete_invoking])
        print("  Debug Mode: " + ['Disabled', 'Enabled'][self.config.debug_mode])
        print()

        # maybe option to leave the ownerid blank and generate a random command for the owner to use
        # wait_for_message is pretty neato

        if self.config.autojoin_channels:
            await self._autojoin_channels(autojoin_channels)

        print()
        # t-t-th-th-that's all folks!

    async def update_presence(author, *, description):
        game = None

        if self.user.bot:
            game = discord.Game(name=description)

        await self.change_presence(game)

# -----------
# Commands
# -----------
    async def cmd_help(self, channel, author, command=None):
        """
        Usage:
            {command_prefix}help [command]

        Prints a help message.
        If a command is specified, it prints a help message for that command.
        Otherwise, it lists the available commands.
        """

        if command:
            cmd = getattr(self, 'cmd_' + command, None)
            if cmd:
                return Response(
                    "```\n{}```".format(
                        dedent(cmd.__doc__),
                        command_prefix=self.config.command_prefix
                    ),
                    delete_after=60 if channel != 'Direct Message' else 0
                )
            else:
                return Response("No such command.", delete_after=10 if channel != 'Direct Message' else 0)

        else:
            helpmsg = ""
            commands = []
            commandCount = 0

            for att in dir(self):
                if att.startswith('cmd_') and att != 'cmd_help':
                    command_name = att.replace('cmd_', '').lower()
                    #commands.append("{}{}".format(self.config.command_prefix, command_name))
                    if (commandCount % 4) == 0:
                        helpmsg += "\n"
                    commandCount += 1
                    #helpmsg += "{0} - \t{1}".format(command_name, dedent(command_name.__doc__))
                    helpmsg += "{0:30}".format(command_name)

            helpmsg += "\n\nhttps://github.com/mbmetcalfe/Abbot/wiki/Commands"

            em = discord.Embed(title='Commands', description=helpmsg, colour=0x2e456b)
            #em.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
            em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)

            return Response(em, reply=False, embed=True, delete_after=60 if channel != 'Direct Message' else 0)

    async def cmd_ping(self, channel, author, message, permissions):
        """
        Usage:
            {command_prefix}ping
        Ping command to test latency.
        """
        myTime = datetime.datetime.now()
        timeDiff = myTime - message.timestamp
        totalMs = ((timeDiff.seconds * 1000000) + timeDiff.microseconds) / 1000
        
        em = discord.Embed(title='Ping', description=':ping_pong: Pong {0}'.format(totalMs))
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(author), icon_url=author.avatar_url)
        return Response(em, reply=False, embed=True, delete_after=90)

    async def cmd_whoami(self, channel, author, message, permissions):
        """Show some stats about thyself."""
        role_names = [role.name for role in author.roles]    
        whoamiMsg = "%s:\n\tRoles: %s\n\tTop Role: %s\n\tStatus: %s\n\tGame: %s\n\tJoined: %s" % (author.mention, role_names, author.top_role, author.status, author.game, author.joined_at)
        return Response(whoamiMsg, reply=False, delete_after=60)

    async def cmd_idea(self, channel, author, permissions, idea):
        """Adds an idea to the idea box."""
        logger.info('IDEA: {0} from {1}.'.format(idea, author.name))
        return Response("Thanks for your submission", reply=True, delete_after=30 if channel != 'Direct Message' else 0)

    async def cmd_choose(self, channel, author, message, permissions, choices):
        """Chooses between multiple choices."""
        myChoices = choices.split(",")
        self.safe_print("Choices: " % choices)
        self.safe_print("Choices: " % myChoices)
        return Response(random.choice(myChoices), reply=True)

    async def cmd_pick(self, channel, author, message, server, permissions):
        """Pick a random person from the server."""
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
        """Rolls a dice in NdN format.\ne.g. 1d6 rolls one 6-sided die;\n2d20 rolls 2 20-sided dice"""
        try:
            rolls, limit = map(int, dice.split('d'))
        except Exception:
            # On exception (invalid format), default to one roll of a 6-sided dice
            rolls = 1
            limit = 6

        result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
        p = inflect.engine()
        wordRolls = p.number_to_words(rolls)

        await self.send_typing(channel)
        await asyncio.sleep(rolls * 3) # simulate rolling the dice (~3 seconds/dice)

        em = discord.Embed(title='Dice Roll', description=author.mention + ' has rolled ' + wordRolls + ' ' + str(limit) + '-sided dice.\n\nThe result is: ' + result, colour=0x2e456b)
        #em.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
        
        em.set_footer(text='Requested by {0.name}#{0.discriminator}'.format(message.author), icon_url=author.avatar_url)
        #await bot.send_message(ctx.message.channel, embed=em)
        return Response(em, reply=False, embed=True)

    async def cmd_presence(self, channel, author, message):
        """Set the bot's presence."""
        await self.update_presence(author, "test")

# -----------
# Owner-only commands
# cmd_clean can be taken out of own_only when sanity checked to not break.
# -----------
    @owner_only
    async def cmd_clean(self, message, channel, server, author, search_range=50):
        """
        Usage:
            {command_prefix}clean [range]

        Removes up to [range] messages the bot has posted in chat. Default: 50, Max: 1000
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
    async def cmd_setname(self, leftover_args, name):
        """
        Usage:
            {command_prefix}setname name

        Changes the bot's username.
        Note: This operation is limited by discord to twice per hour.
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
        Usage:
            {command_prefix}setnick nick

        Changes the bot's nickname.
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
        Usage:
            {command_prefix}setavatar [url]

        Changes the bot's avatar.
        Attaching a file and leaving the url parameter blank also works.
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
        Usage:
            {command_prefix}sendall <message>
        Sends a message to all servers the bot is on
        """
        if leftover_args:
            args = ' '.join([args, *leftover_args])
        for s in self.servers:
            await self.safe_send_message(s, args)
        
        return Response(":ok_hand: '{0} sent to all servers.".format(args), delete_after=20)

# -----------
# Secret-Gifter Event Commands
# -----------
    async def cmd_event(self, channel, author, permissions, leftover_args):
        """
        Usage:
            {command_prefix}event <opt_in|address|size|status>

        Opt-in, give your address, give your size, or check status of the event.
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
                return Response("You must supply an size.")

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
    async def on_message(self, message):
        # TODO: Change the scope of this variable.
        pmCommandList = ['joinserver', 'event', 'idea', 'help']
        await self.wait_until_ready()

        message_content = message.content.strip()
        if not message_content.startswith(self.config.command_prefix):
            return

        if message.author == self.user:
            self.safe_print("Ignoring command from myself (%s)" % message.content)
            return

        if self.config.bound_channels and message.channel.id not in self.config.bound_channels and not message.channel.is_private:
            return  # if I want to log this I just move it under the prefix check

        command, *args = message_content.split()  # Uh, doesn't this break prefixes with spaces in them (it doesn't, config parser already breaks them)
        command = command[len(self.config.command_prefix):].lower().strip()

        handler = getattr(self, 'cmd_%s' % command, None)
        if not handler:
            return

        if message.channel.is_private:
            if not (message.author.id == self.config.owner_id and (command in pmCommandList)):
                await self.send_message(message.channel, 'You cannot use the **{0}** command in a private message.'.format(command))
                return

        if message.author.id in self.blacklist and message.author.id != self.config.owner_id:
            self.safe_print("[User blacklisted] {0.id}/{0.name} ({1})".format(message.author, message_content))
            return

        else:
            self.safe_print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))

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
                if response.reply:
                    content = '%s, %s' % (message.author.mention, content)

                sentmsg = await self.safe_send_message(
                    message.channel, content,
                    expire_in=response.delete_after if self.config.delete_messages else 0,
                    also_delete=message if self.config.delete_invoking else None,
                    embed = response.embed
                )

        except (exceptions.CommandError, exceptions.HelpfulError, exceptions.ExtractionError) as e:
            print("{0.__class__}: {0.message}".format(e))

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

#os.system('clear')
if __name__ == '__main__':
    bot = Abbot()
    bot.run()

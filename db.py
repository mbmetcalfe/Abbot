import sqlite3
import datetime
import random
import string
import logging

DATABASE_NAME = 'abbot.sqlite3'

def insertUpdateUsageCommand(user, server, channel, commandName, valid):
    """ This function is used to insert or update the usage of a command into the database for a user."""
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    commandCount = 1
    values = ()
    sql = ""

    logger.debug("insertUpdateCommand(user={0}, server={1}, channel={2}, commandName={3}, valid={4})".format(user, server, channel, commandName, valid))
    # First check if the user has used this command on the server/channel
    values = (user, server, channel, commandName)

    try:
        cur.execute("select count from usage_commands where user = ? and "
            "server = ? and "
            "channel = ? and "
            "command_name = ?", values)
        row = cur.fetchone()
        if row == None:
            sql = "insert into usage_commands (user, server, channel, command_name, valid, count) VALUES (?, ?, ?, ?, ?, ?)"
            values = (user, server, channel, commandName, valid, commandCount)
        else:
            commandCount = row[0] + 1
            sql = "update usage_commands set valid = ?, count = ? where user = ? and server = ? and channel = ? and command_name = ?"
            values = (valid, commandCount, user, server, channel, commandName)

        cur.execute(sql, values)

        # Save (commit) the changes
        conn.commit()

    except BaseException as ex:
        logger.error("There was a problem inserting or updating the database record: {0}".format(ex))
    finally:
        conn.close()

def insertUpdateUsageMessage(user, server, channel, message):
    """ This function is used to insert or update the usage of a message into the database for a user."""
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    values = ()
    sql = ""
    wordCount = len(message.split())
    characterCount = len(message)
    maxLength = characterCount
    ts = datetime.datetime.now()

    logger.debug("insertUpdateUsageMessage(user={0}, server={1}, channel={2}, message={3})".format(user, server, channel, "***"))

    # First check if the user has sent any messages on the server/channel
    values = (user, server, channel)

    try:
        cur.execute("select word_count, character_count, max_message_length from usage_messages where user = ? and "
            "server = ? and "
            "channel = ?", values)
        row = cur.fetchone()
        if row == None:
            sql = "insert into usage_messages (user, server, channel, word_count, character_count, max_message_length, last_message_timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)"
            values = (user, server, channel, wordCount, characterCount, maxLength, ts.strftime("%Y-%m-%d %H:%M:%S:%f"))
        else:
            wordCount += row[0]
            characterCount += row[1]
            if row[2] > maxLength:
                maxLength = row[2]

            sql = "update usage_messages set word_count = ?, character_count = ?, max_message_length = ?, last_message_timestamp = ? where user = ? and server = ? and channel = ?"
            values = (wordCount, characterCount, maxLength, ts.strftime("%Y-%m-%d %H:%M:%S:%f"), user, server, channel)

        cur.execute(sql, values)

        # Save (commit) the changes
        conn.commit()

    except BaseException as ex:
        logger.error("There was a problem inserting or updating the database record: {0}".format(ex))
    finally:
        conn.close()

def summarizeCommandUsage(server, channel, user, breakdown):
    """ This function is used to summarize the command usage for the given server, channel, and user."""
    values = []
    sql = 'select user, sum(count) as command_calls from usage_commands group by user'

    logger.debug("summarizeCommandUsage(server={0}, channel={1}, user={2}, breakdown={3})".format(server, channel, user, breakdown))
    # For now, assume that server is a required parameter -- all queries should relate
    # to the current server.
    if server == None:
        logger.info("Not implemented.")
        return

    if channel == None and user == None:
        values = [server]
        # Details for all commands
        if breakdown:
            sql = """select command_name, sum(count) as command_calls 
                from usage_commands where server = ? 
                group by command_name 
                order by 2 desc, command_name"""
        else:
            sql = """select sum(count) as command_calls from usage_commands where server = ? order by 1 desc"""

    elif channel == None and user != None:
        values = [server, user]
        # Details for a user on all channels
        if breakdown:
            sql = """select command_name, sum(count) as command_calls 
                from usage_commands where server = ? and user = ? 
                group by user, command_name order by 2 desc, command_name"""
        else:
            sql = """select sum(count) as command_calls 
                from usage_commands where server = ? and user = ? 
                group by user 
                order by 1 desc"""

    if channel != None and user == None:
        values = [server, channel]
        # Details for all commands from all users in a channel
        if breakdown:
            sql = """select command_name, sum(count) as command_calls 
                from usage_commands where server = ? and channel = ? 
                group by command_name order by 2 desc, command_name"""
        else:
            sql = """select sum(count) as command_calls 
                from usage_commands where server = ? and channel = ? 
                order by 1 desc"""

    elif channel != None and user != None:
        values = [server, user]
        # Details for a user on a channels
        if breakdown:
            sql = """select command_name, sum(count) as command_calls 
                from usage_commands where server = ? and channel = ? and user = ? 
                group by user, command_name 
                order by 2 desc, command_name"""
        else:
            sql = """select sum(count) as command_calls 
                from usage_commands where server = ? and channel = ? and user = ? 
                group by user order by 1 desc"""

    elif channel != None and user == None:
        sql = 'select user, sum(count) as command_calls from usage_commands'
        values = []
        
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # logger.debug("SQL = {0}".format(sql))
    # logger.debug("values = {0}".format(values))
    cur.execute(sql, values)
    columns = [i[0] for i in cur.description]
    logger.debug('|{0}|'.format('\t\t\t|'.join(columns)))
    for row in cur:
        rowStr = '|'
        for col in columns:
            rowStr += ("{0}\t\t\t|".format(row[col]))
        logger.debug(rowStr)

def summarizeMessageUsage(server, channel, user):
    """ This function is used to summarize the messages for the given server, channel, and user."""
    values = []
    sql = """select user, word_count, character_count, max_message_length from usage_messages order by max_message_length desc, user where server = ?"""

    logger.debug("summarizeMessageUsage(server={0}, channel={1}, user={2})".format(server, channel, user))
    # For now, assume that server is a required parameter -- all queries should relate to the current server.
    if server == None:
        logger.info("Not implemented.")
        return

    if channel == None and user == None:
        values = [server]
        # Details for all channels and all users
        sql = """select sum(word_count) as word_count, sum(character_count) as character_count, max(max_message_length) as max_message 
            from usage_messages where server = ?"""

    elif channel == None and user != None:
        values = [server, user]
        # Details for a user on all channels
        sql = """select sum(word_count) as word_count, sum(character_count) as character_count, max(max_message_length) as max_message, max(last_message_timestamp) as last_message 
            from usage_messages 
            where server = ? and user = ?"""

    if channel != None and user == None:
        values = [server, channel]
        # Details for all commands from all users in a channel
        sql = """select sum(word_count) as word_count, sum(character_count) as character_count, max(max_message_length) as max_message, max(last_message_timestamp) as last_message 
            from usage_messages 
            where server = ? and user = ?"""

    elif channel != None and user != None:
        # Details for a user on a channel
        values = [server, channel, user]
        sql = """select sum(word_count) as word_count, sum(character_count) as character_count, max(max_message_length) as max_message, max(last_message_timestamp) as last_message 
            from usage_messages 
            where server = ? and channel = ? and user = ?"""

    elif channel != None and user == None:
        sql = 'select user, sum(count) as command_calls from usage_messages'
        values = []
        
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # logger.debug("SQL = {0}".format(sql))
    # logger.debug("values = {0}".format(values))
    cur.execute(sql, values)
    columns = [i[0] for i in cur.description]
    logger.debug('|{0}|'.format('\t\t\t|'.join(columns)))
    for row in cur:
        rowStr = '|'
        for col in columns:
            rowStr += ("{0}\t\t\t|".format(row[col]))
        logger.debug(rowStr)

# Create table
#c.execute('''CREATE TABLE stocks
#             (date text, trans text, symbol text, qty real, price real)''')


#t = ('RHAT',)
#c.execute('SELECT * FROM stocks WHERE symbol=?', t)
#print(c.fetchone())

# Larger example that inserts many records at a time
# purchases = [('2006-03-28', 'BUY', 'IBM', 1000, 45.00),
#              ('2006-04-05', 'BUY', 'MSFT', 1000, 72.00),
#              ('2006-04-06', 'SELL', 'IBM', 500, 53.00),
#             ]
#c.executemany('INSERT INTO stocks VALUES (?,?,?,?,?)', purchases)
#conn.commit
if __name__ == '__main__':
    # Setup logging
    logger = logging.getLogger('abbot')
    logger.setLevel(logging.DEBUG)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s %(name)-8s %(levelname)9s: %(message)s')
    ch.setFormatter(formatter)

    # add the handlers to logger
    logger.addHandler(ch)

    channels = ['main', 'other', 'another']
    users = ['foo', 'bar', 'username', 'blahblah']
    commands = ['help', 'joke', 'roll', 'pick', 'choose', 'rpsls', 'ping', 'whoami']
    serverName = 'servername'

    insertUpdateUsageCommand(users[random.randint(0, len(users)-1)], serverName, channels[random.randint(0, len(channels)-1)], commands[random.randint(0, len(commands)-1)], 1)
    insertUpdateUsageCommand(users[random.randint(0, len(users)-1)], serverName, channels[random.randint(0, len(channels)-1)], commands[random.randint(0, len(commands)-1)], 1)
    message = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase + string.whitespace + string.punctuation, k=random.randint(4, 1024)))
    insertUpdateUsageMessage(users[random.randint(0, len(users)-1)], serverName, channels[random.randint(0, len(channels)-1)], message)
    message = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase + string.whitespace + string.punctuation, k=random.randint(4, 1024)))
    insertUpdateUsageMessage(users[random.randint(0, len(users)-1)], serverName, channels[random.randint(0, len(channels)-1)], message)

    logger.debug("================================================================")
    logger.debug("Command Usage: All Servers, All Channels, All Users, No Breakdown")
    logger.debug("================================================================")
    summarizeCommandUsage(None, None, None, False)
    logger.debug("================================================================")
    logger.debug("Command Usage: One Server, All Channels, All Users, No Breakdown")
    logger.debug("================================================================")
    summarizeCommandUsage(serverName, None, None, False)
    logger.debug("================================================================")
    logger.debug("Command Usage: One Server, All Channels, All Users, With Breakdown")
    logger.debug("================================================================")
    summarizeCommandUsage(serverName, None, None, True)
    logger.debug("================================================================")
    logger.debug("Command Usage: One Server, All Channels, One User, No Breakdown")
    logger.debug("================================================================")
    summarizeCommandUsage(serverName, None, users[random.randint(0, len(users)-1)], False)
    logger.debug("================================================================")
    logger.debug("Command Usage: One Server, All Channels, One User, With Breakdown")
    logger.debug("================================================================")
    summarizeCommandUsage(serverName, None, users[random.randint(0, len(users)-1)], True)

    logger.debug("================================================================")
    logger.debug("Message Usage: All Servers, All Channels, All Users")
    logger.debug("================================================================")
    summarizeMessageUsage(None, None, None)
    logger.debug("================================================================")
    logger.debug("Message Usage: One Servers, All Channels, All Users")
    logger.debug("================================================================")
    summarizeMessageUsage(serverName, None, None)
    logger.debug("================================================================")
    logger.debug("Message Usage: One Servers, All Channels, One Users")
    logger.debug("================================================================")
    summarizeMessageUsage(serverName, None, users[random.randint(0, len(users)-1)])
    logger.debug("================================================================")
    logger.debug("Message Usage: One Servers, One Channels, One Users")
    logger.debug("================================================================")
    summarizeMessageUsage(serverName, channels[random.randint(0, len(channels)-1)], users[random.randint(0, len(users)-1)])
    
    # TODO: Detect/count emojis.
    # https://stackoverflow.com/questions/43146528/how-to-extract-all-the-emojis-from-text
    # a_list = ['🤔 🙈 me así, bla es se 😌 ds 💕👭👙 👨‍👩‍👦‍👦']
    #re.findall(r'[^\w\s,]', a_list[0])
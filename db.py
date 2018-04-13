import sqlite3
import datetime
import random
import string

DATABASE_NAME = 'abbot.sqlite3'

def insertUpdateUsageCommand(user, server, channel, commandName, valid):
    """ This function is used to insert or update the usage of a command into the database for a user."""
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    commandCount = 1
    values = ()
    sql = ""

    #print("insertUpdateCommand({0}, {1}, {2}, {3}, {4})".format(user, server, channel, commandName, valid))
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
        print("There was a problem inserting or updating the database record: {0}".format(ex))
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

    #print("insertUpdateUsageMessage({0}, {1}, {2}, {3})".format(user, server, channel, message))

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
        print("There was a problem inserting or updating the database record: {0}".format(ex))
    finally:
        conn.close()

# Create table
#c.execute('''CREATE TABLE stocks
#             (date text, trans text, symbol text, qty real, price real)''')


#t = ('RHAT',)
#c.execute('SELECT * FROM stocks WHERE symbol=?', t)
#print(c.fetchone())

# Larger example that inserts many records at a time
purchases = [('2006-03-28', 'BUY', 'IBM', 1000, 45.00),
             ('2006-04-05', 'BUY', 'MSFT', 1000, 72.00),
             ('2006-04-06', 'SELL', 'IBM', 500, 53.00),
            ]
#c.executemany('INSERT INTO stocks VALUES (?,?,?,?,?)', purchases)
#conn.commit
if __name__ == '__main__':
    conn = sqlite3.connect(DATABASE_NAME)

    c = conn.cursor()

    insertUpdateUsageCommand('username', 'servername', 'channelname', 'command', 1)
    insertUpdateUsageCommand('foo', 'servername', 'channelname', 'command', 1)
    message = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase + string.whitespace + string.punctuation, k=random.randint(4, 1024)))
    insertUpdateUsageMessage('username', 'servername', 'channelname', message)
    message = ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase + string.whitespace + string.punctuation, k=random.randint(4, 1024)))
    insertUpdateUsageMessage('foo', 'servername', 'channelname', message)

    print("Command usage:")
    headings = ('user', 'server', 'channel', 'command', 'valid', 'count')
    print(tuple(headings))
    for row in c.execute('SELECT * FROM usage_commands ORDER BY server, user, channel, command_name'):
        print(row)

    print("Message usage:")
    headings = ('user', 'server', 'channel', 'word_count', 'character_count', 'max_message_length', 'last_message_timestamp')
    print(tuple(headings))
    for row in c.execute('SELECT user, server, channel, word_count, character_count, max_message_length, last_message_timestamp FROM usage_messages ORDER BY server, user, channel, max_message_length'):
        print(row)


    # We can also close the connection if we are done with it.
    # Just be sure any changes have been committed or they will be lost.
    conn.close()
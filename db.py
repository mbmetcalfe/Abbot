import sqlite3
import datetime
import logging
logger = logging.getLogger('abbot')

from pathlib import Path

DATABASE_DDL = 'config/abbot.sqlite3.sql'

class AbbotDatabase:
    def __init__(self, databaseName):
        """
        Initialize a database.
        """
        self.databaseName = databaseName
        self.connection = None
        self.checkDB()

    def checkDB(self):
        """
        This method is used to check if the database exists.  For the database to exist,
        the database file must reside in the same folder as the scripts.
        If the database does not exist, then an attempt is made to create it with the
        supplied DDL file.
        """
        self.connection = None
        dbFile = Path(self.databaseName) # File should be in same directory as scripts.

        # if file does not exist, make an attempt at creating a blank database.
        if not dbFile.is_file():
            ddlFile = Path(DATABASE_DDL)

            # check that DDL file exists
            if not ddlFile.is_file():
                self.connection = None
                logger.error("Could not locate DDL file for the database.")
            else: # run the SQL script to create the database.
                try:
                    logger.debug("Trying to create database: {0}".format(self.databaseName))
                    ddl = open(DATABASE_DDL, 'r').read()
                    self.connection = sqlite3.connect(self.databaseName)
                    cur = self.connection.cursor()
                    cur.executescript(ddl)

                    logger.debug("Database {0} created.".format(self.databaseName))

                except Exception as ex:
                    self.connection = None
                    logger.error("Problem executing DDL: {0}".format(ex))
                finally:
                    cur.close()
                    self.connection.close()

            if not dbFile.is_file(): # one more check to be sure database was created correctly.
                self.connection = None
        else:
            logger.debug("Database file found.")
        
        # TODO: Do a connection test/query to ensure database is correct.
        self.connect()
        self.close()

    def connect(self):
        """
        Make a connection to the database.
        """
        try:
            self.connection = sqlite3.connect(self.databaseName)
            logger.debug("Database connected.")
            return True
        except BaseException as ex:
            logger.error("There was a problem connecting to the database: {0}".format(ex))
            self.connection = None
            return False

    def close(self):
        """
        Close the connection to the database.
        """
        try:
            self.connection.close()
            self.connection = None
            logger.debug("Database closed.")
            return True
        except BaseException as ex:
            logger.error("There was a problem closing the database: {0}".format(ex))
            self.connection = None
            return False


class Idea:
    def __init__(self, database, user, server, channel, idea):
        """
        Initialize the idea.
        """
        self.database = database
        self.user = user
        self.server = server
        self.channel = channel
        self.idea = idea
        self.ideaDate = datetime.datetime.now()

    def insert(self):
        """
        Insert an idea record.
        """
        insertSQL = "insert into ideas (user, server, channel, idea, idea_date) VALUES (?, ?, ?, ?, ?)"
        values = ()

        # Check that we have all the necessary data first.
        if self.database.connection == None:
            self.database.connect()

        if self.server == None and self.user == None and self.channel == None:
            logger.error("Must supply the user, server, and channel.")
            return False
        else:
            values = (self.user, self.server, self.channel, self.idea, self.ideaDate)

        try:
            cur = self.database.connection.cursor()
            cur.execute(insertSQL, values)

            # Save (commit) the changes
            self.database.connection.commit()
            cur.close()
            return True

        except BaseException as ex:
            logger.error("There was a problem inserting the ideas record: {0}".format(ex))
            return False

class BaseUsage:
    def __init__(self, database, user, server, channel):
        """
        Initialize the base usage class.
        """
        self.database = database
        self.server = server
        self.user = user
        self.channel = channel

class MessageUsage(BaseUsage):
    def __init__(self, database, user, server, channel):
        """
        Create a model for the message usage.
        """
        self.database = database
        self.server = server
        self.user = user
        self.channel = channel
        self.wordCount = 0
        self.characterCount = 0
        self.maxMessageLength = 0
        self.lastMessageTimestamp = None

        self.get(user, server, channel)
    
    def get(self, user, server, channel):
        """
        Get the message usage information for the specific user/server/channel.
        At least one of user, server, or channel must be supplied.
        """
        sql = """select user, 
            sum(word_count) as word_count, 
            sum(character_count) as character_count, 
            sum(max_message_length) as max_message_length, 
            max(last_message_timestamp) as last_message_timestamp 
            from usage_messages """
        if server == None and user == None and channel == None:
            logger.error("Must supply at least user, server, or channel.")
            return False
        else:
            # Build the where clause
            sql += "where "
            values = ()

            if user != None:
                sql += "user = ? "
                values += (user,)

            if server != None:
                sql += " and " if len(values) > 0 else ""
                sql += "server = ? "
                values += (server,)

            if channel != None:
                sql += " and " if len(values) > 0 else ""
                sql += "channel = ? "
                values += (channel,)

        # Add in the group by
        sql += "group by user "

        # TODO: Add ability to state which ranking user wants.
        # Add in the order by
        sql += "order by 3 desc, 4 desc" # 3 is the character count, 4 is the max message length
        if self.database != None:
            try:
                # Check that we have all the necessary data first.
                if self.database.connection == None:
                    self.database.connect()

                self.database.connection.row_factory = sqlite3.Row
                cur = self.database.connection.cursor()
                cur.execute(sql, values)
                row = cur.fetchone() # There "should" only be one record!
                if row != None:
                    self.wordCount = row['word_count']
                    self.characterCount = row['character_count']
                    self.maxMessageLength = row['max_message_length']
                    self.lastMessageTimestamp = row['last_message_timestamp']
                    logger.debug("{0} words; {1} characters; max message length {2} for server/channel/user: {3}/{4}/{5}.".format(
                        self.wordCount, self.characterCount, self.maxMessageLength,
                        self.server, self.channel, self.user))

                cur.close()
                return True

            except Exception as ex:
                logger.error("Problem getting message usage: {0}".format(ex))
                return False
        else:
            logger.error("No valid DB connection available.")
            return False
        
    def insert(self):
        """
        Insert a message usage record.  If the object does not have a user, server,
        and channel set the insert cannot be done.
        """
        insertSQL = "insert into usage_messages (user, server, channel, word_count, character_count, max_message_length, last_message_timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)"
        values = ()

        # Check that we have all the necessary data first.
        if self.database.connection == None:
            self.database.connect()

        if self.server == None and self.user == None and self.channel == None:
            logger.error("Must supply the user, server, and channel.")
            return False
        else:
            ts = datetime.datetime.now()
            values = (self.user, self.server, self.channel, self.wordCount, self.characterCount, self.maxMessageLength, ts.strftime("%Y-%m-%d %H:%M:%S:%f"))

        try:
            cur = self.database.connection.cursor()
            cur.execute(insertSQL, values)

            # Save (commit) the changes
            self.database.connection.commit()
            cur.close()
            return True

        except BaseException as ex:
            logger.error("There was a problem inserting the usage_messages record: {0}".format(ex))
            return False


    def update(self):
        """
        Update a message usage record.  If the object does not have a user, server,
        and channel set the update cannot be done.
        """
        updateSQL = "update usage_messages set word_count = ?, character_count = ?, max_message_length = ?, last_message_timestamp = ? where user = ? and server = ? and channel = ?"
        values = ()

        # Check that we have all the necessary data first.
        if self.database.connection == None:
            self.database.connect()

        if self.server == None and self.user == None and self.channel == None:
            logger.error("Must supply the user, server, and channel.")
            return False
        else:
            ts = datetime.datetime.now()
            values = (self.wordCount, self.characterCount, self.maxMessageLength, ts.strftime("%Y-%m-%d %H:%M:%S:%f"), self.user, self.server, self.channel)

        try:
            # self.database.connect()
            cur = self.database.connection.cursor()
            cur.execute(updateSQL, values)

            # Save (commit) the changes
            self.database.connection.commit()
            cur.close()
            return True

        except BaseException as ex:
            logger.error("There was a problem updating the usage_messages record: {0}".format(ex))
            return False

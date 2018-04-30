import sqlite3
import datetime
import logging
logger = logging.getLogger('abbot')

from pathlib import Path

DATABASE_DDL = 'config/abbot.sqlite3.sql'

class AbbotDatabase:
    """
    Abbot's Database class.  Used to keep track of the database name and connection.
    """
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
    """
    This class is used to represent an idea record in the database.
    """
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
    """
    The base class for usage information.
    """
    def __init__(self, database, user, server, channel):
        """
        Initialize the base usage class.
        """
        self.database = database
        self.server = server
        self.user = user
        self.channel = channel
        self.newRecord = True

class MessageUsage(BaseUsage):
    """
    This class represents a usage_messages record and can insert or update records.
    """
    def __init__(self, database, user, server, channel, fetch=True):
        """
        Create a model for the message usage.
        """
        BaseUsage.__init__(self, database, user, server, channel)
        self.wordCount = 0
        self.characterCount = 0
        self.maxMessageLength = 0
        self.lastMessageTimestamp = None

        if fetch:
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
                    self.newRecord = False
                else:
                    self.newRecord = True

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
        insertSQL = """
            insert into usage_messages (
                user, 
                server, 
                channel, 
                word_count, 
                character_count, 
                max_message_length, 
                last_message_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)"""
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
        updateSQL = """update usage_messages
            set word_count = ?, 
                character_count = ?, 
                max_message_length = ?, 
                last_message_timestamp = ? 
            where user = ? and 
            server = ? and 
            channel = ?"""
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

class ReactionUsage(BaseUsage):
    """
    This class represents a usage_reactions record and can insert or update records.
    """
    def __init__(self, database, user, server, channel, fetch=True):
        """
        Create a model for the reaction usage.
        """
        BaseUsage.__init__(self, database, user, server, channel)
        self.messagesReacted = 0
        self.userReacted = 0
        self.messageReactionsReceived = 0
        self.reactionsReceived = 0

        if fetch:
            self.get(user, server, channel)

    def get(self, user, server, channel):
        """
        Get the reaction usage information for the specific user/server/channel.
        At least one of user, server, or channel must be supplied.
        """
        sql = """select user, 
            sum(messages_reacted_count) as messages_reacted_count, 
            sum(user_reacted_count) as user_reacted_count, 
            sum(message_reactions_received_count) as message_reactions_received_count,
            sum(reactions_received_count) as reactions_received_count
            from usage_reactions """
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
        sql += "order by 2 desc, 4 desc" # 2 is the messages reacted count, 4 is the message reactions received count
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
                    self.messagesReacted = row['messages_reacted_count']
                    self.userReacted = row['user_reacted_count']
                    self.messageReactionsReceived = row['message_reactions_received_count']
                    self.reactionsReceived = row['reactions_received_count']
                    self.newRecord = False
                else:
                    self.newRecord = True

                cur.close()
                return True

            except Exception as ex:
                logger.error("Problem getting reaction usage: {0}".format(ex))
                return False
        else:
            logger.error("No valid DB connection available.")
            return False

    def insert(self):
        """
        Insert a reaction usage record.  If the object does not have a user, server,
        and channel set the insert cannot be done.
        """
        insertSQL = """
            insert into usage_reactions (
                user, 
                server, 
                channel, 
                messages_reacted_count, 
                user_reacted_count, 
                message_reactions_received_count, 
                reactions_received_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)"""
        values = ()

        # Check that we have all the necessary data first.
        if self.database.connection == None:
            self.database.connect()

        if self.server == None and self.user == None and self.channel == None:
            logger.error("Must supply the user, server, and channel.")
            return False
        else:
            values = (self.user, self.server, self.channel, self.messagesReacted, self.userReacted, self.messageReactionsReceived, self.reactionsReceived)

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
        Update a reaction usage record.  If the object does not have a user, server,
        and channel set the update cannot be done.
        """
        updateSQL = """update usage_reactions
            set messages_reacted_count = ?, 
                user_reacted_count = ?, 
                message_reactions_received_count = ?, 
                reactions_received_count = ? 
            where user = ? and 
            server = ? and 
            channel = ?"""
        values = ()

        # Check that we have all the necessary data first.
        if self.database.connection == None:
            self.database.connect()

        if self.server == None and self.user == None and self.channel == None:
            logger.error("Must supply the user, server, and channel.")
            return False
        else:
            values = (self.messagesReacted, self.userReacted, self.messageReactionsReceived, self.reactionsReceived, self.user, self.server, self.channel)

        try:
            # self.database.connect()
            cur = self.database.connection.cursor()
            cur.execute(updateSQL, values)

            # Save (commit) the changes
            self.database.connection.commit()
            cur.close()
            return True

        except BaseException as ex:
            logger.error("There was a problem updating the usage_reactions record: {0}".format(ex))
            return False

class UsageRank(BaseUsage):
    """
    This is the base class used to collect and report usage rankings.
    """
    def __init__(self, database, server, channel, maxRankings=5):
        """
        Initialize the rank usage class.
        """
        self.database = database
        self.server = server
        self.channel = channel
        self.maxRankings = maxRankings
        self.rankings = []

class MessageUsageRank(UsageRank):
    """
    This class is used to collect and report message usage rankings.
    """
    def __init__(self, database, server, channel, maxRankings=5):
        """
        Initialize the message rank usage class.
        """
        UsageRank.__init__(self, database, server, channel, maxRankings)
        self.rankings = []
        self.top = {"Most Words": {"User": None, "Size": 0}, "Most Characters": {"User": None, "Size": 0}, "Longest Message": {"User": None, "Size": 0}}

    def getRankingsByWordCount(self):
        """
        Get the word count ranking information for the specific user/server/channel.
        At least one of user, server, or channel must be supplied.
        """
        sql = """select user, 
            sum(word_count) as word_count 
            from usage_messages """
        if self.server == None and self.channel == None:
            logger.error("Must supply at least server, or channel.")
            return False
        else:
            # Build the where clause
            sql += "where "
            values = ()

            if self.server != None:
                sql += "server = ? "
                values += (self.server,)

            if self.channel != None:
                sql += " and " if len(values) > 0 else ""
                sql += "channel = ? "
                values += (self.channel,)

        # Add in the group by
        sql += "group by user "

        # Add in the order by
        sql += "order by 2 desc, user asc " # 2 is the word count
        # Add the limit
        sql += "limit ?"
        values += (self.maxRankings,)

        if self.database != None:
            try:
                # Check that we have all the necessary data first.
                if self.database.connection == None:
                    self.database.connect()

                self.database.connection.row_factory = sqlite3.Row
                cur = self.database.connection.cursor()
                cur.execute(sql, values)
                for row in cur:
                    messageUsage = MessageUsage(self.database, row['user'], self.server, self.channel, False)
                    messageUsage.wordCount = row['word_count']
                    # messageUsage.characterCount = row['character_count']
                    # messageUsage.maxMessageLength = row['max_message_length']
                    self.rankings.append(messageUsage)
                
                cur.close()
                return True

            except Exception as ex:
                logger.error("Problem getting message usage: {0}".format(ex))
                return False
        else:
            logger.error("No valid DB connection available.")
            return False

    def getRankingsByCharacterCount(self, user, server, channel):
        pass

    def getRankingsByLongestMessage(self, user, server, channel):
        pass
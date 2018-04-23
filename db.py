import sqlite3
import logging
logger = logging.getLogger('abbot')

from pathlib import Path

DATABASE_DDL = 'config/abbot.sqlite3.sql'

def checkDB(databaseName):
    """
    This function is used to check if the database exists.  For the database to exist,
    the database file must reside in the same folder as the scripts.
    If the database does not exist, then an attempt is made to create it with the
    supplied DDL file.
    If the database exists, this function returns True, otherwise, it returns False.
    """
    result = False
    dbFile = Path(databaseName) # File should be in same directory as scripts.

    # if file does not exist, make an attempt at creating a blank database.
    if not dbFile.is_file():
        ddlFile = Path(DATABASE_DDL)

        # check that DDL file exists
        if not ddlFile.is_file():
            result = False
            logger.error("Could not locate DDL file for the database.")
        else: # run the SQL script to create the database.
            try:
                logger.debug("Trying to create database: {0}".format(databaseName))
                ddl = open(DATABASE_DDL, 'r').read()
                conn = sqlite3.connect(databaseName)
                cur = conn.cursor()
                cur.executescript(ddl)
                result = True
            except Exception as ex:
                result = False
                logger.error("Problem executing DDL: {0}".format(ex))
            finally:
                cur.close()
                conn.close()

        result = dbFile.is_file() # one more check to be sure database was created correctly.
    else:
        result = True
    
    # TODO: Do a connection test/query to ensure database is correct.

    return result
#!/usr/local/bin/python3
import os
import sys
import subprocess
import logging
from os.path import getmtime

# Setup logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s: %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='/tmp/abbot_daemon.log',
                    filemode='w')
logger = logging.getLogger('abbot_daemon')
logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
ch = logging.StreamHandler()
#ch.setLevel(logging.ERROR)
ch.setLevel(logging.DEBUG)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s: %(message)s')
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(ch)

watchedFile = "/home/pi/test/abbot.py"
watchedFileMTime = getmtime(watchedFile)

logger.info('Starting ' + watchedFile)

abbotProcess = subprocess.Popen(watchedFile, shell=True)

while True:

    # Check whether a watched file has changed.
    if getmtime(watchedFile) != watchedFileMTime:
        # One of the files has changed, so restart the script.
        logger.info(watchedFile + ' has changed. restarting...')
        # Terminate existing process
        abbotProcess.terminate()
        abbotProcess.wait()
        # Save new watched time
        watchedFileMTime = getmtime(watchedFile)
        # Restart process
        abbotProcess = subprocess.Popen(watchedFile, shell=True)
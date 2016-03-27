#!/usr/bin/python
import RPi.GPIO as GPIO
import time
import os
import subprocess
import shlex 
import time
import sys, traceback
import logging
import logging.handlers
import subprocess

from ConfigParser import SafeConfigParser

###########################
# PERSONAL CONFIG FILE READ
###########################

parser = SafeConfigParser()
parser.read('androidautowake.ini')

# Read path to log file
LOG_FILENAME = parser.get('config', 'log_filename')

# monitoring period
SENSOR_PIN = parser.getint('config', 'sensor_pin')

# Read path to log file
DEVICE_ID = parser.get('config', 'device_id')

#################
#  LOGGING SETUP
#################
LOG_LEVEL = logging.INFO  # Could be e.g. "DEBUG" or "WARNING"

# Configure logging to log to a file, making a new file at midnight and keeping the last 3 day's data
# Give the logger a unique name (good practice)
logger = logging.getLogger(__name__)
# Set the log level to LOG_LEVEL
logger.setLevel(LOG_LEVEL)
# Make a handler that writes to a file, making a new file at midnight and keeping 3 backups
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="midnight", backupCount=3)
# Format each log message like this
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
# Attach the formatter to the handler
handler.setFormatter(formatter)
# Attach the handler to the logger
logger.addHandler(handler)

# Make a class we can use to capture stdout and sterr in the log
class MyLogger(object):
	def __init__(self, logger, level):
		"""Needs a logger and a logger level."""
		self.logger = logger
		self.level = level

	def write(self, message):
		# Only log if there is a message (not just a new line)
		if message.rstrip() != "":
			self.logger.log(self.level, message.rstrip())

# Replace stdout with logging to file at INFO level
sys.stdout = MyLogger(logger, logging.INFO)
# Replace stderr with logging to file at ERROR level
sys.stderr = MyLogger(logger, logging.ERROR)

logger.info('Starting Android auto-wake service')

GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN, GPIO.PUD_DOWN)

def run_command_and_get_output(command):
	process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
	return process.communicate()[0]

while(True):

	try:
		logger.info('Starting loop')

		if not GPIO.input(SENSOR_PIN):
			logger.info('Waiting for next detection...')
			GPIO.wait_for_edge(SENSOR_PIN, GPIO.RISING)
			logger.info("Sensor rising edge detected")

		if GPIO.input(SENSOR_PIN):
			logger.info("Turning on USB")
			os.system("./ykush -u 1")

			start = time.time()

			while True:
				check = run_command_and_get_output("./adb devices")
				if DEVICE_ID in check:
					break
			
			end = time.time()
			print(end - start)

			logger.info("sending adb key 82")
			os.system("./adb shell input keyevent 82")

			start = time.time()

			while True:
				time.sleep(1)
				check = run_command_and_get_output("./adb shell dumpsys power")
				if "mPowerState=0" in check:
					break

			end = time.time()
			print(end - start)

			logger.info("sending adb key 26")
			os.system("./adb shell input keyevent 26")
			
			logger.info("turning USB OFF")
			os.system("./ykush -d 1")

			# Turn USB power back on to save time at next detection, BUT not too early, otherwise
			# it will prevent the screen going to deep sleep.
			remainingSeconds = 30
			delay=1
			while remainingSeconds > 0:
				if GPIO.input(SENSOR_PIN):
					break
				time.sleep(delay)
				remainingSeconds = remainingSeconds - delay

			# No re-activation detected, and by now screen should have gone to deep sleep:
			# turn USB back on to speed-up adb communication upon next detection
			if remainingSeconds == 0:
				logger.info("turning USB back ON for next time")
				os.system("./ykush -u 1")
			else:
				logger.info("shutdown interrupted")

	except:
		logger.info("*****Exception in main loop, continuing in 60 seconds******")
		exc_type, exc_value, exc_traceback = sys.exc_info()
		traceback.print_exception(exc_type, exc_value, exc_traceback,limit=2, file=sys.stdout)	
		del exc_traceback
		time.sleep(60.0)
		continue


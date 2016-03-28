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

# Configure detection pin as an input, pulled-down when no active
GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN, GPIO.PUD_DOWN)

# Execute a shell command and get stdout traces
def run_command_and_get_output(command):
	process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
	return process.communicate()[0]

def wakeDevice(log=True):
	# Send simulated power button push (224 = "KEYCODE_WAKEUP")
	if log:
		logger.info("sending wake command ")
	os.system("./adb shell input keyevent 224")

def toggleDevicePower():
	# Send simulated power button push (26 = "KEYCODE_POWER" ) 
	logger.info("sending power off command")
	os.system("./adb shell input keyevent 26")

def powerOffUSBlink():
	# Power-off the USB port to simulate unplugging the cable
	logger.info("turning USB power OFF")
	os.system("./ykush -d 1")

def powerOnUSBlink():
	# Power-on the USB port
	logger.info("turning USB power ON")
	os.system("./ykush -u 1")

#############
#  MAIN LOOP
#############

while(True):

	try:
		logger.info('Starting loop')

		# Wait for next detection, but only if signal is not already high
		if not GPIO.input(SENSOR_PIN):
			logger.info('Waiting for next detection...')
			GPIO.wait_for_edge(SENSOR_PIN, GPIO.RISING)
			logger.info("Presence DETECTED!")

		# Check if signal is still high before proceeding: the rising edge might have been a glitch.
		if GPIO.input(SENSOR_PIN):
			
			powerOnUSBlink()

			# Poll until device is seen by adb
			while True:
				check = run_command_and_get_output("./adb devices")
				if DEVICE_ID in check:
					break
			
			wakeDevice()

			# Wait until device tries to go back to sleep
			nbRefresh = 0
			while True:
				time.sleep(1)
				check = run_command_and_get_output("./adb shell dumpsys power")
				if "mPowerState=0" in check:
					logger.info("device going back to sleep after " + str(nbRefresh) + " wake refresh cycles")
					break
				# If a new detection occurs, resend wake command to keep screen alive.
				# Just reading the instantaneous value is ok since I setup cooldown time such that 
				# signal stays high for about 2 seconds after each detection, and we loop 
				# every second
				elif GPIO.input(SENSOR_PIN):
					wakeDevice(False)
					nbRefresh = nbRefresh + 1

			powerOffUSBlink()

			# Turn USB power back on to save time at next detection, BUT not too early, otherwise
			# it will prevent the screen going to deep sleep. Since we also wait to be able to react
			# to a possible new detection during those 30 seconds, wait for a rising edge with a timeout
			# of 30 seconds
			
			# We reached the timeout, i.e. no new detection occurred
			if GPIO.wait_for_edge(SENSOR_PIN, GPIO.RISING, timeout=30000) is None:
				logger.info("wait before USB power on: completed")
				powerOnUSBlink()				
			# a new detection occurred: just loop back to the beginning to handle it.
			else:
				logger.info("wait before USB power on: interrupted")

	except:
		logger.info("*****Exception in main loop, continuing in 60 seconds******")
		exc_type, exc_value, exc_traceback = sys.exc_info()
		traceback.print_exception(exc_type, exc_value, exc_traceback,limit=2, file=sys.stdout)	
		del exc_traceback
		time.sleep(60.0)
		continue

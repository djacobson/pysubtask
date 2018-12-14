#
# Script: pysubtask.dropbox.py Module
#
# Author V1: David Jacobson (david@jacobsonhome.com)
# https://github.com/djacobson/pysubtask
#
# Dropbox:
#
# Create an app under your own dropbox account in the "App Console". (https://www.dropbox.com/developers/apps):
#
# 1. App Type as "Dropbox API APP".
# 2. Type of data access as "Files & Datastores"
# 3. Folder access as "My app needs access to files already on Dropbox". (ie: Permission Type as "Full Dropbox".)
# 4. Then click the "generate access token" (this will be entered into the app config)

import os
import dropbox

from . import defaults_config as defaults
from .base import BaseTaskMaster, BaseSubtask


class DropboxTaskMaster(BaseTaskMaster):

	dropboxlogger = None

	def __init__(
		self,
		WatchFiles,
		pconfig,
		LogFileName=defaults.dropbox.Master_Log_FileName,
		LogToConsole=True):

		# Fill in non-specified config items with defaults
		self.config = self.combine(pconfig, defaults.dropbox)

		super().__init__(
			WatchFiles,
			self.config,
			__name__,
			LogFileName,
			LogToConsole)

		self.dropboxlogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			LogToConsole)

		# Add specific args for Dropbox Client to SubProc args
		self._subtaskArgs += [
			'-dtoken', self.config.AccessToken,
			'-bakto', defaults.dropbox.BakToFolder
		]
		# Only add these args if they differ from default config
		if self.config.DeadTimeMilli != defaults.dropbox.DeadTimeMilli:
			self._subtaskArgs += ['-x', str(self.config.DeadTimeMilli)]

	def start(self, precleanup_old_files=False):
		if precleanup_old_files:
			# Pre-archive old data & pre-copy and upload previous residual data, then Start
			super().start(
				prearchive_expired_files_to_folder=defaults.base.ArchiveToFolder,
				precopy_files_to_folder=self.config.BakToFolder)
		else:
			# Just Start
			super().start()

	def stop(self):
		super().stop(defaults.dropbox.SubtaskDescription)


class DropboxSubtask(BaseSubtask):

	_Description = defaults.dropbox.SubtaskDescription
	dropboxlogger = None

	def __init__(
		self,
		args,
		LogFileName=defaults.dropbox.Subtask_Log_FileName):

		super().__init__(args, LogFileName)

		self.dropboxlogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			not args.noconsole)

		# User config settings
		self.Enabled = True  # False = Dropbox not used but Dropbox Subtask still spawned

		# Internal
		self._dropbox = None
		self._accessToken = args.dropbox_token
		self.DeadTimeMilli = args.dropbox_dead_time_milli

	def start(self):
		self.connect(True)  # connect before starting timers ( super().start() )
		super().start()

	def process_interval(self):
		if not self.Enabled:
			return

		# Dropbox Subtask Timer: called every interval.
		deadTime = self.dead_time()
		if deadTime and deadTime > self.DeadTimeMilli:
			if self.is_connected():
				self.dropboxlogger.info("'DEAD' for [{}] secs! (no data) REST'ing Dropbox!".format(
					self.DeadTimeMilli / 1000))
				self.disconnect()

	def process_notify(self, psWatchFile):
		if not self.Enabled:
			return

		# Dropbox Subtask Notified!: New data ready
		if not self.is_connected():
			self.connect()

		if not self.upload_file(psWatchFile):
			if self._SubtaskStopNow:
				return
			self.dropboxlogger.error("Upload, attempting reconnect.")

			# Attempt reconnect loop process ONCE
			if not self.is_connected():
				self.connect()
				if not self.is_connected():
					self.ftplogger.error("Upload FAIL'ed to reconnect!")
					return
				else:
					# Successfully reconnected!
					# Try to upload one more time
					if self._SubtaskStopNow:
						return
					self.upload_file(psWatchFile)

	def connect(self, uploadAllFilesFirst=False):
		# Cycle infinitely until connected

		# make sure BaseSubtask timer is STOP'ed until connected
		self._IgnoreTimer = True

		num_retries = 5
		short_wait = 3  # secs
		long_wait = 30  # secs
		connectSuccess = False

		while not connectSuccess and not self._SubtaskStopNow:
			for i in range(num_retries):
				if self._SubtaskStopNow:
					break

				connectSuccess = self.connect_once()

				if connectSuccess:
					break
				else:
					self.dropboxlogger.error("CONNECT attempt FAILED! Try # [{}] of [{}] retries".format(
						i + 1, num_retries))
					if (i + 1) < num_retries:
						self.dropboxlogger.info("Waiting [{}] secs before next try...".format(short_wait))
						self.sleep(short_wait)

			if not connectSuccess:
				self.dropboxlogger.error("Repeated CONNECT FAILURE!")
				self.dropboxlogger.info("LONGER Wait [{}] secs before next try...".format(long_wait))
				self.sleep(long_wait)

		if connectSuccess and not self._SubtaskStopNow:
			if uploadAllFilesFirst:
				self.upload_all_in_dir(self._bakToFullPath)

		self._IgnoreTimer = False

	def connect_once(self):
		if self.is_connected():
			self.disconnect()

		self.dropboxlogger.info("CONNECT! Access Token [{}]".format(
			'************************'))
		# 	self._accessToken))

		return self.connectDropbox()

	def connectDropbox(self):
		self._dropbox = dropbox.Dropbox(self._accessToken)
		# Check that the access token is valid
		try:
			self._dropbox.users_get_current_account()
		except dropbox.AuthError as err:
			self.dropboxlogger.error('Invalid access token: [{}]'.format(err))
			self._dropbox = None
			return False

		return True

	def is_connected(self):
		if self._dropbox:
			return True
		else:
			return False

	def disconnect(self):
		if self._dropbox:
			self.dropboxlogger.info("Dropbox DISCONNECT!")
			try:
				self._dropbox.close()
			except Exception as e:
				pass
			self._dropbox = None

	def stop(self):
		super().stop()
		# Upload all files one final time
		if self.is_connected():
			self.upload_all_in_dir(self._bakToFullPath)
		self.disconnect()

	def upload_file(self, upFile):
		# Check if upFile exists first
		if not os.path.exists(upFile):
			self.dropboxlogger.error("Upload file [{}] does not exist!".format(upFile))
			return False

		# Check if we need to reconnect
		if not self.is_connected():
			self.connect()
			if not self.is_connected():
				return False

		upname = os.path.basename(upFile)

		if self._dropbox:
			try:
				self.upload_file_dropbox(
					upFile,
					"/" + upname,
					True)
			except Exception as e:
				self.dropboxlogger.error("Upload Data File: [{}]".format(e))
				self.disconnect()
				return False
			else:
				# self.dropboxlogger.info("Upload Data File: [{}]".format(upname))
				return True

	def upload_file_dropbox(self, file_from, file_to, overwrite=False):
		"""upload a file to Dropbox using API v2
		"""
		# https://github.com/dropbox/dropbox-sdk-python/blob/master/example/updown.py

		if not self._dropbox:
			self.dropboxlogger.error('download_file(): No Dropbox object initialized!')
			return False

		mode = (dropbox.files.WriteMode.overwrite if overwrite else dropbox.files.WriteMode.add)
		# mtime = os.path.getmtime(file_from)
		with open(file_from, 'rb') as f:
			try:
				res = self._dropbox.files_upload(
					f.read(),
					file_to,
					mode,
					# client_modified=datetime.datetime(*time.gmtime(mtime)[:6]),
					mute=True)
			except dropbox.exceptions.ApiError as err:
				self.dropboxlogger.error('Dropbox API error:', err)
				return False

		self.dropboxlogger.info("Uploaded as [{}]".format(
			res.name.encode('utf8')))
		return True

	def upload_all_in_dir(self, upDir):
		if not upDir or not os.path.exists(upDir):
			return
		self.dropboxlogger.info("Uploading ALL files in [{}]...".format(upDir))

		allFiles = [f for f in os.listdir(upDir) if os.path.isfile(os.path.join(upDir, f))]
		for bakFile in allFiles:
			self.upload_file(os.path.join(upDir, bakFile))

	def parse_args_init(self, psDescription):
		parser = BaseSubtask.parse_args_init(None, psDescription)

		# Add specific args for Dropbox Client to SubProc args
		parser.add_argument(
			'-dtoken', '--dtoken',
			required=True,
			dest='dropbox_token',
			help='Dropbox API access token')

		parser.add_argument(
			'-x', '--dead-time', '--expired-time',
			dest='dropbox_dead_time_milli',
			default=defaults.dropbox.DeadTimeMilli,
			type=int,
			help="Elapsed 'dead' time in milliseconds with NO Data before rest'ing Dropbox")

		return parser


def spawn_subtask():
	parser = DropboxSubtask.parse_args_init(None, DropboxSubtask._Description)
	subtask = DropboxSubtask(parser.parse_args())
	subtask.dropboxlogger.info("***** HELLO!: [{}] *****".format(subtask._Description))
	subtask.start()


def main():
	spawn_subtask()


if __name__ == "__main__":
	main()

#
# Script: pysubtask.base.py Module
#
# Author V1: David Jacobson (david@jacobsonhome.com)

import sys
import os
import shutil
import glob
import signal
import subprocess
import argparse
from datetime import datetime, date, timedelta
import time
import base64
import logging

from . import defaults_config as defaults
from .InfiniteTimer import InfiniteTimer

ON_WINDOWS = (sys.platform == 'win32')
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008

if ON_WINDOWS:
	_SIGNAL_STOP_subtask = signal.SIGBREAK
else:
	_SIGNAL_STOP_subtask = signal.SIGTERM
_SIGNAL_STOP_subtask_INTERACTIVELY = signal.SIGINT  # CTRL+C


class BaseTaskMaster():

	baselogger = None

	def __init__(
		self,
		WatchFiles,
		pconfig,
		SubtaskModuleName=__name__,
		LogFileName=defaults.base.Master_Log_FileName,
		LogToConsole=True):

		# Fill in non-specified config items with defaults
		self.config = self.combine(pconfig, defaults.base)

		self.baselogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			LogToConsole)

		# Covert WatchFiles List to argument
		self._watch_files = []
		self._watch_files_state = []
		for wfile in WatchFiles:
			self._watch_files.append(wfile['file'])
			wfile_state = {
				'prev_notify_dt': None,
				'pending_data_dt': None,
				'burst_mode': None
			}

			if wfile['burstmode']:
				wfile_burst_mode = {
					'start_dt': None,
					'count': 0,
					'start_trigger_milli': defaults.burst_mode.start_trigger_milli,
					'start_trigger_count': defaults.burst_mode.start_trigger_count,
					'expire_milli': defaults.burst_mode.expire_milli
				}
				wfile_state['burst_mode'] = wfile_burst_mode

			self._watch_files_state.append(wfile_state)

		wfiles_arg = '"{}"'.format(','.join(map(str, self._watch_files)))

		PythonName = sys.executable

		# Add specific args for base SubProc
		self._subtaskArgs = [
			PythonName,
			'-m',
			SubtaskModuleName,
			'-w', wfiles_arg
		]
		if not LogToConsole:
			self._subtaskArgs += ['-noconsole']
		# Only add these args if they differ from default config
		if self.config.TimerIntervalSecs != defaults.base.TimerIntervalSecs:
			self._subtaskArgs += ['-i', str(self.config.TimerIntervalSecs)]

		self._subtask = None

	def combine(self, master_dict, add_this_dict):
		new_dict = master_dict
		for key, value in add_this_dict.__dict__.items():
			if key not in master_dict.__dict__:
				new_dict.__dict__[key] = value
		return new_dict

	def start(self, prearchive_expired_files_to_folder=None, precopy_files_to_folder=None):
		if prearchive_expired_files_to_folder:
			# First, prearchive expired files (all files types in log dir)
			self.archive_expired_files(prearchive_expired_files_to_folder)
		if precopy_files_to_folder:
			# Second, precopy old / residual data files types (for preuplaod, etc.)
			self.copy_all_file_types(precopy_files_to_folder)
		self.cleanup_notify_files_all()
		self.baselogger.info('START!')
		self.spawn_subtask()

	def reset(self):
		self.baselogger.info("RESET: BaseTaskMaster and BaseSubtask (Timer)!")
		self.stop()
		self.start()

	def spawn_subtask(self):
		kwargs = {}
		if ON_WINDOWS:
			kwargs['creationflags'] = CREATE_NEW_PROCESS_GROUP
			# kwargs['creationflags'] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

		self._subtask = subprocess.Popen(self._subtaskArgs, **kwargs)

		self.baselogger.info("BaseTaskMaster PID = [{}] BaseSubtask PID = [{}]".format(
			os.getpid(),
			self._subtask.pid))

	def stop(self, subtaskDescription=defaults.base.SubtaskDescription):
		if self._subtask:
			self.baselogger.info("STOP!: BaseTaskMaster attempting to stop BaseSubtask [{}]...".format(
				self._subtask.pid))
			if ON_WINDOWS:
				self._subtask.send_signal(signal.CTRL_BREAK_EVENT)
			else:
				self._subtask.terminate()
			self._subtask.wait()
		self.cleanup_notify_files_all()
		self.baselogger.info("***** GOODBYE!: [{}] *****".format(subtaskDescription))

	def cleanup_notify_files(self):
		for wfile in self._watch_files:
			nfile = '{}.notify'.format(wfile)
			if os.path.exists(nfile):
				self.baselogger.info("Cleaning up [{}]".format(nfile))
				os.remove(nfile)

	def cleanup_notify_files_all(self):
		if not self._watch_files or len(self._watch_files) < 1:
			return
		watchFolder = os.path.dirname(self._watch_files[0])
		if not os.path.exists(watchFolder):
			return

		allFiles = [f for f in os.listdir(watchFolder) if os.path.isfile(os.path.join(watchFolder, f))]
		for watchNotifyFile in allFiles:
			if watchNotifyFile.endswith('.notify'):
				nfile = os.path.join(watchFolder, watchNotifyFile)
				self.baselogger.info("Cleaning up [{}]".format(nfile))
				os.remove(nfile)

	def copy_all_file_types(self, relativeToFolder):
		# Copy all files in watch list with same .ext to specified folder (i.e.: BakTo folder).
		# Typically used to grab missed / residual data before start()
		if not self._watch_files or len(self._watch_files) < 1:
			return
		watchFolder = os.path.dirname(self._watch_files[0])
		if not os.path.exists(watchFolder):
			return
		fullToFolder = os.path.join(watchFolder, relativeToFolder)

		# get file extensions
		fextensions = []
		for notify_index, wfile in enumerate(self._watch_files):
			fname, fext = os.path.splitext(wfile)
			if fext not in fextensions:
				fextensions.append(fext)

		self.baselogger.info("PreCopy ALL [{}] data from [{}] to [{}]".format(
			",".join(fextensions),
			watchFolder,
			fullToFolder))

		for file_ext in fextensions:
			file_pattern = '*' + file_ext
			self.copy_pattern_from_to(file_pattern, watchFolder, fullToFolder)

	def archive_expired_files(self, relativeToFolder):
		days_old = defaults.base.ArchiveAfterDaysOld
		move_date = date.today() - timedelta(days=days_old)
		move_date = time.mktime(move_date.timetuple())

		# Archive all expired files to specified folder (i.e.: logs/archive folder).
		if not self._watch_files or len(self._watch_files) < 1:
			return
		watchFolder = os.path.dirname(self._watch_files[0])
		if not os.path.exists(watchFolder):
			return
		fullToFolder = os.path.join(watchFolder, relativeToFolder)

		self.baselogger.info("Archiving expired files from [{}] to [{}]".format(
			watchFolder,
			fullToFolder))

		arch_files_found = False

		for file in os.listdir(watchFolder):
			fullfile = os.path.join(watchFolder, file)
			if os.path.isfile(fullfile):
				filetime = os.stat(fullfile).st_mtime
				if filetime < move_date:
					arch_files_found = True

					# Build archive path and file name
					fdate = datetime.fromtimestamp(filetime)
					archpath = '{}{:02d}'.format(fdate.year, fdate.month)
					archpath = os.path.join(archpath, '{:02d}'.format(fdate.day))
					archpath = os.path.join(fullToFolder, archpath)
					archfullfile = os.path.join(archpath, file)
					if not os.path.exists(archpath):
						os.makedirs(archpath)
					else:
						archfullfile = self.getAvailableFileName(archfullfile)

					# Archive file
					self.baselogger.info("Archiving [{}]".format(archfullfile))
					shutil.copy2(fullfile, archfullfile)
					os.remove(fullfile)

		if not arch_files_found:
			self.baselogger.info("No expired files found to Archive")

	def getAvailableFileName(self, pfname):
		if os.path.exists(pfname):
			filename, file_extension = os.path.splitext(pfname)
			i = 1
			while True:
				nfname = "{}_{}{}".format(filename, i, file_extension)
				if not os.path.exists(nfname):
					return nfname
				i += 1
		else:
			return pfname

	def copy_pattern_from_to(self, fpattern, source_dir, dest_dir):
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)

		files = glob.iglob(os.path.join(source_dir, fpattern))
		for file in files:
			if os.path.isfile(file):
				shutil.copy2(file, dest_dir)

	def notify_all(self):
		for notify_index, wfile in enumerate(self._watch_files):
			self.notify_by_index(notify_index, True)

	def notify_by_index(self, notify_index, ignore_burst_mode=False):
		if notify_index < 0 or notify_index >= len(self._watch_files):
			self.baselogger.error("Notify file index [{}] out of range!".format(notify_index))
			return

		wfile = self._watch_files[notify_index]
		wfile_state = self._watch_files_state[notify_index]

		curr_notify_dt = datetime.now()
		if not ignore_burst_mode and wfile_state['burst_mode']:
			wfile_state['pending_data_dt'] = self.notify_by_index_burst_mode(notify_index)
		else:
			self.notify_file(wfile)
		wfile_state['prev_notify_dt'] = curr_notify_dt

	def notify_by_index_burst_mode(self, notify_index):
		curr_notify_dt = datetime.now()
		wfile = self._watch_files[notify_index]
		wfile_state = self._watch_files_state[notify_index]
		burst_mode = wfile_state['burst_mode']

		return_pending_dt = None

		# Read-only props
		prev_notify_dt = wfile_state['prev_notify_dt']
		burst_expire_milli = burst_mode['expire_milli']
		burst_start_trigger_milli = burst_mode['start_trigger_milli']
		burst_start_trigger_count = burst_mode['start_trigger_count']

		# Updated props are:
		# burst_mode['start_dt']
		# burst_mode['count']

		if prev_notify_dt:
			notify_delta_milli = timedelta_milliseconds(curr_notify_dt - prev_notify_dt)
			# Q: Have we already started a Burst buffering mode?
			if burst_mode['start_dt']:
				# Y: Burst mode already started

				# Q: Has our Burst window expired (regardless of whther we're still bursting)?
				if timedelta_milliseconds(curr_notify_dt - burst_mode['start_dt']) >= burst_expire_milli:
					# Y: Burst buffer expired. Time to release it / notify.
					self.baselogger.info("Burst (previous) expired. Notifying! [{}]".format(
						burst_expire_milli))
					self.notify_file(wfile)
					burst_mode['start_dt'] = None
					burst_mode['count'] = 0
				else:
					# Q: Are we still bursting inside the Burst window?
					if notify_delta_milli < burst_start_trigger_milli:
						# Y: Still Bursting.
						return_pending_dt =	\
							burst_mode['start_dt'] + \
							timedelta(milliseconds=burst_expire_milli)
						burst_mode['count'] += 1
						# self.baselogger.info("Still Bursting! [{}]".format(burst_mode['count']))
					else:
						# N: Release it / notify it.
						self.baselogger.info("Burst (existing) ended. Notifying! [{}] elapsed.".format(
							notify_delta_milli))
						self.notify_file(wfile)
						burst_mode['start_dt'] = None
						burst_mode['count'] = 0
			else:
				# N: Not in Burst mode (yet...)

				# Q: Do we need to start a new Burst?
				if notify_delta_milli < burst_start_trigger_milli:
					# Q: Have we reached Burst detection count requirment yet?
					if burst_mode['count'] < (burst_start_trigger_count - 1):
						# N: Burst detected but waiting for n time in a row
						# Return a short expiration until count reached
						return_pending_dt =	\
							prev_notify_dt + \
							timedelta(milliseconds=burst_start_trigger_milli)
						self.baselogger.info("Burst detected *BUT* waiting for [{}] in a row.".format(
							burst_start_trigger_count))
					else:
						# Y: Detected a Burst! Start a new Burst window.
						# Return regular Burst expiration time
						burst_mode['start_dt'] = prev_notify_dt
						return_pending_dt =	\
							burst_mode['start_dt'] + \
							timedelta(milliseconds=burst_expire_milli)
						self.baselogger.info("Burst detected. Starting Burst mode!")
					burst_mode['count'] += 1
				else:
					# N: Data coming in slow enough... just release it / notify immediately.
					self.baselogger.info("Regular rate (not a Burst). Notifying! [{}]".format(
						notify_delta_milli))
					self.notify_file(wfile)
					burst_mode['count'] = 0
		else:
			self.baselogger.info("Initial notify (Burst mode)")
			self.notify_file(wfile)

		return return_pending_dt

	def notify_file(self, wfile):
		nfile = '{}.notify'.format(wfile)
		self.touch(nfile)

	def check_pending_notifications(self):
		# Check for pending data from ending on a Burst
		now_dt = datetime.now()
		for notify_index, wfile in enumerate(self._watch_files):
			wfile_state = self._watch_files_state[notify_index]
			pending_data_dt = wfile_state['pending_data_dt']
			if pending_data_dt:
				if pending_data_dt <= now_dt:
					self.baselogger.info('Pending AND expired data detected. Notifying!')
					self.notify_file(wfile)
					wfile_state['pending_data_dt'] = None  # Clear pending flag
				else:
					self.baselogger.info('Pending data detected. *BUT*, has NOT expired yet. [{}] secs to go.'.format(
						pending_data_dt - now_dt))
			else:
				# self.baselogger.info('No pending data to release / notify.')
				pass

	def touch(self, fname, mode=0o666, dir_fd=None, **kwargs):
		# https://stackoverflow.com/questions/1158076/implement-touch-using-python
		flags = os.O_CREAT | os.O_APPEND
		with os.fdopen(os.open(fname, flags=flags, mode=mode, dir_fd=dir_fd)) as f:
			os.utime(
				f.fileno() if os.utime in os.supports_fd else fname,
				dir_fd=None if os.supports_fd else dir_fd, **kwargs)

	def encode(self, key, clear):
		# https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
		enc = []
		for i in range(len(clear)):
			key_c = key[i % len(key)]
			enc_c = chr((ord(clear[i]) + ord(key_c)) % 256)
			enc.append(enc_c)
		return base64.urlsafe_b64encode("".join(enc).encode()).decode()

	def setup_logging(self, cname, lfname, LogToConsole=True):
		return setup_logging(cname, lfname, LogToConsole)


class BaseSubtask():

	_Description = defaults.base.SubtaskDescription
	baselogger = None

	def __init__(
		self,
		args,
		LogFileName=defaults.base.Subtask_Log_FileName):

		self.baselogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			not args.noconsole)

		self._TimerIntervalSecs = args.interval_secs  # secs

		watch_files = args.watch_files[1:-1]  # dequote
		watch_files_list = watch_files.split(',')
		self._watch_files = watch_files_list
		self._notify_files = None
		self._bakToFolder = args.bak_to_folder
		self._bakToFullPath = None
		self.init_files()

		self._Timer = None
		self._SubtaskStopNow = False
		self._IgnoreTimer = False

		self._last_notify_dt = datetime.now()  # Start of app is first notify dt

		signal.signal(
			_SIGNAL_STOP_subtask,
			lambda signal_number, current_stack_frame: self.stop())

		signal.signal(
			_SIGNAL_STOP_subtask_INTERACTIVELY,
			lambda signal_number, current_stack_frame: self.stop())

	def __del__(self):
		self.stop()

	def init_files(self):
		# Derive notify files list
		# remove any residuals
		self._notify_files = []
		cached_notify_stamp = 0
		for wfile in self._watch_files:
			nfile = '{}.notify'.format(wfile)
			self._notify_files.append((nfile, cached_notify_stamp))
			if os.path.exists(nfile):
				os.remove(nfile)

		# Create bakTo folder if it does not exist
		self._bakToFullPath = self._bakToFolder
		if self._bakToFolder:
			watchFolder = os.path.dirname(self._watch_files[0])

			if watchFolder and len(watchFolder) > 0:
				bakFilePath = os.path.join(watchFolder, self._bakToFolder)
			else:
				bakFilePath = self._bakToFolder
			if not os.path.exists(bakFilePath):
				os.makedirs(bakFilePath)
			self._bakToFullPath = bakFilePath

	def start(self):
		self.baselogger.info("START! Polling every [{}] secs".format(self._TimerIntervalSecs))

		self._Timer = InfiniteTimer(
			self._TimerIntervalSecs,
			self._process)
		self._Timer.start()

	def _process(self):
		# Not meant to be Overridden.
		if self._IgnoreTimer:
			return
		self._process_interval()
		if self._SubtaskStopNow:
			return

		i = 0
		for (nfile, cached_notify_stamp) in self._notify_files:
			if self._SubtaskStopNow:
				return
			if os.path.exists(nfile):
				stamp = os.stat(nfile).st_mtime
				if stamp != cached_notify_stamp:
					# Replace notify file tuple stamp
					self._notify_files[i] = (nfile, stamp)
					# File has changed, so do something...
					wfile = nfile.strip('.notify')
					self._process_notify(wfile)
			i += 1

	def _process_interval(self):
		if self._SubtaskStopNow:
			return
		self.process_interval()

	def process_interval(self):
		# Override
		self.baselogger.info("Subtask Timer: do something every interval.")

	def _process_notify(self, psWatchFile):
		upFile = psWatchFile
		if not os.path.exists(upFile):
			self.baselogger.error("File [{}] notified but does not exist!".format(upFile))
			return

		if self._SubtaskStopNow:
			return
		self._last_notify_dt = datetime.now()

		# If bakTo folder specified, copy file to it and
		# use the copy as the upload file
		if self._bakToFullPath:
			upFile = self.copy_file_to_dir(upFile, self._bakToFullPath)  # returns new copied file name
		if self._SubtaskStopNow or not upFile:
			return

		self.process_notify(upFile)

	def process_notify(self, psWatchFile):
		# Override
		self.baselogger.info("Subtask Notified!: File [{}] changed.".format(psWatchFile))

	def dead_time(self):
		# Return millisecs since last notification
		if not self._last_notify_dt:
			return None
		else:
			return timedelta_milliseconds(datetime.now() - self._last_notify_dt)

	def stop(self):
		self._SubtaskStopNow = True
		if self._Timer:
			self.baselogger.info("STOP!")
			self._Timer.stop()
			self._Timer = None

	def sleep(self, seconds):
		# Politely sleep
		if self._SubtaskStopNow:
			return

		if seconds > 1:
			for i in range(seconds):
				if self._SubtaskStopNow:
					return
				time.sleep(1)
		else:
			if self._SubtaskStopNow:
				return
			time.sleep(seconds)

	def copy_file_to_dir(self, fromFile, toDir):
		if not os.path.exists(fromFile):
			self.baselogger.error("File [{}] does not exist to copy [{}]".format(fromFile))
			return None

		fileBaseName = os.path.basename(fromFile)
		if not os.path.exists(toDir):
			os.makedirs(toDir)
		toFileName = os.path.join(toDir, fileBaseName)
		self.baselogger.info("Copying [{}] to [{}]".format(fromFile, toDir))

		shutil.copy2(fromFile, toDir)

		return toFileName

	def decode(self, key, enc):
		# https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
		dec = []
		enc = base64.urlsafe_b64decode(enc).decode()
		for i in range(len(enc)):
			key_c = key[i % len(key)]
			dec_c = chr((256 + ord(enc[i]) - ord(key_c)) % 256)
			dec.append(dec_c)
		return "".join(dec)

	def parse_args_init(self, psDescription):
		parser = argparse.ArgumentParser(description=psDescription)

		parser.add_argument(
			'-w', '--watch-file-list',
			required=True,
			dest='watch_files',
			help='Delimited list of file paths+names to watch and upload')

		parser.add_argument(
			'-i', '--interval-secs',
			dest='interval_secs',
			default=defaults.base.TimerIntervalSecs,
			type=int,
			help='Timer interval in seconds')

		parser.add_argument(
			'-bakto', '--bak-to-folder',
			dest='bak_to_folder',
			default=defaults.base.BakToFolder,
			help='Folder where to copy notified files to')

		parser.add_argument(
			'-noconsole', '--noconsole',
			dest='noconsole',
			action='store_true',
			default=False,
			help='If specified, do not log to the console')

		return parser

	def setup_logging(self, cname, lfname, LogToConsole=True):
		return setup_logging(cname, lfname, LogToConsole)


def timedelta_milliseconds(td):
	return td.days * 86400000 + td.seconds * 1000 + td.microseconds / 1000


def setup_logging(cname, lfname, LogToConsole=True):
	# 'application' code
	# logger.debug('debug message')
	# logger.info('info message')
	# logger.warn('warn message')
	# logger.error('error message')
	# logger.critical('critical message')

	_logger = logging.getLogger(cname)
	_logger.setLevel(logging.DEBUG)

	# create formatter
	logFormat = '%(asctime)s.%(msecs)03d [%(module)s.%(name)s]: %(levelname)s: %(message)s'
	formatter = logging.Formatter(logFormat, datefmt="%Y-%m-%d %H:%M:%S")

	if LogToConsole:
		# create console handler and set level to debug
		ch = logging.StreamHandler()
		ch.setLevel(logging.DEBUG)
		ch.setFormatter(formatter)  # add formatter to ch
		_logger.addHandler(ch)  # add ch to logger

	# create log file
	lfpath = os.path.dirname(lfname)
	if lfpath and len(lfpath) > 0:
		if not os.path.exists(lfpath):
			os.makedirs(lfpath)

	fhandler = logging.FileHandler(lfname)
	fhandler.setFormatter(formatter)
	_logger.addHandler(fhandler)

	return _logger


def spawn_subtask():
	parser = BaseSubtask.parse_args_init(None, BaseSubtask._Description)
	subtask = BaseSubtask(parser.parse_args())
	subtask.baselogger.info("***** HELLO!: [{}] *****".format(subtask._Description))
	subtask.start()


def main():
	spawn_subtask()


if __name__ == "__main__":
	main()

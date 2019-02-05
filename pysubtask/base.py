#
# Script: pysubtask.base.py Module
#
# Author V1: David Jacobson (david@jacobsonhome.com)
# https://github.com/djacobson/pysubtask

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
import socket

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

_HeartbeatFudgeFactorSecs = 10  # secs to add to expect val in hb file, for server to allow for transfer


###################
# Base TaskMaster #
###################

class BaseTaskMaster():

	baselogger = None

	def __init__(
		self,
		WatchFilesDirs,
		pconfig,
		SubtaskModuleName=__name__,
		LogFileName=defaults.base.Master_Log_FileName,
		LogToConsole=True):

		# Fill in non-specified config items with defaults
		self.base_config = self.combine(pconfig, defaults.base)

		self.baselogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			LogToConsole)

		# Create Watch files and/or dirs list
		self.init_base_files(WatchFilesDirs)
		if len(self._watch_files) < 1 and len(self._watch_dirs) < 1:
			self.baselogger.error("No Watch files or dirs specified!")
			return

		# Convert WatchFiles list to arguments for subtask
		self.init_base_args(SubtaskModuleName, LogToConsole)

		self._subtask = None

	def setup_logging(self, cname, lfname, LogToConsole=True):
		return setup_logging(cname, lfname, LogToConsole)

	def init_base_files(self, WatchFilesDirs):
		# Create WatchFiles list
		self._watch_files = []
		self._watch_files_state = []
		# Create WatchDirs list
		self._watch_dirs = []

		for wfile in WatchFilesDirs:
			if 'file' in wfile:
				self._watch_files.append(wfile['file'])
				wfile_state = {
					'prev_notify_dt': None,
					'pending_data_dt': None,
					'burst_mode': None
				}

				if 'burstmode' in wfile and wfile['burstmode']:
					wfile_burst_mode = {
						'start_dt': None,
						'count': 0,
						'start_trigger_milli': defaults.burst_mode.start_trigger_milli,
						'start_trigger_count': defaults.burst_mode.start_trigger_count,
						'expire_milli': defaults.burst_mode.expire_milli
					}
					wfile_state['burst_mode'] = wfile_burst_mode
				self._watch_files_state.append(wfile_state)

			elif 'dir' in wfile:
				self._watch_dirs.append(wfile['dir'])
				# ToDo: Implement burstmode for dirs (i.e.: all files in dir)

			else:
				self.baselogger.error("Unknown Watch list key [{}]".format(wfile))

	def init_base_args(
		self,
		SubtaskModuleName=__name__,
		LogToConsole=True):

		# Convert WatchFiles list to arguments for subtask
		wfiles_arg = '"{}"'.format(','.join(map(str, self._watch_files)))
		wdirs_arg = '"{}"'.format(','.join(map(str, self._watch_dirs)))

		PythonName = sys.executable

		# Add specific args for base SubProc
		self._subtaskArgs = [
			PythonName,
			'-m',
			SubtaskModuleName
		]
		if len(self._watch_files) > 0:
			self._subtaskArgs += ['-wf', wfiles_arg]
		if len(self._watch_dirs) > 0:
			self._subtaskArgs += ['-wd', wdirs_arg]
		if not LogToConsole:
			self._subtaskArgs += ['-noconsole']
		# Only add these args if they differ from default config
		if self.base_config.TimerIntervalSecs != defaults.base.TimerIntervalSecs:
			self._subtaskArgs += ['-i', str(self.base_config.TimerIntervalSecs)]
		if self.base_config.HeartbeatIntervalSecs != defaults.base.HeartbeatIntervalSecs:
			self._subtaskArgs += ['-hb', str(self.base_config.HeartbeatIntervalSecs)]
		if self.base_config.HeartbeatName != defaults.base.HeartbeatName:
			self._subtaskArgs += ['-hbname', str(self.base_config.HeartbeatName)]

	def combine(self, master_dict, add_this_dict):
		new_dict = master_dict
		for key, value in add_this_dict.__dict__.items():
			if key not in master_dict.__dict__:
				new_dict.__dict__[key] = value
		return new_dict

	def start(self, prearchive_expired_files_to_folder=None, precopy_files_to_folder=None):
		self.cleanup_all_notify_files()
		if prearchive_expired_files_to_folder:
			# First, prearchive expired files (all files types in log dir)
			self.archive_expired_files(prearchive_expired_files_to_folder)
		if precopy_files_to_folder:
			# Second, precopy old / residual data files types (for preupload, etc.)
			self.copy_residual_files(precopy_files_to_folder)
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
				# self._subtask.send_signal(signal.CTRL_BREAK_EVENT)
				os.popen('TASKKILL /PID ' + str(self._subtask.pid) + ' /F')
			else:
				self._subtask.terminate()
			self._subtask.wait()
		self.cleanup_all_notify_files()
		self.baselogger.info("***** GOODBYE!: [{}] *****".format(subtaskDescription))

	def cleanup_notify_files(self):
		for wfile in self._watch_files:
			nfile = '{}.notify'.format(wfile)
			if os.path.exists(nfile):
				self.baselogger.info("Cleaning up [{}]".format(nfile))
				os.remove(nfile)

	def cleanup_all_notify_files(self):
		hbFolder = None

		if self._watch_files and len(self._watch_files) > 0:
			watchFolder = os.path.dirname(self._watch_files[0])
			if os.path.exists(watchFolder):
				self.cleanup_all_notify_files_in_folder(watchFolder)
				hbFolder = watchFolder

		for watchFolder in self._watch_dirs:
			if os.path.exists(watchFolder):
				self.cleanup_all_notify_files_in_folder(watchFolder)
				if not hbFolder:
					hbFolder = watchFolder

		# Cleanup heartbeat files
		if hbFolder:
			self.cleanup_files_with_ext_in_folder('.heartbeat', hbFolder)

	def cleanup_all_notify_files_in_folder(self, inFolder):
		self.cleanup_files_with_ext_in_folder('.notify', inFolder)

	def cleanup_files_with_ext_in_folder(self, fext, inFolder):
		allFiles = [f for f in os.listdir(inFolder) if os.path.isfile(os.path.join(inFolder, f))]
		for watchNotifyFile in allFiles:
			if watchNotifyFile.endswith(fext):
				nfile = os.path.join(inFolder, watchNotifyFile)
				self.baselogger.info("Cleaning up [{}]".format(nfile))
				os.remove(nfile)

	def copy_residual_files(self, relativeToFolder):
		# Copy all files in watch list with same .ext to specified folder (i.e.: BakTo folder).
		# Typically used to grab missed / residual data before start()
		residual_files_found = False
		if self._watch_files and len(self._watch_files) > 0:
			watchFolder = os.path.dirname(self._watch_files[0])
			if os.path.exists(watchFolder):
				fullToFolder = os.path.join(watchFolder, relativeToFolder)

				# get file extensions
				fextensions = []
				for notify_index, wfile in enumerate(self._watch_files):
					fname, fext = os.path.splitext(wfile)
					if fext not in fextensions:
						fextensions.append(fext)

				self.baselogger.info("PreCopy ALL [{}] Residual data from [{}] to [{}]".format(
					",".join(fextensions),
					watchFolder,
					fullToFolder))
				residual_files_found = self.copy_file_types_from_to(fextensions, watchFolder, fullToFolder)

		# Copy ALL files in Watch directory list to specified folder (i.e.: BakTo folder).
		for watchFolder in self._watch_dirs:
			if os.path.exists(watchFolder):
				# Use the same fullToFolder from above if defined,
				# otherwise, create a separate archive folder
				if not fullToFolder:
					fullToFolder = os.path.join(watchFolder, relativeToFolder)
				self.baselogger.info("PreCopy ALL Residual files in Watch directory [{}] to [{}]".format(
					watchFolder,
					fullToFolder))
				fextensions = ['*']
				residual_files_found = self.copy_file_types_from_to(fextensions, watchFolder, fullToFolder)

		if not residual_files_found:
			self.baselogger.info("No Residual files found to Copy")

	def copy_file_types_from_to(self, fextensions, fromFolder, toFolder):
		found_file = False
		for file_ext in fextensions:
			file_pattern = '*' + file_ext
			found_file = self.copy_pattern_from_to(file_pattern, fromFolder, toFolder)

		return found_file

	def archive_expired_files(self, relativeToFolder):
		# Archive all expired files in first listed file path,
		# to specified folder (i.e.: logs/archive folder).
		arch_files_found = False
		fullToFolder = None
		if self._watch_files and len(self._watch_files) > 0:
			watchFolder = os.path.dirname(self._watch_files[0])
			if os.path.exists(watchFolder):
				fullToFolder = os.path.join(watchFolder, relativeToFolder)
				self.baselogger.info("Archiving expired files from [{}] to [{}]".format(
					watchFolder,
					fullToFolder))
				arch_files_found = self.archive_from_to(watchFolder, fullToFolder)

		# Archive all expired files in each listed watch directory,
		# to specified folder (i.e.: logs/archive folder).
		for watchFolder in self._watch_dirs:
			if os.path.exists(watchFolder):
				# Use the same fullToFolder from above if defined,
				# otherwise, create a separate archive folder
				if not fullToFolder:
					fullToFolder = os.path.join(watchFolder, relativeToFolder)
				self.baselogger.info("Archiving expired files from Watch directory [{}] to [{}]".format(
					watchFolder,
					fullToFolder))
				arch_files_found = self.archive_from_to(watchFolder, fullToFolder)

		if not arch_files_found:
			self.baselogger.info("No expired files found to Archive")

	def archive_from_to(self, fromFolder, toFolder):
		days_old = defaults.base.ArchiveAfterDaysOld
		move_date = date.today() - timedelta(days=days_old)
		move_date = time.mktime(move_date.timetuple())

		arch_files_found = False

		for file in os.listdir(fromFolder):
			fullfile = os.path.join(fromFolder, file)
			if os.path.isfile(fullfile):
				filetime = os.stat(fullfile).st_mtime
				if filetime < move_date:
					arch_files_found = True

					# Build archive path and file name
					fdate = datetime.fromtimestamp(filetime)
					archpath = '{}{:02d}'.format(fdate.year, fdate.month)
					archpath = os.path.join(archpath, '{:02d}'.format(fdate.day))
					archpath = os.path.join(toFolder, archpath)
					archfullfile = os.path.join(archpath, file)
					if not os.path.exists(archpath):
						os.makedirs(archpath)
					else:
						archfullfile = self.getAvailableFileName(archfullfile)

					# Archive file
					self.baselogger.info("Archiving [{}]".format(archfullfile))
					shutil.copy2(fullfile, archfullfile)
					os.remove(fullfile)

		return arch_files_found

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
		found_file = False
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)

		files = glob.iglob(os.path.join(source_dir, fpattern))
		for file in files:
			if os.path.isfile(file):
				found_file = True
				shutil.copy2(file, dest_dir)

		return found_file

	def notify_all_files(self):
		for notify_index, wfile in enumerate(self._watch_files):
			self.notify_file_by_index(notify_index, True)

	def notify_file_by_index(self, notify_index, ignore_burst_mode=False):
		if notify_index < 0 or notify_index >= len(self._watch_files):
			self.baselogger.error("Notify file index [{}] out of range!".format(notify_index))
			return

		wfile = self._watch_files[notify_index]
		wfile_state = self._watch_files_state[notify_index]

		curr_notify_dt = datetime.now()
		if not ignore_burst_mode and wfile_state['burst_mode']:
			wfile_state['pending_data_dt'] = self.notify_file_by_index_burst_mode(notify_index)
		else:
			notify_file(wfile)
		wfile_state['prev_notify_dt'] = curr_notify_dt

	def notify_file_by_index_burst_mode(self, notify_index):
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
					notify_file(wfile)
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
						notify_file(wfile)
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
					notify_file(wfile)
					burst_mode['count'] = 0
		else:
			self.baselogger.info("Initial notify (Burst mode)")
			notify_file(wfile)

		return return_pending_dt

	def check_pending_notifications(self):
		# Check for pending data from ending on a Burst
		now_dt = datetime.now()
		for notify_index, wfile in enumerate(self._watch_files):
			wfile_state = self._watch_files_state[notify_index]
			pending_data_dt = wfile_state['pending_data_dt']
			if pending_data_dt:
				if pending_data_dt <= now_dt:
					self.baselogger.info('Pending AND expired data detected. Notifying!')
					notify_file(wfile)
					wfile_state['pending_data_dt'] = None  # Clear pending flag
				else:
					self.baselogger.info('Pending data detected. *BUT*, has NOT expired yet. [{}] secs to go.'.format(
						pending_data_dt - now_dt))
			else:
				# self.baselogger.info('No pending data to release / notify.')
				pass

	##
	# Following methods primarily used by extensions of BaseTaskMaster
	##

	def encode(self, key, clear):
		# https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
		enc = []
		for i in range(len(clear)):
			key_c = key[i % len(key)]
			enc_c = chr((ord(clear[i]) + ord(key_c)) % 256)
			enc.append(enc_c)
		return base64.urlsafe_b64encode("".join(enc).encode()).decode()


################
# Base Subtask #
################

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

		self.init_subtask_args(args)
		self.init_subtask_files()

		self._Timer = None
		self._SubtaskStopNow = False
		self._IgnoreTimer = False

		self._last_notify_dt = datetime.now()  # Start of app is first notify dt
		self._last_heartbeat_dt = datetime.now()

		signal.signal(
			_SIGNAL_STOP_subtask,
			lambda signal_number, current_stack_frame: self.stop())

		signal.signal(
			_SIGNAL_STOP_subtask_INTERACTIVELY,
			lambda signal_number, current_stack_frame: self.stop())

	def __del__(self):
		self.stop()

	def parse_args_init(self, psDescription):
		parser = argparse.ArgumentParser(description=psDescription)

		parser.add_argument(
			'-w', '-wf', '--watch-file-list',
			# required=True, # At least -wf or -wd required
			dest='watch_files',
			help='Delimited list of file paths+names to watch and upload on notify')

		parser.add_argument(
			'-wd', '--watch-dir-list',
			# required=True, # At least -wf or -wd required
			dest='watch_dirs',
			help='Delimited list of directories to watch all of the files inside and upload on notify')

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
			help='Folder where to stage a copy of notified files to')

		parser.add_argument(
			'-hb', '--heartbeat-interval-secs',
			dest='hb_interval_secs',
			default=defaults.base.HeartbeatIntervalSecs,
			type=int,
			help='Heartbeat interval in seconds')

		parser.add_argument(
			'-hbname', '--heartbeat-name',
			dest='hb_name',
			default=defaults.base.HeartbeatName,
			type=str,
			help='Heartbeat file base name')

		parser.add_argument(
			'-noconsole', '--noconsole',
			dest='noconsole',
			action='store_true',
			default=False,
			help='If specified, do not log to the console')

		return parser

	def setup_logging(self, cname, lfname, LogToConsole=True):
		return setup_logging(cname, lfname, LogToConsole)

	def init_subtask_args(self, args):
		self._TimerIntervalSecs = args.interval_secs  # secs
		self._HeartbeatIntervalSecs = args.hb_interval_secs

		watch_files = args.watch_files[1:-1]  # dequote
		watch_files_list = watch_files.split(',')
		self._watch_files = watch_files_list

		watch_dirs = args.watch_dirs[1:-1]  # dequote
		watch_dirs_list = watch_dirs.split(',')
		self._watch_dirs = watch_dirs_list

		self._bakToFolder = args.bak_to_folder
		self._bakToFullPath = None

		if not args.hb_name:
			self.hb_basename = socket.gethostname()
		else:
			self.hb_basename = args.hb_name

	def init_subtask_files(self):
		hb_path = None

		# Derive notify files list
		# remove any residuals
		self._notify_files = []
		self._notify_dir_files = []
		cached_notify_stamp = 0
		for wfile in self._watch_files:
			nfile = '{}.notify'.format(wfile)
			self._notify_files.append((nfile, cached_notify_stamp))
			if os.path.exists(nfile):
				os.remove(nfile)
			# hb path is first watchfile folder
			if not hb_path:
				hb_path = os.path.split(nfile)[0]

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

		# If hb path not derived from first watchfile folder,
		# default to upload folder (parent of bakTo folder)
		if not hb_path:
			hb_path = os.path.abspath(os.path.join(self._bakToFullPath, os.pardir))

		# Pre-generate Heartbeat file (touched each hb interval)
		# Store hb interval val in var and in hb file (for separate apps like remote servers to read)
		hb_filename = '{}.heartbeat'.format(self.hb_basename)
		self.hb_file = os.path.join(hb_path, hb_filename)

		if self._HeartbeatIntervalSecs > 0:
			self.baselogger.info("Heartbeat: File [{}] every [{}] secs.".format(self.hb_file, self._HeartbeatIntervalSecs))
			with open(self.hb_file, 'w') as out_hbf:
				out_hbf.write('{}\n'.format(self._HeartbeatIntervalSecs + _HeartbeatFudgeFactorSecs))

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

		self._process_check_static_file_list()
		if self._SubtaskStopNow:
			return
		self._process_check_dynamic_dir_list()

		if self._HeartbeatIntervalSecs > 0:
			self._process_heartbeat()

	def _process_check_static_file_list(self):
		# Check File list for files ready to be notified
		i = 0
		for (nfile, cached_notify_stamp) in self._notify_files:
			if self._SubtaskStopNow:
				return
			wfile = nfile.strip('.notify')
			self._notify_files[i] = self._process_check_file(
				wfile,
				nfile,
				self._notify_files[i])
			i += 1

	def _process_check_dynamic_dir_list(self):
		# Dynamically check Dir list for dirs with files ready to be notified
		for watchDir in self._watch_dirs:
			if self._SubtaskStopNow:
				return
			if os.path.exists(watchDir):
				for watchDirFile in os.listdir(watchDir):
					if watchDirFile.endswith(".notify"):
						pass
					else:
						# Check to see if each dir file has a .notify list entry,
						# if not, add one and set it for ready to be notified
						ndirfile = os.path.join(watchDir, watchDirFile)
						ndirfile_already_cached = False
						i = 0
						for (cachedndirfile, cached_notify_stamp) in self._notify_dir_files:
							if ndirfile == cachedndirfile:
								ndirfile_already_cached = True
								break
							i += 1

						if not ndirfile_already_cached:
							# New file to start monitoring
							self._notify_dir_files.append((ndirfile, 0))
							notify_file(ndirfile)
							self._process_notify(ndirfile)
						else:
							# Existing file already being monitored
							ndirnotifyfile = '{}.notify'.format(ndirfile)
							self._notify_dir_files[i] = self._process_check_file(
								ndirfile,
								ndirnotifyfile,
								self._notify_dir_files[i])

	def _process_check_file(self, datafile, datanotifyfile, updatenotifylist):
		cachedndirfile = updatenotifylist[0]
		cached_notify_stamp = updatenotifylist[1]

		if os.path.exists(datanotifyfile):
			stamp = os.stat(datanotifyfile).st_mtime
			if stamp != cached_notify_stamp:
				# Replace notify file tuple stamp
				cached_notify_stamp = stamp
				# File has changed, so do something...
				self._process_notify(datafile)

		return (cachedndirfile, cached_notify_stamp)

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

	def _process_heartbeat(self):
		if self._SubtaskStopNow:
			return
		if self.heartbeat_time() > self._HeartbeatIntervalSecs * 1000:
			# Heartbeat due!
			self._last_heartbeat_dt = datetime.now()  # reset hb time
			touch(self.hb_file)
			self.process_heartbeat(self.hb_file)

	def process_heartbeat(self, hb_filename):
		# Override
		self.baselogger.info("Subtask Heartbeat: do something every Heartbeat interval.")

	def stop(self):
		self._SubtaskStopNow = True
		if self._Timer:
			self.baselogger.info("STOP!")
			self._Timer.stop()
			self._Timer = None

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

	def heartbeat_time(self):
		# Return millisecs since last heartbeat
		if not self._last_heartbeat_dt or self._HeartbeatIntervalSecs <= 0:
			return None
		else:
			return timedelta_milliseconds(datetime.now() - self._last_heartbeat_dt)

	##
	# Following methods primarily used by extensions of BaseSubtask
	##

	def dead_time(self):
		# Return millisecs since last notification
		# or last heartbeat, whichever is most recent
		dtime = self._last_notify_dt
		if self._last_heartbeat_dt:
			if dtime < self._last_heartbeat_dt:
				dtime = self._last_heartbeat_dt

		return timedelta_milliseconds(datetime.now() - dtime)

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

	def decode(self, key, enc):
		# https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
		dec = []
		enc = base64.urlsafe_b64decode(enc).decode()
		for i in range(len(enc)):
			key_c = key[i % len(key)]
			dec_c = chr((256 + ord(enc[i]) - ord(key_c)) % 256)
			dec.append(dec_c)
		return "".join(dec)


##
# Functions globally used by both BaseTaskMaster and BaseSubtask
##

def timedelta_milliseconds(td):
	return td.days * 86400000 + td.seconds * 1000 + td.microseconds / 1000


def notify_file(wfile):
	nfile = '{}.notify'.format(wfile)
	touch(nfile)


def touch(fname, mode=0o666, dir_fd=None, **kwargs):
	# https://stackoverflow.com/questions/1158076/implement-touch-using-python
	flags = os.O_CREAT | os.O_APPEND
	with os.fdopen(os.open(fname, flags=flags, mode=mode, dir_fd=dir_fd)) as f:
		os.utime(
			f.fileno() if os.utime in os.supports_fd else fname,
			dir_fd=None if os.supports_fd else dir_fd, **kwargs)


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
	pid = os.getpid()
	logFormat = '%(asctime)s.%(msecs)03d [%(module)s.%(name)s.{}]: %(levelname)s: %(message)s'.format(pid)
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
	pargs = parser.parse_args()
	if not pargs.watch_files and not pargs.watch_dirs:
		parser.error("Either -wf (watch_files) or -wd (watch_dirs) is required.")
		return
	subtask = BaseSubtask(pargs)
	subtask.baselogger.info("***** HELLO!: [{}] *****".format(subtask._Description))
	subtask.start()


def main():
	spawn_subtask()


if __name__ == "__main__":
	main()

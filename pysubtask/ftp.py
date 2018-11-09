#
# Script: pysubtask.ftp.py Module
#
# Author V1: David Jacobson (david@jacobsonhome.com)

import os
import socket

from . import defaults_config as defaults
from .base import BaseTaskMaster, BaseSubtask

_SecretKey = '0987654321123456'


class FTPTaskMaster(BaseTaskMaster):

	ftplogger = None

	def __init__(
		self,
		WatchFiles,
		pconfig,
		LogFileName=defaults.ftp.Master_Log_FileName,
		LogToConsole=True):

		# Fill in non-specified config items with defaults
		self.config = self.combine(pconfig, defaults.ftp)

		super().__init__(
			WatchFiles,
			self.config,
			__name__,
			LogFileName,
			LogToConsole)

		self.ftplogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			LogToConsole)

		# Add specific args for FTP Client to SubProc args
		if self.config.UseSFTP:
			hostPath = self.config.HostSFTPPath
		else:
			hostPath = self.config.HostFTPPath
		passwordEncrypted = self.encode(_SecretKey, self.config.Password)
		self._subtaskArgs += [
			'-u', self.config.User,
			'-p', passwordEncrypted,
			'-host', self.config.Host,
			'-port', str(self.config.HostPort),
			'-path', hostPath,
			'-x', str(self.config.DeadTimeMilli),
			'-bakto', defaults.ftp.BakToFolder
		]
		if self.config.UseSFTP:
			self._subtaskArgs += ['-sftp']

	def start(self, precopy_files=False):
		if precopy_files:
			super().start(precopy_files_from_folder=self.config.BakToFolder)
		else:
			super().start()

	def stop(self):
		super().stop(defaults.ftp.SubtaskDescription)


class FTPSubtask(BaseSubtask):

	_Description = defaults.ftp.SubtaskDescription
	ftplogger = None

	def __init__(
		self,
		args,
		LogFileName=defaults.ftp.Subtask_Log_FileName):

		super().__init__(args, LogFileName)

		self.ftplogger = self.setup_logging(
			__class__.__name__,
			LogFileName,
			not args.noconsole)

		# User config settings
		self.Enabled = True  # False = FTP not used but FTP Subtask still spawned

		# Internal
		self._sftp = None
		self._ftp = None
		self._useSFTP = args.use_sftp
		self._User = args.ftp_user
		self._PasswordEncrypted = args.ftp_password_encrypted
		self._Host = args.ftp_host
		self._HostPort = args.ftp_port
		if self._HostPort < 0:
			# Use S/FTP standard ports
			if self._useSFTP:
				self._HostPort = 22
			else:
				self._HostPort = 21
		self._HostPath = args.ftp_path
		self.DeadTimeMilli = args.ftp_dead_time_milli

	def start(self):
		self.connect(True)  # connect before starting timers ( super().start() )
		super().start()

	def process_interval(self):
		if not self.Enabled:
			return

		# S/FTP Subtask Timer: called every interval.
		deadTime = self.dead_time()
		if deadTime and deadTime > self.DeadTimeMilli:
			if self.is_connected():
				self.ftplogger.info("'DEAD' for [{}] secs! (no data) REST'ing S/FTP!".format(
					self.DeadTimeMilli / 1000))
				self.disconnect()

	def process_notify(self, psWatchFile):
		if not self.Enabled:
			return

		# S/FTP Subtask Notified!: New data ready
		if not self.is_connected():
			self.connect()

		if not self.upload_file(psWatchFile):
			if self._SubtaskStopNow:
				return
			self.ftplogger.error("Upload, attempting reconnect.")

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

				connectSuccess = self.connect_once(retries=num_retries)

				if connectSuccess:
					break
				else:
					self.ftplogger.error("CONNECT attempt FAILED! Try # [{}] of [{}] retries".format(i + 1, num_retries))
					if (i + 1) < num_retries:
						self.ftplogger.info("Waiting [{}] secs before next try...".format(short_wait))
						self.sleep(short_wait)

			if not connectSuccess:
				self.ftplogger.error("Repeated CONNECT FAILURE!")
				self.ftplogger.info("LONGER Wait [{}] secs before next try...".format(long_wait))
				self.sleep(long_wait)

		if connectSuccess and not self._SubtaskStopNow:
			if uploadAllFilesFirst:
				self.upload_all_in_dir(self._bakToFullPath)

		self._IgnoreTimer = False

	def connect_once(self, retries=0):
		if self.is_connected():
			self.disconnect()

		if not self.isHostOpen(self._Host, self._HostPort, retries):
			self.ftplogger.error("Host not open! [{}:{}]".format(
				self._Host,
				self._HostPort))
			return False
		self.ftplogger.info("Host port open Success! [{}:{}]".format(
			self._Host,
			self._HostPort))

		if self._useSFTP:
			self.ftplogger.info("SFTP CONNECT! to [{}@{}:{}/{}]".format(
				self._User,
				self._Host,
				self._HostPort,
				self._HostPath))
			return self.connectSFTP()
		else:
			self.ftplogger.info("FTP CONNECT! to [{}@{}:{}/{}]".format(
				self._User,
				self._Host,
				self._HostPort,
				self._HostPath))
			return self.connectFTP()

	def connectSFTP(self):
		import pysftp

		try:
			cnopts = pysftp.CnOpts()
			cnopts.hostkeys = None  # ignore host key for this special purpose sftp client
			ftp_pw = self.decode(_SecretKey, self._PasswordEncrypted)

			self._sftp = pysftp.Connection(
				host=self._Host,
				port=self._HostPort,
				username=self._User,
				password=ftp_pw,
				# private_key=private_key,
				# private_key_pass=private_key_password,
				cnopts=cnopts)
			# sftp.timeout = SOCKET_TIMEOUT
			# srv._transport.set_keepalive(30)

		except Exception as e:
			self.ftplogger.error("SFTP: Host or Authentication [{}]".format(e))
			self._sftp = None
			return False
		else:
			self.ftplogger.info("SFTP: Success! Connected to [{}]".format(self._Host))

		if self._sftp:
			if self._HostPath and len(self._HostPath.strip()) > 0:
				hostpath = self._HostPath.strip()
				try:
					self._sftp.chdir(hostpath)
				except Exception:
					self.ftplogger.error("SFTP: Invalid chdir to path [{}].".format(hostpath))
					self._sftp = None
					return False
		else:
			return False

		return True

	def connectFTP(self):
		from ftplib import FTP

		try:
			if self._HostPort != 21:
				ftptimeout = 15  # secs
				self._ftp = FTP.connect(self._Host, self._HostPort, ftptimeout)
			else:
				self._ftp = FTP(self._Host)
		except Exception:
			self.ftplogger.error("FTP: Host could not be resolved.")
			self._ftp = None
			return False

		try:
			ftp_pw = self.decode(_SecretKey, self._PasswordEncrypted)
			self._ftp.login(user=self._User, passwd=ftp_pw)
		except Exception:
			self.ftplogger.error("FTP: Invalid login.")
			self._ftp = None
			return False
		else:
			self.ftplogger.info("FTP: Success! Connected to [{}]".format(self._Host))

		if self._ftp:
			if self._HostPath and len(self._HostPath.strip()) > 0:
				hostpath = self._HostPath.strip()
				try:
					self._ftp.cwd(hostpath)
				except Exception:
					self.ftplogger.error("FTP: Invalid CWD to path [{}].".format(hostpath))
					self._ftp = None
					return False
		else:
			return False

		return True

	def is_connected(self):
		if self._useSFTP:
			if self._sftp:
				return True
			else:
				return False
		else:
			if self._ftp:
				return True
			else:
				return False

	def isHostOpen(self, iphost, port, retries=0):
		for i in range(retries + 1):
			connectSuccess = False
			s = None
			try:
				s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				s.settimeout(1)
				s.connect((iphost, port))
				connectSuccess = True
			except Exception as e:
				if i < retries:
					self.ftplogger.error("Trying host connect again... [{}:{}] [{}]".format(
						iphost, port, str(e)))
					self.sleep(1)
			finally:
				if connectSuccess:
					s.shutdown(socket.SHUT_RDWR)
					s.close()
					return True
				else:
					if s:
						s.close()
		return False

	def disconnect(self):
		if self._sftp:
			self.ftplogger.info("SFTP DISCONNECT!")
			try:
				self._sftp.close()
			except Exception as e:
				pass
			self._sftp = None

		if self._ftp:
			self.ftplogger.info("FTP DISCONNECT!")
			try:
				self._ftp.quit()
			except Exception as e:
				pass
			self._ftp = None

	def stop(self):
		super().stop()
		# Upload all files one final time
		if self.is_connected():
			self.upload_all_in_dir(self._bakToFullPath)
		self.disconnect()

	def upload_file(self, upFile):
		# Check if upFile exists first
		if not os.path.exists(upFile):
			self.ftplogger.error("Upload file [{}] does not exist!".format(upFile))
			return False

		# Check if we need to reconnect
		if not self.is_connected():
			self.connect()
			if not self.is_connected():
				return False

		upname = os.path.basename(upFile)

		if self._useSFTP and self._sftp:
			try:
				# ** Transfer the file using SFTP
				self._sftp.put(upFile, preserve_mtime=True)
			except Exception as e:
				self.ftplogger.error("SFTP Upload Data File: [{}]".format(e))
				self.disconnect()
				return False
			else:
				self.ftplogger.info("SFTP Upload Data File: [{}]".format(
					os.path.join(self._HostPath, upname)))
				return True
		elif self._ftp:
			try:
				# ** Transfer the file using FTP
				self._ftp.storbinary('STOR ' + upname, open(upFile, 'rb'))
			except Exception as e:
				self.ftplogger.error("FTP Upload Data File: [{}]".format(e))
				self.disconnect()
				return False
			else:
				self.ftplogger.info("FTP Upload Data File: [{}]".format(
					os.path.join(self._HostPath, upname)))
				return True

	def upload_all_in_dir(self, upDir):
		if not upDir or not os.path.exists(upDir):
			return
		self.ftplogger.info("Uploading ALL files in [{}]...".format(upDir))

		allFiles = [f for f in os.listdir(upDir) if os.path.isfile(os.path.join(upDir, f))]
		for bakFile in allFiles:
			self.upload_file(os.path.join(upDir, bakFile))

	def parse_args_init(self, psDescription):
		parser = BaseSubtask.parse_args_init(None, psDescription)

		# Add specific args for FTP Client to SubProc args
		parser.add_argument(
			'-u', '--user', '--username',
			required=True,
			dest='ftp_user',
			help='FTP user login name')

		parser.add_argument(
			'-p', '--password',
			required=True,
			dest='ftp_password_encrypted',
			help='FTP user login password (encrypted)')

		parser.add_argument(
			'-host', '--hostname',
			required=True,
			dest='ftp_host',
			help='Hostname or IP addr of FTP server to connect to')

		parser.add_argument(
			'-port', '--port',
			dest='ftp_port',
			default=defaults.ftp.HostPort,
			type=int,
			help='FTP server port; default -1 means use standard S/FTP port')

		parser.add_argument(
			'-path', '--path',
			dest='ftp_path',
			default=defaults.ftp.HostPath,
			help='FTP path to chdir after login')

		parser.add_argument(
			'-x', '--dead-time', '--expired-time',
			dest='ftp_dead_time_milli',
			default=defaults.ftp.DeadTimeMilli,
			type=int,
			help="Elapsed 'dead' time in milliseconds with NO Data before rest'ing FTP")

		parser.add_argument(
			'-sftp', '--sftp',
			dest='use_sftp',
			action='store_true',
			help='Use SFTP, else (if not included), use regular FTP')

		return parser


def spawn_subtask():
	parser = FTPSubtask.parse_args_init(None, FTPSubtask._Description)
	subtask = FTPSubtask(parser.parse_args())
	subtask.ftplogger.info("***** HELLO!: [{}] *****".format(subtask._Description))
	subtask.start()


def main():
	spawn_subtask()


if __name__ == "__main__":
	main()

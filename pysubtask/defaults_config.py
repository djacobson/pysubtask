#
# Script: pysubtask.defaults_config.py
#
# Author V1: David Jacobson (david@jacobsonhome.com)
# https://github.com/djacobson/pysubtask

from ._config import Struct as Section

# Default Args for both TaskMaster and Subtask extensions

base = Section('Base TaskMaster-Subtask defaults')

base.SubtaskDescription = "BaseSubtask Scheduler"
base.TimerIntervalSecs = 2
base.BakToFolder = 'upload'  # Relative path, None = does not make a copy of file
base.ArchiveToFolder = 'archive'  # Relative path, None = does not archive expired files
base.ArchiveAfterDaysOld = 3
base.Master_Log_FileName = './logs/base_taskmaster.log.txt'
base.Subtask_Log_FileName = './logs/base_subtask.log.txt'

burst_mode = Section('Base TaskMaster Burst Mode defaults')

burst_mode.start_trigger_milli = 1000  # 1 sec
burst_mode.start_trigger_count = 2  # n times in a row required for burst mode to be triggered
burst_mode.expire_milli = 5000  # 5 secs

ftp = Section('S/FTP TaskMaster-Subtask defaults')

ftp.SubtaskDescription = "S/FTP Uploader"
ftp.HostPort = -1  # Default -1 = Use standard ports for either S/FTP
ftp.HostPath = ""
ftp.DeadTimeMilli = 180000  # 180000 millisecs = 3 mins, Time of no notifies before RESTing
ftp.UseSFTP = True  # False = Use regular FTP
ftp.BakToFolder = 'upload/ftp'  # Relative path, None = does not make a copy of file
ftp.TimerIntervalSecs = 2  # Time to wake up and check for data notifies
ftp.Master_Log_FileName = './logs/ftp_taskmaster.log.txt'
ftp.Subtask_Log_FileName = './logs/ftp_subtask.log.txt'

dropbox = Section('Dropbox TaskMaster-Subtask defaults')

dropbox.SubtaskDescription = "Dropbox Uploader"
dropbox.AccessToken = "*************************************************"
dropbox.DeadTimeMilli = 180000  # 180000 millisecs = 3 mins, Time of no notifies before RESTing
dropbox.BakToFolder = 'upload/dropbox'  # Relative path, None = does not make a copy of file
dropbox.TimerIntervalSecs = 2  # Time to wake up and check for data notifies
dropbox.Master_Log_FileName = './logs/dropbox_taskmaster.log.txt'
dropbox.Subtask_Log_FileName = './logs/dropbox_subtask.log.txt'

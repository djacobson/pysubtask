#
# Script: demo_config.py
#
# Author V1: David Jacobson (david@jacobsonhome.com)
# https://github.com/djacobson/pysubtask

from pysubtask._config import Struct as Section

# Base config changes from defaults
base = Section("pysubtask TaskMaster-Subtask Base demo configuration")
# Use Heartbeat feature
base.HeartbeatIntervalSecs = 60  # default = 0, not used
base.HeartbeatName = None  # default None = hostname

# FTP transfers
ftp = Section("pysubtask TaskMaster-Subtask FTP demo configuration")
ftp.UseFTP = True  # Must be True to use SFTP

# David's Dev S/FTP Server
ftp.UseSFTP = True  # True = sftp protcol, False = unsecure ftp protcol
ftp.User = "DAVIDJ-PC\David"
ftp.Password = "***************"
ftp.Host = "DavidJ-PC"
ftp.HostFTPPath = 'tagreader'
ftp.HostSFTPPath = 'Desktop/winftp/tagreader'
# 180000 millisecs = 3 mins, Time of no notifies before 'REST'ing
ftp.DeadTimeMilli = 30000

# Dropbox transfers
dropbox = Section("pysubtask TaskMaster-Subtask Dropbox demo configuration")
dropbox.UseDropbox = False

# David's Dropbox Token, see pysubtask.dropbox.py for instructions.
dropbox.AccessToken = "**********************************************"
# 180000 millisecs = 3 mins, Time of no notifies before 'REST'ing
dropbox.DeadTimeMilli = 30000

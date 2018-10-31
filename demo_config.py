#
# Script: demo_config.py
#
# Author V1: David Jacobson (david@jacobsonhome.com)

from pysubtask._config import Struct as Section

# FTP transfers
ftp = Section("pysubtask TaskMaster-Subtask FTP demo configuration")
ftp.UseFTP = True

# David's Dev S/FTP Server
ftp.UseSFTP = True  # True = sftp protcol, False = unsecure ftp protcol
ftp.User = "DAVIDJ-PC\David"
ftp.Password = "***********"
ftp.Host = "DavidJ-PC"
ftp.HostFTPPath = "tagreader"
ftp.HostSFTPPath = 'Desktop/winftp/tagreader'
# 180000 millisecs = 3 mins, Time of no notifies before 'REST'ing
ftp.DeadTimeMilli = 40000

# Dropbox transfers
dropbox = Section("pysubtask TaskMaster-Subtask Dropbox demo configuration")
dropbox.UseDropbox = False

# David's Dropbox Token, see pysubtask.dropbox.py for instructions.
dropbox.AccessToken = "**********************************************"
# 180000 millisecs = 3 mins, Time of no notifies before 'REST'ing
dropbox.DeadTimeMilli = 40000

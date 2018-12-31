#
# Script: pysubtask/demo.py Module
#
# Author V1: David Jacobson (david@jacobsonhome.com)
# https://github.com/djacobson/pysubtask

import demo_config as config


def get_commands(master):
	finished = False
	kbd_input = ''

	while not finished:
		try:
			kbd_input = input("Enter cmd (x | r | a | c | 0-n):\n").strip().lower()
		except KeyboardInterrupt:
			# CTRL+C exit
			kbd_input = 'x'

		if kbd_input != '':
			print("cmd = [{}]".format(kbd_input))

			if kbd_input == 'x':
				# Exit
				print("Exiting.")
				finished = True
				break

			elif kbd_input == 'r':
				# Reset subtask
				master.reset()

			elif kbd_input == 'a':
				# Notify subtask of all files and directories
				# having ready data
				master.notify_all_files()

			elif kbd_input == 'c':
				# Check for pending data from ending on a Burst
				master.check_pending_notifications()

			elif kbd_input.isdigit():
				# Notify subtask of specific file in list (by index num)
				master.notify_file_by_index(int(kbd_input))

			else:
				print('ERROR: [{}] Unknown cmd!'.format(kbd_input))

	return


def run_app():

	watchfilesdirs = [
		{'file': 'logs/test1.csv', 'burstmode': True},
		{'file': 'logs/test1.mrk', 'burstmode': False},
		{'dir': 'logs/watch_all_in_here'}
	]

	master = None
	if config.ftp.UseFTP:

		# Use S/FTP
		from pysubtask.ftp import FTPTaskMaster
		master = FTPTaskMaster(watchfilesdirs, config.ftp, LogToConsole=True)

	elif config.dropbox.UseDropbox:

		# Use DropBox
		from pysubtask.dropbox import DropboxTaskMaster
		master = DropboxTaskMaster(watchfilesdirs, config.dropbox, LogToConsole=True)

	else:
		return

	# Pre-archive old data & pre-copy and upload previous residual data, then Start
	master.start(precleanup_old_files=True)

	get_commands(master)
	master.stop()

	return


def main():
	run_app()


if __name__ == "__main__":
	main()

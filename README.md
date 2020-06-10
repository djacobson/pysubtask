# pysubtask

**`pysubtask`** is a subtask and data transfer helper class; **push** only, client-side only (no custom server-side app needed). It is a packaged module, for integration in any Python app, which implements a task-subtask (parent-child, M / S, manager-worker, leader-follower, etc.) pattern with convenient extensions specifically for long-running, unreliable tasks like repeated Internet transfers (i.e.: constant updating of data files on a web server). Extensions include S/FTP, and Dropbox. Resiliency is one of the primary design goals.

## Quick Start

Install from [PyPI](https://pypi.python.org/pypi/pysubtask): To do...

Or install from [GitHub](https://github.com/djacobson/pysubtask):

```
$ git clone https://github.com/djacobson/pysubtask
$ cd pysubtask
```

Edit ``demo_config.py`` to include the login info for your desired S/FTP server account and/or Dropbox access token (if using Dropbox, change the config line to ``dropbox.UseDropbox = True``.

Run the demo:

```
> python3 demo.py
```

...and enter one or more of the following interactive commands to test the module:

```
Enter cmd:

'x' = Exit demo.py
'a' = Notify subtask of all files ready with new data
0-n = Notify subtask of a specific file in list (by index num) ready with new data
'c' = Check for pending data (from ending on a Burst) and notify it if it exists
'r' = Reset the subtask (complete shutdown and restart of the subtask process)
```

Enter one or more of the demo _**Notify**_ commands ``(a, 0, 1, c)`` repeatedly, with varying frequency to watch the notifications and **burst mode** in action, simulating new data being written and "notified" to the registered data file(s), and actually being "pushed" to your specified S/FTP host. Also, copy a random file into the ``logs/watch_all_in_here`` folder and observe it automatically uploaded, and update its auto-gen'd ``.notify`` file and observe it being uploaded (an example of notifying a file externally from the ``demo.py`` app.

Data files to monitor and upload-on-notify are declared either by a static file name(s) list, or with the name of a directory(ies) to watch for files to appear inside dynamically, or both. See the following initialization code in ``demo.py``, and experiment by adding your own data file(s):

```
watchfilesdirs = [
	{'file': 'logs/test1.mrk'},  # Regular, no burstmode
	{'file': 'logs/test1.csv', 'burstmode': True},
	{'dir': 'logs/watch_all_in_here'}
]
```

Also, observe the log output in the ``logs`` folder, as well as the test data files. (See **About** below for a more detailed explanation)

## About

### Base Master and Subtask classes

The main idea / goal behind this module was to implement cross-platform, Unix-like ``fork()``, subprocessing class in Python, that purposely does not use Python's threading or process modules. Instead, the 'spawned' subtask (child process) is very isolated from the master (parent process), in its own process / memory space, and has little opportunity to negatively impact the resources or performance of the subtask's master. However, the spawning master task class still has the ability to manage (start, stop, notify) the subtask. ...and then, build some resilient **push** data transfer extensions on top of this functionality.

This specific use-case pattern is based on a data file(s) being updated (data constantly appended to it) on the master side, and the master efficiently "notifying" the spawned subtask that new data is ready (the subtask is preconfigured with the data file name(s) on initialization). Having been "notified", the subtask (child process) is free to do whatever long-running, performance intensive, potentially unreliable work (i.e.: slow S/FTP or Dropbox transfers over questionable Internet connections) in its own, isolated process space; allowing the master (parent process) to perform its own, possibly near-real-time, processing uninterrupted and isolated.

#### IPC and Data File Manipulation

The "notification" IPC between the master and the subtask is purposely minimal (i.e.: does not use IPC features like pipes that could be susceptible to dead-lock issues if one side fails to keep the pipe empty, etc.). It uses a simple file ``touch()``, which the subtask polls and checks for a change on a reasonable interval (default is set to 2 seconds, configured on class instantiation or in ``pysubtask/defaults_config.py: base.TimerIntervalSecs``). The touched file used for the notification is even a separate, auto-created and removed file so as not to subject the data file(s) to any potentially disrupting i/o (Note: the notify file(s) are named the same the data file(s) with the ``.notify`` file extension added). A copy is made of data file(s) before the child subtask is allowed to work on it, so that the subtask is then performing its work on a snapshot of the data, rather than the master data file(s). Note: data file snapshots are auto-copied to the folder specified in ``pysubtask/defaults_config.py: base.BakToFolder or ftp.BakToFolder or dropbox.BakToFolder``.

The Base Subtask class implements a simple "infinite timer" that calls a user-extended member function, on a configurable time-interval (default is set to 2 seconds, configured on class instantiation or in ``pysubtask/defaults_config.py: base.TimerIntervalSecs or ftp.TimerIntervalSecs or dropbox.TimerIntervalSecs``)

#### Forcekill

Because this module targets reliability first-and-foremost, it avoids potential dead-lock scenarios by eliminating or minimizing any IPC over Pipes between the master and subtask processes, and then uses an OS ``kill()`` to stop the subtask by default (``master.stop() = master.stop(forcekill=True)``). But, a standard **"terminate and wait"** method of stopping the subtask process is available if needed by explicitly specifying ``master.stop(forcekill=False)`` (shown in ``demo.py``). Warning: the **"terminate and wait"** method of stopping the subtask process can often 'hang' (block on the OS ``wait()`` call) if the stdin or sterr or any redirected pipe is not thoroughly 'read off' before the ``stop()``... in fact, if there is lots of i/o, multithreaded processing, etc.; the subtask process can block the ``wait()`` call for unclear reasons (thus, the reason the default is set to ``forcekill=True``). Note: One way to see this difference is if the **"terminate and wait"** method is used (``master.stop(forcekill=False)``), the ``BaseSubtask.stop()`` method (and its extension if used) will be called, also logging ``datetime [base.BaseSubtask.pid]: INFO: STOP!``; if the default **forcekill** method is used, ``BaseSubtask.stop()`` will NOT be called, and the subtask process is immediately killed.

#### Data File Archival and Residuals

The ``pysubtask`` master task class automatically moves _**all**_ files in the data log folder (the folder of the first file listed in ``watchfiles``) older than ``pysubtask/defaults_config.py: base.ArchiveAfterDaysOld`` (default = 3 days old); to a relative archive folder ``pysubtask/defaults_config.py: base.ArchiveToFolder`` (default = "archive"), auto-creating a [file-year][month]/[day_of_month] folder for the file, and auto-incrementing the file name if it already exists, rather than overwriting it.

In cases where ``pysubtask`` experiences unplanned shutdowns, Internet outages, etc.; where data might exist in the ``watchfiles`` file list from previous runs that might not have been **notified**, **uploaded**, etc. (_**residual**_ data)... _**on initial start**_, the master will automatically _**pre-copy**_ all existing files (that have not aged enough to be archived off) of the same file type (the same file extension, i.e.: `.csv`, or `.dat`, etc.) as the first file listed in ``watchfiles``; to the snapshots folder: ``pysubtask/defaults_config.py: base.BakToFolder or ftp.BakToFolder or dropbox.BakToFolder``. The subtask will first consider these files as **notified** (i.e.: **upload** them), then clear / remove their snapshot copies before proceeding with the normal operation of watching the files in the ``watchfiles`` list.

### Extensions: S/FTP and Dropbox data transfer classes

Part of the inspiration behind this package's design involved constant uploading of data from a client computer to an Internet server (without a custom server-side app) from a location with unreliable, "spotty" internet service (i.e.: a cellular hot-spot, etc.), over a long period of time (hours); with the communication failures, retry procedures, error handling robustness of different file transfer libraries, etc.; having ill-effect on the master working process.

#### Retry logic:

The S/FTP and Dropbox extension modules implement the following retry procedure to handle authentication and/or connection failures:
- Retry an initial number of tries (default 5), waiting a short time between each failure (default 3 seconds)
- After the initial number of failures, wait a longer period of time (default 30 seconds) before starting another set of retries
- After successful connection, the module will keep the connection 'open' as long as it is receiving new data notifications from the master. But, if a specified amount of time passes where there are no notifications, **"dead time"**, the module will logout / disconnect (Note: it can be unreliable and resource intensive to keep S/FTP, Dropbox, etc. login connections open over long periods of time, i.e.: hours). The module will automatically re-authenticate + reconnect if a new data notification is observed. ("dead time" default is set to 3 minutes = 180000 millisecs, configured on class instantiation or in ``pysubtask/defaults_config.py: ftp.DeadTimeMilli and/or dropbox.DeadTimeMilli``)

### Heartbeat Health Status

The **Heartbeat** option is intended to report the "health" of subtasks during extended periods of data inactivity (no notifications); **"dead time"**, by sending out a periodic "heartbeat" report file, which contains a value in seconds to expect the next heartbeat. When using this feature, a subtask client can be considered **"offline"** or **"down"** if its expected heartbeat interval, stored in the ``.heartbeat`` file, becomes **past due**, i.e.: if the **current time** surpasses the **modified date-time** of the ``.heartbeat`` file **+** the **expected heartbeat interval** value. The inspiration behind this feature, when combined with the S/FTP or Dropbox data transfer extensions, was to support a server-side "online status" app for the intermittently connected / disconnected ``pysubtask`` clients.

- Heartbeat is enabled by setting the heartbeat interval value ``base.HeartbeatIntervalSecs`` to a number greater than **zero**.
- ``pysubtask`` extensions (i.e.: ``ftp``, ``dropbox``, etc.) are setup to auto-transfer Heartbeat files (``.heartbeat``) so remote server app(s) can monitor the Heartbeat files (Note: ...the original motivation behind this feature).
- ``.heartbeat`` files are stored in the first ``watchfilesdirs`` list entry folder specified during ``TaskMaster`` creation, and also auto-cleaned-up on ``pysubtask`` start and stop.
- ``.heartbeat`` files are prefixed by a name specified using ``base.HeartbeatName`` or, if left unset, the ``pysubtask`` computer ``hostname``.
- The Heartbeat schedule is checked in intervals of ``base.TimerIntervalSecs`` and its ``base.HeartbeatIntervalSecs`` should be set to a greater value. It also makes sense for ``base.HeartbeatIntervalSecs`` to be a value greater than the extension's ``DeadTimeMilli`` setting (i.e.: ``ftp.DeadTimeMilli``); if not, no **dead time** will occur and you will not realize the benefits of efficient disconnects and reconnects during periods of extended **dead time** or inactivity. One initial heartbeat is generated instantly on app startup.

### Burst Mode: (EXPERIMENTAL: Optional per data file during master class initialization)

The idea behind the **burst mode** option is... if a large amount of new data in a short period of time is causing the master to generate frequent notifications, to disable notifications for a specified amount of time, allowing data to "buffer up" in the data file(s), before notifying the subtask to work on it (i.e.: S/FTP transfer it, etc.), and then returning to "regular notification mode", when the burst has ended; **or** an allowed time period expires, regardless if the burst has ended (default 5 seconds = 5000 milliseconds, configured in ``pysubtask/defaults_config.py: burst_mode.expire_milli``). This is purely an optional, fine-tuning efficiency; helpful if your specific use case allows for it. The data is being "buffered up" anyway, in regular "non-burst" mode. This feature encourages a larger amount of data to be transferred with a reduced number of Internet transactions during a **burst**, provided you can wait a little longer for it. The key, configurable, and experimental detail of this feature is detecting when a burst is occurring or beginning. In this Version 1, a rudimentary algorithm of measuring time between notify calls is used. If a certain number of _**consecutive**_ notifies are called below a specified "trigger time" between them, a **burst** is recognized as starting (triggered), and the burst ends (the data is notified) when it expires; **or** if a notify is executed slower than the "trigger time". These **burst mode** defaults are configured in ``pysubtask/defaults_config.py: burst_mode.start_trigger_milli, burst_mode.start_trigger_count, burst_mode.expire_milli``. Important: When using this option, if the last new data notification ends in a **burst**, pending data that has not been notified to the subtask (i.e.: has not yet been transferred, etc.) could be left in the data file... in other words, no new data has come along to flush it out. It is thus up to the user to call ``master.check_pending_notifications()`` on a periodic timer in their main (master) app to check for and flush (notify) possible pending data.

Note: This master side **burst mode** feature is not quite the same as a subtask side _"exponential back off"_ algorithm / feature (see To Do below).

### To Do

- The transfer extensions are currently using "full file" transfer technologies (i.e.: S/FTP, Dropbox). It would be nice to implement an additional extension option that uses Unix's ``rsync``, which supports efficient remote file differential synchronization. It would be even cooler to build this feature directly into ``pysubtask`` to reduce the amount of data sent with ongoing notifications. But, ``rsync`` has its own custom server-side daemon to support its diff'ing process. For the ``pysubtask`` "client-side-only" design, it would be preferable to implement this entirely client-side, possibly using external files to record + compare record positions, etc. But, it may be difficult to achieve 100% reliability and recoverabliity for remote data synchronization in a client-side-only design.
- Version 1 is primarily a **push** / ``put()`` assistant. It would make sense to add **pull** / ``get()`` to the same module, but, would the subtask try to notify the master? Or just simply get data on a timer interval and rely on the master to poll for it?
- ``demo.py`` could probably be made into an official test module, moved into a tests folder, and made to work with pytest (including a setyp.py install section for tests)
- Possible feature: Implement an _"exponential back-off"_ algorithm in the subtask-side (child) of the S/FTP and Dropbox extension classes. This would be slightly different from **burst mode** (task master / parent side), with the objective being to reduce the total number of transfers / transactions over a long period of time (i.e.: 12 or 24 hours), as opposed to just reducing some transfers during a **burst** of data notifications. This feature would have the secondary goal of avoiding surpassing host transaction limits / quotas (i.e.: Dropbox upload limits per day, etc.).
- Possible enhancement: The _"burst detection"_ algorithm could be made more robust if it considered number of bytes being written to the data file(s), possibly replacing or as an alternative to frequency of notifications. Missing this is the main reason this feature remains "Experimental".
- Possibly publish separate 2nd app that demonstrates server-side monitoring of the "Heartbeat" online / offline status feature. This app might be a portable GUI app (i.e.: PyQT, PySide, etc.)

### Dependencies

- ``pysftp``
- ``dropbox``

### Tests

- Platforms tested: **Python 3.6** on **Raspbian**, **Ubuntu 18.10**, **Windows 10**
- Linux note: Total number of processes allowed per user (``nproc``) default might be set surprisingly low as described [here](https://support.cafex.com/hc/en-us/articles/202508492-Increasing-the-number-of-threads-available-on-Linux). Check your settings in ``/etc/security/limits.conf`` if you have issues, more threads in this or other concurrently running apps, etc. I personally was seeing an intermittent ``GLib-ERROR ...`` under Raspbian.

### Dev Notes

The following dev topics may or may not result in future changes...

- _To CLI or not to CLI_: Even though `pysubtask` has a CLI ``demo.py`` test app; and it's master class utilizes Popen, the command line, and ``parse_args()`` to so spawn subtasks (child processes); it alone is not intended to be an actual CLI utility (as its main user interface). It is primarily an API / utility class patttern for integration into other Python applications. So, it currently does not have a typical CLI ``setup.py`` installation, with CLI entry points, synonyms, etc. This could change in a future version though.
- _The multiple_ ``main()`` _'s_: Unique to the way this pattern spawns a separate Python env for the subtask, a separate ``main()`` is required per subtask module. Attempts to use a 'shared' ``main() or _main_.py`` in this specific pattern typically results in a ``ImportError: attempted relative import with no known parent package`` "Catch 22" import issue after spawning the subtask.
- _Doing away with the Master classes in the extension modules, replacing with functions_: With the exception of the ``BaseMaster``, extension Master classes are light, almost simply wrapper classes. Because of this, it is possible that they might be elimanted and replaced with a function. But, there still might be use cases for custom logic to be added to the master, in which case, a master class is useful since the base class (``BaseMaster``) is used to store state data across member function calls.

### Authors, Contributors, etc.

Version 1 of `pysubtask` was designed and written by [David Jacobson](http://blog.jacobsonhome.com/) ([github](https://github.com/djacobson)), with many thanks to [Darryl Agostinelli](http://www.darrylagostinelli.com/) ([github](https://github.com/dagostinelli)) for extensive refactoring and general pythonic assistance.

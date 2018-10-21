# pysubtask

`pysubtask` is a packaged module, for integration in any Python app, that implements a task-subtask (parent-child, master-slave, manager-worker, etc.) pattern with convenient extensions specifically for long-running, unreliable tasks like repeated Internet transfers (i.e.: constant updating of data files on a web server). Extensions include FTP, SFTP, and Dropbox. Resiliency is one of the primary design goals.

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

...and observe the log output in the ``logs`` folder, as well as the test data files.

Experiment with your own data file(s) by editing the following initialization code in ``demo.py``:

```
uploadfiles = [
	{'file': 'logs/test1.csv', 'burstmode': True},
	{'file': 'logs/test1.mrk', 'burstmode': False}
]
```

## About

### Base Master and Subtask classes

The main idea / goal behind this module was to implement cross-platform, Unix-like ``fork()``, subprocessing class in Python, that purposely does not use Python's threading or process modules. Instead, the 'spawned' subtask (child process) is very isolated from the master (parent process), in its own process / memory space, and has little opportunity to negatively impact the resources or performance of the subtask's master. However, the spawning master task class still has the ability to manage (start, stop, notify) the subtask.

This specific use-case pattern is based on a data file(s) being updated (data constantly appended to it) on the master side, and the master efficiently "notifying" the spawned subtask that new data is ready (the subtask is preconfigured with the data file name(s) on initialization). Having been "notified", the subtask (child process) is free to do whatever long-running, performance intensive, potentially unreliable work (i.e.: slow S/FTP or Dropbox transfers over questionable Internet connections) in its own, isolated process space; allowing the master (parent process) to perform its own, possibly near-real-time, processing uninterrupted and isolated.

The "notification" IPC between the master and the subtask is purposely minimal (i.e.: does not use IPC feature like pipes that could be susceptible to dead-lock issues if one side fails to keep the pipe empty, etc.). It uses a simple file ``touch()``, which the subtask polls and checks for a change on a reasonable interval (default is set to 2 seconds, configured on class instantiation or in ``pysubtask/defaults_config.py: base.TimerIntervalSecs``). The touched file used for the notification is even a separate, auto-created and removed file so as not to perform any potentially disrupting i/o on the data file(s) except for reading its contents (Note: the notiy file(s) are the data file name with the ".notify" suffix added). A copy is made of data file(s) before the child subtask is allowed to work on it, so that it is performing its work on a snapshot of the data, rather than the master data file(s) (snapshots auto-copied to the ``pysubtask/logs/extension`` folder).

The Base Subtask class implements a simple 'infinite timer' that calls a user-extended member function, on a configurable time-interval (default is set to 2 seconds, configured on class instantiation or in ``pysubtask/defaults_config.py: base.TimerIntervalSecs or ftp.* or dropbox.*``)

### Extensions: S/FTP and Dropbox classes

Part of the inspiration behind this package's design involved constant uploading of data to an Internet server from a location with unreliable, 'spotty' internet service (i.e.: a cellular hot-spot, etc.), over a long period of time (hours); the communication failures, retry procedures, error handling robustness of different file transfer libraries, etc.; having ill-effect on the master working process.

#### Retry logic:

The FTP and Dropbox extension modules implement the following retry procedure to handle authentication and/or connection failures:
- Retry an initial number of tries (default 5), waiting a short time between each failure (default 3 seconds)
- After the initial number of failures, wait a longer period of time (default 30 seconds) before starting another set of retries
After successful connection, the module will keep the connection 'open' as long as it is receiving new data notifications from the master. But, if a specified amount of time passes where there is no notifications, 'dead time', the module will logout / disconnect (Note: it can be unreliable to keep FTP, Dropbox, etc. Internet service connection open over long periods of time, i.e.: hours). The module will automatically re-authenticate + reconnect if a new data notification is observed. ('dead time' default is set to 3 minutes = 180000 millisecs, configured on class instantiation or in ``pysubtask/defaults_config.py: ftp.DeadTimeMilli and/or dropbox.DeadTimeMilli``)

#### Burst Mode: (optional and experimental)

The idea behind the 'burst mode' option is... if a large amount of new data in a short period of time is causing the master to generate frequent notifications, to disable notifications for a specified amount of time, allowing data to 'buffer up' in the data file(s), before notifying the subtask to work on it (i.e.: FTP transfer it, etc.), and then returning to 'regular notification mode' when the burst is over or a allowed time period expires (default 5 seconds = 5000 milliseconds, configured in ``pysubtask/defaults_config.py: burst_mode.expire_milli``). This is purely an optional fine-tuning efficiency, helpful if your specific use case allows for it. The data is being 'buffered up' any ways, in regular 'non-burst' mode; this feature encourages a larger amount of data to be transferred with a reduced number of Internet transactions during a 'burst', provided you can wait a little longer for it. The key, configurable, experimental detail of this feature is detecting when a burst is occurring or beginning. This version 1 uses a rudimentary algorithm of measuring time between notify calls; if a certain number of _**consecutive**_ notifies are called below a specified 'trigger' time between them, a 'burst' is recognized as starting (triggered), and the burst ends (the data is notified) when it expires or a notify is called over (slower) than the 'trigger' time (these burst mode defaults are configured in ``pysubtask/defaults_config.py: burst_mode.*``). Important detail: Using this option, if the last new data notification ends in a 'burst', pending data that has not been notified to the subtask (i.e.: has not yet been transferred, etc.) could be left in the data file (i.e.: no new data has come along to flush it out, etc.). It is up to the user to call ``master.check_pending_notifications()`` on a periodic timer in their main (master) app to check for and flush (notify) possible pending data.

Note: this master side 'burst mode' feature is not quite the same as a subtask side 'exponential back off' feature (see To Do below).

### To Do

- ``demo.py`` could probably be made into an official test module, moved into a tests folder, and made to work with pytest (including a setyp.py install section for tests)
- Possible feature: Implement an 'exponential back-off' algorithm in the subtask-side (child) of the S/FTP and Dropbox extension classes. This would be slightly different from 'Burst mode' (task master / parent side), with the objective being to reduce the total number of transfers / transactions over a long period (i.e.: 12 hours), as opposed to just reducing some transfers during a 'burst' of data notifications. This feature would have the secondary goal of avoiding surpassing host transaction limits (i.e.: Dropbox upload limits per day, etc.).
- Possible enhancement: The 'burst detection' algorithm could be made more robust if it considered number of bytes being written to the data file(s), possibly replacing or as an alternative to frequency of notifications.

### Dependencies

- ``pysftp``
- ``dropbox``

### Tests

- Platforms tested: **Python 3.6** on **Raspbian**, **Ubuntu 18.10**, **Windows 10**

### Dev Notes

The following dev topics may or may not result in future changes...

- _To CLI or not to CLI_: Even though `pysubtask` has a CLI ``demo.py`` test app; and it's master class utilizes Popen, the command line, and ``parse_args()`` to so spawn subtasks (child processes); it alone is not intended to be an actual CLI utility (as its main user interface). It is primarily an API / utility class patttern for integration into other Python applications. So, it currently does not have a typical CLI ``setup.py`` installation, with CLI entry points, synonyms, etc. This could change in a future version though.
- _The multiple main()'s_: Unique to the way this pattern spawns a separate Python env for the subtask, a separate ``main()`` is required per subtask module. Attempts to use a 'shared main()' in this specific pattern typically results in a ``ImportError: attempted relative import with no known parent package`` 'Catch 22' import issue after spawning the subtask.
- _Doing away with the Master classes in the extension modules, replacing with functions_: With the exception of the ``BaseMaster``, extension Master classes are light, almost simply wrapper classes. Because of this, it is possible that they might be elimanted and replaced with a function. But, there still might be use cases for custom logic to be added to the master, in which case, a master class is useful since the base class (``BaseMaster``) is used to store state data across member function calls.

### Authors, Contributors, etc.

Version 1 of `pysubtask` was designed and written by [David Jacobson](http://blog.jacobsonhome.com/), with many thanks to [Darryl Agostinelli](http://www.darrylagostinelli.com/) for extensive refactoring and general Python assistance.

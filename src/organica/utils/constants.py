"""
This module contains constants that are initialized during
application startup and should not be changed during executing.
"""

"""
Path of directory where main executable (or main.py file) is located.
Dont use QCoreApplication.applicationDirPath as it returns path to
interpreter executable.
"""
app_dir = None

"""
Indicates that application is running in portable mode. While running in
portable mode, application should avoid from any changes in system.
"""
is_portable = False

"""
Data directory is a special folder where application settings and other
application-related files are kept. When Organica is running in portable mode,
this directory is named 'data' and located near application executable. Otherwise
this directory is located in system-defined user directory.
"""
data_dir = None

"""
Thread in context of which live all gui objects. Application code should
avoid manipulating gui from other threads.
"""
gui_thread = None

"""
Use Qt.DirectConnection instead of Qt.QueuedConnection in sets.Set classes.
"""
disable_set_queued_connections = False

debug_plugins = True

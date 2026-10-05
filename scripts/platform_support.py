"""Small OS boundary for local coordination; no third-party dependencies.

Locks are held until their file handle closes. Windows locks byte zero; every
participant must use this module. PID checks are read-only and never signal a
Windows process. POSIX permissions are not a substitute for Windows user ACLs.
"""
import errno
import os
import subprocess
import time

IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    import msvcrt
else:
    import fcntl


def acquire_lock(handle, *, blocking=True):
    """Acquire an exclusive lock, raising BlockingIOError for contention."""
    if not IS_WINDOWS:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    # Windows permits locking beyond EOF, so no write/initialization race is
    # needed. Always reset the byte offset before locking an append-open file.
    while True:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            if not blocking:
                raise BlockingIOError(errno.EAGAIN, 'Coordination lock is held') from exc
            time.sleep(0.05)


def detached_process_options():
    """Detach an owned worker while keeping explicit redirected stdio."""
    if IS_WINDOWS:
        return {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                'close_fds': True}
    return {'start_new_session': True, 'close_fds': True}


def process_alive(pid):
    """Conservative read-only PID probe; a reused PID may delay recovery."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if IS_WINDOWS:
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _windows_process_alive(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: PID does not exist
            return False
        if error == 5:  # ERROR_ACCESS_DENIED: conservatively consider it alive
            return True
        raise ctypes.WinError(error)
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        if result == 0x00000102:  # WAIT_TIMEOUT: still running
            return True
        if result == 0:  # WAIT_OBJECT_0: exited
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def sync_directory(path):
    """Persist rename metadata on POSIX; Windows cannot fsync directory FDs.

    Windows still gets a flushed file and atomic replacement. This does not
    claim power-loss durability for directory metadata on Windows.
    """
    if IS_WINDOWS:
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

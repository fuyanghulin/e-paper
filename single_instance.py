"""Keep one dashboard per Windows session and signal it to show its window."""
import ctypes
from ctypes import wintypes
import threading


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL

NAME = r'Local\EpaperDashboard_7E654C63'
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0


class SingleInstance:
    def __init__(self):
        ctypes.set_last_error(0)
        self.mutex = kernel32.CreateMutexW(None, False, NAME + '_mutex')
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        self.event = kernel32.CreateEventW(None, False, False, NAME + '_show')
        if not self.event:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(self.mutex)
            raise ctypes.WinError(error)
        self.stopping = threading.Event()
        self.thread = None

    def notify_existing(self):
        if not kernel32.SetEvent(self.event):
            raise ctypes.WinError(ctypes.get_last_error())

    def listen(self, events):
        def run():
            while not self.stopping.is_set():
                if kernel32.WaitForSingleObject(self.event, 500) == WAIT_OBJECT_0:
                    if not self.stopping.is_set():
                        events.put(('show_window', None))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        if self.thread:
            kernel32.SetEvent(self.event)
            self.thread.join()
        kernel32.CloseHandle(self.event)
        kernel32.CloseHandle(self.mutex)

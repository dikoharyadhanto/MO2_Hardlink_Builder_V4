import os
import ctypes
from ctypes import wintypes

# Windows Constants
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
HIGH_PRIORITY_CLASS = 0x00000080

# I/O Priority Constants
ProcessIoPriority = 21

def set_priority(cpu=True, io=True):
    """
    Sets the current process to High CPU and/or High I/O priority.
    """
    if os.name != 'nt':
        return False

    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        
        # 1. Set CPU Priority to High
        if cpu:
            ctypes.windll.kernel32.SetPriorityClass(handle, HIGH_PRIORITY_CLASS)
        
        # 2. Set I/O Priority
        # I/O Priority levels: 0=Very Low, 1=Low, 2=Normal, 3=High
        io_priority = ctypes.c_int(3 if io else 2)
        
        # NtSetInformationProcess(ProcessHandle, ProcessInformationClass, ProcessInformation, ProcessInformationLength)
        status = ctypes.windll.ntdll.NtSetInformationProcess(
            handle,
            ProcessIoPriority,
            ctypes.byref(io_priority),
            ctypes.sizeof(io_priority)
        )
        
        return True
    except Exception as e:
        print(f"[!] Failed to set process priority: {e}")
        return False

def set_affinity(mask):
    """
    Sets the CPU affinity for the current process.
    mask: bitmask (integer)
    """
    if os.name != 'nt' or not mask:
        return False

    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        # SetProcessAffinityMask(HANDLE hProcess, DWORD_PTR dwProcessAffinityMask)
        res = ctypes.windll.kernel32.SetProcessAffinityMask(handle, ctypes.c_size_t(mask))
        return res != 0
    except Exception as e:
        print(f"[!] Failed to set CPU affinity: {e}")
        return False

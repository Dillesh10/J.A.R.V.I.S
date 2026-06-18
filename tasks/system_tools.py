from datetime import datetime
import platform
import socket


def get_current_datetime() -> str:
    """
    Returns the current local date, time, day of the week, and timezone.
    Use this whenever the user asks what time it is, what day it is, or the current date.
    """
    now = datetime.now()
    return (
        f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Current time: {now.strftime('%I:%M:%S %p')}\n"
        f"Timezone: Local system time"
    )


def get_system_info() -> str:
    """
    Returns basic system information such as OS, hostname, and Python version.
    Use this if the user asks about their computer or system.
    """
    try:
        return (
            f"OS: {platform.system()} {platform.release()} ({platform.version()})\n"
            f"Machine: {platform.machine()}\n"
            f"Hostname: {socket.gethostname()}\n"
            f"Processor: {platform.processor()}"
        )
    except Exception as e:
        return f"Error fetching system info: {str(e)}"


SYSTEM_TOOLS = [get_current_datetime, get_system_info]

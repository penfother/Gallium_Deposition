import datetime
import os
from zaber_motion import Library, LogOutputMode
# ----------------------------------------------------------------------------------
# LOG SETUP
# ----------------------------------------------------------------------------------
def setup_logging() -> str:
    '''Directs Zaber library logs to a timestamped file for the session.'''
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"session{session_timestamp}.log")
    Library.set_log_output(LogOutputMode.FILE, log_path)
    return log_path

def log_move(file_path: str, device_label: str, action: str, value: float = None):
    '''Logs a movement command with a timestamp.'''
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if value is not None:
        line = f"{timestamp} | {action:<12} | {device_label:<10} | {value:>8.4f} mm\n"
    else:
        line = f"{timestamp} | {action:<12} | {device_label:<10}\n"
    with open(file_path, "a") as f:
        f.write(line)
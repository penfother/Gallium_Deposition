import datetime
from zaber_motion import Library, LogOutputMode
# ----------------------------------------------------------------------------------
# LOG SETUP
# ----------------------------------------------------------------------------------
def setup_logging() -> str:
    '''Directs Zaber library logs to a timestamped file for the session.'''
    session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path= f"session{session_timestamp}.log"
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
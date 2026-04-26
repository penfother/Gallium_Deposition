import sys
import datetime
import os
from zaber_motion import Library, LogOutputMode
# ----------------------------------------------------------------------------------
# LOG SETUP
# ----------------------------------------------------------------------------------
def log_move(file_path: str, device_label: str, action: str, value: float = None):
    '''Logs a movement command with a timestamp.'''
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if value is not None:
        line = f"{timestamp} | {action:<12} | {device_label:<10} | {value:>8.4f} mm\n"
    else:
        line = f"{timestamp} | {action:<12} | {device_label:<10}\n"
    with open(file_path, "a") as f:
        f.write(line)

# ----------------------------------------------------------------------------------
# SPLIT LOGGING — zaber_pure (raw library) + readable (terminal mirror)
# ----------------------------------------------------------------------------------
def setup_zaber_log() -> str:
    '''Directs Zaber library output to logs/zaber_pure/ — debug only, not human-readable.'''
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "zaber_pure")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"zaber_{timestamp}.log")
    Library.set_log_output(LogOutputMode.FILE, path)
    return path

def setup_readable_log() -> str:
    '''Creates the human-readable session log file path. Returns the path to be used by TeeStdout and log_move.'''
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "readable")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"readable_{timestamp}.log")
    return path

class TeeStdout:
    '''Mirrors stdout to a file with a timestamp prepended to every line.
    Terminal still looks normal; log file gets [YYYY-MM-DD HH:MM:SS.mmm] on each line.'''
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, "a", buffering=1)  # line-buffered
        self._at_line_start = True

    def write(self, message):
        self.terminal.write(message)
        for char in message:
            if self._at_line_start and char != '\n':
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                self.log.write(f"[{ts}] ")
                self._at_line_start = False
            self.log.write(char)
            if char == '\n':
                self._at_line_start = True

    def flush(self):
        self.terminal.flush()
        self.log.flush()
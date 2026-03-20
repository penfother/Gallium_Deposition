import sys
import keyboard
import datetime
import msvcrt
import numpy as np

from typing import Dict

from zaber_motion.ascii import Connection
from zaber_motion import Units, Tools, Library, LogOutputMode

# ----------------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------------
# Ensures consistent mapping of devices
SERIAL_TO_LABEL = {
    38205: "stage_z", # size 50mm
    38209: "stage_y", # size 200mm
    38207: "stage_x", # size 100mm
    38206: "stage_s" # size 50mm (syringe)
}

# This is implemented for ASCII level commands, read ASCII Zaber library (ver. 6.32.) for more
# information
LABEL_TO_ADDRESS = {
    "stage_x": 1,       
    "stage_y": 2,
    "stage_z": 3,
    "stage_s": 4,
}

# Syringe variables -> SET BEFORE USE
SYRINGE_INNER_DIAMETER_MM = 12.0 # mm
NOZZLE_INNER_DIAMETER_MM = 0.06 # mm

# ----------------------------------------------------------------------------------
# EMERGENCY STOP
# ----------------------------------------------------------------------------------
def emergency_stop(connection: Connection) -> None:
    '''Stops all axes immediately.'''
    print("\n EMERGENCY STOP triggered! Stopping all motion...")
    connection.stop_all()

def setup_escape_listener(connection: Connection) -> None:
    '''Bind ESC to immediate stop. Runs in-process''' 
    def on_escape():
        emergency_stop(connection)

    keyboard.add_hotkey("esc", on_escape)
    print("Emergency stop enabled - press ESC anytime.")

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

# ----------------------------------------------------------------------------------
#  CONNECTION
# ----------------------------------------------------------------------------------
def connect_auto() -> Connection:
    '''Scans available ports and returns the port where Zaber devices are conected'''
    ports = Tools.list_serial_ports()
    for port in ports:
        try:
            conn = Connection.open_serial_port(port)
            devices = conn.detect_devices()
            if devices:
                print(f"Zaber device found on {port}")
                return conn  # return the open connection
        except Exception:
            pass
    raise RuntimeError("No Zaber devices detected on any port.")

# -----------------------------------------------------------------------------------
#  HELP
# -----------------------------------------------------------------------------------
def print_help() -> None:
    '''Prints available commands.'''
    print("Commands:")
    print("  move x 10                      -> relative move")
    print("  move abs x 50                  -> absolute move")
    print("  home x                         -> home axis")
    print("  home all                       -> home all stages")
    print("  sethome x                      -> mark current pos as home")
    print("  speed x 2.5                    -> set speed mm/s")
    print("  getspeed x                     -> read speed")
    print("  syringe dispense 1             -> dispense syringe")
    print("  syringe retract 1              -> retract syringe")
    print("  syringe speed 2                -> set syringe speed")
    print("  syringe pressure 30            -> set syringe pressure (0-70)")
    print("  setstart                       -> saves the current position for x y and z axis for later deposition")
    print("  makeline 10 x 2 0.001 0.01     -> line 10mm in x, v_stage=2mm/s, Q=0.001mm³/s, h0=0.01mm")
    print("  approach x 0.05                -> approach stage x in increment 0.05")
    print("  exit                           -> quit")

# ----------------------------------------------------------------------------------
# DEVICE CLASS
# ----------------------------------------------------------------------------------
class ZaberDevice:
    ''' Wrapper for the Zaber device'''
    def __init__(self, label: str, axis, connection, device):
        # General information
        self.label = label
        self.axis = axis
        self.connection = connection
        self.device = device

        # Start position for deposition
        self.start_position = 0.0

        # Movement limits
        self.min_pos = device.settings.get("limit.min", unit=Units.LENGTH_MILLIMETRES)
        self.max_pos = device.settings.get("limit.max", unit=Units.LENGTH_MILLIMETRES)

        # Speed profiles
        self.speed_profiles = {}
        self.active_profile = None
        self.default_profile()

    # -------------------- SPEED PROFILES -----------------------------
    def default_profile(self):
        '''Create a default speed profile if none exists and activate it.'''
        if "default" not in self.speed_profiles:
            # default velocity 1 mm/s, acceleration 0
            self.speed_profiles["default"] = {"vel": 1.0, "acc": 0.0, "unit": Units.VELOCITY_MILLIMETRES_PER_SECOND}
        self.active_profile = self.speed_profiles["default"]
        self._push_profile()

    # Create profile
    def set_profile(self, name: str, velocity: float, acceleration: float = 0.0):
        '''Creates a named speed profile.'''
        self.speed_profiles[name] = {"vel": velocity, "acc": acceleration}
    
    # Set profile to use
    def use_profile(self, name: str):
        '''Sets the speed profile to be used.'''
        if name not in self.speed_profiles:
            raise ValueError(f"Speed profile '{name}' not found for {self.label}")
        self.active_profile = self.speed_profiles[name]
        self._push_profile()

    def _push_profile(self):
        '''Pushes active profile to hardware.'''
        self.axis.settings.set(
            "maxspeed",
            self.active_profile["vel"],
            unit = Units.VELOCITY_MILLIMETRES_PER_SECOND
        )
        self.axis.settings.set(
            "accel",
            self.active_profile["acc"],
            unit=Units.ACCELERATION_MILLIMETRES_PER_SECOND_SQUARED
        )

    # Define speed
    def set_speed(self, mm_per_s: float):
        '''Updates active profile speed and pushes to hardware.'''
        self.active_profile["vel"] = mm_per_s
        self._push_profile()

    # Fetch current speed profile
    def get_speed(self) -> float:
        '''Fetches the current device speed profile.'''
        if not self.active_profile:
            return 0
        return self.active_profile["vel"]

    # -------------------- MOTION -----------------------------
    def check_limit(self, move: float, relative=True) -> bool:
        '''Verifies if the movement is within possible axis movement.'''
        pos = self.position()
        target = pos + move if relative else move
        if target < self.min_pos or target > self.max_pos:
            print(f"Movement out of bounds: {target} mm")
            return False
        return True

    def move_to(self, position_native: int, wait: bool = True):
        '''Moves device to defined position in mm away from home.'''
        self.axis.move_absolute(
            position_native,
            unit=Units.LENGTH_MILLIMETRES,
            wait_until_idle =wait,
        )
    
    def move_abs(self, mm: float, wait=False):
        '''Moves the device to a defined position in mm.'''
        if not self.check_limit(mm, relative=False):
            return False
        self.move_to(mm, wait)

    def move_rel(self, mm: float, wait=False):
        '''Moves the device relative to its current position.'''
        if not self.check_limit(mm, relative=True):
            return False

        self.axis.move_relative(
            mm,
            unit=Units.LENGTH_MILLIMETRES,
            wait_until_idle=wait
        )

    # -------------------- POSITIONING -----------------------------
    def position(self) -> float:
        '''Returns device position in mm.'''
        pos = self.axis.get_position(unit = Units.LENGTH_MILLIMETRES)
        return pos

    def home(self):
        '''Homes device.'''
        self.axis.home()

    def stop(self):
        '''Stops device.'''
        self.axis.stop()

    def set_home_here(self):
        '''Sets home for the device. Not used currently.'''
        self.axis.set_home()

    def set_start(self):
        self.start_position = self.position()

    # -------------------- SYRINGE ----------------------------- 
    def is_syringe(self) -> bool:
        '''Returns true if this device is the syringe pump.'''
        return self.label == "stage_s"
    
    def set_pressure(self, run: float, hold: float = 15) -> None:
        '''Sets syringe motor current as pressure proxy.
        run: active current during motion (0-70)
        hold: current when stationary (0-70), default 15'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        self.device.settings.set("driver.current.run", run)
        self.device.settings.set("driver.current.hold", hold)
        print(f"Pressure set -> run: {run}, hold: {hold}")

    def syringe_dispense(self, mm: float, wait: bool = False):
        '''Pump (positive direction). Uses syringe profile.'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        if not self.check_limit(mm, relative=False):
            return False
        self.axis.move_relative(
            mm,
            unit=Units.LENGTH_MILLIMETRES,
        )

    def syringe_retract(self, mm: float, wait: bool = False):
        '''Retract (negative direction). Uses syringe profile.'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        if not self.check_limit(-abs(mm), relative=True):
            return False
        self.axis.move_relative(
                -abs(mm),
                unit=Units.LENGTH_MILLIMETRES,
                wait_until_idle=wait
        )

# ----------------------------------------------------------------------------------
# DEPOSITION CALCULATION
# ----------------------------------------------------------------------------------
def volume_to_plunger_travel(volume_ul: float) -> float:
    '''Converts dispensed volume to plunger travel in mm.'''

    if SYRINGE_INNER_DIAMETER_MM <= 0:
        raise ValueError("SYRINGE_INNER_DIAMETER_MM must be set before dispensing.")
    radius_mm= SYRINGE_INNER_DIAMETER_MM / 2
    area_mm2 = 3.14159265 * (radius_mm ** 2)
    travel_mm = volume_ul / area_mm2
    return travel_mm

# -----------------------------------------------------------------------------------
# DOTS -> Not fully implemented
# -----------------------------------------------------------------------------------

def make_dots(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
              dots: int, spacing: float, dispense_amount: float) -> None:
    '''From the start position dispenses dots along the desired axis'''
    # TODO: Fix the start position capability
    # TODO: Change the speed profile for the printing of dots
    # TODO: do the z approach for each dot
    # TODO: Limit the dispensing amount in a range
    # TODO: Make this give back a string that gives the error or if it does everything
    #       correctly give back printed

    stage_x.set_speed(0.2)



    for i in range(dots):
        # Approach 2 mm to the stage
        stage_z.move_rel(2, wait=True)
        syringe.syringe_dispense(dispense_amount, wait=True)

        stage_z.move_rel(-2, wait=True)
        if i < dots - 1:
            stage_x.move_rel(spacing, wait=True)

    stage_x.home()

# -----------------------------------------------------------------------------------
# MAKE LINE
# -----------------------------------------------------------------------------------
def make_line(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
              start_pos: list, line_length: float, direction: str,
              v_stage: float, Q: float, h0: float) -> None:
    '''Deposits a line from start_pos in given direction.
    v_stage: XY stage speed (mm/s)
    Q: flow rate (mm³/s)
    h0: standoff distance (mm)'''

    # TODO: Implement the touch sensor for the height adjustment
    # TODO: 

    # v_plunger = Q / (π × (D_barrel/2)²) -> continuity equation
    v_plunger = Q / (3.14159265 * ((SYRINGE_INNER_DIAMETER_MM / 2) ** 2))

    # Set speeds
    stage_x.set_speed(v_stage)
    stage_y.set_speed(v_stage)
    stage_z.set_speed(0.2)
    syringe.set_speed(v_plunger)

    # Move XY to start position
    stage_x.move_abs(start_pos[0], wait=True)
    stage_y.move_abs(start_pos[1], wait=True)

    # Drop Z to h0
    stage_z.move_abs(h0, wait=True)

    # Start syringe and line simultaneously
    syringe.syringe_dispense(line_length, wait=False)

    match direction:
        case "x":
            if not stage_x.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_x.move_rel(line_length, wait=True)
        case "y":
            if not stage_y.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_y.move_rel(line_length, wait=True)
        case _:
            print("Invalid direction.")
            syringe.stop()
            stage_z.move_rel(-1, wait=True)
            return

    # Stop syringe and raise Z
    syringe.stop()
    stage_z.move_rel(-5, wait=True)

# -----------------------------------------------------------------------------------
# SWEEP -> not fully implemented
# -----------------------------------------------------------------------------------
def sweep(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
          start_pos: list, line_length: float, direction: str,
          split: float, fixed: dict, swept: dict) -> None:
    '''Runs a 2-parameter sweep of deposition lines.
    fixed: dict of fixed parameters e.g. {"v_stage": 2}
    swept: dict of swept parameters e.g. {"Q": (0.001, 0.01, 0.001), "h0": (0.005, 0.015, 0.001)}'''

    # gap between lines within a group
    gap_width = 3 * NOZZLE_INNER_DIAMETER_MM

    # unpack fixed parameter
    v_stage = fixed.get("v_stage", 1.0)
    Q       = fixed.get("Q", 0.001)
    h0      = fixed.get("h0", 0.01)

    # unpack swept parameters
    param_names = list(swept.keys())
    if len(param_names) != 2:
        print("Sweep requires exactly 2 swept parameters.")
        return

    # outer and inner parameter ranges
    outer_name = param_names[0]
    inner_name = param_names[1]

    outer_start, outer_end, outer_step = swept[outer_name]
    inner_start, inner_end, inner_step = swept[inner_name]

    outer_range = np.arange(outer_start, outer_end + outer_step, outer_step)
    inner_range = np.arange(inner_start, inner_end + inner_step, inner_step)

    current_pos = start_pos.copy()
    n = 0

    for outer_val in outer_range:
        # set outer parameter
        if outer_name == "v_stage": v_stage = outer_val
        elif outer_name == "Q":     Q = outer_val
        elif outer_name == "h0":    h0 = outer_val

        for inner_val in inner_range:
            # set inner parameter
            if inner_name == "v_stage": v_stage = inner_val
            elif inner_name == "Q":     Q = inner_val
            elif inner_name == "h0":    h0 = inner_val

            # alternate direction for serpentine
            actual_length = line_length if n % 2 == 0 else -line_length

            make_line(stage_x, stage_y, stage_z, syringe,
                      current_pos, actual_length, direction,
                      v_stage, Q, h0)

            # reposition by gap_width perpendicular to direction
            if direction in ["x", "X"]:
                current_pos[1] += gap_width
            elif direction in ["y", "Y"]:
                current_pos[0] += gap_width

            n += 1

        # split between outer groups
        if direction in ["x", "X"]:
            current_pos[1] += split
        elif direction in ["y", "Y"]:
            current_pos[0] += split
        
# -----------------------------------------------------------------------------------
# APPROACH
# -----------------------------------------------------------------------------------
def approach(stage: ZaberDevice, step_mm: float) -> None:
    '''Manual fine control for stage'''
    print("Manual approach mode activated. Use W/S to move, X to exit.")

    # Loop
    while True:
        event = keyboard.read_event()

        if event.event_type != "down":
            continue

        key = event.name

        match key:
            case "w":
                if not stage.check_limit(step_mm):
                    return
                stage.move_rel(step_mm, wait=True)
            case "s":
                if not stage.check_limit(-step_mm):
                    return
                stage.move_rel(-step_mm, wait=True)
            case "x":
                break
    
    while msvcrt.kbhit():
        msvcrt.getch()

# -----------------------------------------------------------------------------------
# COMMAND HANDLING
# -----------------------------------------------------------------------------------
def handle_command(line: str, stages: Dict[str, ZaberDevice], log_path: str) -> bool:
    '''Parse and execute a single-line command. Returns False to exit loop.'''

    # Clean input
    partcmd = line.strip().split()
    if not partcmd:
        return True

    # Look at first part of input
    cmd = partcmd[0].lower()

    match cmd:

        # Exit
        case "exit":
            print("Exiting program...")
            return False
        
        # Help
        case "help":
            print_help()
            return True
        
        # Move
        case "move":
            if len(partcmd) < 3:  # Wrong usage
                print("Usage: move <axis label> <units> OR move abs <axis> <mm>")
                return True
            
            if partcmd[1] == "abs":  # Absolute movement
                axis = str(partcmd[2])
                mm = float(partcmd[3])
                dev = stages[f"stage_{axis}"]
                log_move(log_path, f"stage_{axis}", "absolute", mm)
                dev.move_abs(mm)
                print(f"Moved {axis} to abs {mm} mm")
                return True

            else:  # Relative movement
                axis = partcmd[1]
                mm = float(partcmd[2])
                dev = stages[f"stage_{axis}"]
                log_move(log_path, f"stage_{axis}", "relative", mm)
                dev.move_rel(mm)
                print(f"Moved {axis} relative {mm} mm")
                return True

        # Home
        case "home":
            if len(partcmd) == 2 and partcmd[1] == "all": # All devices
                log_move(log_path, "all", "home")
                for dev in stages.values():
                    dev.home()
                print("All devices homed.")
                return True
            
            axis = partcmd[1] # One device
            log_move(log_path, f"stage_{axis}", "home")
            dev = stages[f"stage_{axis}"]
            dev.home()
            return True
        
        # Set Home Position
        case "sethome":
            axis = partcmd[1]
            dev = stages[f"stage_{axis}"]
            dev.set_home_here()
            print(f"Set home for {axis}")
            return True
        
        # Set Start
        case "setstart":
            for stage in stages.values():
                stage.set_start()
            print("Start position set for all stages.")
            return True

        # Speed set in mm/s
        case "speed":
            axis = partcmd[1]
            speed = float(partcmd[2])
            dev = stages[f"stage_{axis}"]
            dev.set_speed(speed)
            print(f"Set speed of {axis} to {speed} mm/s")
            return True

        # Speed get
        case "getspeed":
            axis = partcmd[1]
            dev = stages[f"stage_{axis}"]
            print(dev.get_speed())
            return True
        
        # Syringe
        case "syringe":
            if len(partcmd) < 3:
                print("Usage: syringe <dispense/retract/speed> <value>")
                return True

            action = partcmd[1].lower()
            dev = stages["stage_s"]  # always target syringe

            match action:
                # Dispense (positive)
                case "dispense":
                    mm = float(partcmd[2])
                    log_move(log_path, "stage_s", "dispense", mm)
                    dev.syringe_dispense(mm)
                    print(f"Syringe dispensed {mm} units.")
                    return True

                # Retract (negative)
                case "retract":
                    mm = float(partcmd[2])
                    log_move(log_path, "stage_s", "retract", mm)
                    dev.syringe_retract(mm)
                    print(f"Syringe retracted {mm} units.")
                    return True

                # Set syringe speed (update active profile velocity)
                case "speed":
                    speed = float(partcmd[2])
                    dev.set_speed(speed)
                    print(f"Syringe speed set to {speed} mm/s.")
                    return True
                
                # Syring e presure
                case "pressure":
                    run = float(partcmd[2])
                    dev.set_pressure(run)
                    print(f"Syringe pressure set to {run}")
                    return True

                # Unknown syringe action
                case _:
                    print(f"Unknown syringe command: {action}")
                    return True

        # Approach
        case "approach":
            dev = stages[f"stage_{partcmd[1]}"]
            step_mm = float(partcmd[2])
            approach(dev, step_mm)
            return True
        
        # Make dots -> makedots 1 2 3
        case "makedots":
            number_of_dots = int(partcmd[1])
            dots_spacing = float(partcmd[2])
            dot_amount = float(partcmd[3])
            make_dots(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"], int(number_of_dots), float(dots_spacing), float(dot_amount))
            # TODO: add sethome connection to determine the starting position for the device
            # TODO: add error handling for list index out of range
            return True
        
        # Make line -> makeline 
        case "makeline":
            if len(partcmd) != 6:
                print("Usage: makeline <length> <direction> <v_stage> <Q> <h0>")
                return True
            line_length = float(partcmd[1])
            direction = str(partcmd[2])
            v_stage = float(partcmd[3])
            Q = float(partcmd[4])
            h0 = float(partcmd[5])
            start_pos = [
                float(stages["stage_x"].start_position),
                float(stages["stage_y"].start_position),
                float(stages["stage_z"].start_position)
            ]
            make_line(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"],
                      start_pos, line_length, direction, v_stage, Q, h0)
            return True

        # Sweep
        case "sweep":
            line_length = float(partcmd[1])
            direction = str(partcmd[2])
            split = float(partcmd[3])
            
            # Parse fixed and swept parameters
            fixed = {}
            swept = {}
            for param in partcmd[4:]:
                if "=(" in param:
                    # swept parameter e.g. Q=(0.001,0.01,0.001)
                    name, values = param.split("=(")
                    start, end, step = map(float, values.strip(")").split(","))
                    swept[name] = (start, end, step)
                elif "=" in param:
                    # fixed parameter e.g. v_stage=2
                    name, value = param.split("=")
                    fixed[name] = float(value)
            
            start_pos = [
                float(stages["stage_x"].start_position),
                float(stages["stage_y"].start_position),
                float(stages["stage_z"].start_position)
            ]
            
            sweep(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"],
                start_pos, line_length, direction, split, fixed, swept)
            return True
        
        # Unknown
        case _:
            print(f"Unknown command: {line}")
            return True 

# -----------------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------------
def main() -> None:
    
    # starts logging session
    log_path = setup_logging()
    print(f"Logging to {log_path}")

    try:
        conn = connect_auto()  # Find connection
        # keep the connection open for the session
        with conn:
            devices = conn.detect_devices()
            stages: Dict[str, ZaberDevice] = {}

    #  Label devices according to their serial numbers
            for device in devices:
                serial = device.serial_number
                if serial in SERIAL_TO_LABEL:
                    label = SERIAL_TO_LABEL[serial]
                    LABEL_TO_ADDRESS[label] = device.device_address
                    stages[label] = ZaberDevice(label, device.get_axis(1), conn, device)

            # Check for any missing devices
            missing = [label for label in SERIAL_TO_LABEL.values() if label not in stages]
            if missing:
                raise RuntimeError(f"Missing devices: {missing}")

            # EMERGENCY STOP & HELP
            setup_escape_listener(conn)
            print_help()

            # Home at start
            conn.home_all(wait_until_idle=True)

        # Command loop
            while True:
                user_input = input("Command > ")
                if not handle_command(user_input, stages, log_path):
                    break

    # Escape pressed
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping all devices...")
        emergency_stop(conn)
        sys.exit(0)

    # Error handling
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

# ----------------------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    main()

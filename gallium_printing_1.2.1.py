import sys
import keyboard
from typing import Dict
from zaber_motion.ascii import Connection, DeviceSettings

from zaber_motion import Units, Tools
import msvcrt

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
    print("  move x 10              -> relative move")
    print("  move abs x 50          -> absolute move")
    print("  home x                 -> home axis")
    print("  home all               -> home all stages")
    print("  sethome x              -> mark current pos as home")
    print("  speed x 2.5            -> set speed mm/s")
    print("  getspeed x             -> read speed")
    print("  syringe dispense 1     -> dispense syringe")
    print("  syringe retract 1      -> retract syringe")
    print("  syringe speed 2        -> set syringe speed")
    print("  approach x 0.05        -> approach stage x in increment 0.05")
    print("  exit                   -> quit")

# ----------------------------------------------------------------------------------
# DEVICE CLASS
# ----------------------------------------------------------------------------------
class Device:
    ''' Wrapper for the Zaber device'''
    def __init__(self, label: str, axis, connection, device):
        # General information
        self.label = label
        self.axis = axis
        self.connection = connection

        # Movement limits
        self.min_pos = device.settings.get("limit.min", unit=Units.NATIVE)
        self.max_pos = device.settings.get("limit.max", unit=Units.NATIVE)

        # Speed profiles
        self.speed_profiles = {}
        self.active_profile = None
        self.default_profile()

    # -------------------- SPEED PROFILES -----------------------------
    def default_profile(self):
        '''Create a default speed profile if none exists and activate it.'''
        if "default" not in self.speed_profiles:
            # default velocity 1 mm/s, acceleration 0
            self.speed_profiles["default"] = {"vel": 1, "acc": 0, "unit": Units.VELOCITY_MILLIMETRES_PER_SECOND}
        if not self.active_profile:
            self.active_profile = self.speed_profiles["default"]

    # Create profile
    def set_profile(self, name: str, velocity: float, acceleration: float = 0, unit=Units.LENGTH_MILLIMETRES):
        self.speed_profiles[name] = {
            "vel":velocity, 
            "acc":acceleration, 
            "unit": unit}
    
    # Set profile to use
    def use_profile(self, name: str):
        if name not in self.speed_profiles:
            raise ValueError(f"Speed profile '{name}' not found for {self.label}")
        self.active_profile = self.speed_profiles[name]

    # --------------------- SPEED CONTROL ------------------------------
    # Define speed
    def set_speed(self, mm_per_s: float):
        if not self.active_profile:
            print("Warning: No active speed profile, set to default profile.")
            self.default_profile()
        self.active_profile["vel"] = mm_per_s
        self.active_profile["acc"] = 0
        self.active_profile["unit"] = Units.VELOCITY_MILLIMETRES_PER_SECOND
        return mm_per_s

    # Fetch current speed profile
    def get_speed(self) -> float:
        if not self.active_profile:
            return 0
        return self.active_profile["vel"]

    # -------------------- MOTION -----------------------------
    def check_limit(self, move: float) -> None:
        if move < self.min_pos or move > self.max_pos:
            print("Movement out of bounds.")
        
        return True


    def move_to(self, position_native: int, wait: bool = True):
        '''Moves device to defined NATIVE position'''
        if not self.active_profile:
            raise RuntimeError(f"No active speed profile selected for {self.label}")
        prof = self.active_profile

        self.axis.move_velocity(
            prof["vel"],
            unit = prof["unit"],
            acceleration = prof["acc"],
            acceleration_unit = prof["unit"]
        )

        self.axis.move_absolute(
            position_native,
            unit=Units.LENGTH_MILLIMETRES,
            wait_until_idle =wait,
            velocity=prof["vel"],
            velocity_unit=prof["unit"],
            acceleration=prof["acc"]
        )
    
    def move_abs(self, mm: float, wait=False):
        self.move_to(mm, wait)

    def move_rel(self, mm: float, wait=False):
        prof = self.active_profile

        self.axis.move_velocity(
            prof["vel"],
            unit = prof["unit"],
            acceleration = prof["acc"],
            acceleration_unit = prof["unit"]
        )
        self.axis.move_relative(
            mm,
            unit=Units.LENGTH_MILLIMETRES,
            wait_until_idle=wait
        )

    def home(self):
        self.axis.home()

    def stop(self):
        self.axis.stop()

    def set_home_here(self):
        self.axis.set_home()

    # -------------------- SYRINGE -----------------------------

    # TODO: correct velocities and accelerations
    # TODO: add volume calculation after getting the syringe
    # TODO: 

    def is_syringe(self) -> bool:
        '''Returns true if this device is the syringe pump.'''
        return self.label == "stage_s"

    def syringe_dispense(self, mm: float, wait: bool = False):
        '''Pump (positive direction). Uses syringe profile.'''

        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        
        if not self.active_profile:
            raise RuntimeError("No active speed profile selected for the syringe.")
        
        prof = self.active_profile

        # Set velocity first
        self.axis.move_velocity(
            prof["vel"],
            unit = prof["unit"],
            acceleration = prof["acc"],
            acceleration_unit = prof["unit"]
        )

        # Now movement
        self.axis.move_relative(
            mm,
            unit=Units.LENGTH_MICROMETRES,
            wait_until_idle=wait
        )

    def syringe_retract(self, mm: float, wait: bool = False):
        '''Retract (negative direction). Uses syringe profile.'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        
        if not self.active_profile:
            raise RuntimeError("No active speed profile selected for the syringe.")
        
        prof = self.active_profile

        # Set velocity first
        self.axis.move_velocity(
            prof["vel"],
            unit = prof["unit"],
            acceleration = prof["acc"],
            acceleration_unit = prof["unit"]
        )

        # Now movement
        self.axis.move_relative(
                -abs(mm),
                unit=Units.LENGTH_MILLIMETRES,
                wait_until_idle=wait
        )

# ----------------------------------------------------------------------------------
# SPEED PROFILES
# ----------------------------------------------------------------------------------


# -----------------------------------------------------------------------------------
# DOTS
# -----------------------------------------------------------------------------------

def make_dots(stage_x: Device, stage_y: Device, stage_z: Device, syringe: Device,
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
# DRAW LINE <---------- not implemented in parser
# -----------------------------------------------------------------------------------
#def liquid_amount(volume: float) -> None:
    #'Calculates the plunger travel dependant on the volume of liquid metal'




def draw_line(stage_x: Device, stage_y: Device, stage_z: Device, syringe: Device, 
              line_length: float) -> None:
    
    stage_x.set_speed(0.2)
    # Drop z
    stage_z.move_rel(1, wait=True) # Placeholder for the approach
    # Start dispensing
    syringe.set_speed(0.2)
    syringe.syringe_dispense(0.2)
    # Simultaneously start moving into x direction
    return True

# -----------------------------------------------------------------------------------
# APPROACH
# -----------------------------------------------------------------------------------
def approach(stage: Device, step_mm: float) -> None:
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
                stage.move_rel(step_mm, wait=True)
            case "s":
                stage.move_rel(-step_mm, wait=True)
            case "x":
                break
    
    while msvcrt.kbhit():
        msvcrt.getch()

# -----------------------------------------------------------------------------------
# COMMAND HANDLING
# -----------------------------------------------------------------------------------
def handle_command(line: str, stages: Dict[str, Device]) -> bool:
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
                axis = partcmd[2]
                mm = float(partcmd[3])
                dev = stages[f"stage_{axis}"]
                dev.move_abs(mm)
                print(f"Moved {axis} to abs {mm} mm")
                return True

            else:  # Relative movement
                axis = partcmd[1]
                mm = float(partcmd[2])
                dev = stages[f"stage_{axis}"]
                dev.move_rel(mm)
                print(f"Moved {axis} relative {mm} mm")
                return True

        # Home
        case "home":
            if len(partcmd) == 2 and partcmd[1] == "all": # All devices
                for dev in stages.values():
                    dev.home()
                print("All devices homed.")
                return True
            
            axis = partcmd[1] # One device
            dev = stages[f"stage_{axis}"]
            dev.home()
            return True
        
        # Set Home Position
        case "sethome":
            axis = partcmd[1]
            dev = stages[f"stage_{axis}"]
            dev.home()
            print(f"Homed {axis}")
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
        
        # ---------------- SYRINGE ----------------
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
                    dev.syringe_dispense(mm)
                    print(f"Syringe dispensed {mm} units.")
                    return True

                # Retract (negative)
                case "retract":
                    mm = float(partcmd[2])
                    dev.syringe_retract(mm)
                    print(f"Syringe retracted {mm} units.")
                    return True

                # Set syringe speed (update active profile velocity)
                case "speed":
                    speed = float(partcmd[2])
                    dev.set_speed(speed)
                    print(f"Syringe speed set to {speed} mm/s.")
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

        # Unknown
        case _:
            print(f"Unknown command: {line}")
            return True 

# -----------------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------------
def main() -> None:
    try:
        conn = connect_auto()  # Find connection
        # keep the connection open for the session
        with conn:
            devices = conn.detect_devices()
            stages: Dict[str, Device] = {}

    #  Label devices according to their serial numbers
            for device in devices:
                serial = device.serial_number
                if serial in SERIAL_TO_LABEL:
                    label = SERIAL_TO_LABEL[serial]
                    LABEL_TO_ADDRESS[label] = device.device_address
                    stages[label] = Device(label, device.get_axis(1), conn, device)
                    print(f"stage: {label}, max: {Device.max_pos}, min: {Device.min_pos}")

            # Check for any missing devices
            missing = [label for label in SERIAL_TO_LABEL.values() if label not in stages]
            if missing:
                raise RuntimeError(f"Missing devices: {missing}")

            # EMERGENCY STOP & HELP
            setup_escape_listener(stages)
            print_help()

            # Home at start
            conn.home_all(wait_until_idle=True)

        # Command loop
            while True:
                user_input = input("Command > ")
                if not handle_command(user_input, stages):
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
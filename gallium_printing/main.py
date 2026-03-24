import sys
import keyboard
import serial
import serial.tools.list_ports
import threading

from typing import Dict

from zaber_motion.ascii import Connection
from zaber_motion import Tools

from gallium_printing.core.zaber_wrapper import ZaberDevice
from gallium_printing.core.deposition import make_dots, make_line, sweep
from logging import log_move, setup_logging
from gallium_printing.core.contact import _contact_event, connect_arduino, _listen_arduino, run_approach, approach
from gallium_printing.config.constants import DEVICES, ARDUINO
from gallium_printing.core.substrate_mapping import SubstrateMap

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

def connect_arduino() -> serial.Serial:
    '''Scans available ports and returns the one where Arduino is connected.'''
    ports = serial.tools.list_ports.comports()
    for port in ports:
        try:
            ser = serial.Serial(port.device, ARDUINO["baud"], timeout= 2)
            ser.setDTR(False)
            ser.setDTR(True)
            line  = ser.readline().decode("utf-8").strip()
            if line == "READY":
                print(f"Arduino found on {port.device}")
                return ser
            ser.close()
        except Exception:
            pass
    raise RuntimeError("No Arduino detected on any port.")

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
    print("  touchdown                      -> measure substrate contact height (3x average)")
    print("  mappoint                       -> store current XYZ as a substrate corner")
    print("  mapshow                        -> show current substrate map")
    print("  mapclear                       -> reset substrate map")
    print("  exit                           -> quit")

# -----------------------------------------------------------------------------------
# COMMAND HANDLING
# -----------------------------------------------------------------------------------
def handle_command(line: str, stages: Dict[str, ZaberDevice], log_path: str, arduino: serial.Serial, substrate_map: SubstrateMap) -> bool:
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
        
        # Touchdown
        case "touchdown":
            z_contact = run_approach(stages["stage_z"], arduino, log_path)
            print(f"Substrate contact reference: {z_contact:.4f} mm")
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
                if serial in DEVICES["serial_to_label"]:
                    label = DEVICES["serial_to_label"][serial]
                    DEVICES["label_to_address"][label] = device.device_address
                    stages[label] = ZaberDevice(label, device.get_axis(1), conn, device)

            # Check for any missing devices
            missing = [label for label in DEVICES["serial_to_label"].values() if label not in stages]
            if missing:
                raise RuntimeError(f"Missing devices: {missing}")

            # EMERGENCY STOP & HELP
            setup_escape_listener(conn)
            print_help()

            # Home at start
            conn.home_all(wait_until_idle=True)
    
            # Arduino connection
            arduino = connect_arduino()
            listener = threading.Thread(target=_listen_arduino, args=(arduino, stages["stage_z"]), daemon=True)
            listener.start()

        # Command loop
            while True:
                user_input = input("Command > ")
                if not handle_command(user_input, stages, log_path, arduino):
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

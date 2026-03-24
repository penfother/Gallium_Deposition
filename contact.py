import threading
import serial

# ----------------------------------------------------------------------------------
# ARDUINO
# ----------------------------------------------------------------------------------

_contact_event = threading.event()

ARDUINO_PORT = "COM6"
ARDUINO_BAUD = 115200

def connect_arduino() -> serial.Serial:
    '''Opens serial connection to Arduino and waits for READY.'''
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
    print("Waiting for Arduino READY...")
    while True:
        line = arduino.readline().decode("utf-8").strip()
        if line == "READY":
            print("Arduino ready.")
            return arduino

def _listen_arduino(ser, axis):
    while True:
        line = ser.readilne().decode("utf-8").strip()
        if line:
            print(f"[Arduino] {line}")
        if line == "CONTACT":
            axis.stop()
            _contact_event.set()

# ----------------------------------------------------------------------------------
# SUBSTRATE CONTACT
# ----------------------------------------------------------------------------------
def approach_substrate(stage_z: ZaberDevice, arduino: serial.Serial) -> float:
    '''
    Fast travels Z to approach zone then slowly approaches substrate,
    detects contact via Arduino continuity signal, repeats N_MEASUREMENTS
    times and returns the average contact position in mm.
    '''
    print("Homing Z...")
    stage_z.home()
    print(f"Homed. Position: {stage_z.position():.4f} mm")

    print(f"Fast travel: {APPROACH["fast_distance"]} mm at {APPROACH["fast_speed"]} mm/s...")
    stage_z.set_speed(FAST_APPROACH_SPEED)
    stage_z.move_rel(FAST_APPROACH_DISTANCE, wait=True)
    print(f"Position: {stage_z.position():.4f} mm")

    measurements = []

    for i in range(N_MEASUREMENTS):
        print(f"\nMeasurement {i + 1}/{N_MEASUREMENTS} — approaching at {APPROACH_SPEED} mm/s...")
        _contact_event.clear()
        arduino.write(b'r')

        stage_z.set_current(RUN_CURRENT_APPROACH)
        stage_z.set_speed(APPROACH_SPEED)
        stage_z.move_rel(APPROACH_DISTANCE, wait=False)

        _contact_event.wait()

        pos = stage_z.position()
        measurements.append(pos)
        print(f"  Contact at: {pos:.4f} mm")

        if i < N_MEASUREMENTS - 1:
            stage_z.set_current(RUN_CURRENT_NORMAL)
            stage_z.set_speed(LIFT_SPEED)
            stage_z.move_rel(-LIFT_DISTANCE, wait=True)

    stage_z.set_current(RUN_CURRENT_NORMAL)
    arduino.write(b'r')

    average = sum(measurements) / len(measurements)
    print(f"\n--- Results ---")
    for i, m in enumerate(measurements):
        print(f"  Measurement {i + 1}: {m:.4f} mm")
    print(f"  Average:       {average:.4f} mm")
    print(f"  Spread:        {max(measurements) - min(measurements):.4f} mm")

    return average
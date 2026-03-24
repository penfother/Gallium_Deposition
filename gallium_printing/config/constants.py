# ----------------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------------
# Devices
DEVICES = {
    "serial_to_label": {
        38205: "stage_z", # size 50mm
        38209: "stage_y", # size 200mm
        38207: "stage_x", # size 100mm
        38206: "stage_s", # size 50mm (syringe)
    },

    "label_to_address": {
        "stage_x": 1,       
        "stage_y": 2,
        "stage_z": 3,
        "stage_s": 4,
    }
}

# Syringe
SYRINGE = {
    "barrel_inner_diameter_mm": 12.0,
    "nozzle_inner_diameter_mm": 0.06,
}

# Approach
APPROACH = {
    "fast_speed":        10.0,  # mm/s
    "fast_distance":     40.0,  # mm
    "speed":             0.02,  # mm/s
    "distance":          10.0,  # mm max slow travel
    "lift_distance":     1.0,   # mm between measurements
    "lift_speed":        2.0,   # mm/s
    "current_normal":    30,    # max for this device
    "current_approach":  17,    # low enough to stall on contact
    "n_measurements":    3,
}

# Arduino
ARDUINO = {
    "baud":              115200,
}
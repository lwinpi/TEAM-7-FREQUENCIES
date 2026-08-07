from machine import Pin, I2S
import math
import struct
import time


# ============================================================
# AIRFRET - CLEAN PRECOMPUTED NOTE ENGINE
# ============================================================


# ============================================================
# KEYPAD
# ============================================================

# Confirmed keypad wiring:
# Ribbon 1 -> GP2
# Ribbon 2 -> GP3
# Ribbon 3 -> GP4
# Ribbon 4 -> GP5
# Ribbon 5 -> GP6
# Ribbon 6 -> GP7
# Ribbon 7 -> GP8

ROW_GPIOS = [8, 7, 6, 5]
COL_GPIOS = [4, 3, 2]

KEY_LAYOUT = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["*", "0", "#"]
]

rows = []

for gpio in ROW_GPIOS:
    pin = Pin(gpio, Pin.OUT)
    pin.value(1)
    rows.append(pin)

columns = []

for gpio in COL_GPIOS:
    columns.append(
        Pin(gpio, Pin.IN, Pin.PULL_UP)
    )


# ============================================================
# MAX98357A
# ============================================================

# GP10 -> BCLK
# GP11 -> LRC
# GP12 -> DIN
#
# MAX SD  -> 3V3
# MAX VIN -> 5V / VBUS
# MAX GND -> GND

SAMPLE_RATE = 44100

audio = I2S(
    0,
    sck=Pin(10),
    ws=Pin(11),
    sd=Pin(12),
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=SAMPLE_RATE,
    ibuf=12000
)


# ============================================================
# EXACT MUSICAL NOTES
# ============================================================

NOTES = {
    "1": ("C4", 261.625565),
    "2": ("D4", 293.664768),
    "3": ("E4", 329.627557),
    "4": ("F4", 349.228231),
    "5": ("G4", 391.995436),
    "6": ("A4", 440.000000),
    "7": ("B4", 493.883301),
    "8": ("C5", 523.251131)
}


# ============================================================
# AUDIO SETTINGS
# ============================================================

# Lower = quieter/cleaner
# Start here before increasing it.
AMPLITUDE = 3000

# Number of complete waveform cycles in each stored buffer.
# Because the buffer contains complete cycles, it can repeat
# without producing a click at the loop boundary.
CYCLES_PER_BUFFER = 16

note_buffers = {}


# ============================================================
# BUILD NOTE BUFFER
# ============================================================

def make_note_buffer(frequency):

    # Choose number of samples so that this buffer contains
    # almost exactly 16 complete cycles.
    number_of_samples = int(
        round(
            CYCLES_PER_BUFFER
            * SAMPLE_RATE
            / frequency
        )
    )

    # The actual frequency is extremely close to requested
    # frequency, while giving us a seamless repeating buffer.
    actual_frequency = (
        CYCLES_PER_BUFFER
        * SAMPLE_RATE
        / number_of_samples
    )

    buffer = bytearray(
        number_of_samples * 4
    )

    for i in range(number_of_samples):

        phase = (
            2.0
            * math.pi
            * CYCLES_PER_BUFFER
            * i
            / number_of_samples
        )

        sample = int(
            AMPLITUDE
            * math.sin(phase)
        )

        struct.pack_into(
            "<hh",
            buffer,
            i * 4,
            sample,
            sample
        )

    return buffer, actual_frequency


# ============================================================
# PRECOMPUTE ALL EIGHT NOTES
# ============================================================

print()
print("Building clean AirFret notes...")

for key in NOTES:

    name, frequency = NOTES[key]

    buffer, actual_frequency = make_note_buffer(
        frequency
    )

    note_buffers[key] = buffer

    print(
        name,
        "target:",
        round(frequency, 3),
        "actual:",
        round(actual_frequency, 3),
        "Hz"
    )

print("Notes ready.")
print()


# ============================================================
# KEYPAD SCAN
# ============================================================

def scan_keypad():

    pressed = set()

    for row_index, active_row in enumerate(rows):

        for row in rows:
            row.value(1)

        active_row.value(0)

        time.sleep_us(50)

        for column_index, column in enumerate(columns):

            if column.value() == 0:

                key = KEY_LAYOUT[
                    row_index
                ][
                    column_index
                ]

                pressed.add(key)

        active_row.value(1)

    return pressed


# ============================================================
# SYSTEM STATE
# ============================================================

current_note_key = None
previous_keys = set()

silence = bytearray(1024)


# ============================================================
# START NOTE
# ============================================================

def start_note(key):

    global current_note_key

    if key not in NOTES:
        return

    current_note_key = key

    name, frequency = NOTES[key]

    print(
        "NOTE ON:",
        name
    )


# ============================================================
# STOP NOTE
# ============================================================

def stop_note(key=None):

    global current_note_key

    if (
        key is None
        or key == current_note_key
    ):

        if current_note_key is not None:

            print(
                "NOTE OFF:",
                NOTES[current_note_key][0]
            )

        current_note_key = None


# ============================================================
# STARTUP
# ============================================================

print("==============================")
print("AIRFRET CLEAN NOTES")
print("==============================")
print()
print("1 = C4")
print("2 = D4")
print("3 = E4")
print("4 = F4")
print("5 = G4")
print("6 = A4")
print("7 = B4")
print("8 = C5")
print("0 = STOP")
print()
print("Ready.")
print()


# ============================================================
# MAIN LOOP
# ============================================================

while True:

    # --------------------------------------------------------
    # READ KEYPAD
    # --------------------------------------------------------

    current_keys = scan_keypad()


    # --------------------------------------------------------
    # KEY PRESSED
    # --------------------------------------------------------

    newly_pressed = (
        current_keys
        - previous_keys
    )

    for key in newly_pressed:

        if key in NOTES:

            start_note(key)

        elif key == "0":

            stop_note()


    # --------------------------------------------------------
    # KEY RELEASED
    # --------------------------------------------------------

    newly_released = (
        previous_keys
        - current_keys
    )

    for key in newly_released:

        if key in NOTES:

            stop_note(key)


    previous_keys = current_keys


    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    if current_note_key is not None:

        # No math happens here.
        # We're only sending already-generated audio.
        audio.write(
            note_buffers[
                current_note_key
            ]
        )

    else:

        # Keep I2S supplied with silence
        audio.write(silence)
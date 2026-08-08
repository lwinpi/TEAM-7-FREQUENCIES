from machine import Pin, ADC, I2S
from array import array
import math
import struct
import time
import gc


# ============================================================
# AIRFRET - NO VOLUME CONTROL TEST
# ============================================================
#
# KEYPAD:
#   GP2-GP8
#
# JOYSTICK:
#   SW  -> GP18
#   VRx -> GP27
#   VRy -> GP28
#
# MAX98357A:
#   GP10 -> BCLK
#   GP11 -> LRC
#   GP12 -> DIN
#
# GP26 IS NOT USED
# ============================================================


# ============================================================
# KEYPAD
# ============================================================

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
    p = Pin(gpio, Pin.OUT)
    p.value(1)
    rows.append(p)

columns = []

for gpio in COL_GPIOS:
    columns.append(
        Pin(gpio, Pin.IN, Pin.PULL_UP)
    )


# ============================================================
# JOYSTICK
# ============================================================

joystick_switch = Pin(
    18,
    Pin.IN,
    Pin.PULL_UP
)

joystick_x = ADC(27)
joystick_y = ADC(28)

CENTER_X = 31815
CENTER_Y = 33096

MOVE_DISTANCE = 6000
RESET_DISTANCE = 3000


# ============================================================
# MAX98357A
# ============================================================

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
    ibuf=30000
)


# ============================================================
# NOTE MODE
# ============================================================

NOTE_KEYS = {
    "1": ("C4", 60),
    "2": ("D4", 62),
    "3": ("E4", 64),
    "4": ("F4", 65),
    "5": ("G4", 67),
    "6": ("A4", 69),
    "7": ("B4", 71),
    "8": ("C5", 72)
}


# ============================================================
# SCALE MODE
# ============================================================

SCALE_KEYS = {
    "1": "C_MAJOR",
    "2": "G_MAJOR",
    "3": "A_MINOR",
    "4": "D_MINOR"
}


SCALES = {

    "C_MAJOR": [
        "C_MAJOR",
        "D_MINOR",
        "E_MINOR",
        "F_MAJOR",
        "G_MAJOR",
        "A_MINOR",
        "B_DIMINISHED"
    ],

    "G_MAJOR": [
        "G_MAJOR",
        "A_MINOR",
        "B_MINOR",
        "C_MAJOR",
        "D_MAJOR",
        "E_MINOR",
        "F_SHARP_DIMINISHED"
    ],

    "A_MINOR": [
        "A_MINOR",
        "B_DIMINISHED",
        "C_MAJOR",
        "D_MINOR",
        "E_MINOR",
        "F_MAJOR",
        "G_MAJOR"
    ],

    "D_MINOR": [
        "D_MINOR",
        "E_DIMINISHED",
        "F_MAJOR",
        "G_MINOR",
        "A_MINOR",
        "B_FLAT_MAJOR",
        "C_MAJOR"
    ]
}


# ============================================================
# CHORD NOTES
# ============================================================

CHORD_NOTES = {

    "C_MAJOR": [60, 64, 67],
    "D_MINOR": [62, 65, 69],
    "E_MINOR": [64, 67, 71],
    "F_MAJOR": [65, 69, 72],
    "G_MAJOR": [67, 71, 74],
    "A_MINOR": [69, 72, 76],
    "B_DIMINISHED": [71, 74, 77],

    "B_MINOR": [71, 74, 78],
    "D_MAJOR": [62, 66, 69],
    "F_SHARP_DIMINISHED": [66, 69, 72],

    "E_DIMINISHED": [64, 67, 70],
    "G_MINOR": [67, 70, 74],
    "B_FLAT_MAJOR": [70, 74, 77]
}


# ============================================================
# STATE
# ============================================================

mode = "NOTE"

selected_scale = "C_MAJOR"
chord_index = 0
inversion = 0

previous_keys = set()

current_note_key = None

x_ready = True
y_ready = True

previous_switch = 1
last_strum_time = 0


# ============================================================
# MIDI -> FREQUENCY
# ============================================================

def midi_to_frequency(midi):

    return 440.0 * (
        2 ** ((midi - 69) / 12)
    )


# ============================================================
# CURRENT CHORD
# ============================================================

def current_chord():

    return SCALES[
        selected_scale
    ][
        chord_index
    ]


# ============================================================
# MEMORY-EFFICIENT SINE TABLE
# ============================================================

TABLE_BITS = 10
TABLE_SIZE = 1024
TABLE_MASK = 1023

sine_table = array("h")

print()
print("Building sine table...")

for i in range(TABLE_SIZE):

    value = int(
        32767
        * math.sin(
            2
            * math.pi
            * i
            / TABLE_SIZE
        )
    )

    sine_table.append(value)

print("Sine table ready.")


# ============================================================
# CHORD BUFFER
# ============================================================
#
# 240ms instead of 500ms.
#
# 44100 * 0.240 * 4
# = about 42 KB.
#
# This is allocated ONCE.
# ============================================================

CHORD_DURATION_MS = 240

CHORD_SAMPLES = (
    SAMPLE_RATE
    * CHORD_DURATION_MS
    // 1000
)

CHORD_BUFFER_BYTES = (
    CHORD_SAMPLES * 4
)


print(
    "Chord buffer:",
    CHORD_BUFFER_BYTES,
    "bytes"
)

gc.collect()

current_chord_buffer = bytearray(
    CHORD_BUFFER_BYTES
)

print("Chord buffer allocated.")


# ============================================================
# CLEAN NOTE BUFFERS
# ============================================================

note_buffers = {}


def make_clean_note_buffer(midi):

    frequency = midi_to_frequency(midi)

    # Complete waveform cycles
    cycles = 4

    samples = int(
        round(
            cycles
            * SAMPLE_RATE
            / frequency
        )
    )

    buffer = bytearray(
        samples * 4
    )

    # Same simple clean sine approach
    amplitude = 4000

    for i in range(samples):

        phase = (
            2
            * math.pi
            * cycles
            * i
            / samples
        )

        sample = int(
            amplitude
            * math.sin(phase)
        )

        struct.pack_into(
            "<hh",
            buffer,
            i * 4,
            sample,
            sample
        )

    return buffer


def build_notes():

    print()
    print("Building clean notes...")

    for key in NOTE_KEYS:

        name, midi = NOTE_KEYS[key]

        note_buffers[key] = (
            make_clean_note_buffer(midi)
        )

        print(
            "NOTE READY:",
            name
        )

    gc.collect()

    print("All notes ready.")
    print()


# ============================================================
# CHORD NOTES + INVERSION
# ============================================================

def get_current_chord_notes():

    notes = CHORD_NOTES[
        current_chord()
    ][:]

    for i in range(inversion):

        first = notes.pop(0)

        notes.append(
            first + 12
        )

    return notes


# ============================================================
# GUITAR STRUM SETTINGS
# ============================================================

# Time between virtual strings
STRUM_DELAY_MS = 15

# Very fast pick attack
ATTACK_MS = 2


# ============================================================
# PREPARE GUITAR CHORD
# ============================================================
#
# The important part:
#
# C -------------------
#      E ----------------
#           G ------------
#
# The notes overlap.
# ============================================================

def prepare_current_chord():

    notes = get_current_chord_notes()

    print()
    print(
        "PREPARING:",
        current_chord()
    )

    print(
        "INVERSION:",
        inversion
    )


    strum_delay = (
        SAMPLE_RATE
        * STRUM_DELAY_MS
        // 1000
    )


    attack_samples = (
        SAMPLE_RATE
        * ATTACK_MS
        // 1000
    )

    if attack_samples < 1:
        attack_samples = 1


    # --------------------------------------------------------
    # Oscillator states
    # --------------------------------------------------------

    phases = [0, 0, 0]
    increments = []


    for midi in notes:

        frequency = midi_to_frequency(
            midi
        )

        increment = int(
            frequency
            * (1 << 32)
            / SAMPLE_RATE
        )

        increments.append(
            increment
        )


    # --------------------------------------------------------
    # Each virtual string's maximum strength
    # --------------------------------------------------------

    STRING_GAIN = 4800


    # --------------------------------------------------------
    # Generate the entire chord
    # --------------------------------------------------------

    for sample_index in range(
        CHORD_SAMPLES
    ):

        mixed = 0


        # ====================================================
        # THREE VIRTUAL STRINGS
        # ====================================================

        for voice in range(3):


            start = (
                voice
                * strum_delay
            )


            if sample_index < start:
                continue


            age = (
                sample_index
                - start
            )


            voice_length = (
                CHORD_SAMPLES
                - start
            )


            remaining = (
                voice_length
                - age
            )


            if remaining <= 0:
                continue


            # =================================================
            # ATTACK / DECAY
            # =================================================

            if age < attack_samples:

                envelope = (
                    age
                    * 32767
                    // attack_samples
                )

            else:

                envelope = (
                    remaining
                    * 32767
                    // voice_length
                )


                # Curved decay
                envelope = (
                    envelope
                    * envelope
                    // 32767
                )


            # =================================================
            # HARMONIC DECAY
            # =================================================

            env2 = (
                envelope
                * envelope
                // 32767
            )


            env3 = (
                env2
                * envelope
                // 32767
            )


            # =================================================
            # PHASE
            # =================================================

            phase = phases[voice]


            index1 = (
                phase
                >> (
                    32 - TABLE_BITS
                )
            ) & TABLE_MASK


            index2 = (
                index1 * 2
            ) & TABLE_MASK


            index3 = (
                index1 * 3
            ) & TABLE_MASK


            # =================================================
            # FUNDAMENTAL
            # =================================================

            fundamental = (
                sine_table[index1]
                * envelope
                // 32767
            )


            # =================================================
            # SECOND HARMONIC
            # =================================================

            harmonic2 = (
                sine_table[index2]
                * env2
                // 32767
            )


            # =================================================
            # THIRD HARMONIC
            # =================================================

            harmonic3 = (
                sine_table[index3]
                * env3
                // 32767
            )


            # =================================================
            # STRING SOUND
            # =================================================
            #
            # Mostly clean fundamental.
            #
            # A little harmonic energy gives the
            # beginning a brighter plucked sound.
            # =================================================

            wave = (
                fundamental
                + harmonic2 * 22 // 100
                + harmonic3 * 8 // 100
            )


            string_sample = (
                wave
                * STRING_GAIN
                // 32767
            )


            mixed += string_sample


            phases[voice] = (
                phase
                + increments[voice]
            ) & 0xFFFFFFFF


        # ====================================================
        # PROTECT AGAINST CLIPPING
        # ====================================================

        if mixed > 22000:

            mixed = 22000


        elif mixed < -22000:

            mixed = -22000


        # ====================================================
        # WRITE DIRECTLY INTO REUSABLE CHORD BUFFER
        # ====================================================

        struct.pack_into(
            "<hh",
            current_chord_buffer,
            sample_index * 4,
            mixed,
            mixed
        )


    print(
        "READY:",
        current_chord()
    )

    print()


# ============================================================
# AUDIO PLAYBACK
# ============================================================
#
# NO VOLUME CODE.
# NO I2S.shift.
# NO GP26.
# ============================================================

def play_buffer(buffer):

    view = memoryview(buffer)

    total = len(view)

    position = 0

    CHUNK_SIZE = 4096


    while position < total:

        end = min(
            position + CHUNK_SIZE,
            total
        )


        chunk = view[
            position:end
        ]


        sent = 0


        while sent < len(chunk):

            written = audio.write(
                chunk[sent:]
            )


            if written is None:

                written = (
                    len(chunk)
                    - sent
                )


            if written <= 0:
                break


            sent += written


        position = end


# ============================================================
# STRUM
# ============================================================

def strum_chord():

    print(
        "STRUM:",
        current_chord()
    )

    # Instant playback.
    # No synthesis occurs here.

    play_buffer(
        current_chord_buffer
    )


# ============================================================
# DISPLAY CURRENT STATE
# ============================================================

def show_current():

    print(
        "SCALE:",
        selected_scale
    )

    print(
        "CHORD:",
        current_chord()
    )

    print(
        "INVERSION:",
        inversion
    )


# ============================================================
# SCALE SELECT
# ============================================================

def select_scale(scale):

    global selected_scale
    global chord_index
    global inversion


    selected_scale = scale

    chord_index = 0

    inversion = 0


    show_current()

    prepare_current_chord()


# ============================================================
# NEXT CHORD
# ============================================================

def next_chord():

    global chord_index


    chord_index += 1


    if chord_index >= len(
        SCALES[selected_scale]
    ):

        chord_index = 0


    print(
        "CHORD:",
        current_chord()
    )


    prepare_current_chord()


# ============================================================
# PREVIOUS CHORD
# ============================================================

def previous_chord():

    global chord_index


    chord_index -= 1


    if chord_index < 0:

        chord_index = (
            len(
                SCALES[selected_scale]
            )
            - 1
        )


    print(
        "CHORD:",
        current_chord()
    )


    prepare_current_chord()


# ============================================================
# INVERSION UP
# ============================================================

def increase_inversion():

    global inversion


    inversion += 1


    if inversion > 2:

        inversion = 0


    print(
        "INVERSION:",
        inversion
    )


    prepare_current_chord()


# ============================================================
# INVERSION DOWN
# ============================================================

def decrease_inversion():

    global inversion


    inversion -= 1


    if inversion < 0:

        inversion = 2


    print(
        "INVERSION:",
        inversion
    )


    prepare_current_chord()


# ============================================================
# KEYPAD SCANNER
# ============================================================

def scan_keypad():

    pressed = set()


    for row_index in range(4):


        # All rows inactive

        for row in rows:

            row.value(1)


        # Activate current row

        rows[row_index].value(0)


        time.sleep_us(50)


        # Read columns

        for column_index in range(3):


            if columns[
                column_index
            ].value() == 0:


                key = KEY_LAYOUT[
                    row_index
                ][
                    column_index
                ]


                pressed.add(
                    key
                )


        rows[row_index].value(1)


    return pressed


# ============================================================
# HANDLE KEYPAD PRESS
# ============================================================

def handle_key_press(key):

    global mode
    global current_note_key


    # --------------------------------------------------------
    # NOTE MODE
    # --------------------------------------------------------

    if key == "*":

        mode = "NOTE"

        current_note_key = None

        print(
            "MODE: NOTE"
        )

        return


    # --------------------------------------------------------
    # CHORD MODE
    # --------------------------------------------------------

    if key == "#":

        mode = "CHORD"

        current_note_key = None

        print(
            "MODE: CHORD"
        )

        show_current()

        return


    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    if key == "0":

        current_note_key = None

        print(
            "STOP"
        )

        return


    # --------------------------------------------------------
    # INDIVIDUAL NOTES
    # --------------------------------------------------------

    if mode == "NOTE":

        if key in NOTE_KEYS:

            current_note_key = key

            print(
                "NOTE:",
                NOTE_KEYS[key][0]
            )


    # --------------------------------------------------------
    # SCALE SELECTION
    # --------------------------------------------------------

    elif mode == "CHORD":

        if key in SCALE_KEYS:

            select_scale(
                SCALE_KEYS[key]
            )


# ============================================================
# JOYSTICK
# ============================================================

def read_joystick():

    global x_ready
    global y_ready

    global previous_switch
    global last_strum_time


    x = joystick_x.read_u16()

    y = joystick_y.read_u16()


    dx = (
        x - CENTER_X
    )


    dy = (
        y - CENTER_Y
    )


    # --------------------------------------------------------
    # RE-ARM
    # --------------------------------------------------------

    if abs(dx) < RESET_DISTANCE:

        x_ready = True


    if abs(dy) < RESET_DISTANCE:

        y_ready = True


    # --------------------------------------------------------
    # CHORD MODE
    # --------------------------------------------------------

    if mode == "CHORD":


        # LEFT / RIGHT

        if (
            abs(dx) >= abs(dy)
            and abs(dx) > MOVE_DISTANCE
            and x_ready
        ):


            if dx > 0:

                next_chord()

            else:

                previous_chord()


            x_ready = False


        # UP / DOWN

        elif (
            abs(dy) > abs(dx)
            and abs(dy) > MOVE_DISTANCE
            and y_ready
        ):


            if dy > 0:

                increase_inversion()

            else:

                decrease_inversion()


            y_ready = False


    # --------------------------------------------------------
    # JOYSTICK PRESS
    # --------------------------------------------------------

    switch = (
        joystick_switch.value()
    )


    now = (
        time.ticks_ms()
    )


    if (
        mode == "CHORD"
        and previous_switch == 1
        and switch == 0
        and time.ticks_diff(
            now,
            last_strum_time
        ) > 180
    ):

        strum_chord()

        last_strum_time = now


    previous_switch = switch


# ============================================================
# INITIALIZATION
# ============================================================

# Big buffer was allocated before these note buffers.
# This helps avoid MemoryError.

build_notes()


print(
    "Preparing initial C Major..."
)

prepare_current_chord()


# ============================================================
# READY
# ============================================================

print()
print("================================")
print("       AIRFRET TEST")
print("       NO VOLUME")
print("================================")
print()

print("* = NOTE MODE")
print("# = CHORD MODE")
print("0 = STOP")
print()

print("NOTE MODE:")
print("1 = C4")
print("2 = D4")
print("3 = E4")
print("4 = F4")
print("5 = G4")
print("6 = A4")
print("7 = B4")
print("8 = C5")
print()

print("CHORD MODE:")
print("1 = C MAJOR")
print("2 = G MAJOR")
print("3 = A MINOR")
print("4 = D MINOR")
print()

print("JOYSTICK:")
print("LEFT/RIGHT = CHORD")
print("UP/DOWN = INVERSION")
print("PRESS = STRUM")
print()

print("GP26/POT = COMPLETELY DISABLED")
print()

print("AIRFRET READY")
print()


# ============================================================
# MAIN LOOP
# ============================================================

while True:


    # --------------------------------------------------------
    # KEYPAD
    # --------------------------------------------------------

    current_keys = scan_keypad()


    newly_pressed = (
        current_keys
        - previous_keys
    )


    for key in newly_pressed:

        handle_key_press(
            key
        )


    newly_released = (
        previous_keys
        - current_keys
    )


    for key in newly_released:


        if (
            mode == "NOTE"
            and key == current_note_key
        ):

            print(
                "NOTE OFF:",
                NOTE_KEYS[key][0]
            )

            current_note_key = None


    previous_keys = current_keys


    # --------------------------------------------------------
    # JOYSTICK
    # --------------------------------------------------------

    read_joystick()


    # --------------------------------------------------------
    # NOTE PLAYBACK
    # --------------------------------------------------------

    if (
        mode == "NOTE"
        and current_note_key is not None
    ):

        play_buffer(
            note_buffers[
                current_note_key
            ]
        )


    else:

        time.sleep_ms(2)
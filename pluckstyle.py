from machine import Pin, ADC, I2S
from array import array
import math
import struct
import time
import gc


# ============================================================
# AIRFRET - PHYSICAL GUITAR STRING TEST
# NO VOLUME CONTROL
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
# SCALES
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
# GUITAR VOICINGS
# ============================================================
#
# These are NOT just C-E-G triads anymore.
#
# They repeat notes like real guitar chord shapes.
#
# Example C:
#
# C3 E3 G3 C4 E4
#
# ============================================================

GUITAR_CHORDS = {

    "C_MAJOR": [
        48, 52, 55, 60, 64
    ],

    "D_MINOR": [
        50, 57, 62, 65
    ],

    "E_MINOR": [
        40, 47, 52, 55, 59, 64
    ],

    "F_MAJOR": [
        41, 48, 53, 57, 60, 65
    ],

    "G_MAJOR": [
        43, 47, 50, 55, 59, 67
    ],

    "A_MINOR": [
        45, 52, 57, 60, 64
    ],

    "B_DIMINISHED": [
        47, 50, 53, 59, 62
    ],

    "B_MINOR": [
        47, 54, 59, 62, 66
    ],

    "D_MAJOR": [
        50, 57, 62, 66
    ],

    "F_SHARP_DIMINISHED": [
        54, 57, 60, 66
    ],

    "E_DIMINISHED": [
        52, 55, 58, 64
    ],

    "G_MINOR": [
        43, 50, 55, 58, 62, 67
    ],

    "B_FLAT_MAJOR": [
        46, 53, 58, 62, 65
    ]
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
# FREQUENCY
# ============================================================

def midi_to_frequency(midi):

    return 440.0 * (
        2 ** ((midi - 69) / 12)
    )


def current_chord():

    return SCALES[
        selected_scale
    ][
        chord_index
    ]


# ============================================================
# CHORD AUDIO BUFFER
# ============================================================
#
# About 44 KB.
#
# Allocated ONCE.
# ============================================================

CHORD_DURATION_MS = 250

CHORD_SAMPLES = (
    SAMPLE_RATE
    * CHORD_DURATION_MS
    // 1000
)

CHORD_BYTES = (
    CHORD_SAMPLES * 4
)


print()
print(
    "Allocating chord buffer:",
    CHORD_BYTES,
    "bytes"
)

gc.collect()

current_chord_buffer = bytearray(
    CHORD_BYTES
)

print(
    "Chord buffer ready."
)


# ============================================================
# CLEAN NOTE BUFFERS
# ============================================================

note_buffers = {}


def make_clean_note(midi):

    frequency = midi_to_frequency(
        midi
    )

    cycles = 4

    samples = int(
        round(
            cycles
            * SAMPLE_RATE
            / frequency
        )
    )

    buf = bytearray(
        samples * 4
    )

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
            buf,
            i * 4,
            sample,
            sample
        )

    return buf


def build_notes():

    print()
    print(
        "Building clean notes..."
    )

    for key in NOTE_KEYS:

        name, midi = NOTE_KEYS[
            key
        ]

        note_buffers[key] = (
            make_clean_note(
                midi
            )
        )

        print(
            "NOTE READY:",
            name
        )

    gc.collect()

    print(
        "Notes ready."
    )


# ============================================================
# INVERSION
# ============================================================

def get_guitar_notes():

    notes = GUITAR_CHORDS[
        current_chord()
    ][:]

    # Guitar-style inversion:
    # move the lowest sounding string up an octave.

    for n in range(inversion):

        if len(notes) > 0:

            first = notes.pop(0)

            notes.append(
                first + 12
            )

            notes.sort()

    return notes


# ============================================================
# DETERMINISTIC RANDOM GENERATOR
# ============================================================
#
# We want pick noise but don't need the random module.
# ============================================================

random_state = 0x12345678


def next_noise():

    global random_state

    random_state = (
        random_state
        * 1664525
        + 1013904223
    ) & 0xFFFFFFFF

    value = (
        (random_state >> 16)
        & 0xFFFF
    )

    return (
        value - 32768
    )


# ============================================================
# CREATE ONE PHYSICAL STRING
# ============================================================

def create_string(midi, string_number):

    frequency = midi_to_frequency(
        midi
    )

    # Karplus-Strong pitch compensation
    period = int(
        SAMPLE_RATE
        / frequency
        - 0.5
    )

    if period < 2:
        period = 2


    ring = array(
        "h",
        [0] * period
    )


    # --------------------------------------------------------
    # PICK EXCITATION
    # --------------------------------------------------------
    #
    # Real plucking doesn't start as a sine wave.
    #
    # The string begins with a short broadband displacement.
    # --------------------------------------------------------

    previous_noise = 0


    for i in range(period):

        raw = next_noise()


        # Slightly smooth the noise.
        #
        # Keeps the steel-string brightness while avoiding
        # pure white-noise harshness.

        excitation = (
            raw
            + previous_noise
        ) // 2


        previous_noise = raw


        # Different strings get slightly different strength.

        if string_number == 0:
            strength = 8000

        elif string_number == 1:
            strength = 7600

        elif string_number == 2:
            strength = 7200

        else:
            strength = 6800


        value = (
            excitation
            * strength
            // 32768
        )


        if value > 32767:
            value = 32767

        elif value < -32768:
            value = -32768


        ring[i] = value


    # --------------------------------------------------------
    # DAMPING
    # --------------------------------------------------------
    #
    # Lower number = faster decay.
    #
    # Higher strings can ring slightly longer.
    # --------------------------------------------------------

    if frequency < 150:

        damping = 32640

    elif frequency < 250:

        damping = 32670

    elif frequency < 400:

        damping = 32695

    else:

        damping = 32710


    return {
        "ring": ring,
        "index": 0,
        "length": period,
        "damping": damping
    }


# ============================================================
# GET NEXT PHYSICAL STRING SAMPLE
# ============================================================

def string_sample(string):

    ring = string[
        "ring"
    ]

    index = string[
        "index"
    ]

    length = string[
        "length"
    ]

    next_index = index + 1

    if next_index >= length:

        next_index = 0


    first = ring[
        index
    ]

    second = ring[
        next_index
    ]


    # --------------------------------------------------------
    # KARPLUS-STRONG LOOP
    # --------------------------------------------------------
    #
    # Average neighboring samples.
    #
    # This simulates energy traveling along a vibrating string.
    # --------------------------------------------------------

    new_value = (
        first + second
    ) // 2


    new_value = (
        new_value
        * string[
            "damping"
        ]
        >> 15
    )


    # Store filtered sample back into delay line

    ring[index] = (
        new_value
    )


    string[
        "index"
    ] = (
        next_index
    )


    return first


# ============================================================
# PREPARE REALISTIC STRUM
# ============================================================

STRUM_DELAY_MS = 7

STRUM_DELAY_SAMPLES = (
    SAMPLE_RATE
    * STRUM_DELAY_MS
    // 1000
)


def prepare_current_chord():

    notes = get_guitar_notes()


    print()
    print(
        "PREPARING GUITAR:",
        current_chord()
    )

    print(
        "STRINGS:",
        notes
    )


    # --------------------------------------------------------
    # CREATE PHYSICAL STRING MODELS
    # --------------------------------------------------------

    strings = []


    for i in range(
        len(notes)
    ):

        strings.append(
            create_string(
                notes[i],
                i
            )
        )


    # --------------------------------------------------------
    # MIX PHYSICAL STRINGS INTO CHORD BUFFER
    # --------------------------------------------------------

    for sample_index in range(
        CHORD_SAMPLES
    ):


        mixed = 0

        active_strings = 0


        for voice in range(
            len(strings)
        ):


            start = (
                voice
                * STRUM_DELAY_SAMPLES
            )


            # The pick has not reached this string yet.

            if sample_index < start:

                continue


            value = string_sample(
                strings[
                    voice
                ]
            )


            # ------------------------------------------------
            # Slight initial pick emphasis
            # ------------------------------------------------

            age = (
                sample_index
                - start
            )


            if age < 80:

                value = (
                    value
                    * 115
                    // 100
                )


            mixed += value

            active_strings += 1


        # ----------------------------------------------------
        # MIXING HEADROOM
        # ----------------------------------------------------

        if active_strings > 2:

            mixed = (
                mixed
                * 2
                // 3
            )


        # ----------------------------------------------------
        # END FADE
        # ----------------------------------------------------
        #
        # Avoid a hard click at the end of the 250 ms buffer.
        # ----------------------------------------------------

        fade_samples = 800

        remaining = (
            CHORD_SAMPLES
            - sample_index
        )


        if remaining < fade_samples:

            mixed = (
                mixed
                * remaining
                // fade_samples
            )


        # ----------------------------------------------------
        # SAFETY
        # ----------------------------------------------------

        if mixed > 24000:

            mixed = 24000

        elif mixed < -24000:

            mixed = -24000


        struct.pack_into(
            "<hh",
            current_chord_buffer,
            sample_index * 4,
            mixed,
            mixed
        )


    # Release string delay buffers.

    strings = None

    gc.collect()


    print(
        "READY:",
        current_chord()
    )

    print()


# ============================================================
# PLAY AUDIO
# ============================================================

def play_buffer(buffer):

    view = memoryview(
        buffer
    )

    position = 0

    total = len(
        view
    )

    chunk_size = 4096


    while position < total:

        end = min(
            position + chunk_size,
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

    # Already synthesized.
    # Playback begins immediately.

    play_buffer(
        current_chord_buffer
    )


# ============================================================
# CURRENT STATE
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
# SELECT SCALE
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
        SCALES[
            selected_scale
        ]
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
                SCALES[
                    selected_scale
                ]
            )
            - 1
        )


    print(
        "CHORD:",
        current_chord()
    )

    prepare_current_chord()


# ============================================================
# INVERSION
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
# KEYPAD
# ============================================================

def scan_keypad():

    pressed = set()


    for row_index in range(4):

        for row in rows:

            row.value(1)


        rows[
            row_index
        ].value(0)


        time.sleep_us(50)


        for column_index in range(3):

            if columns[
                column_index
            ].value() == 0:


                pressed.add(
                    KEY_LAYOUT[
                        row_index
                    ][
                        column_index
                    ]
                )


        rows[
            row_index
        ].value(1)


    return pressed


# ============================================================
# KEYPAD CONTROL
# ============================================================

def handle_key_press(key):

    global mode
    global current_note_key


    if key == "*":

        mode = "NOTE"

        current_note_key = None

        print(
            "MODE: NOTE"
        )

        return


    if key == "#":

        mode = "CHORD"

        current_note_key = None

        print(
            "MODE: CHORD"
        )

        show_current()

        return


    if key == "0":

        current_note_key = None

        print(
            "STOP"
        )

        return


    if mode == "NOTE":

        if key in NOTE_KEYS:

            current_note_key = key

            print(
                "NOTE:",
                NOTE_KEYS[
                    key
                ][0]
            )


    elif mode == "CHORD":

        if key in SCALE_KEYS:

            select_scale(
                SCALE_KEYS[
                    key
                ]
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


    if abs(dx) < RESET_DISTANCE:

        x_ready = True


    if abs(dy) < RESET_DISTANCE:

        y_ready = True


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
    # JOYSTICK PRESS = DOWN STRUM
    # --------------------------------------------------------

    switch = joystick_switch.value()

    now = time.ticks_ms()


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
# INITIALIZE
# ============================================================

build_notes()


print()
print(
    "Preparing physical C Major guitar..."
)

prepare_current_chord()


# ============================================================
# READY
# ============================================================

print()
print("==============================")
print("AIRFRET PHYSICAL STRING TEST")
print("==============================")
print()

print("* = NOTE MODE")
print("# = CHORD MODE")
print("0 = STOP")
print()

print("Chord mode:")
print("1 = C Major")
print("2 = G Major")
print("3 = A Minor")
print("4 = D Minor")
print()

print("Joystick left/right = chord")
print("Joystick up/down = inversion")
print("Joystick press = guitar strum")
print()

print("VOLUME CONTROL DISABLED")
print()

print("AIRFRET READY")


# ============================================================
# MAIN LOOP
# ============================================================

while True:

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
                NOTE_KEYS[
                    key
                ][0]
            )

            current_note_key = None


    previous_keys = (
        current_keys
    )


    read_joystick()


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
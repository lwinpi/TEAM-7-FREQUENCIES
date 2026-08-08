from machine import Pin, ADC, I2S
from array import array
import math
import struct
import time
import gc


# ============================================================
# AIRFRET - REALISTIC GUITAR STRUM TEST
#
# NO POTENTIOMETER
# NO VOLUME CONTROL
#
# Uses:
# - real 6-string guitar voicings
# - Karplus-Strong physical string model
# - pick-position filtering
# - per-string damping
# - slight detuning
# - irregular strum timing
# - muted-string scratches
# - pick transient
# - subtle guitar-body resonance
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

# SW  -> GP18
# VRx -> GP27
# VRy -> GP28

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

# GP10 -> BCLK
# GP11 -> LRC
# GP12 -> DIN

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
# CLEAN NOTE MODE
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
# REAL 6-STRING GUITAR VOICINGS
# ============================================================
#
# Array order:
#
# string 6 -> low E
# string 5 -> A
# string 4 -> D
# string 3 -> G
# string 2 -> B
# string 1 -> high E
#
# None = muted string
#
# Example C major:
#
# x 3 2 0 1 0
#
# None, C3, E3, G3, C4, E4
# ============================================================

GUITAR_CHORDS = {

    "C_MAJOR": [
        None, 48, 52, 55, 60, 64
    ],

    "D_MINOR": [
        None, None, 50, 57, 62, 65
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
        None, 45, 52, 57, 60, 64
    ],

    "B_DIMINISHED": [
        None, 47, 53, 59, 62, 65
    ],

    "B_MINOR": [
        None, 47, 54, 59, 62, 66
    ],

    "D_MAJOR": [
        None, None, 50, 57, 62, 66
    ],

    "F_SHARP_DIMINISHED": [
        42, 48, 54, 57, 60, 66
    ],

    "E_DIMINISHED": [
        40, 46, 52, 55, 58, 64
    ],

    "G_MINOR": [
        43, 50, 55, 58, 62, 67
    ],

    "B_FLAT_MAJOR": [
        None, 46, 53, 58, 62, 65
    ]
}


# ============================================================
# SYSTEM STATE
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


def current_chord():

    return SCALES[
        selected_scale
    ][
        chord_index
    ]


# ============================================================
# CHORD BUFFER
# ============================================================
#
# Allocate ONE buffer and reuse it.
#
# 300 ms:
#
# 44100 * .300 * 4
# = 52,920 bytes
# ============================================================

CHORD_DURATION_MS = 300

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
    "Allocating guitar buffer:",
    CHORD_BYTES,
    "bytes"
)

gc.collect()

current_chord_buffer = bytearray(
    CHORD_BYTES
)

print("Guitar buffer ready.")


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

    # Same simple clean tone approach
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
    print("Building clean notes...")

    for key in NOTE_KEYS:

        name, midi = NOTE_KEYS[key]

        note_buffers[key] = (
            make_clean_note(midi)
        )

        print(
            "NOTE READY:",
            name
        )

    gc.collect()

    print("Notes ready.")
    print()


# ============================================================
# RANDOM GENERATOR
# ============================================================
#
# Used for string displacement and pick noise.
# ============================================================

random_state = 0x45ABCDEF


def next_noise():

    global random_state

    random_state = (
        random_state * 1664525
        + 1013904223
    ) & 0xFFFFFFFF

    value = (
        random_state >> 16
    ) & 0xFFFF

    return value - 32768


# ============================================================
# GUITAR STRING CHARACTER
# ============================================================

# Tiny tuning imperfections.
# Real guitar strings are not mathematically perfect.

DETUNE_CENTS = [
    -1.2,
     0.8,
    -0.6,
     0.5,
    -0.4,
     0.7
]


# Pick position as fraction of string length.
#
# Different positions alter harmonic content.

PICK_POSITION = [
    0.24,
    0.22,
    0.21,
    0.19,
    0.18,
    0.17
]


# Initial strength.

STRING_LEVEL = [
    8000,
    7700,
    7400,
    7100,
    6800,
    6500
]


# Feedback damping.
#
# Each string decays slightly differently.

STRING_DAMPING = [
    32728,
    32725,
    32720,
    32715,
    32710,
    32705
]


# ============================================================
# STRUM TIMING
# ============================================================
#
# NOT perfectly even.
#
# A real hand doesn't hit every string exactly 7ms apart.
# ============================================================

STRUM_TIMES_MS = [
    0,
    6,
    13,
    21,
    30,
    40
]

STRUM_STARTS = []

for delay_ms in STRUM_TIMES_MS:

    STRUM_STARTS.append(
        SAMPLE_RATE
        * delay_ms
        // 1000
    )


# ============================================================
# GUITAR INVERSION
# ============================================================

def get_guitar_shape():

    shape = GUITAR_CHORDS[
        current_chord()
    ][:]


    if inversion == 0:

        return shape


    # Find active notes

    active_positions = []
    active_notes = []


    for i in range(6):

        if shape[i] is not None:

            active_positions.append(i)

            active_notes.append(
                shape[i]
            )


    # Move lowest note(s) up one octave

    for n in range(inversion):

        if len(active_notes) > 0:

            lowest = active_notes.pop(0)

            active_notes.append(
                lowest + 12
            )

            active_notes.sort()


    # Put them back on the active physical strings

    result = [
        None,
        None,
        None,
        None,
        None,
        None
    ]


    for i in range(
        len(active_positions)
    ):

        result[
            active_positions[i]
        ] = active_notes[i]


    return result


# ============================================================
# CREATE ONE PHYSICAL GUITAR STRING
# ============================================================

def create_string(
    midi,
    string_number
):

    frequency = midi_to_frequency(
        midi
    )


    # --------------------------------------------------------
    # SMALL REALISTIC DETUNE
    # --------------------------------------------------------

    cents = DETUNE_CENTS[
        string_number
    ]

    frequency = (
        frequency
        * (
            2 ** (
                cents / 1200.0
            )
        )
    )


    # --------------------------------------------------------
    # KARPLUS-STRONG DELAY LENGTH
    # --------------------------------------------------------
    #
    # The averaging filter introduces approximately
    # half a sample of additional delay.
    # --------------------------------------------------------

    exact_period = (
        SAMPLE_RATE
        / frequency
        - 0.5
    )

    period = int(
        exact_period + 0.5
    )


    if period < 4:
        period = 4


    # --------------------------------------------------------
    # INITIAL RANDOM STRING DISPLACEMENT
    # --------------------------------------------------------

    ring = array(
        "h",
        [0] * period
    )


    level = STRING_LEVEL[
        string_number
    ]


    for i in range(period):

        value = (
            next_noise()
            * level
            // 32768
        )

        ring[i] = value


    # --------------------------------------------------------
    # PICK POSITION FILTER
    # --------------------------------------------------------
    #
    # This creates harmonic notches similar to plucking
    # a real string at a particular physical location.
    # --------------------------------------------------------

    original = array(
        "h",
        ring
    )


    pick_delay = int(
        period
        * PICK_POSITION[
            string_number
        ]
    )


    if pick_delay < 1:
        pick_delay = 1


    for i in range(period):

        other_index = (
            i - pick_delay
        ) % period


        value = (
            original[i]
            - (
                original[
                    other_index
                ]
                * 55
                // 100
            )
        )


        # Safety

        if value > 32767:

            value = 32767

        elif value < -32768:

            value = -32768


        ring[i] = value


    original = None


    return [
        ring,
        0,
        period,
        STRING_DAMPING[
            string_number
        ]
    ]


# ============================================================
# NEXT STRING SAMPLE
# ============================================================

def get_string_sample(
    string
):

    ring = string[0]

    index = string[1]

    length = string[2]

    damping = string[3]


    next_index = index + 1


    if next_index >= length:

        next_index = 0


    current = ring[
        index
    ]

    next_value = ring[
        next_index
    ]


    # --------------------------------------------------------
    # STRING ENERGY FEEDBACK
    # --------------------------------------------------------
    #
    # This is the actual Karplus-Strong vibrating-string loop.
    # --------------------------------------------------------

    filtered = (
        current
        + next_value
    ) // 2


    filtered = (
        filtered
        * damping
        >> 15
    )


    # Safety

    if filtered > 32767:

        filtered = 32767

    elif filtered < -32768:

        filtered = -32768


    ring[
        index
    ] = filtered


    string[1] = (
        next_index
    )


    return current


# ============================================================
# BODY RESONANCE BUFFERS
# ============================================================
#
# Very small delayed reflections add a little bit of
# "wood/body" instead of totally dry electronic strings.
# ============================================================

BODY_DELAY_1 = 149
BODY_DELAY_2 = 257


# ============================================================
# PREPARE REALISTIC GUITAR STRUM
# ============================================================

def prepare_current_chord():

    shape = get_guitar_shape()


    print()
    print(
        "PREPARING GUITAR:",
        current_chord()
    )

    print(
        "SHAPE:",
        shape
    )


    # --------------------------------------------------------
    # CREATE STRING MODELS
    # --------------------------------------------------------

    strings = [
        None,
        None,
        None,
        None,
        None,
        None
    ]


    for string_number in range(6):

        midi = shape[
            string_number
        ]


        if midi is not None:

            strings[
                string_number
            ] = create_string(
                midi,
                string_number
            )


    gc.collect()


    # --------------------------------------------------------
    # BODY REFLECTION MEMORY
    # --------------------------------------------------------

    body1 = array(
        "h",
        [0] * BODY_DELAY_1
    )

    body2 = array(
        "h",
        [0] * BODY_DELAY_2
    )

    body_index1 = 0
    body_index2 = 0


    # About 1.2 ms pick click

    PICK_SAMPLES = (
        SAMPLE_RATE
        * 12
        // 10000
    )


    # Muted string scrape lasts about 4 ms

    MUTE_SAMPLES = (
        SAMPLE_RATE
        * 4
        // 1000
    )


    # --------------------------------------------------------
    # RENDER CHORD
    # --------------------------------------------------------

    for sample_index in range(
        CHORD_SAMPLES
    ):

        mixed = 0
        active_count = 0


        # ====================================================
        # SIX PHYSICAL STRINGS
        # ====================================================

        for string_number in range(6):

            start = STRUM_STARTS[
                string_number
            ]


            if sample_index < start:

                continue


            age = (
                sample_index
                - start
            )


            string = strings[
                string_number
            ]


            # =================================================
            # MUTED STRING SCRAPE
            # =================================================

            if string is None:

                if age < MUTE_SAMPLES:

                    strength = (
                        MUTE_SAMPLES
                        - age
                    )


                    scratch = (
                        next_noise()
                        * strength
                        // MUTE_SAMPLES
                    )


                    scratch = (
                        scratch
                        * 350
                        // 32768
                    )


                    mixed += scratch


                continue


            # =================================================
            # VIBRATING STRING
            # =================================================

            value = get_string_sample(
                string
            )


            # =================================================
            # PICK TRANSIENT
            # =================================================
            #
            # Real plectrum contact produces a very short
            # broadband transient before the pitched string
            # becomes dominant.
            # =================================================

            if age < PICK_SAMPLES:

                remaining = (
                    PICK_SAMPLES
                    - age
                )


                click = (
                    next_noise()
                    * remaining
                    // PICK_SAMPLES
                )


                click = (
                    click
                    * 650
                    // 32768
                )


                value += click


            mixed += value

            active_count += 1


        # ====================================================
        # MIXING HEADROOM
        # ====================================================

        if active_count >= 5:

            mixed = (
                mixed
                * 55
                // 100
            )

        elif active_count >= 3:

            mixed = (
                mixed
                * 68
                // 100
            )


        # ====================================================
        # GUITAR BODY REFLECTION
        # ====================================================

        reflection1 = body1[
            body_index1
        ]

        reflection2 = body2[
            body_index2
        ]


        dry = mixed


        mixed = (
            dry
            + reflection1 * 12 // 100
            + reflection2 * 7 // 100
        )


        # Store dry sound into body delay

        if dry > 32767:

            dry_store = 32767

        elif dry < -32768:

            dry_store = -32768

        else:

            dry_store = dry


        body1[
            body_index1
        ] = dry_store


        body2[
            body_index2
        ] = dry_store


        body_index1 += 1

        if body_index1 >= BODY_DELAY_1:

            body_index1 = 0


        body_index2 += 1

        if body_index2 >= BODY_DELAY_2:

            body_index2 = 0


        # ====================================================
        # END FADE
        # ====================================================

        fade_length = 1000

        remaining = (
            CHORD_SAMPLES
            - sample_index
        )


        if remaining < fade_length:

            mixed = (
                mixed
                * remaining
                // fade_length
            )


        # ====================================================
        # SAFETY CLIPPING
        # ====================================================

        if mixed > 26000:

            mixed = 26000

        elif mixed < -26000:

            mixed = -26000


        # ====================================================
        # WRITE 16-BIT STEREO PCM
        # ====================================================

        struct.pack_into(
            "<hh",
            current_chord_buffer,
            sample_index * 4,
            mixed,
            mixed
        )


    strings = None
    body1 = None
    body2 = None

    gc.collect()


    print(
        "READY:",
        current_chord()
    )

    print()


# ============================================================
# AUDIO PLAYBACK
# ============================================================

def play_buffer(buffer):

    view = memoryview(
        buffer
    )

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
    # Chord was already created when selected.

    play_buffer(
        current_chord_buffer
    )


# ============================================================
# CHORD DISPLAY
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
# SCALE
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
# KEYPAD SCANNER
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


    # * = NOTE MODE

    if key == "*":

        mode = "NOTE"

        current_note_key = None

        print(
            "MODE: NOTE"
        )

        return


    # # = CHORD MODE

    if key == "#":

        mode = "CHORD"

        current_note_key = None

        print(
            "MODE: CHORD"
        )

        show_current()

        return


    # 0 = STOP

    if key == "0":

        current_note_key = None

        print(
            "STOP"
        )

        return


    # NOTE MODE

    if mode == "NOTE":

        if key in NOTE_KEYS:

            current_note_key = key

            print(
                "NOTE:",
                NOTE_KEYS[
                    key
                ][0]
            )


    # CHORD MODE

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


    # Re-arm

    if abs(dx) < RESET_DISTANCE:

        x_ready = True


    if abs(dy) < RESET_DISTANCE:

        y_ready = True


    # CHORD MODE

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


    # JOYSTICK PRESS = STRUM

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
    "Creating first realistic C major..."
)

prepare_current_chord()


# ============================================================
# STARTUP
# ============================================================

print()
print("================================")
print(" AIRFRET REAL GUITAR STRUM TEST")
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
print("1 = C Major scale")
print("2 = G Major scale")
print("3 = A Minor scale")
print("4 = D Minor scale")
print()

print("JOYSTICK:")
print("LEFT / RIGHT = chord")
print("UP / DOWN = inversion")
print("PRESS = guitar strum")
print()

print("VOLUME/POTENTIOMETER DISABLED")
print()

print("AIRFRET READY")
print()


# ============================================================
# MAIN LOOP
# ============================================================

while True:


    # KEYPAD

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


    previous_keys = current_keys


    # JOYSTICK

    read_joystick()


    # CLEAN NOTE PLAYBACK

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
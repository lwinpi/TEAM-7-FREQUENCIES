from array import array
import math
import struct
import gc
import os


# ============================================================
# AIRFRET GUITAR SOUND BANK BUILDER
#
# RUN THIS ONCE.
#
# Creates:
#
# /guitar_bank/C_MAJOR_D1.raw
# /guitar_bank/C_MAJOR_D2.raw
# /guitar_bank/C_MAJOR_U1.raw
# etc.
#
# Files are:
# 22050 Hz
# signed 16-bit
# mono
# ~900 ms
# ============================================================


SAMPLE_RATE = 22050

DURATION_MS = 900

TOTAL_SAMPLES = (
    SAMPLE_RATE
    * DURATION_MS
    // 1000
)

BANK_DIR = "/guitar_bank"


# ============================================================
# ARTICLE-INSPIRED GUITAR VOICINGS
# ============================================================
#
# Based on the ideas in the uploaded chord-generator article:
#
# - Build chords from musical intervals.
# - Model a real six-string guitar fretboard.
# - Use one pitch per string.
# - Mute strings that should not sound.
# - Keep playable fret spans compact.
# - Prefer the chord root as the lowest sounding note.
#
# IMPORTANT:
# This improves chord VOICING/clarity. It does not replace the
# Karplus-Strong guitar tone engine below.
# ============================================================


# Standard guitar tuning:
#
# String 6 -> String 1
# E2 A2 D3 G3 B3 E4
#
# MIDI:
# 40 45 50 55 59 64

STANDARD_TUNING_MIDI = [
    40,
    45,
    50,
    55,
    59,
    64
]


# Chromatic pitch classes:
#
# C=0, C#=1, D=2 ... B=11

ROOT_PITCH_CLASS = {

    "C_MAJOR": 0,
    "D_MINOR": 2,
    "E_MINOR": 4,
    "F_MAJOR": 5,
    "G_MAJOR": 7,
    "A_MINOR": 9,
    "B_DIMINISHED": 11,
    "B_MINOR": 11,
    "D_MAJOR": 2,
    "F_SHARP_DIMINISHED": 6,
    "E_DIMINISHED": 4,
    "G_MINOR": 7,
    "B_FLAT_MAJOR": 10
}


CHORD_QUALITY = {

    "C_MAJOR": "major",
    "D_MINOR": "minor",
    "E_MINOR": "minor",
    "F_MAJOR": "major",
    "G_MAJOR": "major",
    "A_MINOR": "minor",
    "B_DIMINISHED": "dim",
    "B_MINOR": "minor",
    "D_MAJOR": "major",
    "F_SHARP_DIMINISHED": "dim",
    "E_DIMINISHED": "dim",
    "G_MINOR": "minor",
    "B_FLAT_MAJOR": "major"
}


# Article-style chord formulas in semitones from root.

CHORD_FORMULAS = {

    "major": [
        0, 4, 7
    ],

    "minor": [
        0, 3, 7
    ],

    "dim": [
        0, 3, 6
    ]
}


# ============================================================
# REAL FRET SHAPES
# ============================================================
#
# Order is low E -> high E.
#
# None = muted string
# 0    = open string
# 1+   = fret number
#
# These are guitar-realizable shapes, not arbitrary MIDI stacks.
# ============================================================

GUITAR_FRETS = {

    # x32010
    "C_MAJOR": [
        None, 3, 2, 0, 1, 0
    ],

    # xx0231
    "D_MINOR": [
        None, None, 0, 2, 3, 1
    ],

    # 022000
    "E_MINOR": [
        0, 2, 2, 0, 0, 0
    ],

    # 133211
    "F_MAJOR": [
        1, 3, 3, 2, 1, 1
    ],

    # 320003
    "G_MAJOR": [
        3, 2, 0, 0, 0, 3
    ],

    # x02210
    "A_MINOR": [
        None, 0, 2, 2, 1, 0
    ],

    # x2343x
    # B - F - B - D
    "B_DIMINISHED": [
        None, 2, 3, 4, 3, None
    ],

    # x24432
    "B_MINOR": [
        None, 2, 4, 4, 3, 2
    ],

    # xx0232
    "D_MAJOR": [
        None, None, 0, 2, 3, 2
    ],

    # xx4212
    # F# - A - C - F#
    "F_SHARP_DIMINISHED": [
        None, None, 4, 2, 1, 2
    ],

    # 0120x0
    # E - Bb - E - G - x - E
    # Keeps E as the bass/root and avoids an impossible note
    # below the open B string.
    "E_DIMINISHED": [
        0, 1, 2, 0, None, 0
    ],

    # 355333
    "G_MINOR": [
        3, 5, 5, 3, 3, 3
    ],

    # x13331
    "B_FLAT_MAJOR": [
        None, 1, 3, 3, 3, 1
    ]
}


def fret_shape_to_midi(shape):

    notes = []

    for string_number in range(6):

        fret = shape[
            string_number
        ]

        if fret is None:

            notes.append(
                None
            )

        else:

            notes.append(

                STANDARD_TUNING_MIDI[
                    string_number
                ]

                + fret
            )

    return notes


def validate_fret_shape(
    chord_name,
    shape
):

    root = ROOT_PITCH_CLASS[
        chord_name
    ]

    quality = CHORD_QUALITY[
        chord_name
    ]

    allowed = set()

    for interval in CHORD_FORMULAS[
        quality
    ]:

        allowed.add(
            (root + interval)
            % 12
        )


    sounding = []

    fretted = []

    for string_number in range(6):

        fret = shape[
            string_number
        ]

        if fret is None:
            continue

        midi = (
            STANDARD_TUNING_MIDI[
                string_number
            ]
            + fret
        )

        pitch_class = (
            midi % 12
        )

        if pitch_class not in allowed:

            raise ValueError(
                "Bad note in "
                + chord_name
            )

        sounding.append(
            midi
        )

        if fret > 0:

            fretted.append(
                fret
            )


    # Every chord tone must appear at least once.

    heard = set()

    for midi in sounding:

        heard.add(
            midi % 12
        )

    if heard != allowed:

        raise ValueError(
            "Missing chord tone in "
            + chord_name
        )


    # Article idea:
    # Keep the chord compact enough for a real hand.

    if len(fretted) > 1:

        if (
            max(fretted)
            - min(fretted)
        ) > 4:

            raise ValueError(
                "Fret span too wide in "
                + chord_name
            )


    # Article idea:
    # Avoid a lower non-root bass note that muddies the chord.

    if len(sounding) > 0:

        if (
            sounding[0] % 12
        ) != root:

            raise ValueError(
                "Bass is not root in "
                + chord_name
            )


    return True


# Validate all shapes once before spending time rendering audio.

for _name in GUITAR_FRETS:

    validate_fret_shape(
        _name,
        GUITAR_FRETS[
            _name
        ]
    )


# Convert fretboard shapes to the MIDI layout expected by
# the existing string synthesizer.

GUITAR_CHORDS = {}

for _name in GUITAR_FRETS:

    GUITAR_CHORDS[
        _name
    ] = fret_shape_to_midi(

        GUITAR_FRETS[
            _name
        ]
    )


print()
print(
    "ARTICLE-STYLE VOICINGS READY"
)

for _name in GUITAR_FRETS:

    print(
        _name,
        GUITAR_FRETS[
            _name
        ],
        GUITAR_CHORDS[
            _name
        ]
    )


CHORD_ORDER = [
    "C_MAJOR",
    "D_MINOR",
    "E_MINOR",
    "F_MAJOR",
    "G_MAJOR",
    "A_MINOR",
    "B_DIMINISHED",
    "B_MINOR",
    "D_MAJOR",
    "F_SHARP_DIMINISHED",
    "E_DIMINISHED",
    "G_MINOR",
    "B_FLAT_MAJOR"
]


# ============================================================
# RANDOM GENERATOR
# ============================================================

random_state = 0x12345678


def set_seed(value):

    global random_state

    random_state = (
        value & 0xFFFFFFFF
    )


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


def rand_int(low, high):

    if high <= low:
        return low

    value = (
        next_noise() + 32768
    )

    return (
        low
        + value
        * (high - low + 1)
        // 65536
    )


# ============================================================
# MIDI
# ============================================================

def midi_to_frequency(midi):

    return 440.0 * (
        2 ** ((midi - 69) / 12)
    )


# ============================================================
# STRING CHARACTER
# ============================================================

BASE_DETUNE = [
    -1.2,
     0.8,
    -0.6,
     0.5,
    -0.4,
     0.7
]


PICK_POSITION = [
    24,
    22,
    21,
    19,
    18,
    17
]


STRING_LEVEL = [
    8500,
    8200,
    7900,
    7500,
    7100,
    6800
]


# Very slow decay = longer ringing

STRING_DAMPING = [
    32762,
    32760,
    32758,
    32756,
    32754,
    32752
]


# ============================================================
# CREATE PHYSICAL STRING
# ============================================================

def create_string(
    midi,
    string_number,
    performance_strength
):

    frequency = midi_to_frequency(
        midi
    )


    # --------------------------------------------------------
    # Tiny imperfect tuning
    # --------------------------------------------------------

    cents = (
        BASE_DETUNE[string_number]
        + rand_int(-8, 8) / 10.0
    )


    frequency *= (
        2 ** (
            cents / 1200.0
        )
    )


    # Karplus-Strong delay length

    period = int(
        SAMPLE_RATE
        / frequency
        - 0.5
    )


    if period < 4:
        period = 4


    ring = array(
        "h",
        [0] * period
    )


    level = (
        STRING_LEVEL[string_number]
        * performance_strength
        // 100
    )


    level += rand_int(
        -300,
        300
    )


    # --------------------------------------------------------
    # Filtered random displacement
    # --------------------------------------------------------

    previous1 = 0
    previous2 = 0


    for i in range(period):

        raw = next_noise()


        excitation = (
            raw * 5
            + previous1 * 3
            + previous2 * 2
        ) // 10


        previous2 = previous1
        previous1 = raw


        value = (
            excitation
            * level
            // 32768
        )


        if value > 32767:
            value = 32767

        elif value < -32768:
            value = -32768


        ring[i] = value


    # --------------------------------------------------------
    # Pick-position filtering
    # --------------------------------------------------------

    pick_percent = (
        PICK_POSITION[string_number]
        + rand_int(-2, 2)
    )


    pick_delay = (
        period
        * pick_percent
        // 100
    )


    if pick_delay < 1:
        pick_delay = 1


    copy = array(
        "h",
        ring
    )


    for i in range(period):

        other = (
            i - pick_delay
        ) % period


        value = (
            copy[i]
            - copy[other]
            * 52
            // 100
        )


        if value > 32767:
            value = 32767

        elif value < -32768:
            value = -32768


        ring[i] = value


    copy = None


    damping = (
        STRING_DAMPING[string_number]
        + rand_int(-3, 3)
    )


    return [
        ring,
        0,
        period,
        damping
    ]


# ============================================================
# NEXT PHYSICAL STRING SAMPLE
# ============================================================

def string_sample(string):

    ring = string[0]
    index = string[1]
    length = string[2]
    damping = string[3]


    next_index = index + 1


    if next_index >= length:
        next_index = 0


    current = ring[index]

    following = ring[
        next_index
    ]


    filtered = (
        current + following
    ) // 2


    filtered = (
        filtered
        * damping
        >> 15
    )


    if filtered > 32767:
        filtered = 32767

    elif filtered < -32768:
        filtered = -32768


    ring[index] = filtered

    string[1] = next_index


    return current


# ============================================================
# HUMAN STRUM TIMING
# ============================================================

def make_strum_timing(direction):

    starts = [
        0, 0, 0, 0, 0, 0
    ]


    if direction == "DOWN":

        order = [
            0, 1, 2, 3, 4, 5
        ]

        minimum = 5
        maximum = 10


    else:

        order = [
            5, 4, 3, 2, 1, 0
        ]

        minimum = 4
        maximum = 8


    cursor_ms = 0


    for position in range(6):

        string_number = (
            order[position]
        )


        if position > 0:

            cursor_ms += rand_int(
                minimum,
                maximum
            )


        starts[
            string_number
        ] = (
            SAMPLE_RATE
            * cursor_ms
            // 1000
        )


    return starts


# ============================================================
# RENDER ONE PERFORMANCE DIRECTLY TO FLASH
# ============================================================

WRITE_SAMPLES = 512

write_buffer = bytearray(
    WRITE_SAMPLES * 2
)


def render_strum(
    chord_name,
    variation,
    direction,
    seed
):

    print()
    print(
        "Rendering",
        chord_name,
        variation
    )


    set_seed(seed)


    shape = GUITAR_CHORDS[
        chord_name
    ]


    if direction == "DOWN":

        strength = rand_int(
            96,
            108
        )

    else:

        strength = rand_int(
            82,
            98
        )


    starts = make_strum_timing(
        direction
    )


    strings = [
        None,
        None,
        None,
        None,
        None,
        None
    ]


    # --------------------------------------------------------
    # Build physical strings
    # --------------------------------------------------------

    for number in range(6):

        midi = shape[number]


        if midi is not None:

            # Natural up-strums usually don't hit
            # the lowest string as strongly.

            if (
                direction == "UP"
                and number == 0
            ):

                continue


            strings[number] = (
                create_string(
                    midi,
                    number,
                    strength
                )
            )


    # --------------------------------------------------------
    # Individual attack differences
    # --------------------------------------------------------

    string_strengths = []


    for i in range(6):

        string_strengths.append(
            rand_int(
                88,
                112
            )
        )


    # --------------------------------------------------------
    # Guitar body resonance
    # --------------------------------------------------------

    body1 = array(
        "h",
        [0] * 71
    )

    body2 = array(
        "h",
        [0] * 149
    )

    body3 = array(
        "h",
        [0] * 233
    )


    body_i1 = 0
    body_i2 = 0
    body_i3 = 0

    body_low = 0


    pick_samples = max(
        1,
        SAMPLE_RATE * 1 // 1000
    )


    mute_samples = max(
        1,
        SAMPLE_RATE * 4 // 1000
    )


    # 100 ms end fade

    fade_samples = (
        SAMPLE_RATE
        * 100
        // 1000
    )


    filename = (
        BANK_DIR
        + "/"
        + chord_name
        + "_"
        + variation
        + ".raw"
    )


    f = open(
        filename,
        "wb"
    )


    buffer_position = 0


    # ========================================================
    # RENDER
    # ========================================================

    for sample_index in range(
        TOTAL_SAMPLES
    ):

        mixed = 0
        active = 0


        # ----------------------------------------------------
        # Six strings
        # ----------------------------------------------------

        for string_number in range(6):

            start = starts[
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


            # ------------------------------------------------
            # Muted string scratch
            # ------------------------------------------------

            if string is None:

                if age < mute_samples:

                    scratch = next_noise()

                    scratch = (
                        scratch
                        * (
                            mute_samples - age
                        )
                        // mute_samples
                    )

                    scratch = (
                        scratch
                        * 140
                        // 32768
                    )

                    mixed += scratch

                continue


            # ------------------------------------------------
            # Vibrating string
            # ------------------------------------------------

            value = string_sample(
                string
            )


            value = (
                value
                * string_strengths[
                    string_number
                ]
                // 100
            )


            # ------------------------------------------------
            # Pick transient
            # ------------------------------------------------

            if age < pick_samples:

                click = next_noise()

                click = (
                    click
                    * (
                        pick_samples - age
                    )
                    // pick_samples
                )


                brightness = (
                    180
                    + string_number * 30
                )


                click = (
                    click
                    * brightness
                    // 32768
                )


                value += click


            mixed += value

            active += 1


        # ----------------------------------------------------
        # Headroom
        # ----------------------------------------------------

        if active >= 5:

            mixed = (
                mixed * 52 // 100
            )

        elif active >= 3:

            mixed = (
                mixed * 66 // 100
            )

        elif active == 2:

            mixed = (
                mixed * 82 // 100
            )


        # ----------------------------------------------------
        # Guitar body
        # ----------------------------------------------------

        reflection1 = body1[
            body_i1
        ]

        reflection2 = body2[
            body_i2
        ]

        reflection3 = body3[
            body_i3
        ]


        body_low = (
            body_low * 7
            + mixed
        ) // 8


        dry = mixed


        mixed = (
            dry
            + reflection1 * 10 // 100
            + reflection2 * 6 // 100
            + reflection3 * 4 // 100
            + body_low * 7 // 100
        )


        stored = (
            dry * 70 // 100
        )


        if stored > 32767:
            stored = 32767

        elif stored < -32768:
            stored = -32768


        body1[body_i1] = stored
        body2[body_i2] = stored
        body3[body_i3] = stored


        body_i1 += 1

        if body_i1 >= len(body1):
            body_i1 = 0


        body_i2 += 1

        if body_i2 >= len(body2):
            body_i2 = 0


        body_i3 += 1

        if body_i3 >= len(body3):
            body_i3 = 0


        # ----------------------------------------------------
        # Final fade
        # ----------------------------------------------------

        remaining = (
            TOTAL_SAMPLES
            - sample_index
        )


        if remaining < fade_samples:

            mixed = (
                mixed
                * remaining
                // fade_samples
            )


        # ----------------------------------------------------
        # Clamp
        # ----------------------------------------------------

        if mixed > 26000:
            mixed = 26000

        elif mixed < -26000:
            mixed = -26000


        # ----------------------------------------------------
        # MONO 16-BIT FILE
        # ----------------------------------------------------

        struct.pack_into(
            "<h",
            write_buffer,
            buffer_position * 2,
            mixed
        )


        buffer_position += 1


        # ----------------------------------------------------
        # Write small chunk to flash
        # ----------------------------------------------------

        if buffer_position >= WRITE_SAMPLES:

            f.write(
                write_buffer
            )

            buffer_position = 0


    # Final partial chunk

    if buffer_position > 0:

        f.write(
            memoryview(
                write_buffer
            )[
                :buffer_position * 2
            ]
        )


    f.close()


    strings = None
    body1 = None
    body2 = None
    body3 = None

    gc.collect()


    print(
        "Saved:",
        filename
    )


# ============================================================
# CREATE DIRECTORY
# ============================================================

try:

    os.mkdir(
        BANK_DIR
    )

except OSError:

    pass


# ============================================================
# BUILD ENTIRE BANK
# ============================================================

print()
print("==============================")
print("AIRFRET GUITAR BANK BUILDER")
print("==============================")
print()

print(
    "Sample rate:",
    SAMPLE_RATE
)

print(
    "Length:",
    DURATION_MS,
    "ms"
)

print()
print(
    "Building 3 performances per chord..."
)
print()


for chord_index in range(
    len(CHORD_ORDER)
):

    chord = CHORD_ORDER[
        chord_index
    ]


    base_seed = (
        100000
        + chord_index * 10000
    )


    # Natural down strum 1

    render_strum(
        chord,
        "D1",
        "DOWN",
        base_seed + 101
    )


    # Natural down strum 2

    render_strum(
        chord,
        "D2",
        "DOWN",
        base_seed + 202
    )


    # Natural up strum

    render_strum(
        chord,
        "U1",
        "UP",
        base_seed + 303
    )


# ============================================================
# DONE MARKER
# ============================================================

marker = open(
    BANK_DIR + "/READY.txt",
    "w"
)

marker.write(
    "AIRFRET GUITAR BANK READY\n"
)

marker.close()


print()
print("==============================")
print("GUITAR BANK COMPLETE")
print("==============================")
print()

print(
    "Now save/run the performance main.py"
)
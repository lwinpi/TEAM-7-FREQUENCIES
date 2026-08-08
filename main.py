from machine import Pin, ADC, I2S
import math
import struct
import time
import gc


# ============================================================
# AIRFRET PERFORMANCE ENGINE
#
# INSTANT CHORD SWITCHING
# FLASH-BASED GUITAR SOUND BANK
#
# NO VOLUME CONTROL YET
# ============================================================


# ============================================================
# SETTINGS
# ============================================================

SAMPLE_RATE = 22050

BANK_DIR = "/guitar_bank"


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

    p = Pin(
        gpio,
        Pin.OUT
    )

    p.value(1)

    rows.append(
        p
    )


columns = []


for gpio in COL_GPIOS:

    columns.append(

        Pin(
            gpio,
            Pin.IN,
            Pin.PULL_UP
        )
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
# I2S AUDIO
# ============================================================
#
# Small buffer keeps performance responsive.
# ============================================================

audio = I2S(
    0,
    sck=Pin(10),
    ws=Pin(11),
    sd=Pin(12),
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=SAMPLE_RATE,
    ibuf=4096
)


# ============================================================
# VERIFY GUITAR BANK
# ============================================================

try:

    test_file = open(
        BANK_DIR + "/READY.txt",
        "r"
    )

    test_file.close()


except OSError:

    print()
    print(
        "ERROR: GUITAR BANK NOT FOUND"
    )

    print(
        "Run build_bank.py first."
    )

    raise RuntimeError(
        "Guitar bank missing"
    )


# ============================================================
# NOTES
# ============================================================

NOTE_KEYS = {

    "1": (
        "C4",
        60
    ),

    "2": (
        "D4",
        62
    ),

    "3": (
        "E4",
        64
    ),

    "4": (
        "F4",
        65
    ),

    "5": (
        "G4",
        67
    ),

    "6": (
        "A4",
        69
    ),

    "7": (
        "B4",
        71
    ),

    "8": (
        "C5",
        72
    )
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
# STATE
# ============================================================

mode = "NOTE"


selected_scale = (
    "C_MAJOR"
)


chord_index = 0


strum_direction = (
    "DOWN"
)


previous_keys = set()


current_note_key = None


x_ready = True

y_ready = True


previous_switch = 1


last_strum_time = 0


# Alternate between natural down-strum performances

down_variation = 0


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
# CLEAN NOTE ENGINE
# ============================================================

note_buffers = {}


def midi_to_frequency(midi):

    return 440.0 * (

        2 ** (
            (midi - 69)
            / 12
        )
    )


def make_note_buffer(
    midi
):

    frequency = (
        midi_to_frequency(
            midi
        )
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


    for i in range(
        samples
    ):

        phase = (

            2
            * math.pi
            * cycles
            * i
            / samples
        )


        sample = int(

            amplitude
            * math.sin(
                phase
            )
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

    print(
        "Building note mode..."
    )


    for key in NOTE_KEYS:

        name, midi = (
            NOTE_KEYS[
                key
            ]
        )


        note_buffers[
            key
        ] = (

            make_note_buffer(
                midi
            )
        )


    gc.collect()


# ============================================================
# STREAMING GUITAR PLAYBACK
# ============================================================
#
# Guitar files are MONO.
#
# We convert small chunks:
#
# mono:
# L
#
# into stereo:
# L L
#
# while streaming.
#
# No entire chord goes into RAM.
# ============================================================

audio_file = None

audio_active = False


MONO_CHUNK_BYTES = 512


# 512 mono bytes
# become 1024 stereo bytes

stereo_buffer = bytearray(
    MONO_CHUNK_BYTES * 2
)


stereo_view = memoryview(
    stereo_buffer
)


# ============================================================
# STOP CURRENT SAMPLE
# ============================================================

def stop_stream():

    global audio_file
    global audio_active


    if audio_file is not None:

        try:

            audio_file.close()

        except:

            pass


    audio_file = None

    audio_active = False


# ============================================================
# START A GUITAR STRUM
# ============================================================

def start_strum():

    global audio_file
    global audio_active

    global down_variation


    # Stop old flash stream immediately.

    stop_stream()


    chord = (
        current_chord()
    )


    # --------------------------------------------------------
    # Choose performance
    # --------------------------------------------------------

    if strum_direction == "DOWN":


        if down_variation == 0:

            version = "D1"

            down_variation = 1


        else:

            version = "D2"

            down_variation = 0


    else:

        version = "U1"


    filename = (

        BANK_DIR
        + "/"
        + chord
        + "_"
        + version
        + ".raw"
    )


    try:

        audio_file = open(
            filename,
            "rb"
        )


    except OSError:

        print(
            "Missing:",
            filename
        )

        audio_file = None

        audio_active = False

        return


    audio_active = True


    print(
        "STRUM:",
        strum_direction,
        chord,
        version
    )


# ============================================================
# SERVICE FLASH AUDIO
# ============================================================
#
# IMPORTANT:
#
# We only process a tiny chunk each loop.
#
# This means keypad + joystick are still checked
# while a 900ms guitar chord is ringing.
# ============================================================

def service_audio():

    global audio_file
    global audio_active


    if not audio_active:

        return


    data = audio_file.read(
        MONO_CHUNK_BYTES
    )


    if not data:

        stop_stream()

        return


    length = len(
        data
    )


    # Must contain complete 16-bit samples

    if length & 1:

        length -= 1


    out = 0


    # --------------------------------------------------------
    # MONO 16 BIT -> STEREO 16 BIT
    # --------------------------------------------------------

    for i in range(
        0,
        length,
        2
    ):

        low_byte = data[i]

        high_byte = data[
            i + 1
        ]


        stereo_buffer[
            out
        ] = low_byte


        stereo_buffer[
            out + 1
        ] = high_byte


        stereo_buffer[
            out + 2
        ] = low_byte


        stereo_buffer[
            out + 3
        ] = high_byte


        out += 4


    audio.write(
        stereo_view[
            :out
        ]
    )


# ============================================================
# NOTE PLAYBACK
# ============================================================

def play_note_piece(
    buffer
):

    # Notes are already stereo.

    audio.write(
        buffer
    )


# ============================================================
# CHORD DISPLAY
# ============================================================

def show_current():

    print()

    print(
        "SCALE:",
        selected_scale
    )


    print(
        "CHORD:",
        current_chord()
    )


    print(
        "STRUM:",
        strum_direction
    )


# ============================================================
# SELECT SCALE
# ============================================================
#
# NO AUDIO GENERATION HERE.
#
# This should be essentially instantaneous.
# ============================================================

def select_scale(
    scale
):

    global selected_scale
    global chord_index


    selected_scale = (
        scale
    )


    chord_index = 0


    show_current()


# ============================================================
# NEXT CHORD
# ============================================================
#
# Again:
#
# ZERO synthesis.
# ZERO loading.
# ZERO preparation.
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


# ============================================================
# DIRECTION
# ============================================================

def set_down():

    global strum_direction


    if strum_direction != "DOWN":

        strum_direction = "DOWN"


        print(
            "STRUM: DOWN"
        )


def set_up():

    global strum_direction


    if strum_direction != "UP":

        strum_direction = "UP"


        print(
            "STRUM: UP"
        )


def toggle_direction():

    if strum_direction == "DOWN":

        set_up()

    else:

        set_down()


# ============================================================
# KEYPAD SCANNER
# ============================================================

def scan_keypad():

    pressed = set()


    for row_index in range(
        4
    ):

        for row in rows:

            row.value(1)


        rows[
            row_index
        ].value(0)


        time.sleep_us(
            40
        )


        for column_index in range(
            3
        ):

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

def handle_key_press(
    key
):

    global mode

    global current_note_key


    # --------------------------------------------------------
    # NOTE MODE
    # --------------------------------------------------------

    if key == "*":

        stop_stream()


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

        current_note_key = None


        mode = "CHORD"


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


        stop_stream()


        print(
            "STOP"
        )


        return


    # --------------------------------------------------------
    # NOTE MODE
    # --------------------------------------------------------

    if mode == "NOTE":


        if key in NOTE_KEYS:


            stop_stream()


            current_note_key = (
                key
            )


            print(
                "NOTE:",
                NOTE_KEYS[
                    key
                ][0]
            )


    # --------------------------------------------------------
    # CHORD MODE
    # --------------------------------------------------------

    elif mode == "CHORD":


        if key in SCALE_KEYS:


            select_scale(

                SCALE_KEYS[
                    key
                ]
            )


        elif key == "9":


            toggle_direction()


# ============================================================
# JOYSTICK
# ============================================================

def read_joystick():

    global x_ready
    global y_ready

    global previous_switch
    global last_strum_time


    x = (
        joystick_x.read_u16()
    )


    y = (
        joystick_y.read_u16()
    )


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
    # CHORD MODE CONTROLS
    # --------------------------------------------------------

    if mode == "CHORD":


        # ====================================================
        # LEFT / RIGHT = CHORD
        # ====================================================

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


        # ====================================================
        # UP / DOWN = STRUM DIRECTION
        # ====================================================

        elif (
            abs(dy) > abs(dx)
            and abs(dy) > MOVE_DISTANCE
            and y_ready
        ):


            if dy > 0:

                set_up()


            else:

                set_down()


            y_ready = False


    # --------------------------------------------------------
    # JOYSTICK BUTTON = STRUM
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
        ) > 100
    ):


        start_strum()


        last_strum_time = (
            now
        )


    previous_switch = (
        switch
    )


# ============================================================
# INITIALIZE
# ============================================================

build_notes()


print()
print("================================")
print(" AIRFRET PERFORMANCE MODE")
print("================================")
print()

print("GUITAR BANK: READY")
print()

print("* = NOTE MODE")
print("# = CHORD MODE")
print("0 = STOP")
print()

print("CHORD MODE:")
print("1 = C MAJOR SCALE")
print("2 = G MAJOR SCALE")
print("3 = A MINOR SCALE")
print("4 = D MINOR SCALE")
print()

print("JOYSTICK:")
print("LEFT / RIGHT = CHANGE CHORD")
print("UP = UP STRUM")
print("DOWN = DOWN STRUM")
print("PRESS = STRUM")
print()

print("9 = TOGGLE UP / DOWN")
print()

print("VOLUME CONTROL DISABLED")
print()

print("AIRFRET READY")
print()


# ============================================================
# MAIN PERFORMANCE LOOP
# ============================================================

while True:


    # ========================================================
    # KEYPAD
    # ========================================================

    current_keys = (
        scan_keypad()
    )


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

            and key
            == current_note_key
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


    # ========================================================
    # JOYSTICK
    # ========================================================

    read_joystick()


    # ========================================================
    # CHORD AUDIO STREAM
    # ========================================================

    if (
        mode == "CHORD"
        and audio_active
    ):

        service_audio()


    # ========================================================
    # NOTE MODE
    # ========================================================

    elif (
        mode == "NOTE"
        and current_note_key
        is not None
    ):

        play_note_piece(

            note_buffers[
                current_note_key
            ]
        )


    else:

        time.sleep_ms(
            1
        )
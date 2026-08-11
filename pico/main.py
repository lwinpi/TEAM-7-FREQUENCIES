from machine import Pin, ADC, I2S, I2C
import math
import struct
import time
import gc
import ssd1306


def send_to_website(event, *values):
    """Write one compact event for the computer's WebSocket bridge."""
    message = "AIRFRET|" + str(event)

    for value in values:
        message += "|" + str(value)

    print(message)


# ============================================================
# AIRFRET CLEAN CONTINUOUS PERFORMANCE ENGINE
#
# INSTANT CHORD SWITCHING
# FLASH-BASED GUITAR SOUND BANK
#
# FILTERED SLIDER VOLUME CONTROL
# OLED VOLUME DISPLAY
# ============================================================


# ============================================================
# SETTINGS
# ============================================================

SAMPLE_RATE = 22050

BANK_DIR = "/guitar_bank"

FX_DIR = "/airfret_fx"

NOTE_FX_DIR = "/note_fx"


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


# ============================================================
# VOLUME SLIDER
# ============================================================
# Slider fixed ends -> 3V3 and GND
# Slider wiper -> GP26 / ADC0
#
# Software filtering:
# - averages ADC readings
# - low-pass smoothing
# - endpoint dead zones
# - 2% hysteresis
# ============================================================

volume_adc = ADC(26)

VOLUME_MIN = 2500
VOLUME_MAX = 63000

volume_filtered = volume_adc.read_u16()

if volume_filtered <= VOLUME_MIN:
    volume_percent = 0
elif volume_filtered >= VOLUME_MAX:
    volume_percent = 100
else:
    volume_percent = (
        (volume_filtered - VOLUME_MIN)
        * 100
        // (VOLUME_MAX - VOLUME_MIN)
    )

# 0 = mute, 256 = full scale
volume_gain = (
    volume_percent * 256 // 100
)

last_volume_read_time = 0
last_volume_oled_time = 0

VOLUME_READ_INTERVAL_MS = 8
VOLUME_OLED_INTERVAL_MS = 80


CENTER_X = 31815

CENTER_Y = 33096


MOVE_DISTANCE = 6000

RESET_DISTANCE = 3000


# ============================================================
# OLED DISPLAY
# ============================================================
# SSD1306 I2C OLED
# SDA -> GP20
# SCL -> GP21
# Address -> 0x3C
# ============================================================

oled_i2c = I2C(
    0,
    sda=Pin(20),
    scl=Pin(21),
    freq=50000
)


oled = ssd1306.SSD1306_I2C(
    128,
    64,
    oled_i2c,
    addr=0x3C
)


# ============================================================
# RIGHT-HAND MPU6050 - SIMPLE FIXED-X STRUM
# ============================================================
#
# Final simplified detector:
#   - X gyro only in SOFTWARE
#   - Y/Z ignored
#   - no accelerometer conditions
#   - no angle calculations
#   - no center gate
#   - no auto-axis detection
#
# A strum requires:
#   1) GX crosses +/-190 dps
#   2) it stays across the threshold for 2 consecutive reads
#
# After a strum:
#   - detector stays locked until |GX| <= 35 dps
#     continuously for 45 ms
#
# +GX = DOWN
# -GX = UP
# keypad 9 can reverse the mapping if needed.
# ============================================================

MPU_PWR_MGMT_1 = 0x6B
MPU_GYRO_CONFIG = 0x1B
MPU_GYRO_XOUT_H = 0x43

# +/-1000 dps
GYRO_SCALE = 32.8

GYRO_READ_INTERVAL_MS = 6

GYRO_TRIGGER_DPS = 190.0
GYRO_RESET_DPS = 35.0
GYRO_RESET_TIME_MS = 45
GYRO_CONFIRM_READS = 2

GYRO_REVERSE = False

gyro_enabled = False
gyro_addr = None

gyro_buffer = bytearray(2)

gyro_bias_x = 0.0

gyro_armed = True
gyro_reset_start = None

gyro_candidate_direction = 0
gyro_candidate_reads = 0

last_gyro_read_time = 0


def gyro_signed16(high, low):

    value = (
        (high << 8)
        | low
    )

    if value & 0x8000:
        value -= 65536

    return value


def read_gyro_x():

    oled_i2c.readfrom_mem_into(
        gyro_addr,
        MPU_GYRO_XOUT_H,
        gyro_buffer
    )

    raw = gyro_signed16(
        gyro_buffer[0],
        gyro_buffer[1]
    )

    return (
        raw / GYRO_SCALE
    )


def initialize_gyro():

    global gyro_enabled
    global gyro_addr
    global gyro_bias_x

    global gyro_armed
    global gyro_reset_start
    global gyro_candidate_direction
    global gyro_candidate_reads
    global last_gyro_read_time


    devices = oled_i2c.scan()


    if 0x68 in devices:

        gyro_addr = 0x68

    elif 0x69 in devices:

        gyro_addr = 0x69

    else:

        print(
            "GYRO: MPU6050 NOT FOUND"
        )

        gyro_enabled = False

        return


    # Wake sensor.
    oled_i2c.writeto_mem(
        gyro_addr,
        MPU_PWR_MGMT_1,
        b"\x00"
    )

    time.sleep_ms(
        100
    )


    # +/-1000 dps.
    oled_i2c.writeto_mem(
        gyro_addr,
        MPU_GYRO_CONFIG,
        b"\x10"
    )

    time.sleep_ms(
        50
    )


    print()
    print(
        "GYRO:",
        hex(gyro_addr)
    )

    print(
        "SIMPLE FIXED-X STRUM"
    )

    print(
        "HOLD PICK STILL FOR 1 SECOND..."
    )


    sample_count = 140
    total = 0.0


    for _ in range(
        sample_count
    ):

        total += read_gyro_x()

        time.sleep_ms(
            7
        )


    gyro_bias_x = (
        total
        / sample_count
    )


    gyro_armed = True
    gyro_reset_start = None

    gyro_candidate_direction = 0
    gyro_candidate_reads = 0

    last_gyro_read_time = (
        time.ticks_ms()
    )

    gyro_enabled = True


    print(
        "GX BIAS: %.2f dps"
        % gyro_bias_x
    )

    print(
        "TRIGGER: %.0f dps x %d reads"
        % (
            GYRO_TRIGGER_DPS,
            GYRO_CONFIRM_READS
        )
    )

    print(
        "+GX = DOWN | -GX = UP"
    )

    print(
        "GYRO READY"
    )

    print()


def toggle_gyro_reverse():

    global GYRO_REVERSE

    GYRO_REVERSE = (
        not GYRO_REVERSE
    )

    print(
        "GYRO REVERSE:",
        GYRO_REVERSE
    )

    send_to_website(
        "GYRO_REVERSE",
        "ON" if GYRO_REVERSE else "OFF"
    )

    update_oled()


def service_gyro_strum():

    global gyro_armed
    global gyro_reset_start

    global gyro_candidate_direction
    global gyro_candidate_reads

    global last_gyro_read_time

    global strum_direction


    if (
        not gyro_enabled
        or mode != "CHORD"
    ):

        return


    now = time.ticks_ms()


    if time.ticks_diff(
        now,
        last_gyro_read_time
    ) < GYRO_READ_INTERVAL_MS:

        return


    last_gyro_read_time = now


    try:

        gx = (
            read_gyro_x()
            - gyro_bias_x
        )

    except OSError:

        return


    if GYRO_REVERSE:

        gx = -gx


    # ========================================================
    # ARMED: LOOK FOR A REAL STRUM
    # ========================================================

    if gyro_armed:

        direction_now = 0


        if gx >= GYRO_TRIGGER_DPS:

            direction_now = 1


        elif gx <= -GYRO_TRIGGER_DPS:

            direction_now = -1


        if direction_now == 0:

            gyro_candidate_direction = 0
            gyro_candidate_reads = 0


        elif (
            direction_now
            == gyro_candidate_direction
        ):

            gyro_candidate_reads += 1


        else:

            gyro_candidate_direction = (
                direction_now
            )

            gyro_candidate_reads = 1


        if (
            gyro_candidate_reads
            < GYRO_CONFIRM_READS
        ):

            return


        # ====================================================
        # CONFIRMED STRUM
        # ====================================================

        if gyro_candidate_direction > 0:

            strum_direction = "DOWN"

        else:

            strum_direction = "UP"


        print(
            "STRUM %-4s | %4d dps"
            % (
                strum_direction,
                int(gx)
            )
        )


        # Use the existing clean guitar playback.
        start_strum()


        gyro_armed = False

        gyro_reset_start = None

        gyro_candidate_direction = 0
        gyro_candidate_reads = 0

        return


    # ========================================================
    # LOCKED: WAIT FOR WRIST TO SLOW BEFORE RE-ARM
    # ========================================================

    if abs(gx) <= GYRO_RESET_DPS:


        if gyro_reset_start is None:

            gyro_reset_start = now


        elif time.ticks_diff(
            now,
            gyro_reset_start
        ) >= GYRO_RESET_TIME_MS:

            gyro_armed = True

            gyro_reset_start = None


    else:

        gyro_reset_start = None


CHORD_DISPLAY = {
    "C_MAJOR": "C MAJOR",
    "D_MINOR": "D MINOR",
    "E_MINOR": "E MINOR",
    "F_MAJOR": "F MAJOR",
    "G_MAJOR": "G MAJOR",
    "A_MINOR": "A MINOR",
    "B_DIMINISHED": "B DIM",
    "B_MINOR": "B MINOR",
    "D_MAJOR": "D MAJOR",
    "F_SHARP_DIMINISHED": "F# DIM",
    "E_DIMINISHED": "E DIM",
    "G_MINOR": "G MINOR",
    "B_FLAT_MAJOR": "Bb MAJOR"
}


SHORT_CHORD = {
    "C_MAJOR": "C",
    "D_MINOR": "Dm",
    "E_MINOR": "Em",
    "F_MAJOR": "F",
    "G_MAJOR": "G",
    "A_MINOR": "Am",
    "B_DIMINISHED": "Bdim",
    "B_MINOR": "Bm",
    "D_MAJOR": "D",
    "F_SHARP_DIMINISHED": "F#dim",
    "E_DIMINISHED": "Edim",
    "G_MINOR": "Gm",
    "B_FLAT_MAJOR": "Bb"
}


SCALE_DISPLAY = {
    "C_MAJOR": "C MAJOR",
    "G_MAJOR": "G MAJOR",
    "A_MINOR": "A MINOR",
    "D_MINOR": "D MINOR",
    "COUNTRY_ROADS": "COUNTRY RD",
    "NEVER_A": "VERSE A",
    "NEVER_B": "VERSE B",
    "STAND_BY_ME": "STAND BY ME"
}


# ============================================================
# I2S AUDIO
# ============================================================
#
# Small buffer keeps retriggering responsive without mixing guitar voices.
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

    "4": "D_MINOR",

    "5": "COUNTRY_ROADS",

    "6": "NEVER_A",

    "7": "NEVER_B",

    "8": "STAND_BY_ME"
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
    ],


    # Country Roads progression requested:
    # G -> Em -> D -> C -> G
    "COUNTRY_ROADS": [

        "G_MAJOR",
        "E_MINOR",
        "D_MAJOR",
        "C_MAJOR",
        "G_MAJOR"
    ],


    # "They'll Never Never Take Her Love From Me"
    # Verse A pattern:
    # G -> C -> D -> G -> C -> D -> G
    "NEVER_A": [

        "G_MAJOR",
        "C_MAJOR",
        "D_MAJOR",
        "G_MAJOR",
        "C_MAJOR",
        "D_MAJOR",
        "G_MAJOR"
    ],


    # Verse B / bridge pattern:
    # C -> G -> D -> G -> C -> D -> G
    "NEVER_B": [

        "C_MAJOR",
        "G_MAJOR",
        "D_MAJOR",
        "G_MAJOR",
        "C_MAJOR",
        "D_MAJOR",
        "G_MAJOR"
    ],


    # Stand By Me mode
    # Simple repeating progression:
    # G -> Em -> C -> D
    "STAND_BY_ME": [

        "G_MAJOR",
        "E_MINOR",
        "C_MAJOR",
        "D_MAJOR"
    ]
}


# ============================================================
# PERFORMANCE EFFECT SOUNDS
# ============================================================
#
# These are pre-rendered RAW files, not live DSP.
# That keeps your clean guitar/chord engine untouched.
#
# Required Pico files:
#   /airfret_fx/WAH.raw
#   /airfret_fx/PLUCK.raw
#   /airfret_fx/WHIP.raw
# ============================================================

EFFECT_ORDER = [
    "WAH",
    "PLUCK",
    "WHIP"
]


EFFECT_FILES = {
    "WAH": FX_DIR + "/WAH.raw",
    "PLUCK": FX_DIR + "/PLUCK.raw",
    "WHIP": FX_DIR + "/WHIP.raw"
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


# Selected performance effect

effect_index = 0


# ============================================================
# NOTE EFFECTS
# ============================================================
#
# NOTE MODE ONLY:
#
# CLEAN  = original sine-wave note
# OCTAVE = same note one octave higher
# SYNTH  = brighter triangle-wave synth tone
#
# Joystick LEFT / RIGHT changes the note effect.
#
# CHORD MODE IS UNCHANGED.
# ============================================================

NOTE_EFFECTS = [
    "CLEAN",
    "OCTAVE",
    "SYNTH",
    "WAH",
    "LASER"
]


# Only these three are synthesized into RAM at boot.
# WAH uses pre-rendered RAW files from flash.
BUFFERED_NOTE_EFFECTS = [
    "CLEAN",
    "OCTAVE",
    "SYNTH"
]


WAH_NOTE_FILES = {
    "1": NOTE_FX_DIR + "/WAH_C4.raw",
    "2": NOTE_FX_DIR + "/WAH_D4.raw",
    "3": NOTE_FX_DIR + "/WAH_E4.raw",
    "4": NOTE_FX_DIR + "/WAH_F4.raw",
    "5": NOTE_FX_DIR + "/WAH_G4.raw",
    "6": NOTE_FX_DIR + "/WAH_A4.raw",
    "7": NOTE_FX_DIR + "/WAH_B4.raw",
    "8": NOTE_FX_DIR + "/WAH_C5.raw"
}


LASER_NOTE_FILES = {
    "1": NOTE_FX_DIR + "/LASER_C4.raw",
    "2": NOTE_FX_DIR + "/LASER_D4.raw",
    "3": NOTE_FX_DIR + "/LASER_E4.raw",
    "4": NOTE_FX_DIR + "/LASER_F4.raw",
    "5": NOTE_FX_DIR + "/LASER_G4.raw",
    "6": NOTE_FX_DIR + "/LASER_A4.raw",
    "7": NOTE_FX_DIR + "/LASER_B4.raw",
    "8": NOTE_FX_DIR + "/LASER_C5.raw"
}

note_effect_index = 0


def current_note_effect():

    return NOTE_EFFECTS[
        note_effect_index
    ]


def current_effect():

    return EFFECT_ORDER[
        effect_index
    ]


def next_note_effect():

    global note_effect_index


    stop_stream()

    note_effect_index += 1

    if note_effect_index >= len(
        NOTE_EFFECTS
    ):

        note_effect_index = 0

    print(
        "NOTE FX:",
        current_note_effect()
    )

    send_to_website(
        "NOTE_FX",
        current_note_effect()
    )

    update_oled()


def previous_note_effect():

    global note_effect_index


    stop_stream()

    note_effect_index -= 1

    if note_effect_index < 0:

        note_effect_index = (
            len(NOTE_EFFECTS) - 1
        )

    print(
        "NOTE FX:",
        current_note_effect()
    )

    send_to_website(
        "NOTE_FX",
        current_note_effect()
    )

    update_oled()


# ============================================================
# PERFORMANCE EFFECT SELECTION
# ============================================================

def next_effect():

    global effect_index


    stop_stream()


    effect_index += 1


    if effect_index >= len(
        EFFECT_ORDER
    ):

        effect_index = 0


    print(
        "PERFORMANCE FX:",
        current_effect()
    )

    send_to_website(
        "EFFECT_SELECT",
        current_effect()
    )


    update_oled()


def previous_effect():

    global effect_index


    stop_stream()


    effect_index -= 1


    if effect_index < 0:

        effect_index = (
            len(EFFECT_ORDER) - 1
        )


    print(
        "PERFORMANCE FX:",
        current_effect()
    )

    send_to_website(
        "EFFECT_SELECT",
        current_effect()
    )


    update_oled()


def enter_effect_mode():

    global mode
    global current_note_key


    stop_stream()


    current_note_key = None


    mode = "FX"

    send_to_website(
        "MODE",
        mode
    )

    send_to_website(
        "EFFECT_SELECT",
        current_effect()
    )


    print(
        "MODE: PERFORMANCE FX"
    )


    print(
        "PERFORMANCE FX:",
        current_effect()
    )


    update_oled()


# ============================================================
# CURRENT CHORD
# ============================================================

def current_chord():

    return SCALES[
        selected_scale
    ][
        chord_index
    ]


def center_text(text, y):

    x = (128 - len(text) * 8) // 2

    if x < 0:
        x = 0

    oled.text(
        text,
        x,
        y
    )


def update_oled(playing=False):

    oled.fill(0)


    if mode == "NOTE":

        center_text(
            "AIRFRET",
            0
        )

        center_text(
            "NOTE MODE",
            12
        )

        if current_note_key is not None:

            note_name = NOTE_KEYS[
                current_note_key
            ][0]

            center_text(
                "NOTE: " + note_name,
                28
            )

        else:

            center_text(
                "PRESS 1-8",
                28
            )

        center_text(
            "FX: " + current_note_effect(),
            38
        )

        center_text(
            "VOL: " + str(volume_percent) + "%",
            48
        )

        center_text(
            "# = CHORD",
            56
        )


    elif mode == "CHORD":

        chord_list = SCALES[
            selected_scale
        ]

        # ----------------------------------------------------
        # SPECIAL SONG DISPLAY
        # ----------------------------------------------------
        if (
            selected_scale == "NEVER_A"
            or selected_scale == "NEVER_B"
            or selected_scale == "STAND_BY_ME"
        ):

            next_name = chord_list[
                (chord_index + 1) % len(chord_list)
            ]

            if selected_scale == "STAND_BY_ME":

                center_text(
                    "STAND BY ME",
                    0
                )

                center_text(
                    "LOOP "
                    + str(chord_index + 1)
                    + "/"
                    + str(len(chord_list)),
                    12
                )

            else:

                center_text(
                    "NEVER NEVER",
                    0
                )

                section_name = (
                    "VERSE A"
                    if selected_scale == "NEVER_A"
                    else "VERSE B"
                )

                center_text(
                    section_name
                    + " "
                    + str(chord_index + 1)
                    + "/"
                    + str(len(chord_list)),
                    12
                )

            center_text(
                CHORD_DISPLAY.get(
                    current_chord(),
                    current_chord()
                ),
                25
            )

            center_text(
                "NEXT: "
                + SHORT_CHORD.get(
                    next_name,
                    next_name
                ),
                37
            )

            center_text(
                "STRUM: " + strum_direction,
                48
            )

            center_text(
                "VOL:" + str(volume_percent) + "%",
                57
            )

        else:

            previous_name = chord_list[
                (chord_index - 1) % len(chord_list)
            ]

            next_name = chord_list[
                (chord_index + 1) % len(chord_list)
            ]

            center_text(
                CHORD_DISPLAY.get(
                    current_chord(),
                    current_chord()
                ),
                0
            )

            oled.text(
                "<" + SHORT_CHORD.get(
                    previous_name,
                    previous_name
                ),
                0,
                14
            )

            right_text = SHORT_CHORD.get(
                next_name,
                next_name
            ) + ">"

            right_x = 128 - len(right_text) * 8

            if right_x < 0:
                right_x = 0

            oled.text(
                right_text,
                right_x,
                14
            )

            center_text(
                "STRUM: " + strum_direction,
                24
            )

            center_text(
                "VOL: " + str(volume_percent) + "%",
                36
            )

            center_text(
                "UP/DOWN = PLAY",
                46
            )

            center_text(
                "SCALE " + SCALE_DISPLAY.get(
                    selected_scale,
                    selected_scale
                ),
                56
            )


    elif mode == "FX":

        previous_fx = EFFECT_ORDER[
            (effect_index - 1) % len(EFFECT_ORDER)
        ]

        next_fx = EFFECT_ORDER[
            (effect_index + 1) % len(EFFECT_ORDER)
        ]


        center_text(
            "PERFORMANCE FX",
            0
        )


        center_text(
            current_effect(),
            14
        )


        oled.text(
            "<" + previous_fx,
            0,
            29
        )


        right_text = (
            next_fx + ">"
        )

        right_x = (
            128 - len(right_text) * 8
        )

        if right_x < 0:

            right_x = 0


        oled.text(
            right_text,
            right_x,
            29
        )


        if playing:

            center_text(
                "PLAYING",
                43
            )

        else:

            center_text(
                "PRESS = PLAY",
                43
            )


        center_text(
            "VOL:" + str(volume_percent) + "%",
            55
        )


    oled.show()


# ============================================================
# FILTERED VOLUME READER
# ============================================================

def service_volume():

    global volume_filtered
    global volume_percent
    global volume_gain

    global last_volume_read_time
    global last_volume_oled_time


    now = time.ticks_ms()


    # Read the knob very frequently so intentional turns
    # feel immediate.
    if time.ticks_diff(
        now,
        last_volume_read_time
    ) < VOLUME_READ_INTERVAL_MS:

        return


    last_volume_read_time = now


    # A small 4-read average removes ADC spikes without
    # adding noticeable control lag.
    total = 0

    for _ in range(4):

        total += volume_adc.read_u16()


    average = total // 4


    # Adaptive filtering:
    # - big movement = snap immediately to the knob
    # - tiny movement = smooth noise while stationary
    difference = abs(
        average - volume_filtered
    )


    if difference >= 1200:

        # User is actually turning the knob.
        volume_filtered = average

    else:

        # Knob is nearly stationary: reject small jitter.
        volume_filtered = (
            volume_filtered * 3
            + average
        ) // 4


    # Endpoint dead zones.
    if volume_filtered <= VOLUME_MIN:

        new_percent = 0

    elif volume_filtered >= VOLUME_MAX:

        new_percent = 100

    else:

        new_percent = (
            (volume_filtered - VOLUME_MIN)
            * 100
            // (VOLUME_MAX - VOLUME_MIN)
        )


    # 1% hysteresis keeps the reading stable while still
    # responding almost immediately when the knob moves.
    force_endpoint = (
        new_percent == 0
        or new_percent == 100
    )


    if (
        force_endpoint
        or abs(
            new_percent - volume_percent
        ) >= 1
    ):

        if new_percent != volume_percent:

            volume_percent = new_percent

            volume_gain = (
                volume_percent
                * 256
                // 100
            )


            print(
                "VOLUME:",
                volume_percent,
                "%"
            )

            send_to_website(
                "VOLUME",
                volume_percent
            )


            # The AUDIO volume changes immediately because
            # volume_gain is already updated above.
            # OLED refresh stays throttled to protect audio.
            if (
                not audio_active
                and current_note_key is None
                and time.ticks_diff(
                    now,
                    last_volume_oled_time
                ) >= VOLUME_OLED_INTERVAL_MS
            ):

                update_oled()

                last_volume_oled_time = now


# ============================================================
# CLEAN NOTE ENGINE
# ============================================================

note_buffers = {
    "CLEAN": {},
    "OCTAVE": {},
    "SYNTH": {}
}

note_output_buffer = None
note_output_view = None


def midi_to_frequency(midi):

    return 440.0 * (

        2 ** (
            (midi - 69)
            / 12
        )
    )


def make_note_buffer(
    midi,
    effect
):

    # OCTAVE raises the note by 12 semitones.
    if effect == "OCTAVE":

        midi += 12


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


    # Keep at least a few samples in the loop.
    if samples < 16:

        samples = 16


    buf = bytearray(
        samples * 4
    )


    # --------------------------------------------------------
    # CLEAN / OCTAVE
    # --------------------------------------------------------
    # Both use a smooth sine wave. OCTAVE changes pitch only.
    # --------------------------------------------------------
    if (
        effect == "CLEAN"
        or effect == "OCTAVE"
    ):

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


    # --------------------------------------------------------
    # SYNTH
    # --------------------------------------------------------
    # Triangle wave:
    # noticeably more electronic than CLEAN,
    # but smoother and less harsh than a square wave.
    # --------------------------------------------------------
    else:

        amplitude = 3600

        for i in range(
            samples
        ):

            phase = (
                (
                    cycles * i
                    / samples
                )
                % 1.0
            )

            if phase < 0.25:

                value = (
                    phase * 4.0
                )

            elif phase < 0.75:

                value = (
                    2.0
                    - phase * 4.0
                )

            else:

                value = (
                    phase * 4.0
                    - 4.0
                )

            sample = int(
                amplitude * value
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

    global note_output_buffer
    global note_output_view


    print(
        "Building note mode..."
    )


    for effect in BUFFERED_NOTE_EFFECTS:

        print(
            "Building note FX:",
            effect
        )

        for key in NOTE_KEYS:

            name, midi = (
                NOTE_KEYS[
                    key
                ]
            )


            note_buffers[
                effect
            ][
                key
            ] = (

                make_note_buffer(
                    midi,
                    effect
                )
            )


    # One reusable buffer for volume-scaled note playback.
    max_note_bytes = max(

        len(buf)

        for effect_buffers
        in note_buffers.values()

        for buf
        in effect_buffers.values()
    )

    note_output_buffer = bytearray(
        max_note_bytes
    )

    note_output_view = memoryview(
        note_output_buffer
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

# Keep track of the currently playing bank file so we can reuse
# a natural part of its decay as a quiet sustain tail.
current_audio_filename = None

audio_position_bytes = 0

sustain_active = False
sustain_pass_index = 0
sustain_gain = 256


# ============================================================
# NATURAL CHORD HOLD
# ============================================================
#
# The original guitar-bank files stay completely unchanged.
#
# Instead of making the bank files larger, AirFret plays the
# natural first ~1.15 seconds, then reuses progressively later
# pieces of the chord's own decay at lower levels.
#
# This extends a chord to roughly 2.3 seconds while keeping
# immediate retriggering: a new strum always interrupts the
# ringing chord instantly.
#
# Each tuple:
# (start_ms, end_ms, gain_0_to_256)
# ============================================================

MAIN_RING_MS = 1300

SUSTAIN_PASSES = [
    (700, 1300, 150),   # ~59% level, 600 ms
    (800, 1300, 105),   # ~41% level, 500 ms
    (900, 1300, 70),    # ~27% level, 400 ms
    (1000, 1300, 40),   # ~16% level, 300 ms
]


def ms_to_mono_bytes(ms):

    # Mono 16-bit = 2 bytes per sample.
    value = (
        SAMPLE_RATE
        * 2
        * ms
        // 1000
    )

    # Keep file position aligned to a complete 16-bit sample.
    return value & ~1


MAIN_RING_BYTES = ms_to_mono_bytes(
    MAIN_RING_MS
)


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
    global current_audio_filename
    global audio_position_bytes
    global sustain_active
    global sustain_pass_index
    global sustain_gain


    if audio_file is not None:

        try:

            audio_file.close()

        except:

            pass


    audio_file = None

    audio_active = False

    current_audio_filename = None

    audio_position_bytes = 0

    sustain_active = False

    sustain_pass_index = 0

    sustain_gain = 256


# ============================================================
# START A GUITAR STRUM
# ============================================================

def start_strum():

    global audio_file
    global audio_active
    global current_audio_filename
    global audio_position_bytes
    global sustain_active
    global sustain_pass_index
    global sustain_gain

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


    current_audio_filename = filename

    audio_position_bytes = 0

    sustain_active = False

    sustain_pass_index = 0

    sustain_gain = 256

    audio_active = True

    send_to_website(
        "STRUM",
        strum_direction,
        chord,
        selected_scale
    )


    # Do not redraw the OLED here. SSD1306 I2C updates can delay
    # the attack of a rapid strum. The display is refreshed by
    # normal chord/direction/volume state changes and at sample end.

    # Keep the attack path fast. Avoid terminal printing here.
    # Audio begins on the next service_audio() pass.


# ============================================================
# START A PERFORMANCE EFFECT
# ============================================================
#
# Effects use their own direct RAW files.
# No sustain-loop logic and no filtering are added.
# ============================================================

def start_effect():

    global audio_file
    global audio_active
    global current_audio_filename
    global audio_position_bytes
    global sustain_active
    global sustain_pass_index
    global sustain_gain


    stop_stream()


    effect = (
        current_effect()
    )


    filename = (
        EFFECT_FILES[
            effect
        ]
    )


    try:

        audio_file = open(
            filename,
            "rb"
        )


    except OSError:

        print(
            "MISSING EFFECT:",
            filename
        )

        audio_file = None

        audio_active = False

        update_oled()

        return


    current_audio_filename = filename

    audio_position_bytes = 0

    sustain_active = False

    sustain_pass_index = 0

    sustain_gain = 256

    audio_active = True

    send_to_website(
        "EFFECT_PLAY",
        effect
    )


    print(
        "PLAY FX:",
        effect
    )


    update_oled(
        playing=True
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

def start_sustain_pass():

    global audio_file
    global audio_position_bytes
    global sustain_active
    global sustain_pass_index
    global sustain_gain


    if sustain_pass_index >= len(
        SUSTAIN_PASSES
    ):

        return False


    start_ms, end_ms, gain = (
        SUSTAIN_PASSES[
            sustain_pass_index
        ]
    )


    start_byte = ms_to_mono_bytes(
        start_ms
    )


    sustain_gain = gain

    try:

        audio_file.seek(
            start_byte
        )

    except:

        return False


    audio_position_bytes = (
        start_byte
    )

    sustain_active = True

    return True


def service_audio():

    global audio_file
    global audio_active


    if not audio_active:

        return


    # ========================================================
    # PROVEN CLEAN GUITAR STREAM
    # ========================================================
    #
    # IMPORTANT:
    # Do NOT process chord samples in Python here.
    #
    # Read the original signed 16-bit mono RAW bytes and copy
    # each sample directly to Left + Right.
    #
    # This is the same architecture that previously gave the
    # clean AirFret guitar sound.
    # ========================================================

    data = audio_file.read(
        MONO_CHUNK_BYTES
    )


    if not data:

        stop_stream()

        update_oled()

        return


    length = len(
        data
    )


    if length & 1:

        length -= 1


    out = 0


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
# SERVICE PERFORMANCE EFFECT AUDIO
# ============================================================
#
# Direct mono RAW -> volume -> stereo streaming.
# No guitar sustain-tail reuse is applied to effects.
# ============================================================

def service_effect_audio():

    global audio_file
    global audio_active


    if not audio_active:

        return


    # ========================================================
    # CLEAN DIRECT EFFECT STREAM
    # ========================================================
    #
    # WAH / PLUCK / WHIP are already pre-rendered RAW files.
    # Do NOT run sample-by-sample DSP on the Pico.
    #
    # Just copy each mono 16-bit sample directly to L + R,
    # exactly like the protected clean chord stream.
    # ========================================================

    data = audio_file.read(
        MONO_CHUNK_BYTES
    )


    if not data:

        stop_stream()

        update_oled()

        return


    length = len(
        data
    )


    if length & 1:

        length -= 1


    out = 0


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
# PITCHED WAH NOTE PLAYBACK
# ============================================================
#
# Each key has its own pre-rendered pitched WAH file:
#
# 1 C4, 2 D4, 3 E4, 4 F4,
# 5 G4, 6 A4, 7 B4, 8 C5
#
# No real-time pitch shifting or filter DSP happens on the Pico.
# The file is streamed directly, preserving reliability.
# ============================================================

def start_sampled_note_effect(
    key,
    effect
):

    global audio_file
    global audio_active
    global current_audio_filename
    global audio_position_bytes
    global sustain_active
    global sustain_pass_index
    global sustain_gain


    stop_stream()


    if effect == "WAH":

        filename = (
            WAH_NOTE_FILES[
                key
            ]
        )

    elif effect == "LASER":

        filename = (
            LASER_NOTE_FILES[
                key
            ]
        )

    else:

        return


    try:

        audio_file = open(
            filename,
            "rb"
        )

    except OSError:

        print(
            "MISSING NOTE FX:",
            filename
        )

        audio_file = None

        audio_active = False

        return


    current_audio_filename = filename

    audio_position_bytes = 0

    sustain_active = False

    sustain_pass_index = 0

    sustain_gain = 256

    audio_active = True


    print(
        effect + " NOTE:",
        NOTE_KEYS[key][0]
    )


    update_oled(
        playing=True
    )


def service_sampled_note_effect_audio():

    global audio_file
    global audio_active
    global current_note_key


    if not audio_active:

        return


    data = audio_file.read(
        MONO_CHUNK_BYTES
    )


    if not data:

        stop_stream()

        current_note_key = None

        update_oled()

        return


    length = len(
        data
    )


    if length & 1:

        length -= 1


    out = 0


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

    length = len(
        buffer
    )


    # Scale every signed 16-bit stereo sample
    # using the same slider volume as Chord Mode.
    for i in range(
        0,
        length,
        2
    ):

        sample = (
            buffer[i]
            | (
                buffer[i + 1]
                << 8
            )
        )


        if sample >= 32768:

            sample -= 65536


        sample = (
            sample
            * volume_gain
        ) >> 8


        note_output_buffer[
            i
        ] = (
            sample & 0xFF
        )

        note_output_buffer[
            i + 1
        ] = (
            (sample >> 8)
            & 0xFF
        )


    audio.write(
        note_output_view[
            :length
        ]
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


    update_oled()


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

    send_to_website(
        "SCALE",
        selected_scale
    )

    send_to_website(
        "CHORD",
        current_chord()
    )


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

    send_to_website(
        "CHORD",
        current_chord()
    )


    update_oled()


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

    send_to_website(
        "CHORD",
        current_chord()
    )


    update_oled()


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


        update_oled()


def set_up():

    global strum_direction


    if strum_direction != "UP":

        strum_direction = "UP"


        print(
            "STRUM: UP"
        )


        update_oled()


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

    send_to_website(
        "KEY",
        key
    )


    # --------------------------------------------------------
    # NOTE MODE
    # --------------------------------------------------------

    if key == "*":

        stop_stream()


        mode = "NOTE"

        send_to_website(
            "MODE",
            mode
        )


        current_note_key = None


        print(
            "MODE: NOTE"
        )


        update_oled()


        return


    # --------------------------------------------------------
    # CHORD MODE
    # --------------------------------------------------------

    if key == "#":

        current_note_key = None


        mode = "CHORD"

        send_to_website(
            "MODE",
            mode
        )


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

        send_to_website(
            "STOP"
        )


        print(
            "STOP"
        )


        update_oled()


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

            send_to_website(
                "NOTE_ON",
                NOTE_KEYS[key][0],
                current_note_effect()
            )


            print(
                "NOTE:",
                NOTE_KEYS[
                    key
                ][0]
            )


            if (
                current_note_effect() == "WAH"
                or current_note_effect() == "LASER"
            ):

                start_sampled_note_effect(
                    key,
                    current_note_effect()
                )

            else:

                update_oled()


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


            toggle_gyro_reverse()


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
    # NOTE MODE CONTROLS
    # --------------------------------------------------------
    # LEFT / RIGHT cycles the 3 note effects.
    # --------------------------------------------------------

    if mode == "NOTE":

        if (
            abs(dx) >= abs(dy)
            and abs(dx) > MOVE_DISTANCE
            and x_ready
        ):

            send_to_website(
                "NAV",
                "RIGHT" if dx > 0 else "LEFT"
            )

            if dx > 0:

                next_note_effect()

            else:

                previous_note_effect()

            x_ready = False


    # --------------------------------------------------------
    # CHORD MODE CONTROLS
    # --------------------------------------------------------

    elif mode == "CHORD":


        # ====================================================
        # LEFT / RIGHT = CHORD
        # ====================================================

        if (
            abs(dx) >= abs(dy)
            and abs(dx) > MOVE_DISTANCE
            and x_ready
        ):

            send_to_website(
                "NAV",
                "RIGHT" if dx > 0 else "LEFT"
            )


            if dx > 0:

                next_chord()


            else:

                previous_chord()


            x_ready = False


        # ====================================================
        # JOYSTICK VERTICAL MOVEMENT
        # ====================================================
        # No strumming here anymore.
        # Right-hand MPU6050 motion controls UP/DOWN strums.
        # ====================================================


    # --------------------------------------------------------
    # PERFORMANCE FX MODE CONTROLS
    # --------------------------------------------------------

    elif mode == "FX":


        if (
            abs(dx) >= abs(dy)
            and abs(dx) > MOVE_DISTANCE
            and x_ready
        ):

            send_to_website(
                "NAV",
                "RIGHT" if dx > 0 else "LEFT"
            )


            if dx > 0:

                next_effect()


            else:

                previous_effect()


            x_ready = False


    # --------------------------------------------------------
    # JOYSTICK BUTTON
    # --------------------------------------------------------
    # No longer required for chord playback.
    # Up/down movement performs the strum directly.
    # --------------------------------------------------------

    switch = (
        joystick_switch.value()
    )


    # Button press:
    # CHORD mode -> open Performance FX mode.
    # FX mode    -> play selected effect.
    if (
        previous_switch == 1
        and switch == 0
        and time.ticks_diff(
            time.ticks_ms(),
            last_strum_time
        ) > 120
    ):

        send_to_website(
            "NAV",
            "PRESS"
        )


        if mode == "CHORD":

            enter_effect_mode()


        elif mode == "FX":

            start_effect()


    previous_switch = (
        switch
    )


# ============================================================
# INITIALIZE
# ============================================================

build_notes()

initialize_gyro()


print()
print("================================")
print(" AIRFRET - SIMPLE FIXED-X STRUM")
print("================================")
print()

print("GUITAR BANK: READY")
print("CHORD AUDIO: CLEAN DIRECT STREAM")
print("FX AUDIO: CLEAN DIRECT STREAM")
print()

print("* = NOTE MODE")
print("# = CHORD MODE")
print("0 = STOP")
print()

print("NOTE MODE:")
print("1-8 = PLAY NOTES")
print("JOYSTICK LEFT / RIGHT = CHANGE NOTE FX")
print("NOTE FX: CLEAN / OCTAVE / SYNTH / WAH / LASER")
print()

print("CHORD MODE:")
print("1 = C MAJOR SCALE")
print("2 = G MAJOR SCALE")
print("3 = A MINOR SCALE")
print("4 = D MINOR SCALE")
print("5 = COUNTRY ROADS: G -> Em -> D -> C -> G")
print("6 = NEVER NEVER - VERSE A")
print("    G -> C -> D -> G -> C -> D -> G")
print("7 = NEVER NEVER - VERSE B / BRIDGE")
print("    C -> G -> D -> G -> C -> D -> G")
print("8 = STAND BY ME")
print("    G -> Em -> C -> D -> repeat")
print()

print("JOYSTICK:")
print("CHORD: LEFT / RIGHT = CHANGE CHORD")
print("CHORD: PRESS = EFFECT MODE")
print("FX: LEFT / RIGHT = WAH / PLUCK / WHIP")
print("FX: PRESS = PLAY EFFECT")
print("# = RETURN TO CHORD MODE")
print()

print("9 = EMERGENCY REVERSE GYRO DIRECTION")
print()

print("VOLUME SLIDER: GP26 / ADC0")
print()

print("AIRFRET READY")
send_to_website(
    "READY",
    mode
)
print()


update_oled()


# ============================================================
# MAIN PERFORMANCE LOOP
# ============================================================

while True:


    # ========================================================
    # RIGHT-HAND GYRO STRUM
    # ========================================================
    # Service this first so wrist motion starts audio as quickly
    # as possible.
    # ========================================================

    service_gyro_strum()


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

            and current_note_effect()
            != "WAH"

            and current_note_effect()
            != "LASER"
        ):


            print(
                "NOTE OFF:",
                NOTE_KEYS[
                    key
                ][0]
            )

            send_to_website(
                "NOTE_OFF",
                NOTE_KEYS[key][0]
            )


            current_note_key = None


            update_oled()


    previous_keys = (
        current_keys
    )


    # ========================================================
    # VOLUME SLIDER
    # ========================================================

    service_volume()


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
    # PERFORMANCE EFFECT AUDIO
    # ========================================================

    elif (
        mode == "FX"
        and audio_active
    ):

        service_effect_audio()


    # ========================================================
    # NOTE MODE
    # ========================================================

    elif (
        mode == "NOTE"
        and (
            current_note_effect() == "WAH"
            or current_note_effect() == "LASER"
        )
        and audio_active
    ):

        service_sampled_note_effect_audio()


    elif (
        mode == "NOTE"
        and current_note_key
        is not None
    ):

        play_note_piece(

            note_buffers[
                current_note_effect()
            ][
                current_note_key
            ]
        )


    else:

        time.sleep_ms(
            1
        )

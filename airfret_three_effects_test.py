from machine import Pin, ADC, I2S
import time
import math
import struct

# ============================================================
# AIRFRET - 3 EFFECTS STANDALONE TEST
# ============================================================
#
# Hardware used:
#   Pico 2
#   MAX98357A + speaker
#   Joystick
#
# NO keypad required.
# NO OLED required.
# NO gyro required for this isolated effects test.
#
# Controls:
#   Joystick LEFT  = previous effect
#   Joystick RIGHT = next effect
#   Joystick PRESS = play test G-major chord
#
# Effects:
#   1. TREMOLO  - pulsing volume
#   2. FUZZ     - clipped/distorted guitar tone
#   3. OCTAVE   - adds a higher octave layer
#
# Speaker / MAX98357A:
#   GP10 -> BCLK
#   GP11 -> LRC / WS
#   GP12 -> DIN
#
# Joystick:
#   SW  -> GP18
#   VRx -> GP27
#   VRy -> GP28 (not used here)
#   VCC -> 3V3
#   GND -> GND
# ============================================================


# ============================================================
# AUDIO
# ============================================================

SAMPLE_RATE = 22050

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
# JOYSTICK
# ============================================================

joystick_x = ADC(27)
joystick_y = ADC(28)

joystick_switch = Pin(
    18,
    Pin.IN,
    Pin.PULL_UP
)

CENTER_X = 31815

MOVE_DISTANCE = 6500
RESET_DISTANCE = 3200

x_ready = True

previous_switch = 1
last_press_time = 0


# ============================================================
# EFFECT SELECTION
# ============================================================

EFFECTS = [
    "TREMOLO",
    "FUZZ",
    "OCTAVE"
]

effect_index = 0


def current_effect():

    return EFFECTS[
        effect_index
    ]


def show_effect():

    print()
    print("====================")
    print("FX:", current_effect())
    print("====================")

    if current_effect() == "TREMOLO":

        print("Pulsing volume effect")

    elif current_effect() == "FUZZ":

        print("Clipped / distorted tone")

    elif current_effect() == "OCTAVE":

        print("Adds a higher octave layer")

    print("PRESS joystick to hear it")


def previous_effect():

    global effect_index

    effect_index = (
        effect_index - 1
    ) % len(EFFECTS)

    show_effect()


def next_effect():

    global effect_index

    effect_index = (
        effect_index + 1
    ) % len(EFFECTS)

    show_effect()


# ============================================================
# SYNTHESIZED G-MAJOR TEST CHORD
# ============================================================
#
# G3  = 196.00 Hz
# B3  = 246.94 Hz
# D4  = 293.66 Hz
#
# We generate the sound in chunks so the Pico does not need
# several huge precomputed effect buffers.
# ============================================================

BASE_FREQS = (
    196.00,
    246.94,
    293.66
)

PLAY_SECONDS = 1.60

CHUNK_FRAMES = 96

MAX_AMP = 7800


def envelope(t):

    if t < 0.018:

        return (
            t / 0.018
        )

    return math.exp(
        -1.75 * (
            t - 0.018
        )
    )


def base_chord_sample(t):

    value = 0.0

    offsets = (
        0.000,
        0.018,
        0.036
    )

    for i in range(3):

        local_t = (
            t - offsets[i]
        )

        if local_t < 0:

            continue

        freq = BASE_FREQS[i]

        value += math.sin(
            2.0 * math.pi
            * freq
            * local_t
        )

        value += 0.28 * math.sin(
            2.0 * math.pi
            * freq * 2.0
            * local_t
        )

    return value / 3.84


def octave_layer(t):

    value = 0.0

    for freq in BASE_FREQS:

        value += math.sin(
            2.0 * math.pi
            * freq * 2.0
            * t
        )

    return value / 3.0


def apply_effect(effect, raw_value, t):

    if effect == "TREMOLO":

        tremolo = (
            0.58
            + 0.42 * (
                0.5
                + 0.5 * math.sin(
                    2.0 * math.pi
                    * 6.5
                    * t
                )
            )
        )

        return (
            raw_value * tremolo
        )

    elif effect == "FUZZ":

        driven = (
            raw_value * 2.8
        )

        if driven > 0.42:

            driven = 0.42

        elif driven < -0.42:

            driven = -0.42

        return (
            driven * 1.75
        )

    elif effect == "OCTAVE":

        high = octave_layer(
            t
        )

        return (
            raw_value * 0.72
            + high * 0.28
        )

    return raw_value


def play_effect():

    effect = current_effect()

    print(
        "PLAY:",
        effect
    )

    total_frames = int(
        SAMPLE_RATE
        * PLAY_SECONDS
    )

    frame_index = 0

    while frame_index < total_frames:

        frames_this_chunk = min(
            CHUNK_FRAMES,
            total_frames - frame_index
        )

        stereo = bytearray(
            frames_this_chunk * 4
        )

        out_index = 0

        for i in range(
            frames_this_chunk
        ):

            n = (
                frame_index + i
            )

            t = (
                n / SAMPLE_RATE
            )

            raw = base_chord_sample(
                t
            )

            effected = apply_effect(
                effect,
                raw,
                t
            )

            amp = envelope(
                t
            )

            sample = int(
                effected
                * amp
                * MAX_AMP
            )

            if sample > 32767:

                sample = 32767

            elif sample < -32768:

                sample = -32768

            struct.pack_into(
                "<hh",
                stereo,
                out_index,
                sample,
                sample
            )

            out_index += 4

        audio.write(
            stereo
        )

        frame_index += (
            frames_this_chunk
        )


# ============================================================
# JOYSTICK SERVICE
# ============================================================

def service_joystick():

    global x_ready
    global previous_switch
    global last_press_time

    x = joystick_x.read_u16()

    dx = (
        x - CENTER_X
    )

    if abs(dx) < RESET_DISTANCE:

        x_ready = True

    if (
        abs(dx) > MOVE_DISTANCE
        and x_ready
    ):

        if dx > 0:

            next_effect()

        else:

            previous_effect()

        x_ready = False

    switch = (
        joystick_switch.value()
    )

    now = (
        time.ticks_ms()
    )

    if (
        previous_switch == 1
        and switch == 0
        and time.ticks_diff(
            now,
            last_press_time
        ) > 180
    ):

        play_effect()

        last_press_time = now

    previous_switch = switch


# ============================================================
# STARTUP
# ============================================================

print()
print("================================")
print(" AIRFRET - 3 EFFECTS TEST")
print("================================")
print()
print("LEFT  = previous effect")
print("RIGHT = next effect")
print("PRESS = play effect")
print()

show_effect()


while True:

    service_joystick()

    time.sleep_ms(
        8
    )

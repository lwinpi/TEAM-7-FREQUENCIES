from machine import Pin, I2S
import math
import struct
import time

# ============================================
# MAX98357A I2S SETUP
# ============================================

audio = I2S(
    0,
    sck=Pin(10),       # BCLK
    ws=Pin(11),        # LRC
    sd=Pin(12),        # DIN
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=22050,
    ibuf=20000
)

SAMPLE_RATE = 22050


def make_tone(frequency, duration_ms, volume=0.25):

    number_of_samples = int(
        SAMPLE_RATE * duration_ms / 1000
    )

    # Stereo = 4 bytes per sample
    buffer = bytearray(
        number_of_samples * 4
    )

    for i in range(number_of_samples):

        sample = int(
            32767
            * volume
            * math.sin(
                2
                * math.pi
                * frequency
                * i
                / SAMPLE_RATE
            )
        )

        # Same audio on left and right
        struct.pack_into(
            "<hh",
            buffer,
            i * 4,
            sample,
            sample
        )

    return buffer


print("Speaker test starting")

# A4 = 440 Hz
tone = make_tone(
    440,
    1000,
    0.20
)

audio.write(tone)

time.sleep_ms(500)

audio.deinit()

print("Speaker test finished")
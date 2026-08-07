from machine import Pin, I2S
import math
import struct
import time


# ==========================================
# MAX98357A CLEAN AUDIO TEST
# ==========================================

SAMPLE_RATE = 44100
FREQUENCY = 440.0

# VERY LOW LEVEL ON PURPOSE
AMPLITUDE = 2500

audio = I2S(
    0,
    sck=Pin(10),       # BCLK
    ws=Pin(11),        # LRC
    sd=Pin(12),        # DIN
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=SAMPLE_RATE,
    ibuf=40000
)


# ==========================================
# PRE-COMPUTE AUDIO
# ==========================================

# 0.25 seconds
# At 440 Hz this contains exactly 110 cycles,
# so repeating it has no seam/click.

NUM_SAMPLES = 11025

buffer = bytearray(
    NUM_SAMPLES * 4
)


for i in range(NUM_SAMPLES):

    sample = int(
        AMPLITUDE
        * math.sin(
            2
            * math.pi
            * FREQUENCY
            * i
            / SAMPLE_RATE
        )
    )

    struct.pack_into(
        "<hh",
        buffer,
        i * 4,
        sample,
        sample
    )


print("Playing CLEAN 440 Hz test...")


# Repeat 0.25-second buffer
# 8 times = 2 seconds

for i in range(8):
    audio.write(buffer)


# Send silence afterward
silence = bytearray(4096)

audio.write(silence)

time.sleep_ms(200)

audio.deinit()

print("Finished")
from machine import Pin, I2S
import os
import time

SAMPLE_RATE = 22050
FILE = "/real_guitar_trial/C_MAJOR_D1.raw"

print("=== AIRFRET REAL SAMPLE DIRECT TEST ===")

try:
    size = os.stat(FILE)[6]
    print("Found:", FILE)
    print("File size:", size, "bytes")
except OSError as e:
    print("FILE ERROR:", e)
    raise

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

MONO_BYTES = 256
mono = bytearray(MONO_BYTES)
stereo = bytearray(MONO_BYTES * 2)
stereo_view = memoryview(stereo)

print("Playing C Major in 1 second...")
time.sleep_ms(1000)

with open(FILE, "rb") as f:
    total = 0

    while True:
        count = f.readinto(mono)

        if not count:
            break

        if count & 1:
            count -= 1

        out = 0

        for i in range(0, count, 2):
            lo = mono[i]
            hi = mono[i + 1]

            stereo[out] = lo
            stereo[out + 1] = hi
            stereo[out + 2] = lo
            stereo[out + 3] = hi
            out += 4

        audio.write(stereo_view[:out])
        total += count

print("Finished. Mono bytes played:", total)
time.sleep_ms(200)
audio.deinit()
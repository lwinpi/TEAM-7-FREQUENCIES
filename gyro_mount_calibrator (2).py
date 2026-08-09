from machine import Pin, I2C
import time

# ============================================================
# AIRFRET - GYRO MOUNT / ORIENTATION CALIBRATOR
# ============================================================
# MPU6050 / GY-521 wiring:
# VCC -> 3V3
# GND -> GND
# SDA -> GP20
# SCL -> GP21
#
# This script prints ONE summary for each deliberate wrist motion:
#
# GESTURE 1
#   X peak:  42 dps
#   Y peak: 238 dps
#   Z peak:  55 dps
#   BEST AXIS: Y
#   SIGN: +
#
# The best mounting orientation is the one where:
# - the SAME axis wins for almost every down/up strum
# - that axis is much larger than the other two
# - down and up have opposite signs
# ============================================================

i2c = I2C(
    0,
    sda=Pin(20),
    scl=Pin(21),
    freq=50000
)

devices = i2c.scan()
print("I2C devices:", [hex(x) for x in devices])

if 0x68 in devices:
    MPU = 0x68
elif 0x69 in devices:
    MPU = 0x69
else:
    raise RuntimeError("MPU6050 not found at 0x68 or 0x69")

PWR_MGMT_1 = 0x6B
GYRO_CONFIG = 0x1B
GYRO_XOUT_H = 0x43

# Wake sensor.
i2c.writeto_mem(MPU, PWR_MGMT_1, b"\x00")
time.sleep_ms(100)

# +/-500 dps gyro range -> about 65.5 counts per degree/sec.
i2c.writeto_mem(MPU, GYRO_CONFIG, b"\x08")
time.sleep_ms(50)

buf = bytearray(6)

def s16(hi, lo):
    value = (hi << 8) | lo
    if value & 0x8000:
        value -= 65536
    return value

def read_raw():
    i2c.readfrom_mem_into(
        MPU,
        GYRO_XOUT_H,
        buf
    )
    return (
        s16(buf[0], buf[1]),
        s16(buf[2], buf[3]),
        s16(buf[4], buf[5])
    )

# ------------------------------------------------------------
# Bias calibration
# ------------------------------------------------------------
print()
print("Hold the gyro completely still for 1 second...")

sx = sy = sz = 0
count = 120

for _ in range(count):
    gx, gy, gz = read_raw()
    sx += gx
    sy += gy
    sz += gz
    time.sleep_ms(5)

bx = sx // count
by = sy // count
bz = sz // count

print("Calibration complete.")
print()
print("Now perform ONE deliberate DOWN or UP strum at a time.")
print("Return your hand to rest between movements.")
print("Try 5 DOWN strums, then 5 UP strums.")
print()

START_DPS = 75
STOP_DPS = 30
STOP_TIME_MS = 120

gesture_active = False
still_start = None
gesture_num = 0

peak_abs_x = 0
peak_abs_y = 0
peak_abs_z = 0

peak_signed_x = 0
peak_signed_y = 0
peak_signed_z = 0

while True:
    gx, gy, gz = read_raw()

    x = (gx - bx) / 65.5
    y = (gy - by) / 65.5
    z = (gz - bz) / 65.5

    magnitude = max(abs(x), abs(y), abs(z))

    # Start a gesture.
    if not gesture_active and magnitude >= START_DPS:
        gesture_active = True
        still_start = None

        peak_abs_x = 0
        peak_abs_y = 0
        peak_abs_z = 0

        peak_signed_x = 0
        peak_signed_y = 0
        peak_signed_z = 0

    if gesture_active:
        if abs(x) > peak_abs_x:
            peak_abs_x = abs(x)
            peak_signed_x = x

        if abs(y) > peak_abs_y:
            peak_abs_y = abs(y)
            peak_signed_y = y

        if abs(z) > peak_abs_z:
            peak_abs_z = abs(z)
            peak_signed_z = z

        # Wait until hand is calm again.
        if magnitude <= STOP_DPS:
            if still_start is None:
                still_start = time.ticks_ms()

            elif time.ticks_diff(
                time.ticks_ms(),
                still_start
            ) >= STOP_TIME_MS:

                gesture_num += 1

                peaks = [
                    ("X", peak_abs_x, peak_signed_x),
                    ("Y", peak_abs_y, peak_signed_y),
                    ("Z", peak_abs_z, peak_signed_z),
                ]

                best = peaks[0]
                if peaks[1][1] > best[1]:
                    best = peaks[1]
                if peaks[2][1] > best[1]:
                    best = peaks[2]

                others = [
                    p[1]
                    for p in peaks
                    if p[0] != best[0]
                ]

                second = max(others)
                ratio = (
                    best[1] / second
                    if second > 0
                    else 99
                )

                sign = "+" if best[2] >= 0 else "-"

                print("GESTURE", gesture_num)
                print("  X peak:", round(peak_signed_x), "dps")
                print("  Y peak:", round(peak_signed_y), "dps")
                print("  Z peak:", round(peak_signed_z), "dps")
                print("  BEST AXIS:", best[0])
                print("  SIGN:", sign)
                print("  DOMINANCE:", round(ratio, 2), "x")

                if ratio >= 1.8:
                    print("  MOUNT QUALITY: EXCELLENT")
                elif ratio >= 1.4:
                    print("  MOUNT QUALITY: GOOD")
                elif ratio >= 1.2:
                    print("  MOUNT QUALITY: OK")
                else:
                    print("  MOUNT QUALITY: ROTATE / REPOSITION SENSOR")

                print()

                gesture_active = False
                still_start = None

        else:
            still_start = None

    time.sleep_ms(8)

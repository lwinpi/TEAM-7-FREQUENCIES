from machine import Pin, I2C
import time
import math

# ============================================================
# AIRFRET STRUM DETECTOR V4 - GYRO + ACCEL FUSION
#
# Designed for an MPU6050 mounted rigidly on the right hand.
#
# Why this version is different:
#   - GYROSCOPE decides UP vs DOWN direction.
#   - ACCELEROMETER only confirms that a real hand stroke happened.
#   - Slow repositioning is ignored.
#   - Braking/rebound from one stroke cannot create a second strum.
#   - Automatically finds the strongest gyro axis.
#
# IMPORTANT:
# Keep the sensor rigidly attached to the hand/glove. Do not let the
# board rotate loosely between your fingers during calibration/play.
# ============================================================

# ---------------- I2C / MPU6050 ----------------
I2C_ID = 0
SDA_PIN = 20
SCL_PIN = 21
I2C_FREQ = 100000

SMPLRT_DIV   = 0x19
CONFIG       = 0x1A
GYRO_CONFIG  = 0x1B
ACCEL_CONFIG = 0x1C
ACCEL_XOUT_H = 0x3B
PWR_MGMT_1   = 0x6B

# +/-4 g accel => 8192 LSB/g
ACCEL_SCALE = 8192.0

# +/-1000 deg/s gyro => 32.8 LSB/(deg/s)
GYRO_SCALE = 32.8

# ---------------- live detector tuning ----------------
SAMPLE_MS = 8                 # ~125 Hz
FILTER_ALPHA = 0.55

MIN_TRIGGER_DPS = 80.0
MAX_TRIGGER_DPS = 190.0

# Accel is only a confirmation signal.
ACCEL_CONFIRM_G = 0.045

# If gyro is very strong, allow the strum even if accel confirmation
# happens to be small.
STRONG_GYRO_MULTIPLIER = 1.35

# Require a couple of consistent samples instead of one spike.
CONFIRM_SAMPLES = 2

# Prevent the stopping/rebound portion of a stroke from becoming
# another strum.
LOCKOUT_MS = 115

# After lockout, angular speed must settle before another stroke.
NEUTRAL_DPS = 35.0
NEUTRAL_TIME_MS = 32


i2c = I2C(
    I2C_ID,
    sda=Pin(SDA_PIN),
    scl=Pin(SCL_PIN),
    freq=I2C_FREQ
)

devices = i2c.scan()
print("I2C:", [hex(x) for x in devices])

if 0x68 in devices:
    MPU = 0x68
elif 0x69 in devices:
    MPU = 0x69
else:
    print("ERROR: MPU6050 not found at 0x68/0x69")
    raise SystemExit

# Wake sensor.
i2c.writeto_mem(MPU, PWR_MGMT_1, b"\x00")
time.sleep_ms(100)

# DLPF around ~44 Hz, useful for hand motion.
i2c.writeto_mem(MPU, CONFIG, b"\x03")

# 1 kHz internal rate / (1 + 7) = 125 Hz.
i2c.writeto_mem(MPU, SMPLRT_DIV, b"\x07")

# Gyro +/-1000 dps.
i2c.writeto_mem(MPU, GYRO_CONFIG, b"\x10")

# Accel +/-4 g.
i2c.writeto_mem(MPU, ACCEL_CONFIG, b"\x08")

time.sleep_ms(50)


def s16(hi, lo):
    v = (hi << 8) | lo
    if v & 0x8000:
        v -= 65536
    return v


def read_imu():
    # 14 bytes:
    # accel XYZ, temp, gyro XYZ
    d = i2c.readfrom_mem(MPU, ACCEL_XOUT_H, 14)

    ax = s16(d[0], d[1]) / ACCEL_SCALE
    ay = s16(d[2], d[3]) / ACCEL_SCALE
    az = s16(d[4], d[5]) / ACCEL_SCALE

    gx = s16(d[8], d[9]) / GYRO_SCALE
    gy = s16(d[10], d[11]) / GYRO_SCALE
    gz = s16(d[12], d[13]) / GYRO_SCALE

    return ax, ay, az, gx, gy, gz


# ============================================================
# STEP 1 - STILL CALIBRATION
# ============================================================

print()
print("STEP 1")
print("Hold the sensor STILL in the exact playing position.")
print("Keep it rigid - do not roll it between your fingers.")
time.sleep_ms(1500)

n = 180
sgx = sgy = sgz = 0.0
sgrav = 0.0

for _ in range(n):
    ax, ay, az, gx, gy, gz = read_imu()

    sgx += gx
    sgy += gy
    sgz += gz

    sgrav += math.sqrt(ax*ax + ay*ay + az*az)

    time.sleep_ms(SAMPLE_MS)

gyro_bias = [
    sgx / n,
    sgy / n,
    sgz / n
]

gravity_mag = sgrav / n

print(
    "Gyro bias: X %.1f | Y %.1f | Z %.1f dps"
    % tuple(gyro_bias)
)
print("Rest accel magnitude: %.3f g" % gravity_mag)


# ============================================================
# STEP 2 - AUTO-FIND THE ROTATION AXIS
# ============================================================

print()
print("STEP 2")
print("In 2 seconds, make normal guitar-pick UP/DOWN strokes")
print("for 3 seconds. Use your WRIST like you will during the song.")
time.sleep_ms(2000)

energy = [0.0, 0.0, 0.0]
peak = [0.0, 0.0, 0.0]

end = time.ticks_add(time.ticks_ms(), 3000)

while time.ticks_diff(end, time.ticks_ms()) > 0:
    ax, ay, az, gx, gy, gz = read_imu()

    g = [
        gx - gyro_bias[0],
        gy - gyro_bias[1],
        gz - gyro_bias[2]
    ]

    for i in range(3):
        a = abs(g[i])
        energy[i] += a
        if a > peak[i]:
            peak[i] = a

    time.sleep_ms(SAMPLE_MS)

axis = max(range(3), key=lambda i: energy[i])
axis_name = ("X", "Y", "Z")[axis]

ordered = sorted(energy, reverse=True)
dominance = ordered[0] / max(ordered[1], 1.0)

print()
print(
    "Gyro motion energy: X %.0f | Y %.0f | Z %.0f"
    % tuple(energy)
)
print(
    "Gyro peak:          X %.0f | Y %.0f | Z %.0f dps"
    % tuple(peak)
)
print("STRUM ROTATION AXIS =", axis_name)
print("Axis dominance = %.2f x" % dominance)

if dominance < 1.20:
    print("WARNING:")
    print("The motion is spread across several axes.")
    print("Mount/hold the board more rigidly for better reliability.")


# ============================================================
# STEP 3 - LEARN WHICH SIGN IS PHYSICAL DOWN
# ============================================================

print()
print("STEP 3")
print("When GO appears, make ONE normal DOWN strum.")
print("Use a quick pick-like wrist stroke, then stop.")
time.sleep_ms(1500)
print("GO - DOWN NOW!")

CAL_START_DPS = 55.0
first_sign = 0
stroke_peak = 0.0
found_at = None

end = time.ticks_add(time.ticks_ms(), 1500)

while time.ticks_diff(end, time.ticks_ms()) > 0:
    ax, ay, az, gx, gy, gz = read_imu()

    g = (
        gx - gyro_bias[0],
        gy - gyro_bias[1],
        gz - gyro_bias[2]
    )

    value = g[axis]

    if first_sign == 0 and abs(value) >= CAL_START_DPS:
        first_sign = 1 if value > 0 else -1
        stroke_peak = abs(value)
        found_at = time.ticks_ms()

    if first_sign != 0:
        sign_now = 1 if value > 0 else -1

        if sign_now == first_sign and abs(value) > stroke_peak:
            stroke_peak = abs(value)

        # Only inspect the start of the stroke.
        if time.ticks_diff(time.ticks_ms(), found_at) >= 100:
            break

    time.sleep_ms(SAMPLE_MS)

if first_sign == 0:
    print("Calibration failed: no clear wrist rotation detected.")
    print("Try mounting the sensor more rigidly and use a wrist stroke.")
    raise SystemExit

down_sign = first_sign

trigger_dps = stroke_peak * 0.45
if trigger_dps < MIN_TRIGGER_DPS:
    trigger_dps = MIN_TRIGGER_DPS
if trigger_dps > MAX_TRIGGER_DPS:
    trigger_dps = MAX_TRIGGER_DPS

print()
print("DOWN sign:", "+" if down_sign > 0 else "-")
print("Calibration peak: %.1f dps" % stroke_peak)
print("Live trigger: %.1f dps" % trigger_dps)


# ============================================================
# LIVE DETECTOR
# ============================================================

print()
print("========================================")
print("     AIRFRET FUSION STRUM V4 READY")
print("========================================")
print("Primary direction sensor: GYROSCOPE")
print("Confirmation sensor:      ACCELEROMETER")
print("Axis:", axis_name)
print()
print("Quick DOWN wrist stroke -> STRUM DOWN")
print("Quick UP wrist stroke   -> STRUM UP")
print("Slow repositioning      -> ignored")
print()

filtered = 0.0

state = "READY"
lock_started = 0
neutral_started = None

candidate_sign = 0
candidate_count = 0
candidate_peak = 0.0
candidate_accel = 0.0

while True:
    ax, ay, az, gx, gy, gz = read_imu()

    gyro_values = (
        gx - gyro_bias[0],
        gy - gyro_bias[1],
        gz - gyro_bias[2]
    )

    raw = gyro_values[axis]
    filtered += FILTER_ALPHA * (raw - filtered)

    accel_mag = math.sqrt(ax*ax + ay*ay + az*az)
    dynamic_accel = abs(accel_mag - gravity_mag)

    now = time.ticks_ms()

    if state == "READY":

        if abs(filtered) >= trigger_dps:
            sign_now = 1 if filtered > 0 else -1

            if candidate_sign == sign_now:
                candidate_count += 1
            else:
                candidate_sign = sign_now
                candidate_count = 1
                candidate_peak = 0.0
                candidate_accel = 0.0

            if abs(filtered) > candidate_peak:
                candidate_peak = abs(filtered)

            if dynamic_accel > candidate_accel:
                candidate_accel = dynamic_accel

            if candidate_count >= CONFIRM_SAMPLES:
                accel_ok = candidate_accel >= ACCEL_CONFIRM_G
                gyro_very_strong = candidate_peak >= (
                    trigger_dps * STRONG_GYRO_MULTIPLIER
                )

                if accel_ok or gyro_very_strong:

                    if candidate_sign == down_sign:
                        print(
                            "STRUM DOWN | gyro %4.0f dps | accel %.2f g"
                            % (candidate_peak, candidate_accel)
                        )
                    else:
                        print(
                            "STRUM UP   | gyro %4.0f dps | accel %.2f g"
                            % (candidate_peak, candidate_accel)
                        )

                    state = "LOCKED"
                    lock_started = now
                    neutral_started = None

                candidate_sign = 0
                candidate_count = 0
                candidate_peak = 0.0
                candidate_accel = 0.0

        else:
            candidate_sign = 0
            candidate_count = 0
            candidate_peak = 0.0
            candidate_accel = 0.0

    elif state == "LOCKED":

        # Ignore the rest of the physical stroke, including rebound/braking.
        if time.ticks_diff(now, lock_started) >= LOCKOUT_MS:
            state = "WAIT_NEUTRAL"
            neutral_started = None

    elif state == "WAIT_NEUTRAL":

        if abs(filtered) <= NEUTRAL_DPS:

            if neutral_started is None:
                neutral_started = now

            elif time.ticks_diff(now, neutral_started) >= NEUTRAL_TIME_MS:
                state = "READY"
                neutral_started = None

        else:
            neutral_started = None

    time.sleep_ms(SAMPLE_MS)

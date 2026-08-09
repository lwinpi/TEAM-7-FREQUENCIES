from machine import Pin, I2C
import time

# ============================================================
# AIRFRET STRUM DETECTOR V3
# More reliable for holding the MPU6050 like a guitar pick.
#
# Main fixes vs V2:
# - Direction comes from the FIRST acceleration impulse of a stroke.
# - The braking impulse at the end of the same stroke is ignored.
# - Longer lockout + required neutral time before re-arming.
# - Threshold is automatically estimated from still noise + calibration.
# ============================================================

I2C_ID = 0
SDA_PIN = 20
SCL_PIN = 21
I2C_FREQ = 100000

PWR_MGMT_1 = 0x6B
ACCEL_CONFIG = 0x1C
ACCEL_XOUT_H = 0x3B

SAMPLE_MS = 8

# Safety limits for automatic threshold
MIN_TRIGGER_G = 0.32
MAX_TRIGGER_G = 0.75

# After a real stroke, completely ignore the braking/reversal impulse.
LOCKOUT_MS = 175

# Then the sensor must stay near neutral for this long before another stroke.
NEUTRAL_G = 0.15
NEUTRAL_TIME_MS = 55

# Light filter: enough to remove jitter without creating much lag.
FILTER_ALPHA = 0.48

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
    print("ERROR: MPU6050 not found")
    raise SystemExit

# Wake MPU6050 and use +/-4g accelerometer range.
i2c.writeto_mem(MPU, PWR_MGMT_1, b"\x00")
time.sleep_ms(100)
i2c.writeto_mem(MPU, ACCEL_CONFIG, b"\x08")

ACCEL_SCALE = 8192.0


def s16(hi, lo):
    v = (hi << 8) | lo
    if v & 0x8000:
        v -= 65536
    return v


def read_accel():
    d = i2c.readfrom_mem(MPU, ACCEL_XOUT_H, 6)
    return (
        s16(d[0], d[1]) / ACCEL_SCALE,
        s16(d[2], d[3]) / ACCEL_SCALE,
        s16(d[4], d[5]) / ACCEL_SCALE,
    )


def average_baseline(samples=130):
    sx = sy = sz = 0.0
    max_dev = [0.0, 0.0, 0.0]

    vals_list = []

    for _ in range(samples):
        vals = read_accel()
        vals_list.append(vals)
        sx += vals[0]
        sy += vals[1]
        sz += vals[2]
        time.sleep_ms(SAMPLE_MS)

    base = [sx / samples, sy / samples, sz / samples]

    for vals in vals_list:
        for i in range(3):
            dev = abs(vals[i] - base[i])
            if dev > max_dev[i]:
                max_dev[i] = dev

    return base, max_dev


# ============================================================
# STEP 1: STILL CALIBRATION
# ============================================================

print()
print("STEP 1")
print("Hold the sensor STILL in your normal playing position.")
print("Calibrating...")
time.sleep_ms(1200)

base, still_noise = average_baseline()

print("Baseline:")
print("X %.3f | Y %.3f | Z %.3f" % tuple(base))
print("Still noise:")
print("X %.3f | Y %.3f | Z %.3f" % tuple(still_noise))


# ============================================================
# STEP 2: FIND THE PHYSICAL STRUM AXIS
# ============================================================

print()
print("STEP 2")
print("In 2 seconds, strum UP/DOWN repeatedly for 3 seconds.")
time.sleep_ms(2000)

energy = [0.0, 0.0, 0.0]
end = time.ticks_add(time.ticks_ms(), 3000)

while time.ticks_diff(end, time.ticks_ms()) > 0:
    vals = read_accel()

    for i in range(3):
        energy[i] += abs(vals[i] - base[i])

    time.sleep_ms(SAMPLE_MS)

axis = max(range(3), key=lambda i: energy[i])
axis_name = ("X", "Y", "Z")[axis]

print("Motion energy:")
print("X %.1f | Y %.1f | Z %.1f" % tuple(energy))
print("STRUM AXIS =", axis_name)


# Re-establish baseline after the training movement.
print()
print("Hold STILL again...")
time.sleep_ms(1000)

base2, noise2 = average_baseline(100)
rest_base = base2[axis]
axis_noise = max(still_noise[axis], noise2[axis])


# ============================================================
# STEP 3: LEARN THE FIRST IMPULSE OF A DOWN STROKE
# ============================================================

# We deliberately detect the FIRST meaningful impulse rather than the
# largest impulse. The largest impulse can be the hand braking at the end.
CAL_START_G = max(0.18, axis_noise * 4.0)

print()
print("STEP 3")
print("When GO appears, make ONE normal DOWN strum.")
print("Do not reverse immediately; finish the stroke naturally.")
time.sleep_ms(1500)
print("GO - DOWN NOW!")

filt = 0.0
first_sign = 0
cal_peak = 0.0
found_at = None
end = time.ticks_add(time.ticks_ms(), 1400)

while time.ticks_diff(end, time.ticks_ms()) > 0:
    vals = read_accel()
    signal = vals[axis] - rest_base
    filt += FILTER_ALPHA * (signal - filt)

    if first_sign == 0 and abs(filt) >= CAL_START_G:
        first_sign = 1 if filt > 0 else -1
        found_at = time.ticks_ms()
        cal_peak = abs(filt)

    # Once the initial impulse has been found, inspect only the next
    # ~90 ms. This captures the stroke start, not the later braking impulse.
    if first_sign != 0:
        if abs(filt) > cal_peak and (1 if filt > 0 else -1) == first_sign:
            cal_peak = abs(filt)

        if time.ticks_diff(time.ticks_ms(), found_at) >= 90:
            break

    time.sleep_ms(SAMPLE_MS)

if first_sign == 0:
    print("Calibration failed: DOWN stroke was too small.")
    print("Restart and make a clearer stroke.")
    raise SystemExit

down_sign = first_sign

# Auto threshold:
# - comfortably above measured still noise
# - below the user's measured normal down-stroke onset
trigger_g = max(
    MIN_TRIGGER_G,
    axis_noise * 6.0,
    cal_peak * 0.55
)
trigger_g = min(trigger_g, MAX_TRIGGER_G)

reset_g = min(NEUTRAL_G, trigger_g * 0.35)

print()
print("DOWN first-impulse sign:", "+" if down_sign > 0 else "-")
print("DOWN onset peak: %.3f g" % cal_peak)
print("Trigger threshold: %.3f g" % trigger_g)
print("Neutral threshold: %.3f g" % reset_g)


# ============================================================
# LIVE DETECTOR
# ============================================================

print()
print("====================================")
print("      AIRFRET STRUM V3 READY")
print("====================================")
print("Axis:", axis_name)
print("Physical DOWN =",
      "positive" if down_sign > 0 else "negative",
      axis_name,
      "first impulse")
print()
print("DOWN motion -> STRUM DOWN")
print("UP motion   -> STRUM UP")
print()

filt = 0.0

# READY -> LOCKED -> WAIT_NEUTRAL -> READY
state = "READY"
lock_started = 0
neutral_started = None

while True:
    vals = read_accel()
    raw_axis = vals[axis]

    signal = raw_axis - rest_base
    filt += FILTER_ALPHA * (signal - filt)

    now = time.ticks_ms()

    if state == "READY":

        if abs(filt) >= trigger_g:
            impulse_sign = 1 if filt > 0 else -1

            if impulse_sign == down_sign:
                print("STRUM DOWN | onset %.2f g" % abs(filt))
            else:
                print("STRUM UP   | onset %.2f g" % abs(filt))

            lock_started = now
            neutral_started = None
            state = "LOCKED"

    elif state == "LOCKED":

        # Ignore every acceleration impulse belonging to the same physical
        # stroke, including the strong opposite braking impulse.
        if time.ticks_diff(now, lock_started) >= LOCKOUT_MS:
            state = "WAIT_NEUTRAL"
            neutral_started = None

    elif state == "WAIT_NEUTRAL":

        if abs(filt) <= reset_g:

            if neutral_started is None:
                neutral_started = now

            elif time.ticks_diff(now, neutral_started) >= NEUTRAL_TIME_MS:
                state = "READY"
                neutral_started = None

        else:
            # Any braking/bounce impulse resets the neutral timer.
            neutral_started = None

    # Slowly compensate for small resting-angle changes only while truly ready.
    if state == "READY" and abs(filt) < reset_g:
        rest_base = rest_base * 0.999 + raw_axis * 0.001

    time.sleep_ms(SAMPLE_MS)

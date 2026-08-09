from machine import Pin, I2C
import time

I2C_ID = 0
SDA_PIN = 20
SCL_PIN = 21
I2C_FREQ = 100000

PWR_MGMT_1 = 0x6B
ACCEL_CONFIG = 0x1C
ACCEL_XOUT_H = 0x3B

SAMPLE_MS = 10
FILTER_ALPHA = 0.32
TRIGGER_G = 0.40
RESET_G = 0.16
MIN_GAP_MS = 95
NEUTRAL_SAMPLES_NEEDED = 3

i2c = I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
devices = i2c.scan()
print("I2C:", [hex(x) for x in devices])

if 0x68 in devices:
    MPU = 0x68
elif 0x69 in devices:
    MPU = 0x69
else:
    print("ERROR: MPU6050 not found")
    raise SystemExit

i2c.writeto_mem(MPU, PWR_MGMT_1, b"\x00")
time.sleep_ms(100)
i2c.writeto_mem(MPU, ACCEL_CONFIG, b"\x08")
ACCEL_SCALE = 8192.0

def s16(hi, lo):
    v = (hi << 8) | lo
    if v & 0x8000:
        v -= 65536
    return v

def read_accel_g():
    d = i2c.readfrom_mem(MPU, ACCEL_XOUT_H, 6)
    return (
        s16(d[0], d[1]) / ACCEL_SCALE,
        s16(d[2], d[3]) / ACCEL_SCALE,
        s16(d[4], d[5]) / ACCEL_SCALE
    )

print("\nSTEP 1: Hold STILL in playing position.")
time.sleep_ms(2000)

sx = sy = sz = 0.0
n = 150
for _ in range(n):
    x, y, z = read_accel_g()
    sx += x; sy += y; sz += z
    time.sleep_ms(SAMPLE_MS)

base = [sx/n, sy/n, sz/n]
print("Baseline X %.3f | Y %.3f | Z %.3f" % tuple(base))

print("\nSTEP 2: In 2 sec, repeatedly strum UP and DOWN for 4 sec.")
time.sleep_ms(2000)

energy = [0.0, 0.0, 0.0]
end_time = time.ticks_add(time.ticks_ms(), 4000)

while time.ticks_diff(end_time, time.ticks_ms()) > 0:
    vals = read_accel_g()
    for i in range(3):
        energy[i] += abs(vals[i] - base[i])
    time.sleep_ms(SAMPLE_MS)

axis = max(range(3), key=lambda i: energy[i])
axis_names = ["X", "Y", "Z"]
print("Motion energy:", energy)
print("AUTO STRUM AXIS =", axis_names[axis])

print("\nHold STILL again.")
time.sleep_ms(1200)

s = 0.0
n = 80
for _ in range(n):
    vals = read_accel_g()
    s += vals[axis]
    time.sleep_ms(SAMPLE_MS)
axis_base = s / n

print("\nSTEP 3: When GO appears, make ONE clear DOWN strum.")
time.sleep_ms(1500)
print("GO - DOWN STRUM NOW!")

best = 0.0
filt = 0.0
end_time = time.ticks_add(time.ticks_ms(), 1800)

while time.ticks_diff(end_time, time.ticks_ms()) > 0:
    vals = read_accel_g()
    signal = vals[axis] - axis_base
    filt += FILTER_ALPHA * (signal - filt)
    if abs(filt) > abs(best):
        best = filt
    time.sleep_ms(SAMPLE_MS)

if abs(best) < 0.18:
    print("DOWN calibration too weak. Restart and use a stronger stroke.")
    raise SystemExit

down_polarity = 1 if best > 0 else -1

print("\nAIRFRET STRUM READY")
print("Axis:", axis_names[axis])
print("DOWN sign:", "+" if down_polarity > 0 else "-")
print("DOWN physical motion -> STRUM DOWN")
print("UP physical motion   -> STRUM UP\n")

filt = 0.0
armed = True
neutral_count = 0
last_trigger = time.ticks_ms()
rest_base = axis_base

while True:
    vals = read_accel_g()
    raw_axis = vals[axis]
    signal = raw_axis - rest_base
    filt += FILTER_ALPHA * (signal - filt)

    now = time.ticks_ms()
    gap = time.ticks_diff(now, last_trigger)

    if armed:
        if abs(filt) >= TRIGGER_G and gap >= MIN_GAP_MS:
            physical = filt * down_polarity
            if physical > 0:
                print("STRUM DOWN | %.2f g" % abs(filt))
            else:
                print("STRUM UP   | %.2f g" % abs(filt))
            last_trigger = now
            armed = False
            neutral_count = 0
    else:
        if gap >= MIN_GAP_MS and abs(filt) <= RESET_G:
            neutral_count += 1
            if neutral_count >= NEUTRAL_SAMPLES_NEEDED:
                armed = True
                neutral_count = 0
        else:
            neutral_count = 0

    if armed and abs(filt) < 0.10:
        rest_base = rest_base * 0.998 + raw_axis * 0.002

    time.sleep_ms(SAMPLE_MS)

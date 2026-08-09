from machine import Pin, I2C
import time

# ============================================================
# AIRFRET MPU6050 STRUM AXIS TEST
# ============================================================
# Wiring:
# VCC -> 3V3
# GND -> GND
# SDA -> GP20
# SCL -> GP21
#
# OLED may stay connected to the same SDA/SCL bus.
# ============================================================

i2c = I2C(
    0,
    sda=Pin(20),
    scl=Pin(21),
    freq=50000
)

devices = i2c.scan()
print("I2C:", [hex(x) for x in devices])

if 0x68 in devices:
    MPU = 0x68
elif 0x69 in devices:
    MPU = 0x69
else:
    raise RuntimeError("MPU6050 not found at 0x68/0x69")

# Registers
PWR_MGMT_1 = 0x6B
GYRO_CONFIG = 0x1B
GYRO_XOUT_H = 0x43

# Wake sensor.
i2c.writeto_mem(MPU, PWR_MGMT_1, b"\x00")
time.sleep_ms(100)

# +/-500 deg/s gyro range.
# Sensitivity: approximately 65.5 raw counts per deg/s.
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
# Still-position calibration
# ------------------------------------------------------------
print()
print("HOLD THE SENSOR STILL...")
time.sleep_ms(500)

sx = 0
sy = 0
sz = 0
samples = 60

for _ in range(samples):
    gx, gy, gz = read_raw()
    sx += gx
    sy += gy
    sz += gz
    time.sleep_ms(5)

bx = sx // samples
by = sy // samples
bz = sz // samples

print("Bias:", bx, by, bz)
print()
print("Now make DOWN and UP guitar-strum motions.")
print("Look for lines such as:")
print("MOTION: Y +220 dps")
print("MOTION: Y -205 dps")
print()

armed = True
TRIGGER_DPS = 90
RESET_DPS = 35

while True:
    gx, gy, gz = read_raw()

    x = (gx - bx) / 65.5
    y = (gy - by) / 65.5
    z = (gz - bz) / 65.5

    values = (x, y, z)
    names = ("X", "Y", "Z")

    dominant_index = 0
    dominant_abs = abs(values[0])

    if abs(values[1]) > dominant_abs:
        dominant_index = 1
        dominant_abs = abs(values[1])

    if abs(values[2]) > dominant_abs:
        dominant_index = 2
        dominant_abs = abs(values[2])

    dominant = values[dominant_index]

    if armed and dominant_abs >= TRIGGER_DPS:
        sign = "+" if dominant >= 0 else "-"
        print(
            "MOTION:",
            names[dominant_index],
            sign + str(round(abs(dominant))),
            "dps",
            "| X", round(x),
            "Y", round(y),
            "Z", round(z)
        )
        armed = False

    elif not armed:
        if max(abs(x), abs(y), abs(z)) <= RESET_DPS:
            armed = True

    time.sleep_ms(8)

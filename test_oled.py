from machine import Pin, I2C
import ssd1306

print("Starting OLED test...")

i2c = I2C(
    0,
    sda=Pin(20),
    scl=Pin(21),
    freq=50000
)

print(
    "I2C devices:",
    i2c.scan()
)

oled = ssd1306.SSD1306_I2C(
    128,
    64,
    i2c,
    addr=0x3C
)

oled.fill(0)

oled.text(
    "AIRFRET",
    32,
    5
)

oled.text(
    "C MAJOR",
    32,
    25
)

oled.text(
    "STRUM DOWN",
    16,
    45
)

oled.show()

print(
    "OLED TEST COMPLETE"
)
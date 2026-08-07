from machine import ADC
import time

slider = ADC(26)

while True:
    raw = slider.read_u16()
    volume = round(raw * 100 / 65535)

    print("Volume:", volume, "%")

    time.sleep_ms(200)
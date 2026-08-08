from machine import ADC
import time

slider = ADC(26)

# Start at current reading
filtered = slider.read_u16()
last_percent = -1

while True:

    # Average 20 measurements
    total = 0

    for _ in range(20):
        total += slider.read_u16()

    average = total // 20

    # Smooth it heavily
    filtered = (
        filtered * 7
        + average
    ) // 8

    # End zones
    if filtered < 2500:
        filtered = 0

    elif filtered > 63000:
        filtered = 65535

    # Convert to 0–100%
    percent = (
        filtered * 100
        // 65535
    )

    # Only report changes of 2% or more
    if (
        last_percent == -1
        or abs(percent - last_percent) >= 2
    ):

        last_percent = percent

        print(
            "VOLUME:",
            percent,
            "%"
        )

    time.sleep_ms(25)
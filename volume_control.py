import RPi.GPIO as GPIO
import time
import subprocess  # Zmieniono: zamiast pyvolume

BUTTON = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

cycle_values = [0, 25, 50, 75, 100]
index = 0
last_press_time = 0
debounce_delay = 0.3  # seconds

print("Volume control started...")

def set_volume(volume_percent):
    try:
        command = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume_percent}%"]
        
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Volume set to {volume_percent}%")
        
    except subprocess.CalledProcessError:
        print(f"Error: Failed to set volume to {volume_percent}%")
    except FileNotFoundError:
        print("Error: 'pactl' command not found. Install it via 'sudo apt install pulseaudio-utils'")

try:
    while True:
        current_time = time.time()

        if GPIO.input(BUTTON) == GPIO.LOW:
            if current_time - last_press_time > debounce_delay:
                # Zmieniono: wywo?anie naszej nowej funkcji
                set_volume(cycle_values[index])
                
                index = (index + 1) % len(cycle_values)
                last_press_time = current_time

            while GPIO.input(BUTTON) == GPIO.LOW:
                time.sleep(0.01)

        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nExiting volume control.")
finally:
    GPIO.cleanup()
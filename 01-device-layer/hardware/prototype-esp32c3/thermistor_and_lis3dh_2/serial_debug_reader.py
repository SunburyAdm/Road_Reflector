import serial
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument("--port", required=True)
parser.add_argument("--baud", type=int, default=115200)
args = parser.parse_args()

ser = serial.Serial(args.port, args.baud, timeout=1)
time.sleep(2)
ser.reset_input_buffer()

print("Reading serial data... Press Ctrl+C to stop.")

try:
    while True:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(line)
except KeyboardInterrupt:
    pass
finally:
    ser.close()
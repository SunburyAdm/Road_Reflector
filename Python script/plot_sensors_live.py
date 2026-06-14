import argparse
import math
import time
from collections import deque

import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


def parse_line(line: str):
    line = line.strip()

    if not line:
        return None

    if line.startswith("time_ms"):
        return None

    if line.startswith("ERROR"):
        print(line)
        return None

    parts = line.split(",")

    # Expected:
    # time_ms,temp_c,ax,ay,az,mag,dynamic_mag,peak_dynamic
    if len(parts) != 8:
        return None

    try:
        time_ms = float(parts[0])
        temp_c = float(parts[1]) if parts[1].lower() != "nan" else math.nan
        ax = float(parts[2])
        ay = float(parts[3])
        az = float(parts[4])
        mag = float(parts[5])
        dynamic_mag = float(parts[6])
        peak_dynamic = float(parts[7])

        return time_ms, temp_c, ax, ay, az, mag, dynamic_mag, peak_dynamic

    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Example: COM5 or /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--window", type=float, default=10.0)
    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.02)
    time.sleep(2)
    ser.reset_input_buffer()

    max_points = 1500

    t_data = deque(maxlen=max_points)
    temp_data = deque(maxlen=max_points)
    ax_data = deque(maxlen=max_points)
    ay_data = deque(maxlen=max_points)
    az_data = deque(maxlen=max_points)
    mag_data = deque(maxlen=max_points)
    dyn_data = deque(maxlen=max_points)
    peak_data = deque(maxlen=max_points)

    start_ms = None

    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)

    ax_temp = axes[0]
    ax_xyz = axes[1]
    ax_mag = axes[2]
    ax_dyn = axes[3]

    line_temp, = ax_temp.plot([], [], label="Temperature C")
    line_x, = ax_xyz.plot([], [], label="X")
    line_y, = ax_xyz.plot([], [], label="Y")
    line_z, = ax_xyz.plot([], [], label="Z")
    line_mag, = ax_mag.plot([], [], label="Magnitude")
    line_dyn, = ax_dyn.plot([], [], label="Dynamic magnitude")
    line_peak, = ax_dyn.plot([], [], label="Peak dynamic")

    ax_temp.set_ylabel("Temp [C]")
    ax_temp.legend(loc="upper right")
    ax_temp.grid(True)

    ax_xyz.set_ylabel("Accel [m/s²]")
    ax_xyz.legend(loc="upper right")
    ax_xyz.grid(True)

    ax_mag.set_ylabel("Mag [m/s²]")
    ax_mag.legend(loc="upper right")
    ax_mag.grid(True)

    ax_dyn.set_xlabel("Time [s]")
    ax_dyn.set_ylabel("Dynamic [m/s²]")
    ax_dyn.legend(loc="upper right")
    ax_dyn.grid(True)

    fig.suptitle("ESP32-C3 NTC + LIS3DH Live Data")

    def update(_frame):
        nonlocal start_ms

        lines_read = 0

        while ser.in_waiting and lines_read < 50:
            raw = ser.readline().decode("utf-8", errors="ignore")
            lines_read += 1

            parsed = parse_line(raw)
            if parsed is None:
                continue

            time_ms, temp_c, ax, ay, az, mag, dynamic_mag, peak_dynamic = parsed

            if start_ms is None:
                start_ms = time_ms

            t_s = (time_ms - start_ms) / 1000.0

            t_data.append(t_s)
            temp_data.append(temp_c)
            ax_data.append(ax)
            ay_data.append(ay)
            az_data.append(az)
            mag_data.append(mag)
            dyn_data.append(dynamic_mag)
            peak_data.append(peak_dynamic)

        if len(t_data) < 2:
            return line_temp, line_x, line_y, line_z, line_mag, line_dyn, line_peak

        current_t = t_data[-1]
        min_t = max(0.0, current_t - args.window)
        max_t = max(args.window, current_t)

        line_temp.set_data(t_data, temp_data)
        line_x.set_data(t_data, ax_data)
        line_y.set_data(t_data, ay_data)
        line_z.set_data(t_data, az_data)
        line_mag.set_data(t_data, mag_data)
        line_dyn.set_data(t_data, dyn_data)
        line_peak.set_data(t_data, peak_data)

        ax_dyn.set_xlim(min_t, max_t)

        valid_temp = [v for v in temp_data if not math.isnan(v)]
        if valid_temp:
            ax_temp.set_ylim(min(valid_temp) - 1, max(valid_temp) + 1)

        xyz_values = list(ax_data) + list(ay_data) + list(az_data)
        if xyz_values:
            ax_xyz.set_ylim(min(xyz_values) - 2, max(xyz_values) + 2)

        if mag_data:
            ax_mag.set_ylim(min(mag_data) - 1, max(mag_data) + 1)

        dynamic_values = list(dyn_data) + list(peak_data)
        if dynamic_values:
            upper = max(dynamic_values) + 0.2
            ax_dyn.set_ylim(0, max(0.5, upper))

        return line_temp, line_x, line_y, line_z, line_mag, line_dyn, line_peak

    animation = FuncAnimation(
        fig,
        update,
        interval=100,
        blit=False,
        cache_frame_data=False
    )

    print("Live plot started.")
    print("Close the plot window or press Ctrl+C to stop.")

    try:
        plt.tight_layout()
        plt.show()
    finally:
        ser.close()
        print("Serial port closed.")


if __name__ == "__main__":
    main()
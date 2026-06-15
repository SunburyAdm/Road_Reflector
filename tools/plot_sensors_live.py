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
    # time_ms,temp_c,ax,ay,az,mag,dynamic_mag,peak_dynamic,piezo_mv,piezo_signal_mv,piezo_peak_mv,piezo_event
    if len(parts) != 12:
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

        piezo_mv = float(parts[8])
        piezo_signal_mv = float(parts[9])
        piezo_peak_mv = float(parts[10])
        piezo_event = int(float(parts[11]))

        return (
            time_ms,
            temp_c,
            ax,
            ay,
            az,
            mag,
            dynamic_mag,
            peak_dynamic,
            piezo_mv,
            piezo_signal_mv,
            piezo_peak_mv,
            piezo_event,
        )

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

    max_points = 2000

    t_data = deque(maxlen=max_points)
    temp_data = deque(maxlen=max_points)

    ax_data = deque(maxlen=max_points)
    ay_data = deque(maxlen=max_points)
    az_data = deque(maxlen=max_points)

    mag_data = deque(maxlen=max_points)
    dyn_data = deque(maxlen=max_points)
    peak_dyn_data = deque(maxlen=max_points)

    piezo_mv_data = deque(maxlen=max_points)
    piezo_signal_data = deque(maxlen=max_points)
    piezo_peak_data = deque(maxlen=max_points)
    piezo_event_data = deque(maxlen=max_points)

    start_ms = None

    fig, axes = plt.subplots(5, 1, figsize=(12, 10), sharex=True)

    ax_temp_plot = axes[0]
    ax_xyz_plot = axes[1]
    ax_dynamic_plot = axes[2]
    ax_piezo_raw_plot = axes[3]
    ax_piezo_signal_plot = axes[4]

    line_temp, = ax_temp_plot.plot([], [], label="Temperature C")

    line_x, = ax_xyz_plot.plot([], [], label="X")
    line_y, = ax_xyz_plot.plot([], [], label="Y")
    line_z, = ax_xyz_plot.plot([], [], label="Z")

    line_dyn, = ax_dynamic_plot.plot([], [], label="Dynamic magnitude")
    line_peak_dyn, = ax_dynamic_plot.plot([], [], label="Peak dynamic")

    line_piezo_mv, = ax_piezo_raw_plot.plot([], [], label="Piezo raw mV")

    line_piezo_signal, = ax_piezo_signal_plot.plot([], [], label="Piezo signal mV")
    line_piezo_peak, = ax_piezo_signal_plot.plot([], [], label="Piezo peak mV")
    line_piezo_event, = ax_piezo_signal_plot.plot([], [], label="Piezo event x100")

    ax_temp_plot.set_ylabel("Temp [C]")
    ax_temp_plot.legend(loc="upper right")
    ax_temp_plot.grid(True)

    ax_xyz_plot.set_ylabel("Accel [m/s²]")
    ax_xyz_plot.legend(loc="upper right")
    ax_xyz_plot.grid(True)

    ax_dynamic_plot.set_ylabel("Dynamic [m/s²]")
    ax_dynamic_plot.legend(loc="upper right")
    ax_dynamic_plot.grid(True)

    ax_piezo_raw_plot.set_ylabel("Piezo raw [mV]")
    ax_piezo_raw_plot.legend(loc="upper right")
    ax_piezo_raw_plot.grid(True)

    ax_piezo_signal_plot.set_xlabel("Time [s]")
    ax_piezo_signal_plot.set_ylabel("Piezo signal [mV]")
    ax_piezo_signal_plot.legend(loc="upper right")
    ax_piezo_signal_plot.grid(True)

    fig.suptitle("ESP32-C3 Smart Reflector Sensors: NTC + LIS3DH + Piezo")

    def update(_frame):
        nonlocal start_ms

        lines_read = 0

        while ser.in_waiting and lines_read < 60:
            raw = ser.readline().decode("utf-8", errors="ignore")
            lines_read += 1

            parsed = parse_line(raw)
            if parsed is None:
                continue

            (
                time_ms,
                temp_c,
                ax,
                ay,
                az,
                mag,
                dynamic_mag,
                peak_dynamic,
                piezo_mv,
                piezo_signal_mv,
                piezo_peak_mv,
                piezo_event,
            ) = parsed

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
            peak_dyn_data.append(peak_dynamic)

            piezo_mv_data.append(piezo_mv)
            piezo_signal_data.append(piezo_signal_mv)
            piezo_peak_data.append(piezo_peak_mv)

            # Scale event so it is visible on the same plot
            piezo_event_data.append(piezo_event * 100.0)

        if len(t_data) < 2:
            return (
                line_temp,
                line_x,
                line_y,
                line_z,
                line_dyn,
                line_peak_dyn,
                line_piezo_mv,
                line_piezo_signal,
                line_piezo_peak,
                line_piezo_event,
            )

        current_t = t_data[-1]
        min_t = max(0.0, current_t - args.window)
        max_t = max(args.window, current_t)

        line_temp.set_data(t_data, temp_data)

        line_x.set_data(t_data, ax_data)
        line_y.set_data(t_data, ay_data)
        line_z.set_data(t_data, az_data)

        line_dyn.set_data(t_data, dyn_data)
        line_peak_dyn.set_data(t_data, peak_dyn_data)

        line_piezo_mv.set_data(t_data, piezo_mv_data)

        line_piezo_signal.set_data(t_data, piezo_signal_data)
        line_piezo_peak.set_data(t_data, piezo_peak_data)
        line_piezo_event.set_data(t_data, piezo_event_data)

        ax_piezo_signal_plot.set_xlim(min_t, max_t)

        valid_temp = [v for v in temp_data if not math.isnan(v)]
        if valid_temp:
            ax_temp_plot.set_ylim(min(valid_temp) - 1, max(valid_temp) + 1)

        xyz_values = list(ax_data) + list(ay_data) + list(az_data)
        if xyz_values:
            ax_xyz_plot.set_ylim(min(xyz_values) - 2, max(xyz_values) + 2)

        dynamic_values = list(dyn_data) + list(peak_dyn_data)
        if dynamic_values:
            upper = max(dynamic_values) + 0.2
            ax_dynamic_plot.set_ylim(0, max(0.5, upper))

        if piezo_mv_data:
            min_p = min(piezo_mv_data)
            max_p = max(piezo_mv_data)
            padding = max(20.0, (max_p - min_p) * 0.2)
            ax_piezo_raw_plot.set_ylim(min_p - padding, max_p + padding)

        piezo_values = list(piezo_signal_data) + list(piezo_peak_data) + list(piezo_event_data)
        if piezo_values:
            upper = max(piezo_values) + 50
            ax_piezo_signal_plot.set_ylim(0, max(200, upper))

        return (
            line_temp,
            line_x,
            line_y,
            line_z,
            line_dyn,
            line_peak_dyn,
            line_piezo_mv,
            line_piezo_signal,
            line_piezo_peak,
            line_piezo_event,
        )

    animation = FuncAnimation(
        fig,
        update,
        interval=100,
        blit=False,
        cache_frame_data=False,
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
# simulation/asphalt_vibration_gui.py

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.signal import spectrogram as _scipy_spectrogram

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


G = 9.80665


@dataclass
class AsphaltModelConfig:
    asphalt_thickness_m: float = 0.08
    asphalt_density_kg_m3: float = 2300.0
    poisson_ratio: float = 0.35
    temperature_c: float = 20.0
    effective_radius_m: float = 0.35
    damping_ratio: float = 0.18
    subgrade_stiffness_n_m3: float = 120e6
    housing_gain: float = 1.0


@dataclass
class VehicleConfig:
    vehicle_mass_kg: float = 1600.0
    speed_m_s: float = 8.0
    num_axles: int = 2
    axle_spacing_m: float = 2.7
    track_width_m: float = 1.6
    lateral_offset_m: float = 0.30
    influence_sigma_x_m: float = 0.45
    influence_sigma_y_m: float = 0.55
    dynamic_load_ratio: float = 0.12
    dynamic_load_frequency_hz: float = 9.0
    start_x_m: float = -10.0
    end_x_m: float = 10.0
    include_opposite_wheels: bool = True


def asphalt_storage_modulus_pa(temperature_c: float) -> float:
    """
    Approximate asphalt storage modulus E'(T).

    Cold asphalt -> stiffer.
    Hot asphalt  -> softer.
    """

    temp_points = np.array([-20.0, -10.0, 0.0, 20.0, 40.0, 55.0])
    modulus_points = np.array([22e9, 16e9, 10e9, 4e9, 0.9e9, 0.35e9])

    log_e = np.log10(modulus_points)
    interpolated_log_e = np.interp(temperature_c, temp_points, log_e)

    return 10 ** interpolated_log_e


def equivalent_asphalt_parameters(config: AsphaltModelConfig):
    area_m2 = np.pi * config.effective_radius_m ** 2

    e_asphalt_pa = asphalt_storage_modulus_pa(config.temperature_c)

    m_eq = (
        config.asphalt_density_kg_m3
        * config.asphalt_thickness_m
        * area_m2
    )

    k_asphalt = (
        e_asphalt_pa
        * area_m2
        / (config.asphalt_thickness_m * (1.0 - config.poisson_ratio ** 2))
    )

    k_subgrade = config.subgrade_stiffness_n_m3 * area_m2

    k_eq = (k_asphalt * k_subgrade) / (k_asphalt + k_subgrade)

    c_eq = 2.0 * config.damping_ratio * np.sqrt(k_eq * m_eq)

    natural_frequency_hz = (1.0 / (2.0 * np.pi)) * np.sqrt(k_eq / m_eq)

    return {
        "area_m2": area_m2,
        "e_asphalt_pa": e_asphalt_pa,
        "m_eq_kg": m_eq,
        "k_asphalt_n_m": k_asphalt,
        "k_subgrade_n_m": k_subgrade,
        "k_eq_n_m": k_eq,
        "c_eq_n_s_m": c_eq,
        "natural_frequency_hz": natural_frequency_hz,
    }


def gaussian_influence(dx_m: float, dy_m: float, sigma_x_m: float, sigma_y_m: float) -> float:
    return np.exp(
        -(
            (dx_m ** 2) / (2.0 * sigma_x_m ** 2)
            + (dy_m ** 2) / (2.0 * sigma_y_m ** 2)
        )
    )


def tire_force_at_sensor(t: float, vehicle: VehicleConfig) -> float:
    sides = 2 if vehicle.include_opposite_wheels else 1
    total_wheels = vehicle.num_axles * sides
    static_force_per_wheel_n = vehicle.vehicle_mass_kg * G / total_wheels

    dynamic_multiplier = (
        1.0
        + vehicle.dynamic_load_ratio
        * np.sin(2.0 * np.pi * vehicle.dynamic_load_frequency_hz * t)
    )

    wheel_force_n = static_force_per_wheel_n * dynamic_multiplier

    front_x_m = vehicle.start_x_m + vehicle.speed_m_s * t

    axle_x_positions = [
        front_x_m - i * vehicle.axle_spacing_m
        for i in range(vehicle.num_axles)
    ]

    wheel_positions = [
        (ax, vehicle.lateral_offset_m)
        for ax in axle_x_positions
    ]

    if vehicle.include_opposite_wheels:
        opposite_lateral_offset_m = vehicle.lateral_offset_m + vehicle.track_width_m
        wheel_positions.extend([
            (ax, opposite_lateral_offset_m)
            for ax in axle_x_positions
        ])

    total_force_n = 0.0

    for wheel_x_m, wheel_y_m in wheel_positions:
        influence = gaussian_influence(
            dx_m=wheel_x_m,
            dy_m=wheel_y_m,
            sigma_x_m=vehicle.influence_sigma_x_m,
            sigma_y_m=vehicle.influence_sigma_y_m,
        )

        total_force_n += wheel_force_n * influence

    return total_force_n


def asphalt_ode(t, state, asphalt_params, vehicle_config):
    z = state[0]
    z_dot = state[1]

    m = asphalt_params["m_eq_kg"]
    c = asphalt_params["c_eq_n_s_m"]
    k = asphalt_params["k_eq_n_m"]

    force_n = tire_force_at_sensor(t, vehicle_config)

    z_ddot = (force_n - c * z_dot - k * z) / m

    return [z_dot, z_ddot]


def simulate(asphalt_config: AsphaltModelConfig, vehicle_config: VehicleConfig, sample_rate_hz: float):
    asphalt_params = equivalent_asphalt_parameters(asphalt_config)

    duration_s = (
        (vehicle_config.end_x_m - vehicle_config.start_x_m)
        / vehicle_config.speed_m_s
    )

    duration_s = max(duration_s, 0.5)

    dt = 1.0 / sample_rate_hz
    t_eval = np.arange(0.0, duration_s, dt)

    solution = solve_ivp(
        fun=lambda t, y: asphalt_ode(
            t=t,
            state=y,
            asphalt_params=asphalt_params,
            vehicle_config=vehicle_config,
        ),
        t_span=(0.0, duration_s),
        y0=[0.0, 0.0],
        t_eval=t_eval,
        method="RK45",
        rtol=1e-7,
        atol=1e-9,
    )

    t = solution.t
    z = solution.y[0]
    z_dot = solution.y[1]

    force = np.array([
        tire_force_at_sensor(time, vehicle_config)
        for time in t
    ])

    m = asphalt_params["m_eq_kg"]
    c = asphalt_params["c_eq_n_s_m"]
    k = asphalt_params["k_eq_n_m"]

    z_ddot = (force - c * z_dot - k * z) / m

    acceleration_m_s2 = asphalt_config.housing_gain * z_ddot
    acceleration_g = acceleration_m_s2 / G

    df = pd.DataFrame({
        "time_s": t,
        "force_n": force,
        "displacement_m": z,
        "displacement_mm": z * 1000.0,
        "velocity_m_s": z_dot,
        "acceleration_m_s2": acceleration_m_s2,
        "acceleration_g": acceleration_g,
    })

    return df, asphalt_params


def estimate_fft(df, sample_rate_hz):
    acceleration = df["acceleration_g"].to_numpy()
    acceleration = acceleration - np.mean(acceleration)

    n = len(acceleration)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)
    spectrum = np.abs(np.fft.rfft(acceleration))

    return freqs, spectrum


def add_sensor_noise(
    acceleration_g: np.ndarray,
    noise_density_ug_sqrthz: float,
    sample_rate_hz: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Add Gaussian white noise matching the ADXL362 noise density spec.
    noise_density_ug_sqrthz: 175 μg/√Hz (ADXL362 typical).
    σ = noise_density [g/√Hz] × √(sample_rate / 2)
    """
    noise_density_g = noise_density_ug_sqrthz * 1e-6
    sigma_g = noise_density_g * np.sqrt(sample_rate_hz / 2.0)
    noise = rng.normal(loc=0.0, scale=sigma_g, size=len(acceleration_g))
    return acceleration_g + noise


def simulate_sensor_array(
    asphalt_config: AsphaltModelConfig,
    vehicle_config: VehicleConfig,
    sensor_x_positions_m: list,
    noise_density_ug_sqrthz: float,
    enable_noise: bool,
    sample_rate_hz: float,
) -> list:
    """
    Simulate the same vehicle pass for N sensors at different x positions.
    All sensors share the same time base: the vehicle range is extended so
    the vehicle fully traverses all sensor positions.
    """
    rng = np.random.default_rng(seed=42)
    max_sensor_x = max(sensor_x_positions_m) if sensor_x_positions_m else 0.0

    sensor_dfs = []
    for sx in sensor_x_positions_m:
        sensor_vehicle = VehicleConfig(
            vehicle_mass_kg=vehicle_config.vehicle_mass_kg,
            speed_m_s=vehicle_config.speed_m_s,
            num_axles=vehicle_config.num_axles,
            axle_spacing_m=vehicle_config.axle_spacing_m,
            track_width_m=vehicle_config.track_width_m,
            lateral_offset_m=vehicle_config.lateral_offset_m,
            influence_sigma_x_m=vehicle_config.influence_sigma_x_m,
            influence_sigma_y_m=vehicle_config.influence_sigma_y_m,
            dynamic_load_ratio=vehicle_config.dynamic_load_ratio,
            dynamic_load_frequency_hz=vehicle_config.dynamic_load_frequency_hz,
            # Shift start/end so all sensors share the same duration
            start_x_m=vehicle_config.start_x_m - sx,
            end_x_m=vehicle_config.end_x_m + max_sensor_x - sx,
            include_opposite_wheels=vehicle_config.include_opposite_wheels,
        )
        df, _ = simulate(asphalt_config, sensor_vehicle, sample_rate_hz)

        clean_accel = df["acceleration_g"].to_numpy()
        noisy_accel = (
            add_sensor_noise(clean_accel, noise_density_ug_sqrthz, sample_rate_hz, rng)
            if enable_noise
            else clean_accel.copy()
        )

        df = df.copy()
        df["acceleration_g_clean"] = clean_accel
        df["acceleration_g"] = noisy_accel
        df["sensor_x_m"] = sx
        sensor_dfs.append(df)

    return sensor_dfs


def estimate_speed_xcorr(
    sig1: np.ndarray,
    sig2: np.ndarray,
    dt: float,
    sensor_spacing_m: float,
):
    """
    Estimate vehicle speed from the cross-correlation lag between two sensors.
    Returns (speed_m_s, lag_s, lags_array, corr_array).
    """
    n = min(len(sig1), len(sig2))
    s1 = sig1[:n] - np.mean(sig1[:n])
    s2 = sig2[:n] - np.mean(sig2[:n])
    corr = np.correlate(s1, s2, mode="full")
    lags = np.arange(-(n - 1), n) * dt
    peak_idx = int(np.argmax(np.abs(corr)))
    lag_s = lags[peak_idx]
    if abs(lag_s) < dt * 0.5:
        return 0.0, lag_s, lags, corr
    return abs(sensor_spacing_m / lag_s), lag_s, lags, corr


def detect_event(
    accel_g: np.ndarray,
    sample_rate_hz: float,
    window_s: float = 0.1,
    threshold_multiplier: float = 3.0,
):
    """
    Detect vehicle events using a windowed RMS + adaptive threshold.
    Returns (rms_array, threshold_value, event_mask).
    """
    window_samples = max(1, int(window_s * sample_rate_hz))
    series = pd.Series(accel_g ** 2)
    rms = np.sqrt(
        series.rolling(window=window_samples, center=True, min_periods=1).mean().to_numpy()
    )
    baseline = np.percentile(rms, 15)
    threshold = max(baseline * threshold_multiplier, 1e-12)
    return rms, threshold, rms > threshold


def compute_spectrogram(accel_g: np.ndarray, sample_rate_hz: float):
    """
    Compute STFT spectrogram of acceleration signal.
    Returns (frequencies, times, power_density).
    """
    nperseg = min(256, max(16, len(accel_g) // 8))
    noverlap = int(nperseg * 0.75)
    f, t, Sxx = _scipy_spectrogram(
        accel_g - np.mean(accel_g),
        fs=sample_rate_hz,
        nperseg=nperseg,
        noverlap=noverlap,
        window="hann",
    )
    return f, t, Sxx


def export_json_dataset(
    sensor_dfs: list,
    vehicle_config: VehicleConfig,
    asphalt_config: AsphaltModelConfig,
    event_mask: np.ndarray,
    estimated_speed_ms: float,
    vehicle_class: str,
    output_path: str,
) -> str:
    """
    Export a labeled sensor dataset as JSON for backend classifier training.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    sensors_meta = [
        {"sensor_id": f"SRR-SIM-{i + 1:03d}", "x_m": float(df["sensor_x_m"].iloc[0])}
        for i, df in enumerate(sensor_dfs)
    ]

    samples = []
    for i, df in enumerate(sensor_dfs):
        sensor_id = f"SRR-SIM-{i + 1:03d}"
        for row in df.itertuples(index=False):
            samples.append({
                "sensor_id": sensor_id,
                "time_s": round(float(row.time_s), 6),
                "acceleration_g": round(float(row.acceleration_g), 8),
                "force_n": round(float(row.force_n), 4),
            })

    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vehicle_class": vehicle_class,
        "vehicle_mass_kg": vehicle_config.vehicle_mass_kg,
        "num_axles": vehicle_config.num_axles,
        "speed_true_m_s": round(vehicle_config.speed_m_s, 4),
        "speed_true_kmh": round(vehicle_config.speed_m_s * 3.6, 2),
        "speed_estimated_m_s": round(abs(estimated_speed_ms), 4) if estimated_speed_ms else None,
        "asphalt_temperature_c": asphalt_config.temperature_c,
        "sensors": sensors_meta,
        "samples": samples,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(dataset, fh, indent=2)

    return output_path


class CollapsibleSection(ttk.Frame):
    def __init__(self, parent, title, expanded=True):
        super().__init__(parent)

        self.title = title
        self.expanded = expanded

        self.header_button = ttk.Button(
            self,
            text=self._get_header_text(),
            command=self.toggle
        )
        self.header_button.pack(fill=tk.X, pady=(4, 1))

        self.body = ttk.Frame(self, padding=(8, 2, 4, 6))

        if self.expanded:
            self.body.pack(fill=tk.X)

    def _get_header_text(self):
        arrow = "▼" if self.expanded else "▶"
        return f"{arrow} {self.title}"

    def toggle(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded):
        self.expanded = expanded

        if self.expanded:
            self.body.pack(fill=tk.X)
        else:
            self.body.pack_forget()

        self.header_button.config(text=self._get_header_text())

        
class AsphaltVibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Asphalt Vibration Model - Interactive Simulation")
        self.root.geometry("1650x960")

        self.latest_df = None
        self.latest_params = None
        self.latest_array_dfs = None
        self.latest_sensor_positions = []
        self.latest_speed_estimate = None
        self.latest_xcorr = None
        self.latest_event = None

        self._create_variables()
        self._create_layout()
        self.update_simulation()

    def _create_variables(self):
        self.temperature_c = tk.DoubleVar(value=20.0)
        self.vehicle_mass_kg = tk.DoubleVar(value=1600.0)
        self.speed_kmh = tk.DoubleVar(value=28.8)
        self.num_axles = tk.IntVar(value=2)
        self.axle_spacing_m = tk.DoubleVar(value=2.7)
        self.lateral_offset_m = tk.DoubleVar(value=0.30)

        self.asphalt_thickness_cm = tk.DoubleVar(value=8.0)
        self.effective_radius_m = tk.DoubleVar(value=0.35)
        self.damping_ratio = tk.DoubleVar(value=0.18)

        self.subgrade_stiffness_mn_m3 = tk.DoubleVar(value=120.0)

        self.dynamic_load_ratio_percent = tk.DoubleVar(value=12.0)
        self.dynamic_load_frequency_hz = tk.DoubleVar(value=9.0)

        self.sigma_x_m = tk.DoubleVar(value=0.45)
        self.sigma_y_m = tk.DoubleVar(value=0.55)

        self.sample_rate_hz = tk.DoubleVar(value=1000.0)
        self.housing_gain = tk.DoubleVar(value=1.0)

        self.include_opposite_wheels = tk.BooleanVar(value=True)

        # Sensor array & detection
        self.num_sensors = tk.IntVar(value=3)
        self.sensor_spacing_m = tk.DoubleVar(value=4.0)
        self.enable_noise = tk.BooleanVar(value=True)
        self.noise_density_ug = tk.DoubleVar(value=175.0)
        self.rms_window_ms = tk.DoubleVar(value=100.0)
        self.detection_threshold_mult = tk.DoubleVar(value=3.0)
        self.vehicle_class = tk.StringVar(value="medium_vehicle")


#####

    def _add_collapsible_section(self, title, expanded=True):
        section = CollapsibleSection(
            self.control_content,
            title=title,
            expanded=expanded
        )
        section.pack(fill=tk.X, pady=(2, 2))

        self.sections.append(section)

        return section.body


    def _expand_all_sections(self):
        for section in self.sections:
            section.set_expanded(True)


    def _collapse_all_sections(self):
        for section in self.sections:
            section.set_expanded(False)


    def _bind_mousewheel(self, widget):
        widget.bind(
            "<Enter>",
            lambda event: widget.bind_all("<MouseWheel>", self._on_mousewheel)
        )

        widget.bind(
            "<Leave>",
            lambda event: widget.unbind_all("<MouseWheel>")
        )

        # Linux scroll support
        widget.bind_all("<Button-4>", self._on_linux_scroll_up)
        widget.bind_all("<Button-5>", self._on_linux_scroll_down)


    def _on_mousewheel(self, event):
        self.controls_canvas.yview_scroll(
            int(-1 * (event.delta / 120)),
            "units"
        )


    def _on_linux_scroll_up(self, event):
        self.controls_canvas.yview_scroll(-1, "units")


    def _on_linux_scroll_down(self, event):
        self.controls_canvas.yview_scroll(1, "units")





#####


    def _create_layout(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel
        control_outer_frame = ttk.Frame(main_frame, width=370)
        control_outer_frame.pack(side=tk.LEFT, fill=tk.Y)
        control_outer_frame.pack_propagate(False)

        # Right plot panel
        plot_frame = ttk.Frame(main_frame)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        title_frame = ttk.Frame(control_outer_frame, padding=(10, 8, 10, 4))
        title_frame.pack(fill=tk.X)

        title = ttk.Label(
            title_frame,
            text="Simulation Controls",
            font=("Segoe UI", 13, "bold")
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            title_frame,
            text="Expand sections, adjust values, then update.",
            font=("Segoe UI", 8)
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Scrollable control area
        scroll_container = ttk.Frame(control_outer_frame)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(4, 4))

        self.controls_canvas = tk.Canvas(
            scroll_container,
            highlightthickness=0,
            width=335
        )
        self.controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls_scrollbar = ttk.Scrollbar(
            scroll_container,
            orient=tk.VERTICAL,
            command=self.controls_canvas.yview
        )
        self.controls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.controls_canvas.configure(
            yscrollcommand=self.controls_scrollbar.set
        )

        self.control_content = ttk.Frame(self.controls_canvas)

        self.control_canvas_window = self.controls_canvas.create_window(
            (0, 0),
            window=self.control_content,
            anchor="nw"
        )

        self.control_content.bind(
            "<Configure>",
            lambda event: self.controls_canvas.configure(
                scrollregion=self.controls_canvas.bbox("all")
            )
        )

        self.controls_canvas.bind(
            "<Configure>",
            lambda event: self.controls_canvas.itemconfigure(
                self.control_canvas_window,
                width=event.width
            )
        )

        self._bind_mousewheel(self.controls_canvas)

        self.sections = []

        # Compact buttons for all sections
        section_button_frame = ttk.Frame(self.control_content)
        section_button_frame.pack(fill=tk.X, pady=(0, 6))

        expand_all_button = ttk.Button(
            section_button_frame,
            text="Expand All",
            command=self._expand_all_sections
        )
        expand_all_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        collapse_all_button = ttk.Button(
            section_button_frame,
            text="Collapse All",
            command=self._collapse_all_sections
        )
        collapse_all_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(3, 0))

        # Asphalt section
        asphalt_body = self._add_collapsible_section("Asphalt", expanded=True)

        self._add_slider(
            asphalt_body,
            "Temperature [°C]",
            self.temperature_c,
            -20,
            55,
            1
        )

        self._add_slider(
            asphalt_body,
            "Thickness [cm]",
            self.asphalt_thickness_cm,
            3,
            20,
            0.5
        )

        self._add_slider(
            asphalt_body,
            "Effective Radius [m]",
            self.effective_radius_m,
            0.10,
            1.00,
            0.01
        )

        self._add_slider(
            asphalt_body,
            "Damping Ratio ζ",
            self.damping_ratio,
            0.01,
            0.60,
            0.01
        )

        self._add_slider(
            asphalt_body,
            "Subgrade Stiffness [MN/m³]",
            self.subgrade_stiffness_mn_m3,
            20,
            300,
            5
        )

        # Vehicle section
        vehicle_body = self._add_collapsible_section("Vehicle", expanded=True)

        self._add_slider(
            vehicle_body,
            "Vehicle Mass [kg]",
            self.vehicle_mass_kg,
            50,
            15000,
            50
        )

        self._add_slider(
            vehicle_body,
            "Speed [km/h]",
            self.speed_kmh,
            2,
            120,
            1
        )

        self._add_slider(
            vehicle_body,
            "Number of Axles",
            self.num_axles,
            1,
            8,
            1
        )

        self._add_slider(
            vehicle_body,
            "Axle Spacing [m]",
            self.axle_spacing_m,
            0.5,
            8.0,
            0.1
        )

        self._add_slider(
            vehicle_body,
            "Sensor Lateral Offset [m]",
            self.lateral_offset_m,
            0.0,
            3.0,
            0.05
        )

        opposite_check = ttk.Checkbutton(
            vehicle_body,
            text="Include opposite-side wheels",
            variable=self.include_opposite_wheels
        )
        opposite_check.pack(anchor="w", pady=(4, 2))

        # Tire load section
        tire_body = self._add_collapsible_section(
            "Tire Load / Road Excitation",
            expanded=False
        )

        self._add_slider(
            tire_body,
            "Dynamic Load Ratio [%]",
            self.dynamic_load_ratio_percent,
            0,
            50,
            1
        )

        self._add_slider(
            tire_body,
            "Dynamic Load Frequency [Hz]",
            self.dynamic_load_frequency_hz,
            1,
            40,
            0.5
        )

        self._add_slider(
            tire_body,
            "Influence Sigma X [m]",
            self.sigma_x_m,
            0.05,
            1.50,
            0.05
        )

        self._add_slider(
            tire_body,
            "Influence Sigma Y [m]",
            self.sigma_y_m,
            0.05,
            1.50,
            0.05
        )

        # Sensor Array & Detection section
        array_body = self._add_collapsible_section("Sensor Array & Detection", expanded=True)

        self._add_slider(array_body, "Number of Sensors", self.num_sensors, 2, 5, 1)
        self._add_slider(array_body, "Sensor Spacing [m]", self.sensor_spacing_m, 1.0, 10.0, 0.5)

        noise_check = ttk.Checkbutton(
            array_body, text="Add ADXL362 noise (175 μg/√Hz)", variable=self.enable_noise
        )
        noise_check.pack(anchor="w", pady=(4, 2))

        self._add_slider(array_body, "Noise Density [μg/√Hz]", self.noise_density_ug, 50, 500, 25)
        self._add_slider(array_body, "RMS Window [ms]", self.rms_window_ms, 10, 500, 10)
        self._add_slider(array_body, "Detection Threshold ×", self.detection_threshold_mult, 1.5, 10.0, 0.5)

        class_frame = ttk.Frame(array_body)
        class_frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(class_frame, text="Vehicle Class", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Combobox(
            class_frame,
            textvariable=self.vehicle_class,
            width=15,
            values=["small_vehicle", "medium_vehicle", "large_vehicle", "heavy_vehicle", "motorcycle"],
            state="readonly",
        ).pack(side=tk.RIGHT)

        # Sensor section
        sensor_body = self._add_collapsible_section(
            "Sensor / Simulation",
            expanded=False
        )

        self._add_slider(
            sensor_body,
            "Housing Gain",
            self.housing_gain,
            0.1,
            5.0,
            0.1
        )

        self._add_slider(
            sensor_body,
            "Sample Rate [Hz]",
            self.sample_rate_hz,
            100,
            3000,
            100
        )

        # Bottom fixed area
        bottom_frame = ttk.Frame(control_outer_frame, padding=(10, 4, 10, 8))
        bottom_frame.pack(fill=tk.X)

        update_button = ttk.Button(
            bottom_frame,
            text="Update Simulation",
            command=self.update_simulation
        )
        update_button.pack(fill=tk.X, pady=(4, 4))

        save_button = ttk.Button(
            bottom_frame,
            text="Save CSV",
            command=self.save_csv
        )
        save_button.pack(fill=tk.X, pady=(0, 3))

        json_button = ttk.Button(
            bottom_frame,
            text="Export JSON Dataset",
            command=self.export_json,
        )
        json_button.pack(fill=tk.X, pady=(0, 3))

        config_frame = ttk.Frame(bottom_frame)
        config_frame.pack(fill=tk.X, pady=(0, 6))

        save_cfg_button = ttk.Button(
            config_frame,
            text="Save Config",
            command=self.save_config,
        )
        save_cfg_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        load_cfg_button = ttk.Button(
            config_frame,
            text="Load Config",
            command=self.load_config,
        )
        load_cfg_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        self.summary_label = ttk.Label(
            bottom_frame,
            text="",
            justify=tk.LEFT,
            font=("Consolas", 8)
        )
        self.summary_label.pack(anchor="w", pady=(4, 0))

        # Plot area
        self.figure = Figure(figsize=(10, 8), dpi=100)
        _ax_grid = self.figure.subplots(3, 2)
        # Store as nested list for easy [row][col] access
        self.axes = _ax_grid

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    ######

    def _add_section_label(self, parent, text):
        label = ttk.Label(
            parent,
            text=text,
            font=("Segoe UI", 11, "bold")
        )
        label.pack(anchor="w", pady=(12, 4))

    def _add_slider(self, parent, label_text, variable, from_value, to_value, resolution):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(1, 3))

        top_row = ttk.Frame(frame)
        top_row.pack(fill=tk.X)

        label = ttk.Label(
            top_row,
            text=label_text,
            font=("Segoe UI", 8)
        )
        label.pack(side=tk.LEFT, anchor="w")

        spinbox = tk.Spinbox(
            top_row,
            textvariable=variable,
            from_=from_value,
            to=to_value,
            increment=resolution,
            width=8,
            justify="right",
            font=("Segoe UI", 8)
        )
        spinbox.pack(side=tk.RIGHT)

        slider = ttk.Scale(
            frame,
            variable=variable,
            from_=from_value,
            to=to_value,
            orient=tk.HORIZONTAL
        )
        slider.pack(fill=tk.X, pady=(1, 0))

    def update_simulation(self):
        try:
            speed_m_s = self.speed_kmh.get() / 3.6

            asphalt_config = AsphaltModelConfig(
                asphalt_thickness_m=self.asphalt_thickness_cm.get() / 100.0,
                asphalt_density_kg_m3=2300.0,
                poisson_ratio=0.35,
                temperature_c=self.temperature_c.get(),
                effective_radius_m=self.effective_radius_m.get(),
                damping_ratio=self.damping_ratio.get(),
                subgrade_stiffness_n_m3=self.subgrade_stiffness_mn_m3.get() * 1e6,
                housing_gain=self.housing_gain.get(),
            )

            vehicle_config = VehicleConfig(
                vehicle_mass_kg=self.vehicle_mass_kg.get(),
                speed_m_s=speed_m_s,
                num_axles=int(self.num_axles.get()),
                axle_spacing_m=self.axle_spacing_m.get(),
                track_width_m=1.6,
                lateral_offset_m=self.lateral_offset_m.get(),
                influence_sigma_x_m=self.sigma_x_m.get(),
                influence_sigma_y_m=self.sigma_y_m.get(),
                dynamic_load_ratio=self.dynamic_load_ratio_percent.get() / 100.0,
                dynamic_load_frequency_hz=self.dynamic_load_frequency_hz.get(),
                start_x_m=-10.0,
                end_x_m=10.0,
                include_opposite_wheels=self.include_opposite_wheels.get(),
            )

            df, params = simulate(
                asphalt_config=asphalt_config,
                vehicle_config=vehicle_config,
                sample_rate_hz=self.sample_rate_hz.get()
            )

            self.latest_df = df
            self.latest_params = params

            # ── Sensor array simulation ─────────────────────────────────────
            num_s = int(self.num_sensors.get())
            spacing = self.sensor_spacing_m.get()
            sensor_positions = [i * spacing for i in range(num_s)]

            array_dfs = simulate_sensor_array(
                asphalt_config=asphalt_config,
                vehicle_config=vehicle_config,
                sensor_x_positions_m=sensor_positions,
                noise_density_ug_sqrthz=self.noise_density_ug.get(),
                enable_noise=self.enable_noise.get(),
                sample_rate_hz=self.sample_rate_hz.get(),
            )
            self.latest_array_dfs = array_dfs
            self.latest_sensor_positions = sensor_positions

            # ── Cross-correlation speed estimate (S1 → S2) ─────────────────
            if len(array_dfs) >= 2:
                dt = 1.0 / self.sample_rate_hz.get()
                speed_est, lag_s, lags, corr = estimate_speed_xcorr(
                    array_dfs[0]["acceleration_g"].to_numpy(),
                    array_dfs[1]["acceleration_g"].to_numpy(),
                    dt,
                    spacing,
                )
                self.latest_speed_estimate = speed_est
                self.latest_xcorr = (lags, corr, lag_s)
            else:
                self.latest_speed_estimate = None
                self.latest_xcorr = None

            # ── Event detection on S1 ───────────────────────────────────────
            rms_vals, threshold, event_mask = detect_event(
                array_dfs[0]["acceleration_g"].to_numpy(),
                self.sample_rate_hz.get(),
                window_s=self.rms_window_ms.get() / 1000.0,
                threshold_multiplier=self.detection_threshold_mult.get(),
            )
            self.latest_event = (rms_vals, threshold, event_mask)

            self._update_plots(df, params)
            self._update_summary(df, params)

        except Exception as error:
            messagebox.showerror(
                "Simulation Error",
                f"Could not run simulation:\n\n{error}"
            )

    def _update_plots(self, df, params):
        for row in self.axes:
            for ax in row:
                ax.clear()

        _COLORS = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple"]

        # (0,0) Tire load at S1 reference position
        self.axes[0][0].plot(df["time_s"], df["force_n"], color="steelblue", linewidth=1.0)
        self.axes[0][0].set_title("Tire Load at S1 (reference)", fontsize=9)
        self.axes[0][0].set_ylabel("Force [N]")
        self.axes[0][0].grid(True)

        # (0,1) Asphalt displacement at S1
        self.axes[0][1].plot(df["time_s"], df["displacement_mm"], color="darkorange", linewidth=1.0)
        self.axes[0][1].set_title("Asphalt Displacement at S1", fontsize=9)
        self.axes[0][1].set_ylabel("Disp. [mm]")
        self.axes[0][1].grid(True)

        # (1,0) Sensor array – all signals overlaid
        if self.latest_array_dfs:
            for i, sdf in enumerate(self.latest_array_dfs):
                lbl = f"S{i + 1}  x={self.latest_sensor_positions[i]:.1f} m"
                self.axes[1][0].plot(
                    sdf["time_s"], sdf["acceleration_g"],
                    color=_COLORS[i % len(_COLORS)], label=lbl,
                    alpha=0.85, linewidth=0.8,
                )
            self.axes[1][0].legend(fontsize=7, loc="upper right")
        self.axes[1][0].set_title("Sensor Array Acceleration (with ADXL362 noise)", fontsize=9)
        self.axes[1][0].set_ylabel("Accel [g]")
        self.axes[1][0].grid(True)

        # (1,1) S1 clean vs noisy
        if self.latest_array_dfs:
            sdf0 = self.latest_array_dfs[0]
            if "acceleration_g_clean" in sdf0.columns:
                self.axes[1][1].plot(
                    sdf0["time_s"], sdf0["acceleration_g_clean"],
                    color="steelblue", label="Clean", linewidth=1.2,
                )
                self.axes[1][1].plot(
                    sdf0["time_s"], sdf0["acceleration_g"],
                    color="tomato", label="Noisy", alpha=0.55, linewidth=0.6,
                )
                self.axes[1][1].legend(fontsize=7)
        self.axes[1][1].set_title("S1: Clean vs. Noisy Signal", fontsize=9)
        self.axes[1][1].set_ylabel("Accel [g]")
        self.axes[1][1].grid(True)

        # (2,0) Spectrogram (STFT) of S1
        if self.latest_array_dfs:
            accel_s1 = self.latest_array_dfs[0]["acceleration_g"].to_numpy()
            f_spec, t_spec, Sxx = compute_spectrogram(accel_s1, self.sample_rate_hz.get())
            f_mask = f_spec <= 100.0
            self.axes[2][0].pcolormesh(
                t_spec, f_spec[f_mask],
                10.0 * np.log10(Sxx[f_mask] + 1e-30),
                shading="auto", cmap="inferno",
            )
            self.axes[2][0].set_title("S1 Spectrogram (STFT, 0–100 Hz)", fontsize=9)
            self.axes[2][0].set_ylabel("Freq [Hz]")
            self.axes[2][0].set_xlabel("Time [s]")

        # (2,1) Windowed RMS + event detection
        if self.latest_event is not None and self.latest_array_dfs:
            rms_v, thr, ev_mask = self.latest_event
            t_arr = self.latest_array_dfs[0]["time_s"].to_numpy()
            self.axes[2][1].plot(t_arr, rms_v, color="steelblue", linewidth=1.0, label="RMS")
            self.axes[2][1].axhline(thr, color="red", linestyle="--", linewidth=1.0, label="Threshold")
            self.axes[2][1].fill_between(t_arr, 0, rms_v, where=ev_mask, color="red", alpha=0.25, label="Event")
            self.axes[2][1].legend(fontsize=7)
        self.axes[2][1].set_title("S1 Event Detection (Windowed RMS)", fontsize=9)
        self.axes[2][1].set_ylabel("RMS [g]")
        self.axes[2][1].set_xlabel("Time [s]")
        self.axes[2][1].grid(True)

        self.figure.suptitle(
            "Asphalt Vibration Simulation — Interactive Model",
            fontsize=13, fontweight="bold",
        )
        self.figure.tight_layout(rect=[0, 0, 1, 0.96])
        self.canvas.draw()

    def _update_summary(self, df, params):
        # Use S1 noisy signal for metrics when available
        if self.latest_array_dfs:
            s1 = self.latest_array_dfs[0]
            accel = s1["acceleration_g"].to_numpy()
            clean = s1.get("acceleration_g_clean", s1["acceleration_g"]).to_numpy()
        else:
            accel = df["acceleration_g"].to_numpy()
            clean = accel

        peak_force_n = df["force_n"].max()
        peak_disp_mm = df["displacement_mm"].abs().max()
        peak_accel_g = np.abs(accel).max()
        rms_accel_g = np.sqrt(np.mean(accel ** 2))

        freqs_arr = np.fft.rfftfreq(len(clean), d=1.0 / self.sample_rate_hz.get())
        spec = np.abs(np.fft.rfft(clean - np.mean(clean)))
        dom_freq = freqs_arr[np.argmax(spec[1:]) + 1] if len(freqs_arr) > 1 else 0.0

        # Speed estimate
        if self.latest_speed_estimate is not None and self.latest_speed_estimate > 0:
            v_km = self.latest_speed_estimate * 3.6
            lag_ms = self.latest_xcorr[2] * 1000 if self.latest_xcorr else 0
            speed_line = f"{self.latest_speed_estimate:.2f} m/s  ({v_km:.1f} km/h)  lag={lag_ms:.1f} ms"
        else:
            speed_line = "N/A"

        # Event detection
        event_line = "No event detected"
        if self.latest_event is not None and self.latest_array_dfs:
            _, _, ev_mask = self.latest_event
            if ev_mask.any():
                t_arr = self.latest_array_dfs[0]["time_s"].to_numpy()
                t_start = t_arr[np.argmax(ev_mask)]
                t_end = t_arr[len(ev_mask) - 1 - np.argmax(ev_mask[::-1])]
                dur_ms = (t_end - t_start) * 1000
                event_line = f"t={t_start:.2f}–{t_end:.2f} s  ({dur_ms:.0f} ms)"

        summary = (
            "S1 Results\n"
            "-------------------------\n"
            f"Peak Force:       {peak_force_n:,.1f} N\n"
            f"Peak Disp.:       {peak_disp_mm:.6f} mm\n"
            f"Peak Accel.:      {peak_accel_g:.6f} g\n"
            f"RMS Accel.:       {rms_accel_g:.6f} g\n"
            f"Dominant Freq.:   {dom_freq:.2f} Hz\n"
            "\n"
            "Array\n"
            "-------------------------\n"
            f"Est. Speed:       {speed_line}\n"
            f"Event:            {event_line}\n"
            "\n"
            "Model\n"
            "-------------------------\n"
            f"Asphalt E':       {params['e_asphalt_pa'] / 1e9:.2f} GPa\n"
            f"Natural Freq.:    {params['natural_frequency_hz']:.2f} Hz\n"
            f"k_eq:             {params['k_eq_n_m']:.3e} N/m\n"
            f"c_eq:             {params['c_eq_n_s_m']:.3e} N·s/m\n"
        )
        self.summary_label.config(text=summary)

    def save_csv(self):
        if self.latest_df is None:
            messagebox.showwarning(
                "No Data",
                "Run the simulation before saving."
            )
            return

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "asphalt_vibration_simulation_gui.csv")
        self.latest_df.to_csv(output_path, index=False)

        messagebox.showinfo(
            "CSV Saved",
            f"Simulation data saved to:\n{output_path}"
        )

    def export_json(self):
        if not self.latest_array_dfs:
            messagebox.showwarning("No Data", "Run the simulation before exporting.")
            return

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"dataset_{timestamp}.json")

        speed = self.latest_speed_estimate or 0.0
        ev_mask = self.latest_event[2] if self.latest_event is not None else np.array([], dtype=bool)

        export_json_dataset(
            sensor_dfs=self.latest_array_dfs,
            vehicle_config=VehicleConfig(
                vehicle_mass_kg=self.vehicle_mass_kg.get(),
                speed_m_s=self.speed_kmh.get() / 3.6,
                num_axles=int(self.num_axles.get()),
                axle_spacing_m=self.axle_spacing_m.get(),
                track_width_m=1.6,
                lateral_offset_m=self.lateral_offset_m.get(),
                influence_sigma_x_m=self.sigma_x_m.get(),
                influence_sigma_y_m=self.sigma_y_m.get(),
                dynamic_load_ratio=self.dynamic_load_ratio_percent.get() / 100.0,
                dynamic_load_frequency_hz=self.dynamic_load_frequency_hz.get(),
                include_opposite_wheels=self.include_opposite_wheels.get(),
            ),
            asphalt_config=AsphaltModelConfig(
                asphalt_thickness_m=self.asphalt_thickness_cm.get() / 100.0,
                asphalt_density_kg_m3=2300.0,
                poisson_ratio=0.35,
                temperature_c=self.temperature_c.get(),
                effective_radius_m=self.effective_radius_m.get(),
                damping_ratio=self.damping_ratio.get(),
                subgrade_stiffness_n_m3=self.subgrade_stiffness_mn_m3.get() * 1e6,
                housing_gain=self.housing_gain.get(),
            ),
            event_mask=ev_mask,
            estimated_speed_ms=speed,
            vehicle_class=self.vehicle_class.get(),
            output_path=output_path,
        )

        messagebox.showinfo("JSON Exported", f"Dataset saved to:\n{output_path}")

    def _get_config_dict(self) -> dict:
        """Collect all control values into a serialisable dictionary."""
        return {
            "asphalt": {
                "temperature_c":            self.temperature_c.get(),
                "thickness_cm":             self.asphalt_thickness_cm.get(),
                "effective_radius_m":        self.effective_radius_m.get(),
                "damping_ratio":             self.damping_ratio.get(),
                "subgrade_stiffness_mn_m3":  self.subgrade_stiffness_mn_m3.get(),
            },
            "vehicle": {
                "vehicle_mass_kg":           self.vehicle_mass_kg.get(),
                "speed_kmh":                 self.speed_kmh.get(),
                "num_axles":                 int(self.num_axles.get()),
                "axle_spacing_m":            self.axle_spacing_m.get(),
                "lateral_offset_m":          self.lateral_offset_m.get(),
                "include_opposite_wheels":   self.include_opposite_wheels.get(),
            },
            "tire_load": {
                "dynamic_load_ratio_percent": self.dynamic_load_ratio_percent.get(),
                "dynamic_load_frequency_hz":  self.dynamic_load_frequency_hz.get(),
                "sigma_x_m":                  self.sigma_x_m.get(),
                "sigma_y_m":                  self.sigma_y_m.get(),
            },
            "sensor_array": {
                "num_sensors":              int(self.num_sensors.get()),
                "sensor_spacing_m":         self.sensor_spacing_m.get(),
                "enable_noise":             self.enable_noise.get(),
                "noise_density_ug":         self.noise_density_ug.get(),
                "rms_window_ms":            self.rms_window_ms.get(),
                "detection_threshold_mult": self.detection_threshold_mult.get(),
                "vehicle_class":            self.vehicle_class.get(),
            },
            "simulation": {
                "housing_gain":   self.housing_gain.get(),
                "sample_rate_hz": self.sample_rate_hz.get(),
            },
        }

    def _apply_config_dict(self, cfg: dict) -> None:
        """Apply a previously saved config dictionary to all control variables."""
        a = cfg.get("asphalt", {})
        self.temperature_c.set(a.get("temperature_c",           self.temperature_c.get()))
        self.asphalt_thickness_cm.set(a.get("thickness_cm",    self.asphalt_thickness_cm.get()))
        self.effective_radius_m.set(a.get("effective_radius_m", self.effective_radius_m.get()))
        self.damping_ratio.set(a.get("damping_ratio",           self.damping_ratio.get()))
        self.subgrade_stiffness_mn_m3.set(a.get("subgrade_stiffness_mn_m3", self.subgrade_stiffness_mn_m3.get()))

        v = cfg.get("vehicle", {})
        self.vehicle_mass_kg.set(v.get("vehicle_mass_kg",         self.vehicle_mass_kg.get()))
        self.speed_kmh.set(v.get("speed_kmh",                     self.speed_kmh.get()))
        self.num_axles.set(int(v.get("num_axles",                 self.num_axles.get())))
        self.axle_spacing_m.set(v.get("axle_spacing_m",           self.axle_spacing_m.get()))
        self.lateral_offset_m.set(v.get("lateral_offset_m",       self.lateral_offset_m.get()))
        self.include_opposite_wheels.set(v.get("include_opposite_wheels", self.include_opposite_wheels.get()))

        t = cfg.get("tire_load", {})
        self.dynamic_load_ratio_percent.set(t.get("dynamic_load_ratio_percent", self.dynamic_load_ratio_percent.get()))
        self.dynamic_load_frequency_hz.set(t.get("dynamic_load_frequency_hz",   self.dynamic_load_frequency_hz.get()))
        self.sigma_x_m.set(t.get("sigma_x_m", self.sigma_x_m.get()))
        self.sigma_y_m.set(t.get("sigma_y_m", self.sigma_y_m.get()))

        sa = cfg.get("sensor_array", {})
        self.num_sensors.set(int(sa.get("num_sensors",          self.num_sensors.get())))
        self.sensor_spacing_m.set(sa.get("sensor_spacing_m",    self.sensor_spacing_m.get()))
        self.enable_noise.set(sa.get("enable_noise",            self.enable_noise.get()))
        self.noise_density_ug.set(sa.get("noise_density_ug",    self.noise_density_ug.get()))
        self.rms_window_ms.set(sa.get("rms_window_ms",          self.rms_window_ms.get()))
        self.detection_threshold_mult.set(sa.get("detection_threshold_mult", self.detection_threshold_mult.get()))
        self.vehicle_class.set(sa.get("vehicle_class",          self.vehicle_class.get()))

        s = cfg.get("simulation", {})
        self.housing_gain.set(s.get("housing_gain",   self.housing_gain.get()))
        self.sample_rate_hz.set(s.get("sample_rate_hz", self.sample_rate_hz.get()))

    def save_config(self) -> None:
        """Save all control values to a JSON file chosen by the user."""
        os.makedirs("configs", exist_ok=True)
        default_name = "config_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        path = filedialog.asksaveasfilename(
            title="Save Configuration",
            initialdir=os.path.abspath("configs"),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self._get_config_dict(), fh, indent=2)
        messagebox.showinfo("Config Saved", f"Configuration saved to:\n{path}")

    def load_config(self) -> None:
        """Load control values from a previously saved JSON config file."""
        path = filedialog.askopenfilename(
            title="Load Configuration",
            initialdir=os.path.abspath("configs") if os.path.isdir("configs") else ".",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            self._apply_config_dict(cfg)
            self.update_simulation()
            messagebox.showinfo("Config Loaded", f"Configuration loaded from:\n{path}")
        except Exception as err:
            messagebox.showerror("Load Error", f"Could not load configuration:\n\n{err}")


def main():
    root = tk.Tk()
    app = AsphaltVibrationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
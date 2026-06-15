/**
 * Smart Road Reflector — 3D Site Visualization (Three.js, ES module)
 * ------------------------------------------------------------------
 * Builds a simplified 3D model of the East Liberty office campus from the site
 * config (building, driveway, parking, sensors) and renders live updates driven
 * by WebSocket events: sensor state colors, vehicle motion along paths, vibration
 * wave pulses when vehicles pass a reflector, and alert markers.
 *
 * Coordinate mapping: config meters (x along driveway, y across lot) ->
 * three.js (x = x_m, y = elevation, z = -y_m). 1 unit = 1 meter.
 *
 * Three.js is loaded via an import map in index.html (CDN, no build step).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const SENSOR_COLORS = {
  ok: 0x35d07f,
  warning: 0xffb020,
  critical: 0xff4d4f,
  offline: 0x8893a5,
};

function m2v(x, y, z = 0) {
  return new THREE.Vector3(x, z, -y);
}

export class SiteScene {
  constructor(container) {
    this.container = container;
    this.sensors = new Map();   // device_id -> { mesh, ring, role }
    this.vehicles = [];         // active animated vehicles
    this.alertMarkers = [];
    this.pulses = [];
    this.pathsById = {};
    this.clock = new THREE.Clock();
    this._initRenderer();
    this._initScene();
    this._animate = this._animate.bind(this);
    window.addEventListener("resize", () => this._onResize());
    this._animate();
  }

  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    this.renderer.shadowMap.enabled = true;
    this.container.appendChild(this.renderer.domElement);
  }

  _initScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0d1117);
    this.scene.fog = new THREE.Fog(0x0d1117, 180, 320);

    this.camera = new THREE.PerspectiveCamera(
      55,
      this.container.clientWidth / this.container.clientHeight,
      0.1,
      1000
    );
    this.camera.position.set(40, 80, 120);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(55, 0, 0);

    const hemi = new THREE.HemisphereLight(0xbcd6ff, 0x202830, 0.9);
    this.scene.add(hemi);
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(60, 120, 40);
    dir.castShadow = true;
    this.scene.add(dir);

    // Ground plane (grass).
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 400),
      new THREE.MeshStandardMaterial({ color: 0x16331f })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(55, -0.05, 0);
    ground.receiveShadow = true;
    this.scene.add(ground);
  }

  /** Build static site geometry from the backend site config. */
  build(config) {
    this.config = config;
    (config.vehicle_paths || []).forEach((p) => (this.pathsById[p.path_id] = p));

    this._buildSegments(config.road_segments || []);
    this._buildParking(config.parking_zones || []);
    this._buildBuilding(config.building);
    this._buildPedestrian(config.pedestrian_zones || []);
    this._buildSensors(config.sensors || []);
    this._frameSite(config);
  }

  _buildSegments(segments) {
    const mat = new THREE.MeshStandardMaterial({ color: 0x2b3340, roughness: 0.95 });
    segments.forEach((seg) => {
      const pts = seg.polyline_m;
      const w = seg.width_m || 6;
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i];
        const b = pts[i + 1];
        const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const geo = new THREE.BoxGeometry(len, 0.12, w);
        const mesh = new THREE.Mesh(geo, mat);
        const mid = m2v((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.06);
        mesh.position.copy(mid);
        mesh.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0]);
        mesh.receiveShadow = true;
        this.scene.add(mesh);
      }
    });
  }

  _buildParking(zones) {
    const mat = new THREE.MeshStandardMaterial({ color: 0x262d38, roughness: 1 });
    const lineMat = new THREE.LineBasicMaterial({ color: 0x9fb3c8 });
    zones.forEach((z) => {
      const w = z.space_size_m.width;
      const d = z.space_size_m.depth;
      const totalW = z.spaces_per_row * w;
      const slab = new THREE.Mesh(
        new THREE.BoxGeometry(totalW, 0.1, d * z.rows + 2),
        mat
      );
      slab.position.copy(m2v(z.anchor_m.x, z.anchor_m.y, 0.05));
      this.scene.add(slab);
      // Parking space markings.
      for (let r = 0; r < z.rows; r++) {
        for (let s = 0; s <= z.spaces_per_row; s++) {
          const x = z.anchor_m.x - totalW / 2 + s * w;
          const y0 = z.anchor_m.y - d / 2 + r * d - (z.rows - 1) * d / 2;
          const g = new THREE.BufferGeometry().setFromPoints([
            m2v(x, y0, 0.11),
            m2v(x, y0 + d, 0.11),
          ]);
          this.scene.add(new THREE.Line(g, lineMat));
        }
      }
    });
  }

  _buildBuilding(b) {
    if (!b) return;
    const geo = new THREE.BoxGeometry(b.footprint_m.width_x, b.height_m, b.footprint_m.depth_y);
    const mat = new THREE.MeshStandardMaterial({ color: 0x4a5568, roughness: 0.7 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(
      m2v(
        b.footprint_m.x + b.footprint_m.width_x / 2,
        b.footprint_m.y + b.footprint_m.depth_y / 2,
        b.height_m / 2
      )
    );
    mesh.rotation.y = -THREE.MathUtils.degToRad(b.footprint_m.rotation_deg || 0);
    mesh.castShadow = true;
    this.scene.add(mesh);

    const roof = new THREE.Mesh(
      new THREE.BoxGeometry(b.footprint_m.width_x + 1, 0.4, b.footprint_m.depth_y + 1),
      new THREE.MeshStandardMaterial({ color: 0x2f3a4a })
    );
    roof.position.copy(mesh.position.clone().setY(b.height_m));
    roof.rotation.y = mesh.rotation.y;
    this.scene.add(roof);
  }

  _buildPedestrian(zones) {
    const mat = new THREE.MeshStandardMaterial({ color: 0xd9e2ec, roughness: 1 });
    zones.forEach((z) => {
      const a = z.polyline_m[0];
      const b = z.polyline_m[1];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const stripes = Math.max(3, Math.floor(len / 0.8));
      for (let i = 0; i < stripes; i += 2) {
        const t = i / stripes;
        const x = a[0] + (b[0] - a[0]) * t;
        const y = a[1] + (b[1] - a[1]) * t;
        const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.13, z.width_m), mat);
        stripe.position.copy(m2v(x, y, 0.07));
        this.scene.add(stripe);
      }
    });
  }

  _buildSensors(sensors) {
    sensors.forEach((s) => {
      const p = s.position_m;
      const post = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.18, 0.9, 12),
        new THREE.MeshStandardMaterial({ color: 0x6b7785 })
      );
      post.position.copy(m2v(p.x, p.y, 0.45));
      this.scene.add(post);

      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.55, 18, 18),
        new THREE.MeshStandardMaterial({
          color: SENSOR_COLORS.offline,
          emissive: SENSOR_COLORS.offline,
          emissiveIntensity: 0.6,
        })
      );
      head.position.copy(m2v(p.x, p.y, 1.1));
      head.userData.deviceId = s.device_id;
      this.scene.add(head);

      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.7, 0.85, 32),
        new THREE.MeshBasicMaterial({
          color: SENSOR_COLORS.ok,
          transparent: true,
          opacity: 0,
          side: THREE.DoubleSide,
        })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.copy(m2v(p.x, p.y, 0.13));
      this.scene.add(ring);

      this.sensors.set(s.device_id, { mesh: head, ring, role: s.role });
    });
  }

  _frameSite(config) {
    const b = config.site.coordinate_system.bounds_m;
    const cx = (b.x_min + b.x_max) / 2;
    this.controls.target.set(cx, 0, 0);
    this.camera.position.set(cx - 30, 70, 95);
  }

  // ---------------------------- live updates ---------------------------- //
  setSensorState(deviceId, telemetry) {
    const node = this.sensors.get(deviceId);
    if (!node) return;
    let state = "ok";
    if (String(telemetry.device_status) === "offline") state = "offline";
    else if (telemetry.surface_water || (telemetry.accel_peak_g || 0) >= 1.2)
      state = "critical";
    else if ((telemetry.battery_pct ?? 100) <= 20) state = "warning";
    const color = SENSOR_COLORS[state] ?? SENSOR_COLORS.ok;
    node.mesh.material.color.setHex(color);
    node.mesh.material.emissive.setHex(color);
    if (telemetry.surface_water) this.addAlertMarker(deviceId, 0x3fa9f5);
  }

  pulseSensor(deviceId, intensity = 1) {
    const node = this.sensors.get(deviceId);
    if (!node) return;
    this.pulses.push({ ring: node.ring, t: 0, intensity });
  }

  spawnVehicle(event) {
    const path = this.pathsById[event.path_id];
    if (!path) return;
    const pts = this._resample(path.waypoints_m, 1.0);
    const isHeavy = ["delivery_van", "maintenance_truck", "large_vehicle"].includes(
      event.vehicle_class
    );
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(isHeavy ? 4.5 : 3.6, 1.4, 1.8),
      new THREE.MeshStandardMaterial({
        color: event.event_type === "abnormal_vibration_event" ? 0xff4d4f : 0xe2e8f0,
      })
    );
    body.castShadow = true;
    this.scene.add(body);
    const speed = Math.max(5, event.estimated_speed_kmh || 15) / 3.6;
    this.vehicles.push({ mesh: body, pts, idx: 0, speed, carry: 0 });
  }

  addAlertMarker(deviceId, color = 0xff4d4f) {
    const node = this.sensors.get(deviceId);
    const pos = node
      ? node.mesh.position.clone().setY(3)
      : new THREE.Vector3(60, 3, 0);
    const m = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.8),
      new THREE.MeshBasicMaterial({ color })
    );
    m.position.copy(pos);
    m.userData.born = performance.now();
    this.scene.add(m);
    this.alertMarkers.push(m);
  }

  _resample(waypoints, step) {
    const pts = [];
    for (let i = 0; i < waypoints.length - 1; i++) {
      const a = waypoints[i];
      const b = waypoints[i + 1];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const n = Math.max(1, Math.floor(len / step));
      for (let k = 0; k < n; k++) {
        const t = k / n;
        pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    pts.push(waypoints[waypoints.length - 1]);
    return pts;
  }

  _animate() {
    requestAnimationFrame(this._animate);
    const dt = Math.min(this.clock.getDelta(), 0.05);

    // Vehicles.
    for (let i = this.vehicles.length - 1; i >= 0; i--) {
      const v = this.vehicles[i];
      v.carry += v.speed * dt;
      while (v.carry >= 1 && v.idx < v.pts.length - 1) {
        v.idx++;
        v.carry -= 1;
      }
      const p = v.pts[Math.min(v.idx, v.pts.length - 1)];
      const next = v.pts[Math.min(v.idx + 1, v.pts.length - 1)];
      v.mesh.position.copy(m2v(p[0], p[1], 0.9));
      v.mesh.rotation.y = -Math.atan2(next[1] - p[1], next[0] - p[0]);
      if (v.idx >= v.pts.length - 1) {
        this.scene.remove(v.mesh);
        this.vehicles.splice(i, 1);
      }
    }

    // Vibration pulses.
    for (let i = this.pulses.length - 1; i >= 0; i--) {
      const p = this.pulses[i];
      p.t += dt * 1.6;
      const s = 1 + p.t * 6 * p.intensity;
      p.ring.scale.set(s, s, s);
      p.ring.material.opacity = Math.max(0, 0.8 - p.t);
      if (p.t >= 0.8) {
        p.ring.material.opacity = 0;
        p.ring.scale.set(1, 1, 1);
        this.pulses.splice(i, 1);
      }
    }

    // Alert markers (float + expire after 12s).
    const now = performance.now();
    for (let i = this.alertMarkers.length - 1; i >= 0; i--) {
      const m = this.alertMarkers[i];
      m.rotation.y += dt * 2;
      m.position.y = 3 + Math.sin(now / 300) * 0.3;
      if (now - m.userData.born > 12000) {
        this.scene.remove(m);
        this.alertMarkers.splice(i, 1);
      }
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  _onResize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }
}

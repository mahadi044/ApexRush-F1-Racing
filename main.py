
from panda3d.core import loadPrcFileData

loadPrcFileData("", "audio-library-name p3openal_audio")
loadPrcFileData("", "audio-active true")
loadPrcFileData("", "audio-volume 1.0")
loadPrcFileData("", "audio-cache-limit 50")

from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.DirectGui import DirectButton
from panda3d.core import (
    AmbientLight, DirectionalLight, CardMaker, Geom, GeomNode,
    GeomTriangles, GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, Vec3, Vec4, LineSegs, TextNode,
    ClockObject, TransparencyAttrib
)
import math
import os
import random
import struct
import tempfile
import wave


class ApexRush(ShowBase):

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.40, 0.62, 0.78, 1)
        self.setFrameRateMeter(False)

        self.outer_x, self.outer_y = 38.5, 52.5
        self.inner_x, self.inner_y = 25.5, 39.5
        self.center_x = (self.outer_x + self.inner_x) / 2
        self.center_y = (self.outer_y + self.inner_y) / 2

        self.total_laps = 3
        self.race_started = False
        self.paused = False
        self.race_finished = False
        self.player_finished = False
        self.countdown = 0.0
        self.countdown_active = False
        self.go_display_timer = 0.0
        self.race_time = 0.0
        self.lap_start_time = 0.0
        self.best_lap = None
        self.player_lap = 0
        self.player_lap_armed = False
        self.previous_player_x = -32.0
        self.previous_player_y = -8.0
        self.player_finish_time = None
        self.finish_order = []
        self.collision_timer = 0.0
        self.collision_cooldown = 0.0

        self.speed = 0.0
        self.max_speed = 38.0
        self.max_reverse = 8.0
        self.acceleration = 13.0
        self.braking = 25.0
        self.drag = 3.0
        self.steering_rate = 48.0
        self.current_dt = 0.0

        self.keys = {
            "accelerate": False,
            "brake": False,
            "left": False,
            "right": False
        }

        self.smoke_particles = []
        self.smoke_timer = 0.0
        self.max_smoke_particles = 34
        self.randomizer = random.Random()

        self.setup_audio()
        self.setup_lighting()
        self.make_ground()
        self.make_track()
        self.make_trackside_details()
        self.make_car()
        self.make_ai_cars()
        self.setup_hud()
        self.setup_menu()
        self.setup_controls()

        self.camera_distance = 12.0
        self.camera_height = 5.5
        self.update_camera(1.0)
        self.taskMgr.add(self.update, "game_update")

    # AUDIO

    def _make_sound_file(self, path, kind):
        rate = 22050
        durations = {
            "engine": 2.0,
            "tire": 0.7,
            "collision": 0.45,
            "countdown": 0.22,
            "go": 0.65
        }
        total = int(rate * durations[kind])
        samples = bytearray()
        rng = random.Random(41)

        for i in range(total):
            t = i / rate

            if kind == "engine":
                envelope = 0.65 + 0.12 * math.sin(2 * math.pi * 2 * t)
                value = envelope * (
                    0.48 * math.sin(2 * math.pi * 75 * t)
                    + 0.25 * math.sin(2 * math.pi * 150 * t)
                    + 0.12 * math.sin(2 * math.pi * 225 * t)
                )
            elif kind == "tire":
                fade = min(1.0, t * 15) * max(
                    0.0, 1 - t / durations[kind]
                )
                value = fade * (
                    0.55 * rng.uniform(-1, 1)
                    + 0.20 * math.sin(2 * math.pi * 1700 * t)
                )
            elif kind == "collision":
                fade = math.exp(-9 * t)
                value = fade * (
                    0.75 * math.sin(2 * math.pi * 75 * t)
                    + 0.30 * math.sin(2 * math.pi * 130 * t)
                    + 0.15 * rng.uniform(-1, 1)
                )
            elif kind == "countdown":
                value = 0.65 * math.sin(2 * math.pi * 880 * t)
                value *= min(1.0, t * 100) * max(
                    0.0, 1 - t / durations[kind]
                )
            else:
                value = 0.60 * (
                    math.sin(2 * math.pi * 1046.5 * t)
                    + 0.45 * math.sin(2 * math.pi * 1318.5 * t)
                )
                value *= min(1.0, t * 30) * max(
                    0.0, 1 - t / durations[kind]
                )

            sample = int(max(-1.0, min(1.0, value)) * 20000)
            samples.extend(struct.pack("<h", sample))

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(samples)

    def setup_audio(self):
        self.audio_enabled = False
        self.engine_sound = None
        self.tire_sound = None
        self.collision_sound = None
        self.countdown_sound = None
        self.go_sound = None
        self.engine_playing = False
        self.tire_playing = False
        self.last_countdown_number = None

        try:
            self.enableSound()
            self.enableMusic()

            if not self.sfxManagerList:
                raise RuntimeError("No available SFX manager")

            folder = os.path.join(tempfile.gettempdir(), "apexrush_audio")
            os.makedirs(folder, exist_ok=True)
            sounds = {}

            for kind in ("engine", "tire", "collision", "countdown", "go"):
                path = os.path.join(folder, kind + ".wav")
                self._make_sound_file(path, kind)
                sound = self.loader.loadSfx(path)

                if sound is None:
                    raise RuntimeError(f"Could not load {path}")

                sound.setVolume(1.0)
                sounds[kind] = sound
                print("Loaded sound:", kind)

            self.engine_sound = sounds["engine"]
            self.engine_sound.setLoop(True)
            self.engine_sound.setVolume(0.40)

            self.tire_sound = sounds["tire"]
            self.tire_sound.setLoop(True)
            self.tire_sound.setVolume(0.45)

            self.collision_sound = sounds["collision"]
            self.collision_sound.setVolume(0.85)

            self.countdown_sound = sounds["countdown"]
            self.countdown_sound.setVolume(0.80)

            self.go_sound = sounds["go"]
            self.go_sound.setVolume(1.0)

            self.audio_enabled = True
            print("APEXRUSH AUDIO: READY")
            self.taskMgr.doMethodLater(
                1.5, self.test_audio, "apexrush-audio-test"
            )

        except Exception as exc:
            self.audio_enabled = False
            print("AUDIO INITIALIZATION FAILED:", repr(exc))
            print("Game will continue without sound.")

    def test_audio(self, task):
        if self.audio_enabled and self.go_sound is not None:
            try:
                self.go_sound.stop()
                self.go_sound.play()
                print("GO sound playback requested")
            except Exception as exc:
                print("GO SOUND ERROR:", repr(exc))
        return task.done

    def play_game_sound(self, sound):
        if not self.audio_enabled or sound is None:
            return
        try:
            sound.stop()
            sound.play()
        except Exception as exc:
            print("Could not play sound:", repr(exc))

    def update_audio(self):
        if not self.audio_enabled:
            return

        driving = (
            self.race_started and not self.paused
            and not self.race_finished and not self.player_finished
        )
        engine_needed = driving and abs(self.speed) > 0.5

        if engine_needed:
            if not self.engine_playing:
                self.engine_sound.setVolume(0.40)
                self.engine_sound.play()
                self.engine_playing = True

            pitch = 0.75 + min(abs(self.speed) / self.max_speed, 1.0) * 0.85
            self.engine_sound.setPlayRate(pitch)
        elif self.engine_playing:
            self.engine_sound.stop()
            self.engine_playing = False

        steering = self.keys["left"] or self.keys["right"]
        tire_needed = driving and steering and abs(self.speed) > 14.0

        if tire_needed and not self.tire_playing:
            self.tire_sound.setVolume(0.45)
            self.tire_sound.play()
            self.tire_playing = True
        elif not tire_needed and self.tire_playing:
            self.tire_sound.stop()
            self.tire_playing = False

    def stop_looping_audio(self):
        if self.engine_sound is not None:
            self.engine_sound.stop()
        if self.tire_sound is not None:
            self.tire_sound.stop()
        self.engine_playing = False
        self.tire_playing = False

    # LIGHTING AND ENVIRONMENT

    def setup_lighting(self):
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.62, 0.62, 0.65, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.95, 0.91, 0.84, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-35, -55, 0)
        self.render.setLight(sun_np)

    def make_ground(self):
        maker = CardMaker("ground")
        maker.setFrame(-180, 180, -180, 180)
        ground = self.render.attachNewNode(maker.generate())
        ground.setP(-90)
        ground.setZ(-0.15)
        ground.setColor(0.15, 0.39, 0.18, 1)
        ground.setTwoSided(True)

        rng = random.Random(17)
        for i in range(38):
            x = rng.uniform(-95, 95)
            y = rng.uniform(-105, 105)

            if (x / self.outer_x) ** 2 + (y / self.outer_y) ** 2 < 1.8:
                continue

            self.add_box(
                self.render, f"grass-patch-{i}",
                (x, y, -0.06),
                (rng.uniform(1.5, 4), rng.uniform(1.5, 4), 0.02),
                (0.19, 0.45, 0.20, 1)
            )

    def make_track(self):
        segments = 180
        fmt = GeomVertexFormat.getV3()
        data = GeomVertexData("track-ring", fmt, Geom.UHStatic)
        data.setNumRows(segments * 2)
        vertex = GeomVertexWriter(data, "vertex")

        for i in range(segments):
            angle = 2 * math.pi * i / segments
            vertex.addData3(
                self.outer_x * math.cos(angle),
                self.outer_y * math.sin(angle), 0.02
            )
            vertex.addData3(
                self.inner_x * math.cos(angle),
                self.inner_y * math.sin(angle), 0.02
            )

        tris = GeomTriangles(Geom.UHStatic)
        for i in range(segments):
            a = i * 2
            b = i * 2 + 1
            c = ((i + 1) % segments) * 2
            d = ((i + 1) % segments) * 2 + 1
            tris.addVertices(a, c, b)
            tris.addVertices(b, c, d)

        tris.closePrimitive()
        geom = Geom(data)
        geom.addPrimitive(tris)
        node = GeomNode("track-surface")
        node.addGeom(geom)
        track = self.render.attachNewNode(node)
        track.setColor(0.16, 0.17, 0.19, 1)
        track.setTwoSided(True)

        self.draw_ellipse(
            self.outer_x, self.outer_y,
            (0.95, 0.95, 0.92, 1), 0.22, 0.06
        )
        self.draw_ellipse(
            self.inner_x, self.inner_y,
            (0.95, 0.95, 0.92, 1), 0.22, 0.06
        )
        self.draw_ellipse(
            self.center_x, self.center_y,
            (0.96, 0.76, 0.10, 1), 0.10, 0.07, dashed=True
        )

        for i in range(48):
            angle = 2 * math.pi * i / 48
            x = (self.outer_x - 1.1) * math.cos(angle)
            y = (self.outer_y - 1.1) * math.sin(angle)
            color = (
                (0.88, 0.12, 0.10, 1)
                if i % 2 == 0 else (1, 1, 1, 1)
            )
            curb = self.add_box(
                self.render, f"curb-{i}", (x, y, 0.12),
                (0.65, 1.25, 0.12), color
            )
            curb.setH(-math.degrees(angle))

        squares = 12
        road_width = self.outer_x - self.inner_x
        square_width = road_width / squares

        for i in range(squares):
            color = (
                (1, 1, 1, 1)
                if i % 2 == 0 else (0.04, 0.04, 0.04, 1)
            )
            x = -self.outer_x + square_width * (i + 0.5)
            self.add_box(
                self.render, f"finish-checker-{i}",
                (x, 0, 0.10), (square_width / 2, 0.23, 0.035), color
            )

        self.draw_ellipse(
            self.inner_x * 0.68, self.inner_y * 0.68,
            (0.25, 0.55, 0.26, 1), 0.18, 0.09
        )
        self.draw_ellipse(
            self.outer_x + 2.0, self.outer_y + 2.0,
            (0.68, 0.70, 0.72, 1), 0.18, 0.22
        )

    def make_trackside_details(self):
        for side in (-1, 1):
            for i, x in enumerate((-22, 0, 22)):
                y = side * 59.5

                self.add_box(
                    self.render, f"grandstand-{side}-{i}",
                    (x, y, 1.0), (7.5, 1.4, 1.0),
                    (0.12, 0.15, 0.20, 1)
                )
                self.add_box(
                    self.render, f"stand-roof-{side}-{i}",
                    (x, y, 2.25), (8.0, 1.7, 0.12),
                    (0.85, 0.08, 0.06, 1)
                )
                self.add_box(
                    self.render, f"race-board-{side}-{i}",
                    (x, y - side * 1.6, 1.45),
                    (3.0, 0.12, 0.45),
                    (0.04, 0.08, 0.14, 1)
                )

        for i, x in enumerate((-44, -32, -20, 20, 32, 44)):
            for y in (-55.5, 55.5):
                self.add_box(
                    self.render, f"barrier-{i}-{y}",
                    (x, y, 0.45), (2.0, 0.25, 0.35),
                    (0.66, 0.69, 0.72, 1)
                )

    def draw_ellipse(self, rx, ry, color, thickness=0.1, z=0.05, dashed=False):
        lines = LineSegs("ellipse")
        lines.setThickness(thickness)
        lines.setColor(*color)
        steps = 180

        for i in range(steps):
            if dashed and (i // 5) % 2:
                continue
            a1 = 2 * math.pi * i / steps
            a2 = 2 * math.pi * (i + 1) / steps
            lines.moveTo(rx * math.cos(a1), ry * math.sin(a1), z)
            lines.drawTo(rx * math.cos(a2), ry * math.sin(a2), z)

        self.render.attachNewNode(lines.create())

    def add_box(self, parent, name, pos, scale, color):
        model = self.loader.loadModel("models/box")
        model.setName(name)
        model.reparentTo(parent)
        model.setPos(*pos)
        model.setScale(*scale)
        model.setColor(*color)
        model.setTwoSided(True)
        return model

    # CARS AND BRAKE LIGHTS

    def build_car(self, parent, color):
        car = self.render.attachNewNode("f1-car")

        self.add_box(car, "main-body", (0, 0, 0.18),
                     (0.58, 1.45, 0.22), color)
        self.add_box(car, "nose", (0, 1.35, 0.10),
                     (0.22, 0.90, 0.12), color)
        self.add_box(car, "cockpit", (0, 0.18, 0.43),
                     (0.34, 0.46, 0.20), (0.08, 0.09, 0.11, 1))
        self.add_box(car, "front-wing", (0, 2.05, 0.03),
                     (0.95, 0.15, 0.08), color)
        self.add_box(car, "rear-wing", (0, -1.25, 0.36),
                     (0.82, 0.15, 0.08), color)
        self.add_box(car, "rear-wing-post", (0, -1.12, 0.25),
                     (0.10, 0.13, 0.20), (0.12, 0.12, 0.13, 1))

        for x in (-0.57, 0.57):
            for y in (-0.95, 1.05):
                self.add_box(
                    car, "wheel", (x, y, 0.0),
                    (0.20, 0.36, 0.24), (0.035, 0.035, 0.04, 1)
                )

        brake_lights = []
        for x in (-0.34, 0.34):
            light = self.add_box(
                car, "brake-light", (x, -1.48, 0.34),
                (0.13, 0.07, 0.09), (0.30, 0.015, 0.015, 1)
            )
            brake_lights.append(light)

        car.setPythonTag("brake_lights", brake_lights)
        car.reparentTo(parent)
        return car

    def set_brake_lights(self, car, enabled):
        try:
            lights = car.getPythonTag("brake_lights")
        except Exception:
            return

        color = (
            (1.0, 0.015, 0.01, 1)
            if enabled else (0.30, 0.015, 0.015, 1)
        )

        for light in lights:
            light.setColor(*color)

    def make_car(self):
        self.car = self.build_car(self.render, (0.88, 0.08, 0.07, 1))
        self.car.setPos(-32, -8, 0.65)
        self.car.setH(0)

    def make_ai_cars(self):
        self.ai_cars = []
        configs = [
            (29.5, 43.0, math.pi + 0.25, 21.0, (0.06, 0.30, 0.95, 1)),
            (34.0, 48.0, math.pi + 0.48, 24.0, (1.0, 0.38, 0.04, 1)),
        ]

        for rx, ry, theta, speed, color in configs:
            car = self.build_car(self.render, color)
            ai = {
                "car": car, "base_rx": rx, "base_ry": ry,
                "rx": rx, "ry": ry, "theta": theta,
                "start_theta": theta, "base_speed": speed, "speed": speed,
                "lane_offset": 0.0, "target_offset": 0.0,
                "overtake_timer": 0.0, "overtaking": False,
                "overtake_cooldown": 0.0, "target_speed": speed,
                "skill": 0.92 if color[2] > 0.5 else 1.0,
                "lap": 0, "armed": False, "previous_x": 0.0,
                "previous_y": 0.0, "finished": False, "finish_time": None,
            }
            self.ai_cars.append(ai)
            self.update_ai_position(ai)
            ai["previous_x"] = car.getX()
            ai["previous_y"] = car.getY()

    def update_ai_position(self, ai):
        x = ai["rx"] * math.cos(ai["theta"])
        y = ai["ry"] * math.sin(ai["theta"])
        ai["car"].setPos(x, y, 0.65)
        dx = ai["rx"] * math.sin(ai["theta"])
        dy = -ai["ry"] * math.cos(ai["theta"])
        ai["car"].setH(math.degrees(math.atan2(-dx, dy)))

    def reset_ai(self):
        starts = [math.pi + 0.25, math.pi + 0.48]

        for ai, start in zip(self.ai_cars, starts):
            ai["theta"] = start
            ai["start_theta"] = start
            ai["rx"], ai["ry"] = ai["base_rx"], ai["base_ry"]
            ai["lap"] = 0
            ai["armed"] = False
            ai["finished"] = False
            ai["finish_time"] = None
            ai["lane_offset"] = 0.0
            ai["target_offset"] = 0.0
            ai["overtake_timer"] = 0.0
            ai["overtaking"] = False
            ai["overtake_cooldown"] = 0.0
            ai["target_speed"] = ai["base_speed"]
            ai["speed"] = ai["base_speed"]
            self.update_ai_position(ai)
            ai["previous_x"] = ai["car"].getX()
            ai["previous_y"] = ai["car"].getY()

    # SMOKE PARTICLES

    def create_smoke_particle(self, x, y, z):
        if len(self.smoke_particles) >= self.max_smoke_particles:
            return

        maker = CardMaker("tire-smoke")
        maker.setFrame(-0.5, 0.5, -0.5, 0.5)

        particle = self.render.attachNewNode(maker.generate())
        particle.setTransparency(TransparencyAttrib.MAlpha)
        particle.setBillboardPointEye()
        particle.setTwoSided(True)
        particle.setPos(x, y, z)
        particle.setScale(self.randomizer.uniform(0.40, 0.65))
        particle.setColor(0.78, 0.79, 0.81, 0.55)

        self.smoke_particles.append({
            "node": particle,
            "life": self.randomizer.uniform(0.65, 1.0),
            "max_life": 1.0,
            "vx": self.randomizer.uniform(-0.8, 0.8),
            "vy": self.randomizer.uniform(-0.8, 0.8),
            "vz": self.randomizer.uniform(0.35, 0.9),
            "size": self.randomizer.uniform(0.9, 1.6),
        })

    def update_smoke(self, dt):
        # FIX: smoke now appears when the player brakes.
        steering = self.keys["left"] or self.keys["right"]
        braking = self.keys["brake"]
        off_track = not self.is_on_track()

        drifting = abs(self.speed) > 15 and steering
        braking_smoke = braking and abs(self.speed) > 3

        smoke_needed = (
            self.race_started
            and not self.paused
            and not self.race_finished
            and not self.player_finished
            and abs(self.speed) > 3
            and (braking_smoke or drifting or off_track)
        )

        self.smoke_timer -= dt

        if smoke_needed and self.smoke_timer <= 0:
            if braking_smoke:
                self.smoke_timer = 0.035
            elif abs(self.speed) > 20:
                self.smoke_timer = 0.045
            else:
                self.smoke_timer = 0.07

            # Rear tyre locations, transformed into world coordinates.
            quat = self.car.getQuat(self.render)
            car_pos = self.car.getPos(self.render)

            for local_x in (-0.57, 0.57):
                offset = quat.xform(Vec3(local_x, -0.95, 0.0))
                p = car_pos + offset

                # Smoke floats just above the track.
                smoke_z = max(0.43, p.z - 0.18)
                self.create_smoke_particle(p.x, p.y, smoke_z)

        alive = []

        for item in self.smoke_particles:
            item["life"] -= dt
            node = item["node"]

            if item["life"] <= 0:
                node.removeNode()
                continue

            node.setPos(
                node.getX() + item["vx"] * dt,
                node.getY() + item["vy"] * dt,
                node.getZ() + item["vz"] * dt
            )

            node.setScale(node.getScale().x + dt * item["size"])

            alpha = max(0.0, min(0.55, item["life"] * 0.65))
            node.setColor(0.78, 0.79, 0.81, alpha)
            alive.append(item)

        self.smoke_particles = alive

    def clear_smoke(self):
        for item in self.smoke_particles:
            item["node"].removeNode()

        self.smoke_particles.clear()
        self.smoke_timer = 0.0

    # HUD AND MENU

    def setup_hud(self):
        self.hud = OnscreenText(
            text="", pos=(-1.28, 0.91), scale=0.048,
            fg=(1, 1, 1, 1), align=TextNode.ALeft,
            mayChange=True, shadow=(0, 0, 0, 0.8)
        )
        self.speed_text = OnscreenText(
            text="SPEED 000 km/h", pos=(1.20, -0.88), scale=0.055,
            fg=(1, 1, 1, 1), align=TextNode.ARight,
            mayChange=True, shadow=(0, 0, 0, 0.8)
        )
        self.status_text = OnscreenText(
            text="READY", pos=(0, 0.80), scale=0.07,
            fg=(1, 1, 1, 1), align=TextNode.ACenter,
            mayChange=True, shadow=(0, 0, 0, 0.8)
        )
        self.countdown_text = OnscreenText(
            text="", pos=(0, 0.05), scale=0.22,
            fg=(1, 0.92, 0.25, 1), align=TextNode.ACenter,
            mayChange=True, shadow=(0, 0, 0, 0.8)
        )
        self.results_text = OnscreenText(
            text="", pos=(0, 0.35), scale=0.065,
            fg=(1, 1, 1, 1), align=TextNode.ACenter,
            mayChange=True, shadow=(0, 0, 0, 0.9)
        )
        self.leaderboard_text = OnscreenText(
            text="LIVE STANDINGS", pos=(1.27, 0.67),
            scale=0.038, fg=(1, 1, 1, 1),
            align=TextNode.ARight, mayChange=True,
            shadow=(0, 0, 0, 0.9)
        )

        for widget in (
            self.hud, self.speed_text, self.status_text,
            self.countdown_text, self.results_text,
            self.leaderboard_text
        ):
            widget.hide()

    def setup_menu(self):
        self.title = OnscreenText(
            text="APEXRUSH", pos=(0, 0.48), scale=0.16,
            fg=(1, 0.14, 0.10, 1), align=TextNode.ACenter,
            shadow=(0, 0, 0, 0.7)
        )
        self.subtitle = OnscreenText(
            text="FORMULA RACING  •  3 LAPS  •  AI CHALLENGE",
            pos=(0, 0.32), scale=0.045,
            fg=(1, 1, 1, 1), align=TextNode.ACenter,
            shadow=(0, 0, 0, 0.7)
        )
        self.start_button = DirectButton(
            text="START RACE", scale=0.075, pos=(0, 0, 0.10),
            command=self.start_race,
            frameColor=(0.80, 0.08, 0.06, 1),
            text_fg=(1, 1, 1, 1), relief=1
        )
        self.quit_button = DirectButton(
            text="QUIT", scale=0.065, pos=(0, 0, -0.12),
            command=self.userExit,
            frameColor=(0.12, 0.14, 0.17, 1),
            text_fg=(1, 1, 1, 1), relief=1
        )
        self.menu_help = OnscreenText(
            text="W / UP Accelerate     S / DOWN Brake     A D / LEFT RIGHT Steer\n"
                 "P Pause     R Restart Race     ESC Quit",
            pos=(0, -0.38), scale=0.045,
            fg=(1, 1, 1, 1), align=TextNode.ACenter,
            shadow=(0, 0, 0, 0.7)
        )
        self.resume_button = DirectButton(
            text="RESUME", scale=0.07, pos=(0, 0, -0.05),
            command=self.toggle_pause,
            frameColor=(0.10, 0.38, 0.18, 1),
            text_fg=(1, 1, 1, 1), relief=1
        )
        self.resume_button.hide()

    def hide_menu(self):
        self.title.hide()
        self.subtitle.hide()
        self.start_button.hide()
        self.quit_button.hide()
        self.menu_help.hide()

    def show_menu(self):
        self.title.show()
        self.subtitle.show()
        self.start_button.show()
        self.quit_button.show()
        self.menu_help.show()

    def show_race_ui(self):
        self.hud.show()
        self.speed_text.show()
        self.status_text.show()
        self.leaderboard_text.show()

    # CONTROLS

    def setup_controls(self):
        for key in ("w", "arrow_up"):
            self.accept(key, self.set_key, ["accelerate", True])
        for key in ("w-up", "arrow_up-up"):
            self.accept(key, self.set_key, ["accelerate", False])
        for key in ("s", "arrow_down"):
            self.accept(key, self.set_key, ["brake", True])
        for key in ("s-up", "arrow_down-up"):
            self.accept(key, self.set_key, ["brake", False])
        for key in ("a", "arrow_left"):
            self.accept(key, self.set_key, ["left", True])
        for key in ("a-up", "arrow_left-up"):
            self.accept(key, self.set_key, ["left", False])
        for key in ("d", "arrow_right"):
            self.accept(key, self.set_key, ["right", True])
        for key in ("d-up", "arrow_right-up"):
            self.accept(key, self.set_key, ["right", False])

        self.accept("escape", self.userExit)
        self.accept("p", self.toggle_pause)
        self.accept("r", self.start_race)

    def set_key(self, key, value):
        self.keys[key] = value

    def start_race(self):
        self.stop_looping_audio()
        self.clear_smoke()
        self.paused = False
        self.race_started = False
        self.race_finished = False
        self.player_finished = False
        self.countdown_active = True
        self.countdown = 3.0
        self.last_countdown_number = None
        self.go_display_timer = 0.0
        self.race_time = 0.0
        self.lap_start_time = 0.0
        self.best_lap = None
        self.player_lap = 0
        self.player_lap_armed = False
        self.player_finish_time = None
        self.finish_order = []
        self.speed = 0.0

        self.car.setPos(-32, -8, 0.65)
        self.car.setH(0)
        self.previous_player_x = self.car.getX()
        self.previous_player_y = self.car.getY()
        self.reset_ai()

        self.keys = {
            "accelerate": False,
            "brake": False,
            "left": False,
            "right": False
        }

        self.set_brake_lights(self.car, False)
        self.hide_menu()
        self.resume_button.hide()
        self.show_race_ui()
        self.results_text.hide()
        self.countdown_text.setText("3")
        self.countdown_text.show()
        self.status_text.setText("GET READY")
        self.update_camera(1.0)

    def toggle_pause(self):
        if (
            self.countdown_active or self.race_finished
            or not self.race_started
        ):
            return

        self.paused = not self.paused

        if self.paused:
            self.status_text.setText("PAUSED")
            self.resume_button.show()
            self.stop_looping_audio()
            self.set_brake_lights(self.car, False)
        else:
            self.status_text.setText("RACING")
            self.resume_button.hide()

    # PHYSICS AND LAPS

    def update_speed(self, dt):
        if self.keys["accelerate"]:
            self.speed += self.acceleration * dt
        elif self.keys["brake"]:
            if self.speed > 0:
                self.speed -= self.braking * dt
            else:
                self.speed -= self.acceleration * 0.65 * dt
        else:
            if self.speed > 0:
                self.speed = max(0, self.speed - self.drag * dt)
            elif self.speed < 0:
                self.speed = min(0, self.speed + self.drag * dt)

        self.speed = max(-self.max_reverse, min(self.max_speed, self.speed))

    def is_on_track(self):
        x, y = self.car.getX(), self.car.getY()
        outer = (x / self.outer_x) ** 2 + (y / self.outer_y) ** 2
        inner = (x / self.inner_x) ** 2 + (y / self.inner_y) ** 2
        return outer <= 1.0 and inner >= 1.0

    def crossed_finish_line(self, px, py, x, y):
        if not (py < 0 <= y):
            return False

        dy = y - py
        if abs(dy) < 1e-8:
            return False

        fraction = -py / dy
        cross_x = px + fraction * (x - px)
        return -self.outer_x <= cross_x <= -self.inner_x

    def update_player_laps(self):
        x, y = self.car.getX(), self.car.getY()

        if x > 0:
            self.player_lap_armed = True

        crossed = self.player_lap_armed and self.crossed_finish_line(
            self.previous_player_x, self.previous_player_y, x, y
        )

        if crossed:
            lap_time = self.race_time - self.lap_start_time
            self.player_lap += 1
            self.lap_start_time = self.race_time
            self.player_lap_armed = False

            if lap_time > 1 and (
                self.best_lap is None or lap_time < self.best_lap
            ):
                self.best_lap = lap_time

            if self.player_lap >= self.total_laps:
                self.finish_player()

        self.previous_player_x, self.previous_player_y = x, y

    # AI RACING AND OVERTAKING

    def _ai_lane_limits(self, ai):
        low = max(self.inner_x + 2.7, ai["base_rx"] - 2.2)
        high = min(self.outer_x - 2.7, ai["base_rx"] + 2.2)
        return low - ai["base_rx"], high - ai["base_rx"]

    def _ai_obstacles_ahead(self, ai):
        obstacles = []
        ax, ay = ai["car"].getX(), ai["car"].getY()

        for other in self.ai_cars:
            if other is ai or other["finished"]:
                continue

            ox, oy = other["car"].getX(), other["car"].getY()
            distance = math.hypot(ox - ax, oy - ay)
            gap = (ai["theta"] - other["theta"]) % (2 * math.pi)

            if 0.015 < gap < 0.42 and distance < 18.0:
                obstacles.append({"distance": distance})

        px, py = self.car.getX(), self.car.getY()

        if not self.player_finished:
            distance = math.hypot(px - ax, py - ay)
            player_theta = math.atan2(
                py / max(ai["ry"], 1.0),
                px / max(ai["rx"], 1.0)
            )
            gap = (ai["theta"] - player_theta) % (2 * math.pi)

            if 0.015 < gap < 0.42 and distance < 18.0:
                obstacles.append({"distance": distance})

        return obstacles

    def _lane_is_clear(self, ai, offset):
        test_rx = ai["base_rx"] + offset
        test_ry = ai["base_ry"] + offset * 1.25
        test_x = test_rx * math.cos(ai["theta"] - 0.20)
        test_y = test_ry * math.sin(ai["theta"] - 0.20)

        for other in self.ai_cars:
            if other is ai or other["finished"]:
                continue

            if math.hypot(
                test_x - other["car"].getX(),
                test_y - other["car"].getY()
            ) < 5.0:
                return False

        if not self.player_finished and math.hypot(
            test_x - self.car.getX(),
            test_y - self.car.getY()
        ) < 5.0:
            return False

        return True

    def choose_overtake_lane(self, ai):
        dt = self.current_dt
        ai["overtake_timer"] = max(0.0, ai["overtake_timer"] - dt)
        ai["overtake_cooldown"] = max(
            0.0, ai["overtake_cooldown"] - dt
        )
        low_offset, high_offset = self._ai_lane_limits(ai)
        obstacles = self._ai_obstacles_ahead(ai)
        ai["target_speed"] = ai["base_speed"]

        if obstacles:
            ai["target_speed"] = ai["base_speed"] + 1.8

            if (
                ai["overtake_timer"] <= 0
                and ai["overtake_cooldown"] <= 0
            ):
                candidates = [high_offset, low_offset]
                candidates.sort(
                    key=lambda v: abs(v - ai["lane_offset"])
                )
                chosen = None

                for candidate in candidates:
                    if abs(candidate - ai["lane_offset"]) < 0.5:
                        continue
                    if self._lane_is_clear(ai, candidate):
                        chosen = candidate
                        break

                if chosen is not None:
                    ai["target_offset"] = chosen
                    ai["overtaking"] = True
                    ai["overtake_timer"] = 1.0
                else:
                    ai["target_speed"] = max(
                        12.0, ai["base_speed"] - 3.0
                    )
                    ai["target_offset"] = 0.0
                    ai["overtaking"] = False
        else:
            if ai["overtaking"]:
                ai["target_speed"] = ai["base_speed"] + 0.6

                if ai["overtake_timer"] <= 0.45:
                    ai["target_offset"] = 0.0
                    if abs(ai["lane_offset"]) < 0.25:
                        ai["overtaking"] = False
                        ai["overtake_cooldown"] = 1.2
            else:
                ai["target_offset"] = 0.0

        response = min(
            1.0, dt * (1.8 if ai["overtaking"] else 1.15)
        )
        ai["lane_offset"] += (
            ai["target_offset"] - ai["lane_offset"]
        ) * response

        ai["lane_offset"] = max(
            low_offset, min(high_offset, ai["lane_offset"])
        )
        ai["rx"] = ai["base_rx"] + ai["lane_offset"]
        ai["ry"] = ai["base_ry"] + ai["lane_offset"] * 1.25

        speed_response = min(
            1.0, dt * (
                2.2 if ai["target_speed"] < ai["speed"] else 0.7
            )
        )
        ai["speed"] += (
            ai["target_speed"] - ai["speed"]
        ) * speed_response

    def update_ai_cars(self, dt):
        for ai in self.ai_cars:
            if ai["finished"]:
                self.set_brake_lights(ai["car"], False)
                continue

            self.choose_overtake_lane(ai)
            ai["theta"] -= ai["speed"] * dt / max(ai["ry"], 1.0)
            self.update_ai_position(ai)

            slowing = ai["target_speed"] < ai["speed"] - 0.8
            self.set_brake_lights(ai["car"], slowing)

            x, y = ai["car"].getX(), ai["car"].getY()

            if x > 0:
                ai["armed"] = True

            crossed = ai["armed"] and self.crossed_finish_line(
                ai["previous_x"], ai["previous_y"], x, y
            )

            if crossed:
                ai["lap"] += 1
                ai["armed"] = False

                if ai["lap"] >= self.total_laps:
                    ai["finished"] = True
                    ai["finish_time"] = self.race_time
                    name = (
                        "BLUE FALCON"
                        if self.ai_cars.index(ai) == 0
                        else "ORANGE STORM"
                    )
                    self.finish_order.append({
                        "name": name, "time": self.race_time
                    })

            ai["previous_x"], ai["previous_y"] = x, y

    def resolve_collisions(self):
        if self.collision_cooldown > 0:
            self.collision_cooldown -= self.current_dt

        for ai in self.ai_cars:
            if ai["finished"]:
                continue

            dx = self.car.getX() - ai["car"].getX()
            dy = self.car.getY() - ai["car"].getY()

            if math.hypot(dx, dy) < 2.4 and self.collision_cooldown <= 0:
                self.speed *= -0.20
                self.collision_cooldown = 0.7
                self.play_game_sound(self.collision_sound)
                self.status_text.setText("CONTACT!")
                distance = math.hypot(dx, dy)

                if distance > 0.01:
                    self.car.setX(self.car.getX() + dx / distance)
                    self.car.setY(self.car.getY() + dy / distance)

    # FINISH AND RESULTS

    def finish_player(self):
        if self.player_finished:
            return

        self.player_finished = True
        self.player_finish_time = self.race_time
        self.speed = 0.0
        self.finish_order.append({
            "name": "YOU", "time": self.player_finish_time
        })
        self.status_text.setText("FINISHED")
        self.results_text.setText(
            "YOU FINISHED!\nWaiting for AI opponents..."
        )
        self.results_text.show()
        self.check_all_finished()

    def check_all_finished(self):
        if (
            not self.player_finished
            or not all(ai["finished"] for ai in self.ai_cars)
        ):
            return

        if self.race_finished:
            return

        self.race_finished = True
        self.race_started = False
        self.countdown_active = False
        self.go_display_timer = 0.0
        self.countdown_text.hide()
        self.stop_looping_audio()

        standings = sorted(
            self.finish_order, key=lambda item: item["time"]
        )
        labels = ["1ST", "2ND", "3RD"]
        lines = ["FINAL LEADERBOARD", ""]

        for i, item in enumerate(standings):
            lines.append(
                f"{labels[i]}  {item['name']}  -  "
                f"{self.format_time(item['time'])}"
            )

        if standings:
            lines.extend(["", f"WINNER: {standings[0]['name']}"])

        lines.append("\nPress R to race again")
        self.results_text.setText("\n".join(lines))
        self.results_text.show()
        self.status_text.setText("RACE COMPLETE")

    def format_time(self, seconds):
        if seconds is None:
            return "--:--.---"

        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes:02d}:{secs:06.3f}"

    # CAMERA AND HUD

    def update_camera(self, dt):
        quat = self.car.getQuat(self.render)
        forward = quat.getForward()
        target = (
            self.car.getPos() - forward * self.camera_distance
            + Vec3(0, 0, self.camera_height)
        )
        blend = min(1.0, max(0.0, dt * 4.0))

        if blend >= 1.0:
            self.camera.setPos(target)
        else:
            self.camera.setPos(
                self.camera.getPos()
                + (target - self.camera.getPos()) * blend
            )

        self.camera.lookAt(self.car.getPos() + Vec3(0, 0, 1.0))

    def get_race_progress(self, x, y, lap):
        angle = math.atan2(y / self.center_y, x / self.center_x)
        progress = (math.pi - angle) % (2 * math.pi)
        return lap * 2 * math.pi + progress

    def update_live_leaderboard(self):
        racers = [{
            "name": "YOU",
            "lap": self.player_lap,
            "progress": self.get_race_progress(
                self.car.getX(), self.car.getY(), self.player_lap
            ),
            "finished": self.player_finished,
            "time": self.player_finish_time
        }]

        for i, ai in enumerate(self.ai_cars):
            racers.append({
                "name": "BLUE FALCON" if i == 0 else "ORANGE STORM",
                "lap": ai["lap"],
                "progress": self.get_race_progress(
                    ai["car"].getX(), ai["car"].getY(), ai["lap"]
                ),
                "finished": ai["finished"],
                "time": ai["finish_time"]
            })

        racers.sort(
            key=lambda r: (
                r["finished"],
                r["time"] if r["finished"] and r["time"] is not None
                else -r["progress"]
            ),
            reverse=True
        )

        lines = ["LIVE STANDINGS", "----------------"]

        for position, racer in enumerate(racers, start=1):
            lap_display = (
                self.total_laps if racer["finished"]
                else min(racer["lap"] + 1, self.total_laps)
            )
            status = "FINISHED" if racer["finished"] else "RACING"
            lines.append(
                f"P{position}  {racer['name']}\n"
                f"     LAP {lap_display}/{self.total_laps}  {status}"
            )

        self.leaderboard_text.setText("\n".join(lines))

    def update_hud(self):
        self.update_live_leaderboard()
        ai_lines = []

        for i, ai in enumerate(self.ai_cars):
            name = "BLUE" if i == 0 else "ORANGE"
            state = "PASSING" if ai["overtaking"] else "RACING"
            ai_lines.append(
                f"{name}: LAP {min(ai['lap'] + 1, self.total_laps)}/"
                f"{self.total_laps}  {state}"
            )

        self.hud.setText(
            f"LAP  {min(self.player_lap + 1, self.total_laps)}/"
            f"{self.total_laps}\n"
            f"TIME  {self.format_time(self.race_time)}\n"
            f"BEST  {self.format_time(self.best_lap)}\n"
            + "\n".join(ai_lines)
        )
        self.speed_text.setText(
            f"SPEED  {int(abs(self.speed) * 7.2):03d} km/h"
        )

        if self.race_started and not self.paused and not self.player_finished:
            self.status_text.setText("RACING")

    # MAIN GAME LOOP

    def update(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.05)
        self.current_dt = dt

        if self.go_display_timer > 0:
            self.go_display_timer -= dt
            if self.go_display_timer <= 0:
                self.go_display_timer = 0.0
                self.countdown_text.hide()

        if self.countdown_active:
            self.countdown -= dt
            number = math.ceil(self.countdown)

            if number > 0:
                self.countdown_text.setText(str(number))

                if number != self.last_countdown_number:
                    self.play_game_sound(self.countdown_sound)
                    self.last_countdown_number = number
            else:
                self.countdown_active = False
                self.race_started = True
                self.countdown_text.setText("GO!")
                self.countdown_text.show()
                self.go_display_timer = 1.0
                self.status_text.setText("RACING")
                self.play_game_sound(self.go_sound)
                self.last_countdown_number = 0

        if self.race_started and not self.paused and not self.race_finished:
            self.race_time += dt

            if not self.player_finished:
                self.update_speed(dt)

                if not self.is_on_track():
                    self.speed *= max(0.0, 1.0 - 1.8 * dt)

                steering = (
                    int(self.keys["left"]) - int(self.keys["right"])
                )

                if abs(self.speed) > 0.25 and steering:
                    factor = 0.25 + 0.75 * min(
                        abs(self.speed) / 20.0, 1.0
                    )
                    direction = 1 if self.speed >= 0 else -1
                    self.car.setH(
                        self.car.getH()
                        + steering * self.steering_rate
                        * factor * direction * dt
                    )

                forward = self.car.getQuat(self.render).getForward()
                self.car.setPos(
                    self.car.getPos() + forward * self.speed * dt
                )
                self.update_player_laps()

            self.update_ai_cars(dt)

            if not self.player_finished:
                self.resolve_collisions()

            self.check_all_finished()
            self.update_hud()

        player_braking = (
            self.race_started
            and not self.paused
            and not self.race_finished
            and self.keys["brake"]
        )
        self.set_brake_lights(self.car, player_braking)

        self.update_smoke(dt)
        self.update_audio()
        self.update_camera(dt)

        return task.cont


if __name__ == "__main__":
    game = ApexRush()
    game.run()

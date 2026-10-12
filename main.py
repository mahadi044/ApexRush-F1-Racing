
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight, DirectionalLight, CardMaker,
    Geom, GeomNode, GeomTriangles,
    GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, Vec3, Vec4, LineSegs
)
import math


class ApexRush(ShowBase):
    def __init__(self):
        super().__init__()

        self.disableMouse()
        self.setBackgroundColor(0.40, 0.62, 0.78, 1)
        self.setFrameRateMeter(True)

        # Basic lighting: lightweight for integrated GPUs
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.55, 0.55, 0.58, 1))
        self.render.setLight(
            self.render.attachNewNode(ambient)
        )

        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.85, 0.82, 0.76, 1))
        sun_node = self.render.attachNewNode(sun)
        sun_node.setHpr(-35, -55, 0)
        self.render.setLight(sun_node)

        self.make_ground()
        self.make_track()
        self.make_car()

        self.speed = 0.0
        self.max_speed = 42.0
        self.acceleration = 20.0
        self.braking = 34.0
        self.drag = 5.0
        self.steering_rate = 65.0
        self.keys = {
            "accelerate": False,
            "brake": False,
            "left": False,
            "right": False,
        }

        self.setup_controls()
        self.setup_hud()

        self.camera.setPos(-32, -12, 7)
        self.camera.lookAt(self.car)

        self.taskMgr.add(self.update, "game_update")

    def make_ground(self):
        maker = CardMaker("grass")
        maker.setFrame(-180, 180, -180, 180)
        ground = self.render.attachNewNode(maker.generate())
        ground.setP(-90)
        ground.setZ(-0.15)
        ground.setColor(0.16, 0.34, 0.19, 1)
        ground.setTwoSided(True)

    def make_track(self):
        # Procedural oval circuit
        segments = 180
        outer_x, outer_y = 38.5, 52.5
        inner_x, inner_y = 25.5, 39.5

        vertex_data = GeomVertexData(
            "road", GeomVertexFormat.getV3(),
            Geom.UHStatic
        )
        vertex = GeomVertexWriter(vertex_data, "vertex")

        for i in range(segments):
            angle = 2 * math.pi * i / segments

            vertex.addData3(
                outer_x * math.cos(angle),
                outer_y * math.sin(angle),
                0
            )
            vertex.addData3(
                inner_x * math.cos(angle),
                inner_y * math.sin(angle),
                0
            )

        triangles = GeomTriangles(Geom.UHStatic)

        for i in range(segments):
            nxt = (i + 1) % segments

            outer = 2 * i
            inner = outer + 1
            outer_next = 2 * nxt
            inner_next = outer_next + 1

            triangles.addVertices(outer, inner, outer_next)
            triangles.addVertices(
                inner, inner_next, outer_next
            )

        geometry = Geom(vertex_data)
        geometry.addPrimitive(triangles)

        node = GeomNode("oval_track")
        node.addGeom(geometry)

        road = self.render.attachNewNode(node)
        road.setZ(0.02)
        road.setColor(0.22, 0.23, 0.25, 1)
        road.setTwoSided(True)

        # Track edges
        lines = LineSegs("track_edges")
        lines.setThickness(3)
        lines.setColor(0.95, 0.95, 0.92, 1)

        for rx, ry in (
            (outer_x, outer_y),
            (inner_x, inner_y),
        ):
            for i in range(segments + 1):
                angle = 2 * math.pi * (i % segments) / segments
                x = rx * math.cos(angle)
                y = ry * math.sin(angle)

                if i == 0:
                    lines.moveTo(x, y, 0.08)
                else:
                    lines.drawTo(x, y, 0.08)

        self.render.attachNewNode(lines.create())

    def make_car(self):
        self.car = self.render.attachNewNode("player_car")
        self.car.setPos(-32, 0, 0.65)

        # Main chassis
        self.add_box(
            self.car, (0, 0, 0),
            (1.55, 3.4, 0.48),
            (0.85, 0.045, 0.055, 1)
        )

        # Nose
        self.add_box(
            self.car, (0, 1.8, -0.04),
            (0.72, 1.15, 0.22),
            (0.95, 0.16, 0.08, 1)
        )

        # Cockpit
        self.add_box(
            self.car, (0, 0.15, 0.38),
            (0.82, 1.1, 0.40),
            (0.08, 0.12, 0.15, 1)
        )

        # Front and rear wings
        self.add_box(
            self.car, (0, 2.15, -0.08),
            (2.15, 0.30, 0.12),
            (0.08, 0.08, 0.09, 1)
        )
        self.add_box(
            self.car, (0, -1.7, 0.05),
            (2.0, 0.38, 0.13),
            (0.08, 0.08, 0.09, 1)
        )

        # Four simple wheels
        for x in (-0.93, 0.93):
            for y in (-1.05, 1.05):
                self.add_box(
                    self.car, (x, y, -0.18),
                    (0.35, 0.75, 0.42),
                    (0.035, 0.035, 0.04, 1)
                )

    def add_box(self, parent, position, scale, color):
        box = self.loader.loadModel("models/box")
        box.reparentTo(parent)
        box.setPos(*position)
        box.setScale(*scale)
        box.setColor(*color)
        return box

    def setup_controls(self):
        bindings = {
            "arrow_up": ("accelerate", True),
            "arrow_down": ("brake", True),
            "arrow_left": ("left", True),
            "arrow_right": ("right", True),
            "w": ("accelerate", True),
            "s": ("brake", True),
            "a": ("left", True),
            "d": ("right", True),
        }

        for key, action in bindings.items():
            name, value = action
            self.accept(key, self.set_key, [name, value])
            self.accept(
                key + "-up", self.set_key, [name, False]
            )

        self.accept("escape", self.userExit)

    def set_key(self, name, value):
        self.keys[name] = value

    def setup_hud(self):
        self.hud = OnscreenText(
            text="APEXRUSH  |  PRACTICE SESSION",
            pos=(-1.28, 0.91),
            scale=0.055,
            fg=(1, 1, 1, 1),
            align=0,
            mayChange=False
        )

        self.speed_text = OnscreenText(
            text="SPEED  000 km/h",
            pos=(1.20, -0.86),
            scale=0.07,
            fg=(1, 1, 1, 1),
            align=2,
            mayChange=True
        )

        self.help_text = OnscreenText(
            text="UP/W: Accelerate   DOWN/S: Brake\n"
                 "LEFT/A  RIGHT/D: Steer   ESC: Exit",
            pos=(-1.28, -0.83),
            scale=0.043,
            fg=(1, 1, 1, 1),
            align=0,
            mayChange=False
        )

    def update(self, task):
        dt = min(
            globalClock.getDt(), 0.04
        )

        if self.keys["accelerate"]:
            self.speed += self.acceleration * dt

        elif self.keys["brake"]:
            if self.speed > 0:
                self.speed -= self.braking * dt
            else:
                self.speed -= self.acceleration * 0.4 * dt
        else:
            if self.speed > 0:
                self.speed = max(
                    0, self.speed - self.drag * dt
                )
            elif self.speed < 0:
                self.speed = min(
                    0, self.speed + self.drag * dt
                )

        self.speed = max(
            -10, min(self.max_speed, self.speed)
        )

        # Steering response reduces at high speed
        steering = (
            int(self.keys["left"])
            - int(self.keys["right"])
        )

        if abs(self.speed) > 0.5:
            speed_factor = min(
                1.0, 8.0 / max(abs(self.speed), 1)
            )
            direction = 1 if self.speed >= 0 else -1

            self.car.setH(
                self.car.getH()
                + steering
                * self.steering_rate
                * speed_factor
                * direction
                * dt
            )

        forward = self.car.getQuat().getForward()
        self.car.setPos(
            self.car.getPos() + forward * self.speed * dt
        )

        # Chase camera
        desired_camera = (
            self.car.getPos()
            - forward * 10
            + Vec3(0, 0, 5)
        )

        blend = min(1.0, dt * 4)
        self.camera.setPos(
            self.camera.getPos()
            + (desired_camera - self.camera.getPos()) * blend
        )
        self.camera.lookAt(self.car.getPos() + Vec3(0, 0, 1))

        self.speed_text.setText(
            f"SPEED  {abs(self.speed) * 3.6:03.0f} km/h"
        )

        return task.cont


game = ApexRush()
game.run()

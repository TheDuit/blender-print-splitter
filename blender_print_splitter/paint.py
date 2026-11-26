"""Single-ID Face Set painter implemented as a small Sculpt Mode modal tool."""

import heapq
import math

import bpy
from .registration import register_classes, unregister_classes
import gpu
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

from .core import (
    BACKGROUND_FACE_SET,
    FACE_SET_ATTRIBUTE,
    FACE_SET_KEY,
    GEOMETRY_SEGMENTATION_KEY,
    TARGET_FACE_SET,
    ROLE_DIVISION,
    ROLE_KEY,
    ROLE_WORKING,
    ensure_face_sets,
    is_mesh_object,
)


def _face_graph(mesh, matrix_world):
    centers = [matrix_world @ polygon.center for polygon in mesh.polygons]
    radii = []
    edge_faces = {}
    for poly in mesh.polygons:
        center = centers[poly.index]
        radii.append(max(((matrix_world @ mesh.vertices[index].co) - center).length for index in poly.vertices))
        for edge_key in poly.edge_keys:
            key = tuple(sorted(edge_key))
            edge_faces.setdefault(key, []).append(poly.index)

    adjacency = [[] for _ in mesh.polygons]
    for linked_faces in edge_faces.values():
        if len(linked_faces) == 2:
            a, b = linked_faces
            cost = (centers[a] - centers[b]).length
            adjacency[a].append((b, cost))
            adjacency[b].append((a, cost))
    return centers, radii, adjacency


class PSS_OT_paint_faceset(bpy.types.Operator):
    """Paint or erase one Face Set ID without relying on Ctrl-modified strokes."""

    bl_idname = "print_splitter.paint_faceset"
    bl_label = "Paint Region"
    bl_description = "Left-drag to paint one Face Set ID; right-drag to erase it"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    radius_px: bpy.props.IntProperty(
        name="Brush Radius",
        description="Brush radius in viewport pixels",
        default=36,
        min=4,
        max=300,
    )

    MIN_RADIUS_PX = 4
    MAX_RADIUS_PX = 300
    RADIUS_STEP_PX = 4

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and obj.get(ROLE_KEY) in {ROLE_WORKING, ROLE_DIVISION}
            and not obj.get(GEOMETRY_SEGMENTATION_KEY)
        )

    def invoke(self, context, event):
        self.obj = context.active_object
        self.mesh = self.obj.data
        if getattr(self.obj, "use_dynamic_topology_sculpting", False):
            self.report({"ERROR"}, "Disable Dyntopo to paint Face Sets with Print Splitter.")
            return {"CANCELLED"}
        self.area = context.area
        self.region = next((region for region in context.area.regions if region.type == "WINDOW"), None)
        self.region_3d = context.space_data.region_3d
        if self.region is None or self.region_3d is None:
            self.report({"ERROR"}, "This tool requires a 3D Viewport region.")
            return {"CANCELLED"}
        self.attribute = ensure_face_sets(self.mesh)
        self.target_id = int(self.obj.get(FACE_SET_KEY, TARGET_FACE_SET))
        self.obj[FACE_SET_KEY] = self.target_id
        self.radius_px = context.scene.print_splitter_settings.brush_radius_px
        if not len(self.mesh.polygons):
            self.report({"ERROR"}, "The mesh has no faces to paint.")
            return {"CANCELLED"}
        self.modifier_visibility = [(modifier, modifier.show_viewport) for modifier in self.obj.modifiers]
        for modifier, _visible in self.modifier_visibility:
            modifier.show_viewport = False
        # Keep BVH face indices aligned with the base mesh Face Set attribute.
        context.view_layer.update()
        try:
            self.bvh = BVHTree.FromObject(
                self.obj,
                context.evaluated_depsgraph_get(),
                deform=False,
            )
        except (RuntimeError, TypeError, ValueError):
            self._restore_modifiers()
            self.report({"ERROR"}, "Could not prepare the surface for painting.")
            return {"CANCELLED"}
        if self.bvh is None:
            self._restore_modifiers()
            self.report({"ERROR"}, "Could not prepare the surface for painting.")
            return {"CANCELLED"}
        self.centers, self.face_radii, self.adjacency = _face_graph(self.mesh, self.obj.matrix_world)
        self.inverse = self.obj.matrix_world.inverted()
        self.inverse_3x3 = self.inverse.to_3x3()
        self.original_values = {}
        self.painting = False
        self.paint_action = "PAINT"
        self.last_mouse = None
        self.cursor_location = self._event_coord(event)
        self.cursor_visible = True
        try:
            self.cursor_shader = gpu.shader.from_builtin("UNIFORM_COLOR")
            self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_brush_cursor,
                (),
                "WINDOW",
                "POST_PIXEL",
            )
        except (RuntimeError, TypeError, ValueError):
            self._restore_modifiers()
            self.report({"ERROR"}, "Could not create the brush radius preview.")
            return {"CANCELLED"}
        try:
            context.space_data.overlay.show_sculpt_face_sets = True
        except AttributeError:
            pass
        context.window_manager.modal_handler_add(self)
        self.window = context.window
        self.window.cursor_modal_set("PAINT_BRUSH")
        self.cursor_is_modal = True
        self.area.tag_redraw()
        context.workspace.status_text_set(
            f"Print Splitter: left-drag paint | right-drag erase | wheel radius ({self.radius_px}px; Shift faster) | Enter finish | Esc cancel"
        )
        return {"RUNNING_MODAL"}

    def _draw_brush_cursor(self):
        if not self.cursor_visible or self.cursor_location is None:
            return
        if bpy.context.area != self.area:
            return

        x, y = self.cursor_location
        radius = self.radius_px
        segments = 64
        points = [
            (
                x + math.cos((2.0 * math.pi * index) / segments) * radius,
                y + math.sin((2.0 * math.pi * index) / segments) * radius,
            )
            for index in range(segments)
        ]
        points.append(points[0])
        batch = batch_for_shader(self.cursor_shader, "LINE_STRIP", {"pos": points})

        gpu.state.blend_set("ALPHA")
        try:
            self.cursor_shader.bind()
            self.cursor_shader.uniform_float("color", (0.0, 0.0, 0.0, 0.8))
            gpu.state.line_width_set(3.0)
            batch.draw(self.cursor_shader)
            self.cursor_shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
            gpu.state.line_width_set(1.25)
            batch.draw(self.cursor_shader)
        finally:
            gpu.state.line_width_set(1.0)
            gpu.state.blend_set("NONE")

    def _set_cursor_from_event(self, event):
        x, y = self._event_coord(event)
        self.cursor_location = (x, y)
        self.cursor_visible = 0 <= x < self.region.width and 0 <= y < self.region.height
        self.area.tag_redraw()

    def _adjust_radius(self, context, direction, event):
        step = 16 if event.shift else self.RADIUS_STEP_PX
        self.radius_px = max(
            self.MIN_RADIUS_PX,
            min(self.MAX_RADIUS_PX, self.radius_px + direction * step),
        )
        context.scene.print_splitter_settings.brush_radius_px = self.radius_px
        context.workspace.status_text_set(
            f"Print Splitter: radius {self.radius_px}px | wheel change radius (Shift faster) | left-drag paint | right-drag erase | Enter finish | Esc cancel"
        )
        self.area.tag_redraw()

    def _ray_hit(self, x, y):
        coord = (x, y)
        origin_world = view3d_utils.region_2d_to_origin_3d(self.region, self.region_3d, coord)
        direction_world = view3d_utils.region_2d_to_vector_3d(self.region, self.region_3d, coord)
        origin_local = self.inverse @ origin_world
        direction_local = (self.inverse_3x3 @ direction_world).normalized()
        hit = self.bvh.ray_cast(origin_local, direction_local)
        if hit[0] is None or hit[2] < 0:
            return None
        location_world = self.obj.matrix_world @ hit[0]
        return hit[2], location_world

    def _radius_world(self, x, y, hit_location):
        edge_location = view3d_utils.region_2d_to_location_3d(
            self.region,
            self.region_3d,
            (x + self.radius_px, y),
            hit_location,
        )
        return max((edge_location - hit_location).length, 1e-6)

    def _paint_at(self, x, y):
        if x < 0 or y < 0 or x >= self.region.width or y >= self.region.height:
            return False
        hit = self._ray_hit(x, y)
        if hit is None:
            return False
        seed_face, hit_location = hit
        radius_world = self._radius_world(x, y, hit_location)
        limit = radius_world
        queue = [(max(0.0, (self.centers[seed_face] - hit_location).length - self.face_radii[seed_face]), seed_face)]
        distances = {seed_face: queue[0][0]}
        touched = []
        while queue:
            distance, face_index = heapq.heappop(queue)
            if distance != distances.get(face_index):
                continue
            if distance > limit:
                continue
            touched.append(face_index)
            for neighbor, edge_cost in self.adjacency[face_index]:
                next_distance = distance + edge_cost
                if next_distance <= limit and next_distance < distances.get(neighbor, math.inf):
                    distances[neighbor] = next_distance
                    heapq.heappush(queue, (next_distance, neighbor))

        changed = False
        new_value = self.target_id if self.paint_action == "PAINT" else BACKGROUND_FACE_SET
        for face_index in touched:
            current_value = int(self.attribute.data[face_index].value)
            if self.paint_action == "ERASE" and current_value != self.target_id:
                continue
            if current_value == new_value:
                continue
            self.original_values.setdefault(face_index, current_value)
            self.attribute.data[face_index].value = new_value
            changed = True
        if changed:
            self.mesh.update()
            self.obj.update_tag(refresh={"DATA"})
            if self.region:
                self.region.tag_redraw()
        return changed

    def _sample_segment(self, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        spacing = max(2.0, self.radius_px * 0.28)
        steps = max(1, int(length / spacing))
        for index in range(1, steps + 1):
            factor = index / steps
            self._paint_at(start[0] + dx * factor, start[1] + dy * factor)

    def _event_coord(self, event):
        return event.mouse_x - self.region.x, event.mouse_y - self.region.y

    def _finish(self, context, cancelled=False):
        if cancelled:
            for face_index, original_value in self.original_values.items():
                self.attribute.data[face_index].value = original_value
            self.mesh.update()
            self.obj.update_tag(refresh={"DATA"})
        self._restore_modifiers()
        draw_handle = getattr(self, "draw_handle", None)
        if draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handle, "WINDOW")
            self.draw_handle = None
        if getattr(self, "cursor_is_modal", False):
            self.window.cursor_modal_restore()
            self.cursor_is_modal = False
        context.workspace.status_text_set(None)
        return {"CANCELLED" if cancelled else "FINISHED"}

    def _start_stroke(self, context, event, action):
        self.painting = True
        self.paint_action = action
        self.window.cursor_modal_set("PAINT_BRUSH" if action == "PAINT" else "ERASER")
        self._set_cursor_from_event(event)
        self.last_mouse = self._event_coord(event)
        self._paint_at(*self.last_mouse)

    def _restore_modifiers(self):
        for modifier, visible in self.modifier_visibility:
            try:
                modifier.show_viewport = visible
            except ReferenceError:
                pass

    def modal(self, context, event):
        if event.type in {"MIDDLEMOUSE", "NDOF_MOTION"}:
            return {"PASS_THROUGH"}
        if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            x, y = self._event_coord(event)
            if not (0 <= x < self.region.width and 0 <= y < self.region.height):
                return {"PASS_THROUGH"}
            self._adjust_radius(context, 1 if event.type == "WHEELUPMOUSE" else -1, event)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            return self._finish(context, cancelled=True)
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            return self._finish(context)
        if event.type in {"LEFTMOUSE", "RIGHTMOUSE"}:
            if event.value == "PRESS":
                action = "PAINT" if event.type == "LEFTMOUSE" else "ERASE"
                self._start_stroke(context, event, action)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and self.painting:
                self.painting = False
                self.paint_action = "PAINT"
                self.window.cursor_modal_set("PAINT_BRUSH")
                self.last_mouse = None
                return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self._set_cursor_from_event(event)
            current = self._event_coord(event)
            if self.painting:
                if self.last_mouse is not None:
                    self._sample_segment(self.last_mouse, current)
                self.last_mouse = current
            return {"RUNNING_MODAL"}
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._finish(context, cancelled=True)


CLASSES = (PSS_OT_paint_faceset,)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

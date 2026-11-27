"""Single-ID Face Set painter implemented as a small Sculpt Mode modal tool."""

import heapq
import math

import bpy
from .registration import register_classes, unregister_classes
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

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
    """Paint one persistent Face Set with Blender's standard left-drag interaction."""

    bl_idname = "print_splitter.paint_faceset"
    bl_label = "Paint Region"
    bl_description = "Left-drag to paint; press E to erase or P to paint; F-drag changes brush size"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    radius_px: bpy.props.IntProperty(
        name="Brush Size",
        description="Brush radius in viewport pixels",
        default=70,
        min=1,
        max=10000,
    )

    action: bpy.props.EnumProperty(
        name="Action",
        items=(
            ("PAINT", "Paint", "Paint the current Face Set"),
            ("ERASE", "Erase", "Return painted faces to the background Face Set"),
        ),
        default="PAINT",
        options={"SKIP_SAVE"},
    )

    MIN_RADIUS_PX = 1
    MAX_RADIUS_PX = 10000

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
        if context.area is None or context.area.type != "VIEW_3D" or context.space_data is None:
            self.report({"ERROR"}, "Start Face Set painting from the 3D Viewport.")
            return {"CANCELLED"}
        self.area = context.area
        self.region = next((region for region in context.area.regions if region.type == "WINDOW"), None)
        self.region_3d = getattr(context.space_data, "region_3d", None)
        if self.region is None or self.region_3d is None:
            self.report({"ERROR"}, "This tool requires a 3D Viewport region.")
            return {"CANCELLED"}
        self.attribute = ensure_face_sets(self.mesh)
        self.target_id = int(self.obj.get(FACE_SET_KEY, TARGET_FACE_SET))
        self.obj[FACE_SET_KEY] = self.target_id
        if not len(self.mesh.polygons):
            self.report({"ERROR"}, "The mesh has no faces to paint.")
            return {"CANCELLED"}
        self.sculpt_settings = context.tool_settings.sculpt
        self.brush = self.sculpt_settings.brush
        self.show_brush_before = self.sculpt_settings.show_brush
        self.sculpt_settings.show_brush = True
        settings = context.scene.print_splitter_settings
        native_radius = int(self.brush.size) if self.brush is not None else settings.brush_radius_px
        self.radius_px = max(self.MIN_RADIUS_PX, min(self.MAX_RADIUS_PX, native_radius))
        settings.brush_radius_px = self.radius_px
        self.use_pressure_size = bool(self.brush and self.brush.use_pressure_size)
        self.pressure = 1.0
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
            self.sculpt_settings.show_brush = self.show_brush_before
            self.report({"ERROR"}, "Could not prepare the surface for painting.")
            return {"CANCELLED"}
        if self.bvh is None:
            self._restore_modifiers()
            self.sculpt_settings.show_brush = self.show_brush_before
            self.report({"ERROR"}, "Could not prepare the surface for painting.")
            return {"CANCELLED"}
        self.centers, self.face_radii, self.adjacency = _face_graph(self.mesh, self.obj.matrix_world)
        self.inverse = self.obj.matrix_world.inverted()
        self.inverse_3x3 = self.inverse.to_3x3()
        self.original_values = {}
        self.painting = False
        self.paint_action = self.action
        self.radius_adjusting = False
        self.last_mouse = None
        try:
            context.space_data.overlay.show_sculpt_face_sets = True
        except AttributeError:
            pass
        context.window_manager.modal_handler_add(self)
        self.window = context.window
        self.window.cursor_modal_set("ERASER" if self.paint_action == "ERASE" else "PAINT_BRUSH")
        self.cursor_is_modal = True
        self.area.tag_redraw()
        self._set_status(context)
        return {"RUNNING_MODAL"}

    def _set_status(self, context):
        mode = "ERASE" if self.paint_action == "ERASE" else "PAINT"
        context.workspace.status_text_set(
            f"Print Splitter {mode} | left-drag apply | E erase / P paint | F-drag size ({self.radius_px}px) | right/middle mouse + wheel navigate | Enter finish | Esc cancel"
        )

    def _set_action(self, context, action):
        self.paint_action = action
        self.window.cursor_modal_set("ERASER" if action == "ERASE" else "PAINT_BRUSH")
        self._set_status(context)
        self.area.tag_redraw()

    def _adjust_radius(self, context, radius):
        self.radius_px = max(self.MIN_RADIUS_PX, min(self.MAX_RADIUS_PX, int(radius)))
        context.scene.print_splitter_settings.brush_radius_px = self.radius_px
        if self.brush is not None:
            self.brush.size = self.radius_px
        self._set_status(context)
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
        radius_px = max(1, int(self.radius_px * self.pressure))
        edge_location = view3d_utils.region_2d_to_location_3d(
            self.region,
            self.region_3d,
            (x + radius_px, y),
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
        spacing = max(2.0, self.radius_px * self.pressure * 0.28)
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
        if getattr(self, "cursor_is_modal", False):
            self.window.cursor_modal_restore()
            self.cursor_is_modal = False
        try:
            self.sculpt_settings.show_brush = self.show_brush_before
        except (AttributeError, ReferenceError):
            pass
        context.workspace.status_text_set(None)
        return {"CANCELLED" if cancelled else "FINISHED"}

    def _start_stroke(self, context, event):
        self.painting = True
        self.pressure = event.pressure if self.use_pressure_size and event.pressure > 0.0 else 1.0
        self.last_mouse = self._event_coord(event)
        self._paint_at(*self.last_mouse)

    def _restore_modifiers(self):
        for modifier, visible in self.modifier_visibility:
            try:
                modifier.show_viewport = visible
            except ReferenceError:
                pass

    def modal(self, context, event):
        if context.mode != "SCULPT" or context.active_object != self.obj:
            return self._finish(context)
        if event.type in {"MIDDLEMOUSE", "RIGHTMOUSE", "NDOF_MOTION", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        if event.type == "E" and event.value == "PRESS":
            self._set_action(context, "ERASE")
            return {"RUNNING_MODAL"}
        if event.type == "P" and event.value == "PRESS":
            self._set_action(context, "PAINT")
            return {"RUNNING_MODAL"}
        if event.type == "F" and event.value == "PRESS" and not self.radius_adjusting:
            self.radius_adjusting = True
            self.radius_drag_start_x = event.mouse_x
            self.radius_drag_start_value = self.radius_px
            return {"RUNNING_MODAL"}
        if event.type == "F" and event.value == "RELEASE" and self.radius_adjusting:
            self.radius_adjusting = False
            return {"RUNNING_MODAL"}
        if event.type in {"LEFT_BRACKET", "RIGHT_BRACKET"} and event.value == "PRESS":
            factor = 0.9 if event.type == "LEFT_BRACKET" else 1.1
            self._adjust_radius(context, self.radius_px * factor)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            return self._finish(context, cancelled=True)
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            return self._finish(context)
        if event.type == "LEFTMOUSE":
            if event.value == "RELEASE" and self.painting:
                self.painting = False
                self.last_mouse = None
                return {"RUNNING_MODAL"}
            x, y = self._event_coord(event)
            if not (0 <= x < self.region.width and 0 <= y < self.region.height):
                return {"PASS_THROUGH"}
            if event.value == "PRESS":
                self._start_stroke(context, event)
                return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            current = self._event_coord(event)
            if self.radius_adjusting:
                self._adjust_radius(
                    context,
                    self.radius_drag_start_value + event.mouse_x - self.radius_drag_start_x,
                )
                return {"RUNNING_MODAL"}
            self.pressure = event.pressure if self.use_pressure_size and event.pressure > 0.0 else 1.0
            if self.painting:
                if self.last_mouse is not None:
                    self._sample_segment(self.last_mouse, current)
                self.last_mouse = current
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        self._finish(context, cancelled=True)


CLASSES = (PSS_OT_paint_faceset,)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

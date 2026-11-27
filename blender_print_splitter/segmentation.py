"""Geometry-only Face Set generation and region management."""

from __future__ import annotations

from array import array
from collections import Counter
import json
import math

import bpy
from bpy_extras import view3d_utils
from mathutils.bvhtree import BVHTree
from .registration import register_classes, unregister_classes

from .core import (
    BACKGROUND_FACE_SET,
    FACE_SET_ATTRIBUTE,
    FACE_SET_KEY,
    GEOMETRY_FACE_SET_SUMMARY_KEY,
    GEOMETRY_MOTHER_FACE_SET_KEY,
    GEOMETRY_SEGMENTATION_KEY,
    MOTHER_PART_ID_KEY,
    PART_ID_KEY,
    ROLE_DIVISION,
    ROLE_KEY,
    ROLE_WORKING,
    TARGET_FACE_SET,
    ensure_face_sets,
    is_mesh_object,
    reset_face_sets,
)


def _read_values(attribute):
    values = array("i", [0]) * len(attribute.data)
    if values:
        attribute.data.foreach_get("value", values)
    return values


def _write_summary(obj, counts=None):
    counts = counts if counts is not None else face_set_counts(obj)
    obj[GEOMETRY_FACE_SET_SUMMARY_KEY] = json.dumps(counts)


def analyze_geometry(obj, method, angle_degrees):
    """Use Blender's native Face Set initializer to keep analysis fast on dense meshes."""
    if not is_mesh_object(obj) or not obj.data.polygons:
        raise ValueError("Select a mesh with faces to analyze.")
    if method not in {"SURFACE_FOLDS", "LOOSE_PARTS"}:
        raise ValueError("Choose a supported geometry analysis method.")
    if bpy.context.mode != "SCULPT" or bpy.context.active_object != obj:
        raise ValueError("Make the mesh active in Sculpt Mode before analyzing it.")

    obj.pop(GEOMETRY_SEGMENTATION_KEY, None)
    obj.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
    obj.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
    reset_face_sets(obj.data)
    attribute = ensure_face_sets(obj.data)

    native_mode = "NORMALS" if method == "SURFACE_FOLDS" else "LOOSE_PARTS"
    threshold = math.cos(math.radians(min(max(float(angle_degrees), 5.0), 89.0)))
    try:
        result = bpy.ops.sculpt.face_sets_init(mode=native_mode, threshold=threshold)
    except RuntimeError as exc:
        raise RuntimeError("Blender could not initialize Face Sets for this mesh.") from exc
    if "FINISHED" not in result:
        raise RuntimeError("Blender could not initialize Face Sets for this mesh.")

    attribute = ensure_face_sets(obj.data)
    raw_values = _read_values(attribute)
    values = array("i", (int(value) + 1 for value in raw_values))
    counts = Counter(values)
    if values:
        attribute.data.foreach_set("value", values)
    obj.data.update()

    largest_id = max(counts, key=counts.get)
    obj[FACE_SET_KEY] = largest_id
    counts = dict(counts)
    _write_summary(obj, counts)
    obj[GEOMETRY_SEGMENTATION_KEY] = method
    obj.update_tag(refresh={"DATA"})
    return counts, largest_id


def face_set_counts(obj):
    attribute = obj.data.attributes.get(FACE_SET_ATTRIBUTE) if is_mesh_object(obj) else None
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        return {}
    values = _read_values(attribute)
    return {
        int(face_set_id): count
        for face_set_id, count in Counter(values).items()
        if face_set_id >= TARGET_FACE_SET
    }


def merge_face_sets(obj, source_id, destination_id):
    if source_id == destination_id:
        raise ValueError("Choose two different Face Sets to merge.")
    attribute = obj.data.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        raise ValueError("Analyze the mesh before merging Face Sets.")
    values = _read_values(attribute)
    source_count = 0
    destination_exists = False
    for index, value in enumerate(values):
        if value == source_id:
            values[index] = destination_id
            source_count += 1
        elif value == destination_id:
            destination_exists = True
    if source_count == 0:
        raise ValueError("The source Face Set no longer exists. Refresh the region list.")
    if not destination_exists:
        raise ValueError("The destination Face Set no longer exists. Refresh the region list.")
    attribute.data.foreach_set("value", values)
    obj.data.update()
    obj[FACE_SET_KEY] = destination_id
    _write_summary(obj)
    obj.update_tag(refresh={"DATA"})
    return source_count


def _sync_face_set_merge_selection(context, obj, source_id, destination_id):
    settings = context.scene.print_splitter_settings
    mother_id = int(obj.get(GEOMETRY_MOTHER_FACE_SET_KEY, TARGET_FACE_SET))
    if source_id == mother_id:
        settings.geometry_mother_face_set = f"FACE_SET_{destination_id}"
    settings.geometry_target_face_set = f"FACE_SET_{destination_id}"


class FaceSetMergeSelection:
    """Small selection state machine shared by click and drag interactions."""

    def __init__(self):
        self.source_id = None
        self.destination_id = None

    def click(self, face_set_id):
        if face_set_id is None:
            return
        if self.source_id is None or face_set_id == self.source_id:
            self.source_id = face_set_id
            self.destination_id = None
        else:
            self.destination_id = face_set_id

    def drag_to(self, face_set_id):
        if self.source_id is None or face_set_id is None or face_set_id == self.source_id:
            return None
        return self.source_id, face_set_id

    def confirm(self):
        if self.source_id is None or self.destination_id is None or self.source_id == self.destination_id:
            return None
        return self.source_id, self.destination_id

    def clear(self):
        self.source_id = None
        self.destination_id = None


class PSS_OT_start_face_set_merge(bpy.types.Operator):
    """Select and merge two analyzed Face Sets directly on the mesh."""

    bl_idname = "print_splitter.start_face_set_merge"
    bl_label = "Merge Face Sets"
    bl_description = (
        "Drag a source region onto a target, or click both and press Enter; "
        "right-click clears selection and Esc cancels"
    )
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    DRAG_THRESHOLD_PX = 6.0

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and bool(obj.get(GEOMETRY_SEGMENTATION_KEY))
            and not getattr(obj, "use_dynamic_topology_sculpting", False)
        ):
            return False
        from .connectors import has_pending_connector

        return not has_pending_connector(obj) and len(face_set_counts(obj)) >= 2

    def invoke(self, context, event):
        self.obj = context.active_object
        self.mesh = self.obj.data
        self.attribute = self.mesh.attributes.get(FACE_SET_ATTRIBUTE)
        if self.attribute is None or self.attribute.domain != "FACE" or self.attribute.data_type != "INT":
            self.report({"ERROR"}, "Analyze the mesh first to create Face Sets.")
            return {"CANCELLED"}
        if context.area is None or context.area.type != "VIEW_3D" or context.space_data.region_3d is None:
            self.report({"ERROR"}, "Start Face Set merging from the 3D Viewport.")
            return {"CANCELLED"}
        self.region = next((region for region in context.area.regions if region.type == "WINDOW"), None)
        if self.region is None:
            self.report({"ERROR"}, "Could not find the 3D Viewport region.")
            return {"CANCELLED"}

        self.region_3d = context.space_data.region_3d
        self.face_values = _read_values(self.attribute)
        self.valid_face_sets = {value for value in self.face_values if value >= TARGET_FACE_SET}
        self.face_set_face_counts = {}
        for face_set_id in self.face_values:
            if face_set_id >= TARGET_FACE_SET:
                self.face_set_face_counts[face_set_id] = self.face_set_face_counts.get(face_set_id, 0) + 1
        if len(self.valid_face_sets) < 2:
            self.report({"ERROR"}, "At least two analyzed Face Sets are required.")
            return {"CANCELLED"}

        self.modifier_visibility = [(modifier, modifier.show_viewport) for modifier in self.obj.modifiers]
        for modifier, _visible in self.modifier_visibility:
            modifier.show_viewport = False
        try:
            context.view_layer.update()
            self.bvh = BVHTree.FromObject(
                self.obj,
                context.evaluated_depsgraph_get(),
                deform=False,
            )
            self.inverse = self.obj.matrix_world.inverted()
            self.inverse_3x3 = self.inverse.to_3x3()
        except (RuntimeError, TypeError, ValueError):
            self._restore_modifiers()
            self.report({"ERROR"}, "Could not prepare the mesh for Face Set selection.")
            return {"CANCELLED"}
        if self.bvh is None:
            self._restore_modifiers()
            self.report({"ERROR"}, "Could not prepare the mesh for Face Set selection.")
            return {"CANCELLED"}

        self.window = context.window
        self.selection = FaceSetMergeSelection()
        self.left_down = False
        self.press_coord = None
        self.dragged = False
        self.cursor_is_modal = False
        context.window_manager.modal_handler_add(self)
        self.window.cursor_modal_set("CROSSHAIR")
        self.cursor_is_modal = True
        self._set_status(context)
        return {"RUNNING_MODAL"}

    def _event_coord(self, event):
        return event.mouse_x - self.region.x, event.mouse_y - self.region.y

    def _face_set_at(self, x, y):
        if x < 0 or y < 0 or x >= self.region.width or y >= self.region.height:
            return None
        try:
            origin_world = view3d_utils.region_2d_to_origin_3d(self.region, self.region_3d, (x, y))
            direction_world = view3d_utils.region_2d_to_vector_3d(self.region, self.region_3d, (x, y))
            origin_local = self.inverse @ origin_world
            direction_local = (self.inverse_3x3 @ direction_world).normalized()
            hit = self.bvh.ray_cast(origin_local, direction_local)
        except (RuntimeError, TypeError, ValueError):
            return None
        if hit[0] is None or hit[2] < 0 or hit[2] >= len(self.face_values):
            return None
        face_set_id = self.face_values[hit[2]]
        return face_set_id if face_set_id in self.valid_face_sets else None

    def _set_status(self, context, hover_id=None, notice=""):
        selection = "Select a source Face Set"
        source_id = self.selection.source_id
        destination_id = self.selection.destination_id
        if source_id is None and hover_id is not None:
            selection = f"Hover Face Set {hover_id} ({self.face_set_face_counts.get(hover_id, 0)} faces); click to select"
        elif source_id is not None:
            source_count = self.face_set_face_counts.get(source_id, 0)
            selection = f"Source Face Set {source_id} ({source_count} faces)"
            if destination_id is not None:
                destination_count = self.face_set_face_counts.get(destination_id, 0)
                selection += f" → target {destination_id} ({destination_count} faces); Enter merges"
            elif hover_id is not None and hover_id != source_id:
                hover_count = self.face_set_face_counts.get(hover_id, 0)
                if self.left_down and self.dragged:
                    selection += f" → release over {hover_id} ({hover_count} faces) to merge"
                else:
                    selection += f" → hover {hover_id} ({hover_count}); click target or drag"
            else:
                selection += "; click another region and press Enter, or drag here to merge"
        message = f"Print Splitter Merge: {selection} | Right-click clear · Esc cancel"
        if notice:
            message = f"Print Splitter Merge: {notice} | Right-click clear · Esc cancel"
        context.workspace.status_text_set(message)
        if context.area:
            context.area.tag_redraw()

    def _restore_modifiers(self):
        for modifier, visible in getattr(self, "modifier_visibility", ()):
            try:
                modifier.show_viewport = visible
            except ReferenceError:
                pass

    def _finish(self, context, cancelled=False):
        self._restore_modifiers()
        if self.cursor_is_modal:
            self.window.cursor_modal_restore()
            self.cursor_is_modal = False
        context.workspace.status_text_set(None)
        if context.area:
            context.area.tag_redraw()
        return {"CANCELLED" if cancelled else "FINISHED"}

    def _merge(self, context, source_id, destination_id):
        if source_id == destination_id:
            self._set_status(context, notice="Choose two different Face Sets")
            return None
        try:
            count = merge_face_sets(self.obj, source_id, destination_id)
        except (RuntimeError, ValueError) as exc:
            self._set_status(context, notice=str(exc))
            return None
        _sync_face_set_merge_selection(context, self.obj, source_id, destination_id)
        self.report({"INFO"}, f"Merged {count} faces from Face Set {source_id} into Face Set {destination_id}.")
        return self._finish(context)

    def modal(self, context, event):
        if context.active_object is not self.obj or context.mode != "SCULPT":
            return self._finish(context, cancelled=True)
        if event.type in {"MIDDLEMOUSE", "NDOF_MOTION", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        if event.type == "ESC" and event.value == "PRESS":
            return self._finish(context, cancelled=True)
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            selection = self.selection.confirm()
            if selection is None:
                self._set_status(context, notice="Click a source and a different target Face Set first")
                return {"RUNNING_MODAL"}
            result = self._merge(context, *selection)
            return result or {"RUNNING_MODAL"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            self.selection.clear()
            self._set_status(context, notice="Selection cleared; click a source Face Set")
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            self.left_down = True
            self.press_coord = self._event_coord(event)
            pressed_id = self._face_set_at(*self.press_coord)
            self.dragged = False
            if self.selection.source_id is None and pressed_id is not None:
                self.selection.click(pressed_id)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            coord = self._event_coord(event)
            hover_id = self._face_set_at(*coord)
            if self.left_down and self.press_coord is not None:
                dx = coord[0] - self.press_coord[0]
                dy = coord[1] - self.press_coord[1]
                self.dragged = self.dragged or math.hypot(dx, dy) >= self.DRAG_THRESHOLD_PX
            self._set_status(context, hover_id=hover_id)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self.left_down:
            self.left_down = False
            release_id = self._face_set_at(*self._event_coord(event))
            if release_id is None:
                self._set_status(context, notice="Click a visible Face Set region")
                return {"RUNNING_MODAL"}
            if self.dragged:
                selection = self.selection.drag_to(release_id)
                if selection is not None:
                    result = self._merge(context, *selection)
                    return result or {"RUNNING_MODAL"}
            self.selection.click(release_id)
            self._set_status(context)
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._finish(context, cancelled=True)


class PSS_OT_analyze_geometry(bpy.types.Operator):
    bl_idname = "print_splitter.analyze_geometry"
    bl_label = "Analyze Geometry"
    bl_description = "Use Blender's fast native normal grouping or disconnected-part detection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and obj.get(ROLE_KEY) in {ROLE_WORKING, ROLE_DIVISION}
            and not getattr(obj, "use_dynamic_topology_sculpting", False)
        )

    def execute(self, context):
        settings = context.scene.print_splitter_settings
        try:
            counts, largest_id = analyze_geometry(
                context.active_object,
                settings.geometry_partition_method,
                settings.geometry_angle_degrees,
            )
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        obj = context.active_object
        settings.geometry_mother_face_set = f"FACE_SET_{largest_id}"
        alternate = max(
            (face_id for face_id in counts if face_id != largest_id),
            key=lambda face_id: counts[face_id],
            default=largest_id,
        )
        settings.geometry_target_face_set = f"FACE_SET_{alternate}"
        if obj.get(PART_ID_KEY):
            obj[MOTHER_PART_ID_KEY] = obj[PART_ID_KEY]
        self.report(
            {"INFO"},
            f"Generated {len(counts)} regions; largest Face Set {largest_id} is the initial mother.",
        )
        return {"FINISHED"}


class PSS_OT_refresh_geometry_regions(bpy.types.Operator):
    bl_idname = "print_splitter.refresh_geometry_regions"
    bl_label = "Refresh Region List"
    bl_description = "Refresh the region selector after editing with Blender's native Face Set brush"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and bool(obj.get(GEOMETRY_SEGMENTATION_KEY))
            and not getattr(obj, "use_dynamic_topology_sculpting", False)
        )

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.print_splitter_settings
        counts = face_set_counts(obj)
        if not counts:
            self.report({"ERROR"}, "No generated Face Sets were found. Analyze the mesh again.")
            return {"CANCELLED"}
        _write_summary(obj)
        active_id = int(obj.get(FACE_SET_KEY, TARGET_FACE_SET))
        if active_id not in counts:
            active_id = max(counts, key=counts.get)
        mother_id = int(obj.get(GEOMETRY_MOTHER_FACE_SET_KEY, TARGET_FACE_SET))
        if mother_id not in counts:
            mother_id = max(counts, key=counts.get)
        settings.geometry_mother_face_set = f"FACE_SET_{mother_id}"
        if active_id == mother_id:
            active_id = next((face_id for face_id in counts if face_id != mother_id), mother_id)
        settings.geometry_target_face_set = f"FACE_SET_{active_id}"
        self.report({"INFO"}, f"Refreshed {len(counts)} Face Set regions.")
        return {"FINISHED"}


class PSS_OT_native_faceset_brush(bpy.types.Operator):
    bl_idname = "print_splitter.native_faceset_brush"
    bl_label = "Use Native Face Set Brush"
    bl_description = "Activate Blender's Draw Face Sets brush to refine the generated regions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and bool(obj.get(GEOMETRY_SEGMENTATION_KEY))
            and not getattr(obj, "use_dynamic_topology_sculpting", False)
        )

    def execute(self, context):
        try:
            result = bpy.ops.wm.tool_set_by_id(name="builtin_brush.draw_face_sets")
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Could not activate Blender's Face Set brush: {exc}")
            return {"CANCELLED"}
        if "FINISHED" not in result:
            self.report({"ERROR"}, "Blender could not activate the Draw Face Sets brush.")
            return {"CANCELLED"}
        self.report({"INFO"}, "Blender's Draw Face Sets brush is active.")
        return {"FINISHED"}


class PSS_OT_manual_faceset_mode(bpy.types.Operator):
    bl_idname = "print_splitter.manual_faceset_mode"
    bl_label = "Switch to Manual Paint"
    bl_description = "Clear generated regions and return to the Print Splitter paint brush"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == "SCULPT" and is_mesh_object(obj) and bool(obj.get(GEOMETRY_SEGMENTATION_KEY))

    def execute(self, context):
        obj = context.active_object
        attribute = ensure_face_sets(obj.data)
        values = array("i", [BACKGROUND_FACE_SET]) * len(obj.data.polygons)
        if values:
            attribute.data.foreach_set("value", values)
        obj.data.update()
        obj[FACE_SET_KEY] = TARGET_FACE_SET
        obj.pop(GEOMETRY_SEGMENTATION_KEY, None)
        obj.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
        obj.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
        obj.update_tag(refresh={"DATA"})
        context.area.tag_redraw()
        self.report({"INFO"}, "Generated regions cleared. Manual Face Set painting is ready.")
        return {"FINISHED"}


CLASSES = (
    PSS_OT_analyze_geometry,
    PSS_OT_start_face_set_merge,
    PSS_OT_refresh_geometry_regions,
    PSS_OT_native_faceset_brush,
    PSS_OT_manual_faceset_mode,
)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

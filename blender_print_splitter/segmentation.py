"""Geometry-only Face Set generation and region management."""

from __future__ import annotations

from array import array
import json
import math

import bpy
from mathutils import Matrix
from .registration import register_classes, unregister_classes

from .core import (
    BACKGROUND_FACE_SET,
    FACE_SET_ATTRIBUTE,
    FACE_SET_KEY,
    GEOMETRY_FACE_SET_SUMMARY_KEY,
    GEOMETRY_SEGMENTATION_KEY,
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


def _write_summary(obj):
    obj[GEOMETRY_FACE_SET_SUMMARY_KEY] = json.dumps(face_set_counts(obj))


def _world_face_area(polygon, matrix, normal_matrix, determinant):
    transformed_normal = normal_matrix @ polygon.normal
    normal_scale = transformed_normal.length
    if normal_scale < 1e-12:
        return max(float(polygon.area), 0.0)
    return max(float(polygon.area), 0.0) * determinant * normal_scale


def analyze_geometry(obj, method, angle_degrees):
    """Use Blender's native flood fill to analyze geometry without marked edge data."""
    if not is_mesh_object(obj) or not obj.data.polygons:
        raise ValueError("Select a mesh with faces to analyze.")
    obj.pop(GEOMETRY_SEGMENTATION_KEY, None)
    obj.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
    reset_face_sets(obj.data)

    if method == "SURFACE_FOLDS":
        threshold = math.cos(math.radians(angle_degrees))
        result = bpy.ops.sculpt.face_sets_init(mode="NORMALS", threshold=threshold)
        marker = "SURFACE_FOLDS"
    elif method == "LOOSE_PARTS":
        result = bpy.ops.sculpt.face_sets_init(mode="LOOSE_PARTS", threshold=0.5)
        marker = "LOOSE_PARTS"
    else:
        raise ValueError("Choose a supported geometry analysis method.")
    if "FINISHED" not in result:
        raise RuntimeError("Blender could not generate Face Sets from the mesh geometry.")

    attribute = ensure_face_sets(obj.data)
    values = _read_values(attribute)
    matrix = obj.matrix_world.to_3x3()
    determinant = abs(matrix.determinant())
    if determinant < 1e-12:
        matrix = Matrix.Identity(3)
        determinant = 1.0
    try:
        normal_matrix = matrix.inverted().transposed()
    except ValueError:
        normal_matrix = Matrix.Identity(3)
        determinant = 1.0

    counts = {}
    areas = {}
    remapped_ids = {}
    for index, polygon in enumerate(obj.data.polygons):
        old_id = int(values[index])
        new_id = remapped_ids.get(old_id)
        if new_id is None:
            new_id = TARGET_FACE_SET + len(remapped_ids)
            remapped_ids[old_id] = new_id
        values[index] = new_id
        counts[new_id] = counts.get(new_id, 0) + 1
        areas[new_id] = areas.get(new_id, 0.0) + _world_face_area(
            polygon,
            matrix,
            normal_matrix,
            determinant,
        )
    if values:
        attribute.data.foreach_set("value", values)
    obj.data.update()

    largest_id = max(areas, key=areas.get)
    obj[FACE_SET_KEY] = largest_id
    _write_summary(obj)
    obj[GEOMETRY_SEGMENTATION_KEY] = marker
    obj.update_tag(refresh={"DATA"})
    return counts, largest_id


def face_set_counts(obj):
    attribute = obj.data.attributes.get(FACE_SET_ATTRIBUTE) if is_mesh_object(obj) else None
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        return {}
    values = _read_values(attribute)
    counts = {}
    for value in values:
        value = int(value)
        if value >= TARGET_FACE_SET:
            counts[value] = counts.get(value, 0) + 1
    return counts


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


class PSS_OT_analyze_geometry(bpy.types.Operator):
    bl_idname = "print_splitter.analyze_geometry"
    bl_label = "Analyze Geometry"
    bl_description = "Create temporary Face Sets from surface normals or disconnected parts"
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
        settings.geometry_target_face_set = f"FACE_SET_{largest_id}"
        alternate = next((face_id for face_id in counts if face_id != largest_id), largest_id)
        settings.geometry_merge_into_face_set = f"FACE_SET_{alternate}"
        self.report({"INFO"}, f"Generated {len(counts)} geometry regions.")
        return {"FINISHED"}


class PSS_OT_merge_geometry_facesets(bpy.types.Operator):
    bl_idname = "print_splitter.merge_geometry_facesets"
    bl_label = "Merge Face Sets"
    bl_description = "Relabel the selected region into the destination Face Set without changing geometry"
    bl_options = {"REGISTER", "UNDO"}

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
        settings = context.scene.print_splitter_settings
        try:
            source_id = int(settings.geometry_target_face_set.rsplit("_", 1)[1])
            destination_id = int(settings.geometry_merge_into_face_set.rsplit("_", 1)[1])
        except (AttributeError, IndexError, ValueError):
            return False
        return source_id != destination_id

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.print_splitter_settings
        try:
            source_id = int(settings.geometry_target_face_set.rsplit("_", 1)[1])
            destination_id = int(settings.geometry_merge_into_face_set.rsplit("_", 1)[1])
            count = merge_face_sets(obj, source_id, destination_id)
        except (AttributeError, IndexError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.geometry_target_face_set = f"FACE_SET_{destination_id}"
        remaining = face_set_counts(obj)
        alternate = next((face_id for face_id in remaining if face_id != destination_id), destination_id)
        settings.geometry_merge_into_face_set = f"FACE_SET_{alternate}"
        self.report({"INFO"}, f"Merged {count} faces into Face Set {destination_id}.")
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
        settings.geometry_target_face_set = f"FACE_SET_{active_id}"
        destination_id = next((face_id for face_id in counts if face_id != active_id), active_id)
        settings.geometry_merge_into_face_set = f"FACE_SET_{destination_id}"
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
        obj.update_tag(refresh={"DATA"})
        context.area.tag_redraw()
        self.report({"INFO"}, "Generated regions cleared. Manual Face Set painting is ready.")
        return {"FINISHED"}


CLASSES = (
    PSS_OT_analyze_geometry,
    PSS_OT_merge_geometry_facesets,
    PSS_OT_refresh_geometry_regions,
    PSS_OT_native_faceset_brush,
    PSS_OT_manual_faceset_mode,
)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

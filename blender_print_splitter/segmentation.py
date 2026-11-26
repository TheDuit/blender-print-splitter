"""Geometry-only Face Set generation and region management."""

from __future__ import annotations

from array import array
from collections import defaultdict
import json
import math

import bpy
from mathutils import Matrix, Vector
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


def _write_summary(obj):
    obj[GEOMETRY_FACE_SET_SUMMARY_KEY] = json.dumps(face_set_counts(obj))


def _world_face_area(polygon, matrix, normal_matrix, determinant):
    transformed_normal = normal_matrix @ polygon.normal
    normal_scale = transformed_normal.length
    if normal_scale < 1e-12:
        return max(float(polygon.area), 0.0)
    return max(float(polygon.area), 0.0) * determinant * normal_scale


def _face_region_labels(obj, method, angle_degrees, feature_scale_percent, minimum_region_percent):
    """Build connected regions from surface folds, without relying on edge flags."""
    mesh = obj.data
    face_count = len(mesh.polygons)
    edge_count = len(mesh.edges)
    labels = array("i", [-1]) * face_count
    edge_faces = array("i", [-1]) * (edge_count * 2)
    loop_edges = array("i", [0]) * len(mesh.loops)
    mesh.loops.foreach_get("edge_index", loop_edges)
    if method == "SURFACE_FOLDS":
        mesh.update()
        normals = array("f", [0.0]) * (face_count * 3)
        mesh.polygons.foreach_get("normal", normals)
        try:
            normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        except ValueError:
            normal_matrix = Matrix.Identity(3)
        for face_index in range(face_count):
            offset = face_index * 3
            x = normals[offset]
            y = normals[offset + 1]
            z = normals[offset + 2]
            nx = normal_matrix[0][0] * x + normal_matrix[0][1] * y + normal_matrix[0][2] * z
            ny = normal_matrix[1][0] * x + normal_matrix[1][1] * y + normal_matrix[1][2] * z
            nz = normal_matrix[2][0] * x + normal_matrix[2][1] * y + normal_matrix[2][2] * z
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            if length > 1e-12:
                normals[offset] = nx / length
                normals[offset + 1] = ny / length
                normals[offset + 2] = nz / length
        bounds_min = [math.inf, math.inf, math.inf]
        bounds_max = [-math.inf, -math.inf, -math.inf]
        for vertex in mesh.vertices:
            for axis in range(3):
                coordinate = vertex.co[axis]
                bounds_min[axis] = min(bounds_min[axis], coordinate)
                bounds_max[axis] = max(bounds_max[axis], coordinate)
        diagonal = math.sqrt(sum((bounds_max[axis] - bounds_min[axis]) ** 2 for axis in range(3)))
        feature_scale = max(diagonal * feature_scale_percent / 100.0, 1e-12)
        edge_lengths = array("f", [0.0]) * edge_count
        for edge in mesh.edges:
            first, second = edge.vertices
            edge_lengths[edge.index] = (mesh.vertices[first].co - mesh.vertices[second].co).length
        angle_per_scale = math.radians(angle_degrees) / feature_scale
    else:
        normals = None
        edge_lengths = None
        angle_per_scale = 0.0

    for polygon in mesh.polygons:
        face_index = polygon.index
        start = polygon.loop_start
        end = start + polygon.loop_total
        for loop_index in range(start, end):
            edge_index = loop_edges[loop_index]
            offset = edge_index * 2
            if edge_faces[offset] < 0:
                edge_faces[offset] = face_index
            elif edge_faces[offset + 1] < 0:
                edge_faces[offset + 1] = face_index

    region_areas = array("d")
    region_count = 0
    for seed in range(face_count):
        if labels[seed] >= 0:
            continue
        labels[seed] = region_count
        stack = [seed]
        area = 0.0
        while stack:
            face_index = stack.pop()
            polygon = mesh.polygons[face_index]
            area += max(float(polygon.area), 0.0)
            start = polygon.loop_start
            end = start + polygon.loop_total
            for loop_index in range(start, end):
                edge_index = loop_edges[loop_index]
                offset = edge_index * 2
                first = edge_faces[offset]
                second = edge_faces[offset + 1]
                if second < 0:
                    continue
                other_index = second if first == face_index else first
                if other_index < 0 or labels[other_index] >= 0:
                    continue
                if normals is not None:
                    normal_offset = face_index * 3
                    other_offset = other_index * 3
                    dot = sum(
                        normals[normal_offset + axis] * normals[other_offset + axis]
                        for axis in range(3)
                    )
                    edge_angle_limit = min(
                        math.radians(min(angle_degrees * 1.5, 89.0)),
                        angle_per_scale * edge_lengths[edge_index],
                    )
                    if dot < math.cos(edge_angle_limit):
                        continue
                labels[other_index] = region_count
                stack.append(other_index)
        region_areas.append(area)
        region_count += 1

    if method == "SURFACE_FOLDS" and region_count > 1 and minimum_region_percent > 0.0:
        minimum_area = sum(region_areas) * (minimum_region_percent / 100.0)
        parents = array("i", range(region_count))
        region_heads = array("i", [-1]) * region_count
        region_tails = array("i", [-1]) * region_count
        next_faces = array("i", [-1]) * face_count
        for face_index, region_id in enumerate(labels):
            if region_heads[region_id] < 0:
                region_heads[region_id] = face_index
            else:
                next_faces[region_tails[region_id]] = face_index
            region_tails[region_id] = face_index

        def find(region_id):
            while parents[region_id] != region_id:
                parents[region_id] = parents[parents[region_id]]
                region_id = parents[region_id]
            return region_id

        for source in range(region_count):
            source = find(source)
            while region_areas[source] < minimum_area:
                neighbor_scores = defaultdict(float)
                face_index = region_heads[source]
                while face_index >= 0:
                    polygon = mesh.polygons[face_index]
                    start = polygon.loop_start
                    end = start + polygon.loop_total
                    for loop_index in range(start, end):
                        edge_offset = loop_edges[loop_index] * 2
                        first = edge_faces[edge_offset]
                        second = edge_faces[edge_offset + 1]
                        if second < 0:
                            continue
                        other_face = second if first == face_index else first
                        destination = find(labels[other_face])
                        if destination != source:
                            neighbor_scores[destination] += edge_lengths[loop_edges[loop_index]]
                    face_index = next_faces[face_index]
                if not neighbor_scores:
                    break
                destination = max(
                    neighbor_scores,
                    key=lambda region_id: (neighbor_scores[region_id], region_areas[region_id]),
                )
                parents[source] = destination
                region_areas[destination] += region_areas[source]
                if region_heads[destination] < 0:
                    region_heads[destination] = region_heads[source]
                elif region_heads[source] >= 0:
                    next_faces[region_tails[destination]] = region_heads[source]
                if region_tails[source] >= 0:
                    region_tails[destination] = region_tails[source]
                region_heads[source] = -1
                region_tails[source] = -1
                source = find(destination)

        remapped_regions = {}
        next_region = 0
        for face_index, region_id in enumerate(labels):
            root = find(region_id)
            if root not in remapped_regions:
                remapped_regions[root] = next_region
                next_region += 1
            labels[face_index] = remapped_regions[root]
        region_count = next_region

    return labels, region_count


def analyze_geometry(
    obj,
    method,
    angle_degrees,
    feature_scale_percent=10.0,
    minimum_region_percent=3.0,
):
    """Generate geometry-based Face Sets and merge tiny fold patches into neighbors."""
    if not is_mesh_object(obj) or not obj.data.polygons:
        raise ValueError("Select a mesh with faces to analyze.")
    if method not in {"SURFACE_FOLDS", "LOOSE_PARTS"}:
        raise ValueError("Choose a supported geometry analysis method.")
    obj.pop(GEOMETRY_SEGMENTATION_KEY, None)
    obj.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
    obj.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
    reset_face_sets(obj.data)

    labels, region_count = _face_region_labels(
        obj,
        method,
        angle_degrees,
        feature_scale_percent,
        minimum_region_percent,
    )

    attribute = ensure_face_sets(obj.data)
    values = array("i", [0]) * len(attribute.data)
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
        region_id = int(labels[index])
        new_id = remapped_ids.get(region_id)
        if new_id is None:
            new_id = TARGET_FACE_SET + len(remapped_ids)
            remapped_ids[region_id] = new_id
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
    obj[GEOMETRY_SEGMENTATION_KEY] = method
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


def _most_central_face_set_id(obj, candidates=None):
    """Pick the generated region whose area-weighted center is nearest the mesh center."""
    mesh = obj.data
    attribute = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None or not mesh.vertices or not mesh.polygons:
        return None
    values = _read_values(attribute)
    candidate_ids = set(candidates or (int(value) for value in values if value >= TARGET_FACE_SET))
    if not candidate_ids:
        return None

    matrix = obj.matrix_world
    linear = matrix.to_3x3()
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    for vertex in mesh.vertices:
        world_vertex = matrix @ vertex.co
        for axis in range(3):
            minimum[axis] = min(minimum[axis], world_vertex[axis])
            maximum[axis] = max(maximum[axis], world_vertex[axis])
    mesh_center = (minimum + maximum) * 0.5
    try:
        normal_matrix = linear.inverted().transposed()
        determinant = abs(linear.determinant())
    except ValueError:
        normal_matrix = Matrix.Identity(3)
        determinant = 1.0

    weighted_centers = {face_set_id: Vector((0.0, 0.0, 0.0)) for face_set_id in candidate_ids}
    region_areas = {face_set_id: 0.0 for face_set_id in candidate_ids}
    for polygon, face_set_id in zip(mesh.polygons, values):
        face_set_id = int(face_set_id)
        if face_set_id not in candidate_ids:
            continue
        area = _world_face_area(polygon, linear, normal_matrix, determinant)
        if area <= 1e-12:
            area = 1.0
        weighted_centers[face_set_id] += matrix @ polygon.center * area
        region_areas[face_set_id] += area

    ranked = []
    for face_set_id, total_area in region_areas.items():
        if total_area <= 0.0:
            continue
        center = weighted_centers[face_set_id] / total_area
        ranked.append(((center - mesh_center).length_squared, -total_area, face_set_id))
    return min(ranked)[2] if ranked else None


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
    bl_description = "Create temporary Face Sets from geometric curvature or disconnected parts"
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
                settings.geometry_feature_scale_percent,
                settings.geometry_min_region_percent,
            )
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        obj = context.active_object
        central_id = _most_central_face_set_id(obj, counts) or largest_id
        settings.geometry_mother_face_set = f"FACE_SET_{central_id}"
        alternate = max(
            (face_id for face_id in counts if face_id != central_id),
            key=lambda face_id: counts[face_id],
            default=central_id,
        )
        settings.geometry_target_face_set = f"FACE_SET_{alternate}"
        settings.geometry_merge_into_face_set = f"FACE_SET_{central_id}"
        if obj.get(PART_ID_KEY):
            obj[MOTHER_PART_ID_KEY] = obj[PART_ID_KEY]
        self.report(
            {"INFO"},
            f"Generated {len(counts)} editable regions; Face Set {central_id} is the initial mother.",
        )
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
        mother_id = int(obj.get(GEOMETRY_MOTHER_FACE_SET_KEY, TARGET_FACE_SET))
        if source_id == mother_id:
            settings.geometry_mother_face_set = f"FACE_SET_{destination_id}"
        remaining = face_set_counts(obj)
        alternate = next(
            (face_id for face_id in remaining if face_id != destination_id),
            destination_id,
        )
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
        mother_id = int(obj.get(GEOMETRY_MOTHER_FACE_SET_KEY, TARGET_FACE_SET))
        if mother_id not in counts:
            mother_id = max(counts, key=counts.get)
        settings.geometry_mother_face_set = f"FACE_SET_{mother_id}"
        if active_id == mother_id:
            active_id = next((face_id for face_id in counts if face_id != mother_id), mother_id)
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
        obj.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
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

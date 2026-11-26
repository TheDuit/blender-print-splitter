"""Region cleanup, Face Set-to-mask conversion, and one-piece extraction."""

from __future__ import annotations

import heapq
import math
import uuid

import bpy
from mathutils import Vector
from .registration import register_classes, unregister_classes

from .core import (
    BACKGROUND_FACE_SET,
    FACE_SET_ATTRIBUTE,
    FACE_SET_KEY,
    GEOMETRY_FACE_SET_SUMMARY_KEY,
    GEOMETRY_MOTHER_FACE_SET_KEY,
    GEOMETRY_SEGMENTATION_KEY,
    MASK_ATTRIBUTE,
    MOTHER_PART_ID_KEY,
    PAIR_ID_KEY,
    add_pair_id,
    PART_ID_KEY,
    ROLE_KEY,
    ROLE_DIVISION,
    SOURCE_ID_KEY,
    TARGET_FACE_SET,
    ROLE_WORKING,
    clear_mask,
    collection_for_parts,
    is_mesh_object,
    mark_division,
    mm_to_bu,
    move_object_to_collection,
    next_part_name,
    reset_face_sets,
)


def _face_graph(mesh, matrix_world):
    centers = [matrix_world @ polygon.center for polygon in mesh.polygons]
    edge_faces = {}
    for poly in mesh.polygons:
        for edge_key in poly.edge_keys:
            key = tuple(sorted(edge_key))
            edge_faces.setdefault(key, []).append(poly.index)
    adjacency = [[] for _ in mesh.polygons]
    for linked in edge_faces.values():
        if len(linked) == 2:
            a, b = linked
            cost = (centers[a] - centers[b]).length
            adjacency[a].append((b, cost))
            adjacency[b].append((a, cost))
    return centers, adjacency


def _read_int_attribute(attribute, length):
    values = [0] * length
    if length:
        attribute.data.foreach_get("value", values)
    return values


def _write_int_attribute(attribute, values):
    if values:
        attribute.data.foreach_set("value", values)


def _components(values, adjacency, target_id):
    seen = set()
    result = []
    for start, value in enumerate(values):
        if value != target_id or start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = []
        while stack:
            face = stack.pop()
            component.append(face)
            for neighbor, _cost in adjacency[face]:
                if neighbor not in seen and values[neighbor] == target_id:
                    seen.add(neighbor)
                    stack.append(neighbor)
        result.append(component)
    return result


def _face_area(mesh, index):
    return max(float(mesh.polygons[index].area), 0.0)


def _shortest_component_path(adjacency, centers, component_a, component_b):
    target = set(component_b)
    distances = {}
    previous = {}
    queue = []
    for face in component_a:
        distances[face] = 0.0
        heapq.heappush(queue, (0.0, face))
    reached = None
    while queue:
        distance, face = heapq.heappop(queue)
        if distance != distances.get(face):
            continue
        if face in target:
            reached = face
            break
        for neighbor, _edge_cost in adjacency[face]:
            # A path through face centers approximates the surface gap and avoids
            # merging regions that are close in 3D but far apart on the topology.
            step = max((centers[face] - centers[neighbor]).length, 1e-9)
            candidate = distance + step
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = face
                heapq.heappush(queue, (candidate, neighbor))
    if reached is None:
        return None, math.inf
    path = [reached]
    while path[-1] not in component_a:
        path.append(previous[path[-1]])
    path.reverse()
    return path, distances[reached]


def clean_face_set(obj, settings):
    mesh = obj.data
    attribute = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        raise ValueError("Paint a region or analyze the mesh to create Face Sets first.")
    target_id = int(obj.get(FACE_SET_KEY, TARGET_FACE_SET))
    values = _read_int_attribute(attribute, len(mesh.polygons))
    if target_id not in values:
        raise ValueError("No painted region was found.")

    centers, adjacency = _face_graph(mesh, obj.matrix_world)
    components = _components(values, adjacency, target_id)
    if not components:
        raise ValueError("No painted region was found.")
    areas = [sum(_face_area(mesh, face) for face in component) for component in components]
    largest_area = max(areas, default=0.0)
    threshold = largest_area * (settings.small_island_percent / 100.0)
    removed = 0
    for component, area in zip(components, areas):
        if len(components) > 1 and area < threshold:
            for face in component:
                values[face] = BACKGROUND_FACE_SET
                removed += 1

    _write_int_attribute(attribute, values)
    mesh.update()
    components = _components(values, adjacency, target_id)

    merged = 0
    max_gap = mm_to_bu(settings.merge_gap_mm, bpy.context.scene)
    if max_gap > 0.0 and 1 < len(components) <= 32:
        changed = True
        while changed:
            changed = False
            components = _components(values, adjacency, target_id)
            for index, component_a in enumerate(components):
                for component_b in components[index + 1 :]:
                    path, distance = _shortest_component_path(adjacency, centers, component_a, component_b)
                    if path and distance <= max_gap:
                        for face in path:
                            if values[face] != target_id:
                                values[face] = target_id
                        merged += 1
                        changed = True
                        break
                if changed:
                    break
        _write_int_attribute(attribute, values)
        mesh.update()

    remaining = len(_components(values, adjacency, target_id))
    return removed, merged, remaining


def smooth_face_set_labels(obj, target_id, iterations=1):
    """Relax the Face Set boundary by relabeling faces without moving vertices."""
    mesh = obj.data
    attribute = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        raise ValueError("The mesh has no Face Set attribute.")
    values = _read_int_attribute(attribute, len(mesh.polygons))
    if target_id not in values:
        raise ValueError("Paint a region with the Print Splitter brush first.")

    _centers, adjacency = _face_graph(mesh, obj.matrix_world)
    for _iteration in range(max(1, iterations)):
        updated = values.copy()
        for face_index, neighbors in enumerate(adjacency):
            if not neighbors:
                continue
            target_neighbors = sum(values[neighbor] == target_id for neighbor, _cost in neighbors)
            background_neighbors = len(neighbors) - target_neighbors
            if target_neighbors > background_neighbors:
                updated[face_index] = target_id
            elif background_neighbors > target_neighbors:
                updated[face_index] = BACKGROUND_FACE_SET
        if updated == values or target_id not in updated:
            break
        values = updated

    _write_int_attribute(attribute, values)
    mesh.update()
    obj.update_tag(refresh={"DATA"})
    return values.count(target_id)


class PSS_OT_smooth_faceset(bpy.types.Operator):
    """Relax Face Set labels only; leave the mesh surface unchanged."""

    bl_idname = "print_splitter.smooth_faceset"
    bl_label = "Smooth Face Set Boundary"
    bl_description = "Smooth the Face Set boundary without moving mesh vertices"
    bl_options = {"REGISTER", "UNDO"}

    iterations: bpy.props.IntProperty(
        name="Iterations",
        default=1,
        min=1,
        max=10,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and obj.get(ROLE_KEY) in {ROLE_WORKING, ROLE_DIVISION}
            and not obj.get(GEOMETRY_SEGMENTATION_KEY)
        )

    def execute(self, context):
        obj = context.active_object
        target_id = int(obj.get(FACE_SET_KEY, TARGET_FACE_SET))
        try:
            count = smooth_face_set_labels(obj, target_id, self.iterations)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Smoothed the Face Set boundary; {count} faces remain selected.")
        return {"FINISHED"}


def face_set_to_mask(obj, target_id, threshold=0.5):
    """Map the selected face set to the point-domain sculpt mask."""
    mesh = obj.data
    face_sets = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if face_sets is None:
        raise ValueError("The mesh has no Face Sets.")
    face_values = _read_int_attribute(face_sets, len(mesh.polygons))
    selected_faces = [value == target_id for value in face_values]
    selected_count = sum(selected_faces)
    if selected_count == 0:
        raise ValueError("No faces belong to the active Face Set.")

    selected_per_vertex = [0] * len(mesh.vertices)
    incident_per_vertex = [0] * len(mesh.vertices)
    for polygon in mesh.polygons:
        selected = selected_faces[polygon.index]
        for vertex_index in polygon.vertices:
            incident_per_vertex[vertex_index] += 1
            if selected:
                selected_per_vertex[vertex_index] += 1

    mask = mesh.attributes.get(MASK_ATTRIBUTE)
    if mask is None or mask.domain != "POINT" or mask.data_type != "FLOAT":
        if mask is not None:
            mesh.attributes.remove(mask)
        mask = mesh.attributes.new(name=MASK_ATTRIBUTE, type="FLOAT", domain="POINT")
    values = [
        (selected_per_vertex[index] / incident_per_vertex[index]) if incident_per_vertex[index] else 0.0
        for index in range(len(mesh.vertices))
    ]
    if values:
        mask.data.foreach_set("value", values)
    mesh.update()
    obj.update_tag(refresh={"DATA"})
    return selected_count


def _seam_frame(obj, target_id):
    """Estimate a shared connector origin and axis from the painted boundary."""
    mesh = obj.data
    attribute = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None:
        return None
    values = _read_int_attribute(attribute, len(mesh.polygons))
    edge_faces = {}
    for polygon in mesh.polygons:
        for edge_key in polygon.edge_keys:
            edge_faces.setdefault(tuple(sorted(edge_key)), []).append(polygon.index)

    boundary_edges = []
    boundary_vertices = set()
    for edge, linked_faces in edge_faces.items():
        if len(linked_faces) == 2 and (values[linked_faces[0]] == target_id) != (values[linked_faces[1]] == target_id):
            boundary_edges.append(edge)
            boundary_vertices.update(edge)
    if not boundary_edges:
        return None

    matrix = obj.matrix_world
    location = sum(
        (matrix @ mesh.vertices[index].co for index in boundary_vertices),
        Vector((0.0, 0.0, 0.0)),
    )
    location /= len(boundary_vertices)

    selected_center = Vector((0.0, 0.0, 0.0))
    selected_area = 0.0
    remainder_center = Vector((0.0, 0.0, 0.0))
    remainder_area = 0.0
    for polygon in mesh.polygons:
        area = max(float(polygon.area), 1e-12)
        center = matrix @ polygon.center
        if values[polygon.index] == target_id:
            selected_center += center * area
            selected_area += area
        else:
            remainder_center += center * area
            remainder_area += area
    if selected_area <= 0.0 or remainder_area <= 0.0:
        return None
    axis = (remainder_center / remainder_area) - (selected_center / selected_area)
    if axis.length_squared < 1e-12:
        return None
    return location, axis.normalized()


def _select_active(context, obj):
    for selected in list(context.selected_objects):
        selected.select_set(False)
    obj.hide_set(False)
    obj.hide_select = False
    obj.select_set(True)
    context.view_layer.objects.active = obj


class PSS_OT_extract_part(bpy.types.Operator):
    bl_idname = "print_splitter.extract_part"
    bl_label = "Extract Part"
    bl_description = "Split the painted region into matching capped mesh parts and add a connector"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        from .connectors import has_pending_connector

        return (
            context.mode == "SCULPT"
            and is_mesh_object(obj)
            and obj.get(ROLE_KEY) in {ROLE_WORKING, ROLE_DIVISION}
            and not getattr(obj, "use_dynamic_topology_sculpting", False)
            and not has_pending_connector(obj)
        )

    def execute(self, context):
        source = context.active_object
        settings = context.scene.print_splitter_settings
        geometry_mode = source.get(GEOMETRY_SEGMENTATION_KEY, "")
        if geometry_mode:
            try:
                target_id = int(settings.geometry_target_face_set.rsplit("_", 1)[1])
            except (AttributeError, IndexError, ValueError):
                self.report({"ERROR"}, "Choose a valid Face Set region to extract.")
                return {"CANCELLED"}
            source[FACE_SET_KEY] = target_id
        else:
            target_id = int(source.get(FACE_SET_KEY, TARGET_FACE_SET))
        mother_region_id = int(source.get(GEOMETRY_MOTHER_FACE_SET_KEY, 0))
        geometry_mother_mode = bool(geometry_mode and mother_region_id)
        if geometry_mother_mode and target_id == mother_region_id:
            self.report({"ERROR"}, "The mother region stays on the remainder. Choose another region to extract.")
            return {"CANCELLED"}
        try:
            removed, merged, remaining_components = clean_face_set(source, settings)
            face_count = face_set_to_mask(source, target_id, settings.mask_threshold)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        seam_frame = _seam_frame(source, target_id)
        if geometry_mother_mode and seam_frame is None:
            self.report({"ERROR"}, "No shared boundary was found. Refine the Face Set boundary before extracting this part.")
            return {"CANCELLED"}
        source_matrix = source.matrix_world.copy()
        old_objects = {obj.as_pointer() for obj in bpy.data.objects}
        source_part_id = source.get(PART_ID_KEY, "")
        source_id = source.get(SOURCE_ID_KEY, "")
        pair_id = uuid.uuid4().hex
        self.report(
            {"INFO"},
            f"Extracting {face_count} faces; removed islands: {removed}; merged regions: {merged}.",
        )

        try:
            # Mask Slice creates both complementary halves and fills the matching
            # interface loops. This avoids a separately solidified surface patch
            # extending through the remainder's volume.
            slice_result = bpy.ops.sculpt.paint_mask_slice(
                "EXEC_DEFAULT",
                mask_threshold=settings.mask_threshold,
                fill_holes=True,
                new_object=True,
            )
        except RuntimeError:
            slice_result = {"CANCELLED"}
        if "FINISHED" not in slice_result:
            self.report({"ERROR"}, "Blender could not create both sides of the split.")
            return {"CANCELLED"}

        created = [obj for obj in bpy.data.objects if obj.as_pointer() not in old_objects and obj.type == "MESH"]
        if not created:
            self.report({"ERROR"}, "Mask Slice finished without creating the selected part.")
            return {"CANCELLED"}
        part = created[-1]
        part.matrix_world = source_matrix
        part_source_id = source_id or uuid.uuid4().hex

        _select_active(context, source)
        if source.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        clear_mask(source.data)
        reset_face_sets(source.data)
        source[FACE_SET_KEY] = TARGET_FACE_SET
        source.pop(GEOMETRY_SEGMENTATION_KEY, None)
        source.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
        source.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
        mark_division(source, part_source_id)
        source["print_splitter_last_remaining_components"] = remaining_components
        part["print_splitter_prefix"] = "PS_Part"
        part[PART_ID_KEY] = uuid.uuid4().hex
        mark_division(part, part_source_id, parent_id=source_part_id)
        part.name = next_part_name(source.name)
        if geometry_mother_mode:
            mother_part_id = source.get(MOTHER_PART_ID_KEY) or source_part_id or source.get(PART_ID_KEY, "")
            if mother_part_id:
                source[MOTHER_PART_ID_KEY] = mother_part_id
                part[MOTHER_PART_ID_KEY] = mother_part_id
        clear_mask(part.data)
        reset_face_sets(part.data)
        part[FACE_SET_KEY] = TARGET_FACE_SET
        part.pop(GEOMETRY_SEGMENTATION_KEY, None)
        part.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
        part.pop(GEOMETRY_MOTHER_FACE_SET_KEY, None)
        move_object_to_collection(part, collection_for_parts(context.scene))

        has_remainder = source.name in bpy.data.objects and len(source.data.polygons) > 0
        if has_remainder:
            if seam_frame:
                from .connectors import create_connector_pair

                try:
                    seam_location, seam_axis = seam_frame
                    if geometry_mother_mode:
                        create_connector_pair(
                            context,
                            source,
                            part,
                            pair_id,
                            seam_location,
                            -seam_axis,
                        )
                    else:
                        create_connector_pair(
                            context,
                            part,
                            source,
                            pair_id,
                            seam_location,
                            seam_axis,
                        )
                    add_pair_id(source, pair_id)
                    add_pair_id(part, pair_id)
                except (RuntimeError, ValueError) as exc:
                    self.report({"WARNING"}, f"The split is complete, but the connector could not be created: {exc}")
            else:
                self.report({"WARNING"}, "The split is complete, but no shared boundary was found for a connector.")
        else:
            part.pop(PAIR_ID_KEY, None)

        if has_remainder:
            _select_active(context, part)
        else:
            if source.name in bpy.data.objects:
                source_mesh = source.data
                bpy.data.objects.remove(source, do_unlink=True)
                if source_mesh.users == 0:
                    bpy.data.meshes.remove(source_mesh)
            _select_active(context, part)
        if part.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if removed:
            self.report({"INFO"}, f"Ignored {removed} faces in small islands.")
        if has_remainder and seam_frame:
            self.report({"INFO"}, "The part was split and a connector pair was placed at the interface.")
        return {"FINISHED"}


CLASSES = (PSS_OT_smooth_faceset, PSS_OT_extract_part)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

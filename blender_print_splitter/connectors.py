"""Automatic connector previews, applied with a Manifold Boolean on confirmation."""

from __future__ import annotations

import math
import json
from array import array

import bpy
from .registration import register_classes, unregister_classes
from bpy.app.handlers import persistent
from mathutils import Vector

from .core import (
    PAIR_ID_KEY,
    PAIR_IDS_KEY,
    PART_ID_KEY,
    activate_only,
    has_pair_id,
    collection_for_connectors,
    is_mesh_object,
    mm_to_bu,
)


KIND_KEY = "print_splitter_helper_kind"
HELPER_PAIR_KEY = "print_splitter_helper_pair_id"
KIND_CONTROL = "CONTROL"
KIND_PIN = "PIN"
KIND_CUTTER = "CUTTER"
BOOLEAN_PREFIX = "PS Connector"
BOOLEAN_OVERLAP_MM = 0.25
CONFIRMED_PAIRS_KEY = "print_splitter_confirmed_connector_pairs"
CONFIRMED_SOLVER_KEY = "print_splitter_confirmed_boolean_solver"
PIN_TARGET_ID_KEY = "print_splitter_connector_pin_target_id"
SOCKET_TARGET_ID_KEY = "print_splitter_connector_socket_target_id"


def _cylinder_mesh(name, radius, length, start, segments=32):
    mesh = bpy.data.meshes.new(name)
    bottom = start
    top = start + length
    vertices = []
    for z in (bottom, top):
        for index in range(segments):
            angle = (2.0 * math.pi * index) / segments
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
    faces = [tuple(reversed(range(segments))), tuple(range(segments, segments * 2))]
    for index in range(segments):
        next_index = (index + 1) % segments
        faces.append((index, next_index, next_index + segments, index + segments))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def _dimensions(scene):
    settings = scene.print_splitter_settings
    diameter = mm_to_bu(settings.connector_diameter_mm, scene)
    depth = mm_to_bu(settings.connector_depth_mm, scene)
    embed_depth = mm_to_bu(settings.connector_embed_depth_mm, scene)
    radial_clearance = mm_to_bu(settings.connector_clearance_mm * 0.5, scene)
    overlap = mm_to_bu(BOOLEAN_OVERLAP_MM, scene)
    return (
        max(diameter * 0.5, 1e-6),
        max(depth, 1e-6),
        max(embed_depth, 1e-6),
        max(radial_clearance, 0.0),
        overlap,
    )


def _regenerate_helper(obj, scene):
    radius, depth, embed_depth, radial_clearance, overlap = _dimensions(scene)
    kind = obj.get(KIND_KEY)
    if kind == KIND_CUTTER:
        radius += radial_clearance
        start = -overlap
        length = depth + (overlap * 2.0)
    elif kind == KIND_PIN:
        start = -embed_depth
        length = embed_depth + depth + overlap
    elif kind != KIND_PIN:
        return
    mesh = _cylinder_mesh(
        obj.name + "_Mesh",
        radius,
        length,
        start=start,
    )
    old_mesh = obj.data
    obj.data = mesh
    if old_mesh and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    obj.update_tag(refresh={"DATA"})


def update_helpers(context):
    scene = context.scene if context else bpy.context.scene
    if not scene or not hasattr(scene, "print_splitter_settings"):
        return
    for obj in bpy.data.objects:
        if obj.get(KIND_KEY) in {KIND_PIN, KIND_CUTTER}:
            _regenerate_helper(obj, scene)


def helpers_for_pair(pair_id):
    helpers = {KIND_CONTROL: None, KIND_PIN: None, KIND_CUTTER: None}
    if not pair_id:
        return helpers
    for obj in bpy.data.objects:
        if obj.get(HELPER_PAIR_KEY) == pair_id:
            kind = obj.get(KIND_KEY)
            if kind in helpers and helpers[kind] is None:
                helpers[kind] = obj
    return helpers


def targets_for_pair(pair_id):
    control = helpers_for_pair(pair_id)[KIND_CONTROL]
    if control is None:
        return None, None
    return (
        _object_by_part_id(control.get(PIN_TARGET_ID_KEY, "")),
        _object_by_part_id(control.get(SOCKET_TARGET_ID_KEY, "")),
    )


def pair_is_confirmed(obj, pair_id):
    try:
        confirmed_pairs = json.loads(obj.get(CONFIRMED_PAIRS_KEY, "[]"))
    except (TypeError, ValueError):
        confirmed_pairs = []
    return pair_id in confirmed_pairs


def pending_connector_pairs(obj):
    try:
        pair_ids = json.loads(obj.get(PAIR_IDS_KEY, "[]"))
    except (TypeError, ValueError):
        pair_ids = []
    current_pair_id = obj.get(PAIR_ID_KEY, "")
    if current_pair_id and current_pair_id not in pair_ids:
        pair_ids.append(current_pair_id)
    try:
        confirmed_pairs = set(json.loads(obj.get(CONFIRMED_PAIRS_KEY, "[]")))
    except (TypeError, ValueError):
        confirmed_pairs = set()
    return [pair_id for pair_id in pair_ids if pair_id and pair_id not in confirmed_pairs]


def has_pending_connector(obj):
    return bool(obj and is_mesh_object(obj) and pending_connector_pairs(obj))


@persistent
def _disable_legacy_connector_previews(_unused=None):
    """Disable live Exact previews saved by earlier add-on versions."""
    try:
        objects = bpy.data.objects
    except AttributeError:
        # Add-on registration can run with Blender's restricted data proxy.
        # Timers retry after registration; load_post handles later file loads.
        return 0.1
    scene = bpy.context.scene
    for obj in objects:
        for modifier in obj.modifiers:
            if modifier.type == "BOOLEAN" and modifier.name.startswith(BOOLEAN_PREFIX):
                modifier.show_viewport = False
                modifier.show_render = False
        if scene and obj.get(KIND_KEY) in {KIND_PIN, KIND_CUTTER}:
            _regenerate_helper(obj, scene)
    return None


def _make_controller(context, pair_id, location, axis):
    settings = context.scene.print_splitter_settings
    name = f"PS_ConnectorControl_{pair_id[:6]}"
    control = bpy.data.objects.new(name, None)
    control[KIND_KEY] = KIND_CONTROL
    control[HELPER_PAIR_KEY] = pair_id
    control.location = location
    control.rotation_mode = "XYZ"
    control.rotation_euler = axis.normalized().to_track_quat("Z", "Y").to_euler()
    control.empty_display_type = "ARROWS"
    control.empty_display_size = max(mm_to_bu(settings.connector_diameter_mm * 2.0, context.scene), 0.005)
    control.show_in_front = True
    control.hide_render = True
    collection = collection_for_connectors(context.scene)
    collection.objects.link(control)
    return control


def _make_helper(context, name, kind, pair_id, controller):
    radius, depth, _embed_depth, radial_clearance, _overlap = _dimensions(context.scene)
    if kind == KIND_CUTTER:
        radius += radial_clearance
    mesh = _cylinder_mesh(
        name + "_Mesh",
        radius,
        depth,
        start=0.0,
    )
    obj = bpy.data.objects.new(name, mesh)
    obj[KIND_KEY] = kind
    obj[HELPER_PAIR_KEY] = pair_id
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_render = True
    collection_for_connectors(context.scene).objects.link(obj)
    obj.parent = controller
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    _regenerate_helper(obj, context.scene)
    return obj


def _add_boolean(target, operand, operation, label, solver):
    modifier = target.modifiers.new(name=f"{BOOLEAN_PREFIX} {label}", type="BOOLEAN")
    modifier.operation = operation
    modifier.solver = solver
    modifier.object = operand
    return modifier


def create_connector_pair(context, pin_target, socket_target, pair_id, seam_location, seam_axis):
    """Create an embedded male pin and matching female cutter for two split meshes."""
    if not is_mesh_object(pin_target) or not is_mesh_object(socket_target):
        raise ValueError("A mesh is required on both sides of the split.")
    existing = helpers_for_pair(pair_id)
    if all(existing.values()):
        return existing
    _remove_helpers(existing)

    axis = Vector(seam_axis)
    if axis.length_squared < 1e-12:
        raise ValueError("Could not determine a stable connector direction at the split.")
    control = _make_controller(context, pair_id, Vector(seam_location), axis)
    control[PIN_TARGET_ID_KEY] = pin_target.get(PART_ID_KEY, "")
    control[SOCKET_TARGET_ID_KEY] = socket_target.get(PART_ID_KEY, "")
    try:
        pin = _make_helper(context, f"PS_Pin_{pair_id[:6]}", KIND_PIN, pair_id, control)
        socket = _make_helper(context, f"PS_Socket_{pair_id[:6]}", KIND_CUTTER, pair_id, control)
    except Exception:
        _remove_helpers(helpers_for_pair(pair_id))
        raise
    return {KIND_CONTROL: control, KIND_PIN: pin, KIND_CUTTER: socket}


def _find_pair(obj):
    pair_id = obj.get(PAIR_ID_KEY, "")
    if not pair_id:
        return None
    for candidate in bpy.data.objects:
        if candidate is not obj and has_pair_id(candidate, pair_id) and candidate.type == "MESH":
            return candidate
    return None


def _object_by_part_id(part_id):
    if not part_id:
        return None
    for obj in bpy.data.objects:
        if obj.get(PART_ID_KEY) == part_id and is_mesh_object(obj):
            return obj
    return None


def _legacy_target_for_helper(helper, operation):
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if (
                modifier.type == "BOOLEAN"
                and modifier.name.startswith(BOOLEAN_PREFIX)
                and modifier.object is helper
                and modifier.operation == operation
            ):
                return obj
    return None


def _remember_confirmed_pair(obj, pair_id):
    try:
        confirmed_pairs = json.loads(obj.get(CONFIRMED_PAIRS_KEY, "[]"))
    except (TypeError, ValueError):
        confirmed_pairs = []
    if pair_id not in confirmed_pairs:
        confirmed_pairs.append(pair_id)
    obj[CONFIRMED_PAIRS_KEY] = json.dumps(confirmed_pairs)


def _remove_helpers(helpers):
    for kind in (KIND_PIN, KIND_CUTTER, KIND_CONTROL):
        obj = helpers.get(kind)
        if obj is None or obj.name not in bpy.data.objects:
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _mesh_quality(mesh):
    """Return absolute volume and the count of non-two-face edges."""
    if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
        return 0.0, len(mesh.edges)
    edge_uses = array("i", [0]) * len(mesh.edges)
    loop_edges = array("i", [0]) * len(mesh.loops)
    mesh.loops.foreach_get("edge_index", loop_edges)
    for edge_index in loop_edges:
        edge_uses[edge_index] += 1
    nonmanifold_edges = sum(uses != 2 for uses in edge_uses)

    mesh.calc_loop_triangles()
    origin = mesh.vertices[0].co
    signed_volume = 0.0
    for triangle in mesh.loop_triangles:
        first, second, third = (mesh.vertices[index].co - origin for index in triangle.vertices)
        signed_volume += first.dot(second.cross(third)) / 6.0
    return abs(signed_volume), nonmanifold_edges


def _apply_boolean(context, target, operand, operation, label, solver, pending):
    # Let Manifold attempt to normalize small topology defects from Mask Slice.
    # Its result is still rejected below unless it is closed and changes volume
    # in the expected direction; the caller restores both target meshes on error.
    original_volume, _open_edges = _mesh_quality(target.data)
    if original_volume <= 1e-15:
        raise RuntimeError(f"{label} target has no measurable enclosed volume.")
    modifier = _add_boolean(target, operand, operation, label, solver)
    pending.append((target, modifier.name))
    activate_only(context, target)
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result or not len(target.data.polygons):
        raise RuntimeError(f"The {solver.title()} solver could not produce a valid mesh.")
    result_volume, open_edges = _mesh_quality(target.data)
    if open_edges:
        raise RuntimeError(f"{label} left {open_edges} open or non-manifold edges; the operation was rolled back.")
    epsilon = max(original_volume * 1e-8, 1e-15)
    if operation == "UNION" and result_volume <= original_volume + epsilon:
        raise RuntimeError(f"{label} did not add a pin that intersects the target mesh.")
    if operation == "DIFFERENCE" and result_volume >= original_volume - epsilon:
        raise RuntimeError(f"{label} did not cut a socket into the target mesh.")


def _confirm_connector(context, pair_id, solver):
    helpers = helpers_for_pair(pair_id)
    control = helpers[KIND_CONTROL]
    pin = helpers[KIND_PIN]
    socket = helpers[KIND_CUTTER]
    if control is None or pin is None or socket is None:
        raise ValueError("The editable connector preview is incomplete.")

    pin_target_id = control.get(PIN_TARGET_ID_KEY, "")
    socket_target_id = control.get(SOCKET_TARGET_ID_KEY, "")
    if not pin_target_id or not socket_target_id:
        # Older previews had live modifiers but did not store their target IDs.
        legacy_part = _legacy_target_for_helper(pin, "UNION")
        legacy_remainder = _legacy_target_for_helper(socket, "DIFFERENCE")
        if legacy_part is not None and legacy_remainder is not None:
            pin_target_id = legacy_part.get(PART_ID_KEY, "")
            socket_target_id = legacy_remainder.get(PART_ID_KEY, "")
            control[PIN_TARGET_ID_KEY] = pin_target_id
            control[SOCKET_TARGET_ID_KEY] = socket_target_id

    pin_target = _object_by_part_id(pin_target_id)
    socket_target = _object_by_part_id(socket_target_id)
    if pin_target is None or socket_target is None or pin_target is socket_target:
        raise ValueError("Could not find both meshes associated with this connector.")
    if pin_target.data is socket_target.data:
        raise ValueError("The two parts must use separate mesh data before confirming the connector.")

    original_mesh_names = [pin_target.data.name, socket_target.data.name]
    backups = [(pin_target, pin_target.data.copy()), (socket_target, socket_target.data.copy())]
    pending = []
    try:
        _apply_boolean(context, pin_target, pin, "UNION", "Pin Union", solver, pending)
        _apply_boolean(context, socket_target, socket, "DIFFERENCE", "Socket Cut", solver, pending)
    except (RuntimeError, ValueError, TypeError) as exc:
        for target, backup in backups:
            current_mesh_name = target.data.name
            target.data = backup
            current_mesh = bpy.data.meshes.get(current_mesh_name)
            if current_mesh is not None and current_mesh.users == 0:
                bpy.data.meshes.remove(current_mesh)
        for mesh_name in original_mesh_names:
            original_mesh = bpy.data.meshes.get(mesh_name)
            if original_mesh is not None and original_mesh.users == 0:
                bpy.data.meshes.remove(original_mesh)
        for target, modifier_name in pending:
            modifier = target.modifiers.get(modifier_name)
            if modifier is not None:
                target.modifiers.remove(modifier)
        for _target, backup in backups:
            backup_mesh = bpy.data.meshes.get(backup.name)
            if backup_mesh is not None and backup_mesh.users == 0:
                bpy.data.meshes.remove(backup_mesh)
        activate_only(context, pin_target)
        raise RuntimeError(f"{solver.title()} Boolean failed; both meshes were restored. {exc}") from exc

    for _target, backup in backups:
        backup_mesh = bpy.data.meshes.get(backup.name)
        if backup_mesh is not None and backup_mesh.users == 0:
            bpy.data.meshes.remove(backup_mesh)
    for mesh_name in original_mesh_names:
        original_mesh = bpy.data.meshes.get(mesh_name)
        if original_mesh is not None and original_mesh.users == 0:
            bpy.data.meshes.remove(original_mesh)
    for target in (pin_target, socket_target):
        for modifier in list(target.modifiers):
            if modifier.type == "BOOLEAN" and modifier.name.startswith(BOOLEAN_PREFIX):
                target.modifiers.remove(modifier)
    _remember_confirmed_pair(pin_target, pair_id)
    _remember_confirmed_pair(socket_target, pair_id)
    pin_target[CONFIRMED_SOLVER_KEY] = solver
    socket_target[CONFIRMED_SOLVER_KEY] = solver
    _remove_helpers(helpers)
    activate_only(context, pin_target)


class PSS_OT_confirm_connector(bpy.types.Operator):
    bl_idname = "print_splitter.confirm_connector"
    bl_label = "Apply Connector to Mesh"
    bl_description = "Choose a Boolean solver, confirm, and apply the connector to both parts"
    bl_options = {"REGISTER", "UNDO"}

    pair_id: bpy.props.StringProperty(
        name="Connector Pair",
        options={"HIDDEN"},
    )

    solver: bpy.props.EnumProperty(
        name="Boolean Solver",
        description="Choose the Boolean algorithm used to apply both connector operations",
        items=(
            ("MANIFOLD", "Manifold", "Fast; may correct minor split defects and validates both outputs"),
            ("EXACT", "Exact", "Handles overlapping geometry, with higher cost"),
            ("FLOAT", "Float", "Fast; may fail with overlapping geometry"),
        ),
        default="MANIFOLD",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if context.mode != "OBJECT" or obj is None:
            return False
        if is_mesh_object(obj):
            return bool(pending_connector_pairs(obj))
        pair_id = obj.get(HELPER_PAIR_KEY, "")
        pin_target, _socket_target = targets_for_pair(pair_id)
        return bool(pair_id and pin_target and not pair_is_confirmed(pin_target, pair_id))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=420,
            title="Apply Connector to Mesh?",
            confirm_text="Apply to Mesh",
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Boolean Solver")
        layout.prop(self, "solver", text="", expand=True)
        layout.label(text="This applies the pin union and socket cut to both parts.", icon="INFO")

    def execute(self, context):
        obj = context.active_object
        pair_id = self.pair_id or obj.get(PAIR_ID_KEY, "") or obj.get(HELPER_PAIR_KEY, "")
        try:
            _confirm_connector(context, pair_id, self.solver)
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Male pin and female socket applied with the {self.solver.title()} solver.")
        return {"FINISHED"}


class PSS_OT_select_mate(bpy.types.Operator):
    bl_idname = "print_splitter.select_mate"
    bl_label = "Select Matching Part"
    bl_description = "Select the other divided mesh associated with this seam"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return is_mesh_object(obj) and bool(obj.get(PAIR_ID_KEY, ""))

    def execute(self, context):
        partner = _find_pair(context.active_object)
        if partner is None:
            self.report({"ERROR"}, "Could not find the matching part.")
            return {"CANCELLED"}
        for selected in list(context.selected_objects):
            selected.select_set(False)
        partner.hide_set(False)
        partner.hide_select = False
        partner.select_set(True)
        context.view_layer.objects.active = partner
        return {"FINISHED"}


CLASSES = (PSS_OT_confirm_connector, PSS_OT_select_mate)


def register():
    _remove_load_post_handlers()
    bpy.app.handlers.load_post.append(_disable_legacy_connector_previews)
    if not bpy.app.timers.is_registered(_disable_legacy_connector_previews):
        bpy.app.timers.register(_disable_legacy_connector_previews, first_interval=0.0)
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)
    _remove_load_post_handlers()
    if bpy.app.timers.is_registered(_disable_legacy_connector_previews):
        bpy.app.timers.unregister(_disable_legacy_connector_previews)


def _remove_load_post_handlers():
    for handler in tuple(bpy.app.handlers.load_post):
        if (
            getattr(handler, "__name__", "") == _disable_legacy_connector_previews.__name__
        ):
            bpy.app.handlers.load_post.remove(handler)

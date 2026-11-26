"""Automatic connector previews, applied with a Manifold Boolean on confirmation."""

from __future__ import annotations

import math
import json

import bpy
from .registration import register_classes, unregister_classes
from bpy.app.handlers import persistent
from mathutils import Vector

from .core import (
    PAIR_ID_KEY,
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
    radial_clearance = mm_to_bu(settings.connector_clearance_mm * 0.5, scene)
    overlap = mm_to_bu(BOOLEAN_OVERLAP_MM, scene)
    return max(diameter * 0.5, 1e-6), max(depth + overlap, 1e-6), max(radial_clearance, 0.0), overlap


def _regenerate_helper(obj, scene):
    radius, length, radial_clearance, overlap = _dimensions(scene)
    kind = obj.get(KIND_KEY)
    if kind == KIND_CUTTER:
        radius += radial_clearance
    elif kind != KIND_PIN:
        return
    mesh = _cylinder_mesh(
        obj.name + "_Mesh",
        radius,
        length,
        start=-overlap,
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


def pair_is_confirmed(obj, pair_id):
    try:
        confirmed_pairs = json.loads(obj.get(CONFIRMED_PAIRS_KEY, "[]"))
    except (TypeError, ValueError):
        confirmed_pairs = []
    return pair_id in confirmed_pairs


@persistent
def _disable_legacy_connector_previews(_unused=None):
    """Disable live Exact previews saved by earlier add-on versions."""
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type == "BOOLEAN" and modifier.name.startswith(BOOLEAN_PREFIX):
                modifier.show_viewport = False
                modifier.show_render = False


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
    radius, _length, radial_clearance, _overlap = _dimensions(context.scene)
    if kind == KIND_CUTTER:
        radius += radial_clearance
    mesh = _cylinder_mesh(
        name + "_Mesh",
        radius,
        max(mm_to_bu(context.scene.print_splitter_settings.connector_depth_mm, context.scene), 1e-6),
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


def create_connector_pair(context, part, remainder, pair_id, seam_location, seam_axis):
    """Create one pin/socket pair at the split interface, with a shared transform control."""
    if not is_mesh_object(part) or not is_mesh_object(remainder):
        raise ValueError("A mesh is required on both sides of the split.")
    existing = helpers_for_pair(pair_id)
    if all(existing.values()):
        return existing

    axis = Vector(seam_axis)
    if axis.length_squared < 1e-12:
        raise ValueError("Could not determine a stable connector direction at the split.")
    control = _make_controller(context, pair_id, Vector(seam_location), axis)
    control[PIN_TARGET_ID_KEY] = part.get(PART_ID_KEY, "")
    control[SOCKET_TARGET_ID_KEY] = remainder.get(PART_ID_KEY, "")
    pin = _make_helper(context, f"PS_Pin_{pair_id[:6]}", KIND_PIN, pair_id, control)
    socket = _make_helper(context, f"PS_Socket_{pair_id[:6]}", KIND_CUTTER, pair_id, control)
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


def _apply_boolean(context, target, operand, operation, label, solver, pending):
    modifier = _add_boolean(target, operand, operation, label, solver)
    pending.append((target, modifier.name))
    activate_only(context, target)
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result or not len(target.data.polygons):
        raise RuntimeError(f"The {solver.title()} solver could not produce a valid mesh.")


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

    part = _object_by_part_id(pin_target_id)
    remainder = _object_by_part_id(socket_target_id)
    if part is None or remainder is None or part is remainder:
        raise ValueError("Could not find both meshes associated with this connector.")
    if part.data is remainder.data:
        raise ValueError("The two parts must use separate mesh data before confirming the connector.")

    original_meshes = [part.data, remainder.data]
    backups = [(part, part.data.copy()), (remainder, remainder.data.copy())]
    pending = []
    try:
        _apply_boolean(context, part, pin, "UNION", "Pin Union", solver, pending)
        _apply_boolean(context, remainder, socket, "DIFFERENCE", "Socket Cut", solver, pending)
    except (RuntimeError, ValueError, TypeError) as exc:
        for target, backup in backups:
            current_mesh = target.data
            target.data = backup
            if current_mesh.users == 0:
                bpy.data.meshes.remove(current_mesh)
        for original_mesh in original_meshes:
            if original_mesh.users == 0:
                bpy.data.meshes.remove(original_mesh)
        for target, modifier_name in pending:
            modifier = target.modifiers.get(modifier_name)
            if modifier is not None:
                target.modifiers.remove(modifier)
        for _target, backup in backups:
            if backup.users == 0:
                bpy.data.meshes.remove(backup)
        activate_only(context, part)
        requirement = " Both parts must be manifold." if solver == "MANIFOLD" else ""
        raise RuntimeError(f"{solver.title()} Boolean failed.{requirement} {exc}") from exc

    for _target, backup in backups:
        if backup.users == 0:
            bpy.data.meshes.remove(backup)
    for original_mesh in original_meshes:
        if original_mesh.users == 0:
            bpy.data.meshes.remove(original_mesh)
    for target in (part, remainder):
        for modifier in list(target.modifiers):
            if modifier.type == "BOOLEAN" and modifier.name.startswith(BOOLEAN_PREFIX):
                target.modifiers.remove(modifier)
    _remember_confirmed_pair(part, pair_id)
    _remember_confirmed_pair(remainder, pair_id)
    part[CONFIRMED_SOLVER_KEY] = solver
    remainder[CONFIRMED_SOLVER_KEY] = solver
    _remove_helpers(helpers)
    activate_only(context, part)


class PSS_OT_confirm_connector(bpy.types.Operator):
    bl_idname = "print_splitter.confirm_connector"
    bl_label = "Apply Connector to Mesh"
    bl_description = "Choose a Boolean solver, confirm, and apply the connector to both parts"
    bl_options = {"REGISTER", "UNDO"}

    solver: bpy.props.EnumProperty(
        name="Boolean Solver",
        description="Choose the Boolean algorithm used to apply both connector operations",
        items=(
            ("MANIFOLD", "Manifold", "Fast; requires manifold input meshes"),
            ("EXACT", "Exact", "Handles overlapping geometry, with higher cost"),
            ("FLOAT", "Float", "Fast; may fail with overlapping geometry"),
        ),
        default="MANIFOLD",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        pair_id = (obj.get(PAIR_ID_KEY, "") or obj.get(HELPER_PAIR_KEY, "")) if obj else ""
        return (
            context.mode == "OBJECT"
            and obj is not None
            and (is_mesh_object(obj) or bool(obj.get(HELPER_PAIR_KEY, "")))
            and bool(pair_id)
            and not pair_is_confirmed(obj, pair_id)
        )

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
        pair_id = obj.get(PAIR_ID_KEY, "") or obj.get(HELPER_PAIR_KEY, "")
        try:
            _confirm_connector(context, pair_id, self.solver)
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Connector applied to both parts with the {self.solver.title()} solver.")
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
    _disable_legacy_connector_previews()
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)
    _remove_load_post_handlers()


def _remove_load_post_handlers():
    for handler in tuple(bpy.app.handlers.load_post):
        if (
            getattr(handler, "__name__", "") == _disable_legacy_connector_previews.__name__
        ):
            bpy.app.handlers.load_post.remove(handler)

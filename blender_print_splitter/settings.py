"""Persistent UI settings for Blender Print Splitter."""

import json

import bpy

from .core import (
    FACE_SET_KEY,
    GEOMETRY_FACE_SET_SUMMARY_KEY,
    GEOMETRY_MOTHER_FACE_SET_KEY,
    TARGET_FACE_SET,
    is_mesh_object,
)
from .registration import register_classes, unregister_class_by_name


_FACE_SET_ENUM_STRINGS = {}


def _refresh_connectors(_self, context):
    try:
        from .connectors import update_helpers

        update_helpers(context)
    except (ImportError, RuntimeError, AttributeError):
        # The property group can be registered before the connector module.
        pass


def _sync_brush_radius(self, context):
    sculpt = getattr(getattr(context, "tool_settings", None), "sculpt", None)
    brush = getattr(sculpt, "brush", None)
    if brush is not None:
        brush.size = self.brush_radius_px


def _geometry_face_set_items(_self, context):
    obj = context.active_object if context else None
    try:
        summary = json.loads(obj.get(GEOMETRY_FACE_SET_SUMMARY_KEY, "{}")) if is_mesh_object(obj) else {}
        face_set_ids = sorted(int(value) for value in summary if int(value) >= TARGET_FACE_SET)
    except (TypeError, ValueError):
        face_set_ids = []

    items = []
    for face_set_id in face_set_ids:
        item = _FACE_SET_ENUM_STRINGS.get(face_set_id)
        if item is None:
            item = (
                f"FACE_SET_{face_set_id}",
                f"Face Set {face_set_id}",
                "Generated geometric region",
            )
            _FACE_SET_ENUM_STRINGS[face_set_id] = item
        items.append(item)
    if not items:
        fallback = _FACE_SET_ENUM_STRINGS.get(TARGET_FACE_SET)
        if fallback is None:
            fallback = (f"FACE_SET_{TARGET_FACE_SET}", f"Face Set {TARGET_FACE_SET}", "No generated region available")
            _FACE_SET_ENUM_STRINGS[TARGET_FACE_SET] = fallback
        items.append(fallback)
    return items


def _set_geometry_target(self, context):
    obj = context.active_object if context else None
    identifier = getattr(self, "geometry_target_face_set", "")
    if not is_mesh_object(obj) or not identifier.startswith("FACE_SET_"):
        return
    try:
        obj[FACE_SET_KEY] = int(identifier.rsplit("_", 1)[1])
    except ValueError:
        return
    if context.area:
        context.area.tag_redraw()


def _set_geometry_mother(self, context):
    obj = context.active_object if context else None
    identifier = getattr(self, "geometry_mother_face_set", "")
    if not is_mesh_object(obj) or not identifier.startswith("FACE_SET_"):
        return
    try:
        mother_face_set = int(identifier.rsplit("_", 1)[1])
    except ValueError:
        return
    obj[GEOMETRY_MOTHER_FACE_SET_KEY] = mother_face_set
    obj[FACE_SET_KEY] = mother_face_set
    if context.area:
        context.area.tag_redraw()


class PSS_Settings(bpy.types.PropertyGroup):
    brush_radius_px: bpy.props.IntProperty(
        name="Brush Size",
        default=70,
        min=1,
        max=10000,
        description="Paint brush radius in viewport pixels",
        update=_sync_brush_radius,
    )
    small_island_percent: bpy.props.FloatProperty(
        name="Ignore Islands Below (%)",
        default=1.0,
        min=0.0,
        max=50.0,
        precision=1,
        description="Remove painted components smaller than this fraction of the largest region",
    )
    merge_gap_mm: bpy.props.FloatProperty(
        name="Merge Regions Within (mm)",
        default=1.0,
        min=0.0,
        max=100.0,
        precision=2,
        description="Maximum geodesic distance for filling the gap between large regions",
    )
    face_set_smooth_iterations: bpy.props.IntProperty(
        name="Boundary Smoothing Iterations",
        default=1,
        min=1,
        max=10,
        description="Relax Face Set labels without moving mesh vertices",
    )
    mask_threshold: bpy.props.FloatProperty(
        name="Mask Threshold",
        default=0.5,
        min=0.0,
        max=1.0,
        precision=2,
        description="Threshold used by Blender's native Mask Slice operator",
    )
    geometry_partition_method: bpy.props.EnumProperty(
        name="Analysis Method",
        description="Use Blender's native normal grouping or disconnected-part detection",
        items=(
            (
                "SURFACE_FOLDS",
                "Surface Features",
                "Use Blender's fast native normal grouping to create approximate surface regions",
            ),
            ("LOOSE_PARTS", "Disconnected Parts", "Create one region for each disconnected mesh component"),
        ),
        default="SURFACE_FOLDS",
    )
    geometry_angle_degrees: bpy.props.FloatProperty(
        name="Normal Angle (°)",
        default=60.0,
        min=5.0,
        max=89.0,
        precision=1,
        description="Fast normal threshold; larger angles create fewer, broader regions",
    )
    geometry_target_face_set: bpy.props.EnumProperty(
        name="Region to Extract",
        description="Choose the generated region for the next split",
        items=_geometry_face_set_items,
        update=_set_geometry_target,
        options={"SKIP_SAVE"},
    )
    geometry_mother_face_set: bpy.props.EnumProperty(
        name="Mother Region",
        description="Keep this region on the remainder and attach the connector to it; largest is selected by default",
        items=_geometry_face_set_items,
        update=_set_geometry_mother,
        options={"SKIP_SAVE"},
    )
    show_advanced_options: bpy.props.BoolProperty(
        name="Advanced Options",
        default=False,
        options={"SKIP_SAVE"},
    )
    create_connector_after_split: bpy.props.BoolProperty(
        name="Create Connector After Split",
        description="Create an editable connector preview after the split; when off, no connector confirmation is required",
        default=True,
    )
    connector_shape: bpy.props.EnumProperty(
        name="Connector Shape",
        description="Choose a round pin or a square tapered key",
        items=(
            ("CYLINDER", "Cylinder", "Round connector pin and socket"),
            ("TAPERED_KEY", "Tapered Square Key", "Square key with a narrower end for easier assembly"),
        ),
        default="CYLINDER",
        update=_refresh_connectors,
    )
    connector_diameter_mm: bpy.props.FloatProperty(
        name="Connector Width (mm)",
        description="Cylinder diameter or square key width",
        default=4.0,
        min=0.5,
        max=50.0,
        precision=2,
        update=_refresh_connectors,
    )
    connector_magnet_enabled: bpy.props.BoolProperty(
        name="Add Magnet Pockets",
        description="Cut a matching magnet pocket into each half, beside the connector",
        default=False,
        update=_refresh_connectors,
    )
    connector_magnet_diameter_mm: bpy.props.FloatProperty(
        name="Magnet Diameter (mm)",
        default=6.0,
        min=1.0,
        max=30.0,
        precision=2,
        update=_refresh_connectors,
    )
    connector_magnet_depth_mm: bpy.props.FloatProperty(
        name="Magnet Depth (mm)",
        description="Pocket depth inside each half, measured from the split surface",
        default=2.0,
        min=0.5,
        max=10.0,
        precision=2,
        update=_refresh_connectors,
    )
    connector_magnet_clearance_mm: bpy.props.FloatProperty(
        name="Magnet Fit Clearance (mm)",
        default=0.2,
        min=0.0,
        max=1.0,
        precision=2,
        description="Radial clearance around each magnet",
        update=_refresh_connectors,
    )
    connector_depth_mm: bpy.props.FloatProperty(
        name="Socket / Pin Reach (mm)",
        default=3.0,
        min=0.5,
        max=50.0,
        precision=2,
        update=_refresh_connectors,
    )
    connector_embed_depth_mm: bpy.props.FloatProperty(
        name="Pin Embed Depth (mm)",
        default=5.0,
        min=0.5,
        max=50.0,
        precision=2,
        description="How far the male pin extends back into its base part",
        update=_refresh_connectors,
    )
    connector_clearance_mm: bpy.props.FloatProperty(
        name="Diametral Clearance (mm)",
        default=0.2,
        min=0.0,
        max=2.0,
        precision=2,
        update=_refresh_connectors,
    )
def register():
    if hasattr(bpy.types.Scene, "print_splitter_settings"):
        return
    registered_types = register_classes((PSS_Settings,))
    if not registered_types:
        raise RuntimeError(
            "PSS_Settings is already registered in Blender but cannot be resolved. Restart Blender and enable the add-on again."
        )
    settings_type = registered_types[0]
    bpy.types.Scene.print_splitter_settings = bpy.props.PointerProperty(type=settings_type)


def unregister():
    removed = unregister_class_by_name(PSS_Settings.__name__)
    if removed and hasattr(bpy.types.Scene, "print_splitter_settings"):
        del bpy.types.Scene.print_splitter_settings

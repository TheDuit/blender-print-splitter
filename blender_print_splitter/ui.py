"""3D View sidebar panel."""

import bpy
from .registration import register_classes, unregister_classes

from .connectors import CONFIRMED_SOLVER_KEY, HELPER_PAIR_KEY, helpers_for_pair, pair_is_confirmed
from .core import (
    GEOMETRY_SEGMENTATION_KEY,
    IS_DIVISION_KEY,
    PAIR_ID_KEY,
    ROLE_DIVISION,
    ROLE_KEY,
    ROLE_WORKING,
    is_mesh_object,
)


class PSS_PT_panel(bpy.types.Panel):
    bl_label = "Print Splitter"
    bl_idname = "PSS_PT_print_splitter"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Print Splitter"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return is_mesh_object(obj) or bool(obj and obj.get(HELPER_PAIR_KEY, ""))

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        settings = context.scene.print_splitter_settings
        role = obj.get(ROLE_KEY, "Original / External")
        is_division = bool(obj.get(IS_DIVISION_KEY, False))

        selected_helper_pair = obj.get(HELPER_PAIR_KEY, "")
        if selected_helper_pair:
            self._draw_connector_controls(layout, settings, obj, selected_helper_pair)
            return

        box = layout.box()
        box.label(text=f"Object: {obj.name}", icon="MESH_DATA")
        box.label(text=f"Status: {'Division' if is_division else role}")

        if context.mode != "SCULPT" or role not in {ROLE_WORKING, ROLE_DIVISION}:
            layout.operator("print_splitter.start_operation", icon="DUPLICATE")
            layout.separator()
            layout.label(text="Start a split to prepare a safe working copy and paint.")
            if obj.get(PAIR_ID_KEY):
                self._draw_connector_controls(layout, settings, obj)
            return

        if obj.get(GEOMETRY_SEGMENTATION_KEY):
            self._draw_geometry_segmentation(layout, settings, obj)
            return

        layout.label(text="1. Paint the region. Every stroke uses the same Face Set.", icon="BRUSH_DATA")
        row = layout.row(align=True)
        row.operator("print_splitter.paint_faceset", text="Paint Face Set", icon="BRUSH_DATA")
        row.prop(settings, "brush_radius_px", text="Radius")
        layout.label(text="Left-drag paint; right-drag erase; scroll changes brush radius.", icon="INFO")

        row = layout.row(align=True)
        smooth = row.operator("print_splitter.smooth_faceset", text="Smooth Face Sets", icon="MOD_SMOOTH")
        smooth.iterations = settings.face_set_smooth_iterations
        row.prop(settings, "face_set_smooth_iterations", text="Iterations")
        layout.label(text="Only Face Set labels change; mesh vertices stay fixed.", icon="INFO")

        layout.separator()
        layout.label(text="2. Cleanup and extraction")
        col = layout.column(align=True)
        col.prop(settings, "small_island_percent")
        col.prop(settings, "merge_gap_mm")
        col.prop(settings, "mask_threshold")
        layout.operator("print_splitter.extract_part", text="Extract Part", icon="MOD_BOOLEAN")

        box = layout.box()
        box.label(text="Alternative: Analyze the Mesh", icon="MOD_DECIM")
        box.prop(settings, "geometry_partition_method")
        if settings.geometry_partition_method == "SURFACE_FOLDS":
            box.prop(settings, "geometry_angle_degrees")
        if getattr(obj, "use_dynamic_topology_sculpting", False):
            box.label(text="Disable Dyntopo before analyzing Face Sets.", icon="ERROR")
        box.operator("print_splitter.analyze_geometry", text="Generate Geometry Face Sets", icon="OUTLINER_OB_MESH")

    @staticmethod
    def _draw_geometry_segmentation(layout, settings, obj):
        box = layout.box()
        box.label(text="Geometry Face Sets", icon="MOD_DECIM")
        box.label(text="Temporary regions generated from mesh geometry.", icon="INFO")
        box.prop(settings, "geometry_partition_method")
        if settings.geometry_partition_method == "SURFACE_FOLDS":
            box.prop(settings, "geometry_angle_degrees")
        if getattr(obj, "use_dynamic_topology_sculpting", False):
            box.label(text="Disable Dyntopo before editing generated Face Sets.", icon="ERROR")
        box.operator("print_splitter.analyze_geometry", text="Reanalyze Geometry", icon="FILE_REFRESH")

        box.separator()
        box.prop(settings, "geometry_target_face_set", text="Region to Extract")
        box.prop(settings, "geometry_merge_into_face_set", text="Merge Into")
        box.operator("print_splitter.merge_geometry_facesets", text="Merge Regions", icon="AUTOMERGE_ON")
        row = box.row(align=True)
        row.operator("print_splitter.native_faceset_brush", text="Native Face Set Brush", icon="BRUSH_DATA")
        row.operator("print_splitter.refresh_geometry_regions", text="Refresh List", icon="FILE_REFRESH")
        box.label(text="Refresh the list after the native brush creates new regions.", icon="INFO")

        box.separator()
        box.label(text="Split the selected region")
        col = box.column(align=True)
        col.prop(settings, "small_island_percent")
        col.prop(settings, "merge_gap_mm")
        col.prop(settings, "mask_threshold")
        box.operator("print_splitter.extract_part", text="Extract Selected Region", icon="MOD_BOOLEAN")
        box.separator()
        box.operator("print_splitter.manual_faceset_mode", text="Switch to Manual Paint", icon="BRUSH_DATA")

    @staticmethod
    def _draw_connector_controls(layout, settings, obj, pair_id=None):
        box = layout.box()
        box.label(text="Automatic Split Connector", icon="MOD_BOOLEAN")
        pair_id = pair_id or obj.get(PAIR_ID_KEY, "")
        if pair_is_confirmed(obj, pair_id):
            solver = obj.get(CONFIRMED_SOLVER_KEY, "MANIFOLD").title()
            box.label(text=f"Confirmed — {solver} Booleans applied.", icon="CHECKMARK")
            if obj.get(PAIR_ID_KEY):
                box.operator("print_splitter.select_mate", icon="FILE_REFRESH")
            return

        box.label(text="Preview only; no Boolean is active yet.", icon="INFO")
        box.prop(settings, "connector_diameter_mm")
        box.prop(settings, "connector_depth_mm")
        box.prop(settings, "connector_clearance_mm")
        helpers = helpers_for_pair(pair_id)
        control = helpers.get("CONTROL")
        if control is not None:
            box.separator()
            box.label(text="Position, rotation, and scale", icon="EMPTY_ARROWS")
            box.prop(control, "location", text="Position")
            box.prop(control, "rotation_euler", text="Rotation")
            box.prop(control, "scale", text="Scale")
        else:
            box.label(text="No connector helper is linked to this split.", icon="INFO")
        box.operator("print_splitter.confirm_connector", text="Apply Connector to Mesh", icon="CHECKMARK")
        box.label(text="Choose the Boolean solver in the confirmation dialog.", icon="INFO")
        if obj.get(PAIR_ID_KEY):
            box.operator("print_splitter.select_mate", icon="FILE_REFRESH")


CLASSES = (PSS_PT_panel,)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

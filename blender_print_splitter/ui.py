"""3D View sidebar panel."""

import bpy
from .registration import register_classes, unregister_classes

from .connectors import (
    CONFIRMED_SOLVER_KEY,
    HELPER_PAIR_KEY,
    has_pending_connector,
    helpers_for_pair,
    pair_is_confirmed,
    pending_connector_pairs,
    targets_for_pair,
)
from .core import (
    GEOMETRY_SEGMENTATION_KEY,
    IS_DIVISION_KEY,
    MOTHER_PART_ID_KEY,
    PAIR_ID_KEY,
    PART_ID_KEY,
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

        if has_pending_connector(obj):
            layout.label(text="Resolve this connector before splitting another part.", icon="ERROR")
            for pair_id in pending_connector_pairs(obj):
                self._draw_connector_controls(layout, settings, obj, pair_id)
            return

        box = layout.box()
        box.label(text=f"{obj.name} · {'Division' if is_division else role}", icon="MESH_DATA")

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

        manual = layout.box()
        manual.label(text="Paint one region", icon="BRUSH_DATA")
        row = manual.row(align=True)
        row.operator("print_splitter.paint_faceset", text="Paint Region", icon="BRUSH_DATA")
        smooth = row.operator("print_splitter.smooth_faceset", text="Smooth Boundary", icon="MOD_SMOOTH")
        smooth.iterations = settings.face_set_smooth_iterations
        manual.label(text="Left-drag paints · right-drag erases · wheel changes brush size", icon="INFO")
        manual.operator("print_splitter.extract_part", text="Extract Part", icon="MOD_BOOLEAN")

        analysis = layout.box()
        analysis.label(text="Or analyze the surface", icon="MOD_DECIM")
        analysis.prop(settings, "geometry_partition_method", text="Method")
        if getattr(obj, "use_dynamic_topology_sculpting", False):
            analysis.label(text="Disable Dyntopo before analyzing regions.", icon="ERROR")
        analysis.operator("print_splitter.analyze_geometry", text="Analyze Mesh", icon="VIEWZOOM")
        self._draw_advanced_toggle(layout, settings)
        if settings.show_advanced_options:
            self._draw_advanced_options(layout, settings, obj, include_geometry=True)

    @staticmethod
    def _draw_geometry_segmentation(layout, settings, obj):
        box = layout.box()
        box.label(text="Choose the central base for male pins", icon="MOD_DECIM")
        box.prop(settings, "geometry_mother_face_set", text="Mother (Male Pins)")
        box.prop(settings, "geometry_target_face_set", text="Part (Female Socket)")
        box.label(text="The analyzer preselects the region nearest the mesh center.", icon="INFO")
        if settings.geometry_target_face_set == settings.geometry_mother_face_set:
            box.label(text="Choose a different region to extract.", icon="ERROR")
        else:
            box.operator("print_splitter.extract_part", text="Extract Selected Region", icon="MOD_BOOLEAN")

        row = layout.row(align=True)
        row.prop(settings, "geometry_partition_method", text="")
        row.operator("print_splitter.analyze_geometry", text="Reanalyze", icon="FILE_REFRESH")
        if getattr(obj, "use_dynamic_topology_sculpting", False):
            layout.label(text="Disable Dyntopo before editing generated regions.", icon="ERROR")
        layout.label(text="Refine regions with Blender's Face Set brush, or merge them in Options.", icon="INFO")
        PSS_PT_panel._draw_advanced_toggle(layout, settings)
        if settings.show_advanced_options:
            PSS_PT_panel._draw_advanced_options(layout, settings, obj, include_geometry=True)

    @staticmethod
    def _draw_advanced_toggle(layout, settings):
        row = layout.row()
        row.prop(
            settings,
            "show_advanced_options",
            text="Options",
            icon="PREFERENCES",
            toggle=True,
        )

    @staticmethod
    def _draw_advanced_options(layout, settings, obj, include_geometry=False):
        box = layout.box()
        box.label(text="Advanced Options", icon="PREFERENCES")
        box.prop(settings, "brush_radius_px")
        box.prop(settings, "face_set_smooth_iterations")
        box.separator()
        box.prop(settings, "small_island_percent")
        box.prop(settings, "merge_gap_mm")
        box.prop(settings, "mask_threshold")
        if include_geometry:
            box.separator()
            if settings.geometry_partition_method == "SURFACE_FOLDS":
                box.prop(settings, "geometry_angle_degrees")
                box.prop(settings, "geometry_feature_scale_percent")
                box.prop(settings, "geometry_min_region_percent")
            if obj.get(GEOMETRY_SEGMENTATION_KEY):
                box.label(text="Merge selected region into:")
                box.prop(settings, "geometry_merge_into_face_set", text="")
                box.operator("print_splitter.merge_geometry_facesets", text="Merge Regions", icon="AUTOMERGE_ON")
                row = box.row(align=True)
                row.operator("print_splitter.native_faceset_brush", text="Face Set Brush", icon="BRUSH_DATA")
                row.operator("print_splitter.refresh_geometry_regions", text="Refresh", icon="FILE_REFRESH")
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
        pin_target, socket_target = targets_for_pair(pair_id)
        box.label(text=f"Male pin: {pin_target.name if pin_target else 'Missing target'}")
        box.label(text=f"Female socket: {socket_target.name if socket_target else 'Missing target'}")
        embed_label = "Pin Embed Depth (mm)"
        if pin_target and pin_target.get(MOTHER_PART_ID_KEY) == pin_target.get(PART_ID_KEY):
            embed_label = "Embed in Mother (mm)"
        box.prop(settings, "connector_diameter_mm", text="Diameter (mm)")
        box.prop(settings, "connector_depth_mm", text="Reach / Socket (mm)")
        box.prop(settings, "connector_embed_depth_mm", text=embed_label)
        box.prop(settings, "connector_clearance_mm", text="Fit Clearance (mm)")
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
        confirm = box.operator("print_splitter.confirm_connector", text="Apply Connector to Mesh", icon="CHECKMARK")
        confirm.pair_id = pair_id
        box.label(text="Confirm this connector before splitting another part.", icon="INFO")
        if obj.get(PAIR_ID_KEY):
            box.operator("print_splitter.select_mate", icon="FILE_REFRESH")


CLASSES = (PSS_PT_panel,)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

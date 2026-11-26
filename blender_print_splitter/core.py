"""Object lifecycle and mesh attribute helpers."""

from __future__ import annotations

import uuid
import json
from array import array

import bpy
from .registration import register_classes, unregister_classes


ROLE_KEY = "print_splitter_role"
SOURCE_ID_KEY = "print_splitter_source_id"
PART_ID_KEY = "print_splitter_part_id"
PAIR_ID_KEY = "print_splitter_pair_id"
PAIR_IDS_KEY = "print_splitter_pair_ids"
PARENT_ID_KEY = "print_splitter_parent_id"
FACE_SET_KEY = "print_splitter_face_set_id"
IS_DIVISION_KEY = "print_splitter_is_division"
GEOMETRY_SEGMENTATION_KEY = "print_splitter_geometry_segmentation"
GEOMETRY_FACE_SET_SUMMARY_KEY = "print_splitter_geometry_face_set_summary"

ROLE_ORIGINAL = "ORIGINAL"
ROLE_WORKING = "WORKING"
ROLE_DIVISION = "DIVISION"

FACE_SET_ATTRIBUTE = ".sculpt_face_set"
MASK_ATTRIBUTE = ".sculpt_mask"
BACKGROUND_FACE_SET = 1
TARGET_FACE_SET = 2

ARCHIVE_COLLECTION = "Print Splitter | Archived Originals"
PARTS_COLLECTION = "Print Splitter | Parts"
CONNECTORS_COLLECTION = "Print Splitter | Connector Helpers"


def is_mesh_object(obj):
    return obj is not None and obj.type == "MESH" and obj.data is not None


def role_of(obj):
    return obj.get(ROLE_KEY, "") if obj else ""


def is_division(obj):
    return bool(obj and obj.get(IS_DIVISION_KEY, False))


def ensure_uuid(obj, key=SOURCE_ID_KEY):
    value = obj.get(key)
    if not value:
        value = uuid.uuid4().hex
        obj[key] = value
    return value


def find_collection(name, scene=None):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    root_collection = scene.collection if scene else bpy.context.scene.collection
    if not any(child == collection for child in root_collection.children):
        root_collection.children.link(collection)
    return collection


def move_object_to_collection(obj, collection):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)


def activate_only(context, obj):
    for item in context.selected_objects:
        item.select_set(False)
    obj.hide_set(False)
    obj.hide_select = False
    obj.select_set(True)
    context.view_layer.objects.active = obj


def remove_mesh_attribute(mesh, name):
    attribute = mesh.attributes.get(name)
    if attribute is not None:
        mesh.attributes.remove(attribute)


def reset_face_sets(mesh):
    """Leave a single background Face Set, ready for the plugin paint tool."""
    remove_mesh_attribute(mesh, FACE_SET_ATTRIBUTE)
    attribute = mesh.attributes.new(
        name=FACE_SET_ATTRIBUTE,
        type="INT",
        domain="FACE",
    )
    values = array("i", [BACKGROUND_FACE_SET]) * len(mesh.polygons)
    if values:
        attribute.data.foreach_set("value", values)
    mesh.update()
    return attribute


def ensure_face_sets(mesh):
    attribute = mesh.attributes.get(FACE_SET_ATTRIBUTE)
    if attribute is None:
        return reset_face_sets(mesh)
    if attribute.domain != "FACE" or attribute.data_type != "INT":
        remove_mesh_attribute(mesh, FACE_SET_ATTRIBUTE)
        return reset_face_sets(mesh)
    return attribute


def clear_mask(mesh):
    remove_mesh_attribute(mesh, MASK_ATTRIBUTE)
    mesh.update()


def object_by_pointer(pointer):
    for obj in bpy.data.objects:
        if obj.as_pointer() == pointer:
            return obj
    return None


def next_part_name(source_name):
    index = 1
    while True:
        candidate = f"PS_Part_{index:03d}_{source_name}"
        if bpy.data.objects.get(candidate) is None:
            return candidate
        index += 1


def mark_division(obj, source_id, parent_id=""):
    obj[ROLE_KEY] = ROLE_DIVISION
    obj[IS_DIVISION_KEY] = True
    obj[SOURCE_ID_KEY] = source_id
    obj[PART_ID_KEY] = obj.get(PART_ID_KEY) or uuid.uuid4().hex
    if parent_id:
        obj[PARENT_ID_KEY] = parent_id
    return obj[PART_ID_KEY]


def add_pair_id(obj, pair_id):
    try:
        pair_ids = json.loads(obj.get(PAIR_IDS_KEY, "[]"))
    except (TypeError, ValueError):
        pair_ids = []
    if pair_id not in pair_ids:
        pair_ids.append(pair_id)
    obj[PAIR_IDS_KEY] = json.dumps(pair_ids)
    obj[PAIR_ID_KEY] = pair_id


def has_pair_id(obj, pair_id):
    try:
        pair_ids = json.loads(obj.get(PAIR_IDS_KEY, "[]"))
    except (TypeError, ValueError):
        pair_ids = []
    return pair_id in pair_ids or obj.get(PAIR_ID_KEY, "") == pair_id


def archive_original_and_make_working(context, source):
    """Archive an original once and create its one independent work mesh."""
    source_name = source.name
    source_id = ensure_uuid(source)
    source[ROLE_KEY] = ROLE_ORIGINAL
    source["print_splitter_original_name"] = source_name

    target_collection = context.collection or context.scene.collection
    work = source.copy()
    work.data = source.data.copy()
    work.name = f"PS_Work_{source_name}"
    work[ROLE_KEY] = ROLE_WORKING
    work[IS_DIVISION_KEY] = False
    work.pop(GEOMETRY_SEGMENTATION_KEY, None)
    work.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
    work[SOURCE_ID_KEY] = source_id
    work[PART_ID_KEY] = uuid.uuid4().hex

    # Preserve object placement and source name; put only the backup in archive.
    archive = find_collection(ARCHIVE_COLLECTION, context.scene)
    move_object_to_collection(source, archive)
    source.hide_set(True)
    source.hide_select = True
    source.hide_render = True

    if target_collection == archive:
        target_collection = context.scene.collection
    target_collection.objects.link(work)
    reset_face_sets(work.data)
    work[FACE_SET_KEY] = TARGET_FACE_SET
    clear_mask(work.data)
    activate_only(context, work)
    return work


def prepare_division(context, obj):
    """Use an already divided object in place; never clone a division."""
    source_id = ensure_uuid(obj)
    if role_of(obj) == ROLE_WORKING:
        obj[IS_DIVISION_KEY] = False
    else:
        obj[ROLE_KEY] = ROLE_DIVISION
        obj[IS_DIVISION_KEY] = True
        obj[PART_ID_KEY] = obj.get(PART_ID_KEY) or uuid.uuid4().hex
    reset_face_sets(obj.data)
    obj[FACE_SET_KEY] = TARGET_FACE_SET
    obj.pop(GEOMETRY_SEGMENTATION_KEY, None)
    obj.pop(GEOMETRY_FACE_SET_SUMMARY_KEY, None)
    clear_mask(obj.data)
    activate_only(context, obj)
    return obj


def start_work_object(context, obj):
    if not is_mesh_object(obj):
        raise ValueError("Select a mesh object.")
    role = role_of(obj)
    if role in {ROLE_WORKING, ROLE_DIVISION} or is_division(obj):
        return prepare_division(context, obj)
    return archive_original_and_make_working(context, obj)


def mm_to_bu(value_mm, scene=None):
    scene = scene or bpy.context.scene
    scale_length = scene.unit_settings.scale_length or 1.0
    # Blender's API stores geometry in Blender Units; with no unit system,
    # interpret one BU as one meter for the add-on's millimeter controls.
    return (value_mm * 0.001) / scale_length


def collection_for_parts(scene=None):
    return find_collection(PARTS_COLLECTION, scene)


def collection_for_connectors(scene=None):
    return find_collection(CONNECTORS_COLLECTION, scene)


class PSS_OT_start_operation(bpy.types.Operator):
    bl_idname = "print_splitter.start_operation"
    bl_label = "Start New Part"
    bl_description = "Prepare a copy of an original, or reuse a divided mesh, for one piece extraction"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_mesh_object(context.active_object) and context.mode in {"OBJECT", "SCULPT"}

    def execute(self, context):
        obj = context.active_object
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            work = start_work_object(context, obj)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        bpy.ops.object.mode_set(mode="SCULPT")
        self.report({"INFO"}, f"Ready to mark a part on {work.name}.")
        return {"FINISHED"}


CLASSES = (PSS_OT_start_operation,)


def register():
    register_classes(CLASSES)


def unregister():
    unregister_classes(CLASSES)

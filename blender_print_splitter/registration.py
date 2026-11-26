"""Idempotent Blender class registration helpers."""

import bpy


def _registered_class(name):
    # bpy.types attribute lookup can return an unregistered RNA metaclass stub.
    # Query Blender's live RNA registry before calling unregister_class.
    return bpy.types.Struct.bl_rna_get_subclass_py(name, None)


def unregister_class_by_name(name):
    registered = _registered_class(name)
    if registered is not None:
        try:
            bpy.utils.unregister_class(registered)
        except RuntimeError:
            # A class can disappear between lookup and unregister during reload.
            if _registered_class(name) is not None:
                raise


def register_classes(classes):
    registered_here = []
    try:
        for cls in classes:
            existing = _registered_class(cls.__name__)
            if existing is cls:
                continue
            if existing is not None:
                unregister_class_by_name(cls.__name__)
            bpy.utils.register_class(cls)
            registered_here.append(cls.__name__)
    except Exception:
        for name in reversed(registered_here):
            unregister_class_by_name(name)
        raise


def unregister_classes(classes):
    for cls in reversed(classes):
        unregister_class_by_name(cls.__name__)

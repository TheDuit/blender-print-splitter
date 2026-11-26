"""Idempotent Blender class registration helpers."""

import bpy


def _registered_class(name):
    # Search the actual registrable base classes. bpy.types attribute lookup
    # can return an unregistered Python metaclass stub.
    for base in (bpy.types.Operator, bpy.types.Panel, bpy.types.PropertyGroup):
        registered = base.bl_rna_get_subclass_py(name, None)
        if registered is not None:
            return registered
    return None


def unregister_class_by_name(name):
    registered = _registered_class(name)
    if registered is not None:
        try:
            bpy.utils.unregister_class(registered)
        except Exception:
            # Reloads can leave Python metaclass references after Blender has
            # already removed their RNA registration.
            pass


def register_classes(classes):
    registered_here = []
    resolved_classes = []
    try:
        for cls in classes:
            # Keep an existing Blender registration in place. It may belong to
            # an earlier module instance that cannot safely be unregistered.
            existing = _registered_class(cls.__name__)
            if existing is not None:
                resolved_classes.append(existing)
                continue
            try:
                bpy.utils.register_class(cls)
            except RuntimeError as exc:
                if "already registered as a subclass" not in str(exc):
                    raise
                existing = _registered_class(cls.__name__)
                if existing is not None:
                    resolved_classes.append(existing)
                continue
            registered_here.append(cls.__name__)
            resolved_classes.append(cls)
    except Exception:
        for name in reversed(registered_here):
            unregister_class_by_name(name)
        raise
    return tuple(resolved_classes)


def unregister_classes(classes):
    for cls in reversed(classes):
        unregister_class_by_name(cls.__name__)

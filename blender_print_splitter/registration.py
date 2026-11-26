"""Idempotent Blender class registration helpers."""

import bpy


def _registered_class(name):
    # Inspect actual Python subclasses so stale bpy.types metaclass stubs are
    # never passed to unregister_class.
    for base in (bpy.types.Operator, bpy.types.Panel, bpy.types.PropertyGroup):
        for candidate in base.__subclasses__():
            if candidate.__name__ != name:
                continue
            try:
                if candidate.bl_rna.identifier == name:
                    return candidate
            except Exception:
                continue
    return None


def unregister_class_by_name(name):
    registered = _registered_class(name)
    if registered is None:
        return True
    try:
        bpy.utils.unregister_class(registered)
    except Exception:
        # Reloads can leave Python metaclass references after Blender has
        # already removed their RNA registration.
        return _registered_class(name) is None
    return _registered_class(name) is None


def register_classes(classes):
    registered_here = []
    resolved_classes = []
    try:
        for cls in classes:
            existing = _registered_class(cls.__name__)
            if existing is cls:
                resolved_classes.append(existing)
                continue
            if existing is not None:
                try:
                    bpy.utils.unregister_class(existing)
                except Exception:
                    still_registered = _registered_class(cls.__name__)
                    if still_registered is not None:
                        resolved_classes.append(still_registered)
                        continue
            try:
                bpy.utils.register_class(cls)
            except Exception:
                existing = _registered_class(cls.__name__)
                if existing is None:
                    raise
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

"""Blender Print Splitter add-on."""

bl_info = {
    "name": "Blender Print Splitter",
    "author": "Blender Print Splitter contributors",
    "version": (0, 4, 0),
    "blender": (5, 3, 0),
    "location": "View3D > Sidebar > Print Splitter",
    "description": "Analyze or paint Face Sets and split parts for 3D printing",
    "category": "Mesh",
}

from . import connectors, core, paint, segmentation, settings, split, ui


MODULES = (core, settings, paint, segmentation, split, connectors, ui)


def register():
    try:
        for module in MODULES:
            module.register()
    except Exception:
        for module in reversed(MODULES):
            try:
                module.unregister()
            except Exception:
                pass
        raise


def unregister():
    for module in reversed(MODULES):
        module.unregister()


if __name__ == "__main__":
    register()

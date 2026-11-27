# Development Guide

## Environment

- Blender 5.3.0 is the minimum supported version.
- The add-on uses Blender's bundled Python API and has no third-party package installation step.
- UI operators that use Sculpt data, viewport rays, or modal mouse input must be exercised in a Blender GUI with a 3D Viewport context. A headless run is useful for import/registration checks, but it cannot fully validate viewport workflows.

## Repository layout

```text
blender-print-splitter/
├── blender_print_splitter/   # Extension source and manifest
├── docs/                     # User, architecture, development, and troubleshooting guides
├── package.py                # Builds the installable extension ZIP
├── README.md                 # Project landing page
└── PLAN.md                   # Scope and implementation roadmap
```

## Build the extension

From the repository root:

```bash
python3 package.py
```

The script creates `blender_print_splitter-0.9.0.zip` with the extension manifest at the archive root. Install it from Blender Preferences → Get Extensions → Install from Disk.

For local iteration, copy the Python and TOML files from `blender_print_splitter/` into Blender's installed extension directory, then reload the extension or restart Blender. Avoid editing the installed copy as the source of record; make changes in this repository.

## Version updates

Keep the extension version in sync across:

1. `blender_print_splitter/__init__.py` (`bl_info["version"]`).
2. `blender_print_splitter/blender_manifest.toml` (`version`).
3. `package.py` (output ZIP name).
4. `README.md` and the user guide where the package name is shown.

The manifest minimum Blender version must remain consistent with tested API use.

## Implementation guidelines

- Keep interface labels and user-facing messages in English by default.
- Keep domain behavior in the module responsible for it: lifecycle in `core.py`, extraction in `split.py`, and connector application in `connectors.py`.
- Preserve the invariants in [Architecture](ARCHITECTURE.md#main-invariants), especially never applying Booleans to archived originals.
- Use Blender's data API and operators with explicit context checks. Viewport-dependent operators should fail with an actionable message when invoked outside a 3D Viewport.
- Treat `.sculpt_face_set` and `.sculpt_mask` as mesh attributes. Reset or clear these attributes at the documented workflow boundaries.
- Keep registration and unregistration safe after partial failures and reloads; `registration.py` contains the shared helpers.
- Update the user guide when button names, defaults, supported Blender versions, or workflows change.

## Manual QA checklist

Run these checks in Blender 5.3.0 after changing core workflows:

- Enable/disable the extension and reload it more than once; check for duplicate class or handler registration errors.
- Start from an original mesh and confirm the original keeps its name in the hidden archive while exactly one working copy is created.
- Start from an existing division and confirm no additional working copy is made.
- Paint, erase, switch modes, resize the brush, cancel, and finish a manual paint session. Confirm Face Set labels and modifier visibility behave as expected.
- Analyze Surface Features and Disconnected Parts on both simple and dense meshes; merge regions by drag and by click plus Enter.
- Extract one part and inspect both filled interfaces; repeat on a resulting division.
- Run one split with connectors disabled. Run another with a connector preview, edit its controls, confirm it, and check that failed Booleans restore both meshes.
- Test optional magnet pockets and verify wall thickness in the resulting parts.

Use this checklist for GUI validation. Complete end-to-end verification on representative production meshes is still needed to establish geometry quality and memory behavior.

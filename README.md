# Blender Print Splitter

Blender add-on for dividing a mesh into printable parts with Face Sets. It supports manual painting, fast approximate region analysis, optional pin-and-socket connectors, and paired magnet pockets.

**Version:** 0.9.0

**Blender:** 5.3.0 or later

**Default documentation language:** English

**License:** GPL-3.0-or-later

## Quick start

1. Build `blender_print_splitter-0.9.0.zip` with `python3 package.py`, then install it through **Edit → Preferences → Get Extensions → Install from Disk**.
2. Select a mesh and click **Start New Part** in the Print Splitter tab of the 3D View sidebar (`N`).
3. Paint a region or detect regions, then click **Extract Part**.
4. If connector creation is enabled, edit the preview and click **Apply Connector to Mesh** before splitting another part.

## Documentation

- [User guide](docs/USER_GUIDE.md): installation, manual and automatic workflows, connector editing, and export checks.
- [Architecture](docs/ARCHITECTURE.md): object lifecycle, Face Set data, split pipeline, and module responsibilities.
- [Development guide](docs/DEVELOPMENT.md): repository setup, packaging, version updates, and manual QA.
- [Troubleshooting](docs/TROUBLESHOOTING.md): common workflow and geometry errors.
- [Action plan](PLAN.md): implementation history, scope, and follow-up work.

## Current limitations

- Automatic surface analysis is approximate. It groups face normals and does not identify semantic features such as ears or a nose.
- Dyntopo must be disabled for Print Splitter painting, analysis, and extraction.
- Mask Slice fills split boundaries with triangulated faces. Inspect complex or non-manifold source meshes before printing.
- Hiding the archived original does not free its memory. The add-on copies an original once; later divisions are processed in place.

See the [full limitations and workflow notes](docs/USER_GUIDE.md#limitations).

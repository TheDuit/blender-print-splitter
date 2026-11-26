# Blender Print Splitter

An independent Blender add-on for splitting printable parts from a sculpted mesh using Face Sets.

## Compatibility and status

Prototype version **0.4.0**, targeting **Blender 5.3.0 and later**. The geometry analyzer and add-on registration have been checked in Blender 5.3.0; the full split workflow still needs validation on representative models.

## Installation

1. Run `python3 package.py` from this directory to build `blender_print_splitter-0.4.0.zip`.
2. In Blender, open **Edit > Preferences > Get Extensions > Install from Disk** and select the ZIP.
3. Enable **Blender Print Splitter**, then open the **Print Splitter** tab in the 3D Viewport sidebar (`N`).

You can also install the `blender_print_splitter` directory as a local add-on.

## Basic workflow

1. Select the original mesh and click **Start New Part**. The original keeps its name and is moved to a hidden, unselectable collection. The add-on creates one independent working copy.
2. In Sculpt Mode, click **Paint Region**. Left-drag paints; right-drag erases. Scroll to resize the brush, or Shift-scroll for larger steps. All strokes use the same Face Set ID and color. Press Enter to finish or Esc to cancel.
3. Optionally click **Smooth Boundary** to relax Face Set labels without moving mesh vertices.
4. Click **Extract Part**. The add-on filters small islands, attempts to join nearby regions along the mesh surface, converts the Face Set to a mask, and uses Blender's Mask Slice to create complementary parts with filled interface boundaries. Less common controls are grouped under **Options**.
5. A connector pair is created automatically at the split interface as editable helper geometry. Adjust its diameter, depth, clearance, position, rotation, and scale in the panel. No Boolean modifier is active during this positioning phase.
6. Select a connector helper or either part and click **Apply Connector to Mesh**. Choose **Manifold**, **Exact**, or **Float** in the dialog; Manifold is the default. Confirm to apply the pin union and socket cut with that solver, then remove the temporary helpers.
7. The remainder and extracted part are marked as divisions. Starting another split on a division processes it in place without making another full-mesh copy.

## Alternative workflow: analyze the mesh

1. Choose **Surface Features** or **Disconnected Parts**, then click **Analyze Mesh**.
2. **Surface Features** finds connected regions from changes in the mesh's surface curvature. Tiny patches are merged into the neighboring region with the widest shared boundary. It does not depend on marked sharp edges, seams, or material slots. **Disconnected Parts** creates one Face Set per connected mesh component.
3. Choose a region and click **Extract Selected Region**. To combine regions or refine the labels with Blender's native Draw Face Sets brush, expand **Options**.
4. Face Sets are cleared on both resulting parts; analyze the selected piece again if it needs another automatic split.

The curvature angle and scale, minimum region size, merge tools, and cleanup controls are in the collapsed **Options** section. Geometry regions are editable proposals: the analyzer can separate clear forms such as ears, eyes, and muzzle on suitable meshes, but it does not recognize semantic labels such as "nose" or "face". Use the native Face Set brush to adjust boundaries before extracting.

## Prototype limitations

- The brush builds its surface from the base mesh and paints geodesically across adjacent faces. Models with complex topology or modifiers need additional validation.
- Dyntopo must be disabled. Modifiers are temporarily hidden while painting so the brush maps to the base mesh, then restored when the brush finishes or is cancelled.
- Automatic region merging follows the shortest path over the mesh topology and may not suit every model. Review the painted region before extracting.
- Geometry segmentation measures curvature from mesh topology and face normals, then coalesces tiny neighboring patches. Meshes with gradual folds or very uneven topology can still need manual edits. The analyzer uses compact mesh buffers rather than a second full BMesh copy, and the curvature scale helps produce useful regions across different mesh densities.
- The automatic connector starts at the average of the painted interface vertices; inspect and adjust its shared controller when the boundary is curved or irregular.
- Mask Slice fills the two interface boundaries with triangulated faces; the result still needs inspection on complex or non-manifold source meshes.
- Mask Slice uses temporary mesh copies while splitting; peak memory can rise during the operation on dense models.
- The Manifold solver requires manifold split parts. Exact handles overlapping geometry at a higher cost; Float is faster but does not support overlapping geometry. If the chosen solver fails, the add-on reports the error and restores the parts.
- Connector Booleans are applied when confirmed and are not editable as live modifiers afterward. Use Blender Undo before continuing if the confirmed fit needs to be adjusted.
- An internal marker identifies divided objects even after they are renamed. The `PS_Part_` name prefix is only a visual hint.

See the detailed [action plan](./PLAN.md).

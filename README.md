# Blender Print Splitter

An independent Blender add-on for splitting printable parts from a sculpted mesh using Face Sets.

## Compatibility and status

Prototype version **0.3.7**, targeting **Blender 5.3.0 and later**. Registration lifecycle has been checked in Blender 5.3.0; the full split workflow still needs validation on representative models.

## Installation

1. Run `python3 package.py` from this directory to build `blender_print_splitter-0.3.7.zip`.
2. In Blender, open **Edit > Preferences > Get Extensions > Install from Disk** and select the ZIP.
3. Enable **Blender Print Splitter**, then open the **Print Splitter** tab in the 3D Viewport sidebar (`N`).

You can also install the `blender_print_splitter` directory as a local add-on.

## Basic workflow

1. Select the original mesh and click **Start New Part**. The original keeps its name and is moved to a hidden, unselectable collection. The add-on creates one independent working copy.
2. In Sculpt Mode, left-drag with **Paint Face Set** to mark a region; right-drag to erase it. A circular radius preview follows the cursor. Scroll to resize it, or Shift-scroll for larger steps. All strokes use the same Face Set ID and color. Press Enter to finish or Esc to cancel.
3. Use **Smooth Face Sets** to relax the Face Set labels. This changes the division boundary without moving mesh vertices.
4. Click **Extract Part**. The add-on filters small islands, attempts to join nearby regions along the mesh surface, converts the Face Set to a mask, and uses Blender's Mask Slice to create complementary parts with filled interface boundaries.
5. A connector pair is created automatically at the split interface as editable helper geometry. Adjust its diameter, depth, clearance, position, rotation, and scale in the panel. No Boolean modifier is active during this positioning phase.
6. Select a connector helper or either part and click **Apply Connector to Mesh**. Choose **Manifold**, **Exact**, or **Float** in the dialog; Manifold is the default. Confirm to apply the pin union and socket cut with that solver, then remove the temporary helpers.
7. The remainder and extracted part are marked as divisions. Starting another split on a division processes it in place without making another full-mesh copy.

## Alternative workflow: geometry-based Face Sets

1. Start a part as usual and choose **Surface Folds** or **Disconnected Parts** under **Analyze the Mesh**.
2. For **Surface Folds**, set the normal-angle threshold and click **Generate Geometry Face Sets**. Blender's native **By Normals** initializer groups connected faces by their normal directions. **Disconnected Parts** uses Blender's native loose-parts initializer. Neither mode reads marked sharp edges, seams, or material slots.
3. Choose a **Region to Extract**. To combine regions, choose a destination under **Merge Into** and click **Merge Regions**. This relabels the source faces and leaves the mesh geometry unchanged.
4. Click **Native Face Set Brush** to refine the generated regions with Blender's native Draw Face Sets brush. Click **Refresh List** after the brush creates or changes regions.
5. Click **Extract Selected Region**. Face Sets are cleared on both resulting parts; analyze the selected piece again if it needs another automatic split.

Use **Switch to Manual Paint** to discard the generated regions and return to the Print Splitter brush workflow. The generated segmentation is temporary: both resulting pieces have their Face Sets cleared after extraction, and each can be analyzed again independently.

## Prototype limitations

- The brush builds its surface from the base mesh and paints geodesically across adjacent faces. Models with complex topology or modifiers need additional validation.
- Dyntopo must be disabled. Modifiers are temporarily hidden while painting so the brush maps to the base mesh, then restored when the brush finishes or is cancelled.
- Automatic region merging follows the shortest path over the mesh topology and may not suit every model. Review the painted region before extracting.
- Geometry segmentation uses Blender's native face-normal flood fill or disconnected-component initializer. Smooth surfaces without clear folds may produce one large region, while dense uneven topology may produce many small regions; adjust the fold threshold, merge Face Sets, and refine them with the native brush before extracting.
- The automatic connector starts at the average of the painted interface vertices; inspect and adjust its shared controller when the boundary is curved or irregular.
- Mask Slice fills the two interface boundaries with triangulated faces; the result still needs inspection on complex or non-manifold source meshes.
- Mask Slice uses temporary mesh copies while splitting; peak memory can rise during the operation on dense models.
- The Manifold solver requires manifold split parts. Exact handles overlapping geometry at a higher cost; Float is faster but does not support overlapping geometry. If the chosen solver fails, the add-on reports the error and restores the parts.
- Connector Booleans are applied when confirmed and are not editable as live modifiers afterward. Use Blender Undo before continuing if the confirmed fit needs to be adjusted.
- An internal marker identifies divided objects even after they are renamed. The `PS_Part_` name prefix is only a visual hint.

See the detailed [action plan](./PLAN.md).

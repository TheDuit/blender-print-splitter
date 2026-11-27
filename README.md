# Blender Print Splitter

An independent Blender add-on for splitting printable parts from a sculpted mesh using Face Sets.

## Compatibility and status

Prototype version **0.9.0**, targeting **Blender 5.3.0 and later**. Surface analysis uses Blender's native normal-based Face Set initializer for faster processing on dense meshes. Manual painting follows Blender's sculpt brush conventions: the same Face Set is painted with each stroke, `E` switches to erase, `P` switches back to paint, and `F`-drag changes brush size. Complex user meshes still need inspection because Mask Slice output depends on the source topology.

## Installation

1. Run `python3 package.py` from this directory to build `blender_print_splitter-0.9.0.zip`.
2. In Blender, open **Edit > Preferences > Get Extensions > Install from Disk** and select the ZIP.
3. Enable **Blender Print Splitter**, then open the **Print Splitter** tab in the 3D Viewport sidebar (`N`).

You can also install the `blender_print_splitter` directory as a local add-on.

## Basic workflow

1. Select the original mesh and click **Start New Part**. The original keeps its name and is moved to a hidden, unselectable collection. The add-on creates one independent working copy.
2. Before painting or analyzing, choose **Add connector after split** in the panel. Turn it off to separate parts without creating connector helpers or requiring connector confirmation. In Sculpt Mode, click **Paint** or **Erase**, then left-drag on the mesh. Press `E` to erase, `P` to paint again, and hold `F` while dragging to resize. Right/middle mouse and the wheel remain available for viewport navigation. All paint strokes use the same Face Set ID and color. Press Enter to finish or Esc to cancel.
3. Optionally click **Smooth Face Sets** to relax Face Set labels without moving mesh vertices.
4. Click **Extract Part**. The add-on filters small islands, attempts to join nearby regions along the mesh surface, converts the Face Set to a mask, and uses Blender's Mask Slice to create complementary parts with filled interface boundaries. Less common controls are grouped under **Options**.
5. A male connector is embedded 5 mm into its target by default and reaches across the interface. Choose a cylinder or a tapered square key, then adjust its size, reach, embed depth, clearance, position, rotation, and scale. No Boolean runs during preview.
6. While editing the connector, optionally enable **Add Magnet Pockets** and set magnet diameter, depth, and fit clearance. The preview places a matching pocket in each half, beside the connector. The pockets are cut when the connector is applied.
7. Select a connector helper or either part and click **Apply Connector to Mesh**. Choose **Manifold**, **Exact**, or **Float** in the dialog; Manifold is the default. The add-on checks that each result remains closed and that the connector adds volume and the sockets remove volume. Failed results are rolled back and the preview stays available.
8. The remainder and extracted part are marked as divisions. Starting another split on a division processes it in place without making another full-mesh copy.

## Alternative workflow: analyze the mesh

1. Choose **Surface Features** or **Disconnected Parts**, then click **Analyze Mesh**.
2. **Surface Features** uses Blender's native normal-based Face Set initializer to divide connected surface regions. It does not depend on marked sharp edges, seams, or material slots. **Disconnected Parts** uses Blender's native loose-part initializer. Both avoid the add-on's former Python traversal over every face and edge.
3. The largest generated Face Set is selected as **Mother** by default. Change that dropdown if another region should stay on the remainder, then choose **Part** to extract.
4. Click **Merge Face Sets**, then click the source and destination regions and press Enter. Or drag from the source onto the destination to merge immediately. Right-click clears the selection; Esc exits without changing the mesh. The source labels are reassigned to the destination without moving vertices.
5. If **Create connector after split** is enabled, edit and confirm the connector before splitting the next region. The add-on blocks another split while a connector is unresolved. If the option is disabled, the split completes without connector helpers.
6. To refine boundaries with Blender's native Draw Face Sets brush, expand **Options**. Face Sets are cleared on both resulting parts; analyze the selected piece again if it needs another automatic split.

The **Normal Angle** threshold and cleanup controls are in the collapsed **Options** section. A larger angle creates fewer, broader regions; a smaller angle creates more regions. This fast detector is intentionally approximate. Use the native Face Set brush or **Merge Face Sets** to adjust the regions before extracting; the analyzer does not recognize semantic labels such as "nose" or "face".

## Prototype limitations

- The brush builds its surface from the base mesh and paints geodesically across adjacent faces. Models with complex topology or modifiers need additional validation.
- Dyntopo must be disabled. Modifiers are temporarily hidden while painting so the brush maps to the base mesh, then restored when the brush finishes or is cancelled.
- Automatic region merging follows the shortest path over the mesh topology and may not suit every model. Review the painted region before extracting.
- Geometry segmentation uses Blender's native normal grouping. It is faster on dense meshes but may leave small regions or combine features that the earlier scale-aware detector separated. Adjust the Normal Angle or edit Face Sets manually.
- The automatic connector starts at the average of the painted interface vertices; inspect and adjust its shared controller when the boundary is curved or irregular.
- The optional magnet pockets are paired, centered on the split plane, and placed beside the pin. Check wall thickness and available space before applying them.
- Mask Slice fills the two interface boundaries with triangulated faces; the result still needs inspection on complex or non-manifold source meshes.
- Mask Slice uses temporary mesh copies while splitting; peak memory can rise during the operation on dense models.
- The Manifold solver can correct some small topology defects in split parts, then checks that both results are closed and have the expected volume change. More severe defects can still make it fail; the add-on restores both parts and keeps the preview available.
- Connector Booleans are applied when confirmed and are not editable as live modifiers afterward. Use Blender Undo before continuing if the confirmed fit needs to be adjusted.
- An internal marker identifies divided objects even after they are renamed. The `PS_Part_` name prefix is only a visual hint.

See the detailed [action plan](./PLAN.md).

# User Guide

Blender Print Splitter prepares one piece per interaction. Mark a region, extract it from the remainder, optionally configure a connector, and repeat on a resulting division when needed.

## Requirements

- Blender 5.3.0 or later.
- A mesh object with faces.
- Dyntopo disabled while using the add-on's paint, analysis, and extraction tools.

The add-on works in Sculpt Mode after **Start New Part** prepares the mesh.

## Installation

1. From the project directory, run `python3 package.py`.
2. In Blender, open **Edit → Preferences → Get Extensions → Install from Disk**.
3. Choose `blender_print_splitter-0.9.0.zip` and enable Blender Print Splitter.
4. In the 3D Viewport, press `N` and open the **Print Splitter** tab.

To install a local development copy, place the `blender_print_splitter` package in Blender's add-on or extension directory. Restart Blender or reload the extension after changing its files.

## Start a split

1. Select the source mesh and click **Start New Part**. The add-on switches to Sculpt Mode and prepares the working mesh.
2. Decide whether to enable **Add connector after split** before marking or detecting the region. Turn it off to split without connector helpers or a connector confirmation step.
3. Choose manual painting or automatic region detection below.
4. Click **Extract Part** after marking a region.

### Original meshes and later splits

On the first use, the original keeps its name and moves to the hidden, unselectable **Print Splitter | Archived Originals** collection. The add-on creates one working copy. Extracted pieces are named with a `PS_Part_` prefix and stored in **Print Splitter | Parts**.

The add-on identifies divisions with internal object properties, so renaming a division does not make it an original. Starting another split on a division reuses it in place and does not create another full-mesh copy. Each successful split clears Face Sets and masks from the resulting meshes; analyze or paint the selected division again before its next split.

## Manual paint workflow

1. Click **Paint** to paint, or **Erase** to begin in erase mode.
2. Left-drag over the mesh. Every paint stroke writes the same target Face Set ID, so you do not need to hold Ctrl to continue the region.
3. Press `E` to switch to erase mode and `P` to return to paint mode. Erasing returns faces in the target region to the background Face Set.
4. Use `F` while dragging to resize the brush. The **Brush Size** field also controls the active Sculpt brush size. If pressure-based size is enabled on the active brush, tablet pressure affects the radius.
5. Right mouse, middle mouse, and the wheel pass through to viewport navigation. Press Enter to finish the painting session or Esc to discard its strokes.
6. Optionally click **Smooth Face Sets**. This changes Face Set labels and leaves vertex positions unchanged.
7. Click **Extract Part**.

The brush uses a surface-aware region around each stroke. Modifiers are temporarily hidden so ray hits map to the base mesh Face Set data, then restored when the session ends.

## Automatic region workflow

1. In **Or detect regions automatically**, choose a method and click **Detect**.
   - **Surface Features** uses Blender's native normal-based Face Set initializer. **Normal Angle** is available under **Options**. A larger angle generally creates broader regions and fewer boundaries.
   - **Disconnected Parts** creates regions from disconnected mesh components.
2. The largest generated region by face count is selected as **Mother** by default. Choose a different Mother if necessary, then choose the **Part** to extract.
3. To combine regions, click **Merge Regions**. Drag from the source region to the destination to merge immediately, or click the two regions and press Enter. Right-click clears the selection; Esc cancels.
4. **Edit Boundaries** activates Blender's native Draw Face Sets brush. That brush follows Blender's normal Face Set drawing behavior ([Blender 5.3 reference](https://docs.blender.org/manual/en/5.3/sculpt_paint/sculpting/brushes/draw_facesets.html)); the Print Splitter **Paint** button is the mode that keeps one target Face Set automatically. Use **Options → Refresh Regions** after native-brush edits if the Mother and Part lists need updating.
5. Click **Extract Part**. The Mother remains on the remainder; the selected Part is extracted. In this workflow the connector pin is placed on the Mother and the socket on the extracted Part.

Generated regions are proposals, not semantic labels. The analyzer may combine nearby forms or make extra regions on a noisy surface. Merge regions or edit them with the native brush before extraction. To clear the analysis and switch back to manual painting, expand **Options** and click **Clear Regions and Paint Manually**.

The initial method is **Surface Features** with a 60° normal angle. The largest generated region by face count is the default Mother; the next largest is initially selected as Part when one exists.

## Connector preview and confirmation

When **Add connector after split** is enabled, the add-on creates editable helper geometry at the split interface. Previewing does not run Boolean operations on the part meshes.

| Control | Purpose |
| --- | --- |
| Shape | Round cylinder or tapered square key. |
| Diameter / Key Width | Connector width. |
| Reach / Socket | Length across the interface and into the socket. |
| Pin Embed Depth | How far the male connector enters its base part. |
| Fit Clearance | Clearance between the pin/key and socket. |
| Position, Rotation, Scale | Transform the shared connector controller in the panel. |
| Add Magnet Pockets | Create matching pockets beside the connector. |
| Magnet Diameter, Depth, Fit Clearance | Set pocket dimensions and magnet fit. |

The initial connector defaults are 4 mm width, 3 mm reach, 5 mm embed depth, and 0.2 mm fit clearance. Magnet pockets are off by default; when enabled, their initial dimensions are 6 mm diameter, 2 mm depth, and 0.2 mm radial clearance. Adjust these values for the model, printer, and hardware.

Connector and magnet dimensions are entered in millimeters and converted using the scene's unit scale. Check the scene units and object transforms if the preview dimensions do not match the intended print measurements.

Inspect the preview, then click **Apply Connector to Mesh**. Choose **Manifold**, **Exact**, or **Float** in the confirmation dialog; Manifold is the default. The add-on applies the male union, female socket cut, and enabled magnet cuts, then checks the results for closed edges and expected volume changes. If validation fails, both part meshes are restored and the helpers remain available for adjustment.

Resolve a pending connector pair before extracting another part. When connector creation was turned off before the split, no helpers are created and no confirmation is required.

## Advanced options

The collapsed **Options** section contains less common controls:

- **Boundary Smoothing Iterations**: number of label-relaxation passes for Smooth Face Sets (default: 1).
- **Ignore Islands Below (%)**: ignore small disconnected areas of the manually painted target (default: 1%).
- **Merge Regions Within (mm)**: maximum surface-path distance used to bridge nearby painted areas (default: 1 mm).
- **Mask Threshold**: threshold passed to Blender's Mask Slice operation (default: 0.5).
- **Normal Angle (°)**: grouping threshold for Surface Features analysis (default: 60°).
- **Refresh Regions**: update region selectors after native Face Set edits.
- **Clear Regions and Paint Manually**: remove generated analysis data and return to manual mode.

## Export checks

Before exporting for printing:

1. Inspect the remainder and extracted part, including the filled interface surfaces.
2. Check connector fit, magnet polarity, and remaining wall thickness in the slicer or a mesh inspection tool.
3. Confirm the parts are closed and have the intended dimensions after applying the connector.
4. Export the actual division objects. The archived original is hidden and is not part of the split output.

## Limitations

- Automatic surface analysis is based on normal grouping, not feature recognition. It cannot identify parts such as a face, nose, or ear by meaning.
- Highly uneven tessellation can affect which region is selected as the default Mother because that choice uses face count.
- Dyntopo is unsupported in the current paint, analysis, and extraction workflow.
- Complex modifiers are hidden during manual painting so the add-on can paint the base mesh. Apply or otherwise validate modifiers before splitting if their evaluated shape matters.
- Mask Slice creates triangulated caps. The add-on does not guarantee quad-dominant or self-intersection-free output.
- Pre-existing non-manifold geometry can cause splitting or Boolean validation to fail. The add-on does not repair arbitrary source mesh defects.
- Dense Mask Slice operations can temporarily use additional memory. Hiding the archived original does not release its mesh memory.
- Magnet polarity is not inferred. Mark and orient physical magnets consistently yourself.
- Connector Booleans are applied on confirmation and are not retained as editable live modifiers. Use Blender Undo if you need to revise a confirmed connector.

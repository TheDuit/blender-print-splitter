# Troubleshooting

## Print Splitter tab or buttons are missing

- Confirm **Blender Print Splitter** is enabled in Preferences → Get Extensions.
- Reload the extension or restart Blender after installing a new ZIP.
- Select a mesh and click **Start New Part**. Paint, analysis, and extraction buttons are available for a working mesh in Sculpt Mode.

## Paint, detection, or extraction is disabled

- Check that the active object is a mesh in Sculpt Mode and has been prepared with **Start New Part**.
- Disable Dyntopo. The current workflow requires stable base-mesh face indices.
- In automatic analysis, use a mesh that contains faces and make it the active object.

## Painting does not change the expected region

- Click **Paint** and left-drag over the surface. The add-on paints one target Face Set across all strokes.
- Press `P` to paint and `E` to erase. Erase mode only returns faces belonging to the target set to the background.
- Use **Brush Size** or hold `F` while dragging to resize.
- If a modifier changes the visible surface, note that modifiers are hidden during the paint session so the base mesh receives Face Set labels.
- Press Enter to keep the session's changes. Esc cancels its strokes.

## Automatic analysis makes too few, too many, or unexpected regions

- **Surface Features** groups adjacent faces by normal similarity; it does not recognize semantic parts.
- Adjust **Normal Angle** in **Options**. Larger values generally create broader regions; smaller values generally create more boundaries.
- Try **Disconnected Parts** only when separate mesh islands should become separate regions.
- Merge or edit regions manually. The largest region by face count is only a default Mother selection and can be misleading on unevenly tessellated meshes.

## Extract Part reports that no region was found

- Paint at least one visible region, or run **Detect** and choose a generated Part region.
- In automatic mode, Mother and Part must be different regions.
- If you used Blender's native Draw Face Sets brush, use **Options → Refresh Regions** before choosing the Part.

## The next split is blocked

If **Add connector after split** was enabled, the connector pair is pending. Select either part or its helper and finish **Apply Connector to Mesh**. If no connector is desired on future splits, turn the option off before starting that split.

## A connector preview is missing or cannot be applied

- Ensure both split parts still exist and are separate mesh datablocks.
- Inspect the preview against the interface. Adjust size, reach, embed depth, clearance, or the shared controller transform.
- A connector can fail validation if the pin does not intersect its target, the socket cutter misses, a part has zero measurable volume, or the result contains open/non-manifold edges.
- If Manifold fails, retry in the confirmation dialog with Exact or Float. The add-on restores both meshes after a failed operation and keeps the preview available.
- Disable magnet pockets or reduce their depth/diameter if they weaken a thin wall or intersect other geometry.

## The split cap or mesh looks poor

Mask Slice triangulates the interface caps. Inspect the source for open edges, self-intersections, very thin features, and dense boundary noise before extracting. The add-on does not guarantee quad caps or repair arbitrary non-manifold input.

## Blender reports a registration error after reload

1. Disable Blender Print Splitter in Preferences.
2. Restart Blender to clear stale RNA class references.
3. Enable the add-on again and check the system console for the first error in the traceback.

If the error persists, capture the complete traceback, Blender version, and the action that triggered it.

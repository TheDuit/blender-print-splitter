# Blender Print Splitter — Action Plan

## Objective

Build a Sculpt Mode add-on with two independent ways to mark a printable part: paint one region manually, or analyze the selected mesh and generate temporary geometry-based Face Sets for its surface regions. The user can merge generated regions and refine them with Blender's native Draw Face Sets brush, then split one selected region into two complementary capped parts. Generated sets are cleared after each split; a later split starts with a fresh analysis. Connector creation is optional; when enabled, the user can configure the shape and paired magnet pockets before applying the Booleans. Boolean operations must never use the archived original mesh.

The add-on is an independent project outside the Imobflow repository. **English is the default language for the UI, messages, and documentation.** The compatibility target is **Blender 5.3.0 and later**.

## Implementation status — v0.8.0

- [x] Keep manual painting and geometry analysis as separate workflows.
- [x] Use Blender's native normal-based Face Set initializer for surface analysis, avoiding repeated Python traversals across dense meshes.
- [x] Use Blender's native loose-part initializer for disconnected-component analysis; map results to the add-on's region IDs in one linear pass.
- [x] Sacrifice some boundary accuracy for faster analysis; select the largest generated region as the initial mother and leave refinement to the user.
- [x] Keep the main panel focused on paint, smooth, analyze, and extract; collapse less common controls under **Options**.
- [x] Use connected mesh components for the separate **Disconnected Parts** analysis.
- [x] Let geometry mode select a retained mother region; place male pins on the mother and female sockets on extracted parts.
- [x] Preselect the largest region as the mother, while allowing manual override.
- [x] Embed pins 5 mm into their base by default and validate closed topology plus expected volume changes after each Boolean.
- [x] Let Manifold try to correct minor Mask Slice topology defects, then validate output and roll back invalid results.
- [x] Block the next split until the current connector pair is confirmed; restore both backups if a Boolean fails validation.
- [x] Add a pre-paint/pre-analysis checkbox to split without creating connector helpers or requiring confirmation.
- [x] Offer cylindrical pins or tapered square keys, with the shape editable in the connector panel.
- [x] Add optional paired magnet pockets with editable diameter, depth, and fit clearance beside the connector.
- [x] Provide region selection, merge-by-relabeling, list refresh, and native Draw Face Sets brush access.
- [x] Add a Sculpt Mode Face Set merge tool: drag source to destination for immediate merge, or click both and confirm with Enter.
- [x] Replace the scale-aware Python detector and automatic tiny-region merging with Blender's native normal grouping and manual region merging.
- [x] Exercise 84 click/drag selection-state sequences on the default seven-region result and validate click/Enter, drag, right-click clear, and Esc cancel in the Blender 5.3 UI.
- [x] Clear generated Face Sets after each successful split so a resulting piece can be analyzed again.
- [x] Recover from partial Blender registration by removing stale classes and handlers before re-registering.
- [x] Check Blender's RNA registry before unregistering stale Python class references.
- [x] Build an installable extension ZIP and statically parse the Python modules.
- [x] Verify register, repeated register/unregister, hot reload, and recovery from partial registration in Blender 5.3.0.
- [x] Defer legacy Boolean preview cleanup until Blender exits its restricted registration context.
- [ ] Run the complete workflow in Blender 5.3.0 on representative meshes; this remains the next validation step.

## Required workflow

1. Select a mesh object and click **Start New Part**.
2. On the first split, preserve the original object's name and archive it in a hidden, unselectable collection. Create exactly one independent working copy. If the selected mesh is already marked as a division, process it in place without copying it.
3. Choose whether to create a connector after the split. Choose one marking workflow: paint one region with the Print Splitter brush, or analyze approximate surface-normal regions / disconnected mesh components. The geometry workflow does not depend on material slots or marked seams/edges.
4. In geometry mode, click **Merge Face Sets**, select a source and destination region then press Enter, or drag source to destination to merge immediately. Right-click clears the selection; Esc cancels. Use Blender's native **Draw Face Sets** brush for manual boundary edits. The Print Splitter brush and **Smooth Face Sets** remain part of the separate manual flow.
5. In the manual paint workflow, ignore small painted islands and optionally bridge nearby target regions along the mesh surface. Geometry analysis uses Blender's fast approximate normal grouping; merge or repaint generated regions manually if needed.
6. Convert the selected Face Set to a mask and use Blender's Mask Slice with a new object and hole filling, producing complementary parts with matching capped boundaries. Clear Face Sets on both results; run a fresh analysis before a later geometry-based split. Mark both parts as divisions.
7. If enabled, create an editable connector preview at the interface after the split. Choose a cylinder or tapered square key; embed the connector 5 mm into its base by default. Optionally add matching magnet pockets on both halves. Keep position, rotation, scale, and dimensions adjustable without running Boolean operations. Apply the connector and pockets only after explicit confirmation.

Each interaction extracts one part. The original keeps its name and remains preserved in the archive collection. The remainder or any extracted division can be split again without creating another full-mesh copy.

## Scope

### Included in the prototype

- Work on one active mesh at a time.
- Create a single working copy the first time an original mesh enters the split workflow; archive and hide the original while preserving its name.
- Identify divisions with persistent internal custom properties, independently of object names. Use a readable `PS_Part_` prefix as an optional visual cue.
- Reuse an already divided mesh directly, without making another copy.
- Clear old Face Sets and masks before each new interaction.
- Provide a custom Face Set paint tool that assigns one ID and color across strokes without Ctrl.
- Offer a separate geometry-analysis workflow using Blender's native face-normal grouping to identify approximate surface regions, plus native disconnected-part detection. Users can merge and edit generated regions manually.
- Let the user choose a retained mother Face Set; select the largest generated region by default and extract other regions one at a time. Put the male pin on the mother and the female socket on each extracted piece; require connector confirmation before the next split.
- Let users turn connector creation off before painting or analyzing; a split without a connector creates no pending pair and does not block the next split.
- Let users choose the target region, merge one Face Set into another by relabeling faces, and activate Blender's native Draw Face Sets brush for manual cleanup in geometry mode.
- Let users merge regions by selecting them directly on the mesh: drag source onto destination to confirm, or click both and press Enter.
- Clear generated Face Sets after each split so repeated splits reanalyze only the selected resulting mesh.
- Use left-drag to paint and right-drag to erase before applying the split; display brush and eraser cursors plus a circular radius preview. Allow scrolling to resize the brush while painting.
- Discard small disconnected painted islands and try to merge nearby large regions along mesh topology.
- Smooth only Face Set labels; do not deform mesh vertices.
- Convert the selected Face Set to a point-domain mask and use Blender's Mask Slice to create both complementary parts with filled boundaries.
- Automatically position an editable cylindrical pin/socket or tapered square-key helper pair at the split interface. Embed the male connector into its target and extend it across the seam. Size the socket cutter with the configured fit clearance and a small Boolean overlap.
- Optionally add matching, side-by-side magnet pockets in both split parts; configure magnet diameter, depth, and fit clearance while editing the connector.
- Apply the connector union, socket cut, and optional magnet-pocket cuts only after explicit confirmation in a dialog. Offer Manifold, Exact, and Float solvers, with Manifold as the default. Check closed topology and expected volume changes; restore both mesh backups if any operation is invalid.
- When connector creation is enabled, block further part extraction until the current connector preview is confirmed. When disabled, allow repeated splits without connector confirmation.
- Keep split operations compatible with Blender Undo.

### Planned follow-up work

- Add independent fit clearance between the mating part surfaces and connector clearance, in millimeters.
- Improve preview and validation for boundary topology, non-manifold results, thin walls, and connector collisions.
- Prepare confirmed connector geometry for export and improve recovery if either Manifold Boolean fails.
- Improve the paint tool's performance and memory use on dense meshes.
- Consider additional paint controls after the core workflow is validated.

### Out of scope for the first usable version

- Snap-fit, dovetail, and other complex connector profiles.
- Automatic identification of magnet polarity. The add-on can create and position pockets, but users must determine and mark physical polarity.
- General repair of pre-existing non-manifold meshes or self-intersections.
- A guarantee of quad-dominant output. Closed, printable geometry and functional fits take priority.
- Processing multiple source objects or multiple Face Sets in one interaction.

## Implementation stages

### Stage 0 — Confirm environment and use cases

1. Target Blender 5.3.0 as the minimum supported version.
2. Gather representative models: a clean mesh, a curved split, a small region, a jagged boundary, and a mesh with a known defect.
3. Record expected print units and object scale behavior.
4. Define expected behavior when a painted region cannot produce a valid solid.

**Deliverable:** a short compatibility matrix and representative project files for validation.

### Stage 1 — Geometry proof of concept

1. Confirm one-time copying, original-name preservation, and hidden/unselectable archival.
2. Confirm that every manual paint stroke uses one Face Set ID without Ctrl.
3. Confirm that native normal analysis and disconnected-part mode generate usable Face Sets on representative meshes, including dense meshes; measure analysis time and review the accuracy tradeoff.
4. Confirm Face Set merge relabels faces without changing mesh geometry and that the native Draw Face Sets brush edits generated labels.
5. Confirm generated Face Sets are cleared after a split and a later split analyzes the current mesh again.
6. Test Face Set-to-mask conversion and `paint_mask_slice(new_object=True, fill_holes=True)`; inspect matching cap topology and mask thresholds.
7. Validate the FACE-domain to POINT-domain mask mapping at vertices shared by marked and unmarked faces.
8. Measure connected components, discard small islands, and fill short geodesic gaps between large components.
9. Evaluate dense, thin, curved, and concave meshes. Inspect thickness, boundary quality, normals, and manifoldness.
10. Prototype connector helper geometry after extraction; apply the selected Boolean solver only after explicit confirmation and without modifying the archived original. Manifold is the default.
11. Repeat splits on the remainder and on an extracted division, without making another full-mesh copy.
12. Measure memory on dense models. Verify that repeated splits retain the original, the one initial working copy, and the resulting parts, without further full-mesh clones.

**Exit criteria:** validate the Face Set → label smoothing → mask → complementary Mask Slice sequence, choose conservative defaults for island cleanup and gap filling, and confirm division metadata.

### Stage 2 — Add-on structure and minimal interface

1. Package the Python add-on with a manifest, registration/unregistration, and required preferences.
2. Add a dedicated panel to the 3D Viewport sidebar (N-panel).
3. Implement **Start New Part**: archive and copy an original once; reuse a marked division directly.
4. Register the custom paint tool and assign every stroke to the same Face Set.
5. Add component cleanup and a label-only **Smooth Face Sets** action.
6. Add **Surface Features** and **Disconnected Parts** analysis, plus target selection, Face Set merging, list refresh, and native Draw Face Sets brush activation.
7. Keep generated segmentation temporary and clear it after each split; reanalyze the selected piece on a later geometry-based interaction.
8. Convert the selected Face Set to a mask and use Mask Slice to create both complementary parts with filled interfaces.
9. Mark both resulting objects as divisions using internal properties.
10. Show the active object's state and provide clear prerequisite/error messages.
11. Organize archived originals, extracted parts, and connector helpers into collections.

### Stage 3 — Automatic pin/socket connector and magnet pockets

1. Create visible helper objects at the interface after a split when connector creation is enabled.
2. Expose connector shape, position, rotation, scale, width/diameter, depth, and fit through the panel.
3. Expose magnet-pocket enablement, diameter, depth, and fit clearance in the connector editor.
4. Update helper geometry and transform controls without Boolean operations or changes to the archived original.
5. Provide an **Apply Connector to Mesh** button and a confirmation dialog that offers Manifold, Exact, and Float before applying both operations and removing the helpers.
6. Validate performance, alignment, minimum wall thickness, manifoldness, and collisions on both halves.
7. Allow users to split without connectors by turning off the checkbox before painting or analysis.
8. Make magnet orientation visible without inferring or setting physical polarity.

### Stage 4 — Friendlier Face Set editing

1. Keep **Smooth Face Sets** in the panel as a topology-only relabeling operation.
2. Expose the number of label-relaxation iterations and refresh the viewport after execution.
3. Do not move or smooth the mesh surface in this tool.

### Stage 5 — Validation and packaging

1. Validate the representative models in Blender 5.3.0 and each additional declared supported version.
2. Check dimensions, clearances, manifoldness, normals, and STL/3MF export.
3. Check Undo, cancellation, and error handling.
4. Maintain English installation instructions, known limitations, and a quick-start guide.
5. Build an installable ZIP and prepare a demonstration scene.

## Acceptance criteria

- The original keeps its name and is hidden and unselectable in an archive collection when the first split begins.
- The original mesh is copied only once. Marked divisions are processed in place.
- Internal metadata identifies divisions even after users rename the objects; the name prefix is only a visual hint.
- Each interaction turns its input mesh into the remainder and creates exactly one extracted part, with connector creation controlled by the pre-paint/pre-analysis checkbox.
- Manual mode clears Face Sets and paints one target set per interaction.
- Geometry mode creates approximate regions from face normals or disconnected components, without using marked seams, sharp edges, or material data.
- Geometry mode exposes the generated regions for target selection, merge-by-relabeling, and native Draw Face Sets brush cleanup.
- Geometry mode has a dedicated modal merge tool with on-mesh source/target selection and both drag-to-merge and Enter-to-confirm interaction paths.
- The modal merge tool uses the base-mesh Face Set data, shows the selected and hovered region IDs in the status bar, and restores modifier visibility when it exits.
- The modal reports hovered/source/target Face Set IDs and face counts. Right-click clears its selection; middle mouse, NDOF, and wheel events pass through to viewport navigation.
- In geometry mode, a selected mother region stays on the remainder and receives the male connector. Each selected peripheral region becomes a female part. If connector creation is enabled, another part cannot be extracted until the current connector is confirmed.
- Face Sets are temporary: every successful split clears both results, and the next geometry-based split analyzes its selected input again.
- Every brush stroke uses the same Face Set ID and color without pressing Ctrl.
- Face Set boundary smoothing changes labels only and leaves mesh vertex positions unchanged.
- In manual paint mode, small painted islands can be ignored and nearby target regions can be joined along a valid surface path. Geometry-analysis regions can be merged and refined by the user.
- The selected region becomes a filled mask and is extracted as a new object.
- The archived original and the remaining geometry are preserved.
- With connector creation enabled, an editable connector preview is created at the split interface. Users can choose a cylinder or tapered square key and edit its position, rotation, scale, and fit without running Booleans.
- Optional magnet pockets create one matching recess in each half, beside the connector; magnet diameter, depth, and fit clearance are editable.
- **Apply Connector to Mesh** opens a confirmation dialog with Manifold, Exact, and Float choices; Manifold is the default. It applies the connector union, socket cut, and optional magnet-pocket cuts with the selected solver, then removes temporary helpers.
- With connector creation disabled before painting or analysis, the split creates no connector helpers and does not block the next split.
- Mask Slice fills the two matching interface boundaries instead of solidifying a surface patch through the other part.
- No Boolean is run during connector positioning, and no Boolean is applied to the archived original.
- Confirmed connector Booleans use the solver selected in the modal; Manifold is the default, and failed operations produce a clear error.
- Split operations can be undone with Blender Undo.

## Decisions still to make

- The final internal metadata schema and versioning strategy for division lineage.
- Whether mating-surface clearance is symmetric or applied to one half only.
- Whether later versions should place multiple connector pairs automatically along long interfaces.
- The paint cleanup percentage and maximum geodesic gap, to be tuned with real models.

## Technical risks to validate early

- Face Set-to-mask conversion works at face/vertex boundaries and may produce a different contour than expected; tune it on dense and thin meshes.
- A custom Sculpt Mode paint tool must map ray hits to the correct base-mesh face indices and remain usable on dense meshes.
- Mask Slice's hole filling triangulates the split boundary. Inspect cap quality and matching between both halves on complex, concave, and non-manifold meshes.
- Mask Slice uses temporary mesh copies while splitting; measure peak memory on dense models even though repeated splits do not leave extra full-mesh clones in the scene.
- Island filtering and gap filling can merge regions that the user intended to keep separate; use conservative thresholds and a reviewable preview.
- Geometry segmentation uses Blender's native face-normal grouping and is intentionally approximate. It can combine nearby forms or create extra regions on noisy surfaces; users can adjust the normal angle, merge regions, and refine boundaries with the native brush. The analyzer does not semantically identify named features.
- The analyzer selects the largest region as the default mother; asymmetrical models may need a different mother chosen in the panel.
- Manifold can repair some small topology defects, but more severe non-manifold inputs may still fail. Validate closed output, expected volume changes, and restore both original meshes if a Boolean result is invalid.
- Connectors may not fit on highly curved, narrow, or small surfaces; detect and explain such cases.
- Magnet pockets can weaken thin walls or collide with the connector on small interfaces; inspect the preview and adjust dimensions before applying.
- The workflow must distinguish the archived original, working remainder, and extracted parts across repeated splits.
- Hiding the original does not release its memory. Memory savings come from making one initial full-mesh copy and processing divisions without further full-mesh clones. Extracted parts still occupy memory while present in the scene.
- Face Set attributes and Sculpt operators can change between Blender versions; verify the declared minimum version before adding support for newer releases.

## Technical references

- [Blender 5.3 Python API — BVHTree](https://docs.blender.org/api/5.3/mathutils.bvhtree.html): supported constructors include `FromObject` and `FromPolygons`; `FromMesh` is not part of the API. The brush uses `FromObject` after hiding viewport modifiers, avoiding large temporary Python copies of the mesh data.
- [Blender 5.3 Python API — Sculpt operators](https://docs.blender.org/api/5.3/bpy.ops.sculpt.html)
- [Blender 5.3 Manual — Face Sets](https://docs.blender.org/manual/en/5.3/sculpt_paint/sculpting/editing/face_sets.html)
- [Blender 5.3 Manual — Draw Face Sets](https://docs.blender.org/manual/en/5.3/sculpt_paint/sculpting/brushes/draw_facesets.html)
- [Blender 5.3 Manual — Mesh Filter, including Relax Face Sets](https://docs.blender.org/manual/en/5.3/sculpt_paint/sculpting/tools/mesh_filter.html)
- [Blender source — Mesh Filter implementation](https://projects.blender.org/blender/blender/src/branch/main/source/blender/editors/sculpt_paint/mesh/sculpt_filter_mesh.cc): `RELAX_FACE_SETS` calculates vertex translations; this add-on uses label-only smoothing to keep the surface fixed.
- [Blender 5.3 Manual — Mask](https://docs.blender.org/manual/en/5.3/sculpt_paint/sculpting/editing/mask.html)
- [Blender source — Mask Slice implementation](https://projects.blender.org/blender/blender/src/branch/main/source/blender/editors/sculpt_paint/mesh/sculpt_mask_extract.cc): documents the complementary `new_object` slice and hole-fill path.
- [Blender 5.3 Python API — Window cursor controls](https://docs.blender.org/api/5.3/bpy.types.Window.html)
- [Blender 5.3 Python API — WindowManager dialogs](https://docs.blender.org/api/5.3/bpy.types.WindowManager.html)
- [Blender 5.3 Python API — Boolean Modifier solver](https://docs.blender.org/api/5.3/bpy.types.BooleanModifier.html)
- [Blender 5.3 Python API — GPU drawing](https://docs.blender.org/api/5.3/gpu.html)
- [Blender 5.3 Manual — Boolean Modifier](https://docs.blender.org/manual/en/5.3/modeling/modifiers/generate/booleans.html)

# SCS Blender Tools: new features and fixes

This page describes the features and fixes this repository adds on top of the official SCS Blender Tools.
For general usage of the tools see the
[SCS Blender Tools wiki](http://modding.scssoft.com/wiki/Documentation/Tools/SCS_Blender_Tools).

Target Blender version is 5.2 (older 5.x versions keep working where noted).

- [Tool Shelf tools](#tool-shelf-tools)
  - [Move Roots](#move-roots)
  - [Replace Texture Paths](#replace-texture-paths)
  - [Replace Export Paths](#replace-export-paths)
  - [Search & replace options](#search--replace-options)
- [SCS Outliner](#scs-outliner)
- [Locators](#locators)
  - [Selection colors and click selection](#selection-colors-and-click-selection)
  - [Camera locators FOV override](#camera-locators-fov-override)
- [Local view isolation of SCS Game Objects](#local-view-isolation-of-scs-game-objects)
- [Export](#export)
  - [Selection export exports whole SCS Game Object](#selection-export-exports-whole-scs-game-object)
  - [Objects are switched to object mode](#objects-are-switched-to-object-mode)
  - [Instances and hidden objects](#instances-and-hidden-objects)
  - [Export fixes](#export-fixes)
- [Materials and looks fixes](#materials-and-looks-fixes)
- [Performance](#performance)


## Tool Shelf tools

All of these are buttons in **3D View > Sidebar (N) > SCS Tools > Tool Shelf**, below **Relocate Roots**.

### Move Roots

Moves SCS Root objects in the scene, together with all their children, by an X, Y, Z offset.

- The offset is entered in a dialog and is applied in world space, so it also works on roots parented to other objects.
- **Selected Only** moves only the selected SCS Root objects. Otherwise every SCS Root in the scene moves.
- A nested SCS Root moves once, together with its parent root. SCS Roots linked from a library are skipped with a warning.
- The move is a single undo step, and the offset can be changed afterwards in the **Adjust Last Operation** panel.

### Replace Texture Paths

Searches texture paths of SCS materials and replaces text in them. **Replace In** picks which materials are processed:

- **Scene** (default: the current scene): SCS materials used by any object in the scene, plus the looks of all SCS Roots in it.
- **Collection**: SCS Roots in the collection, including its child collections, with their objects' materials and their looks.
- **SCS Root**: only that SCS Root, with its objects' materials and its looks. Nested SCS Roots are not included.

Materials that no object in the chosen scope uses are never changed. A material shared with objects outside the scope
still changes for them too, because it is the same material. Looks of SCS Roots outside the scope are left as they are.

- Every texture of every SCS shader is processed: base, mask, normal maps, detail textures and so on. This covers both
  the texture path and the path of an imported TOBJ.
- Paths are replaced in the **material and in all looks** of the SCS Roots in scope, not only in the active look.
- Each changed texture is updated exactly as if it had been picked with the texture path button: the TOBJ settings are
  reloaded, the image is reloaded in the shader nodes and the viewport is refreshed. New paths are normalized to project
  relative (`//...`) form.
- **Locked** textures (texture paths locked by the shader preset) are left untouched, and the final report counts them.
- If nothing matched, the operator reports a warning and changes nothing.

### Replace Export Paths

Searches the custom export paths of SCS Root objects and replaces text in them. **Replace In** picks which roots are processed:

- **Scene** (default: the current scene): all SCS Roots in the scene.
- **Collection**: SCS Roots in the collection, including its child collections.

- Both paths of every SCS Root are processed: the **custom export path** and the **animations custom export path**.
- Each changed path is printed to the console. The report says how many paths in how many roots were changed.
- SCS Roots linked from a library can't be changed and are skipped with a warning.
- **Export when finished**: after replacing, every SCS Root whose path changed is exported, one root at a time.
  - Each root is exported together with all its objects. A nested SCS Root is exported on its own, and only if its own path changed.
  - A missing export folder is created first, as long as it is inside the SCS Project Base Path.
  - Roots with export switched off are not exported.
  - If one root fails to export, the others still get exported, and the final report names the roots that failed.
  - Unchanged roots, and roots outside the chosen scope, are never exported, regardless of the export scope setting.
- To avoid exporting again by accident, this tool has no **Adjust Last Operation** panel. The replace itself can be undone
  with Ctrl + Z, but files that were already exported stay on disk.

### Search & replace options

Both Replace tools open the same dialog:

| Option | Description |
| --- | --- |
| **Replace In** | Where replacing is done, picked from a hierarchy like the outliner's. Scenes come first, with the current scene on top as the default. Under each scene are the collections that contain SCS Roots, nested as in the outliner; collections without any SCS Root are left out. Replace Texture Paths also lists the SCS Roots themselves under their collections. |
| **Search for** | Text to search for, or a regular expression. |
| **Replace** | Text that replaces every match. |
| **Case Sensitive** | Match upper and lower case exactly. Off by default, so `Vehicle` also matches `vehicle`. |
| **Regular Expressions** | Treat **Search for** as a regular expression (Python syntax). Off by default, so the text is matched literally. |

With **Regular Expressions** on, **Replace** can put back parts of the match:

| Syntax | Inserts |
| --- | --- |
| `$1`, `${1}` or `\1` | text matched by group 1 (also 2, 3, ...) |
| `${name}` or `\g<name>` | text matched by named group `(?P<name>...)` |
| `$0` or `\g<0>` | the whole match |
| `$$` | a literal `$` |

Example: search `vehicle/truck/(\w+)/` and replace with `vehicle/truck_new/$1/` changes
`//vehicle/truck/cabin/base.tobj` into `//vehicle/truck_new/cabin/base.tobj`.

The dialog checks your input while you type:

- **Empty search**: the **Replace** button is disabled.
- **Invalid regular expression**, or a replace that refers to a group which doesn't exist: the search field turns red,
  the error is shown in the dialog and the **Replace** button is disabled. Pressing Enter doesn't replace anything either;
  it only reports the error.
- **Unused groups**: if the search has capture groups but **Replace** doesn't use any of them, the dialog shows a note.
  Pressing **Replace** then asks *"Replace anyway?"* before anything changes, because this usually means the groups were
  forgotten in the replace text. `$0`, `$$1` and `\\1` don't count as using a group, and non-capturing groups `(?:...)`
  aren't counted.


## SCS Outliner

An optional outliner panel in **3D View > Sidebar (N) > SCS Tools**, right below the Tool Shelf. It is **off by default**:
turn it on with **Show SCS Outliner** in **Display Settings** (the setting is saved in the config). While it's off, it is
not drawn and doesn't register any handlers.

- Lists SCS Root objects with their objects as a tree. Each item uses its SCS type icon: SCS Root, model, shadow caster,
  glass and static collision meshes, model locators, collision locators by collider shape, and prefab locators by prefab type.
- Selection works as in the Blender Outliner:
  - click selects only the item;
  - Ctrl + click extends or toggles the selection;
  - Shift + click selects a range from the active object.

  Selected items are shown pressed and the active object is highlighted.
- Items can be expanded and collapsed, with Shift for the whole sub-tree. Expand states are kept for the current session
  only, so they don't create undo steps or change the file.
- Visibility (eye) toggle per item, with Shift to include its children, plus a selectability toggle. Hidden objects are greyed out.
- The name filter shows matching items together with their parents.
- The tree is cached and rebuilt only on scene changes that can affect it, not on transformations.


## Locators

### Selection colors and click selection

- Custom drawn prefab, model and collision locators use the theme **Object Selected** and **Active Object** colors when
  selected, like other objects in the 3D view.
- Locators can be selected by clicking their drawn shapes (arrows, axes, boxes...), not only the small empty at their origin.
- Click selection behaves as Blender's own:
  - click selects the locator and deselects others;
  - Shift + click extends the selection or deselects the active locator;
  - click-drag still does box selection.
- Objects in front of the locator are respected: a selectable object under the mouse in front of the locator gets selected
  instead. Unselectable objects don't block the locator, and X-ray selects through everything.
- Collision locators are picked like meshes: with faces displayed their whole surface is selectable, with wires only their lines.
- Works in Object Mode with empties visible and selectable in the viewport. Local view and gizmo visibility are respected.

### Camera locators FOV override

Model locators whose name starts with `cam_` have a **FOV Override** option in **Locator Settings**: an on/off toggle with
a FOV value (whole or decimal numbers, default 22).

- It is exported as a hookup payload in the PIM and PIM EF locator section: `Hookup: "#fov_override:22"`.
- It can be combined with a hookup and other payloads, for example `Hookup: "some.hook.id#fov_override:22"`.
- Import reads the payload back into the locator properties. Before this change, such a payload broke the import.


## Local view isolation of SCS Game Objects

Isolating an SCS Root object with Blender local view (numpad `/` or **View > Local View**) isolates the whole SCS Game Object:

- All objects within the root are added to local view, so collection, geometry nodes and other instances of those objects
  are shown too.
- Local view is framed on the whole isolated game object.
- Objects outside the root, including instance source objects, stay out of local view. Isolating a single object within
  the root keeps Blender's default behavior.


## Export

### Selection export exports whole SCS Game Object

With export scope **Selection**, any selected object (mesh, locator...) exports the **whole SCS Game Object** of the closest
SCS Root above it, not only the selected objects. Selecting objects in several roots exports each of those roots
completely. Roots without any selected object are not exported.

### Objects are switched to object mode

Objects for export that are in edit, vertex/weight/texture paint or any other mode are switched to object mode before
export, so their unsaved edits are exported. Before this change, they were skipped with an *"Invalid object mode"* warning.

- Works with multi-object editing and for objects left in another mode while not being active.
- Each switched object is reported in the export log.
- Applies to every export: SCS export with or without selection preview, and **File > Export**.

### Instances and hidden objects

Instances under an SCS Root are exported as part of the game object:

- **Kinds:** collection instances (including nested ones), vertex/face instancing, particles and geometry nodes instances.
- **How:** each instance is turned into a temporary object for export with its complete transformation, including shear
  from nested or non-uniformly scaled instancing, and is removed when the export is done.
- **What gets exported:**
  - Instanced meshes are exported from the evaluated instance geometry, with the materials the instance shows.
  - Instanced model and collision locators are exported as locators.
  - Instanced prefab locators are skipped with a warning, because they are bound to their connections.
- **Part:** instances belong to the part of their instancer.
- **Modifiers:** the export modifier settings also apply to instance source objects.

Everything under an exported SCS Root is exported regardless of visibility. That includes:

- hidden objects and collections inside instanced collections;
- hidden geometry nodes and particle source objects;
- instancers that hide themselves.

Hide states are remembered and restored after export, also when the export fails.

### Export fixes

- Fixed export being cancelled in Blender 5.2 when the scene contains an object with a geometry nodes modifier
  (*"bpy_struct.keys(): this type doesn't support IDProperties"*).
- Fixed export being cancelled with `KeyError 'DetailNMapUVs'` on materials with a leftover detail normal map UV mapping
  while the detail normal map flavor isn't set.
- Fixed face flip detection: it now uses the full transformation relative to the SCS Root, including parent inverse matrices.
- Fixed exported normals on non-uniformly scaled or sheared objects: they now stay perpendicular to the surface.
- Fixed the outliner losing its scroll position after export. It now scrolls back to the active object.
- Float values in non-hex PIX output (for example PIT material attribute values) are rounded to 2 decimals.


## Materials and looks fixes

- Fixed material values being reverted after export on SCS Game Objects with several looks. The PIT, PIT EF and AutoMat
  exporters save the exact state of the materials before applying looks for export, and restore it afterwards.
- Fixed EF export leaving materials in the state of the last look.
- Material changes are written into the looks of the material that was actually changed, not only the active material of
  the active object. This matters when editing several objects at once, or editing a material while another object is active.
- Fixed changing the active look of an SCS Root applying the looks of the active object's SCS Root instead.
- Setting the UV of the detail normal map does nothing while its flavor isn't set, the same as setting its texture
  ("dif.spec.weight.add.env" and "dif.spec.fade.mult.dif.spec" shaders).
- Switching looks re-applies UV mapping and aux values only when they changed, which avoids needless shader updates.
- Added the "sky_bottom" flavor module.


## Performance

- **Viewport drawing:**
  - GPU batches are cached and rebuilt only when their data changes;
  - the clip planes buffer is reused while the planes stay the same;
  - empty buffers are skipped.
- **Preview model visibility:** only locators with a cached preview model are checked, not every object in the view layer.
- **Lighting:** the light direction and camera nodes are updated only when their values change.

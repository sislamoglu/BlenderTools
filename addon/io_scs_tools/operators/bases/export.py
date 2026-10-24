# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Copyright (C) 2019-2021: SCS Software

import bpy
from mathutils import Matrix
from ... import exp as _export
from ...utils import object as _object_utils
from ...utils import get_scs_globals as _get_scs_globals
from ...utils.printout import lprint


def _outliners_show_active():
    """Scrolls all outliners in all windows to the active object.

    NOTE: Intended to be used as timer callback, thus returns None to be unregistered after first call.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'OUTLINER':
                continue

            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if region is None:
                continue

            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.outliner.show_active()
            except RuntimeError as e:
                lprint("D Outliner show active failed: %s", (e,))

    return None


class SCSExportHelper:
    """Class for implementation of SCS export routines, to take care of objects/collections visibilites and
    implemenet convinient methods for usage as parent class in export operators.
    """

    export_scene_name = None
    """Stores name of the export scene (used to skip custom drawing elements update on export scene)."""

    def __init__(self, *args, **kwargs):
        self.cached_objects = None
        """:type list[bpy.types.Object]: Used in selection mode to cache selected objects, to avoid multiple collecting."""
        self.objects_states = dict()
        """:type dict[bpy.types.Object, boo]]: Hide & selection states for objects gathered on selection export. Used to restore 
        their states after export."""
        self.collection_visibilites = dict()
        """:type dict[bpy.types.Object, bool]: Original collection visibilities used to restore their state after export."""
        self.scene = None
        """:type bpy.types.Scene: Scene to which we will temporarly link objects that needs to be exported."""
        self.active_scene = None
        """:type bpy.types.Scene: Scene which was active before export and should be recovered as active once export is done."""
        self.active_view_layer = None
        """:type bpy.types.ViewLayer: View layer which was active before export and should be recovered as active once export is done."""
        self.disabled_modifiers = dict()
        """:type dict[bpy.types.Object, tuple]"""
        self.realized_instances = []
        """:type list[bpy.types.Object]: Temporary objects created from instances of export objects, removed once export is done."""

    def get_objects_for_export(self):
        """Get objects for export, list filtered and extended depending on export scope.

        :return: list of objects to export calculated from selection
        :rtype: list[bpy.types.Object]
        """

        # if cached, just return
        if self.cached_objects:
            return self.cached_objects

        objs_to_export = []

        export_scope = _get_scs_globals().export_scope
        if export_scope == "selection":
            for root in _object_utils.gather_scs_roots(bpy.context.selected_objects):
                objs_to_export.append(root)

                children = _object_utils.get_children(root)
                children_unselected = []
                children_selected = []

                for child_obj in children:
                    if child_obj.select_get():
                        children_selected.append(child_obj)
                    elif child_obj.users_scene:  # unlinked objects shouldn't be exported
                        children_unselected.append(child_obj)

                # if any children was selected make sure, to export only them
                if len(children_selected) > 0:
                    objs_to_export.extend(children_selected)
                else:
                    objs_to_export.extend(children_unselected)
        elif export_scope == "scene":
            objs_to_export = tuple(bpy.context.scene.objects)
        elif export_scope == "scenes":
            scenes_objs = set()
            for scene in bpy.data.scenes:
                scenes_objs.update(scene.objects)
            objs_to_export = tuple(scenes_objs)

        # cache filtered list, to be able to retrive it quickly on second call
        self.cached_objects = objs_to_export

        return self.cached_objects

    def init(self):
        """Init routine to create export scene, link all exprt objects to it and unhide objects so they can be seen in preview and exported properly.
        The problem is that depsgraph doesn't apply modifiers if object is hidden (directly or via collections).

        NOTE: Should be called before get_objects_for_export.
        """

        # we have to get object to export now, because creating new scene
        # will invalidate context and selected objects within context are lost.
        objs_to_export = self.get_objects_for_export()

        # create export scene
        self.scene = bpy.data.scenes.new("SCS Export")
        self.active_scene = bpy.context.window.scene
        self.active_view_layer = bpy.context.window.view_layer
        bpy.context.window.scene = self.scene

        # copy default_export_filepath from active scene
        self.scene.scs_props.default_export_filepath = self.active_scene.scs_props.default_export_filepath

        # store name of current export scene
        SCSExportHelper.export_scene_name = self.scene.name

        # link objects to export scene and unhide all of them
        for obj in objs_to_export:
            self.scene.collection.objects.link(obj)
            self.objects_states[obj] = obj.hide_viewport
            obj.hide_viewport = False

        # unhide also everything instanced by objects for export, so hidden instance sources get exported as well
        instanced_collections, instanced_objs = _object_utils.get_instance_sources(objs_to_export)
        for collection in instanced_collections:
            self.collection_visibilites[collection] = collection.hide_viewport
            collection.hide_viewport = False

        for obj in instanced_objs:
            if obj not in self.objects_states:
                self.objects_states[obj] = obj.hide_viewport
                obj.hide_viewport = False

        # disable modifiers before depsgraph gets updated
        # (also on instanced objects, so their instances are evaluated with the same modifiers settings)
        self.disabled_modifiers = _object_utils.disable_modifiers(set(objs_to_export) | instanced_objs)

        # finally update depshraph so that all linked objects will get nneded update
        # (properly applied modifiers, visibility states etc.)
        bpy.context.window.view_layer.depsgraph.update()

        scs_globals = _get_scs_globals()
        if scs_globals.export_scope == "selection" and scs_globals.preview_export_selection:
            scs_globals.preview_export_selection_active = True

    def finish(self):
        """Finish routine to restore objects & scene state after export.

        NOTE: Should be called after export has completed.
        """
        _get_scs_globals().preview_export_selection_active = False

        # recover viewport states
        for obj, state in self.objects_states.items():
            obj.hide_viewport = state

        for collection, state in self.collection_visibilites.items():
            collection.hide_viewport = state

        # recover disabled modifiers
        _object_utils.restore_modifiers(self.disabled_modifiers)

        # recover old active scene and remove temporary one
        bpy.context.window.scene = self.active_scene
        bpy.context.window.view_layer = self.active_view_layer
        bpy.data.scenes.remove(self.scene)
        self.scene = None

        # unset name of current export scene since we are done
        SCSExportHelper.export_scene_name = None

        # switching to export scene and back resets outliner scroll, so scroll back to active object,
        # deferred via timer so outliners get to rebuild their trees for recovered scene first
        bpy.app.timers.register(_outliners_show_active, first_interval=0.1)

    def realize_instances(self, objs_to_export):
        """Creates temporary objects for all the instances (collection, vertices/faces, particles or geometry nodes instances)
        generated by export objects inside SCS Game Objects, so they get exported as part of the game object.

        Instance mesh is taken from evaluated instance geometry and instance world matrix is put into parent inverse matrix
        of temporary object parented to SCS Root, so that complete transformation (including possible shear
        from nested instancing) is preserved exactly.

        NOTE: Should be called after init and should be followed by remove_realized_instances once export is done.

        :param objs_to_export: objects for export
        :type objs_to_export: list[bpy.types.Object]
        :return: objects for export, with realized instances added
        :rtype: list[bpy.types.Object]
        """

        depsgraph = bpy.context.window.view_layer.depsgraph
        export_objs = set(objs_to_export)

        realized = []  # list of tuples: (temp object, scs root, instance matrix)
        skipped_prefab_locators = set()

        for inst in depsgraph.object_instances:

            if not inst.is_instance:
                continue

            instancer = inst.parent.original
            if instancer not in export_objs:
                continue

            scs_root = _object_utils.get_scs_root(instancer)
            if scs_root is None:
                continue

            src_obj = inst.object

            if src_obj.type == 'EMPTY':

                orig_obj = src_obj.original
                if orig_obj.scs_props.empty_object_type != 'Locator':
                    continue

                if orig_obj.scs_props.locator_type == 'Prefab':
                    # prefab locators are bound to connections by their names, thus can't be copied
                    skipped_prefab_locators.add(orig_obj.name)
                    continue

                if orig_obj.scs_props.locator_type not in ('Model', 'Collision'):
                    continue

                tmp_obj = orig_obj.copy()
                tmp_obj.animation_data_clear()
                tmp_obj.constraints.clear()
                tmp_obj.instance_type = 'NONE'

            elif src_obj.type in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META'):

                # don't export preview models of instanced locators
                if src_obj.type == 'MESH' and src_obj.data.scs_props.locator_preview_model_path != "":
                    continue

                # NOTE: all data layers are not preserved on purpose, as that re-evaluates instance object
                # from its original data and geometry nodes instances would end up with wrong geometry
                try:
                    mesh = bpy.data.meshes.new_from_object(src_obj, depsgraph=depsgraph)
                except RuntimeError:
                    continue

                if len(mesh.polygons) == 0:
                    bpy.data.meshes.remove(mesh)
                    continue

                # use materials as seen by instance object (taking care of object linked materials)
                materials = [slot.material.original if slot.material else None for slot in src_obj.material_slots]
                mesh.materials.clear()
                for material in materials:
                    mesh.materials.append(material)

                mesh.scs_props.locator_preview_model_path = ""

                tmp_obj = bpy.data.objects.new(instancer.name + ">" + src_obj.name, mesh)

            else:
                continue

            # register right away, so temporary object gets removed even if something fails later on
            self.realized_instances.append(tmp_obj)

            # instances are part of the instancer, so they belong to its part
            if instancer is scs_root:
                if len(scs_root.scs_object_part_inventory) > 0:
                    tmp_obj.scs_props.scs_part = scs_root.scs_object_part_inventory[0].name
            else:
                tmp_obj.scs_props.scs_part = instancer.scs_props.scs_part

            realized.append((tmp_obj, scs_root, inst.matrix_world.copy()))

        if skipped_prefab_locators:
            lprint("W Instanced prefab locators can't be exported, as they are bound to their connections, skipping:\n\t   %r",
                   (sorted(skipped_prefab_locators),))

        # link & parent temporary objects only after iteration is done, as depsgraph instances are valid only during iteration
        for tmp_obj, scs_root, matrix in realized:
            self.scene.collection.objects.link(tmp_obj)

            tmp_obj.hide_viewport = False
            tmp_obj.parent = scs_root
            tmp_obj.parent_type = 'OBJECT'
            tmp_obj.matrix_basis = Matrix.Identity(4)
            tmp_obj.delta_location = (0.0, 0.0, 0.0)
            tmp_obj.delta_rotation_euler = (0.0, 0.0, 0.0)
            tmp_obj.delta_rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            tmp_obj.delta_scale = (1.0, 1.0, 1.0)
            tmp_obj.matrix_parent_inverse = scs_root.matrix_world.inverted() @ matrix

        if self.realized_instances:
            # fix scene objects count to avoid callback of new objects
            self.scene.scs_cached_num_objects = len(self.scene.objects)

            depsgraph.update()

            lprint("I Realized %i instance(s) for export.", (len(self.realized_instances),))

        return list(objs_to_export) + self.realized_instances

    def remove_realized_instances(self):
        """Removes temporary objects and their meshes created by realize_instances."""

        for tmp_obj in self.realized_instances:
            mesh = tmp_obj.data if tmp_obj.type == 'MESH' else None

            bpy.data.objects.remove(tmp_obj, do_unlink=True)

            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

        self.realized_instances.clear()

    def execute_export(self, context, without_preview, menu_filepath=None):
        """Executes export.

        :param context: operator context
        :type context: bpy_struct
        :param without_preview: is export run without preview?
        :type without_preview: bool
        :param menu_filepath: filepath used from menu export, if not provided export is done to none menu set path
        :type menu_filepath: str
        :return: success of batch export
        :rtype: {'FINISHED'} | {'CANCELLED'}
        """

        # check extension for EF format and properly assign it to name suffix
        ef_name_suffix = ""
        if _get_scs_globals().export_output_type == "EF":
            ef_name_suffix = ".ef"

        try:
            # show all collections, if normal export, so all modifiers will be applied correctly
            if without_preview:
                self.init()

            # export instances as part of the game objects they are instanced in
            init_obj_list = self.realize_instances(self.get_objects_for_export())

            result = _export.batch_export(self, init_obj_list, name_suffix=ef_name_suffix, menu_filepath=menu_filepath)
        except Exception as e:

            result = {"CANCELLED"}
            context.window.cursor_modal_restore()

            import traceback

            trace_str = traceback.format_exc().replace("\n", "\n\t   ")
            lprint("E Unexpected %r accured during batch export:\n\t   %s",
                   (type(e).__name__, trace_str),
                   report_errors=1,
                   report_warnings=1)

        # always remove temporary objects and restore original hide states of objects & collections,
        # even if export failed (with preview, finish is called by the modal operator once it ends)
        self.remove_realized_instances()

        if without_preview and self.scene:
            self.finish()

        return result

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

# Copyright (C) 2026: SCS Software

import bpy
from io_scs_tools.internals.open_gl import primitive as _primitive
from io_scs_tools.utils import get_scs_globals as _get_scs_globals

_KEYMAP_NAME = "SCS Locators Selection Gizmo"


class SCS_TOOLS_GT_LocatorShape(bpy.types.Gizmo):
    """Invisible gizmo with shape of custom drawn locator, making the locator selectable by click on its shape.
    Shape consists of drawn lines and drawn faces (e.g. collision locators faces), so locator is picked same way as mesh would be.
    Gizmo itself is never drawn, as locator is already drawn by our custom drawing.
    """
    bl_idname = "SCS_TOOLS_GT_locator_shape"

    __slots__ = (
        "shapes",
        "locator_shape",
    )

    def setup(self):
        self.shapes = ()
        self.locator_shape = None

    def set_locator_shape(self, locator_shape):
        """Sets shape of this gizmo, gizmo shapes are recreated only if locator shape changed.

        :param locator_shape: lines vertices positions (each two make a line) and triangles vertices positions (each three make a triangle)
        :type locator_shape: (list[tuple], list[tuple])
        """
        if locator_shape == self.locator_shape:
            return

        self.locator_shape = locator_shape

        lines, tris = locator_shape
        shapes = []
        if lines:
            shapes.append(self.new_custom_shape('LINES', lines))
        if tris:
            shapes.append(self.new_custom_shape('TRIS', tris))
        self.shapes = tuple(shapes)

    def draw(self, context):
        pass

    def draw_select(self, context, select_id):
        for shape in self.shapes:
            self.draw_custom_shape(shape, select_id=select_id)


class SCS_TOOLS_GGT_LocatorsSelection(bpy.types.GizmoGroup):
    """Gizmo group creating selection gizmo for each custom drawn locator.

    Gizmos are activated on click only, so click-drag still behaves as by default (e.g. box selection).
    Objects in front of the locator are respected by selection operator, which uses Blender click selection in such case.
    """
    bl_idname = "SCS_TOOLS_GGT_locators_selection"
    bl_label = "SCS Locators Selection"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'DEPTH_3D'}

    @classmethod
    def setup_keymap(cls, keyconfig):
        keymap = keyconfig.keymaps.new(name=_KEYMAP_NAME, space_type='EMPTY', region_type='WINDOW')
        if not keymap.keymap_items:
            keymap.keymap_items.new("gizmogroup.gizmo_tweak", 'LEFTMOUSE', 'CLICK', any=True)
        return keymap

    @classmethod
    def poll(cls, context):
        if context.mode != 'OBJECT':
            return False

        space = context.space_data
        if not space.show_object_viewport_empty or not space.show_object_select_empty:
            return False

        return _get_scs_globals().display_locators

    def setup(self, context):
        self.shapes_version = None
        self.locator_gizmos = {}
        """:type dict[str, SCS_TOOLS_GT_LocatorShape]: Gizmos by locator names."""

    def _sync_gizmos(self):
        """Creates, updates and removes gizmos to match currently captured locators shapes."""

        shapes_version, locators_shapes = _primitive.get_locators_shapes()
        if shapes_version == self.shapes_version:
            return

        self.shapes_version = shapes_version

        for locator_name in list(self.locator_gizmos):
            if locator_name not in locators_shapes:
                self.gizmos.remove(self.locator_gizmos.pop(locator_name))

        for locator_name, locator_shape in locators_shapes.items():
            gz = self.locator_gizmos.get(locator_name)
            if gz is None:
                gz = self.gizmos.new(SCS_TOOLS_GT_LocatorShape.bl_idname)
                gz.use_draw_scale = False
                gz.use_draw_modal = False
                gz.line_width = 3.0

                props = gz.target_set_operator("object.scs_tools_select_locator")
                props.locator_name = locator_name

                self.locator_gizmos[locator_name] = gz

            gz.set_locator_shape(locator_shape)

    def refresh(self, context):
        self._sync_gizmos()

    def draw_prepare(self, context):
        self._sync_gizmos()

        # hide gizmos of locators which aren't selectable or not in local view of current viewport
        space = context.space_data
        objects = bpy.data.objects
        for locator_name, gz in self.locator_gizmos.items():
            obj = objects.get(locator_name)
            hide = obj is None or obj.hide_select or (space.local_view is not None and not obj.local_view_get(space))

            # set only on change, as setting hide property refreshes gizmo map
            if gz.hide != hide:
                gz.hide = hide


classes = (
    SCS_TOOLS_GT_LocatorShape,
    SCS_TOOLS_GGT_LocatorsSelection,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

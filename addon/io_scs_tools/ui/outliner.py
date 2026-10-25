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
from bpy.types import UIList
from ..internals import outliner as _outliner

_UI_UNIT = 20
"""Blender UI unit size in pixels (without UI scale)."""
_TOGGLES_UNITS = 2.5
"""Width of toggles on the right side of SCS Outliner item in UI units."""
_LIST_MARGINS = 60
"""Estimated horizontal margins of the list inside sidebar panel in pixels (without UI scale), including list scrollbar."""


class SCS_TOOLS_UL_Outliner(UIList):
    """SCS Outliner list: SCS Game Objects shown as tree of their objects with SCS types icons.
    It lists all blend data objects, but filters and orders them into the tree.
    """

    def filter_items(self, context, data, propname):
        # NOTE: filtering is cached, so it costs almost nothing until scene changes
        return _outliner.get_list_filter(getattr(data, propname), context.scene, self.filter_name, self.bitflag_filter_item)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = item
        tree_item = _outliner.get_list_item(obj.name)
        if tree_item is None:
            return

        # split row so that toggles keep fixed width on the right side and names get all the rest
        toggles_width = _TOGGLES_UNITS * _UI_UNIT * context.preferences.system.ui_scale
        list_width = max(context.region.width - _LIST_MARGINS * context.preferences.system.ui_scale, toggles_width * 2)
        split = layout.split(factor=1.0 - toggles_width / list_width)

        # left side: indentation, expand toggle and name with type icon
        tree_row = split.row(align=True)
        tree_row.alignment = 'LEFT'

        for _ in range(tree_item.depth):
            tree_row.label(text="", icon='BLANK1')

        if tree_item.has_children and not self.filter_name:
            expand_icon = 'DISCLOSURE_TRI_DOWN' if _outliner.is_expanded(obj) else 'DISCLOSURE_TRI_RIGHT'
            props = tree_row.operator("object.scs_tools_outliner_toggle_expand", text="", icon=expand_icon, emboss=False)
            props.object_name = obj.name
        else:
            tree_row.label(text="", icon='BLANK1')

        in_view_layer = obj.name in context.view_layer.objects
        is_selected = in_view_layer and obj.select_get()

        name_row = tree_row.row(align=True)
        name_row.alignment = 'LEFT'
        name_row.active = in_view_layer and obj.visible_get()
        props = name_row.operator("object.scs_tools_outliner_select", text=obj.name, emboss=is_selected, depress=is_selected,
                                  **_outliner.get_icon(obj))
        props.object_name = obj.name

        # right side: visibility & selectability toggles
        toggles_row = split.row(align=True)
        toggles_row.alignment = 'RIGHT'

        if in_view_layer:
            props = toggles_row.operator("object.scs_tools_outliner_toggle_hide", text="", emboss=False,
                                         icon='HIDE_ON' if obj.hide_get() else 'HIDE_OFF')
            props.object_name = obj.name
        else:
            toggles_row.label(text="", icon='HIDE_ON')

        toggles_row.prop(obj, "hide_select", text="", emboss=False)


def draw_outliner(layout, context):
    """Draws SCS Outliner list.

    :param layout: Blender UI Layout to draw to
    :type layout: bpy.types.UILayout
    :param context: Blender context
    :type context: bpy.types.Context
    """
    workspace = context.workspace

    if not workspace or not context.scene:
        return

    # make sure tree cache gets invalidated on scene changes from now on
    _outliner.enable()

    if not _outliner.get_tree(context.scene):
        layout.label(text="No SCS Root Objects in scene.", icon='INFO')
        return

    layout.template_list(
        SCS_TOOLS_UL_Outliner.__name__,
        list_id="",
        dataptr=bpy.data,
        propname="objects",
        active_dataptr=workspace.scs_props,
        active_propname="outliner_active_index",
        rows=12,
    )


classes = (
    SCS_TOOLS_UL_Outliner,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _outliner.disable()

    for cls in classes:
        bpy.utils.unregister_class(cls)

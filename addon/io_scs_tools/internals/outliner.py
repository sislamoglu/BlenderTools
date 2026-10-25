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

"""SCS Outliner internals: tree of SCS Game Objects, items expand states and icons.

Tree is cached and rebuilt only after scene changes which can affect it (not on pure transformation changes),
so SCS Outliner doesn't slow down Blender. Handlers for cache invalidation are added only once SCS Outliner is used
and removed again when it's disabled.
"""

import bpy
from bpy.app.handlers import persistent
from fnmatch import fnmatchcase
from io_scs_tools.consts import Icons as _ICONS_consts
from io_scs_tools.internals.icons import get_icon as _get_icon
from io_scs_tools.utils import material as _material_utils

_ICON_TYPES = _ICONS_consts.Types

_PREFAB_TYPE_ICONS = {
    'Control Node': _ICON_TYPES.loc_prefab_node,
    'Sign': _ICON_TYPES.loc_prefab_sign,
    'Spawn Point': _ICON_TYPES.loc_prefab_spawn,
    'Traffic Semaphore': _ICON_TYPES.loc_prefab_semaphore,
    'Navigation Point': _ICON_TYPES.loc_prefab_navigation,
    'Map Point': _ICON_TYPES.loc_prefab_map,
    'Trigger Point': _ICON_TYPES.loc_prefab_trigger,
}

_COLLIDER_TYPE_ICONS = {
    'Box': _ICON_TYPES.loc_collider_box,
    'Sphere': _ICON_TYPES.loc_collider_sphere,
    'Capsule': _ICON_TYPES.loc_collider_capsule,
    'Cylinder': _ICON_TYPES.loc_collider_cylinder,
    'Convex': _ICON_TYPES.loc_collider_convex,
}

_BLENDER_TYPE_ICONS = {
    'EMPTY': 'OUTLINER_OB_EMPTY',
    'ARMATURE': 'OUTLINER_OB_ARMATURE',
    'MESH': 'OUTLINER_OB_MESH',
    'CURVE': 'OUTLINER_OB_CURVE',
    'LIGHT': 'OUTLINER_OB_LIGHT',
    'CAMERA': 'OUTLINER_OB_CAMERA',
}

_collapsed = set()
"""Names of collapsed items. Kept only for current session, so expanding/collapsing doesn't make undo steps or change the file."""

_cache = {
    "version": 0,  # incremented on each invalidation
    "trees": {},  # cached trees by (version, scene name, name filter)
    "list_filter": None,  # cached list filtering as (key, flags, new order, items by names, displayed order)
}
_handlers_enabled = False


class TreeItem:
    """Item of SCS Outliner tree.

    NOTE: object is referenced only by name, as tree is cached and object references can become invalid (e.g. by undo).
    """

    __slots__ = ("name", "depth", "has_children")

    def __init__(self, name, depth, has_children):
        self.name = name
        """:type str: Name of the object of this item."""
        self.depth = depth
        """:type int: Depth of this item in the tree, SCS Root items have depth 0."""
        self.has_children = has_children
        """:type bool: Does this item have any children in the tree?"""


def invalidate():
    """Invalidates cached tree, so it gets rebuilt on next SCS Outliner redraw."""
    _cache["version"] += 1
    _cache["trees"].clear()
    _cache["list_filter"] = None


@persistent
def _post_depsgraph(scene, depsgraph):
    """Invalidates tree on updates which can affect it, pure transformations changes are ignored."""
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object) and update.is_updated_transform and not update.is_updated_geometry:
            continue

        if isinstance(update.id, (bpy.types.Object, bpy.types.Scene, bpy.types.Collection, bpy.types.Mesh)):
            invalidate()
            return


@persistent
def _post_undo_redo_load(*_):
    invalidate()


_HANDLERS = (
    (bpy.app.handlers.depsgraph_update_post, _post_depsgraph),
    (bpy.app.handlers.undo_post, _post_undo_redo_load),
    (bpy.app.handlers.redo_post, _post_undo_redo_load),
    (bpy.app.handlers.load_post, _post_undo_redo_load),
)


def enable():
    """Enables tree cache invalidation handlers, should be called whenever SCS Outliner is drawn."""
    global _handlers_enabled

    if _handlers_enabled:
        return

    for handlers, handler in _HANDLERS:
        if handler not in handlers:
            handlers.append(handler)

    _handlers_enabled = True
    invalidate()


def disable():
    """Disables tree cache invalidation handlers and frees the caches, should be called when SCS Outliner isn't used anymore."""
    global _handlers_enabled

    for handlers, handler in _HANDLERS:
        if handler in handlers:
            handlers.remove(handler)

    _handlers_enabled = False
    invalidate()


def is_scs_root(obj):
    """Tells if given object is SCS Root object."""
    return obj.type == 'EMPTY' and obj.scs_props.empty_object_type == 'SCS_Root'


def _is_preview_model(obj):
    """Tells if given object is preview model of model locator (these are not shown in SCS Outliner)."""
    return obj.type == 'MESH' and obj.data is not None and obj.data.scs_props.locator_preview_model_path != ""


def is_expanded(obj):
    """Tells if given item is expanded."""
    return obj.name not in _collapsed


def set_expanded(obj, expanded):
    """Sets expand state of given item."""
    if expanded:
        _collapsed.discard(obj.name)
    else:
        _collapsed.add(obj.name)

    invalidate()


def get_tree(scene, name_filter=""):
    """Gets SCS Outliner tree items for given scene, in display order. Tree is cached until next invalidation.

    :param scene: scene of which SCS Game Objects should be listed
    :type scene: bpy.types.Scene
    :param name_filter: case insensitive filter of item names, can use wildcards
    :type name_filter: str
    :return: tree items in display order
    :rtype: list[TreeItem]
    """
    key = (_cache["version"], scene.name, name_filter)
    tree = _cache["trees"].get(key)
    if tree is None:
        tree = _cache["trees"][key] = _build_tree(scene, name_filter)
    return tree


def get_list_filter(objects, scene, name_filter, shown_flag):
    """Gets filtering of given objects list into SCS Outliner tree, as needed by UIList.filter_items. Filtering is cached until
    next invalidation.

    :param objects: all blend data objects
    :type objects: bpy.types.BlendDataObjects
    :param scene: scene of which SCS Game Objects should be listed
    :type scene: bpy.types.Scene
    :param name_filter: case insensitive filter of item names, can use wildcards
    :type name_filter: str
    :param shown_flag: filter flag value for shown items
    :type shown_flag: int
    :return: filter flags and new order of objects
    :rtype: (list[int], list[int])
    """
    key = (_cache["version"], scene.name, name_filter, len(objects), shown_flag)
    list_filter = _cache["list_filter"]
    if list_filter is not None and list_filter[0] == key:
        return list_filter[1], list_filter[2]

    tree = get_tree(scene, name_filter)
    objects_indices = {obj.name: i for i, obj in enumerate(objects)}

    # show only tree items, ordered as in the tree, followed by all hidden items
    flags = [0] * len(objects)
    new_order = [0] * len(objects)

    new_index = 0
    for item in tree:
        obj_index = objects_indices[item.name]
        flags[obj_index] = shown_flag
        new_order[obj_index] = new_index
        new_index += 1

    for obj_index, flag in enumerate(flags):
        if not flag:
            new_order[obj_index] = new_index
            new_index += 1

    _cache["list_filter"] = (key, flags, new_order, {item.name: item for item in tree}, [item.name for item in tree])
    return flags, new_order


def get_list_item(object_name):
    """Gets tree item of given object as lastly filtered for SCS Outliner list.

    :param object_name: name of the object
    :type object_name: str
    :return: tree item; None if object is not shown in SCS Outliner list
    :rtype: TreeItem | None
    """
    list_filter = _cache["list_filter"]
    return list_filter[3].get(object_name) if list_filter else None


def get_displayed_order():
    """Gets names of objects in order as they were lastly displayed in SCS Outliner list, used for range selection.

    :return: names of objects
    :rtype: list[str]
    """
    list_filter = _cache["list_filter"]
    return list_filter[4] if list_filter else []


def _build_tree(scene, name_filter):
    """Builds SCS Outliner tree items for given scene, in display order.

    When name filter is given, only matching items and their ancestors are returned (ignoring collapsed items),
    otherwise children of collapsed items are skipped.

    :param scene: scene of which SCS Game Objects should be listed
    :type scene: bpy.types.Scene
    :param name_filter: case insensitive filter of item names, can use wildcards
    :type name_filter: str
    :return: tree items in display order
    :rtype: list[TreeItem]
    """
    # gather hierarchy in one pass over scene objects
    # NOTE: Object.children is not used, as it iterates all blend data objects on each call
    records = []
    for obj in scene.objects:
        parent = obj.parent
        records.append((obj.name, parent.name if parent else None, is_scs_root(obj), _is_preview_model(obj)))

    scene_names = {record[0] for record in records}
    children = {}
    roots = []
    for name, parent_name, is_root, is_preview_model in records:
        if parent_name is not None and parent_name in scene_names:
            if not is_preview_model:
                children.setdefault(parent_name, []).append(name)
        elif is_root:  # top level SCS Roots only, nested ones are shown within their parents
            roots.append(name)

    roots.sort()
    for child_names in children.values():
        child_names.sort()

    pattern = ("*%s*" % name_filter.lower()) if name_filter else None
    items = []

    def visit(name, depth):
        """Visits object and its children, returns True if object or any of its children matched name filter."""
        child_names = children.get(name, ())
        item_index = len(items)
        items.append(TreeItem(name, depth, len(child_names) > 0))

        if pattern:
            matched = fnmatchcase(name.lower(), pattern)
            for child_name in child_names:
                matched |= visit(child_name, depth + 1)

            # remove not matching items without matching children
            if not matched:
                del items[item_index:]
            return matched

        if name not in _collapsed:
            for child_name in child_names:
                visit(child_name, depth + 1)
        return True

    for root_name in roots:
        visit(root_name, 0)

    return items


def get_icon(obj):
    """Gets icon for given object as keyword arguments for layout functions.

    :param obj: Blender object
    :type obj: bpy.types.Object
    :return: dictionary with "icon_value" for custom SCS icons or "icon" for Blender icons
    :rtype: dict
    """
    icon_type = None

    if obj.type == 'EMPTY':
        scs_props = obj.scs_props
        if scs_props.empty_object_type == 'SCS_Root':
            icon_type = _ICON_TYPES.scs_root
        elif scs_props.empty_object_type == 'Locator':
            if scs_props.locator_type == 'Model':
                icon_type = _ICON_TYPES.loc_model
            elif scs_props.locator_type == 'Collision':
                icon_type = _COLLIDER_TYPE_ICONS.get(scs_props.locator_collider_type, _ICON_TYPES.loc_collider)
            elif scs_props.locator_type == 'Prefab':
                icon_type = _PREFAB_TYPE_ICONS.get(scs_props.locator_prefab_type, _ICON_TYPES.loc_prefab)
            else:
                icon_type = _ICON_TYPES.loc

    elif obj.type == 'MESH':
        has_shadow, has_glass, has_static_collision, is_other = _material_utils.get_material_info(obj)
        if has_static_collision:
            icon_type = _ICON_TYPES.mesh_with_physics
        elif has_glass:
            icon_type = _ICON_TYPES.mesh_glass
        elif has_shadow and not is_other:
            icon_type = _ICON_TYPES.mesh_shadow_caster
        else:
            icon_type = _ICON_TYPES.mesh

    if icon_type:
        icon_value = _get_icon(icon_type)
        if icon_value:
            return {"icon_value": icon_value}

    return {"icon": _BLENDER_TYPE_ICONS.get(obj.type, 'OBJECT_DATA')}

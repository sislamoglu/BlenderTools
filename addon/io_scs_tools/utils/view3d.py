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

# Copyright (C) 2013-2019: SCS Software

import bpy


def get_all_spaces(screen=None):
    """Gets all the spaces in Blender which are type of bpy.types.SpaceView3D

    :param screen: blender screen; if None is given all screens are taken from window manager
    :type screen: bpy.types.Screen
    :return: all the spaces of type bpy.types.SpaceView3D
    :rtype: list of bpy.types.SpaceView3D
    """
    screens = set()
    if not screen:
        for wnd in bpy.context.window_manager.windows:
            screens.add(wnd.screen)
    else:
        screens.add(screen)

    spaces = []
    for screen in screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if isinstance(space, bpy.types.SpaceView3D):
                        spaces.append(space)

    return spaces


def has_multiple_view3d_spaces(screen=None):
    """Tells if given blender screen has multile 3D views or not.

    :param screen: blender screen; if None is given all screens are taken from window manager
    :type screen: bpy.types.Screen
    :return: True if at leas one 3d view is present; False otherwise
    :rtype: bool
    """

    screens = set()
    if not screen:
        for wnd in bpy.context.window_manager.windows:
            screens.add(wnd.screen)
    else:
        screens.add(screen)

    spaces_count = 0
    for scr in screens:
        for area in scr.areas:

            if area.type == 'VIEW_3D':
                spaces_count += 1

            if spaces_count > 1:
                return True

    return False


def has_view3d_space(screen):
    """Tells if given blender screen has 3D view or not.

    :param screen: blender screen
    :type screen: bpy.types.Screen
    :return: True if at leas one 3d view is present; False otherwise
    :rtype: bool
    """

    if screen is None:
        return False

    for area in screen.areas:
        if area.type == 'VIEW_3D':
            return True

    return False


def get_spaces_with_local_view(screen=None):
    """Gets all spaces of current screen that currently have active local view.

    :param screen: blender screen; if None is given all screens are taken from window manager
    :type screen: bpy.types.Screen
    :return: list of local view spaces
    :rtype: list[bpy.types.SpaceView3D]
    """
    spaces = []
    for space in get_all_spaces(screen):
        if space.local_view:
            spaces.append(space)

    return spaces


def tag_redraw_all_view3d():
    # NOTE: Py can't access notifiers!
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


def tag_redraw_all_view3d_and_props():
    # NOTE: Py can't access notifiers!
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


def tag_redraw_all_regions():
    # NOTE: Py can't access notifiers!
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            for region in area.regions:
                region.tag_redraw()


def get_shape_hit_depth(lines, tris, region, region_3d, mouse_co, radius):
    """Gets depth along the view ray under the mouse, at which given shape is hit.

    Triangles are hit by ray intersection, lines are hit when closer to the mouse than given radius in pixels.

    :param lines: lines vertices positions in world space (each two vertices make a line)
    :type lines: list[tuple]
    :param tris: triangles vertices positions in world space (each three vertices make a triangle)
    :type tris: list[tuple]
    :param region: 3D view region
    :type region: bpy.types.Region
    :param region_3d: 3D view region data
    :type region_3d: bpy.types.RegionView3D
    :param mouse_co: mouse position in region coordinates
    :type mouse_co: mathutils.Vector
    :param radius: lines picking radius in pixels
    :type radius: float
    :return: depth along view ray of the closest hit; None if shape isn't hit
    :rtype: float | None
    """
    from mathutils import Vector
    from mathutils.geometry import intersect_ray_tri, intersect_point_line
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d, location_3d_to_region_2d

    ray_origin = region_2d_to_origin_3d(region, region_3d, mouse_co)
    ray_dir = region_2d_to_vector_3d(region, region_3d, mouse_co)

    depths = []

    for i in range(0, len(tris) - 2, 3):
        hit = intersect_ray_tri(Vector(tris[i]), Vector(tris[i + 1]), Vector(tris[i + 2]), ray_dir, ray_origin, False)
        if hit is not None:
            depths.append((hit - ray_origin).dot(ray_dir))

    for i in range(0, len(lines) - 1, 2):
        start, end = Vector(lines[i]), Vector(lines[i + 1])
        start_2d = location_3d_to_region_2d(region, region_3d, start)
        end_2d = location_3d_to_region_2d(region, region_3d, end)
        if start_2d is None or end_2d is None:
            continue

        closest_2d, factor = intersect_point_line(mouse_co, start_2d, end_2d)
        factor = min(max(factor, 0.0), 1.0)
        if (start_2d.lerp(end_2d, factor) - mouse_co).length <= radius:
            depths.append((start.lerp(end, factor) - ray_origin).dot(ray_dir))

    return min(depths) if depths else None


def get_selectable_object_hit_depth(context, region, region_3d, mouse_co):
    """Gets depth along the view ray under the mouse, at which closest selectable and visible object geometry is hit.
    Objects which can't be selected don't occlude, same as by Blender selection.

    :param context: Blender context
    :type context: bpy.types.Context
    :param region: 3D view region
    :type region: bpy.types.Region
    :param region_3d: 3D view region data
    :type region_3d: bpy.types.RegionView3D
    :param mouse_co: mouse position in region coordinates
    :type mouse_co: mathutils.Vector
    :return: depth along view ray of the closest hit; None if no selectable object is hit
    :rtype: float | None
    """
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d

    ray_origin = region_2d_to_origin_3d(region, region_3d, mouse_co)
    ray_dir = region_2d_to_vector_3d(region, region_3d, mouse_co)
    depsgraph = context.evaluated_depsgraph_get()

    origin = ray_origin
    for _ in range(32):
        is_hit, location, _, _, obj, _ = context.scene.ray_cast(depsgraph, origin, ray_dir)
        if not is_hit:
            return None

        obj = obj.original
        if not obj.hide_select and obj.visible_get():
            return (location - ray_origin).dot(ray_dir)

        # continue ray behind not selectable object
        origin = location + ray_dir * 1e-4

    return None

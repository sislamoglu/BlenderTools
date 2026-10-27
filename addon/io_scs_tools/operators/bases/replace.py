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
import re
from bpy.props import StringProperty, BoolProperty
from io_scs_tools.consts import Icons as _ICONS_consts
from io_scs_tools.internals.icons import get_icon as _get_icon
from io_scs_tools.utils import object as _object_utils

_SCOPE_SEPARATOR = "\t"
_SCOPE_INDENT = "      "
_scope_items_cache = {}
"""Last returned scope enum items per roots inclusion, Python has to keep references to dynamic enum items strings."""


def _is_scs_root(obj):
    return obj.type == 'EMPTY' and obj.scs_props.empty_object_type == 'SCS_Root'


class Replace:
    """Base class for search & replace operators: search/replace properties with case sensitive and regular expressions options
    and scope, selecting scene, collection or SCS Root under which replacing is done.
    NOTE: Can not be used directly, only trough inheriting! Inheriting class has to define "scope" property using
    "get_scope_items" as items callback, e.g.:
    scope: EnumProperty(name="Replace In", items=lambda self, context: Replace.get_scope_items(context, True), options={'SKIP_SAVE'})
    """

    @staticmethod
    def get_scope_items(context, include_roots):
        """Gets scope enum items as hierarchy: scenes (current one first, thus default) > collections containing SCS Roots
        (nested as in outliner) > optionally SCS Roots themselves.

        :param context: Blender context
        :type context: bpy.types.Context
        :param include_roots: should SCS Roots be listed as items too
        :type include_roots: bool
        :return: enum items
        :rtype: list[tuple]
        """
        items = []
        identifiers = set()
        root_icon = _get_icon(_ICONS_consts.Types.scs_root)

        def add(identifier, name, description, icon, depth):
            if identifier in identifiers:  # collections and objects can be linked in multiple places, list only first one
                return
            identifiers.add(identifier)
            items.append((identifier, _SCOPE_INDENT * depth + name, description, icon, len(items)))

        def add_roots(scene, objects, depth):
            if not include_roots:
                return
            for obj in sorted((obj for obj in objects if _is_scs_root(obj)), key=lambda o: o.name):
                add(_SCOPE_SEPARATOR.join(("ROOT", scene.name, obj.name)), obj.name,
                    "Only SCS Root %r with its objects" % obj.name, root_icon, depth)

        def add_collection(scene, collection, depth):
            if not any(_is_scs_root(obj) for obj in collection.all_objects):
                return
            add(_SCOPE_SEPARATOR.join(("COLLECTION", scene.name, collection.name)), collection.name,
                "All SCS Roots in collection %r (incl. its child collections) with their objects" % collection.name,
                'OUTLINER_COLLECTION', depth)
            for child in collection.children:
                add_collection(scene, child, depth + 1)
            add_roots(scene, collection.objects, depth + 1)

        scenes = list(bpy.data.scenes)
        if context.scene in scenes:
            scenes.remove(context.scene)
            scenes.insert(0, context.scene)

        for scene in scenes:
            add(_SCOPE_SEPARATOR.join(("SCENE", scene.name)), scene.name, "All objects in scene %r" % scene.name, 'SCENE_DATA', 0)
            for child in scene.collection.children:
                add_collection(scene, child, 1)
            add_roots(scene, scene.collection.objects, 1)

        _scope_items_cache[include_roots] = items
        return items

    def get_scope(self, context):
        """Gets scene and collection or SCS Root selected by scope property.

        :param context: Blender context
        :type context: bpy.types.Context
        :return: scope type ("SCENE", "COLLECTION" or "ROOT"), scene and collection/SCS Root (None for scene)
        :rtype: (str, bpy.types.Scene, bpy.types.Collection | bpy.types.Object | None)
        """
        kind, scene_name, name = (self.scope.split(_SCOPE_SEPARATOR) + ["", ""])[:3]
        scene = bpy.data.scenes.get(scene_name, context.scene)

        if kind == "COLLECTION" and name in bpy.data.collections:
            return kind, scene, bpy.data.collections[name]
        if kind == "ROOT" and name in bpy.data.objects:
            return kind, scene, bpy.data.objects[name]

        return "SCENE", scene, None

    def get_scope_roots(self, context):
        """Gets SCS Roots within selected scope.

        :param context: Blender context
        :type context: bpy.types.Context
        :return: SCS Root objects
        :rtype: list[bpy.types.Object]
        """
        kind, scene, data = self.get_scope(context)
        if kind == "ROOT":
            return [data]

        objects = data.all_objects if kind == "COLLECTION" else scene.objects
        return [obj for obj in objects if _is_scs_root(obj)]

    def get_scope_objects(self, context):
        """Gets objects within selected scope: all scene objects for scene,
        otherwise SCS Roots and objects belonging to them (nested SCS Roots only if they are within scope themselves).

        :param context: Blender context
        :type context: bpy.types.Context
        :return: objects
        :rtype: list[bpy.types.Object]
        """
        kind, scene, data = self.get_scope(context)
        if kind == "SCENE":
            return list(scene.objects)

        objects = []
        for root_obj in self.get_scope_roots(context):
            objects.append(root_obj)
            objects.extend(obj for obj in _object_utils.get_children(root_obj) if _object_utils.get_scs_root(obj) == root_obj)

        return objects

    search_for: StringProperty(
        name="Search for",
        description="Text (or regular expression) to search for",
        default="",
    )
    replace_with: StringProperty(
        name="Replace",
        description="Text to replace found text with. With regular expressions groups can be referenced as \\1 or $1, "
                    "${name} or \\g<name> for named groups, $0 for whole match and $$ for literal dollar sign",
        default="",
    )
    case_sensitive: BoolProperty(
        name="Case Sensitive",
        description="Match upper and lower case exactly",
        default=False,
    )
    use_regex: BoolProperty(
        name="Regular Expressions",
        description="Use regular expression for search (Python syntax)",
        default=False,
    )

    @staticmethod
    def to_python_template(replace_with):
        """Converts "$" group references used by many tools into Python regular expression template:
        $1 and ${1} -> \\g<1>, ${name} -> \\g<name>, $0 -> \\g<0> (whole match), $$ -> $.
        Python references (\\1, \\g<name>) stay as they are.

        :param replace_with: replacement string
        :type replace_with: str
        :return: replacement string usable by re.sub
        :rtype: str
        """
        def convert(match):
            if match.group(0) == "$$":
                return "$"
            return "\\g<%s>" % (match.group(1) or match.group(2))

        return re.sub(r"\$\$|\$(\d+)|\$\{(\w+)\}", convert, replace_with)

    def get_replace_function(self):
        """Gets function replacing text by current search & replace settings.

        :return: function taking string and returning string with replacements done
        :rtype: callable
        :raises ValueError: if search is empty or regular expression/replacement is invalid, with message for the user
        """
        if self.search_for == "":
            raise ValueError("Nothing to search for, please enter search text!")

        flags = 0 if self.case_sensitive else re.IGNORECASE
        replace_with = self.to_python_template(self.replace_with) if self.use_regex else self.replace_with
        try:
            pattern = re.compile(self.search_for if self.use_regex else re.escape(self.search_for), flags)
            # validate replacement string (e.g. invalid group reference)
            if self.use_regex:
                pattern.sub(replace_with, "")
        except re.error as e:
            raise ValueError("Invalid regular expression: %s" % e)
        except IndexError as e:  # group referenced in replacement doesn't exist in search
            raise ValueError("Invalid group reference in replace: %s" % e)

        if self.use_regex:
            return lambda value: pattern.sub(replace_with, value)

        return lambda value: pattern.sub(lambda _: replace_with, value)

    def get_unused_groups_warning(self):
        """Gets warning if regular expression search has groups, but none of them is referenced in replace,
        which usually means user forgot to put them back into replaced text.

        :return: message for the user if groups are unused, None otherwise (also if settings are invalid)
        :rtype: str | None
        """
        if not self.use_regex or self.search_for == "":
            return None

        try:
            pattern = re.compile(self.search_for)
        except re.error:
            return None

        if pattern.groups == 0:
            return None

        # group references other than whole match (\0 isn't a group reference in Python, but $0 converts to \g<0>),
        # backslash preceded by even number of backslashes is escaped thus not a reference
        template = self.to_python_template(self.replace_with)
        for match in re.finditer(r"(?<!\\)(?:\\\\)*\\(?:(\d+)|g<(\w+)>)", template):
            group = match.group(1) or match.group(2)
            if group.lstrip("0") != "":
                return None

        if pattern.groups == 1:
            return "Search has a regex group, but Replace doesn't use it ($1 or \\1)"

        return "Search has %i regex groups, but Replace doesn't use any of them ($1 or \\1)" % pattern.groups

    in_dialog: BoolProperty(
        description="Is operator drawn in its invoke dialog, which draws its own buttons",
        default=False,
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    ask_confirm: BoolProperty(
        description="Ask user for confirmation before replacing, as regex groups are unused in replace",
        default=False,
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    def get_error(self):
        """Gets error of current search & replace settings.

        :return: message for the user if settings are invalid, None otherwise
        :rtype: str | None
        """
        try:
            self.get_replace_function()
        except ValueError as e:
            return str(e)

        return None

    def draw_scope(self, layout):
        """Draws scope property as menu button showing selected item name without hierarchy indentation.

        :param layout: Blender UI Layout to draw to
        :type layout: bpy.types.UILayout
        """
        kind, scene_name, name = (self.scope.split(_SCOPE_SEPARATOR) + ["", ""])[:3]
        icons = {"SCENE": 'SCENE_DATA', "COLLECTION": 'OUTLINER_COLLECTION', "ROOT": 'OUTLINER_OB_EMPTY'}

        # split same as property split layout
        split = layout.split(factor=0.4, align=True)
        label_row = split.row()
        label_row.alignment = 'RIGHT'
        label_row.label(text="Replace In")
        split.prop_menu_enum(self, "scope", text=scene_name if kind == "SCENE" else name, icon=icons.get(kind, 'SCENE_DATA'))

    def draw_replace_props(self, layout):
        """Draws search & replace properties, with warning if regular expression is invalid or its groups are unused.

        :param layout: Blender UI Layout to draw to
        :type layout: bpy.types.UILayout
        """
        layout.use_property_split = True
        layout.use_property_decorate = False

        # empty search is not an error worth warning about, user just didn't enter it yet
        error = self.get_error() if self.search_for != "" else None

        self.draw_scope(layout)

        col = layout.column()
        col.alert = error is not None and self.use_regex
        col.prop(self, "search_for")
        layout.prop(self, "replace_with")
        layout.prop(self, "case_sensitive")
        layout.prop(self, "use_regex")

        if error:
            row = layout.row()
            row.alert = True
            row.label(text=error, icon='ERROR')
        else:
            warning = self.get_unused_groups_warning()
            if warning:
                layout.label(text=warning, icon='QUESTION')

    def draw_replace_buttons(self, layout, text="Replace"):
        """Draws confirm & cancel buttons of the invoke dialog, confirm one disabled while settings are invalid
        and asking for confirmation if regex groups are unused in replace.

        NOTE: Should be called at the end of draw. As dialog then has its own default button,
        Blender doesn't add its own confirm & cancel buttons, which can't be disabled.

        :param layout: Blender UI Layout to draw to
        :type layout: bpy.types.UILayout
        :param text: confirm button text
        :type text: str
        """
        if not self.in_dialog:  # e.g. adjust last operation panel
            return

        layout.separator()

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator_context = 'EXEC_DEFAULT'

        confirm_row = row.row(align=True)
        confirm_row.enabled = self.get_error() is None
        confirm_row.active_default = True
        ask_confirm = self.get_unused_groups_warning() is not None
        if ask_confirm:
            confirm_row.operator_context = 'INVOKE_DEFAULT'

        props = confirm_row.operator(self.bl_idname, text=text)
        for prop in props.bl_rna.properties:
            if prop.identifier not in ("rna_type", "in_dialog", "ask_confirm"):
                setattr(props, prop.identifier, getattr(self, prop.identifier))
        props.ask_confirm = ask_confirm

        row.operator("wm.scs_tools_close_dialog")

    def invoke_replace_dialog(self, context, event):
        """Invokes dialog with search & replace properties and own buttons,
        or confirmation if invoked from that dialog with unused regex groups.

        :param context: Blender context
        :type context: bpy.types.Context
        :param event: Blender event
        :type event: bpy.types.Event
        :return: invoke dialog result
        :rtype: set
        """
        warning = self.get_unused_groups_warning() if self.ask_confirm else None
        if warning:
            return context.window_manager.invoke_confirm(self, event,
                                                         title=self.bl_label,
                                                         message=warning + ". Replace anyway?",
                                                         confirm_text="Replace",
                                                         icon='WARNING')

        self.in_dialog = True
        return context.window_manager.invoke_props_dialog(self, width=400)

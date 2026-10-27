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

import re
from bpy.props import StringProperty, BoolProperty


class Replace:
    """Base class for search & replace operators: search/replace properties with case sensitive and regular expressions options.
    NOTE: Can not be used directly, only trough inheriting!
    """

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

    def draw_replace_props(self, layout):
        """Draws search & replace properties, with warning if regular expression is invalid or its groups are unused.

        :param layout: Blender UI Layout to draw to
        :type layout: bpy.types.UILayout
        """
        layout.use_property_split = True
        layout.use_property_decorate = False

        # empty search is not an error worth warning about, user just didn't enter it yet
        error = self.get_error() if self.search_for != "" else None

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

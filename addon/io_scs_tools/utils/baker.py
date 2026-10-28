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

"""
LOD baker setup helpers. Baking setup is a SII file named after target SCS Root ("<root name>.bake"),
written beside exported PIM file in the same format as SCS Maya tools write it. It's consumed by SCS baker
which bakes textures of source model onto target model.
"""

import getpass
import os
from collections import OrderedDict
from io_scs_tools.consts import Baker as _BAKER_consts
from io_scs_tools.internals.containers import sii as _sii_container
from io_scs_tools.utils import object as _object_utils
from io_scs_tools.utils import path as _path_utils
from io_scs_tools.utils import get_scs_globals as _get_scs_globals
from io_scs_tools.utils.printout import lprint


def get_scs_roots(scene):
    """Gets all SCS Root objects from given scene.

    :param scene: scene to search in
    :type scene: bpy.types.Scene
    :return: SCS Root objects sorted by name
    :rtype: list[bpy.types.Object]
    """
    roots = [obj for obj in scene.objects if obj.scs_props.empty_object_type == 'SCS_Root']
    return sorted(roots, key=lambda obj: obj.name)


def get_export_dirpath(root_obj):
    """Gets export directory of given SCS Root, the same way as export does it.

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :return: normalized export directory path
    :rtype: str
    """
    custom_filepath = _path_utils.get_custom_scs_root_export_path(root_obj)
    if custom_filepath:
        return _path_utils.readable_norm(custom_filepath)
    return _path_utils.readable_norm(_path_utils.get_global_export_path())


def get_setup_filepath(root_obj):
    """Gets baking setup file path of given SCS Root as target ("<export dir>/<root name>.bake").

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: str
    """
    return _path_utils.readable_norm(os.path.join(get_export_dirpath(root_obj), root_obj.name + _BAKER_consts.setup_ext))


def get_model_filepath(root_obj):
    """Gets model descriptor file path of given SCS Root as referenced by baking setup ("<export dir>/<root name>.pmd").

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: str
    """
    return _path_utils.readable_norm(os.path.join(get_export_dirpath(root_obj), root_obj.name + ".pmd"))


def is_bake_sources_setup(setup_filepath):
    """Tells if baking setup is inside bake sources directory.

    :param setup_filepath: baking setup file path
    :type setup_filepath: str
    :rtype: bool
    """
    return _BAKER_consts.bake_sources_dir in setup_filepath


def get_available_texture_types(setup_filepath):
    """Gets texture types which can be baked by baking setup on given path.

    :param setup_filepath: baking setup file path
    :type setup_filepath: str
    :rtype: list[str]
    """
    if is_bake_sources_setup(setup_filepath):
        return list(_BAKER_consts.texture_types)
    return [tex_type for tex_type in _BAKER_consts.texture_types if tex_type not in _BAKER_consts.bake_sources_only_texture_types]


def guess_source_root(target_root, roots):
    """Guesses source SCS Root for given target the same way as SCS Maya tools:
    "name_lodN" is baked from "name_lod(N-1)", if it doesn't exist from "name".

    :param target_root: target SCS Root object
    :type target_root: bpy.types.Object
    :param roots: SCS Root objects to search in
    :type roots: list[bpy.types.Object]
    :return: guessed source SCS Root or None
    :rtype: bpy.types.Object | None
    """
    target_name = target_root.name
    if "_lod" not in target_name:
        return None

    tokens = target_name.split("_lod")
    if not tokens[1].isdigit() or int(tokens[1]) == 0:
        return None

    roots_by_name = {root.name: root for root in roots if root != target_root}
    lower_lod_name = tokens[0] + "_lod" + str(int(tokens[1]) - 1)
    if lower_lod_name in roots_by_name:
        return roots_by_name[lower_lod_name]

    return roots_by_name.get(tokens[0], None)


def get_root_meshes(root_obj):
    """Gets mesh objects belonging to given SCS Root (excluding meshes of nested SCS Roots).

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: list[bpy.types.Object]
    """
    return [obj for obj in _object_utils.get_children(root_obj)
            if obj.type == 'MESH' and _object_utils.get_scs_root(obj) == root_obj]


def is_baked_material(material):
    """Tells if given material uses baked effect.

    :type material: bpy.types.Material | None
    :rtype: bool
    """
    return material is not None and material.scs_props.mat_effect_name.startswith(_BAKER_consts.baked_effect_prefix)


def get_baked_materials(root_obj):
    """Gets baked materials used by meshes of given SCS Root.

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: set[bpy.types.Material]
    """
    materials = set()
    for mesh_obj in get_root_meshes(root_obj):
        for slot in mesh_obj.material_slots:
            if is_baked_material(slot.material):
                materials.add(slot.material)
    return materials


def get_part_names(root_obj):
    """Gets part names of given SCS Root.

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: list[str]
    """
    return [part.name for part in root_obj.scs_object_part_inventory]


def get_look_names(root_obj):
    """Gets look names of given SCS Root.

    :param root_obj: SCS Root object
    :type root_obj: bpy.types.Object
    :rtype: list[str]
    """
    return [look.name for look in root_obj.scs_object_look_inventory]


def get_part_mapping(target_root, source_root):
    """Gets mapping of target parts onto source parts. Only target parts with meshes using baked material are mapped,
    each onto the source part with the same name.

    :param target_root: target SCS Root object
    :type target_root: bpy.types.Object
    :param source_root: source SCS Root object
    :type source_root: bpy.types.Object
    :return: ordered dictionary of target part name -> list of source part names
    :rtype: collections.OrderedDict[str, list[str]]
    """
    baked_parts = set()
    for mesh_obj in get_root_meshes(target_root):
        if any(is_baked_material(slot.material) for slot in mesh_obj.material_slots):
            baked_parts.add(mesh_obj.scs_props.scs_part)

    source_parts = set(get_part_names(source_root))

    part_mapping = OrderedDict()
    for part_name in get_part_names(target_root):
        if part_name in baked_parts and part_name in source_parts:
            part_mapping[part_name] = [part_name]
    return part_mapping


def _get_relative_path(path, setup_filepath):
    """Gets path relative to baking setup directory with forward slashes."""
    return os.path.relpath(path, os.path.dirname(setup_filepath)).replace("\\", "/")


def _get_output_directory(setup_filepath):
    """Gets textures output directory relative to baking setup. Setups inside bake sources directory output textures
    beside bake sources directory, others in the same directory as baking setup.
    """
    if is_bake_sources_setup(setup_filepath):
        output_dirpath = setup_filepath.split(_BAKER_consts.bake_sources_dir)[0]
        return _get_relative_path(output_dirpath, setup_filepath)
    return "./"


def _format_float(value):
    return str(round(value, 6))


def _as_list(value):
    """Gets SII property value as list. Count only array properties (e.g. "enabled_options: 0") are parsed as strings."""
    if isinstance(value, list):
        return value
    if value is None or (isinstance(value, str) and value.isdigit()):
        return []
    return [value]


def _read_generated_textures(setup_filepath):
    """Reads list of textures generated by previous bake, so they are kept when baking setup is saved again."""
    if not os.path.isfile(setup_filepath):
        return []

    units = _sii_container.get_data_from_file(setup_filepath)
    if not units:
        return []

    for unit in units:
        if unit.type == "baking_result":
            return _as_list(unit.props.get("generated_textures"))
    return []


def get_check_messages(target_root, scene):
    """Checks baking setup of given target SCS Root.

    :param target_root: target SCS Root object
    :type target_root: bpy.types.Object
    :param scene: scene with SCS Roots
    :type scene: bpy.types.Scene
    :return: list of (type, message) tuples, type being 'ERROR' or 'WARNING'
    :rtype: list[tuple[str, str]]
    """
    messages = []
    setup = target_root.scs_props.bake_setup
    setup_filepath = get_setup_filepath(target_root)
    source_root = setup.source_root

    scs_project_path = _get_scs_globals().scs_project_path
    if scs_project_path == "" or not _path_utils.startswith(setup_filepath, scs_project_path):
        messages.append(('ERROR', "Export path of %r is not inside SCS Project Base Path." % target_root.name))

    if source_root is None:
        messages.append(('ERROR', "Source SCS Root is not set."))
    elif source_root.name not in scene.objects:
        messages.append(('ERROR', "Source SCS Root %r is not in this scene." % source_root.name))

    target_baked_materials = get_baked_materials(target_root)
    if len(target_baked_materials) != 1:
        messages.append(('ERROR', "Target %r must use exactly one baked material (%s effect), it uses %s." %
                         (target_root.name, _BAKER_consts.baked_effect_prefix, len(target_baked_materials))))
    else:
        baked_material = next(iter(target_baked_materials))
        for root in get_scs_roots(scene):
            if root != target_root and baked_material in get_baked_materials(root):
                messages.append(('ERROR', "Baked material %r of target is also used by %r." % (baked_material.name, root.name)))

    enabled_types = [tex_type for tex_type in _BAKER_consts.texture_types if setup.get_output(tex_type).enabled]
    available_types = get_available_texture_types(setup_filepath)
    for tex_type in enabled_types:
        if tex_type not in available_types:
            messages.append(('ERROR', "Texture %r can be baked only by baking setups inside %r directory." %
                             (tex_type, _BAKER_consts.bake_sources_dir)))

    if len(enabled_types) == 0:
        messages.append(('ERROR', "Baking setup doesn't bake any textures."))

    if "baked_paint" in enabled_types:
        if "baked_specular" not in enabled_types:
            messages.append(('ERROR', "Specular map must be enabled when baking paintable material."))
        if "baked_environment" not in enabled_types:
            messages.append(('ERROR', "Environment map must be enabled when baking paintable material."))

    if "baked_environment" in enabled_types and "baked_specular" not in enabled_types:
        messages.append(('ERROR', "Specular map must be enabled when baking environment."))

    if "normal_map" in enabled_types and setup.get_output("normal_map").per_look and not setup.bake_source_normal_maps:
        messages.append(('ERROR', "When baking normal map per look, 'Bake Through Material Normals' must be also enabled."))

    width_ratio, height_ratio = setup.get_aspect_ratio()
    for tex_type in enabled_types:
        output = setup.get_output(tex_type)
        height = int(int(output.size) * height_ratio / width_ratio)
        if height > _BAKER_consts.texture_sizes[-1]:
            messages.append(('ERROR', "Texture height for %r is too big (%s), make it smaller or choose different aspect ratio." %
                             (tex_type, height)))

        if output.per_color_variant and is_bake_sources_setup(setup_filepath):
            messages.append(('ERROR', "Baking per color variant is invalid for bake sources."))

    if -setup.near_plane >= setup.far_plane:
        messages.append(('ERROR', "Near plane must be closer than far plane."))

    if source_root is not None:
        target_looks = set(get_look_names(target_root))
        source_looks = set(get_look_names(source_root))
        if target_looks != source_looks:
            messages.append(('ERROR', "Source and target must have the same looks."))

        source_parts = set(get_part_names(source_root))
        for part_name in get_part_names(target_root):
            if part_name not in source_parts:
                messages.append(('ERROR', "Target part %r is missing in source." % part_name))

        if len(target_baked_materials) == 1 and len(get_part_mapping(target_root, source_root)) == 0:
            messages.append(('ERROR', "No target part with baked material can be mapped onto source part."))

    if not os.path.isfile(get_model_filepath(target_root)[:-4] + ".pim"):
        messages.append(('WARNING', "Target %r is not exported yet." % target_root.name))
    if source_root is not None and not os.path.isfile(get_model_filepath(source_root)[:-4] + ".pim"):
        messages.append(('WARNING', "Source %r is not exported yet." % source_root.name))

    return messages


def save_setup(target_root):
    """Writes baking setup of given target SCS Root into its "*.bake" file, in the same format as SCS Maya tools.
    Textures generated by previous bake are kept in the file.

    :param target_root: target SCS Root object
    :type target_root: bpy.types.Object
    :return: tuple of (success, message)
    :rtype: tuple[bool, str]
    """
    setup = target_root.scs_props.bake_setup
    source_root = setup.source_root
    if source_root is None:
        return False, "Source SCS Root is not set!"

    setup_filepath = get_setup_filepath(target_root)
    setup_dirpath = os.path.dirname(setup_filepath)
    if not os.path.isdir(setup_dirpath):
        scs_project_path = _get_scs_globals().scs_project_path
        if scs_project_path == "" or not _path_utils.startswith(setup_dirpath, scs_project_path):
            return False, "Export directory %r doesn't exist and isn't inside SCS Project Base Path!" % setup_dirpath
        os.makedirs(setup_dirpath)

    part_mapping = get_part_mapping(target_root, source_root)
    width_ratio, height_ratio = setup.get_aspect_ratio()
    enabled_types = [tex_type for tex_type in _BAKER_consts.texture_types if setup.get_output(tex_type).enabled]

    # baked parts
    baked_parts_def = ""
    for target_part, source_parts in part_mapping.items():
        baked_parts_def += "baked_part : .%s {\n" % target_part
        for source_part in source_parts:
            baked_parts_def += "\tsource_parts[]: %s\n" % source_part
        baked_parts_def += "\ttarget_part: %s\n" % target_part
        baked_parts_def += "}\n"

    # baking outputs (unit names are made of last 12 characters of texture type, as in Maya tools)
    baking_outputs_def = ""
    for tex_type in enabled_types:
        output = setup.get_output(tex_type)
        width = int(output.size)
        height = int(width * height_ratio / width_ratio)

        baking_outputs_def += "baking_output : .%s {\n" % tex_type[-12:]
        baking_outputs_def += "\tsize: (%s, %s)\n" % (width, height)
        baking_outputs_def += "\ttype: %s\n" % tex_type
        options = _BAKER_consts.texture_type_options[tex_type]
        if output.per_color_variant and _BAKER_consts.TextureOptions.per_color_variant in options:
            baking_outputs_def += "\tenabled_options[]: %s\n" % _BAKER_consts.TextureOptions.per_color_variant
        if output.per_look and _BAKER_consts.TextureOptions.per_look in options:
            baking_outputs_def += "\tenabled_options[]: %s\n" % _BAKER_consts.TextureOptions.per_look
        baking_outputs_def += "}\n"

    # texture set
    texture_set_def = "baked_texture_set : tex_main.main {\n"
    texture_set_def += "\toutput_directory: \"%s\"\n" % _get_output_directory(setup_filepath)
    for target_part in part_mapping:
        texture_set_def += "\tbaked_parts[]: .%s\n" % target_part
    for tex_type in enabled_types:
        texture_set_def += "\tbaking_outputs[]: .%s\n" % tex_type[-12:]
    for global_option in sorted(_BAKER_consts.global_options):
        if getattr(setup, global_option):
            texture_set_def += "\tenabled_options[]: %s\n" % global_option
    texture_set_def += "}\n"

    # baking setup
    setup_def = "baking_setup : _nameless.setup {\n"
    setup_def += "\tsource_model_path: \"./%s\"\n" % _get_relative_path(get_model_filepath(source_root), setup_filepath)
    setup_def += "\ttarget_model_path: \"./%s\"\n" % _get_relative_path(get_model_filepath(target_root), setup_filepath)
    setup_def += "\tnear_plane_distance: %s\n" % _format_float(-setup.near_plane)
    setup_def += "\tfar_plane_distance: %s\n" % _format_float(setup.far_plane)
    setup_def += "\toutput_texture_sets[]: tex_main.main\n"
    setup_def += "\tbaking_result: result.main\n"
    setup_def += "}"

    # baking result, keeping textures from previous bake
    generated_textures = _read_generated_textures(setup_filepath)
    result_def = "baking_result : result.main {\n"
    if len(generated_textures) > 0:
        result_def += "\tgenerated_textures : %s\n" % len(generated_textures)
    for i, texture_path in enumerate(generated_textures):
        result_def += "\tgenerated_textures[%s] : \"%s\"\n" % (i, texture_path)
    result_def += "\tauthor : \"%s\"\n" % getpass.getuser()
    result_def += "}"

    sii_text = "SiiNunit \n{\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n}\n" % (setup_def, texture_set_def, baked_parts_def, baking_outputs_def, result_def)

    with open(setup_filepath, mode="w", encoding="utf-8") as f:
        f.write(sii_text)

    lprint("I Baking setup saved: %r", (setup_filepath,))
    return True, "Baking setup saved: %r" % setup_filepath


def load_setup(target_root, scene):
    """Reads baking setup file of given target SCS Root into its baking setup properties.
    Reads setups written by SCS Maya tools, SCS Blender Tools and also setups rewritten by the baker.

    :param target_root: target SCS Root object
    :type target_root: bpy.types.Object
    :param scene: scene with SCS Roots, used to find source SCS Root
    :type scene: bpy.types.Scene
    :return: tuple of (success, message)
    :rtype: tuple[bool, str]
    """
    setup_filepath = get_setup_filepath(target_root)
    if not os.path.isfile(setup_filepath):
        return False, "Baking setup %r doesn't exist!" % setup_filepath

    units = _sii_container.get_data_from_file(setup_filepath)
    if not units:
        return False, "Baking setup %r couldn't be read!" % setup_filepath

    setup = target_root.scs_props.bake_setup

    # reset to defaults, so properties not written in file don't stay from before
    for prop_name in ("near_plane", "far_plane", "aspect_ratio") + _BAKER_consts.global_options:
        setup.property_unset(prop_name)
    for tex_type in _BAKER_consts.texture_types:
        output = setup.get_output(tex_type)
        for prop_name in ("enabled", "size", "per_look", "per_color_variant"):
            output.property_unset(prop_name)

    message = "Baking setup loaded: %r" % setup_filepath
    for unit in units:

        if unit.type == "baking_setup":

            if "near_plane_distance" in unit.props:
                setup.near_plane = abs(float(unit.props["near_plane_distance"]))
            if "far_plane_distance" in unit.props:
                setup.far_plane = float(unit.props["far_plane_distance"])

            # find source SCS Root by its exported model path
            source_model_path = unit.props.get("source_model_path", "")
            source_model_path = os.path.join(os.path.dirname(setup_filepath), source_model_path)
            source_model_path = _path_utils.full_norm(source_model_path)
            setup.source_root = None
            for root in get_scs_roots(scene):
                if root != target_root and _path_utils.full_norm(get_model_filepath(root)) == source_model_path:
                    setup.source_root = root
                    break
            else:
                message = "Baking setup loaded, but source model %r doesn't match export path of any SCS Root!" % \
                          unit.props.get("source_model_path", "")

        elif unit.type == "baked_texture_set":

            for option in _as_list(unit.props.get("enabled_options")):
                if option in _BAKER_consts.global_options:
                    setattr(setup, option, True)

        elif unit.type == "baking_output":

            tex_type = unit.props.get("type", "")
            if tex_type not in _BAKER_consts.texture_types:
                lprint("W Unsupported baking output type %r in %r, ignoring it!", (tex_type, setup_filepath))
                continue

            output = setup.get_output(tex_type)
            output.enabled = True

            # newer format has size with width and height, older only width as texture size
            size = unit.props.get("size")
            if isinstance(size, list) and len(size) == 2:
                width, height = int(float(size[0])), int(float(size[1]))
                for ratio in _BAKER_consts.aspect_ratios:
                    if int(width * ratio[1] / ratio[0]) == height:
                        setup.aspect_ratio = "%s_%s" % ratio
                        break
            else:
                width = int(unit.props.get("texture_size", _BAKER_consts.texture_sizes[0]))

            if width in _BAKER_consts.texture_sizes:
                output.size = str(width)

            # in older format some global options could be listed in each baking output
            for option in _as_list(unit.props.get("enabled_options")):
                if option == _BAKER_consts.TextureOptions.per_look:
                    output.per_look = True
                elif option == _BAKER_consts.TextureOptions.per_color_variant:
                    output.per_color_variant = True
                elif option in _BAKER_consts.global_options:
                    setattr(setup, option, True)

    lprint("I %s", (message,))
    return setup.source_root is not None, message

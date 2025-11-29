from bl_operators.presets import AddPresetBase
import subprocess
import platform
import os
import re
from collections import namedtuple
import time
import mathutils
import math
import bpy

bl_info = {
    'name': 'Theme Editor',
    'author': 'Miguel Pozo (pragma37)',
    'version': (1, 1, 2),
    'blender': (5, 0, 0),
    'description':
        'Nicer theme editor :)',
    'location':
        '3D View > Properties > Theme Editor',
    'category': 'UI',
    'doc_url': "https://github.com/pragma37/Blender-Theme-Editor",
    'tracker_url': "https://github.com/pragma37/Blender-Theme-Editor"
}


ColorTuple = namedtuple('ColorTuple', ['struct', 'key', 'path'])
theme_properties = None
colors = None
ordered_colors = None
already_built = False

UndoItem = namedtuple('UndoItem', ['color', 'struct', 'key'])
UndoSteps = []
UndoLevel = 0
CanPushUndo = True


def push_undo_step():
    global CanPushUndo
    if CanPushUndo == False:
        return

    theme_edit = bpy.context.window_manager.theme_edit
    highlight = theme_edit.highlight_selected
    theme_edit.highlight_selected = False

    global UndoLevel
    for i in range(0, UndoLevel):
        UndoSteps.pop()
    UndoLevel = 0
    undo_step = []
    for prop in theme_properties:
        attribute = getattr(prop.struct, prop.key)
        color = color_to_tuple(attribute)
        undo_step.append(UndoItem(color, prop.struct, prop.key))
    UndoSteps.append(undo_step)
    theme_edit.highlight_selected = highlight


def apply_undo_step(undo_step):
    theme_edit = bpy.context.window_manager.theme_edit
    highlight = theme_edit.highlight_selected
    theme_edit.highlight_selected = False

    for undo_item in undo_step:
        set_color(undo_item, undo_item.color)

    build_color_list()
    theme_edit.highlight_selected = highlight


class WM_OT_theme_editor_undo(bpy.types.Operator):
    bl_idname = "wm.theme_editor_undo"
    bl_label = "Theme Editor Undo"
    bl_description = "Undo the last change made to the theme colors"

    @classmethod
    def poll(cls, context):
        return len(UndoSteps) > 1 and len(UndoSteps) > UndoLevel + 1

    def execute(self, context):
        global UndoLevel
        UndoLevel += 1
        index = len(UndoSteps) - 1 - UndoLevel
        apply_undo_step(UndoSteps[index])
        return {'FINISHED'}


class WM_OT_theme_editor_redo(bpy.types.Operator):
    bl_idname = "wm.theme_editor_redo"
    bl_label = "Theme Editor Redo"
    bl_description = "Redo the last undone change made to the theme colors"

    @classmethod
    def poll(cls, context):
        return UndoLevel > 0

    def execute(self, context):
        global UndoLevel
        UndoLevel -= 1
        index = len(UndoSteps) - 1 - UndoLevel
        apply_undo_step(UndoSteps[index])
        return {'FINISHED'}


def color_paths(index):
    return colors[ordered_colors[index]]


def color_to_tuple(color):
    if color.__class__.__name__ == 'Color':
        return (color.r, color.g, color.b, 1.0)
    if color.__class__.__name__ == 'bpy_prop_array':
        return tuple(color)


def set_collection_length(collection, length):
    while len(collection) < length:
        collection.add()
    while len(collection) > length:
        collection.remove(len(collection) - 1)


def update_path_collection_length():
    theme_edit = bpy.context.window_manager.theme_edit
    index = theme_edit.group_index
    length = 0
    if index < len(ordered_colors):
        length = len(color_paths(index))
    set_collection_length(theme_edit.color_paths, length)


def sort_paths(search_terms):
    for color, params in colors.items():
        params.sort(key=lambda e: (filter_string(
            e.path, search_terms) == False, e.path))


def filter_string(string, filter):
    match = False
    string = string.lower()
    filter = filter.lower()
    filters = filter.split(',')
    for filter in filters:
        filter = filter.strip()
        if filter.startswith('?'):
            if filter.strip('? ') in string:
                match = True
        elif filter.startswith('-'):
            if filter.strip('- ') in string:
                match = False
                break
        else:
            if filter in string:
                match = True
            else:
                match = False
                break
    return match


def build_color_list():
    global CanPushUndo
    CanPushUndo = False
    theme_edit = bpy.context.window_manager.theme_edit
    filter_by_color = theme_edit.filter_by_color
    color_filter = theme_edit.color_filter
    color_filter_hsv = mathutils.Color(color_filter[0:3])
    filter_by_name = theme_edit.filter_by_name
    name_filter = theme_edit.name_filter
    theme_colors = theme_edit.color_groups
    sort_terms = theme_edit.sort_terms
    global already_built
    already_built = False

    highlight = theme_edit.highlight_selected
    if highlight:
        theme_edit.highlight_selected = False

    theme = bpy.context.preferences.themes[0]

    global theme_properties

    if theme_properties is None:
        theme_properties = []

        def inspect_struct(struct, path=""):
            for key in dir(struct):
                if key in ["bl_rna", "rna_type"]:
                    continue
                attribute = getattr(struct, key)
                name = ""
                if key in struct.bl_rna.properties:
                    name = struct.bl_rna.properties[key].name
                separator = "::" if path != "" else ""
                if issubclass(type(attribute), bpy.types.bpy_struct):
                    inspect_struct(attribute, path+separator+name)
                else:
                    attribute = getattr(struct, key)
                    color = color_to_tuple(attribute)
                    if color:
                        theme_properties.append(ColorTuple(
                            struct, key, path+separator+name))

        inspect_struct(theme)

    global colors
    colors = {}
    global ordered_colors
    ordered_colors = {}

    set_collection_length(theme_edit.color_paths, 0)

    for prop in theme_properties:
        struct, key, path = prop
        attribute = getattr(struct, key)
        color = color_to_tuple(attribute)

        if color:
            if filter_by_color:
                hsv = mathutils.Color(color[0:3])
                if (math.isclose(hsv.h, color_filter_hsv.h, abs_tol=theme_edit.color_filter_h) == False or
                    math.isclose(hsv.s, color_filter_hsv.s, abs_tol=theme_edit.color_filter_s) == False or
                        math.isclose(hsv.v, color_filter_hsv.v, abs_tol=theme_edit.color_filter_v) == False):
                    continue
            if filter_by_name:
                # if not re.search(name_filter, path, re.IGNORECASE):
                if not filter_string(path, name_filter):
                    continue

            color_tuple = ColorTuple(struct, key, path)
            if color in colors:
                colors[color].append(color_tuple)
            else:
                colors[color] = [color_tuple]

    def build_theme_colors(dic):
        def user_sort(e):
            return len(dic[e])

        def color_sort(e):
            e = dic[e][0]
            attribute = getattr(e.struct, e.key)
            color = color_to_tuple(attribute)
            color = mathutils.Color(color[0:3])
            return (color.s == 0, -color.h, color.s, color.v)
            # return -color.h * 1000000 + color.s * 100 + color.v

        sort = user_sort if theme_edit.sort_type == 'USERS' else color_sort
        global ordered_colors
        ordered_colors = sorted(dic, key=sort, reverse=True)
        set_collection_length(theme_colors, len(ordered_colors))

        for i, key in enumerate(ordered_colors):
            theme_colors[i].color = key
            theme_colors[i].index = i

    build_theme_colors(colors)
    sort_paths(sort_terms)
    theme_edit.group_index = 0
    if highlight:
        theme_edit.highlight_selected = True

    update_path_collection_length()

    already_built = True
    CanPushUndo = True


def build_color_list_callback(self, context):
    build_color_list()


def set_color(property, color):
    try:
        setattr(property.struct, property.key, color[0:3])
    except ValueError:
        setattr(property.struct, property.key, color)


def set_color_group(group_index, color):
    for property in color_paths(group_index):
        set_color(property, color)


last_index = None


def group_index_callback(self, context):
    global CanPushUndo
    CanPushUndo = False
    global last_index
    new_index = self.group_index

    if last_index is not None:
        for i, color_path in enumerate(self.color_paths):
            prop = color_paths(last_index)[i]
            set_color(prop, color_path.color)

    update_path_collection_length()

    for i, color_path in enumerate(self.color_paths):
        prop = color_paths(new_index)[i]
        color_path.index = i
        color_path.color = color_to_tuple(getattr(prop.struct, prop.key))

    if self.highlight_selected:
        set_color_group(new_index, self.highlight_color)

    last_index = new_index
    global last_property_index
    last_property_index = 0
    CanPushUndo = True


last_property_index = 0


def property_index_callback(self, context):
    global CanPushUndo
    CanPushUndo = False
    global last_property_index
    new_index = self.paths_index
    group_index = self.group_index
    highlight_color = self.highlight_color
    property_highlight_color = self.property_highlight_color
    if self.highlight_selected:
        set_color(color_paths(group_index)[
                  last_property_index], highlight_color)
        set_color(color_paths(group_index)[
                  new_index], property_highlight_color)
    last_property_index = new_index
    CanPushUndo = True


def highlight_selected_callback(self, context):
    theme_edit = self
    highlight = theme_edit.highlight_selected
    highlight_color = theme_edit.highlight_color
    property_highlight_color = theme_edit.property_highlight_color
    index = theme_edit.group_index
    property_index = theme_edit.paths_index

    if ordered_colors and index < len(ordered_colors):
        if highlight:
            set_color_group(index, highlight_color)
            prop = color_paths(index)[property_index]
            set_color(prop, property_highlight_color)
        else:
            for i, color_path in enumerate(theme_edit.color_paths):
                prop = color_paths(last_index)[i]
                set_color(prop, color_path.color)


def sort_terms_callback(self, context):
    sort_terms = context.window_manager.theme_edit.sort_terms
    sort_paths(sort_terms)


last_color = {
    "color": (0, 0, 0, 0),
    "count": 0
}


def set_last_color(color):
    if not hasattr(bpy.data, "palettes"):
        return
    # first run
    if "theme_edit" not in bpy.data.palettes:
        palette = bpy.data.palettes.new("theme_edit")
        bpy.context.window_manager.theme_edit.history_palette = palette
        for i in range(0, 20):
            palette.colors.new()

    global last_color
    last_color["color"] = color
    count = last_color["count"] + 1
    last_color["count"] = count

    global CanPushUndo
    local_push_undo = CanPushUndo

    def delayed_set_last_color():
        global last_color
        if count == last_color["count"]:
            palette = bpy.data.palettes["theme_edit"].colors
            for i in range(len(palette)-1, 0, -1):
                palette[i].color = palette[i - 1].color
            palette[0].color = last_color["color"][0:3]
            if local_push_undo:
                push_undo_step()

    bpy.app.timers.register(delayed_set_last_color, first_interval=0.5)


class ColorGroupProperties(bpy.types.PropertyGroup):
    def color_updated(self, context):
        if already_built == False:
            return
        color_tuple = color_to_tuple(self.color)
        colors[color_tuple] = color_paths(self.index)
        ordered_colors[self.index] = color_tuple
        theme_edit = context.window_manager.theme_edit

        set_color_group(self.index, self.color)
        set_last_color(self.color)

        if self.index == theme_edit.group_index:
            for path in theme_edit.color_paths:
                path.color = self.color

    color: bpy.props.FloatVectorProperty(
        name="Color", size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0, update=color_updated)
    index: bpy.props.IntProperty(name="Index")
    paths: bpy.props.StringProperty(name="Paths")


class ColorPathsPropertyGroup(bpy.types.PropertyGroup):
    def color_updated(self, context):
        group_index = context.window_manager.theme_edit.group_index
        prop = color_paths(group_index)[self.index]
        set_color(prop, self.color)
        set_last_color(self.color)

    color: bpy.props.FloatVectorProperty(
        name="Color", size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0, update=color_updated)
    index: bpy.props.IntProperty(name="Index")


class VIEW_3D_UL_color_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        color_key = ordered_colors[index]
        color = colors[color_key]
        layout.prop(item, 'color', text="")
        if len(color) > 1:
            layout.label(text=("("+str(len(color))+" properties)"))
        else:
            layout.label(text=("("+str(len(color))+" property)"))

    def draw_filter(self, context, layout):
        pass


class VIEW_3D_UL_path_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        color_index = context.window_manager.theme_edit.group_index
        color = color_paths(color_index)
        layout.label(text=(color[index].path))
        row = layout.row()
        row.alignment = 'RIGHT'
        row.prop(item, 'color', text="")

    def draw_filter(self, context, layout):
        pass


last_theme = None


class WM_OT_theme_edit_execute_preset(bpy.types.Operator):
    bl_idname = "script.theme_edit_execute_preset"
    bl_label = "Theme Edit Execute Preset"

    filepath: bpy.props.StringProperty(
        subtype='FILE_PATH', options={'SKIP_SAVE'})

    def execute(self, context):
        global last_theme
        last_theme = None
        bpy.ops.script.execute_preset(
            filepath=self.filepath, menu_idname="THEME_EDIT_MT_Presets")
        return {'FINISHED'}


class THEME_EDIT_MT_Presets(bpy.types.Menu):
    bl_label = "Presets"
    preset_subdir = "interface_theme"
    preset_operator = "script.theme_edit_execute_preset"
    preset_type = 'XML'
    preset_xml_map = (
        ("preferences.themes[0]", "Theme"),
        ("preferences.ui_styles[0]", "ThemeStyle"),
    )
    draw = bpy.types.Menu.draw_preset


class ThemeEditAddPresetInterfaceTheme(AddPresetBase, bpy.types.Operator):
    bl_idname = "wm.theme_edit_interface_theme_preset_add"
    bl_label = "Save Current Theme Preset As"
    bl_description = "Save a copy of the current theme with a new name"

    preset_menu = "THEME_EDIT_MT_Presets"
    preset_subdir = "interface_theme"


class WM_OT_theme_edit_open_preset_folder(bpy.types.Operator):
    bl_idname = "wm.theme_edit_open_preset_folder"
    bl_label = "Open Theme Presets Folder"
    bl_description = "Open the folder were your user themes are located"

    def execute(self, context):
        path = os.path.join("presets", "interface_theme")
        path = bpy.utils.user_resource('SCRIPTS', path=path, create=True)

        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

        return {'FINISHED'}


class VIEW_3D_PT_theme_editor(bpy.types.Panel):
    bl_label = "Theme Editor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        theme_edit = context.window_manager.theme_edit

        global last_theme
        current_theme = bpy.types.THEME_EDIT_MT_Presets.bl_label
        if last_theme != current_theme:
            last_theme = current_theme
            build_color_list()
            push_undo_step()

        row = layout.row(align=True)
        row.menu("THEME_EDIT_MT_Presets", text=current_theme)
        row.operator("wm.interface_theme_preset_save",
                     text="", icon='FILE_TICK')
        row.operator("wm.theme_edit_interface_theme_preset_add",
                     text="", icon='DUPLICATE')
        row.operator("wm.theme_edit_open_preset_folder",
                     text="", icon='FILE_FOLDER')

        button_text = "Rebuild Color List" if already_built else "Build Color List"
        layout.operator("wm.build_theme_colors", text=button_text)

        if colors is not None:
            layout.operator("wm.edit_theme_colors")
            layout.operator("wm.merge_similar_theme_colors")

            row = layout.row()
            row.operator("wm.theme_editor_undo", text="Undo")
            row.operator("wm.theme_editor_redo", text="Redo")

            layout.prop(theme_edit, "highlight_selected")
            if theme_edit.highlight_selected:
                row = layout.row()
                row.prop(theme_edit, "highlight_color", text="Group")
                row.prop(theme_edit, "property_highlight_color", text="Item")

            row = layout.row()
            row.prop(theme_edit, "filter_by_color")
            if theme_edit.filter_by_color:
                row.prop(theme_edit, "color_filter", text="")
                row = layout.row()
                row.prop(theme_edit, "color_filter_h", text="H")
                row.prop(theme_edit, "color_filter_s", text="S")
                row.prop(theme_edit, "color_filter_v", text="V")

            row = layout.row()
            row.prop(theme_edit, "filter_by_name")
            if theme_edit.filter_by_name:
                row.prop(theme_edit, "name_filter", text="")

            layout.template_list("VIEW_3D_UL_color_list", "",
                                 theme_edit, "color_groups", theme_edit, "group_index")
            layout.prop(theme_edit, "sort_type", text="")

            layout.template_list("VIEW_3D_UL_path_list", "", theme_edit, "color_paths",
                                 theme_edit, "paths_index")

            layout.prop(theme_edit, "sort_terms")

            if "theme_edit" in bpy.data.palettes:
                layout.label(text="Recent Colors:")
                # reassign in case the palette was already there before addon initialization
                theme_edit.history_palette = bpy.data.palettes['theme_edit']
                # if this is not the active palette inside the active paint mode + - doesn't work
                layout.template_palette(
                    theme_edit, "history_palette", color=True)
        else:
            box = layout.box()
            box.label("Please, build the color list", icon='ERROR')


class WM_OT_build_theme_colors(bpy.types.Operator):
    bl_idname = "wm.build_theme_colors"
    bl_label = "Build Theme Colors"
    bl_description = """Rebuilds the entire color groups list, putting matching colors in the same groups.
Useful when the you assign the same color to several groups or change individual properties"""

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager)

    def execute(self, context):
        build_color_list()
        return {'FINISHED'}


class WM_OT_edit_theme_colors(bpy.types.Operator):
    bl_idname = "wm.edit_theme_colors"
    bl_label = "Edit HSV + Contrast"
    bl_description = "Edit all colors at the same time, taking name and color filters into account"

    def run_implementation(self, context):
        theme_edit = context.window_manager.theme_edit
        for group in theme_edit.color_groups:
            color = mathutils.Color(group.color[0:3])
            color.h += self.hue * 0.5
            if color.s > 0:
                color.s += self.saturation * 0.5
            color.v += self.value * 0.5

            contrast_scalar = self.contrast + 1.0
            color.r = (color.r - 0.5) * contrast_scalar + 0.5
            color.g = (color.g - 0.5) * contrast_scalar + 0.5
            color.b = (color.b - 0.5) * contrast_scalar + 0.5

            set_color_group(
                group.index, (color.r, color.g, color.b, group.color[3]))

    hue: bpy.props.FloatProperty(
        name="Hue", min=-1, max=1, update=run_implementation)
    saturation: bpy.props.FloatProperty(
        name="Saturation", min=-1, max=1, update=run_implementation)
    value: bpy.props.FloatProperty(
        name="Value", min=-1, max=1, update=run_implementation)
    contrast: bpy.props.FloatProperty(
        name="Contrast", min=-1, max=1, update=run_implementation)

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager)

    def execute(self, context):
        self.run_implementation(context)
        build_color_list()
        push_undo_step()
        return {'FINISHED'}

    def invoke(self, context, event):
        self.hue = 0
        self.saturation = 0
        self.value = 0
        self.contrast = 0

        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def cancel(self, context):
        self.hue = 0
        self.saturation = 0
        self.value = 0
        self.contrast = 0
        self.run_implementation(context)


class WM_OT_merge_similar_theme_colors(bpy.types.Operator):
    bl_idname = "wm.merge_similar_theme_colors"
    bl_label = "Merge Similar Colors"
    bl_description = """Merge color groups below the specified tolerance threshold, taking name and color filters into account.
Merge priority is determined by list order, so if color groups are ordered by user count, 
the ones with lower user counts are merged into the ones with higher user counts"""

    def run_implementation(self, context):
        theme_edit = context.window_manager.theme_edit
        self.merged_groups = 0
        for i, group in reversed(list(enumerate(theme_edit.color_groups))):
            hsv1 = mathutils.Color(group.color[0:3])
            merged = False
            for i2, group2 in enumerate(theme_edit.color_groups):
                # if i == i2:
                #    continue
                hsv2 = mathutils.Color(group2.color[0:3])
                match = True
                if (math.isclose(hsv1.h, hsv2.h, abs_tol=self.h) == False or
                    math.isclose(hsv1.s, hsv2.s, abs_tol=self.s) == False or
                    math.isclose(hsv1.v, hsv2.v, abs_tol=self.v) == False or
                        math.isclose(group.color[3], group2.color[3], abs_tol=self.a) == False):
                    match = False
                    continue
                if match:
                    if i != i2:
                        merged = True
                    if self.only_name_matches and merged:
                        merged = False
                        for prop1 in color_paths(group.index):
                            for prop2 in color_paths(group2.index):
                                if prop1.key == prop2.key:
                                    if prop1.path.split('::')[1:] == prop2.path.split('::')[1:]:
                                        merged = True
                                        set_color(prop2, group.color)
                    else:
                        set_color_group(group2.index, group.color)
            if merged:
                self.merged_groups += 1

    # tolerance : bpy.props.FloatProperty(name="Tolerance", default=0.015, update=run_implementation)
    only_name_matches: bpy.props.BoolProperty(name="Only Name Matches",
                                              description="Only merge color properties that has a matching property name in the merged color group", default=False, update=run_implementation)
    h: bpy.props.FloatProperty(name="Hue", description="Hue Tolerance",
                               default=0.015, min=0.0015, max=1.0, update=run_implementation)
    s: bpy.props.FloatProperty(name="Saturation", description="Saturation Tolerance",
                               default=0.015, min=0.0015, max=1.0, update=run_implementation)
    v: bpy.props.FloatProperty(name="Value", description="Value Tolerance",
                               default=0.015, min=0.0015, max=1.0, update=run_implementation)
    a: bpy.props.FloatProperty(name="Alpha", description="Alpha Tolerance",
                               default=0.015, min=0.0015, max=1.0, update=run_implementation)
    merged_groups: bpy.props.IntProperty(name="Merged Groups", default=0)

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager)

    def execute(self, context):
        self.run_implementation(context)
        build_color_list()
        push_undo_step()
        return {'FINISHED'}

    def invoke(self, context, event):
        self.merged_groups = 0
        self.run_implementation(context)
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def cancel(self, context):
        self.only_name_matches = False
        self.h = 0
        self.s = 0
        self.v = 0
        self.a = 0
        self.run_implementation(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'h', text="H")
        layout.prop(self, 's', text="S")
        layout.prop(self, 'v', text="V")
        layout.prop(self, 'a', text="A")
        layout.prop(self, 'only_name_matches')
        layout.label(text=str(self.merged_groups) + " group(s) will be merged")


class ThemeEditPropertyGroup(bpy.types.PropertyGroup):
    filter_by_color: bpy.props.BoolProperty(name="Filter by Color",
                                            description="Filter the color list by property color", update=build_color_list_callback)

    color_filter: bpy.props.FloatVectorProperty(name="Color Filter",
                                                size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0, update=build_color_list_callback)

    color_filter_h: bpy.props.FloatProperty(name="Hue", description="Hue Tolerance",
                                            default=0.0015, min=0.0015, max=1.0, update=build_color_list_callback)

    color_filter_s: bpy.props.FloatProperty(name="Saturation", description="Saturation Tolerance",
                                            default=0.0015, min=0.0015, max=1.0, update=build_color_list_callback)

    color_filter_v: bpy.props.FloatProperty(name="Value", description="Value Tolerance",
                                            default=0.0015, min=0.0015, max=1.0, update=build_color_list_callback)

    filter_by_name: bpy.props.BoolProperty(name="Filter by Name",
                                           description="Filter the color list by property name", update=build_color_list_callback)

    name_filter: bpy.props.StringProperty(name='Name Filter',
                                          description="""Separate search tearms by commas, 
precede optional search terms by '?' and filtered out search terms by '-'. 
Letter case is ignored.
Example: theme space, ? text, ? title, -highlight""",
                                          update=build_color_list_callback)

    highlight_selected: bpy.props.BoolProperty(name="Highlight Selected",
                                               description="Highlight the currently selected list items", update=highlight_selected_callback)

    highlight_color: bpy.props.FloatVectorProperty(name="Group Highlight Color",
                                                   size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0, update=highlight_selected_callback, default=(1, 0, 1, 1))

    property_highlight_color: bpy.props.FloatVectorProperty(name="Property Highlight Color",
                                                            size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0, update=highlight_selected_callback, default=(1, 1, 0, 1))

    sort_type: bpy.props.EnumProperty(items=(('USERS', 'Sort color groups by user count', 'Sort color groups by user count'),
                                             ('COLOR', 'Sort color groups by color', 'Sort color groups by color')), default='USERS',
                                      name="Sort color groups by", update=build_color_list_callback)

    color_groups: bpy.props.CollectionProperty(type=ColorGroupProperties)
    group_index: bpy.props.IntProperty(
        name="Group Index", update=group_index_callback)
    color_paths: bpy.props.CollectionProperty(type=ColorPathsPropertyGroup)
    paths_index: bpy.props.IntProperty(
        default=0, update=property_index_callback)

    sort_terms: bpy.props.StringProperty(name='Sort Paths by',
                                         description="Show first on the path list the properties that matches this search terms",
                                         update=sort_terms_callback)

    history_palette: bpy.props.PointerProperty(type=bpy.types.Palette)


classes = [
    WM_OT_theme_editor_undo,
    WM_OT_theme_editor_redo,
    ColorGroupProperties,
    VIEW_3D_UL_color_list,
    VIEW_3D_UL_path_list,
    VIEW_3D_PT_theme_editor,
    WM_OT_build_theme_colors,
    WM_OT_edit_theme_colors,
    WM_OT_merge_similar_theme_colors,
    ColorPathsPropertyGroup,
    ThemeEditPropertyGroup,
    WM_OT_theme_edit_execute_preset,
    WM_OT_theme_edit_open_preset_folder,
    THEME_EDIT_MT_Presets,
    ThemeEditAddPresetInterfaceTheme
]


def register():
    for _class in classes:
        bpy.utils.register_class(_class)

    bpy.types.WindowManager.theme_edit = bpy.props.PointerProperty(
        type=ThemeEditPropertyGroup)

    build_color_list()


def unregister():
    for _class in classes:
        bpy.utils.unregister_class(_class)

    del bpy.types.WindowManager.theme_edit


if __name__ == "__main__":
    register()

"""
IFC Quick Select Blender Addon

This addon is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 2 of the License, or
 (at your option) any later version.

This addon is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

---

This addon uses IfcOpenShell (LGPL) as a dependency. See: https://ifcopenshell.org/
The IFC unit detection helpers are open-source (MIT/LGPL) for compliance.

"""

bl_info = {
    "name": "ifcqselect",
    "blender": (2, 80, 0),
    "category": "Object",
    "version": (1, 0, 0),
}

import bpy
import re
import os
import traceback
import bmesh
import mathutils
import ifcopenshell
import hashlib
import shutil

# --- Open-source (MIT/LGPL) helper functions for robust IFC unit detection ---
# These functions use the IfcOpenShell API and are open-source for compliance.
try:
    import ifcopenshell.util.unit
    IFCOPENSHELL_AVAILABLE = True
except ImportError:
    IFCOPENSHELL_AVAILABLE = False

def open_ifc_file(ifc_path):
    """
    Open an IFC file and return the IfcOpenShell file object.
    """
    return ifcopenshell.open(ifc_path)

def get_ifc_units(ifc_file):
    """
    Get the project's default units for length, area, and volume.
    Returns a dict: { 'length': unit_entity, 'area': unit_entity, 'volume': unit_entity }
    """
    units = {}
    for unit_type, key in [("LENGTHUNIT", "length"), ("AREAUNIT", "area"), ("VOLUMEUNIT", "volume")]:
        unit = ifcopenshell.util.unit.get_project_unit(ifc_file, unit_type)
        units[key] = unit
    return units

def get_ifc_unit_scales(ifc_file):
    """
    Get the scale factors to convert project units to SI units (meters, square meters, cubic meters).
    Returns a dict: { 'length': scale, 'area': scale, 'volume': scale }
    """
    scales = {}
    for unit_type, key in [("LENGTHUNIT", "length"), ("AREAUNIT", "area"), ("VOLUMEUNIT", "volume")]:
        scale = ifcopenshell.util.unit.calculate_unit_scale(ifc_file, unit_type)
        scales[key] = scale
    return scales
# --- End open-source helper section ---

# ... existing code from ifc_quick_select.py, but:
# - Remove import ifc_units_detect
# - Replace all uses of ifc_units_detect.open_ifc_file, get_ifc_units, get_ifc_unit_scales with the above functions
# - All other logic remains proprietary and unchanged

# List all Blender object types (static for EnumProperty registration)
OBJECT_TYPES = [
    ("MESH", "Mesh", ""),
    ("CURVE", "Curve", ""),
    ("LIGHT", "Light", ""),
    ("CAMERA", "Camera", ""),
    ("EMPTY", "Empty", ""),
    ("SURFACE", "Surface", ""),
    ("META", "Meta", ""),
    ("FONT", "Font", ""),
    ("ARMATURE", "Armature", ""),
    ("LATTICE", "Lattice", ""),
    ("SPEAKER", "Speaker", ""),
    ("LIGHT_PROBE", "Light Probe", "")
]

# Quantities for geometry/BIM
IFC_BASE_QUANTITIES = [
    ("GrossArea", "Gross Area", ""),
    ("NetArea", "Net Area", ""),
    ("GrossVolume", "Gross Volume", ""),
    ("NetVolume", "Net Volume", ""),
    ("Length", "Length", ""),
    ("Width", "Width", ""),
    ("Height", "Height", ""),
    ("Depth", "Depth", ""),
    ("Perimeter", "Perimeter", ""),
    ("GrossFootprintArea", "Gross Footprint Area", ""),
    ("NetSideArea", "Net Side Area", ""),
    ("CrossSectionArea", "Cross Section Area", ""),
    ("OuterSurfaceArea", "Outer Surface Area", ""),
    ("Thickness", "Thickness", ""),
]

QUANTITY_SETS = [
    "IFC4 Base Quantities - Blender",
    "IFC4 Base Quantities - Ifcopenshell",
    "Qto_SlabBaseQuantities"
]

UNIT_SYSTEMS = [
    ("AUTO", "Auto (Detect from IFC/Blender)", ""),
    ("SI", "SI (Metric)", ""),
    ("IMPERIAL_US", "Imperial (US)", ""),
    ("IMPERIAL_UK", "Imperial (UK)", ""),
    ("CGS", "CGS (cm, g, s)", ""),
    ("MKS", "MKS (m, kg, s)", ""),
    ("CUSTOM", "Custom", "")
]

UNIT_MAP = {
    "SI": {"length": "m", "area": "m²", "volume": "m³"},
    "IMPERIAL_US": {"length": "ft", "area": "ft²", "volume": "ft³"},
    "IMPERIAL_UK": {"length": "ft", "area": "ft²", "volume": "ft³"},
    "CGS": {"length": "cm", "area": "cm²", "volume": "cm³"},
    "MKS": {"length": "m", "area": "m²", "volume": "m³"},
}

DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "ifc_quick_select_debug.log")

def log_debug_info(message):
    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(message + "\n")

def log_detected_units():
    ifc_units = get_ifc_project_units()
    blender_units = get_blender_scene_units()
    log_debug_info(f"Detected IFC units: {ifc_units}")
    log_debug_info(f"Detected Blender scene units: {blender_units}")

class IFCQSelectProps(bpy.types.PropertyGroup):
    get_data_from_ifcopenshell: bpy.props.BoolProperty(
        name="Get data from IFC_OpenShell",
        description="If enabled, parse all data from IFC_OpenShell (recommended)",
        default=True
    )
    object_type: bpy.props.EnumProperty(
        name="Object Type",
        items=OBJECT_TYPES,
        default="MESH"
    )
    name_filter: bpy.props.StringProperty(name="Name contains...", default="")
    parameter: bpy.props.EnumProperty(
        name="Parameter",
        items=IFC_BASE_QUANTITIES,
        default="GrossArea"
    )
    value_number_min: bpy.props.FloatProperty(name="Min Value", default=0.0)
    value_number_max: bpy.props.FloatProperty(name="Max Value", default=10000.0)
    value_material: bpy.props.StringProperty(name="Material Name", default="")
    detected_units: bpy.props.StringProperty(name="Detected Units", default="meters")
    unit_system: bpy.props.EnumProperty(
        name="Unit System",
        items=UNIT_SYSTEMS,
        default="AUTO"
    )
    custom_length_unit: bpy.props.StringProperty(name="Custom Length Unit", default="m")
    custom_area_unit: bpy.props.StringProperty(name="Custom Area Unit", default="m²")
    custom_volume_unit: bpy.props.StringProperty(name="Custom Volume Unit", default="m³")
    ifc_file_path: bpy.props.StringProperty(
        name="IFC File Path", subtype='FILE_PATH', default=""
    )
    strict_bim: bpy.props.BoolProperty(
        name="Strict BIM Properties",
        description="Only use BIM (IFC) properties for selection. No geometry fallback.",
        default=True
    )
    allow_bim_fallback: bpy.props.BoolProperty(
        name="Allow BIMProperties Fallback",
        description="If no IFC match, try BIMProperties for selection.",
        default=True
    )
    allow_geom_fallback: bpy.props.BoolProperty(
        name="Allow Geometry Fallback",
        description="If no IFC or BIMProperties match, use geometry (dimensions) for selection.",
        default=True
    )
    select_quantity_type: bpy.props.EnumProperty(
        name="Quantity Type",
        items=IFC_BASE_QUANTITIES,
        default="GrossArea"
    )
    select_value_min: bpy.props.FloatProperty(name="Min Value", default=0.0)
    select_value_max: bpy.props.FloatProperty(name="Max Value", default=10000.0)
    name_contains: bpy.props.StringProperty(name="Name Contains", default="")

def get_blender_scene_units():
    scene = bpy.context.scene
    us = scene.unit_settings
    if us.system == 'IMPERIAL':
        if us.length_unit == 'FEET':
            return 'ft'
        elif us.length_unit == 'INCHES':
            return 'in'
        else:
            return 'imperial'
    return 'meters'

def get_ifc_file_path():
    try:
        from bonsai.bim.ifc import IfcStore
        if hasattr(IfcStore, "get_file") and hasattr(IfcStore, "path"):
            return IfcStore.path
    except Exception:
        pass
    return None

def get_ifc_project_units(force_fallback=False):
    props = bpy.context.scene.ifcqselect_props if hasattr(bpy.context.scene, 'ifcqselect_props') else None
    use_ifcopenshell = getattr(props, 'get_data_from_ifcopenshell', True) if props else True
    if not force_fallback and use_ifcopenshell and IFCOPENSHELL_AVAILABLE:
        ifc_path = get_ifc_file_path()
        if ifc_path and os.path.exists(ifc_path):
            try:
                ifc_file = open_ifc_file(ifc_path)
                units = get_ifc_units(ifc_file)
                scales = get_ifc_unit_scales(ifc_file)
                log_debug_info(f"[OpenSource] IFC file: {ifc_path}")
                log_debug_info(f"[OpenSource] IFC units: {units}")
                log_debug_info(f"[OpenSource] IFC unit scales: {scales}")
                summary = {k: str(units[k]) for k in units}
                return summary
            except Exception as e:
                log_debug_info(f"[OpenSource] IFC unit detection error: {e}")
    for obj in bpy.data.objects:
        if hasattr(obj, "BIMProperties"):
            if "IfcProject" in getattr(obj, "BIMProperties", {}):
                for k, v in obj.BIMProperties.items():
                    if isinstance(v, dict):
                        for subk, subv in v.items():
                            if "unit" in subk.lower() and isinstance(subv, str):
                                if "meter" in subv.lower():
                                    return "meters"
                                elif "millimeter" in subv.lower():
                                    return "mm"
                                elif "foot" in subv.lower():
                                    return "ft"
                                elif "inch" in subv.lower():
                                    return "in"
                return "meters"
    return None

# --- Helper: Parse IFC file for entity relationships, properties, and GlobalId ---
def parse_ifc_entities_and_quantities(ifc_path, debug=False):
    entities = {}
    rels = {}
    quantities = {}
    globalid_to_eid = {}
    try:
        with open(ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Parse IFCSLAB and other entities with GlobalId
                m = re.match(r'#(\d+)=IFCSLAB\(\'([^\']+)\',\$,' + r"'([\w_]+)'", line)
                if m:
                    eid, globalid, name = m.groups()
                    entities[eid] = {'globalid': globalid, 'name': name}
                    globalid_to_eid[globalid] = eid
                # Parse IFCELEMENTQUANTITY
                m = re.match(r'#(\d+)=IFCELEMENTQUANTITY\([^,]+,[^,]+,' + r"'([\w_]+)'", line)
                if m:
                    qid, qset = m.groups()
                    quantities[qid] = {'qset': qset, 'quantities': []}
                # Parse IFCQUANTITYAREA and IFCQUANTITYVOLUME
                m = re.match(r'#(\d+)=IFCQUANTITY(AREA|VOLUME)\(' + r"'([\w_]+)'" + r',\$\$,([\d\.Ee\+-]+),', line)
                if m:
                    qid, qtype, qname, qval = m.groups()
                    quantities[qid] = {'type': qtype, 'name': qname, 'value': float(qval)}
                # Parse IFCRELDEFINESBYPROPERTIES
                m = re.match(r'#(\d+)=IFCRELDEFINESBYPROPERTIES\([^,]+,[^,]+,[^,]+,[^,]+,\((#[\d,]+)\),#(\d+)\);', line)
                if m:
                    rid, ent_ids, qid = m.groups()
                    ent_ids = [x.replace('#','') for x in ent_ids.split(',')]
                    for eid in ent_ids:
                        rels[eid] = qid
        if debug:
            log_debug_info(f"[IFC PARSE] Entities: {entities}")
            log_debug_info(f"[IFC PARSE] Relationships: {rels}")
            log_debug_info(f"[IFC PARSE] Quantities: {quantities}")
            log_debug_info(f"[IFC PARSE] GlobalId to EID: {globalid_to_eid}")
    except Exception as e:
        if debug:
            log_debug_info(f"[IFC PARSE ERROR] {e}\n{traceback.format_exc()}")
    return entities, rels, quantities, globalid_to_eid

# --- Robust IFC Unit Detection using IfcOpenShell ---
def detect_ifc_units(ifc_path, debug=False):
    units = {'length': 'm', 'area': 'm²', 'volume': 'm³'}
    scales = {'length': 1.0, 'area': 1.0, 'volume': 1.0}
    try:
        if IFCOPENSHELL_AVAILABLE:
            ifc_file = ifcopenshell.open(ifc_path)
            for unit_type, key in [("LENGTHUNIT", "length"), ("AREAUNIT", "area"), ("VOLUMEUNIT", "volume")]:
                u = ifcopenshell.util.unit.get_project_unit(ifc_file, unit_type)
                s = ifcopenshell.util.unit.calculate_unit_scale(ifc_file, unit_type)
                if u:
                    units[key] = u.get_info().get('UnitType', u.get_info().get('Name', ''))
                scales[key] = s
            if debug:
                log_debug_info(f"[IfcOpenShell] Detected units: {units}")
                log_debug_info(f"[IfcOpenShell] Detected scales: {scales}")
        else:
            if debug:
                log_debug_info("[IfcOpenShell] Not available, using fallback units.")
    except Exception as e:
        if debug:
            log_debug_info(f"[IfcOpenShell] Unit detection error: {e}\n{traceback.format_exc()}")
    return units, scales

# --- Replace select_matching_objects with a robust, mesh-focused version ---
def select_matching_objects(context, props, entities, rels, quantities, globalid_to_eid, units, scales, log=True, do_select=True):
    selected_count = 0
    param = props.parameter.lower().replace('_', '').replace(' ', '')
    name_filter = props.name_filter.lower().strip()
    material_filter = props.value_material.lower().strip() if hasattr(props, 'value_material') else ''
    warning_shown = False
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            if do_select:
                obj.select_set(False)
            continue
        if name_filter and name_filter not in obj.name.lower():
            if do_select:
                obj.select_set(False)
            continue
        selected = False
        value = None
        values = []
        # --- 1. Area/Volume integration logic ---
        def get_all_area_values(obj):
            vals = []
            # ManualSurfaceArea
            try:
                if hasattr(obj, 'BIMProperties') and 'ManualSurfaceArea' in obj.BIMProperties:
                    vals.append(('ManualSurfaceArea', float(obj.BIMProperties['ManualSurfaceArea'])))
            except Exception:
                pass
            if 'ManualSurfaceArea' in obj:
                try:
                    vals.append(('ManualSurfaceArea', float(obj['ManualSurfaceArea'])))
                except Exception:
                    pass
            # GrossArea
            try:
                if hasattr(obj, 'BIMProperties') and 'GrossArea' in obj.BIMProperties:
                    vals.append(('GrossArea', float(obj.BIMProperties['GrossArea'])))
            except Exception:
                pass
            if 'GrossArea' in obj:
                try:
                    vals.append(('GrossArea', float(obj['GrossArea'])))
                except Exception:
                    pass
            # NetArea
            try:
                if hasattr(obj, 'BIMProperties') and 'NetArea' in obj.BIMProperties:
                    vals.append(('NetArea', float(obj.BIMProperties['NetArea'])))
            except Exception:
                pass
            if 'NetArea' in obj:
                try:
                    vals.append(('NetArea', float(obj['NetArea'])))
                except Exception:
                    pass
            # Geometry fallback
            dims = obj.dimensions
            geom_area = dims[0] * dims[1]
            vals.append(('Geometry', geom_area))
            return vals
        def get_all_volume_values(obj):
            vals = []
            # ManualVolume
            try:
                if hasattr(obj, 'BIMProperties') and 'ManualVolume' in obj.BIMProperties:
                    vals.append(('ManualVolume', float(obj.BIMProperties['ManualVolume'])))
            except Exception:
                pass
            if 'ManualVolume' in obj:
                try:
                    vals.append(('ManualVolume', float(obj['ManualVolume'])))
                except Exception:
                    pass
            # GrossVolume
            try:
                if hasattr(obj, 'BIMProperties') and 'GrossVolume' in obj.BIMProperties:
                    vals.append(('GrossVolume', float(obj.BIMProperties['GrossVolume'])))
            except Exception:
                pass
            if 'GrossVolume' in obj:
                try:
                    vals.append(('GrossVolume', float(obj['GrossVolume'])))
                except Exception:
                    pass
            # NetVolume
            try:
                if hasattr(obj, 'BIMProperties') and 'NetVolume' in obj.BIMProperties:
                    vals.append(('NetVolume', float(obj.BIMProperties['NetVolume'])))
            except Exception:
                pass
            if 'NetVolume' in obj:
                try:
                    vals.append(('NetVolume', float(obj['NetVolume'])))
                except Exception:
                    pass
            # Geometry fallback
            dims = obj.dimensions
            geom_volume = dims[0] * dims[1] * dims[2]
            vals.append(('Geometry', geom_volume))
            return vals
        # --- 2. Main selection logic ---
        if param == 'area':
            values = get_all_area_values(obj)
            # Check for value differences and warn
            if values:
                unique_vals = set(round(v[1], 6) for v in values)
                if len(unique_vals) > 1 and not warning_shown:
                    msg = f"Warning: Multiple area values found for object '{obj.name}': " + ", ".join(f"{n}={v}" for n, v in values)
                    if hasattr(bpy.context, 'window_manager'):
                        bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=msg), title="Area Mismatch", icon='ERROR')
                    warning_shown = True
            if values:
                value = values[0][1]
        elif param == 'volume':
            values = get_all_volume_values(obj)
            if values:
                unique_vals = set(round(v[1], 6) for v in values)
                if len(unique_vals) > 1 and not warning_shown:
                    msg = f"Warning: Multiple volume values found for object '{obj.name}': " + ", ".join(f"{n}={v}" for n, v in values)
                    if hasattr(bpy.context, 'window_manager'):
                        bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=msg), title="Volume Mismatch", icon='ERROR')
                    warning_shown = True
            if values:
                value = values[0][1]
        else:
            # Use original direct-matching logic for other parameters
            def get_bim_value(obj, param):
                # Try GlobalId-based lookup (if available)
                globalid = obj.get('IfcGlobalId') or obj.get('GlobalId')
                if globalid and globalid in globalid_to_eid:
                    eid = globalid_to_eid[globalid]
                    if eid in rels:
                        qid = rels[eid]
                        for qref in re.findall(r'#(\d+)', qid):
                            q = quantities.get(qref)
                            if q and q.get('name', '').replace('_', '').replace(' ', '').lower() == param:
                                return q.get('value')
                # Try BIMProperties sets
                if "BIMProperties" in obj:
                    for qset in QUANTITY_SETS:
                        pset = obj["BIMProperties"].get(qset)
                        if pset:
                            for key, val in pset.items():
                                if key.replace('_', '').replace(' ', '').lower() == param:
                                    try:
                                        return float(val)
                                    except Exception:
                                        continue
                return None
            value = get_bim_value(obj, param)
            # Fallback to geometry if no BIM value
            if value is None:
                dims = obj.dimensions
                if param in ['length', 'netlength', 'grosslength']:
                    value = max(dims)
                elif param in ['width', 'thickness', 'netwidth', 'grossthickness', 'netthickness', 'grosswidth']:
                    value = min(dims)
                elif param in ['height', 'depth', 'netheight', 'grossheight']:
                    value = sorted(dims)[1]  # middle value
                elif param in ['perimeter']:
                    value = 2 * (dims[0] + dims[1])
                elif param in ['crosssectionarea', 'outersurfacearea']:
                    value = dims[0] * dims[1]
        # Selection by value range
        if value is not None:
            if props.value_number_min <= value <= props.value_number_max:
                selected = True
        if selected:
            if do_select:
                obj.select_set(True)
            selected_count += 1
        else:
            if do_select:
                obj.select_set(False)
    return selected_count

# --- Update Selection Logic to Use GlobalId Matching ---
class OBJECT_OT_ifcqselect(bpy.types.Operator):
    bl_idname = "object.ifcqselect"
    bl_label = "IFC Quick Select Operator"
    def execute(self, context):
        props = context.scene.ifcqselect_props
        debug = True
        entities, rels, quantities, globalid_to_eid = {}, {}, {}, {}
        units, scales = {'length': 'm', 'area': 'm²', 'volume': 'm³'}, {'length': 1.0, 'area': 1.0, 'volume': 1.0}
        if props.ifc_file_path:
            units, scales = detect_ifc_units(props.ifc_file_path, debug=debug)
            entities, rels, quantities, globalid_to_eid = parse_ifc_entities_and_quantities(props.ifc_file_path, debug=debug)
        selected_count = select_matching_objects(context, props, entities, rels, quantities, globalid_to_eid, units, scales, log=True, do_select=True)
        self.report({'INFO'}, f"Selection complete. {selected_count} objects selected. See debug log for details.")
        return {'FINISHED'}

class IFCQSelectPanel(bpy.types.Panel):
    bl_label = "IFC Quick Select"
    bl_idname = "VIEW3D_PT_ifcqselect"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'IFC Quick Select'
    def draw(self, context):
        layout = self.layout
        props = context.scene.ifcqselect_props
        layout.label(text="Select Meshes by:")
        layout.prop(props, "name_filter")
        layout.prop(props, "parameter")
        if props.parameter == "Material":
            layout.prop(props, "value_material")
        else:
            layout.prop(props, "value_number_min")
            layout.prop(props, "value_number_max")
        layout.operator("object.ifcqselect", text="Quick Select")
        layout.separator()
        layout.label(text="(IFC/BIM or geometry fallback)")

class OBJECT_OT_ifcqselect_debug(bpy.types.Operator):
    bl_idname = "object.ifcqselect_debug"
    bl_label = "Debug IFC Quick Select"
    bl_description = "Run selection logic and log all actions/results to a debug log file"
    def execute(self, context):
        props = context.scene.ifcqselect_props
        with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("--- IFC Quick Select Debug Log ---\n")
        log_detected_units()
        log_debug_info(f"Parameter: {props.parameter}")
        log_debug_info(f"Min: {props.value_number_min}, Max: {props.value_number_max}")
        log_debug_info(f"Unit System: {props.unit_system}")
        log_debug_info(f"Object Type: {props.object_type}")
        log_debug_info(f"Name Filter: {props.name_filter}")
        log_debug_info(f"Material Filter: {props.value_material}")
        logged = 0
        for obj in bpy.data.objects:
            if hasattr(obj, "BIMProperties") and logged < 10:
                log_debug_info(f"\n[DEBUG] BIMProperties for {obj.name}:")
                for qset, pset in obj.BIMProperties.items():
                    log_debug_info(f"  {qset}:")
                    if isinstance(pset, dict):
                        for k, v in pset.items():
                            log_debug_info(f"    {k}: {v}")
                logged += 1
        selected_count = select_matching_objects(context, props, {}, {}, {}, {}, {}, {}, log=True, do_select=True)
        self.report({'INFO'}, f"Debug log written. {selected_count} objects selected.")
        return {'FINISHED'}

class OBJECT_OT_ifcqselect_clearlog(bpy.types.Operator):
    bl_idname = "object.ifcqselect_clearlog"
    bl_label = "Clear IFC Quick Select Debug Log"
    bl_description = "Clear the debug log file for IFC Quick Select"
    def execute(self, context):
        with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
        self.report({'INFO'}, "Debug log cleared.")
        return {'FINISHED'}

class OBJECT_OT_save_selected_face_area(bpy.types.Operator):
    bl_idname = "object.save_selected_face_area"
    bl_label = "Save Selected Face Area to BIM Properties"
    bl_description = "Calculate the area of selected faces and save to BIMProperties['ManualSurfaceArea']"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh.")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Must be in Edit Mode with faces selected.")
            return {'CANCELLED'}
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        area = sum(f.calc_area() for f in bm.faces if f.select)
        # Detect units
        _, unit = get_selected_faces_area_and_unit(context)
        # Store in BIMProperties
        if not hasattr(obj, 'BIMProperties'):
            obj["BIMProperties"] = {}
        try:
            bimprops = obj.BIMProperties
            bimprops['ManualSurfaceArea'] = area
            bimprops['ManualSurfaceAreaUnit'] = unit
        except Exception:
            obj["ManualSurfaceArea"] = area
            obj["ManualSurfaceAreaUnit"] = unit
        self.report({'INFO'}, f"Saved area: {area:.4f} {unit} to BIMProperties['ManualSurfaceArea']")
        return {'FINISHED'}

# --- Helper to get area and units for selected faces ---
def get_selected_faces_area_and_unit(context):
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or context.mode != 'EDIT_MESH':
        return 0.0, 'm²'
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    area = sum(f.calc_area() for f in bm.faces if f.select)
    # Prefer IFC units if available
    unit = None
    if hasattr(obj, 'BIMProperties') and 'IfcUnit' in obj.BIMProperties and obj.BIMProperties['IfcUnit']:
        unit = str(obj.BIMProperties['IfcUnit'])
    if not unit or unit.lower() in ('', 'none', 'unknown'):
        # Fallback to Blender scene units
        try:
            scene = context.scene
            us = scene.unit_settings
            if us.system == 'IMPERIAL':
                if us.length_unit == 'FEET':
                    unit = 'ft²'
                elif us.length_unit == 'INCHES':
                    unit = 'in²'
                else:
                    unit = 'imperial'
            elif us.system == 'METRIC':
                if us.length_unit == 'MILLIMETERS':
                    unit = 'mm²'
                elif us.length_unit == 'CENTIMETERS':
                    unit = 'cm²'
                elif us.length_unit == 'METERS':
                    unit = 'm²'
                else:
                    unit = 'm²'
            else:
                unit = 'm²'
        except Exception:
            unit = 'm²'
    return area, unit

# --- Helper to get object volume and units ---
def get_object_volume_and_unit(context):
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or context.mode != 'OBJECT':
        return 0.0, 'm³'
    import bmesh
    mesh = obj.to_mesh()
    mesh.transform(obj.matrix_world)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    volume = bm.calc_volume(signed=False)
    bm.free()
    obj.to_mesh_clear()
    # Prefer IFC units for volume if available
    unit = None
    if hasattr(obj, 'BIMProperties') and 'IfcUnit' in obj.BIMProperties and obj.BIMProperties['IfcUnit']:
        # Try to infer volume unit from IFC unit (e.g., m³ if m, ft³ if ft)
        ifc_unit = str(obj.BIMProperties['IfcUnit'])
        if ifc_unit == 'm':
            unit = 'm³'
        elif ifc_unit == 'ft':
            unit = 'ft³'
        elif ifc_unit == 'cm':
            unit = 'cm³'
        elif ifc_unit == 'mm':
            unit = 'mm³'
        else:
            unit = ifc_unit + '³'
    if not unit or unit.lower() in ('', 'none', 'unknown'):
        # Fallback to Blender scene units
        try:
            scene = context.scene
            us = scene.unit_settings
            if us.system == 'IMPERIAL':
                if us.length_unit == 'FEET':
                    unit = 'ft³'
                elif us.length_unit == 'INCHES':
                    unit = 'in³'
                else:
                    unit = 'imperial'
            elif us.system == 'METRIC':
                if us.length_unit == 'MILLIMETERS':
                    unit = 'mm³'
                elif us.length_unit == 'CENTIMETERS':
                    unit = 'cm³'
                elif us.length_unit == 'METERS':
                    unit = 'm³'
                else:
                    unit = 'm³'
            else:
                unit = 'm³'
        except Exception:
            unit = 'm³'
    return volume, unit

# --- Operator to save object volume ---
class OBJECT_OT_save_object_volume(bpy.types.Operator):
    bl_idname = "object.save_object_volume"
    bl_label = "Save Object Volume to BIM Properties"
    bl_description = "Calculate the object's mesh volume and save to BIMProperties['ManualVolume']"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or context.mode != 'OBJECT':
            self.report({'ERROR'}, "Active object must be a mesh in Object Mode.")
            return {'CANCELLED'}
        volume, unit = get_object_volume_and_unit(context)
        if not hasattr(obj, 'BIMProperties'):
            obj["BIMProperties"] = {}
        try:
            bimprops = obj.BIMProperties
            bimprops['ManualVolume'] = volume
            bimprops['ManualVolumeUnit'] = unit
        except Exception:
            obj["ManualVolume"] = volume
            obj["ManualVolumeUnit"] = unit
        self.report({'INFO'}, f"Saved volume: {volume:.4f} {unit} to BIMProperties['ManualVolume']")
        return {'FINISHED'}

# --- Helper to get object area from IFC/BIM properties or fallback to geometry ---
def get_object_area_and_unit(context):
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or context.mode != 'OBJECT':
        return 0.0, 'm²'
    # Try to get area from BIMProperties (prefer ManualSurfaceArea first)
    area = None
    unit = None
    area_keys = ['ManualSurfaceArea', 'GrossArea', 'NetArea', 'Area']
    if "BIMProperties" in obj:
        for key in area_keys:
            if key in obj["BIMProperties"]:
                try:
                    area = float(obj["BIMProperties"][key])
                    unit = obj["BIMProperties"].get(f'{key}Unit', None)
                    break
                except Exception:
                    pass
    # Fallback to geometry
    if area is None:
        dims = obj.dimensions
        area = dims[0] * dims[1]
    # Unit fallback logic
    if not unit or unit.lower() in ('', 'none', 'unknown'):
        try:
            scene = context.scene
            us = scene.unit_settings
            if us.system == 'IMPERIAL':
                if us.length_unit == 'FEET':
                    unit = 'ft²'
                elif us.length_unit == 'INCHES':
                    unit = 'in²'
                else:
                    unit = 'imperial'
            elif us.system == 'METRIC':
                if us.length_unit == 'MILLIMETERS':
                    unit = 'mm²'
                elif us.length_unit == 'CENTIMETERS':
                    unit = 'cm²'
                elif us.length_unit == 'METERS':
                    unit = 'm²'
                else:
                    unit = 'm²'
            else:
                unit = 'm²'
        except Exception:
            unit = 'm²'
    return area, unit

# --- Operator to save IFC area to BIM Properties ---
class OBJECT_OT_save_object_ifc_area(bpy.types.Operator):
    bl_idname = "object.save_object_ifc_area"
    bl_label = "Save IFC Area to BIM Properties"
    bl_description = "Save the object's IFC/BIM area to BIMProperties['ManualSurfaceArea']"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or context.mode != 'OBJECT':
            self.report({'ERROR'}, "Active object must be a mesh in Object Mode.")
            return {'CANCELLED'}
        area, unit = get_object_area_and_unit(context)
        if not hasattr(obj, 'BIMProperties'):
            obj["BIMProperties"] = {}
        try:
            bimprops = obj.BIMProperties
            bimprops['ManualSurfaceArea'] = area
            bimprops['ManualSurfaceAreaUnit'] = unit
        except Exception:
            obj["ManualSurfaceArea"] = area
            obj["ManualSurfaceAreaUnit"] = unit
        self.report({'INFO'}, f"Saved area: {area:.4f} {unit} to BIMProperties['ManualSurfaceArea']")
        return {'FINISHED'}

# --- Function to save all IFC properties to Blender properties (not in UI yet) ---
def save_all_ifc_properties_to_blender(obj, ifc_props_dict):
    """
    Save all IFC properties from a dict to Blender's custom properties for the object.
    """
    if not hasattr(obj, 'BIMProperties'):
        obj["BIMProperties"] = {}
    try:
        bimprops = obj.BIMProperties
        for k, v in ifc_props_dict.items():
            bimprops[k] = v
    except Exception:
        for k, v in ifc_props_dict.items():
            obj[k] = v

# --- Update panel draw for live inspector ---
old_draw = IFCQSelectPanel.draw

def new_draw(self, context):
    props = context.scene.ifcqselect_props
    obj = context.active_object
    if context.mode == 'OBJECT':
        self.layout.prop(props, "ifc_file_path", text="IFC File")
        self.layout.operator("object.pull_all_ifc_quantities", icon='IMPORT', text="Pull All Quantities from IFC")
        self.layout.prop(props, "name_contains", text="Name Contains")
        self.layout.prop(props, "select_quantity_type", text="Quantity Type")
        self.layout.prop(props, "select_value_min", text="Min Value")
        self.layout.prop(props, "select_value_max", text="Max Value")
        self.layout.operator("object.ifcqselect_by_quantity", icon='RESTRICT_SELECT_OFF', text="Select by IFC Quantity")
    if obj and "BIMProperties" in obj and obj["BIMProperties"]:
        bim = obj["BIMProperties"]
        self.layout.separator()
        self.layout.label(text="IFC Quantities:")
        for key, value in bim.items():
            self.layout.label(text=f"{key}: {value:.4f}")
    if context.mode == 'EDIT_MESH':
        area, unit = get_selected_faces_area_and_unit(context)
        self.layout.separator()
        self.layout.label(text=f"Selected Face Area: {area:.4f} {unit}")

IFCQSelectPanel.draw = new_draw

# --- IFC TXT Cache Utilities ---
def get_ifc_txt_cache_path(ifc_path):
    cache_dir = os.path.expanduser('~/.cache/ifcqselect/')
    os.makedirs(cache_dir, exist_ok=True)
    base = os.path.basename(ifc_path)
    txt_name = os.path.splitext(base)[0] + '.txt'
    return os.path.join(cache_dir, txt_name)

def ensure_ifc_txt_cache(ifc_path):
    txt_path = get_ifc_txt_cache_path(ifc_path)
    if not os.path.exists(txt_path) or os.path.getmtime(txt_path) < os.path.getmtime(ifc_path):
        shutil.copy2(ifc_path, txt_path)
    return txt_path

# --- IFC Element Matching Utilities ---
def find_ifc_line_by_guid(txt_lines, guid):
    # Match lines like: IFCSLAB('0Yum10KqXDCB1RoWVMXOwE',$,'SM_PCC',...)
    pattern = re.compile(r"IFCSLAB\('%s',\$,'([^']+)'" % re.escape(guid))
    for line in txt_lines:
        if pattern.search(line):
            return line
    return None

def find_ifc_line_by_name(txt_lines, name):
    # Blender object names are like 'IfcWall/Wall01', 'IfcBeam/BeamA', etc.
    # IFC name is third argument in any IFC entity line (e.g., IFCWALL, IFCSLAB, etc.)
    # Always extract the part after the slash for matching
    if '/' in name:
        name = name.split('/')[-1]
    # Match lines like: IFCWALL('...',$,'Wall01',...) or IFCSLAB('...',$,'SM_PCC',...)
    pattern = re.compile(r"IFC[A-Z]+\('([^']+)',\$,'%s'" % re.escape(name))
    for line in txt_lines:
        if pattern.search(line):
            return line
    return None

# In match_ifc_element, clarify name extraction:
def match_ifc_element(obj, txt_path):
    guid = (
        obj.get('IfcGuid') or
        getattr(obj, 'IfcGuid', None) or
        obj.get('GlobalId') or
        getattr(obj, 'GlobalId', None) or
        obj.get('globalid') or
        getattr(obj, 'globalid', None)
    )
    # Always extract the part after the slash for name matching
    name = obj.name.split('/')[-1] if obj.name else None
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        txt_lines = f.readlines()
    line = None
    # Name-based matching is now primary
    if name:
        line = find_ifc_line_by_name(txt_lines, name)
        if line and guid and guid not in line:
            print(f"[WARNING] Name matched but GUID '{guid}' not found in line: {line.strip()}")
    if not line and guid:
        line = find_ifc_line_by_guid(txt_lines, guid)
        if line and name and name not in line:
            print(f"[WARNING] GUID matched but name '{name}' not found in line: {line.strip()}")
    return line

# --- Modified quantity pull to use .txt cache for parsing ---
def pull_all_ifc_quantities_to_blender(obj, ifc_path):
    if not ifc_path or not os.path.exists(ifc_path):
        return False, 'No IFC file path set or file does not exist.'
    txt_path = ensure_ifc_txt_cache(ifc_path)
    line = match_ifc_element(obj, txt_path)
    if not line:
        return False, 'No matching IFC element found for this object (by name or GUID) in .txt cache.'
    entity_ref = line.split('=')[0].strip() if '=' in line else None
    if not entity_ref:
        return False, 'Could not extract entity reference.'
    # Streaming approach: process file line by line, build minimal maps
    rels = set()
    qsets = {}
    quantities = {}
    # First pass: find all IFCRELDEFINESBYPROPERTIES referencing the entity
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        for l in f:
            if 'IFCRELDEFINESBYPROPERTIES' in l and f'({entity_ref})' in l:
                parts = l.split(',')
                ref = parts[-1].replace(')','').replace(';','').strip()
                rels.add(ref)
    # Second pass: find all IFCELEMENTQUANTITY/IFCPROPERTYSET and their referenced quantities
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        for l in f:
            if ('IFCELEMENTQUANTITY' in l or 'IFCPROPERTYSET' in l):
                set_ref = l.split('=')[0].strip()
                if set_ref in rels:
                    if '(' in l and ')' in l:
                        tuple_str = l[l.find('(')+1:l.rfind(')')]
                        refs = [r.strip() for r in tuple_str.split(',') if r.strip().startswith('#')]
                        qsets[set_ref] = refs
    # Third pass: find all referenced IFCQUANTITY* lines
    all_qrefs = set()
    for refs in qsets.values():
        all_qrefs.update(refs)
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        for l in f:
            if 'IFCQUANTITY' in l:
                q_ref = l.split('=')[0].strip()
                if q_ref in all_qrefs:
                    # Extract all possible quantity types and names
                    m = re.match(r"#\d+=IFCQUANTITY\w+\('([^']+)'[,$][^,]*,[^,]*,([^,]+)", l)
                    if m:
                        qname = m.group(1)
                        parts = l.split(',')
                        if len(parts) > 3:
                            try:
                                val = float(parts[3].replace(')', '').replace(';', '').replace('$', '').strip())
                                quantities[qname] = val
                            except Exception:
                                pass
    if not quantities:
        return False, 'No IFC quantities found for this object.'
    obj["BIMProperties"] = quantities
    return True, f'Copied {len(quantities)} IFC properties to BIMProperties (from .txt cache).'

class OBJECT_OT_pull_all_ifc_quantities(bpy.types.Operator):
    bl_idname = "object.pull_all_ifc_quantities"
    bl_label = "Pull All Quantities from IFC"
    bl_description = "Copy all IFC quantities for all selected objects to their BIMProperties."

    def execute(self, context):
        props = context.scene.ifcqselect_props
        ifc_path = getattr(props, 'ifc_file_path', None)
        selected = context.selected_objects
        updated = 0
        errors = []
        wm = context.window_manager
        wm.progress_begin(0, len(selected))
        for idx, obj in enumerate(selected):
            ok, msg = pull_all_ifc_quantities_to_blender(obj, ifc_path)
            if ok:
                updated += 1
            else:
                errors.append(f"{obj.name}: {msg}")
            wm.progress_update(idx + 1)
        wm.progress_end()
        self.report({'INFO'}, f"Updated {updated} objects. {'; '.join(errors) if errors else ''}")
        return {'FINISHED'}

class OBJECT_OT_ifcqselect_by_quantity(bpy.types.Operator):
    bl_idname = "object.ifcqselect_by_quantity"
    bl_label = "Select by IFC Quantity"
    bl_description = "Select objects whose IFC quantity matches the specified range."

    def execute(self, context):
        props = context.scene.ifcqselect_props
        quantity_type = props.select_quantity_type
        vmin = props.select_value_min
        vmax = props.select_value_max
        name_filter = props.name_contains.strip().lower()
        matched = 0
        for ob in context.scene.objects:
            name = ob.name.lower() if ob.name else ""
            if name_filter and name_filter not in name:
                ob.select_set(False)
                continue
            if "BIMProperties" in ob and ob["BIMProperties"] and quantity_type in ob["BIMProperties"]:
                val = ob["BIMProperties"][quantity_type]
                if vmin <= val <= vmax:
                    ob.select_set(True)
                    matched += 1
                else:
                    ob.select_set(False)
            else:
                ob.select_set(False)
        self.report({'INFO'}, f"Selected {matched} objects by {quantity_type} in range [{vmin}, {vmax}] with name filter '{name_filter}'.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(IFCQSelectProps)
    bpy.utils.register_class(OBJECT_OT_ifcqselect)
    bpy.utils.register_class(IFCQSelectPanel)
    bpy.utils.register_class(OBJECT_OT_ifcqselect_debug)
    bpy.utils.register_class(OBJECT_OT_ifcqselect_clearlog)
    bpy.utils.register_class(OBJECT_OT_save_selected_face_area)
    bpy.utils.register_class(OBJECT_OT_save_object_ifc_area)
    bpy.utils.register_class(OBJECT_OT_save_object_volume)
    bpy.utils.register_class(OBJECT_OT_pull_all_ifc_quantities)
    bpy.utils.register_class(OBJECT_OT_ifcqselect_by_quantity)
    bpy.types.Scene.ifcqselect_props = bpy.props.PointerProperty(type=IFCQSelectProps)

def unregister():
    bpy.utils.unregister_class(IFCQSelectPanel)
    bpy.utils.unregister_class(OBJECT_OT_ifcqselect)
    bpy.utils.unregister_class(OBJECT_OT_ifcqselect_debug)
    bpy.utils.unregister_class(OBJECT_OT_ifcqselect_clearlog)
    bpy.utils.unregister_class(OBJECT_OT_save_selected_face_area)
    bpy.utils.unregister_class(OBJECT_OT_save_object_ifc_area)
    bpy.utils.unregister_class(OBJECT_OT_save_object_volume)
    bpy.utils.unregister_class(OBJECT_OT_pull_all_ifc_quantities)
    bpy.utils.unregister_class(OBJECT_OT_ifcqselect_by_quantity)
    bpy.utils.unregister_class(IFCQSelectProps)
    del bpy.types.Scene.ifcqselect_props

if __name__ == "__main__":
    register() 
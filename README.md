# ifcqselect Blender Addon

> **Project folder:** `ifcqselect`

> **Known Limitation:**
> The plugin currently parses and exposes only one IFC quantity per object for quick selection. This means that if your selection does not work as expected, you should try different quantity types in the selection dropdown. Only the parsed quantity will be available for filtering and selection for each object. For example, if two quantity types (such as GrossArea and NetArea) have the same value for an object, only one of them will be available for selection, so only that parameter will work. This is a current limitation and may affect workflows where multiple quantities are needed. Future updates may address this limitation by allowing multiple quantities to be parsed and selected per object.

## Overview

**ifcqselect** is a Blender addon for BIM-centric selection and quantity extraction from IFC files. It enables users to:
- Pull all BIM/IFC quantities for objects directly from an IFC file
- Filter and select objects in the 3D viewport by any IFC quantity (e.g., area, volume, length, etc.)
- Filter by object name ("Name Contains")
- View all extracted IFC quantities for each object

## Features
- Manual IFC file selection (never modifies the original IFC file)
- Fast, robust IFC-to-.txt caching for parsing
- Pull all quantities for all selected objects with one click
- Select objects by any IFC quantity and value range
- Filter selection by object name substring
- Only displays and selects by authoritative BIM/IFC data (no geometry fallback)

## Dependencies
- **IfcOpenShell** (LGPL): Required for all IFC parsing and quantity extraction. Must be installed in Blender's Python environment. See: https://ifcopenshell.org/
- **bmesh** and **mathutils**: Standard Blender Python modules (no extra installation needed).

### Checking IfcOpenShell Installation
To verify that IfcOpenShell is installed in Blender, open Blender's **Scripting** workspace and run the following in the Python Console:

```python
import ifcopenshell
print(ifcopenshell.__version__)
```
If you see a version number and no error, IfcOpenShell is installed correctly.

> **Troubleshooting:**
> If you have trouble installing IfcOpenShell directly, try installing the [BonsaiBIM](https://bonsaibim.com/) add-on for Blender. BonsaiBIM will automatically install IfcOpenShell and its dependencies, making it available for ifcqselect and other IFC/BIM add-ons.

## Installation
1. Download or copy `ifcqselectv100.py` to your computer.
2. In Blender, go to **Edit > Preferences > Add-ons > Install** and select the file.
3. Enable the addon in the Add-ons list.

## How to use
1. **Select IFC File:**
   - In the 3D Viewport sidebar (N-panel), go to the "ifcqselect" tab.
   - Use the "IFC File" field to select your IFC file. The addon will cache a .txt copy for fast parsing.
2. **Pull Quantities:**
   - Click "Pull All Quantities from IFC" to extract all BIM/IFC quantities for all selected objects.
3. **Filter/Select by Quantity:**
   - Use the "Name Contains" field to filter objects by name (case-insensitive substring).
   - Choose a "Quantity Type" (e.g., GrossArea, NetVolume, etc.).
   - Set the Min/Max value range.
   - Click "Select by IFC Quantity" to select all objects matching the filter and value range.
4. **View Quantities:**
   - With an object selected, all extracted IFC quantities are shown in the panel.
   - In Edit Mode, the area of selected faces is displayed for manual inspection.

## License
- The core code of ifcqselect is **proprietary** (c) 2025 tankshield. All rights reserved.
- The IFC unit detection helpers are open-source (MIT/LGPL) for compliance.
- This addon uses IfcOpenShell (LGPL) as a dependency. See: https://ifcopenshell.org/

For licensing inquiries, support, or to report issues, please contact tankshield via GitHub at https://github.com/tankshield. You may send a direct message or open an issue on the repository. 
# Hume Region Values Checking Tool for ArcGIS Pro
Spatial analysis tool for ArcGIS Pro that analyses intersections between proposed works (e.g. JFMP, DAP) and multiple values layers, supporting presence checks, counts, and area/length measurements with optional buffer zones.
**Version:** 3.0.0.1  
**Author:** Michael & Vanessa  
**Date:** August 1, 2025

### Features
- **Multiple Analysis Methods:** Support for presence checks, counting, and area/length measurements
- **Buffer Analysis:** Optional buffer zones around input features for proximity analysis
- **Batch Processing:** Process multiple values layers simultaneously using a reference table
- **Performance Optimized:** Uses in-memory workspace and parallel processing for faster execution
- **Flexible Output:** Generates timestamped CSV reports with detailed intersection results
- **Error Handling:** Comprehensive logging and error management

### Requirements
- ArcGIS Pro 3.1 or newer
- Python 3.x (included with ArcGIS Pro)
- ArcPy library (included with ArcGIS Pro)
- Write permissions to output directory

## Usage - ArcGIS Pro Toolbox
1. Download the script file to your local machine
2. Open ArcGIS Pro
3. Add the script as a custom tool:
   - Open Catalog pane
   - Drag and drop the HumeValueChecking.atbx file into the toolbox
   - Browse to the script file and configure parameters

#### Toolbox parameters:
   - **Input Feature Class:** Your analysis features (polygons, points, or lines)
   - **Feature ID Field:** Unique identifier field contained in Input Feature Class
   - **Theme Reference Table:** Path to your configured reference table
   - **GIS Public Path:** Base path for your spatial data, can be network or local. 
   - **Output Path:** Directory for results and logs

## Usage - Standalone Execution
1. Configure the manual parameters in the script
2. Run the script directly in your Python environment or using Run in PyCharm, VSCode or alternative
```python
python values_check_tool.py
```

#### Manual Parameters (for standalone execution)
If running outside the ArcGIS Pro toolbox interface, adjust these variables at the top of the script:
```python
FEATURE_CLASS   = 'path/to/your/input/features.gdb/feature_class'
FEATURE_ID      = 'UNIQUE_ID_FIELD'
THEME_REFTAB    = 'path/to/reference/table.gdb/reference_table'
GISPUB_PATH     = 'path/to/gis_public/folder'
OUT_PATH        = 'path/to/output/directory'
SPATIAL_REF     = 7899  # VICGRID2020 or your preferred spatial reference
```

## Reference Table
The tool requires a reference table with the following fields:
| Field Name | Type | Description |
|------------|------|-------------|
| `THEMENAME` | Text | Display name for the theme/layer |
| `CHECK_YN` | Text | "Y" to include layer, "N" to skip |
| `DEFAULTWS_YN` | Text | "Y" if using default workspace path |
| `DATA_LOC` | Text | Custom path (if DEFAULTWS_YN = "N") |
| `GDB_NAME` | Text | Geodatabase name |
| `FC_NAME` | Text | Feature class name |
| `DEF_QUERY` | Text | Optional definition query |
| `CHECK_METHOD` | Text | "PRESENT", "COUNT", or "MEASURE" |
| `REPFLD1` | Text | Fields to be included in output |
| `REPFLD2` | Text | .. |
| `REPFLD3` | Text | .. |
| `REPFLD4` | Text | .. |
| `BUFFER_DIST` | Number | Buffer distance in meters (0 = no buffer) |
> [!IMPORTANT] 
> For non-CSDL/gis_public values layers, DEFAULTWS should be "N" and DATA_LOC should contain the full path to the feature class or shapefile.  
> For CSDL/gis_public values layers, the data will be drawn from the GIS_PUBLIC parameter supplied from script or toolbox:  
>  * {GIS PUBLIC PATH}\DATA_LOC\GDB_NAME\FC_NAME 

### Analysis Methods
The format of returned data is determined by the analysis method provided in the reference table's CHECK_METHOD field.

##### PRESENT
Checks for the presence of intersecting features and reports their attribute values. Duplicate values are discarded.  
**Output format:** `"Primary Value (Secondary | Tertiary | Additional)"`
##### COUNT
Counts the number of intersecting features and groups by attribute values.  
**Output format:** `"Primary Value (Secondary | Tertiary) - Count"`
##### MEASURE
Calculates total area (for polygons) or length (for lines) of intersecting features.  
**Output format:** `"Primary Value (Secondary | Tertiary) - 15.2ha"` or `"Value - 3.7km"`

## Output
The tool generates two types of output files:
#### 1. Results CSV
- **Location:** `{output_path}/{timestamp}_{input_name}_ValuesCheck.csv`
- **Format:** One row per input feature with columns for each theme
- **Content:** Detailed intersection results formatted according to analysis method

#### 2. Performance Log
- **Location:** `{output_path}/{timestamp}_script_performance.txt`
- **Content:** Execution timeline, error messages, and processing statistics

## License
[Add your license information here]

## Support
LOL... I don't think so.

## Version History

- **3.0.0.1** (2025-08-01): Complete re-write, buffers works features once per buffer distance, intersections are performed once for each values layer rather than sequentially. Reduced run time on DAP from 10 hours to 15 minutes.
- **2.0.0.8** (2025-07-28): Reworking of previous Python 2.7 version with minor changes to improve performance and error handling.

"""
ArcGIS Pro Toolbox Script - Values Check Tool
Performs spatial analysis to check values intersecting with input features.
Supports presence checks, counts, and area/length measurements with optional buffer zones.
Author: 
Date: 20250729
Version: 2.0.0.5 (Refactored)
"""
import os
import arcpy
from datetime import datetime
from typing import List, Tuple, Optional, Any

#####################################################################################
#           ADJUST THESE IF RUNNING OUTSIDE OF THE ARCGIS PRO TOOLBOX               #
#####################################################################################

# Manual parameters - script will use these if arcpy.GetParameterAsText isn't found
FEATURE_CLASS   = 'C:\\data\\daptest\\Hume_uploadtoVDP_20250718.gdb\\DAP_FINAL_AREA_20250718'             # Input Feature Class
FEATURE_ID      = 'DAP_REF_NO'                                  # Feature ID Field
THEME_REFTAB    = 'C:\\data\\daptest\\Single Report Tool\\Reference Tables\\reftables.gdb\\REFTABLE_INDIGENOUS_HERITAGE_ALL_RECORDS'  # Theme Reference Table
GISPUB_LOCATION = 'C:\\data'                                    # CSDL Location
OUT_PATH        = 'C:\\data\\20250709_hume_test'    # Output Path

######################################################################################
######################################################################################

class ValuesCheckTool:
    """Main class for performing spatial values checking operations."""
    
    def __init__(self, input_fc: str, id_field: str, ref_table: str, 
                 csdl_location: str, output_path: str):
        """Initialize the tool with parameters."""
        self.input_fc = input_fc
        self.id_field = id_field
        self.ref_table = ref_table
        self.csdl_location = csdl_location
        self.output_path = output_path
        self.temp_gdb = None
        self.counter = 0
        perf_log_path = os.path.join(self.output_path, f"{self.get_timestamp()}_script_performance.txt")
        self.perf_log = open(perf_log_path, "w")
        
        # Setup environment
        self._setup_environment()
    
    def _setup_environment(self) -> None:
        """Configure ArcPy environment settings."""
        arcpy.env.overwriteOutput = True
        arcpy.env.parallelProcessingFactor = "75%"
        arcpy.SetLogHistory(False)
        
        
        sr = arcpy.SpatialReference(7899) # Set spatial reference to VICGRID2020
        # sr = arcpy.SpatialReference(4283) # Set spatial reference to GDA94
        arcpy.env.outputCoordinateSystem = sr
        arcpy.env.cartographicCoordinateSystem = sr
        
        # Create output directory and temp workspace
        os.makedirs(self.output_path, exist_ok=True)

        """Create temporary geodatabase workspace."""
        self.temp_gdb = os.path.join(self.output_path, "valuescheck_temp.gdb")
        if arcpy.Exists(self.temp_gdb):
            arcpy.Delete_management(self.temp_gdb)
        
        arcpy.CreateFileGDB_management(
            self.output_path, "valuescheck_temp.gdb", "10.0"
        )
        arcpy.env.workspace = self.temp_gdb
        
        self.logMessage('info', f"Created temp workspace: {self.temp_gdb}")
    
    @staticmethod
    def get_timestamp() -> str:
        """Return formatted timestamp string."""
        return datetime.now().strftime("%Y%m%d_%H%Mhr")
    
    @staticmethod
    def get_basename(filepath: str) -> str:
        """Extract basename from file path without extension."""
        return os.path.splitext(os.path.basename(filepath))[0]
    
    @staticmethod
    def shorten_text(text: str) -> str:
        """Abbreviate common words to reduce text length."""
        abbreviations = {
            'Landscape': 'Lndscp', 'Highway': 'Hwy', 'Road': 'Rd',
            'Designated': 'Dsgntd', 'Catchment': 'Ctchmnt', 'Woodland': 'Wdlnd',
            'Drive': 'Dr', 'Mosaic': 'Msc', 'Complex': 'Cmplx',
            'Eucalyptus': 'Eu.', 'Shrubland': 'Shrbl', 'Herbland': 'Hrbl',
            'Forest': 'Fst', 'Point': 'Pt', 'protection': 'prtn',
            'Creek': 'Ck', 'Township': 'Tshp', 'habitat': 'hab',
            'settlement': 'stlmnt', 'Reserve': 'Rsv', ' and ': ' & ',
            'Alpine': 'Alp', 'alpine': 'alp', 'Goulburn': 'Glbn',
            'River': 'Riv', ',': ';', "'": ''
        }
        
        for full_word, abbr in abbreviations.items():
            text = text.replace(full_word, abbr)
        
        return text
    
    def create_buffer(self, geometry: str, buffer_dist: float) -> str:
        """Create buffer around geometry, excluding internal area for polygons."""
        desc = arcpy.Describe(geometry)
        geometry_type = desc.shapeType.upper()
        buffer_name = "currentFeature_buffer"
       
        if geometry_type == "POLYGON":
            # If the feature is a polygon, create ring buffer
            buffer_fc = arcpy.analysis.Buffer(
                    in_features=geometry,
                    out_feature_class=buffer_name,
                    buffer_distance_or_field=f"{buffer_dist} meters",
                    line_side="OUTSIDE_ONLY",
                    line_end_type="ROUND",
                    dissolve_option="NONE",
                    dissolve_field=None,
                    method="PLANAR"
                )
        else:
            # Otherwise, create a regular buffer
            buffer_fc = arcpy.analysis.Buffer(
                    in_features=geometry,
                    out_feature_class=buffer_name,
                    buffer_distance_or_field=f"{buffer_dist} meters",
                    line_side="FULL",
                    line_end_type="ROUND",
                    dissolve_option="NONE",
                    dissolve_field=None,
                    method="PLANAR"
                )
       
        return buffer_fc
    
    def get_reporting_fields(self, field_list: List[str]) -> List[str]:
        """Filter out empty or null reporting fields."""
        return [field for field in field_list if field and field.strip()]
    
    def get_values_present(self, input_feature: str, values_fc: str, checktype: str, *report_fields: str) -> List[List[str]]:
        """Get unique values present in intersecting features."""
        try:
            desc = arcpy.Describe(values_fc)
            
            # Spatial selection
            values_intersecting = arcpy.management.SelectLayerByLocation(values_fc, "INTERSECT", input_feature, selection_type="SUBSET_SELECTION")

            feature_count = int(arcpy.GetCount_management(values_intersecting).getOutput(0))
            if feature_count == 0:
                self.logMessage('info', f"{desc.baseName} {checktype} presence results: 0 unique values")
                return [[]]
            
            # Get reporting fields
            reporting_fields = self.get_reporting_fields(list(report_fields))
            if not reporting_fields:
                self.logMessage('info', f"{desc.baseName} {checktype} presence results: 0 reporting fields")
                return [[]]
            
            # Use set for much faster duplicate checking
            results_set = set()
            
            with arcpy.da.SearchCursor(values_intersecting, reporting_fields) as cursor:
                for row in cursor:
                    # Process attributes
                    row_list = []
                    for val in row:
                        if isinstance(val, datetime):
                            row_list.append(val.strftime('%Y-%m-%d'))
                        elif val is not None:
                            clean_val = str(val).replace("'", "").replace(",", ";").replace("\n","_n")
                            row_list.append(clean_val)
                    
                    # Add to set (automatic duplicate removal)
                    results_set.add(tuple(row_list))
            
            # Convert to list and sort
            results = [list(item) for item in results_set]
            results.sort()
            
            self.logMessage('info', f"{desc.baseName} {checktype} presence results: {len(results)} unique values")
            return results
            
        except Exception as e:
            self.logMessage('error', f"Error in get_values_present_fast: {str(e)}")
            return [[]]
    
    def get_values_count(self, input_feature: str, values_fc: str, checktype: str, *report_fields: str) -> List[List[Any]]:
        """Get intersecting values with their occurrence counts."""
        try:
            desc = arcpy.Describe(values_fc)
            
            # Spatial selection
            values_intersecting = arcpy.management.SelectLayerByLocation(values_fc, "INTERSECT", input_feature, selection_type="SUBSET_SELECTION")
            
            feature_count = int(arcpy.GetCount_management(values_intersecting).getOutput(0))
            if feature_count == 0:
                self.logMessage('info', f"{desc.baseName} {checktype} count results: 0 unique values")
                return [[]]
            
            reporting_fields = self.get_reporting_fields(list(report_fields))
            if not reporting_fields:
                self.logMessage('info', f"{desc.baseName} {checktype} count results: 0 reporting values")
                return [[]]
            
            # Count occurrences with proper attribute cleaning
            value_counts = {}
            with arcpy.da.SearchCursor(values_intersecting, reporting_fields) as cursor:
                for row in cursor:
                    # Clean the row data
                    cleaned_row = []
                    for val in row:
                        if isinstance(val, datetime):
                            cleaned_row.append(val.strftime('%Y-%m-%d'))
                        elif val is not None:
                            clean_val = str(val).replace("'", "").replace(",", ";").replace("\n", "_n")
                            cleaned_row.append(clean_val)
                    
                    key = tuple(cleaned_row)
                    value_counts[key] = value_counts.get(key, 0) + 1
            
            # Format results
            results = [list(key) + [count] for key, count in value_counts.items()]
            results.sort()
            
            self.logMessage('info', f"{desc.baseName} {checktype} count results: {len(results)} unique values")
            
            return results
            
        except Exception as e:
            self.logMessage('error', f"Error in get_values_count: {str(e)}")
            return [[]]

    def get_values_areas(self, input_feature: str, values_fc: str, checktype: str, *report_fields: str) -> List[List[Any]]:
        """Get values with their area/length measurements using geometry intersection."""
        try:
            desc = arcpy.Describe(values_fc)
            
            # Get the input feature geometry
            input_geom = None
            with arcpy.da.SearchCursor(input_feature, ["SHAPE@"]) as cursor:
                for row in cursor:
                    input_geom = row[0]
                    break  # Only need the first (selected) feature
            
            if not input_geom:
                self.logMessage('error', "Could not get input feature geometry")
                return [[]]
            
            # First, do spatial selection to reduce dataset size
            values_intersecting = arcpy.management.SelectLayerByLocation(values_fc, "INTERSECT", input_feature, selection_type="SUBSET_SELECTION")
            
            # Check if any features were selected
            selected_count = int(arcpy.GetCount_management(values_intersecting).getOutput(0))
            if selected_count == 0:
                self.logMessage('info', f"{desc.baseName} {checktype} measure results: 0 unique values")
                return [[]]
            
            reporting_fields = self.get_reporting_fields(list(report_fields))
            if not reporting_fields:
                self.logMessage('info', f"{desc.baseName} {checktype} measure results: 0 reporting fields")
                return [[]]
            
            # Determine measurement type
            geometry_type = desc.shapeType.upper()
            
            if geometry_type == "POLYGON":
                measure_field = "SHAPE@"
                def calculate_measure(geom):
                    intersected = geom.intersect(input_geom, 4)  # 4 = esriGeometryIntersection
                    return intersected.getArea() if intersected else 0
                unit_conversion = lambda x: f"{x / 10000:.1f}ha"
            elif geometry_type == "POLYLINE":
                measure_field = "SHAPE@"
                def calculate_measure(geom):
                    intersected = geom.intersect(input_geom, 4)  # 4 = esriGeometryIntersection
                    return intersected.getLength if intersected else 0
                unit_conversion = lambda x: f"{x / 1000:.3f}km"
            else:
                self.logMessage('error', f"Unsupported geometry type: {geometry_type}")
                return [[]]
            
            fields = reporting_fields + [measure_field]
            
            # Aggregate measurements by attributes using geometry intersection
            value_measures = {}
            processed_count = 0
            
            with arcpy.da.SearchCursor(values_intersecting, fields) as cursor:
                for row in cursor:
                    try:
                        # Calculate intersection measure
                        feature_geom = row[-1]
                        intersected_measure = calculate_measure(feature_geom)
                        
                        if intersected_measure > 0:  # Only include if there's actual intersection
                            # Clean attribute values
                            attrs = []
                            for val in row[:-1]:
                                if isinstance(val, datetime):
                                    attrs.append(val.strftime('%Y-%m-%d'))
                                else:
                                    clean_val = str(val).replace("'", "").replace(",", ";").replace("\n","_n")
                                    if len(clean_val) > 200:
                                        clean_val = clean_val[:200] + "..."
                                    attrs.append(clean_val)
                            
                            total_len = sum(len(attr) for attr in attrs) + 3 * (len(attrs) - 1)

                            while total_len > 200:
                                # Find the longest attribute
                                longest_idx = max(range(len(attrs)), key=lambda i: len(attrs[i]))
                                longest_attr = attrs[longest_idx]
                                longest_len = len(longest_attr)
                                
                                # Remove existing ellipsis if present
                                if longest_attr.endswith("..."):
                                    longest_attr = longest_attr[:-3]  # Remove the "..."
                                    longest_len = len(longest_attr)

                                # Trim one character from longest attribute, then add the elipsis
                                new_length = longest_len - 1
                                attrs[longest_idx] = longest_attr[:new_length] + "..."

                                # re-calculate total length
                                total_len = sum(len(attr) for attr in attrs) + 3 * (len(attrs) - 1)
                            
                            key = tuple(attrs)
                            value_measures[key] = value_measures.get(key, 0) + intersected_measure
                        processed_count += 1
                        
                    except Exception as geom_error:
                        self.logMessage('warn', f"Geometry processing error for feature {processed_count}: {str(geom_error)}")
                        continue
            
            # Format results
            results = []
            for key, total_measure in value_measures.items():
                if total_measure > 0:  # Only include non-zero measurements
                    measure_str = unit_conversion(total_measure)
                    results.append(list(key) + [measure_str])
            
            results.sort()
            self.logMessage('info', f"{desc.baseName} {checktype} measure results: {len(results)} unique values from {processed_count} features")
            return results
            
        except Exception as e:
            self.logMessage('error', f"Error in get_values_areas_no_clip: {str(e)}")
            return [[]]
    
    def format_presence_output(self, value_list: List[Any]) -> str:
        """Format presence results for output."""
        if not value_list or (len(value_list) == 1 and not value_list[0]):
            return ""
        
        # Clean the list
        cleaned = [str(item).replace(",", ";") for item in value_list 
                  if item and str(item).strip() and str(item) != "None"]
        
        if not cleaned:
            return ""
        
        if len(cleaned) == 1:
            return cleaned[0]
        
        # Format as: "first (second | third | fourth)"
        return f"{cleaned[0]} ({' | '.join(cleaned[1:])})"
    
    def format_measure_output(self, value_list: List[Any]) -> str:
        """Format measure/count results for output."""
        if not value_list or (len(value_list) == 1 and not value_list[0]):
            return ""
        
        # Clean the list
        cleaned = [str(item).replace(",", ";") for item in value_list 
                  if item and str(item).strip() and str(item) != "None"]
        
        if not cleaned:
            return ""
        
        if len(cleaned) == 2:
            return f"{cleaned[0]} - {cleaned[1]}"
        
        # Format as: "first (second | third) - measure"
        if len(cleaned) > 2:
            middle_parts = ' | '.join(cleaned[1:-1])
            return f"{cleaned[0]} ({middle_parts}) - {cleaned[-1]}"
        
        return cleaned[0]
    
    def get_method_functions(self, method: str) -> Tuple[callable, callable]:
        """Return appropriate checking and formatting functions based on method."""
        method = method.upper()
        
        if method == "PRESENT":
            return self.get_values_present, self.format_presence_output
        elif method == "COUNT":
            return self.get_values_count, self.format_measure_output
        else:  # Default to areas/measures
            return self.get_values_areas, self.format_measure_output
    
    def process_feature(self, feature_name: str, field_type: str, output_file: Any) -> None:
        """Process a single feature for values checking."""
        try:
            # Create selection expression
            if field_type.upper() == "STRING":
                expression = f"{self.id_field} = '{feature_name}'"
            else:
                expression = f"{self.id_field} = {feature_name}"
            
            self.counter += 1
            
            self.logMessage('info', f"\nProcessing feature {self.counter}: {expression}")
            
            # Write feature name to output
            output_file.write(str(feature_name))
            
            # Clean up any existing current feature
            if arcpy.Exists("currentFeature"):
                arcpy.Delete_management("currentFeature")
            
            # Select current feature
            current_feature = arcpy.management.SelectLayerByAttribute(self.input_fc, "NEW_SELECTION", expression)
            
            # Process each theme in reference table
            theme_fields = [
                "CHECK_YN", "DEFAULTWS_YN", "DATA_LOC", "GDB_NAME", "FC_NAME",
                "DEF_QUERY", "CHECK_METHOD", "REPFLD1", "REPFLD2", "REPFLD3", 
                "REPFLD4", "BUFFER_DIST"
            ]
            
            with arcpy.da.SearchCursor(self.ref_table, theme_fields) as cursor:
                for row in cursor:
                    if row[0].upper() != "Y":  # Skip if CHECK_YN != "Y"
                        continue
                    
                    # Get theme data location
                    if row[1].upper() == "Y":  # DEFAULTWS_YN
                        theme_path = os.path.join(self.csdl_location, row[2], row[3], row[4])
                    else:
                        theme_path = row[2]  # DATA_LOC
                    
                    # Apply definition query if specified
                    def_query = row[5]  # DEF_QUERY
                    if def_query and len(def_query.strip()) > 1:
                        theme_layer = arcpy.management.SelectLayerByAttribute(theme_path, "NEW_SELECTION", def_query)
                    else:
                        theme_layer = arcpy.management.SelectLayerByAttribute(theme_path, "CLEAR_SELECTION")
                    
                    # Get method and reporting fields
                    method = row[6]  # CHECK_METHOD
                    reporting_fields = row[7:11]  # REPFLD1-4
                    buffer_dist = row[11]  # BUFFER_DIST
                    
                    # Get appropriate functions
                    check_func, format_func = self.get_method_functions(method)
                    
                    # Check values within feature
                    results = check_func(current_feature, theme_layer, "polygon", *reporting_fields)
                    
                    # Write results
                    self._write_results(output_file, results, format_func)
                    
                    # Check buffer if specified
                    if buffer_dist and buffer_dist > 0:
                        if def_query and len(def_query.strip()) > 1:
                            # reset selection - required because previous check may have reduced selection
                            theme_layer = arcpy.management.SelectLayerByAttribute(theme_path, "NEW_SELECTION", def_query)
                        else:
                            theme_layer = arcpy.management.SelectLayerByAttribute(theme_path, "CLEAR_SELECTION")
                        self._process_buffer(current_feature, theme_layer, buffer_dist, 
                            check_func, format_func, output_file, results, *reporting_fields)
            
            # Finish the row
            output_file.write("\n")
            
            # Clear selection
            arcpy.SelectLayerByAttribute_management(self.input_fc, "CLEAR_SELECTION")
            
        except Exception as e:
            self.logMessage('error', f"Error processing feature {feature_name}: {str(e)}")
            output_file.write(",Error occurred\n")
    
    def _write_results(self, output_file: Any, results: List[List[Any]], 
                      format_func: callable) -> None:
        """Write results to output file."""
        if not results or (len(results) == 1 and not results[0]):
            output_file.write(',="Nil features"')
        elif len(results) == 1:
            formatted = format_func(results[0])
            output_file.write(f',="{formatted}"')
        else:
            # Multiple results
            formatted_results = []
            for result in results:
                formatted = format_func(result)
                if formatted:
                    formatted_results.append(formatted)
            
            if formatted_results:
                output_file.write(f',="{formatted_results[0]}"')
                for result in formatted_results[1:]:
                    output_file.write(f'& CHAR(10) & "{result}"')
            else:
                output_file.write(',="Nil features"')
    
    def _process_buffer(self, current_feature: str, theme_layer: str, 
                       buffer_dist: float, check_func: callable, 
                       format_func: callable, output_file: Any, 
                       main_results: List[List[Any]],
                       *reporting_fields: str) -> None:
        """Process buffer area around feature."""
        try:
            
            # Create buffer
            buffer_feature = self.create_buffer(current_feature, buffer_dist)
            
            # Check values in buffer
            buffer_results = check_func(buffer_feature, theme_layer, f"{buffer_dist}m buffer", *reporting_fields) 
            
            # Determine if main results were empty
            has_main_results = (main_results and not (len(main_results) == 1 and not main_results[0]))
            
            # Write buffer results
            prefix = " & CHAR(10) &" if has_main_results else "&"
            
            if not buffer_results or (len(buffer_results) == 1 and not buffer_results[0]):
                output_file.write(
                    f'{prefix} CHAR(10) & "Within Buffer Area ({buffer_dist}m): Nil features"'
                )
            else:
                output_file.write(
                    f'{prefix} CHAR(10) & "Within Buffer Area ({buffer_dist}m):"'
                )
                for result in buffer_results:
                    formatted = format_func(result)
                    if formatted:
                        output_file.write(f' & CHAR(10) & "{formatted}"')
                        
        except Exception as e:
            self.logMessage('error', f"Error processing buffer: {str(e)}")
    
    def run(self) -> None:
        """Execute the main values checking process."""
        try:
            timestamp = self.get_timestamp()

            
            # Create output CSV
            output_csv_path = os.path.join(
                self.output_path, 
                f"{timestamp}_{self.get_basename(self.input_fc)}_ValuesCheck.csv"
            )
            
            self.logMessage('info', f"Output CSV: {output_csv_path}")

            with open(output_csv_path, "w") as output_file:
                
                self.logMessage('info', f"Script started: {datetime.now()}")
                # self._log(f"Script started: {datetime.now()}")
                
                # Write CSV header
                self._write_csv_header(output_file)
                
                # Get list of unique features
                feature_list = self._get_unique_features()
                
                # Get field type for expression building
                field_type = self._get_field_type()
                
                # Set up progress indicator
                arcpy.SetProgressor(
                    "step", "Checking for values intersecting features...", 
                    0, len(feature_list), 1
                )
                
                # Process each feature
                for feature_name in feature_list:
                    self.process_feature(feature_name, field_type, output_file)
                    arcpy.SetProgressorPosition()
                
                self.logMessage('info', f"\nScript completed. Total features processed: {self.counter}")
            
        except Exception as e:
            self.logMessage('error', f"Error in main execution: {str(e)}")
            raise
        
        finally:
            self._cleanup()
    
    def _write_csv_header(self, output_file: Any) -> None:
        """Write CSV header row."""
        output_file.write(f"{self.id_field}")

        with arcpy.da.SearchCursor(self.ref_table, ["CHECK_YN", "THEMENAME"]) as cursor:
            for row in cursor:
                if row[0].upper() == "Y":
                    output_file.write(f",{row[1]}")
        output_file.write("\n")
    
    def _get_unique_features(self) -> List[str]:
        """Get sorted list of unique feature identifiers."""
        feature_list = []
        with arcpy.da.SearchCursor(self.input_fc, [self.id_field]) as cursor:
            for row in cursor:
                if row[0] not in feature_list:
                    feature_list.append(row[0])
        
        feature_list.sort()
        self.logMessage('info', f"{len(feature_list)} unique features found")
        return feature_list
    
    def _get_field_type(self) -> str:
        """Get the field type of the ID field."""
        desc = arcpy.Describe(self.input_fc)
        for field in desc.fields:
            if field.name == self.id_field:
                return field.type
        
        raise ValueError(f"Field '{self.id_field}' not found in {self.input_fc}")

    def logMessage(self, type, message: str) -> None:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.perf_log.write(f"{now} {message}\n")
            self.perf_log.flush()
        except Exception as e:
            # Fallback if file writing fails
            print(f"Log write error: {e}")
        
        if type == "error":
            arcpy.AddError(message)
        elif type == "warn":
            arcpy.AddWarning(message)
        else:
            arcpy.AddMessage(message)

    def _cleanup(self) -> None:
        """Clean up temporary files and workspace."""
        try:
            if self.temp_gdb and arcpy.Exists(self.temp_gdb):
                # Clean up any remaining feature classes
                arcpy.env.workspace = self.temp_gdb
                temp_fcs = arcpy.ListFeatureClasses()
                for fc in temp_fcs:
                    try:
                        arcpy.Delete_management(fc)
                    except:
                        pass  # Continue cleanup even if individual deletions fail
                
                # Delete the temporary geodatabase
                try:
                    arcpy.Delete_management(self.temp_gdb)
                    self.logMessage('info', "Temporary workspace cleaned up")
                except:
                    self.logMessage('warn', f"Could not delete temporary workspace: {self.temp_gdb}")
                    
        except Exception as e:
            self.logMessage('warn', f"Error during cleanup: {str(e)}")

def script_tool(input_fc: str, id_field: str, ref_table: str, 
               csdl_location: str, output_path: str) -> None:
    """
    Main script tool function for ArcGIS Pro toolbox.
    
    Parameters:
    - input_fc: Input feature class path
    - id_field: Field name for feature identification
    - ref_table: Reference table with theme definitions
    - csdl_location: Location of CSDL data
    - output_path: Output directory path
    """
    try:
        # Validate inputs
        if not arcpy.Exists(input_fc):
            raise ValueError(f"Input feature class does not exist: {input_fc}")
        
        if not arcpy.Exists(ref_table):
            raise ValueError(f"Reference table does not exist: {ref_table}")
        
        if not os.path.exists(csdl_location):
            raise ValueError(f"CSDL location does not exist: {csdl_location}")
        
        # Create and run the tool
        tool = ValuesCheckTool(input_fc, id_field, ref_table, csdl_location, output_path)
        tool.run()
        
        arcpy.AddMessage("Values check completed successfully!")
        
    except Exception as e:
        arcpy.AddError(f"Script execution failed: {str(e)}")
        raise
if __name__ == "__main__":
    # Get parameters from ArcGIS Pro tool interface
    param0 = arcpy.GetParameterAsText(0) or FEATURE_CLASS   # Input Feature Class
    param1 = arcpy.GetParameterAsText(1) or FEATURE_ID      # Feature ID Field
    param2 = arcpy.GetParameterAsText(2) or THEME_REFTAB    # Theme Reference Table
    param3 = arcpy.GetParameterAsText(3) or GISPUB_LOCATION # CSDL Location
    param4 = arcpy.GetParameterAsText(4) or OUT_PATH        # Output Path
 
    script_tool(param0, param1, param2, param3, param4)

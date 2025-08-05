"""
ArcGIS Pro Toolbox Script - Values Check Tool
Performs spatial analysis to check values intersecting with input features.
Supports presence checks, counts, and area/length measurements with optional buffer zones.
Author: 
Date: 20250804
Version: 3.0.0.2
"""

import os
import arcpy
from datetime import datetime
from typing import List, Tuple, Any
import csv

#######################################################################################
#            ADJUST THESE IF RUNNING OUTSIDE OF THE ARCGIS PRO TOOLBOX                #
#######################################################################################
"""Manual parameters - script will use these if arcpy.GetParameterAsText isn't found"""
FEATURE_CLASS   = 'C:\\data\\daptest\\Hume_uploadtoVDP_20250718.gdb\\DAP_FINAL_AREA_20250718' # Input Feature Class
FEATURE_ID      = 'DAP_REF_NO'                     # Feature ID Field
THEME_REFTAB    = 'C:\\data\\daptest\\Single Report Tool\\Reference Tables\\reftables.gdb\\REFTABLE_DAP_20250417'  # Theme Reference Table
GISPUB_PATH     = 'C:\\data'                       # gis_public folder location
OUT_PATH        = 'C:\\data\\20250709_hume_test'   # Output Path
SPATIAL_REF     = 7899                             # Set spatial ref to VICGRID2020
MAX_STRING_LEN  = 50                               # Limit field length for all rptflds

#######################################################################################
#######################################################################################

class ValuesCheckTool:
    """Main class for performing spatial values checking operations."""
    
    def __init__(self, input_fc: str, id_field: str, ref_table: str, 
                 gispub_path: str, output_path: str):
        
        # Initialise parameters
        self.input_fc = input_fc
        self.id_field = id_field
        self.ref_table = ref_table
        self.gispub_path = gispub_path
        self.output_path = output_path
        
        # Initialise dictionaries
        self.buffer_cache = {}
        self.values_cache = {}
        self.reftab_dict = {}
        self.output_dict = {}

        # Set up performance logging
        perf_log_path = os.path.join(self.output_path, f"{self.get_timestamp()}_script_performance.txt")
        self.perf_log = open(perf_log_path, "w")
        self.progress = 1

        # Set up output CSV
        self.out_csv_path = os.path.join(self.output_path, f"{self.get_timestamp()}_{self.get_basename(self.input_fc)}_ValuesCheck.csv")
        self.output_csv = open(self.out_csv_path, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.output_csv)

        # Setup geoprocessing environment
        arcpy.env.overwriteOutput = True
        arcpy.env.parallelProcessingFactor = "75%"
        arcpy.SetLogHistory(False)
        arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(SPATIAL_REF)
        arcpy.env.cartographicCoordinateSystem = arcpy.SpatialReference(SPATIAL_REF)
        arcpy.env.autoCommit = 1000  # Commit every 1000 operations
        arcpy.env.workspace = r"in_memory" # Much faster than GDB due to disk operations
        
    def run(self) -> None:
        """Execute the main values checking process."""

        try:
            self.logMessage('info', f"Starting values checking for {self.get_basename(self.input_fc)} at {self.get_timestamp()}")
            self.logMessage('info', f" - - - - -")
            # STEP 1. Cache values feature classes and adds details to reftab_dict
            self.load_values_fcs(self.ref_table)

            # STEP 2. Cache works feature class and buffers
            self.load_and_buffer_works_fc(self.input_fc)

            # STEP 3. Create output dictionary to store intersecting values
            self.create_output_dict(self.input_fc, self.reftab_dict)

            # STEP 4. Process intersections between works and values data and add to output dictionary
            self.logMessage('info', f" - - - - -")
            self.logMessage('info', f"Intersecting {len(self.reftab_dict)} values layers")
            for fc_name in self.reftab_dict:
                self.process_intersections(fc_name)

            # STEP 5. Create output report
            self.data_to_csv()

            self.logMessage('info', f" - - - - -")
            self.logMessage('info', f"Script completed. Total values layers processed: {len(self.reftab_dict)}")
            
        except Exception as e:
            self.logMessage('error', f"Error in main execution: {str(e)}")
            raise
    
    def data_to_csv(self) -> None:
        """
        Convert the populated output dictionary to a formatted CSV file.
        Calls helper method to combine multiple intersections (results) into a single string.
        """

        try:
            # localise dictionary
            output_dict = self.output_dict
                
            # create header row
            header = [self.id_field]
            first_feature = next(iter(output_dict.values()))
            theme_names = list(first_feature.keys())
            for theme in theme_names:
                header.append(theme)

            # write header to output CSV
            self.writer.writerow(header)
            
            # step through dict, compiling row data
            for feature_id, feature_data in output_dict.items():
                row_data = [feature_id]

                for theme in theme_names:

                    # retrieve method and buffer distance for current theme from reftab
                    for fc_name, fc_data in self.reftab_dict.items():
                        if fc_data["theme_name"] == theme:
                            method = fc_data["method"]
                            buffer_distance = fc_data["buffer_distance"]
                            geometry_type = fc_data["geometry_type"]

                    # get list data for polygon and buffer
                    polygon_data = feature_data[theme]['in_polygon']
                    buffer_data = feature_data[theme]['in_buffer']

                    value_string = self._results_to_string(polygon_data, buffer_data, method, buffer_distance, geometry_type)
                    row_data.append(value_string)
                
                # write row to output CSV
                self.writer.writerow(row_data)

            self.output_csv.close()
            self.logMessage('info', f" - - - - -") 
            self.logMessage('info', f"Results written to CSV: {self.out_csv_path}") 

        except Exception as e:
            self.logMessage('error', f"Error while creating CSV file: {str(e)}") 

    def _results_to_string(self, list_poly: list, list_buff: list, method: str, buffer_distance: int, geometry_type: str) -> List:
        """
        Format intersection results into readable strings based on analysis method.
        Handles PRESENT, COUNT, and MEASURE methods with appropriate units and formatting.
        Returns formatted string combining polygon and buffer results with unique results 
        for each feature id/theme separated by CSV line breaks.
        """

        try:
            # temporary storage and mapping
            attrs_poly = []
            attrs_buff = []

            data_mapping = {
                "poly": (list_poly, attrs_poly),
                "buff": (list_buff, attrs_buff)
            }
            
            if buffer_distance > 0:
                locations = ["poly", "buff"]
            else:
                locations = ["poly"]

            for location in locations:
                input, output = data_mapping[location]

                # Handle situation where no values exist or all values are empty
                if not any(input):
                    output.append("Nil") # populate with string "Nil" if list empty
                else:
                    for value in input:   
                        if method.upper() == "PRESENT":
                            # set default value string
                            val_str = "Nil"
                            # Format as: "first (second | third | fourth)"
                            if len(value) > 1:
                                val_str = f"{value[0]} ({' | '.join(map(str, value[1:]))})"
                            elif any(value):
                                val_str = str(value[0])
                        elif method.upper() == "COUNT":
                            # Format as: "first (second | third) - count"
                            if len(value) > 1:
                                count = value[-1]  # Last element is the count
                                if len(value) > 2:
                                    val_str = f"{value[0]} ({' | '.join(map(str, value[1:-1]))}) - {count}"
                                else:
                                    val_str = f"{value[0]} - {count}"
                            elif any(value):
                                val_str = str(value[0])
                        elif method.upper() == "MEASURE":
                            # Format as: "first (second | third) - measure"
                            if geometry_type == "POLYGON":
                                meas_str = "ha"
                            elif geometry_type == "POLYLINE":
                                meas_str = "km"
                            else:
                                meas_str = ""

                            if len(value) > 1:
                                measure = value[-1]  # Last element is the measure
                                if len(value) > 2:
                                    val_str = f"{value[0]} ({' | '.join(map(str, value[1:-1]))}) - {measure:.1f}{meas_str}"
                                else:
                                    val_str = f"{value[0]} - {measure:.1f}{meas_str}"
                            elif any(value):
                                val_str = str(value[0])
                        output.append(val_str)
                    
                    # sort strings
                    output.sort()

            # if theme has a buffer, format with 'Inside feature:' and 'In XXXm buffer:'
            if buffer_distance > 0:
                values_string = (
                    'In polygon:' +
                    ('\r\n' if attrs_poly[0] != "Nil" else ' ') + # Don't add line break for Nil
                    '\r\n'.join(str(item) for item in attrs_poly) + 
                    f'\r\nIn {buffer_distance}m buffer:' +
                    ('\r\n' if attrs_buff[0] != "Nil" else ' ') + # Don't add line break for Nil
                    '\r\n'.join(str(item) for item in attrs_buff)
                )
            else:
                # if no buffer, just list values found
                values_string = ('In polygon:' +
                    ('\r\n' if attrs_poly[0] != "Nil" else ' ') + # Don't add line break for Nil
                    '\r\n'.join(str(item) for item in attrs_poly)
                )
            
            return values_string
        
        except Exception as e:
            self.logMessage('error', f"Error creating values string: {str(e)}")


    def process_intersections(self, fc_name: str, ) -> None:
        """
        Process spatial intersections for a single values layer.
        Handles both direct polygon intersections and buffer zone intersections,
        calling helper method for actual spatial analysis and result population.
        """
        
        try:
            # localise relevant reftab details
            fc_dict = self.reftab_dict[fc_name]
            values_fc = fc_dict["cached_fc"]
            buffer_dist = fc_dict["buffer_distance"]
            rpt_fields = []
            for key in ["repfld1", "repfld2", "repfld3", "repfld4"]:
                field = fc_dict[key]
                if field and field.strip():  # ignore if empty
                    rpt_fields.append(field)
            query = fc_dict["definition_query"]

            # Get the base works feature class (unbuffered)
            works_base_name = self.get_basename(self.input_fc)
            works_fc = self.buffer_cache.get(works_base_name)

            # log error if unfound
            if works_fc is None:
                self.logMessage('error', f"Could not find base works feature class in cache: {works_base_name}")
                return

            # Process direct intersections (polygon to polygon/point/line)
            self._process_spatial_intersection(works_fc, values_fc, fc_name, "in_polygon", rpt_fields)

            # repeat for buffer if required
            if buffer_dist is not None and buffer_dist > 0:
                # Get the buffered works feature class
                buffer_key = f"{works_base_name}_{buffer_dist}"
                buffered_works_fc = self.buffer_cache.get(buffer_key)
                
                # log error if unfound
                if buffered_works_fc is None:
                    self.logMessage('error', f"Could not find buffered works feature class in cache: {buffer_key}")
                    return
                
                # Process direct intersections (polygon to polygon/point/line)
                self._process_spatial_intersection(buffered_works_fc, values_fc, fc_name, "in_buffer", rpt_fields)
                
            # Track number of layers processed
            self.progress += 1

        except Exception as e:
            self.logMessage('error', f"Error processing intersections for {fc_name}: {str(e)}")

    def _process_spatial_intersection(self, works_fc: str, values_fc: str, fc_name: str, 
                                location_type: str, rpt_fields: List[str]) -> None:
        """
        Perform spatial intersection analysis between one works feature and one values feature.
        Uses ArcPy Intersect tool and populates output dictionary based on analysis method.
        Handles geometry-specific calculations for COUNT and MEASURE methods
        """
        
        try:
            # retrieve parameters from the output dictionary
            theme_name = self.reftab_dict[fc_name]["theme_name"]
            method = self.reftab_dict[fc_name]["method"]
            buffer_distance = self.reftab_dict[fc_name]["buffer_distance"]
            query = self.reftab_dict[fc_name]["definition_query"]
            
            # clear any existing selection on values layer and apply definition query if provided
            arcpy.management.SelectLayerByAttribute(values_fc, "CLEAR_SELECTION")
            if query and query != "":
                arcpy.management.SelectLayerByAttribute(values_fc, "NEW_SELECTION", query)

            # Check what sort of geometry we're looking at
            desc = arcpy.Describe(values_fc)
            geometry_type = desc.shapeType.upper()
            
            # make string for message logging
            if location_type == "in_polygon":
                msg_string = f"between {fc_name} and works polygons ({method})"
            else:
                msg_string = f"between {fc_name} and {buffer_distance}m works buffer ({method})"

            # add works feature identifier and shape to report fields
            out_fields = ["SHAPE@", FEATURE_ID] + rpt_fields

            # temporary feature class name
            joined_fc = f"in_memory\\temporary_joined_data"
            
            # Use one-to-many join so we can process all works at once
            arcpy.analysis.Intersect([works_fc, values_fc], joined_fc)
            intersected_count = int(arcpy.management.GetCount(joined_fc)[0])
            if intersected_count == 0:
                self.logMessage('info', f"{self.progress}/{len(self.reftab_dict)} No intersections found {msg_string}")
                return

            # Step through each row in the join and add to output dictionary if it doesn't already exist
            with arcpy.da.SearchCursor(joined_fc, out_fields) as cursor:
                for row in cursor:
                    shape = row[0]
                    works_feature_id = row[1]

                    # process individual reporting fields identified in reference table
                    field_values = []

                    # some clean up - this needs to be thorough to ensure later robustness
                    for field_value in row[2:]:  # Skip index 0 and 1 (shape & id)
                        
                        if isinstance(field_value, datetime):
                            # if date & time, convert to simplified date string
                            str_val = field_value.strftime('%Y-%m-%d')
                        else:
                            # make sure value is string and remove leading/trailing spaces 
                            str_val = str(field_value).strip()

                        # remove any CSV-breaking elements
                        str_val = str(str_val).replace("'", "").replace(",", ";").replace("\n", "_n")
                        
                        # skip if empty or any variety of no-value
                        if str_val and str_val.lower() not in ['none', 'null', 'nan', '']:
                            # reduce to max characters and add to list field data
                            if len(str_val) > MAX_STRING_LEN:
                                field_values.append(f"{str_val[:MAX_STRING_LEN-3]}...")
                            else:
                                field_values.append(str_val)
                        
                    # add reporting fields (plus count/measure if req.) to output dictionary, as a LIST                    
                    if method.upper() == "PRESENT":
                        # if matching item doesn't exist, add to output dictionary
                        if field_values not in self.output_dict[works_feature_id][theme_name][location_type]:
                            self.output_dict[works_feature_id][theme_name][location_type].append(field_values)
                    
                    elif method.upper() == "COUNT":
                        found = False
                        # if matching item already exists, increment its count field
                        for existing_entry in self.output_dict[works_feature_id][theme_name][location_type]:
                            # compare everything except the last element (which is the count)
                            if existing_entry[:-1] == field_values: # Found a match - increment the count
                                existing_entry[-1] += 1
                                found = True
                                break

                        # if matching item doesn't exist, add to output dictionary with a count of 1
                        if not found:
                            field_values.append(1)  # Add count as last element
                            self.output_dict[works_feature_id][theme_name][location_type].append(field_values)

                    elif method.upper() == "MEASURE":
                        # determine how to calculate the measure field (area or length)
                        if geometry_type == "POLYGON":
                            measure = shape.area/10000  # Area in hectares
                        elif geometry_type == "POLYLINE":
                            measure = shape.length/1000   # Length in kilometers

                        # if matching item already exists, add to its measure field
                        found = False
                        for existing_entry in self.output_dict[works_feature_id][theme_name][location_type]:
                            # compare everything except the last element (which is the measure)
                            if existing_entry[:-1] == field_values: # Found a match - increment the measure
                                existing_entry[-1] += measure
                                found = True
                                break
                        
                        # if matching item doesn't exist, add to output dictionary and populate measure field
                        if not found:
                            field_values.append(measure)  # Add measure as last element
                            self.output_dict[works_feature_id][theme_name][location_type].append(field_values)

                # Clean up temporary feature class
                if arcpy.Exists(joined_fc):
                    arcpy.Delete_management(joined_fc)
            
            self.logMessage('info', f"{self.progress}/{len(self.reftab_dict)} Processed {intersected_count} intersections {msg_string}")
            
        except Exception as e:
            self.logMessage('error', f"Error in spatial intersection processing: {str(e)}")

    def create_output_dict(self, works_fc: str, values_dict: str) -> None:
        """
        Initialise the output dictionary structure for all works features and themes.
        Creates nested dictionary with feature IDs, theme names, and separate storage
        for polygon and buffer intersection results.
        """
        
        try:
            # make a list of required column names - these will be headers for csv
            column_names = []
            for fc_name in self.reftab_dict:
                column_names.append(self.reftab_dict[fc_name]["theme_name"])

            # add all works feature ids
            with arcpy.da.SearchCursor(works_fc, FEATURE_ID) as cursor:
                for row in cursor:
                    feature = row[0]
                    self.output_dict[feature] = {}
                    
                    # populate column names
                    for column_name in column_names:
                        self.output_dict[feature][column_name] = {}

                        #add storage for results inside polygon and inside buffer - note the values storage is a [list] not dict 
                        for location in ["in_polygon", "in_buffer"]:
                            self.output_dict[feature][column_name][location] = []

            self.logMessage('info', f"Created empty output dictionary")

        except Exception as e:
            self.logMessage('error', f"Error creating output dictionary: {str(e)}")
        
    def load_and_buffer_works_fc(self, feature_class: str) -> None:
        """
        Cache the input works feature class and create required buffer zones.
        Determines needed buffer distances from reference table and creates
        in-memory buffered feature classes for efficient spatial analysis.
        """
        try:
            
            self.logMessage('info', f"Caching works and buffers, please be patient...")

            # determine all required buffer distances
            buffer_distances = []

            for fc_name in self.reftab_dict:
                dist = self.reftab_dict[fc_name]["buffer_distance"]
                # check if buffer is required and not already in our list
                if dist > 0 and dist not in buffer_distances:
                    buffer_distances.append(dist)

            # have a look at the feature class (describe)
            desc = arcpy.Describe(feature_class)

            # Copy base features (unbuffered) unless it already exists in cache
            name = desc.baseName
            if name not in self.buffer_cache:
                layer_name = f"{name}_{id(self)}"
                arcpy.management.MakeFeatureLayer(feature_class, layer_name)
                self.buffer_cache[name] = layer_name

            # Create buffered features if requested, unless it already exists in cache
            for distance in buffer_distances:
                buffer_name = f"{desc.baseName}_{distance}"

                if buffer_name not in self.buffer_cache:
                    geometry_type = desc.shapeType.upper()

                    if geometry_type == "POLYGON":
                        side = "OUTSIDE_ONLY"
                    else:
                        side = "FULL"

                    # Use in_memory workspace for buffers with unique naming
                    unique_suffix = id(self)
                    buffer_fc = f"in_memory\\{buffer_name}_{unique_suffix}"
                    layer_name = f"{buffer_name}_layer_{unique_suffix}"
                    
                    arcpy.analysis.Buffer(
                            in_features=feature_class,
                            out_feature_class=buffer_fc,
                            buffer_distance_or_field=f"{distance} meters",
                            line_side=side,
                            line_end_type="ROUND",
                            dissolve_option="NONE",
                            dissolve_field=None,
                            method="PLANAR"
                        )

                    # Create layer from buffer
                    arcpy.management.MakeFeatureLayer(buffer_fc, layer_name)
                    self.buffer_cache[buffer_name] = layer_name

            self.logMessage('info', f"Cached {feature_class} and {len(buffer_distances)} buffers")

        except Exception as e:
            self.logMessage('error', f"Error caching works feature class and buffers: {str(e)}")

    def load_values_fcs(self, reftab: str) -> None:
        """
        Load and cache all values feature classes specified in the reference table.
        Reads reference table, creates feature layers for enabled themes, and
        populates the reftab_dict with analysis parameters and cached layer references.
        """

        try:
            self.logMessage('info', f"Caching values layers, please be patient...")

            # Create empty dictionary
            self.reftab_dict = {}

            # Populate dictionary from reference table
            theme_fields = ["THEMENAME", "CHECK_YN", "DEFAULTWS_YN", "DATA_LOC", "GDB_NAME", "FC_NAME",
                "DEF_QUERY", "CHECK_METHOD", "REPFLD1", "REPFLD2", "REPFLD3", "REPFLD4", "BUFFER_DIST"]
            
            with arcpy.da.SearchCursor(reftab, theme_fields) as cursor:
                for row in cursor:
                    # alias row data for ease of understanding, e.g. fc_name rather than row[4]
                    (theme_name, requires_check, default_ws, location, gdb_name, fc_name, 
                        query, method, repfld1, repfld2, repfld3, repfld4, 
                        buffer_distance) = row

                    # ignore values layer if check not required
                    if requires_check.upper() == "Y":
                        
                        # determine location of feature class
                        if default_ws.upper() == "Y": 
                            values_fc_path = os.path.join(self.gispub_path, location, gdb_name, fc_name)
                        else:
                            values_fc_path = location  # DATA_LOC
                        
                        # Cache values layer with unique name
                        if fc_name not in self.values_cache:
                            layer_name = f"{fc_name}_{id(self)}"
                            arcpy.management.MakeFeatureLayer(values_fc_path, layer_name)
                            self.values_cache[fc_name] = layer_name
                            # self.logMessage('info', f"Cached {fc_name}")

                        # determine geometry type
                        desc = arcpy.Describe(layer_name)
                        geometry_type = desc.shapeType.upper()

                        # Remove " " values from definition queries
                        clean_query = None if not query or not query.strip() else query

                        # Populate reference table dictionary
                        self.reftab_dict[fc_name] = {
                            "theme_name": theme_name,
                            "cached_fc": layer_name,
                            "geometry_type": geometry_type,
                            "method": method,
                            "definition_query": clean_query,
                            "buffer_distance": buffer_distance,
                            "repfld1": repfld1,
                            "repfld2": repfld2,
                            "repfld3": repfld3,
                            "repfld4": repfld4
                        }

            self.logMessage('info', f"Cached {len(self.reftab_dict)} values layers")

        except Exception as e:
            self.logMessage('error', f"Error while loading values feature classes: {str(e)}")

    # UTILITY FUNCTIONS
    @staticmethod
    def get_timestamp() -> str:
        """Return formatted timestamp string."""
        return datetime.now().strftime("%Y%m%d_%H%Mhr")
    
    @staticmethod
    def get_basename(filepath: str) -> str:
        """Extract basename from file path without extension."""
        return os.path.splitext(os.path.basename(filepath))[0]

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

if __name__ == "__main__":

    # Get parameters from ArcGIS Pro tool interface
    input_fc    = arcpy.GetParameterAsText(0) or FEATURE_CLASS   # Input Feature Class
    id_field    = arcpy.GetParameterAsText(1) or FEATURE_ID      # Feature ID Field
    ref_table   = arcpy.GetParameterAsText(2) or THEME_REFTAB    # Theme Reference Table
    gispub_path = arcpy.GetParameterAsText(3) or GISPUB_PATH     # Location of local copy of gis_public
    output_path = arcpy.GetParameterAsText(4) or OUT_PATH        # Output Path
    
    try:
        # Validate inputs
        if not arcpy.Exists(input_fc):
            raise ValueError(f"Input feature class does not exist: {input_fc}")
        if not arcpy.Exists(ref_table):
            raise ValueError(f"Reference table does not exist: {ref_table}")
        if not os.path.exists(gispub_path):
            raise ValueError(f"GIS public location does not exist: {gispub_path}")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)
        
        # Create and run the tool
        tool = ValuesCheckTool(input_fc, id_field, ref_table, gispub_path, output_path)
        tool.run()
        
        arcpy.AddMessage("Values check completed successfully!")
        
    except Exception as e:
        arcpy.AddError(f"Script execution failed: {str(e)}")
        raise
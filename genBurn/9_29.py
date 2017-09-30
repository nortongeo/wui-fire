#-------------------------------------------------------------------------------
# Name:        genFuel Tool
# Purpose:     Takes raw naip and raw heights data and segments the data into
#              objects and classifies these objects using a fuzzy classifier
#              rule and the SVM algorithm. Once objects are classified, they
#              are prepared as ASCIIs to be burned in FlamMap.
#
#             Primary Steps:
#               - Segment heights into unique objects using SMS
#               - Calculate and join mean height to objects with Zonal Stastics
#               - Separate ground and nonground features and mask naip
#               - Classify objects using fuzzy classifier rule in 2 stages
#               - Use classified vegetation objects as training samples for SVM
#               - Run SVM and use output to classify 'confused' objects
#               - Assign all objects a fuel model
#               - Create Landscape file (.LCP)
#               - Burn LCP using FlamMap (outputs in default)
#               - Fire line intensity, flame length, and rate of spread calculated
#               - Maximum potential static fire behavior joined back to objects
#               - Pipeline/infrastructure (if present) is assessed by incident threat

# Author:      Peter Norton
#
# Created:     05/25/2017
# Updated:     09/22/2017
# Copyright:   (c) Peter Norton and Matt Ashenfarb 2017
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
# USER LOG
date = "9_28"
# Summary
#
#
#

# Geographic Data
location_name = "Tahoe"
bioregion = "Tahoe" #[Tahoe, Richmond]
projection = "UTMZ10"  #["UTMZ10", "UTMZ11", "SPIII", "SPIV"]

# Settings
coarsening_size = "5" #meters
tile_size = "1" #square miles
model = "13"  # Fuel Model set
pipe_analysis = "yes"  # Assess infrastructure
buff_distance = "1000 feet" # Buffer around infrastructure

# inputs
input_bnd = "bnd.shp" 
input_naip = "naip.tif"
input_heights = "heights.tif"
input_dem = "dem.tif"
input_pipeline = "pipeline.shp"

input_fuel_moisture = "fuel_moisture.fms"
input_wind = ""
input_weather = ""
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Processing - DO NOT MODIFY BELOW
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Import modules
import arcpy
import os
import sys
import shutil
from arcpy import env
from arcpy.sa import *

# Overwrite Setting
arcpy.env.overwriteOutput = True
script_db = "K:\\TFS_Fire\\Tools"
#-----------------------------------------------
#-----------------------------------------------


#-----------------------------------------------
#-----------------------------------------------
# File Structure
folder_structure = [
  "Scripts",
  "Inputs",
  "Outputs",
  "Scratch"
]

# Dependent scripts
dependent_scripts = [
  "thresholdsLib.py",
  "tableJoin.py"
]

# Dependent dlls 
dependent_dlls = [
  "GenLCPv2.dll",
  "FlamMapF.dll"
]
# Create new project folder and set environment
scriptpath = sys.path[0] # Find script
toolpath = os.path.dirname(scriptpath)  # Find parent directory
current_project = os.path.join(toolpath)
if os.path.basename(toolpath) == date:
  arcpy.AddMessage("File structure is setup.")
elif os.path.basename(scriptpath) != date:
    if os.path.basename(scriptpath) == "Scripts":
      new_toolpath = os.path.dirname(toolpath)
      current_project = os.path.join(new_toolpath,date)
    else:
      current_project = os.path.join(toolpath,date)
    os.makedirs(current_project)        # Make new project folder
    for folder_name in folder_structure:
      folder = os.path.join(current_project, folder_name)
      os.makedirs(folder)
      if folder_name == "Inputs":
        if os.path.basename(scriptpath) == "Scripts":
          input_path = os.path.join(toolpath, "Inputs")
          for root, dirs, inputs in os.walk(scriptpath):
            for input_file in inputs:
              script_folder = os.path.join(current_project, "Scripts")
              base=os.path.basename(input_file)
              extension = os.path.splitext(input_file)[1]
              if extension == ".py" and input_file not in dependent_scripts:
                arcpy.Copy_management(input_file, os.path.join(script_folder, date+".py")) # copies main to script folde
              else:
                arcpy.Copy_management(input_file, os.path.join(script_folder, base))
        else:
          input_path = scriptpath
        for root, dirs, inputs in os.walk(input_path):
          for input_file in inputs:
            base=os.path.basename(input_file)
            extension = os.path.splitext(input_file)[1]
            
            if extension not in [".py", ".tbx"]:
                              
              input_folder = os.path.join(current_project, folder_name)
              arcpy.Copy_management(os.path.join(input_path,input_file), os.path.join(input_folder, base)) # copies main to script folder
            else:
              input_folder = os.path.join(current_project, "Scripts")
              if extension == ".py":
                arcpy.Copy_management(input_file, os.path.join(input_folder, date)) # copies main to script folde
              else:
                arcpy.Copy_management(input_file, os.path.join(input_folder, base)) # copies main to script folde
      elif folder_name == "Scratch":
        arcpy.CreateFileGDB_management(folder, "Scratch.gdb")
      elif folder_name == "Scripts":
        input_folder = os.path.join(current_project, folder_name)
              
        for dependent_script in dependent_scripts:
          shutil.copy2(os.path.join(script_db, dependent_script), os.path.join(input_folder, dependent_script)) # copies main to script folder 
        for dependent_dll in dependent_dlls:
          shutil.copy2(os.path.join(script_db, dependent_dll), os.path.join(input_folder, dependent_dll)) # copies main to script folder 
  #os.remove(scriptpath)

# Dependent scripts
from tableJoin import one_to_one_join
from thresholdsLib import get_thresholds

#Setting inputs, outputs, scratchws, scratch.gdb
inputs = os.path.join(current_project, "Inputs")
outputs = os.path.join(current_project, "Outputs")
scratchws = os.path.join(current_project, "Scratch") 
scratchgdb = os.path.join(scratchws, "Scratch.gdb")   
dll_path = os.path.join(current_project, "Scripts")

#-----------------------------------------------
#-----------------------------------------------
# Set Global Variables
# Raw inputs
raw_naip = os.path.join(inputs, input_naip) # NAIP Imagery at 1m res
raw_heights = os.path.join(inputs, input_heights) # Heights
raw_dem = os.path.join(inputs, input_dem) # DEM
pipeline = os.path.join(inputs, input_pipeline) # Pipeline 
fuel_moisture = os.path.join(inputs, input_fuel_moisture) # Fuel Moisture
wind = os.path.join(inputs, input_wind) # Wind
weather = os.path.join(inputs, input_weather) # Weather
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Set Create Layers
# Inputs
bnd_zones = os.path.join(inputs, input_bnd) # Bounding box for each tile

# Outputs
classified = os.path.join(outputs, "classified.shp")
analysis_area = bnd_zones  # analysis area/ area of interest
dem = os.path.join(outputs, "dem.tif")  # Resampled DEM in native units 
heights = os.path.join(outputs, "heights.tif")  # Resampled heights in native units
scaled_heights = os.path.join(outputs, "scaled_heights.tif")  # Heights in project units
scaled_dem = os.path.join(outputs, "scaled_dem.tif")  # DEM in project units

naip = os.path.join(outputs, "naip.tif")  # NAIP in project units
naip_b1 = os.path.join(naip, "Band_1")
naip_b2 = os.path.join(naip, "Band_2")
naip_b3 = os.path.join(naip, "Band_3")
naip_b4 = os.path.join(naip, "Band_4")
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Alert function with step counter
count = 1
def generateMessage(text):
  global count
  arcpy.AddMessage("Step " + str(count) + ": " +text),
  count += 1

# Details
arcpy.AddMessage("Site: "+location_name)
arcpy.AddMessage("Projection: "+projection)
arcpy.AddMessage("Resolution: "+coarsening_size + "m")
arcpy.AddMessage("Fuel Model: "+model)
arcpy.AddMessage("-----------------------------")
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Projection and scaling information
if projection == "UTMZ10":
  scale_height = 1
  scale_naip = 1
  unit = "Meters"
  projection = "PROJCS['NAD_1983_UTM_Zone_10N',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Transverse_Mercator'],PARAMETER['False_Easting',500000.0],PARAMETER['False_Northing',0.0],PARAMETER['Central_Meridian',-123.0],PARAMETER['Scale_Factor',0.9996],PARAMETER['Latitude_Of_Origin',0.0],UNIT['Meter',1.0]]"
elif projection == "UTMZ11":
  scale_height = 1
  scale_naip = 1
  unit = "Meters"
  projection = "PROJCS['NAD_1983_UTM_Zone_11N',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Transverse_Mercator'],PARAMETER['False_Easting',500000.0],PARAMETER['False_Northing',0.0],PARAMETER['Central_Meridian',-117.0],PARAMETER['Scale_Factor',0.9996],PARAMETER['Latitude_Of_Origin',0.0],UNIT['Meter',1.0]]"
elif projection == "SPIII":
  scale_height = 1
  scale_naip = 3.28084
  unit = "Feet"
  projection = "PROJCS['NAD_1983_StatePlane_California_III_FIPS_0403_Feet',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Lambert_Conformal_Conic'],PARAMETER['False_Easting',6561666.666666666],PARAMETER['False_Northing',1640416.666666667],PARAMETER['Central_Meridian',-120.5],PARAMETER['Standard_Parallel_1',37.06666666666667],PARAMETER['Standard_Parallel_2',38.43333333333333],PARAMETER['Latitude_Of_Origin',36.5],UNIT['Foot_US',0.3048006096012192]]"
elif projection == "SPIV":
  scale_height = 1
  scale_naip = 3.28084
  unit = "Feet"
  projection = "PROJCS['NAD_1983_StatePlane_California_VI_FIPS_0406_Feet',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Lambert_Conformal_Conic'],PARAMETER['False_Easting',6561666.666666666],PARAMETER['False_Northing',1640416.666666667],PARAMETER['Central_Meridian',-116.25],PARAMETER['Standard_Parallel_1',32.78333333333333],PARAMETER['Standard_Parallel_2',33.88333333333333],PARAMETER['Latitude_Of_Origin',32.16666666666666],UNIT['Foot_US',0.3048006096012192]]"
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
arcpy.AddMessage("-----------------------------")
arcpy.AddMessage("Processing Started.")
arcpy.AddMessage("-----------------------------")


#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Aligning cells."
generateMessage(text)
# Resample NAIP Imagery, heights, and DEM to 
# align cells and scale measurements to 
# projection. Resampled layers will be saved to 
# 'Outputs' folder

#NAIP
naip = os.path.join(outputs,"naip_"+coarsening_size+"m.tif")
bnd_zones_rast = os.path.join(scratchgdb, "bnd_zones_rast")
cell_size = int(int(coarsening_size)*scale_naip)
naip_cell_size = str(cell_size) +" "+str(cell_size)
arcpy.Resample_management(raw_naip, naip, naip_cell_size, "BILINEAR") # Bilinear Interpolation reduce image distortion when scaling.It linearly interpolates the nearest 4 pixels
arcpy.DefineProjection_management(naip, projection)
bands = ["Band_1","Band_2","Band_3","Band_4"] # NAIP has 4 bands (in increasing order) B,G,R,NIR

# Create a fitted, resampled boundary
this = Int(Raster(naip)*0)  
this.save(bnd_zones_rast)
arcpy.DefineProjection_management(bnd_zones_rast, projection)
arcpy.RasterToPolygon_conversion(bnd_zones_rast, bnd_zones, "NO_SIMPLIFY", "Value")
  


## Segment bnd zones into fishnet according to maximum tile size
arcpy.AddField_management(bnd_zones, "Shape_area", "DOUBLE")
exp = "!SHAPE.AREA@SQUAREMETERS!"
arcpy.CalculateField_management(bnd_zones, "Shape_area", exp, "PYTHON_9.3")
searchcursor = arcpy.SearchCursor(bnd_zones)
area = searchcursor.next()
naip_area = area.getValue("Shape_area")
if naip_area > (int(tile_size)*1609):
 #number_of_pixels = naip_area * Float(1609.34/5)
 desc = arcpy.Describe(bnd_zones)
 extent = desc.extent
 X_axis = extent.XMax - extent.XMin
 Y_axis = extent.YMax - extent.YMin
 num_rows = Int(Y_axis/(int(tile_size)*1609))
 num_columns = Int(X_axis/(int(tile_size)*1609))

 text = "Creating tiles."
 generateMessage(text)
 #arcpy.CreateFishnet_management(bnd_zones, str(extent.XMin)+" "+str(extent.YMin), str(extent.YMax), "", "", num_rows, num_columns, str(extent.XMax)+" "+str(extent.YMax), "", "", "POLYGON")
 #arcpy.DefineProjection_management(bnd_zones, projection)
 #-----------------------------------------------
 #-----------------------------------------------
 
 #-----------------------------------------------
 #-----------------------------------------------
 #text = "Printing tile structure: "+str(num_rows)+ "x"+str(num_columns)
 #generateMessage(text)

 # Print tiling structure on screen
 cell_rows = ""
 cell_columuns = []
 #for i in range(num_rows):
 #  cell_rows += "[-]"
 #for i in range(num_columns):
 #  arcpy.AddMessage(cell_rows)
 #-----------------------------------------------
 #-----------------------------------------------

 #-----------------------------------------------
 #-----------------------------------------------
#Heights

resample_heights = os.path.join(outputs, "heights_1m.tif")  # 1m heights
arcpy.env.snapRaster = naip
factor = float(cell_size)/float(scale_naip) # scale naiip
arcpy.Resample_management(raw_heights, resample_heights, str(scale_naip) + " " + str(scale_naip), "BILINEAR") # Bilinear Interpolation reduce image distortion when scaling.It linearly interpolates the nearest 4 pixels
this = Aggregate(resample_heights, factor, "MAXIMUM") # Aggregate cells by maximum to preserve max heights
this.save(heights)
this = Float(heights) * scale_height  # scale heights 
this.save(scaled_heights)
arcpy.DefineProjection_management(scaled_heights, projection)
this = ExtractByMask(scaled_heights, bnd_zones_rast) # Extract scaled
this.save(scaled_heights)

#DEM

resample_dem = os.path.join(outputs, "dem_1m.tif")
arcpy.env.snapRaster = naip
factor = float(cell_size)/float(scale_height)
arcpy.Resample_management(raw_dem, resample_dem, str(scale_height) + " " + str(scale_height), "BILINEAR")
this = Aggregate(resample_dem, factor, "MAXIMUM")
this.save(dem)
this = Float(dem) * scale_height
this.save(scaled_dem)
arcpy.DefineProjection_management(scaled_dem, projection)
his = ExtractByMask(scaled_dem, bnd_zones_rast)
this.save(scaled_dem)
#-----------------------------------------------
#-----------------------------------------------

if pipe_analysis == "yes":
 
 #-----------------------------------------------
 #-----------------------------------------------
 text = "Creating "+str(buff_distance)+" buffer around pipeline."
 generateMessage(text)

 #Variables
 pipe_seg = os.path.join(outputs, "pipe_seg.shp")
 pipe_buffer = os.path.join(outputs, "pipe_buffer.shp")
 pipe_rast = os.path.join(scratchgdb, "pipe_rast")
 naip_pipe = os.path.join(scratchgdb, "naip_pipe")
 height_pipe = os.path.join(scratchgdb, "height_pipe")
 pipe_proj = os.path.join(scratchgdb, "pipe_proj")
 bnd_rast = os.path.join(scratchgdb, "bnd_rast")
 bands = ["Band_1","Band_2","Band_3","Band_4"]  
 pipe_bands = []
 analysis_area = pipe_buffer

 # Clip pipeline to study area, buffer pipeline
 arcpy.Clip_analysis(pipeline, bnd_zones, pipe_seg)
 arcpy.PolygonToRaster_conversion(bnd_zones, "FID", bnd_rast, "CELL_CENTER", "", int(coarsening_size))
 arcpy.Buffer_analysis(pipe_seg, pipe_buffer, buff_distance, "", "", "ALL")
 arcpy.PolygonToRaster_conversion(pipe_buffer, "FID", pipe_rast, "CELL_CENTER")
 arcpy.ProjectRaster_management(pipe_rast, pipe_proj, bnd_zones, "BILINEAR", str(cell_size) +" "+str(cell_size))
 arcpy.RasterToPolygon_conversion(pipe_proj, pipe_buffer, "NO_SIMPLIFY")

   
 # Extract NAIP and heights to pipeline buffer
 this = ExtractByMask(naip, pipe_buffer)
 this.save(naip_pipe)

 for band in bands:
   band_ras = os.path.join(scratchgdb, band)
   naip_band = os.path.join(naip_pipe, band)
   outRas = Con(IsNull(naip_band),0, naip_band)
   outRas.save(band_ras)
   pipe_bands.append(band_ras)
 arcpy.CompositeBands_management(pipe_bands, naip)
 arcpy.DefineProjection_management(naip, projection)

 this = ExtractByMask(scaled_heights, pipe_buffer)
 this.save(height_pipe)
 outRas = Con(IsNull(height_pipe),0, Raster(height_pipe))
 outRas.save(scaled_heights)
 #-----------------------------------------------
 #-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
# Iterate through all zones (if possible)
searchcursor = arcpy.SearchCursor(bnd_zones)
zones = searchcursor.next()
while zones:
 field = "FID"
 zone_num = zones.getValue(field)
 text = "Extracting NAIP and heights by zone "+str(zone_num)+" boundary."
 generateMessage(text)

 #Variables
 bnd = os.path.join(outputs, "zone_"+str(zone_num)+".shp")
 bnd_rast = os.path.join(outputs, "bnd.tif")
 where_clause = field+" = " + str(zone_num)
 naip_zone = os.path.join(outputs, "naip_zone_"+str(zone_num)+".tif")
 naip_zone_b1 = os.path.join(naip_zone, "Band_1")
 naip_zone_b2 = os.path.join(naip_zone, "Band_2")
 naip_zone_b3 = os.path.join(naip_zone, "Band_3")
 naip_zone_b4 = os.path.join(naip_zone, "Band_4")                        
 heights_zone = os.path.join(outputs, "height_zone_"+str(zone_num)+".tif")
 naip_sms = os.path.join(scratchgdb, "naip_sms_"+str(zone_num))
 sms_fc = os.path.join(scratchgdb, "sms_fc_"+str(zone_num))
 lst_merge = []
 veg_lst = []
 imp_lst = []

 # Create zone boundary and extract NAIP and heights

 arcpy.Select_analysis(bnd_zones, bnd, where_clause)
 this = ExtractByMask(naip, bnd)
 this.save(naip_zone)
 this = ExtractByMask(scaled_heights, bnd)
 this.save(heights_zone)
 #-----------------------------------------------
 #-----------------------------------------------
 
 #-----------------------------------------------
 #-----------------------------------------------
 text = "Creating ground and non-ground surfaces."
 generateMessage(text)

 #Variables
 ground_mask_poly = os.path.join(scratchgdb, "ground_mask_poly")
 nonground_mask_poly = os.path.join(scratchgdb, "nonground_mask_poly")
 ground_mask_raw = os.path.join(scratchgdb, "ground_mask_raw")
 nonground_mask_raw = os.path.join(scratchgdb, "nonground_mask_raw")
 ground_dissolve_output = os.path.join(scratchgdb, "ground_mask_dis")
 nonground_dissolve_output = os.path.join(scratchgdb, "nonground_mask_dis")
 ground_mask_raster = os.path.join(scratchgdb, "ground_mask_raster")
 nonground_mask_raster = os.path.join(scratchgdb, "nonground_mask_raster")
 nonground_mask_resample = os.path.join(scratchgdb, "nonground_mask_resample")
 ground_mask_resample = os.path.join(scratchgdb, "ground_mask_resample")

 #Find minimum cell area
 min_cell_area = int(float(str(arcpy.GetRasterProperties_management(naip, "CELLSIZEX", "")))**2)+1
 where_clause = "Shape_Area > " + str(min_cell_area)

 # Create masks for ground and nonground features according to ground_ht_threshold
 if unit == "Meters":
   ground_ht_threshold = 0.6096
 elif unit == "Feet":
   ground_ht_threshold = 2

 mask = SetNull(Int(heights_zone),Int(heights_zone),"VALUE > " + str(ground_ht_threshold))
 arcpy.RasterToPolygon_conversion(mask, ground_mask_raw, "NO_SIMPLIFY", "VALUE", )
 arcpy.Dissolve_management(ground_mask_raw, ground_dissolve_output)

 # Find cell size of imagery
 cell_size = str(arcpy.GetRasterProperties_management(naip, "CELLSIZEX", ""))

 # A process of clipping polygons and erasing rasters
 arcpy.Erase_analysis(bnd, ground_dissolve_output, nonground_mask_raw)
 arcpy.PolygonToRaster_conversion(nonground_mask_raw, "OBJECTID", nonground_mask_raster, "CELL_CENTER", "", cell_size)
 arcpy.RasterToPolygon_conversion(nonground_mask_raster, nonground_mask_raw, "NO_SIMPLIFY", "VALUE")
 arcpy.Select_analysis(nonground_mask_raw, nonground_mask_poly, where_clause)
 arcpy.Erase_analysis(bnd, nonground_mask_poly, ground_mask_poly)
 arcpy.PolygonToRaster_conversion(ground_mask_poly, "OBJECTID", ground_mask_raster, "CELL_CENTER", "", cell_size)
 arcpy.RasterToPolygon_conversion(ground_mask_raster, ground_mask_raw, "NO_SIMPLIFY", "VALUE")
 arcpy.Select_analysis(ground_mask_raw, ground_mask_poly, where_clause)
 arcpy.Erase_analysis(bnd, ground_mask_poly, nonground_mask_poly)
 #-----------------------------------------------
 #-----------------------------------------------

 #-----------------------------------------------
 #-----------------------------------------------
 # Segment each surface separately using SMS
 spectral_detail = 20
 spatial_detail = 20
 min_seg_size = 1

 surfaces = ["ground", "nonground"]
 naip_lst = []
 ground_mask_poly = []

 for surface in surfaces:

   #-----------------------------------------------
   #-----------------------------------------------
   text = "Extracting NAIP imagery by "+ surface + " mask."
   generateMessage(text)
   
   #Variables
   sms_raster = os.path.join(scratchgdb, surface+"_sms_raster")
   naip_fc =  os.path.join(scratchgdb, surface + "_naip_fc")
   mask_poly = os.path.join(scratchgdb, surface+ "_mask_poly")
   mask = mask_poly
   sms = os.path.join(scratchgdb, surface+"_sms")
   naip_mask = os.path.join(scratchgdb,surface + "_naip")
   mask_raw = os.path.join(scratchgdb, surface + "_mask_raw")
   dissolve_output = os.path.join(scratchgdb, surface + "_mask_dis")

   this = ExtractByMask(naip_zone, mask)
   this.save(naip_mask)
   surface_raster_slide = Con(IsNull(Float(naip_mask)),-10000,Float(naip_mask))
   #-----------------------------------------------
   #-----------------------------------------------

   #-----------------------------------------------
   #-----------------------------------------------
   text = "Segmenting NAIP imagery into "+ surface + " objects."
   generateMessage(text)
   
   # Creating objects and clipping to surface type
   seg_naip = SegmentMeanShift(surface_raster_slide, spectral_detail, spatial_detail, min_seg_size) #, band_inputs)
   seg_naip.save(sms_raster)
   arcpy.RasterToPolygon_conversion(sms_raster, naip_fc, "NO_SIMPLIFY", "VALUE")
   arcpy.Clip_analysis(naip_fc, mask_poly, sms)
   naip_lst.extend([sms])
   #-----------------------------------------------
   #-----------------------------------------------
 
 #-----------------------------------------------
 #-----------------------------------------------
 text = "Merging ground and nonground objects."
 generateMessage(text)

 # Merge surface layers, clip to pipe buffer
 sms_full = os.path.join(scratchgdb, "sms_full")
 arcpy.Merge_management(naip_lst, sms_full)
 arcpy.Clip_analysis(sms_full, bnd, sms_fc)

 # Update Join IDs
 arcpy.AddField_management(sms_fc, "JOIN", "INTEGER")
 rows = arcpy.UpdateCursor(sms_fc)
 i = 1
 for row in rows:
   row.setValue("JOIN", i)
   rows.updateRow(row)
   i+= 1

 #-----------------------------------------------
 #-----------------------------------------------
 # Create Image Enhancements and join to objects
 
 #Attributes used for classification
 image_enhancements = ["ndvi", "ndwi", "gndvi", "osavi", "height"]


 def normalize(index):
     return (2 * (Float(index) - Float(index.minimum)) / (Float(index.maximum) - Float(index.minimum))) - 1

 def createImageEnhancements(x, join, cell_size, created_enhancements):

    for field in image_enhancements:
     # -----------------------------------------------
     # -----------------------------------------------
     
     # -----------------------------------------------
     # -----------------------------------------------
     text = "Computing " + field + " at "+coarsening_size+"m."
     generateMessage(text)
     
     #Variables
     enhancement_path = os.path.join(scratchgdb, field+"_"+str(zone_num))
     outTable = os.path.join(scratchgdb, "zonal_"+field)

     # Equations
     if field == "ndvi":
       inValueRaster = ((Float(naip_zone_b4))-(Float(naip_zone_b1))) / ((Float(naip_zone_b4))+(Float(naip_zone_b1)))
       inValueRaster.save(enhancement_path)
       ie = enhancement_path
     elif field == "ndwi":
       inValueRaster = ((Float(naip_zone_b2))-(Float(naip_zone_b4))) / ((Float(naip_zone_b2))+(Float(naip_zone_b4)))
       inValueRaster.save(enhancement_path)
       ie = enhancement_path
     elif field == "gndvi":
       inValueRaster = ((Float(naip_zone_b4))-(Float(naip_zone_b2))) / ((Float(naip_zone_b4))+(Float(naip_zone_b2)))
       inValueRaster.save(enhancement_path)
       ie = enhancement_path
     elif field == "osavi":
       inValueRaster = normalize((1.5 * (Float(naip_zone_b4) - Float(naip_zone_b1))) / ((Float(naip_zone_b4)) + (Float(naip_zone_b1)) + 0.16))
       inValueRaster.save(enhancement_path)
       ie = enhancement_path
     elif field == "height":
       enhancement_path = heights_zone
     created_enhancements.append(enhancement_path)
     # -----------------------------------------------
     # -----------------------------------------------

     # -----------------------------------------------
     # -----------------------------------------------
     if join == "yes":
       text = "Joining mean " + field + " to each object."
       generateMessage(text)
     
       # Calculating zonal mean and joining to object
       z_stat = ZonalStatisticsAsTable(sms_fc, "JOIN", enhancement_path, outTable, "NODATA", "MEAN")

       arcpy.AddField_management(outTable, field, "FLOAT")
       arcpy.CalculateField_management(outTable, field, "[MEAN]")
       one_to_one_join(sms_fc, outTable, field, "FLOAT")
    return created_enhancements

 created_enhancements_1m = createImageEnhancements(image_enhancements, "yes", "1", [])
 arcpy.DefineProjection_management(sms_fc, projection)
 #-----------------------------------------------
 #-----------------------------------------------

 #-----------------------------------------------
 #-----------------------------------------------
 # Fuzzy rule classifier
 #
 #Primitive types = [vegetation, impervious, water, confusion]
 #Land cover types = [tree, shrub, grass, pavement, building, water]
 #
 # Stages:
 #   1. Classify object based on majority primitive type
 #   2. Classify each primitive object based on IE and height

 def classify(stage, landcover, field):
   if stage == "S1":
     if field == "S1_grid":
       threshold = get_thresholds(bioregion, stage, landcover, field, unit)
       healthy = threshold[0]
       dry = threshold[1]
       return("def landcover(x):\\n"+
              "  if x "+healthy+":\\n"+
              "    return \"healthy\"\\n"+
              "  elif x "+dry+":\\n"+
              "    return \"senescent\"\\n"+
              "  return \"impervious\""
              )
   
     elif field == "S1_ndvi":
       threshold = get_thresholds(bioregion, stage, landcover, field, unit)
       imp = threshold[0]
       veg = threshold[1]
       return ("def landcover(x):\\n"+
              "  membership = \"\"\\n"+
              "  if "+imp+":\\n"+
              "    membership += \"I\"\\n"+
              "  if "+veg+":\\n"+
              "    membership += \"V\"\\n"+
              "  return membership\\n"
              )

     elif field == "S1_ndwi":
       threshold = get_thresholds(bioregion, stage, landcover, field, unit)
       imp = threshold[0]
       veg = threshold[1]
       return ("def landcover(x):\\n"+
              "  membership = \"\"\\n"+
              "  if "+imp+":\\n"+
              "    membership += \"I\"\\n"+
              "  if "+veg+":\\n"+
              "    membership += \"V\"\\n"+
              "  return membership\\n"
              )
     
     elif field == "S1_gndv":
       threshold = get_thresholds(bioregion, stage, landcover, field, unit)
       imp = threshold[0]
       veg = threshold[1]
       return ("def landcover(x):\\n"+
              "  membership = \"\"\\n"+
              "  if "+imp+":\\n"+
              "    membership += \"I\"\\n"+
              "  if "+veg+":\\n"+
              "    membership += \"V\"\\n"+
              "  return membership\\n"
              )

     elif field == "S1_osav":
       threshold = get_thresholds(bioregion, stage, landcover, field, unit)
       imp = threshold[0]
       veg = threshold[1]
       return ("def landcover(x):\\n"+
              "  membership = \"\"\\n"+
              "  if "+imp+":\\n"+
              "    membership += \"I\"\\n"+
              "  if "+veg+":\\n"+
              "    membership += \"V\"\\n"+
              "  return membership\\n"
              )
     
     elif field == "S1":
       return("def landcover(a,b,c,d):\\n"+
              "  membership = a+b+c+d\\n"+
              "  V,I = 0,0\\n"+
              "  for m in membership:\\n"+
              "    if m == \"V\":\\n"+
              "      V += 1\\n"+
              "    if m == \"I\":\\n"+
              "      I += 1\\n"+                  
              "  if V > I:\\n"+
              "    return \"vegetation\"\\n"+
              "  elif I > V:\\n"+
              "    return \"impervious\"\\n"+
              "  else:\\n"+
              "    return \"confusion\"\\n"
              )

   elif stage == "S2":
     if landcover == "vegetation":
       if field == "S2_grid":
         threshold = get_thresholds(bioregion, stage, landcover, field, unit)
         dry = threshold[0]
         healthy = threshold[1]
         return("def landcover(x):\\n"+
                "  if x "+dry+":\\n"+
                "    return \"dry\"\\n"+
                "  elif x "+healthy+":\\n"+
                "    return \"healthy\"\\n"+
                "  else:\\n"+
                "    return \"confusion\""
                )
               
       elif field == "S2_heig":
         
         threshold = get_thresholds(bioregion, stage, landcover, field, unit)
         grass = threshold[0]
         shrub = threshold[1]
         tree = threshold[2]
         return("def landcover(x):\\n"+
                "  if "+grass+":\\n"+
                "    return \"grass\"\\n"+
                "  elif "+shrub+":\\n"+
                "    return \"shrub\"\\n"+
                "  elif "+tree+":\\n"+
                "    return \"tree\""
                )
     
       elif field == "S2":
         return("def landcover(x):\\n"+
                "  return x\\n"
                )

     elif landcover == "impervious":
       if field == "S2_heig":
         threshold = get_thresholds(bioregion, stage, landcover, field, unit)
         path = threshold[0]
         building = threshold[1]
         return("def landcover(x):\\n"+
                "  if "+path+":\\n"+
                "    return \"path\"\\n"+
                "  elif "+building+":\\n"+
                "    return \"building\""
                )

       elif field == "S2":
         return ("def landcover(x):\\n"+
                 "  return x\\n"
                 )

 # Assigns classess
 def createClassMembership(stage, landcover, field, field_lst, output):
   if field in stages:
     field_lst = field_lst[:-2]
     fxn = "landcover("+field_lst+")"

   else:
     index = field
     field = stage+"_"+field[:4]
     field_lst += "!"+field+"!, "
     fxn = "landcover(!"+index+"!)"
       
   label_class = classify(stage, landcover, field)
   arcpy.AddField_management(output, field, "TEXT")
   arcpy.CalculateField_management(output, field, fxn, "PYTHON_9.3", label_class)
   return field_lst
 #-----------------------------------------------
 #-----------------------------------------------

 #-----------------------------------------------
 #-----------------------------------------------
 
 # Classifier methods
 stages = ["S1","S2"]
 class_structure = [
                    ["vegetation",
                         ["grass", "shrub", "tree"]],
                    ["impervious",
                         ["building", "path"]]
                   ]

 # Indices used for each stage of classification
 s1_indices = ["ndvi", "ndwi", "gndvi", "osavi"]#, "gridcode"]
 s2_indices = ["height"]#, "gridcode"]

 for stage in stages:
   text = "Executing Stage "+str(stage)+" classification."
   generateMessage(text)

   # Stage 1 classification workflow
   if stage == "S1":
     s1_indices.extend([stage])
     field_lst = ""
     for field in s1_indices:

       # Assign full membership
       if field == "S1":
         text = "Creating primitive-type objects."
         generateMessage(text)
         
         # Classification method
         createClassMembership(stage, "", field, field_lst, sms_fc)

         # Create new shapefiles with primitive classess
         for primitive in class_structure:
             output = os.path.join(outputs, primitive[0]+"_"+str(zone_num)+".shp")
             where_clause = field + " = '" + primitive[0] + "'"
             arcpy.Select_analysis(sms_fc, output, where_clause)
             if primitive == "vegetation":
               veg_lst.append(output)
             else:
               imp_lst.append(output)
             
       # Assign partial membership     
       else:
         text = "Classifying objects by "+field+"."
         generateMessage(text)
         field_lst = createClassMembership(stage, "", field, field_lst, sms_fc)

   # Stage 2 classification workflow
   if stage == "S2":
     s2_indices.extend([stage])
     merge_lst = []
     for primitive in class_structure:
       stage_output = os.path.join(outputs, primitive[0]+"_"+str(zone_num)+".shp")
       landcover = primitive[0]
       field_lst = ""

       for field in s2_indices:
         
         # Assign final membership
         if field == "S2":
           text = "Creating "+primitive[0]+"-class objects."
           generateMessage(text)

           #Classification method
           createClassMembership(stage, landcover, field, field_lst, stage_output)
         
         # Assign partial memberships    
         else:
           text = "Classifying "+primitive[0]+" objects by "+field+"."
           generateMessage(text)
           field_lst = createClassMembership(stage, landcover, field, field_lst, stage_output)

 # iterate through next zone if possible
 zones = searchcursor.next()
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Preparing 'Confused' objects for SVM."
generateMessage(text)

# Variables
confused = os.path.join(outputs, "confused.shp")
veg_join = os.path.join(scratchgdb, "veg_join")
training_samples = os.path.join(outputs, "training_fc.shp")
merged = os.path.join(scratchgdb, "merged_imp_veg")
composite = os.path.join(outputs, "composite.tif")
vegetation = os.path.join(outputs, "vegetation_0.shp")
impervious = os.path.join(outputs, "impervious_0.shp")

# Only vegetation objects are used as training samples for SVM
if len(lst_merge) > 1:
 arcpy.Merge_management(veg_lst, veg_join)
else:
 veg_join = vegetation
arcpy.Dissolve_management(veg_join, training_samples, ["S2"])

# Code note: make sure veg_lst is merged
arcpy.Merge_management(veg_lst + imp_lst, merged) 

# Create dataset with only confused objects                     
arcpy.Erase_analysis (sms_fc, merged, confused)
arcpy.AddField_management(confused, "S2", "TEXT")

# Indices used as bands in raster for SVM
band_lst = ["ndvi", "ndwi", "height"]

# Creating Layer composite
bands_5m = createImageEnhancements(bands, "no", "5", [])
arcpy.CompositeBands_management(bands_5m, composite)
arcpy.DefineProjection_management(composite, projection)
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Preparing training samples for SVM."
generateMessage(text)

# Variables
svm_training = os.path.join(outputs, "svm_training.shp")
training_fields = [["Classname", "TEXT"], ["Classvalue", "LONG"], ["RED", "LONG"], ["GREEN", "LONG"], ["BLUE", "LONG"], ["Count", "LONG"]]
zonal_training = os.path.join(scratchgdb, "zonal_train")

# Adding the appropriate fields for training samples
arcpy.FeatureClassToFeatureClass_conversion (training_samples, outputs, "svm_training")
for field in training_fields:
 field_name = field[0]
 field_type = field[1]
 arcpy.AddField_management(svm_training, field_name, field_type)

# Calculating attributes for training samples
arcpy.AddField_management(svm_training, "JOIN", "INTEGER")
arcpy.CalculateField_management(svm_training, "JOIN", "[FID]")
z_stat = ZonalStatisticsAsTable(svm_training, "JOIN", composite, zonal_training, "NODATA", "ALL")                      
arcpy.AddField_management(svm_training, "COUNT", "LONG")                      
one_to_one_join(svm_training, zonal_training, "COUNT", "INTEGER")
arcpy.CalculateField_management(svm_training, "Classname", "[S2]")
arcpy.CalculateField_management(svm_training, "Classvalue", "[JOIN]")
arcpy.CalculateField_management(svm_training, "RED", 1)
arcpy.CalculateField_management(svm_training, "GREEN", 1)
arcpy.CalculateField_management(svm_training, "BLUE", 1)
arcpy.CalculateField_management(svm_training, "COUNT", "[COUNT]")

# Removing unnecessary fields for training samples
fields = [f.name for f in arcpy.ListFields(svm_training)]
delete_fields = []
for field in fields:
 if field not in ["FID", "Shape", "Shape_Area", "Shape_Length", "Classname", "Classvalue", "RED", "GREEN", "BLUE", "Count"]:
   delete_fields.append(field)
arcpy.DeleteField_management(svm_training, delete_fields)

# Parameters used for SVM
out_definition = os.path.join(outputs, "svm_classifier.ecd")
maxNumSamples = "100"
attributes = "" #[COLOR, SHAPE, etc.]
# No color because color isn't related to land cover type
# No to shape because shape isn't associated with any type
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Classifying composite using Support Vector Machines."
generateMessage(text)

# Variables
svm = os.path.join(scratchgdb, "svm")

# Creating classifier rule from training samples
arcpy.gp.TrainSupportVectorMachineClassifier(composite, svm_training, out_definition, "", maxNumSamples, attributes)

# Classifying raster with pixel-based method, not segmented raster
classifiedraster = ClassifyRaster(composite, out_definition, "")
classifiedraster.save(svm)
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Classifying 'Confused' objects with SVM outputs."
generateMessage(text)

# Variables
zonal_svm = os.path.join(scratchgdb, "zonal_svm")

## Joining zonal majority to confused object
z_stat = ZonalStatisticsAsTable(confused, "JOIN", svm, zonal_svm, "NODATA", "MAJORITY")
arcpy.AddField_management(confused, "MAJORITY", "LONG")
one_to_one_join(confused, zonal_svm, "MAJORITY", "LONG")

# Assigning land cover to 'Confused' objects
def classify_confusion(x):
 grass = "x == 0"
 shrub = "x == 1"
 tree = " x== 2"
 return("def landcover(x):\\n"+
                "  if "+grass+":\\n"+
                "    return \"grass\"\\n"+
                "  elif "+shrub+":\\n"+
                "    return \"shrub\"\\n"+
                "  elif "+tree+":\\n"+
                "    return \"tree\""
                )

fxn = "landcover(!MAJORITY!)"
label_class = classify_confusion("MAJORITY")
arcpy.CalculateField_management(confused, "S2", fxn, "PYTHON_9.3", label_class)
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Creating contiguously classified land cover."
generateMessage(text)

# Merging all layers back together as classified layer
arcpy.Merge_management([confused, vegetation, impervious], classified)
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Assigning fuel models and creating canopy cover assessments."
generateMessage(text)

# Variables
land_cover = classified
land_cover_fields = [["fuel", "S2"], ["canopy", "S2"], ["stand", "height"]]

def classify(model, x):
   
 # Anderson 13 fuel models
 if model == "13":
   building = "99"
   tree = "10"
   shrub = "6"
   grass = "1"
   water = "98"
   path = "99"
 elif model != "13":
   #-----------------------------------------------
   #-----------------------------------------------
   text = "Cannot classify fuels. Only Anderson 13 are available."
   generateMessage(text)
   #-----------------------------------------------
   classify("13", output_field)
 if x == "fuel":
   return ("def classify(x):\\n"+
           "  if x == \"building\":\\n"+
           "    return "+building+"\\n"+
           "  elif x == \"path\": \\n"+
           "    return "+path+"\\n"+
           "  elif x == \"water\":\\n"+
           "    return "+water+"\\n"+
           "  elif x == \"grass\":\\n"+
           "    return "+grass+"\\n"+
           "  elif x == \"shrub\":\\n"+
           "    return "+shrub+"\\n"+
           "  elif x == \"tree\":\\n"+
           "    return "+tree+"\\n"
           )

 elif x == "canopy":
   return ("def classify(x):\\n"+
           "  if x == \"tree\" or x == \"building\":\\n"+
           "    return 50\\n"+ # 75% canopy cover b/c 
           "  return 0"
           )
 # Returns height attribute - May delete if cannot include into .LCP
 elif x == "stand":
   return("def classify(x):\\n"+
          "  return x"
          )

for field in land_cover_fields:
 input_field = field[1]
 output_field = field[0]
 arcpy.AddField_management(land_cover, output_field, "INTEGER")
 fxn = "classify(!"+input_field+"!)"
 label_class = classify(model, output_field)
 arcpy.CalculateField_management(land_cover, output_field, fxn, "PYTHON_9.3", label_class)

#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Fuel complex created."
generateMessage(text)
#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Creating inputs for Landscape File."
generateMessage(text)

# Variables
fuel_lst = ["fuel", "canopy", "stand"]
elevation_lst = ["slope", "elevation", "aspect"]
ascii_layers = []
fuel = os.path.join(outputs, "fuel.asc")

def convertToAscii(x, landscape_elements):
 
 for layer in landscape_elements:

   # Variables
   ascii_output = os.path.join(outputs, layer + ".asc")
   where_clause = layer +" <> 9999"
   temp = os.path.join(scratchgdb, "t_"+layer)
   temp_raster = os.path.join(scratchgdb, "t_"+layer+"_r")
   final = os.path.join(scratchgdb, layer)

   # Selecting layer and converting to raster
   if layer in fuel_lst:
     arcpy.Select_analysis(land_cover, temp, where_clause)
     arcpy.PolygonToRaster_conversion(temp, layer, temp_raster, "CELL_CENTER", "", scaled_dem)
   elif layer in elevation_lst:

     # Calculating elevation derived layers
     if layer == "slope":
       arcpy.Slope_3d(scaled_dem, temp_raster, "DEGREE")
     elif layer == "aspect":
       arcpy.Aspect_3d(scaled_dem, temp_raster)
     elif layer == "elevation":
       temp_raster = scaled_dem

   # Preparing raster for LCP specifications
   arcpy.CopyRaster_management(temp_raster, final, "", "", "0", "NONE", "NONE", "32_BIT_SIGNED","NONE", "NONE", "GRID", "NONE")
   arcpy.DefineProjection_management(temp_raster, projection)

   # Extracting layer by analysis area
   ready = ExtractByMask(final, naip)
   ready.save(temp_raster)

   # Converting to ascii format and adding to list for LCP tool
   arcpy.RasterToASCII_conversion(ready, ascii_output)
   ascii_layers.append(ascii_output)

   text = "The "+layer+" ascii file was created."
   generateMessage(text)

# Coding note: Check to see that lists are concatenated
convertToAscii(land_cover, fuel_lst + elevation_lst)

#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Creating LCP file."
generateMessage(text)

import ctypes
##
### Variables
landscape_file = os.path.join(outputs, "landscape.lcp")
genlcp = os.path.join(dll_path, "GenLCPv2.dll")
Res = landscape_file
Elev = os.path.join(outputs,"elevation.asc")
Slope = os.path.join(outputs,"slope.asc")
Aspect = os.path.join(outputs,"aspect.asc")
Fuel = os.path.join(outputs,"fuel.asc")
Canopy = os.path.join(outputs,"canopy.asc")

# Create LCP
dll = ctypes.cdll.LoadLibrary(genlcp)
fm = getattr(dll, "?Gen@@YAHPBD000000@Z")
fm.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
fm.restype = ctypes.c_int

e = fm(Res, Elev, Slope, Aspect, Fuel, Canopy, "")
if e > 0:
 arcpy.AddError("Error {0}".format(e))

#-----------------------------------------------
#-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "Burning in FlamMap."
#generateMessage(text)

# Burn in FlamMap
#
flamMap = os.path.join(dll_path, "FlamMapF.dll")
dll = ctypes.cdll.LoadLibrary(flamMap)
fm = getattr(dll, "?Run@@YAHPBD000NN000HHN@Z")
fm.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double, ctypes.c_double, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_double]
fm.restype = ctypes.c_int

Landscape = landscape_file
FuelMoist = fuel_moisture
OutputFile = os.path.join(outputs, "Burn")
FuelModel = "-1"
Windspeed = 30.0  # mph
WindDir = 0.0   # Direction angle in degrees
Weather = "-1"
WindFileName = "-1"
DateFileName = "-1"
FoliarMoist = 100 # 50%
CalcMeth = 0    # 0 = Finney 1998, 1 = Scott & Reinhardt 2001
Res = -1.0

e = fm(Landscape, FuelMoist, OutputFile, FuelModel, Windspeed, WindDir, Weather, WindFileName, DateFileName, FoliarMoist, CalcMeth, Res)
if e > 0:
   arcpy.AddError("Problem with parameter {0}".format(e))

burn_metrics = ["fli", "fml", "ros"]

for root, dirs, fm_outputs in os.walk(outputs): #Check to confirm outputs are saved here
    for burn in fm_outputs:
       if burn[-3:].lower() in burn_metrics:
           metric = burn[-3:].lower()
           burn_ascii = os.path.join(outputs, metric+".asc")
           os.rename(os.path.join(outputs, burn), burn_ascii)


text = "Burn complete."
generateMessage(text)
#-----------------------------------------------
#-----------------------------------------------
# Set Cell Size
arcpy.env.snapRaster = naip
cell_size = str(arcpy.GetRasterProperties_management(naip, "CELLSIZEX", ""))
naip_cell_size = cell_size +" " +cell_size
#-----------------------------------------------
#-----------------------------------------------

for metric in burn_metrics:

  #-----------------------------------------------
  #-----------------------------------------------
  text = "Calculating and joining max " + metric + " to each object."
  generateMessage(text)
  #-----------------------------------------------
  #Set variables
  in_ascii_file = os.path.join(outputs, metric + ".asc")
  burn = os.path.join(scratchgdb, metric)
  raw_raster = os.path.join(scratchgdb, metric  + "_raw")
  scaled_raster = os.path.join(outputs, metric +"_scaled.tif")
  raster_resample = os.path.join(outputs, metric + "_res.tif")
  #shift = os.path.join(outputs, metric+".tif")
  outTable = os.path.join(scratchgdb, "zonal_"+metric)
  
  #-----------------------------------------------
  #-----------------------------------------------
  # Convert ascii output to raster and align cells
  arcpy.ASCIIToRaster_conversion(in_ascii_file, raw_raster, "INTEGER")
  arcpy.DefineProjection_management(raw_raster, projection)
  ["fli", "fml", "ros"]
  if metric == "fli":
    unit_scalar = 0.288894658
  elif metric == "fml":
    unit_scalar = 1
  elif metric == "ros":
    unit_scalar = 3.28084
    
  this = Raster(raw_raster)*unit_scalar
  this.save(scaled_raster)
  arcpy.Resample_management(scaled_raster, burn, naip_cell_size, "NEAREST")
  #arcpy.Shift_management(burn, shift, -(int(cell_size)), 0, naip)
  #-----------------------------------------------
  #-----------------------------------------------
  
  #-----------------------------------------------
  #-----------------------------------------------
  # Calculate zonal max and join to each object
  arcpy.CalculateField_management(classified, "JOIN", "[FID]+1")
  z_table = ZonalStatisticsAsTable(classified, "JOIN", burn, outTable, "NODATA", "MAXIMUM")
  arcpy.AddField_management(outTable, metric, "FLOAT")
  arcpy.CalculateField_management(outTable, metric, "[MAX]")
  one_to_one_join(classified, outTable, metric, "FLOAT")
  #-----------------------------------------------
  #-----------------------------------------------

#-----------------------------------------------
#-----------------------------------------------
text = "All burn severity joins are complete."
generateMessage(text)
#-----------------------------------------------
#-----------------------------------------------
#-----------------------------------------------
text = "All processes are complete."
generateMessage(text)
#-----------------------------------------------

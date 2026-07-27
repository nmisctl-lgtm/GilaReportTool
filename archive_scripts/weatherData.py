import xarray as xr
import geopandas as gpd
import pandas as pd
import numpy as np
from rasterstats import zonal_stats
import matplotlib.pyplot as plt
from shapely.geometry import box
import warnings
warnings.filterwarnings('ignore') # 

# ================= 配置参数 =================
YEAR = 2025 # 
SHP_PATH = "config/HydroSurvAreas.shp" # 
CU_ID_COL = "Name"                 
START_DATE = f"{YEAR}-01-01"              # 
END_DATE = f"{YEAR}-12-31"                # 
OUTPUT_CSV = f"CU_gridMET_Monthly_{YEAR}.csv"  # 
# ============================================

print("1. Reading Shapefile and calculating study area boundaries...")
gdf = gpd.read_file(SHP_PATH).to_crs("EPSG:4326")

# Obtain the bounding box of the study area from the shapefile geometry
# Add a small buffer (0.1 degree) to ensure we capture all relevant gridMET pixels around the edges of the polygons
bounds = gdf.total_bounds 
min_lon, min_lat, max_lon, max_lat = bounds[0]-0.1, bounds[1]-0.1, bounds[2]+0.1, bounds[3]+0.1

print("2. Reading gridMET OPeNDAP data (this may take a few seconds)...")
# gridMET 实时 THREDDS OPeNDAP 链接
url_pr = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_pr_1979_CurrentYear_CONUS.nc"
url_tmax = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmx_1979_CurrentYear_CONUS.nc"
url_tmin = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmn_1979_CurrentYear_CONUS.nc"

# Open the datasets using xarray (this does not load all data into memory yet, just opens the connection)
ds_pr = xr.open_dataset(url_pr)
ds_tmax = xr.open_dataset(url_tmax)
ds_tmin = xr.open_dataset(url_tmin)

print("3. Performing spatial clipping and temporal aggregation (downloading necessary data chunks to memory)...")
# gridMET latitude decreases from north to south (49 to 25), so max_lat comes first in the slice
# Only get the data for the specified year and the bounding box of the study area
sub_pr = ds_pr['precipitation_amount'].sel(
    lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(START_DATE, END_DATE)
)
sub_tmax = ds_tmax['daily_maximum_temperature'].sel(
    lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(START_DATE, END_DATE)
)
sub_tmin = ds_tmin['daily_minimum_temperature'].sel(
    lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(START_DATE, END_DATE)
)

# Calculate mean temperature in Celsius (gridMET temperatures are in Kelvin)
sub_tmean = ((sub_tmax + sub_tmin) / 2) - 273.15

# Resample precipitation by summing daily values to get total monthly precipitation (mm)
# Resample temperature by averaging daily values to get mean monthly temperature (°C)
monthly_pr = sub_pr.resample(day='ME').sum(dim='day').compute() # .compute() forces the actual data to be loaded into memory at this point
monthly_tmean = sub_tmean.resample(day='ME').mean(dim='day').compute()

print("4. Extracting Zonal Statistics for each polygon...")
# Get the affine transform of the gridMET data for use in zonal_stats
# Extract the affine transform matrix (for use with rasterstats)
# The spatial resolution is typically 1/24 degree (~0.041666)
transform = monthly_pr.rio.transform()

results = []
time_coords = monthly_pr.day.values # obtain the time coordinates for iteration (these are the end-of-month timestamps after resampling)

# Iterate over each time step (month) and extract zonal statistics for precipitation and temperature
for i, time_val in enumerate(time_coords):
    year = pd.to_datetime(time_val).year
    month = pd.to_datetime(time_val).month
    print(f"   Processing progress: {year} {month}...")
    
    # Extract the 2D array for the current time step (month) for both precipitation and mean temperature
    pr_array = monthly_pr.isel(day=i).values
    tmean_array = monthly_tmean.isel(day=i).values
    
    # Extract precipitation mean (calculate mean of pixels within each polygon, representing the average precipitation depth for that area)
    pr_stats = zonal_stats(gdf, pr_array, affine=transform, stats="mean", nodata=np.nan)
    # Extract temperature mean (calculate mean of pixels within each polygon, representing the average temperature for that area)
    tmean_stats = zonal_stats(gdf, tmean_array, affine=transform, stats="mean", nodata=np.nan)
    
    # Iterate over each polygon and merge results
    for j, row in gdf.iterrows():
        cu_id = row[CU_ID_COL]
        results.append({
            CU_ID_COL: cu_id,
            'Year': year,
            'Month': month,
            'Precip_Total_in': pr_stats[j]['mean']/25.4, # Convert mm to inches
            'Temp_Mean_F': tmean_stats[j]['mean'] * 9/5 + 32 # Convert °C to °F, handle None case
        })

print("5. Saving results...")
df_results = pd.DataFrame(results)
df_results = df_results.sort_values(by=[CU_ID_COL, 'Year', 'Month'])
df_results = df_results.reset_index(drop=True) 
df_results.to_csv(OUTPUT_CSV, index=False)
print(f"✅ Processing complete! Results saved to: {OUTPUT_CSV}")

print("6. Generating gridMET cell polygons for visualization...")

# gridMET spatial resolution is exactly 1/24 degrees (~0.041666)
res = 1 / 24.0
half_res = res / 2

# Get the coordinate arrays from the subsetted dataset
lons = monthly_pr.lon.values
lats = monthly_pr.lat.values

# Create Shapely box polygons for each grid cell center
grid_polys = []
for lon in lons:
    for lat in lats:
        grid_polys.append(box(lon - half_res, lat - half_res, lon + half_res, lat + half_res))

# Convert the list of polygons into a GeoDataFrame
grid_gdf = gpd.GeoDataFrame(geometry=grid_polys, crs="EPSG:4326")

# Filter: Keep only the grids that actually intersect your CU areas
study_grids = gpd.sjoin(grid_gdf, gdf, how="inner", predicate="intersects")

# Drop duplicates in case a single grid cell touches multiple polygons
study_grids = study_grids.drop_duplicates(subset='geometry')

# Plot it instantly in Python
fig, ax = plt.subplots(figsize=(10, 8))
# Plot the gridMET cells in dashed blue
study_grids.boundary.plot(ax=ax, color='blue', linewidth=0.8, linestyle='--', alpha=0.7)
# Plot your CU Areas in bold red
gdf.plot(ax=ax, color='none', edgecolor='red', linewidth=2)

plt.title("gridMET Grids Overlapping HydroSurvAreas")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.show()
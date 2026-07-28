"""
Module: backend/etl_climate.py
Description: 
Spatial ETL pipeline to extract climate data (GridMET) via OPeNDAP, 
perform zonal statistics against irrigated polygons, and compute daylight hours.

STATUS / 状态：Input-extraction module pending production review / 输入提取模块，
尚待生产审查。GridMET 数据质量当前按项目决定暂不重新验证；在 2025 报告使用
前，仍需确认该模块的空间参考、远程服务可用性和输出 QA/QC。
"""

import logging
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import warnings
warnings.filterwarnings('ignore') # Suppress warnings for cleaner logs
from rasterstats import zonal_stats


logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

class ClimateETL:
    """Climate extraction adapter / 气象提取适配器（投产前需审查）。"""
    def __init__(self, gdb_path: str, layer_name: str, year: int, table16_df: pd.DataFrame):
        self.year = year
        self.start_date = f"{year}-01-01"
        self.end_date = f"{year}-12-31"
        self.table_16 = table16_df
        self.layer_name = layer_name

        logging.info(f"Loading Shapefile for {self.year}...")
        gdf_raw = gpd.read_file(gdb_path, layer=layer_name, engine="pyogrio")
        gdf_raw = gdf_raw.set_crs("EPSG:26913", allow_override=True)
        print(f"Original CRS: {gdf_raw.crs}")
        print(f"Original bounds: {gdf_raw.total_bounds}")
        self.gdf = gdf_raw.to_crs("EPSG:4326")

        # Define GridMET OPeNDAP URLs
        self.url_pr = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_pr_1979_CurrentYear_CONUS.nc"
        self.url_tmax = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmx_1979_CurrentYear_CONUS.nc"
        self.url_tmin = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmn_1979_CurrentYear_CONUS.nc"

    def interpolate_daylight_percentage(self, latitude: float, month_idx: int) -> float:
        """
        Calculates monthly daylight percentage / 按纬度线性插值计算月度日照百分比。
        """
        lats = self.table_16.index.values
        if latitude <= lats[0]: return float(self.table_16.iloc[0, month_idx - 1])
        if latitude >= lats[-1]: return float(self.table_16.iloc[-1, month_idx - 1])
        
        for i in range(len(lats) - 1):
            if lats[i] <= latitude <= lats[i + 1]:
                lat1, lat2 = lats[i], lats[i + 1]
                p1 = self.table_16.loc[lat1].iloc[month_idx - 1]
                p2 = self.table_16.loc[lat2].iloc[month_idx - 1]
                return float(p1 + (p2 - p1) * ((latitude - lat1) / (lat2 - lat1)))
        return 0.0

    def run_pipeline(self, polygon_id_column: str = "Name"):
        """
        Extracts GridMET data and returns compute inputs / 提取 GridMET、转换单位、
        执行分区统计并返回计算引擎输入。投产前必须确认空间与服务 QA/QC。
        """
        bounds = self.gdf.total_bounds
        min_lon, min_lat = bounds[0] - 0.1, bounds[1] - 0.1
        max_lon, max_lat = bounds[2] + 0.1, bounds[3] + 0.1
        # debug
        logging.info(f"Bounding box: {min_lon}, {min_lat}, {max_lon}, {max_lat}")
    
        logging.info("Extracting NetCDF data via OPeNDAP connection...")
        
        try:
            ds_pr = xr.open_dataset(self.url_pr)['precipitation_amount'].sel(
                lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))
            ds_tmax = xr.open_dataset(self.url_tmax)['daily_maximum_temperature'].sel(
                lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))
            ds_tmin = xr.open_dataset(self.url_tmin)['daily_minimum_temperature'].sel(
                lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))
        except Exception as e:
            logging.error(f"Failed to connect to GridMET servers: {e}")
            raise

        logging.info("Transforming units (Kelvin -> Fahrenheit, mm -> inches)...")
        daily_tmin_F = (ds_tmin - 273.15) * 1.8 + 32.0
        daily_tmax_F = (ds_tmax - 273.15) * 1.8 + 32.0
        daily_pr_in = ds_pr / 25.4
        daily_tmean_F = (daily_tmax_F + daily_tmin_F) / 2.0

        monthly_tmean_F = daily_tmean_F.resample(day='ME').mean(dim='day').compute()
        monthly_pr_in = daily_pr_in.resample(day='ME').sum(dim='day').compute()

        # monthly_pr_in = monthly_pr_in.rio.set_spatial_dims(x_dim="lon", y_dim="lat")
        # monthly_pr_in = monthly_pr_in.rio.write_crs("epsg:4326")
        # transform = monthly_pr_in.rio.transform()
        daily_tmin_F = daily_tmin_F.compute()
        
        transform = monthly_pr_in.rio.transform()
        
        polygon_ids = self.gdf[polygon_id_column].tolist()#; print(polygon_ids) # Debug: Print polygon IDs to verify correct column
        centroids_lat = self.gdf.geometry.centroid.y.tolist()

        logging.info("Executing Zonal Statistics across all polygons...")
        monthly_results = []
        
        # Outer loop by Time (Monthly) to minimize I/O overhead
        for month_idx in range(1, 13):
            pr_matrix = monthly_pr_in.isel(day=month_idx - 1).values
            tmean_matrix = monthly_tmean_F.isel(day=month_idx - 1).values
            # print(f"Month {month_idx} pr_matrix: {pr_matrix}") # Debug: Print the values of the precipitation matrix for verification
            # print(f"Month {month_idx} tmean_matrix: {tmean_matrix}") # Debug: Print the values of the temperature matrix for verification
            
            pr_zonal = zonal_stats(self.gdf, pr_matrix, affine=transform, 
                                   stats="mean", nodata=np.nan, all_touched=True)
            tmean_zonal = zonal_stats(self.gdf, tmean_matrix, affine=transform, 
                                      stats="mean", nodata=np.nan, all_touched=True)
            # print(f"Month {month_idx} results: {pr_zonal}, {tmean_zonal}") # Debug: Print zonal stats results for verification

            for i, poly_id in enumerate(polygon_ids):
                pr_val = float(pr_zonal[i]['mean']) if pr_zonal[i]['mean'] is not None else 0.0
                tmean_val = float(tmean_zonal[i]['mean']) if tmean_zonal[i]['mean'] is not None else 0.0
                p_pct = self.interpolate_daylight_percentage(centroids_lat[i], month_idx)
                
                monthly_results.append({
                    'Polygon_ID': poly_id, 
                    'Month': month_idx,
                    'T_mean_F': tmean_val,
                    'Precip_in': pr_val,
                    'Daylight_pct_p': p_pct
                })
                
        logging.info("Spatial ETL pipeline completed successfully.")
        return pd.DataFrame(monthly_results), daily_tmin_F, transform

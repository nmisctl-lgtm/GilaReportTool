import xarray as xr
import geopandas as gpd
import pandas as pd
import numpy as np
from rasterstats import zonal_stats
import warnings
warnings.filterwarnings('ignore') # 

class GilaClimateProvider:
    def __init__(self, shp_path, year, table16_csv_path):
        self.year = year
        self.start_date = f"{year}-01-01"
        self.end_date = f"{year}-12-31"
        self.gdf = gpd.read_file(shp_path).to_crs("EPSG:4326")
        self.CU_ID_COL = "Name" # 假设 shapefile 中的 CU ID 列名为 "Name"
        
        # 加载保存的 Table 16 CSV
        self.table_16_df = pd.read_csv(table16_csv_path).set_index("Latitude")

    def _interpolate_daylight(self, lat, month_idx):
        """基于质心纬度插值 Table 16 的日照百分比"""
        lats = self.table_16_df.index.values
        if lat <= lats[0] or lat >= lats[-1]:
            raise IndexError("Latitude out of bounds for Table 16 interpolation.")

        # 寻找相邻纬度进行线性插值
        for i in range(len(lats)-1):
            if lats[i] <= lat <= lats[i+1]:
                lat1, lat2 = lats[i], lats[i+1]
                p1 = self.table_16_df.loc[lat1].iloc[month_idx-1]
                p2 = self.table_16_df.loc[lat2].iloc[month_idx-1]
                return p1 + (p2 - p1) * ((lat - lat1) / (lat2 - lat1))

    def fetch_climate_data(self):
        """拉取数据、英制转换、Zonal Stats 并提取逐日 Tmin"""
        bounds = self.gdf.total_bounds
        min_lon, min_lat, max_lon, max_lat = bounds[0]-0.1, bounds[1]-0.1, bounds[2]+0.1, bounds[3]+0.1
        
        # 1. 建立 OPeNDAP 连接并获取数据
        url_pr = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_pr_1979_CurrentYear_CONUS.nc"
        url_tmax = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmx_1979_CurrentYear_CONUS.nc"
        url_tmin = "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_tmmn_1979_CurrentYear_CONUS.nc"
        
        ds_pr = xr.open_dataset(url_pr)
        sub_pr = ds_pr['precipitation_amount'].sel(
            lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))
        ds_tmax = xr.open_dataset(url_tmax)
        sub_tmax = ds_tmax['daily_maximum_temperature'].sel(
            lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))
        ds_tmin = xr.open_dataset(url_tmin)
        sub_tmin = ds_tmin['daily_minimum_temperature'].sel(
            lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat), day=slice(self.start_date, self.end_date))

        # 2. 单位转换 (Kelvin -> Fahrenheit, mm -> inches)
        daily_tmin_F = (sub_tmin - 273.15) * 1.8 + 32.0
        daily_tmax_F = (sub_tmax - 273.15) * 1.8 + 32.0
        daily_pr_in = sub_pr / 25.4
        daily_tmean_F = (daily_tmax_F + daily_tmin_F) / 2.0

        # 3. 按月聚合 (B-C 公式需要)
        monthly_tmean_F = daily_tmean_F.resample(day='ME').mean(dim='day').compute()
        monthly_pr_in = daily_pr_in.resample(day='ME').sum(dim='day').compute()
        daily_tmin_F = daily_tmin_F.compute() # 保留逐日 Tmin 备用
        
        # 准备 Zonal Stats 所需的 affine transform
        transform = monthly_pr_in.rio.transform()

        monthly_results = []
        daily_frost_results = [] # 记录每天的最低温以寻找霜冻日

        print("Executing Zonal Statistics for Polygons...")
        polygon_ids = self.gdf[self.CU_ID_COL].tolist()
        centroids_lat = self.gdf.geometry.centroid.y.tolist()

        # ==========================================
        # --- Zonal Stats 提取月度数据 (先遍历月份) ---
        # ==========================================
        for month_idx in range(1, 13):
            # 获取该月的单个 xarray 栅格片（12次读取）
            pr_raster = monthly_pr_in.isel(day=month_idx-1).values
            tmean_raster = monthly_tmean_F.isel(day=month_idx-1).values
            
            # Extract precipitation mean (calculate mean of pixels within each polygon)
            pr_zonal_list = zonal_stats(self.gdf, pr_raster, affine=transform, stats="mean", nodata=np.nan)
            tmean_zonal_list = zonal_stats(self.gdf, tmean_raster, affine=transform, stats="mean", nodata=np.nan)
            
            # 将该月的结果分配给各个多边形
            for i, poly_id in enumerate(polygon_ids):
                pr_zonal = pr_zonal_list[i]['mean']
                tmean_zonal = tmean_zonal_list[i]['mean']
                lat = centroids_lat[i]
                
                # 仅针对该多边形的纬度进行日照插值
                p_pct = self._interpolate_daylight(lat, month_idx)
                
                monthly_results.append({
                    # 'Locale': locales[i],
                    'Polygon_ID': poly_id, 
                    'Month': month_idx,
                    'T_mean_F': tmean_zonal,
                    'Precip_in': pr_zonal,
                    'Daylight_pct_p': p_pct,
                    'Factor_f': (tmean_zonal * p_pct) / 100.0 if tmean_zonal else 0
                })

        # ==========================================
        # --- 提前提取逐日数据用于查找霜冻日 (先遍历日期) ---
        # ==========================================
        time_coords = daily_tmin_F.day.values # 获取时间轴数组 [1]
        for day_idx in range(len(time_coords)):
            # 每天仅提取一次该日的最低温栅格矩阵（365/366次读取）
            tmin_raster = daily_tmin_F.isel(day=day_idx).values
            
            # 一次性计算所有多边形的均值
            tmin_zonal_list = zonal_stats(self.gdf, tmin_raster, affine=transform, stats="mean", nodata=np.nan)
            
            current_date = time_coords[day_idx]
            # 分配该日的结果给对应的多边形
            for i, poly_id in enumerate(polygon_ids):
                daily_frost_results.append({
                    'Polygon_ID': poly_id,
                    'Date': current_date,
                    'T_min_F': tmin_zonal_list[i]['mean']
                })

        return pd.DataFrame(monthly_results), pd.DataFrame(daily_frost_results)
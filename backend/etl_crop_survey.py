"""
Module: backend/etl_crop_survey.py
Description: 
Parses GIS spatial data (Geodatabase/Shapefile) to extract exact acreage of irrigated crops.
Utilizes Official NMOSE Land Use Codes and Descriptions to assign Blaney-Criddle IDs (BC_ID).
Implements Soft-Delete for un-irrigated/fallow areas to ensure audit traceability.
Strictly follows 1964 Supreme Court Decree rules for Metered vs Unmetered (M29/P29) logic.
"""

import logging
import re
import pandas as pd
import geopandas as gpd
from dataclasses import dataclass
from typing import List
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# ==========================================
# 1. 终极版 NMOSE 官方映射 (涵盖 Gila River 全流域)
# ==========================================
OFFICIAL_LU_TO_BC_ID = {
    "AL": 1, "CR": 2, "CB": 3, "ON": 3, "MV": 3, "AP": 4, "OR": 4, "ONG": 4, "OCG": 4,
    "PT": 5, "PIC": 5, "PIW": 5, "OA": 6, "SSG": 6, "TC": 7, "WW": 8, "CW": 8, "CS": 10,
    "BE": 12, "ME": 13, "CH": 14, "GR": 15, "SG": 16, "SO": 16, "PN": 19, "HA": 20,
    "NT": 21, "CC": 22, "MFC": 22, "CO": 23, "TW": 25, "PE": 27, "PU": 29,
    
    # 0 代表不计入农业 CIR (保留原始面积，但不参与耗水计算)
    "MON": 0, "BL": 0, "FA": 0, "ID": 0, "NA": 0, "NC": 0, "OUT": 0, 
    "RW": 0, "RD": 0, "STW": 0, "STD": 0, "UN": 0,
}

OFFICIAL_DESC_TO_BC_ID = {
    "ALFALFA": 1, "CORN (GRAIN)": 2, "MISC. VEGETABLE": 3, "ORCHARD (NO GROUND COVER)": 4,
    "ORCHARD (GROUND COVER)": 4, "ORCHARD": 4, "PASTURE (IMPROVED/PLANTED, COOL GRASS)": 5,
    "PASTURE (IMPROVED/PLANTED, WARM GRASS)": 5, "SPRING SMALL GRAIN": 6, "TURFGRASS (COOL SEASON)": 7,
    "WINTER WHEAT": 8, "CORN (SILAGE)": 10, "DRY BEANS": 12, "MELONS": 13, "CHILE": 14,
    "GRAPES": 15, "SORGHUM": 16, "PASTURE (NATIVE)": 19, "HAY": 20, "MISC. FIELD CROPS": 22,
    "COTTON": 23, "TURFGRASS (WARM SEASON)": 25, "PECANS": 27, "PASTURE (UNIMPROVED)": 29,
    
    # 强制 0 CIR 的关键字兜底
    "OUTDOOR NURSERY": 0, "FALLOW": 0, "IDLE": 0, "RESERVOIR": 0, "STOCK TANK": 0, 
    "OUT AREA": 0, "UNREPORTED": 0, "NON-AG": 0
}

# ==========================================
# 2. Data Contracts (遵循最高法院法令重构)
# ==========================================
@dataclass
class SurveyPolygon:
    polygon_id: str
    ditch_name: str       # 按水渠分组的依据 (Line 7 / Line 9)
    crop_code: str
    crop_type: str
    bc_id: int
    acreage: float
    irr_code: int         # 必须提取！用于区分 M29 (Flood, 代码1) 与 P29 (Sprinkler/Drip, 代码2,3)
    is_metered: bool      # 蓝图逻辑：属于知名水渠=True，空白/未记录水渠=False
    remarks: str          # 保留原始备注文本，供下一步计算水库 M31/P31 时使用正则提取蓄水率
    is_crop: bool          # True=有效作物 (参与 CIR 计算), False=休耕/界外区 (仅用于最终审计占位)
    is_reservoir: bool    # True=水库/蓄水池/Stock Tank
    evap_acreage: float   # 计算用蒸发面积 (仅在 M31/P31 时使用)
    is_effective: bool      # True=有效地块 (参与 CIR 计算), False=休耕/界外区 (仅用于最终审计占位)

class CropSurveyETL:
    def __init__(self, gdb_path: str, layer_name: str):
        self.gdb_path = gdb_path
        self.layer_name = layer_name
        self.raw_gdf = None
        
    def load_data(self) -> bool:
        logging.info(f"Loading survey layer '{self.layer_name}' from {self.gdb_path}...")
        try:
            self.raw_gdf = gpd.read_file(self.gdb_path, layer=self.layer_name, engine="pyogrio")
            return True
        except Exception as e:
            logging.error(f"Failed to load GDB layer: {e}")
            return False

    def _determine_bc_id(self, crop_code: str, crop_desc: str) -> int:
        code_clean = str(crop_code).strip().upper() if pd.notna(crop_code) and str(crop_code).strip().upper() != 'NAN' else ""
        desc_clean = str(crop_desc).strip().upper() if pd.notna(crop_desc) and str(crop_desc).strip().upper() != 'NAN' else ""

        if not code_clean and not desc_clean: return 0
        if code_clean in OFFICIAL_LU_TO_BC_ID: return OFFICIAL_LU_TO_BC_ID[code_clean]
            
        for key, val in OFFICIAL_DESC_TO_BC_ID.items():
            if key in desc_clean: return val
                
        return 0

    def _parse_fill_percentage(self, remarks: str) -> float:
        """
        核心智能解析：从 Remarks 中读取水库蓄水率 (例如 "85% Full", "0.8")。
        如果未标明，默认按最高法院从严原则视为 1.0 (100% 满)。
        """
        if not remarks or pd.isna(remarks):
            return 1.0
            
        remarks_upper = remarks.upper()
        
        # 1. 匹配百分比，如 "85%", "50 % FULL"
        match_pct = re.search(r'(\d+(?:\.\d+)?)\s*%', remarks_upper)
        if match_pct:
            return float(match_pct.group(1)) / 100.0
            
        # 2. 匹配小数，如 "0.8 FULL"
        match_dec = re.search(r'(0\.\d+)\s*FULL', remarks_upper)
        if match_dec:
            return float(match_dec.group(1))
            
        # 3. 匹配文本关键字
        if "HALF" in remarks_upper: return 0.5
        if "DRY" in remarks_upper or "EMPTY" in remarks_upper: return 0.0
            
        return 1.0

    def extract_survey_data(self) -> pd.DataFrame:
        if self.raw_gdf is None:
            if not self.load_data(): return pd.DataFrame()

        logging.info("Applying Supreme Court Decree rules: Parsing Reservoir Evaporation % ...")
        all_polys: List[SurveyPolygon] = []
        
        cols = self.raw_gdf.columns
        lu_col = 'Crop_Code' if 'Crop_Code' in cols else ('LU_CODE' if 'LU_CODE' in cols else 'LU')
        desc_col = 'Crop_Type' if 'Crop_Type' in cols else ('CROP_DESC' if 'CROP_DESC' in cols else None)
        ditch_col = 'Ditch' if 'Ditch' in cols else 'Name'
        acres_col = 'Computed_Acreage' if 'Computed_Acreage' in cols else ('Acres' if 'Acres' in cols else 'Shape_Area')
        remarks_col = 'Remarks' if 'Remarks' in cols else None
        irr_code_col = 'Irr_Code' if 'Irr_Code' in cols else None
        
        effective_count = 0
        skipped_count = 0

        for idx, row in self.raw_gdf.iterrows():
            poly_id = str(row.get('OBJECTID', idx))
            acres = float(row.get(acres_col, 0.0))
            crop_code = row.get(lu_col, '')
            crop_type = row.get(desc_col, '')
            remarks = str(row[remarks_col]) if remarks_col and pd.notna(row.get(remarks_col)) else ""
            
            # --- 提取 Irr_Code 与计量状态 ---
            irr_code_val = row.get(irr_code_col, 0) if irr_code_col else 0
            try:
                irr_code_int = int(float(irr_code_val)) if pd.notna(irr_code_val) and str(irr_code_val).strip() != '' else 0
            except ValueError:
                irr_code_int = 0
            
            raw_ditch = str(row.get(ditch_col, '')).strip()
            if not raw_ditch or raw_ditch.upper() in ['NAN', 'NONE', 'UNKNOWN', 'NULL']:
                is_metered = False
                ditch_name = "Ungaged_or_Blank"
            else:
                is_metered = True
                ditch_name = raw_ditch

            bc_id = self._determine_bc_id(crop_code, crop_type)
            is_crop = (bc_id > 0)
            
            is_effective = True
            if bc_id == 0 or acres <= 0 or crop_code == "RD":
                is_effective = False
                skipped_count += 1
            else:
                effective_count += 1
            
            # --- 核心：Line 7 水库逻辑 (RW, STW) ---
            crop_code_clean = str(crop_code).strip().upper() if pd.notna(crop_code) else ""
            crop_type_clean = str(crop_type).upper() if pd.notna(crop_type) else ""
            
            is_reservoir = (crop_code_clean in ['RW', 'STW']) or ('RESERVOIR' in crop_type_clean and 'DRY' not in crop_type_clean)
            
            evap_mult = 0.0
            if is_reservoir:
                evap_mult = self._parse_fill_percentage(remarks)
            
            evap_acreage = acres * evap_mult
            
            all_polys.append(SurveyPolygon(
                polygon_id=poly_id,
                ditch_name=ditch_name,
                crop_code=crop_code_clean,
                crop_type=crop_type_clean,
                bc_id=bc_id,
                acreage=acres,
                irr_code=irr_code_int,
                is_metered=is_metered,
                remarks=remarks,
                is_crop=is_crop,
                is_reservoir=is_reservoir,
                evap_acreage=evap_acreage,
                is_effective=is_effective
            ))
            
        logging.info(f"Survey Parsing Complete: {len(all_polys)} total polygons extracted. "
                     f"({effective_count} Effective for CIR Math | {skipped_count} retained for Audit/Reporting).")
        return pd.DataFrame([p.__dict__ for p in all_polys])


# ==========================================
# 临时测试代码 (仅在直接运行此文件时执行)
# ==========================================
# if __name__ == "__main__":
#     test_gdb =  r"C:\Users\Tao.Liu\OneDrive - State of New Mexico\Documents\Projects_local\GilaReport\ToolDev\data_inputs\geodatabase\irrigated_acreage_20251.gdb"
#     test_layer = "GSLU_IA_2025" # Gila-San Francisco Luna Irrigated Acreage 2025
    
    # etl = CropSurveyETL(gdb_path=test_gdb, layer_name=test_layer)
    # df_all = etl.extract_survey_data()
    
    # if not df_all.empty:
    #     print("\n>>> 💡 准备用于物理引擎的有效计算地块 (is_effective=True)：")
    #     print(df_all[df_all['is_effective'] == True].head(5))
        
    #     print("\n>>> 📝 保留用于最终审计报表的无效地块 (is_effective=False)：")
    #     print(df_all[df_all['is_effective'] == False].head(5))
        
    #     print("\n>>> 📊 全量台账 (包含休耕/界外区) 分组总览：")
    #     # 这就是你最后那张图片的雏形
    #     summary = df_all.groupby(['is_effective', 'crop_code', 'crop_type'])['acreage'].sum().reset_index()
    #     print(summary)
        
    #     print("\n>>> 💡 [计量的有效区域] (用于 Line 9):")
    #     print(df_all[(df_all['is_effective'] == True) & (df_all['is_metered'] == True)].head(3))
        
    #     print("\n>>> 💡 [未计量的有效区域] (用于 M29/P29):")
    #     unmetered = df_all[(df_all['is_effective'] == True) & (df_all['is_metered'] == False)]
    #     print(unmetered[['crop_code', 'irr_code', 'acreage', 'is_metered']].head(3))
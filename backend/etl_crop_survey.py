"""
Module: backend/etl_crop_survey.py
Description: 
Extracts crop survey data from ESRI .ppkx/.gdb files using open-source libraries.
Parses reservoir capacities and well permits from 'Remarks', and aggregates 
acreage into Metered (by Ditch) and Unmetered categories.
"""

import os
import zipfile
import re
import logging
import pandas as pd
import geopandas as gpd
import pyogrio, difflib
from typing import Dict, List

# Import data models
from .models import CropAcreageStat, DitchAcreageSummary, IrrigationStat, RegionalUnmeteredSummary, RegionalSurveyData

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

class CropSurveyETL:
    # Crop code mapping based on 2025 survey report (Tao: wait for final confirmation)

    def __init__(self, gdb_path: str, crop_coefficients: dict = None):
        self.gdb_path = gdb_path
        self.crop_catalog = crop_coefficients or {}
        # print(self.crop_catalog.values()) # Debug: Check loaded crop catalog
    
        self.standard_crop_names = [crop.crop_name for crop in self.crop_catalog.values()]
        # print(f"Standard Crop Names for Fuzzy Matching: {self.standard_crop_names}") # Debug: Check standard crop names
        # === 新增：反向查找字典 (通过标准名字找回 Key 和 Type) ===
        self.name_to_catalog = {}
        for c_id, crop in self.crop_catalog.items():
            if crop.crop_name:
                self.name_to_catalog[crop.crop_name] = (c_id, crop.crop_type)
        self.dynamic_mapping_cache = {} # For any dynamic mapping we might need based on actual data

       # 64 unique crop labels identified in the 2025 survey GIS data (Tao: wait for final confirmation of these labels and their mappings)
        self.SURVEY_CODE_TO_LABEL = {
            'AL': 'Alfalfa',
            'AN': 'New alfalfa (1st year)',
            'AV': 'Avacados',
            'BO': 'Bulb Onions',
            'CF': 'Citrus Fruit',
            'CG': 'Corn (Grain)',
            'CH': 'Chile',
            'CLL': 'Clover (Landino)',
            'CO': 'Cotton',
            'CS': 'Corn (Silage)',
            'CT': 'Chistmas Trees',
            'DF': 'Dry Farmed',
            'FA': 'Fallow, idle or otherwise not irrigated',
            'GB': 'Garden Beans',
            'GR': 'Grapes',
            'HA': 'Hay (all other)',
            'IP': 'Irish Potatoes',
            'LL': 'Leaf Lettuce',
            'MAC': 'Melons and Cantelopes',
            'MB': 'Misc. Berries',
            'MDB': 'Misc. Dry Beans',
            'MFC': 'Misc. Field Crops',
            'MON': 'Misc. Outdoor Nursery Stock',
            'MV': 'Misc. Vegetables',
            'OGC': 'Orchard (ground cover)',
            'ONG': 'Orchard (no ground cover)',
            'OUT': 'Out Areas',
            'PEI': 'Pecans ISC',
            'PEW': 'Pecans WUCB',
            'PG': 'Peanuts (ground)',
            'PI': 'Pistachios',
            'PIC': 'Pasture (Improved/Planted, Cool Grass)',
            'PIW': 'Pasture (improved/Planted, Warm Grass)',
            'PLG': 'Plowed Ground',
            'PN': 'Pasture (Native)',
            'PPCG': 'Pre-Planted Corn (Grain)',
            'PPCO': 'Pre-Planted Cotton',
            'PPCS': 'Pre-Planted Corn (silage)',
            'PPMV': 'Pre-Planted Misc. Vegetables',
            'PPSG': 'Pre-Planted Sorghum (Grain)',
            'PPSS': 'Pre-Planted Sorghum (Silage)',
            'PPSSG': 'Pre-Planted Spring Small Grains',
            'PPWSG': 'Pre-Planted Winter Small Grains (Fall)',
            'PU': 'Pasture (Unimproved)',
            'RD': 'Reservoir Dry',
            'RW': 'Reservoir Retaining water (note volume in remarks)',
            'SA': 'Short Alfalfa',
            'SB': 'Sugar Beets',
            'SC': 'Sweet Corn',
            'SG': 'Sorghum (Grain)',
            'SO': 'Soybeans',
            'SP': 'Sweet Peas',
            'SS': 'Sorghum (Silage)',
            'SSG': 'Spring Small Grains',
            'SSL': 'Swamped/Seeped Land',
            'STD': 'Stock Rank, Dry',
            'STW': 'Stock Tank Retaining water (note volume in remarks)',
            'SW': 'Shrub Wetlands',
            'TC': 'Turfgrass (Cool Season)',
            'TO': 'Tomatoes',
            'TW': 'Turfgrass (Warm Season)',
            'UN': 'Unreported',
            'WA': 'Walnuts',
            'WSG': 'Winter Small Grains'
        }
        self.IRR_METHOD_MAPPING = {
            1: 'Flood',
            2: 'Sprinkler',
            3: 'Drip',
            4: 'Reservoir / Unmetered',
            5: 'Sub-irrigation',
            0: 'Unreported',
            
        }

    def _fuzzy_match_crop(self, survey_label: str) -> str:
        """Maps a raw survey crop label to a standardized crop name using fuzzy matching and dynamic rules."""
        if not survey_label or pd.isna(survey_label): return "Unknown"
            
        survey_label_str = str(survey_label).strip()
        
        # Check dynamic mapping cache first to avoid repeated fuzzy matching for the same label
        if survey_label_str in self.dynamic_mapping_cache:
            return self.dynamic_mapping_cache[survey_label_str]

        # 1. Hardcoded rules for common patterns (e.g., if label contains "reservoir" or "tank", map to "Reservoir")
        lower_label = survey_label_str.lower()
        if 'out area' in lower_label:
            result = 'Out Areas'
        elif 'unreported' in lower_label:
            result = 'Unreported'
        elif 'reservoir dry' in lower_label or 'dry reservoir' in lower_label:
            result = 'Reservoir Dry'
        elif 'pistachio' in lower_label:
            result = 'Pistachios' # Keep it as Pistachios, no pistachio in the 30 crop names
        elif 'reservoir' in lower_label or 'tank' in lower_label:
            result = 'Reservoir Wet'
        elif 'fallow' in lower_label:
            result = 'Fallow'
        elif 'dryland' in lower_label or 'dsl' in lower_label:
            result = 'Dryland'
        else:
            # 2. Use difflib for core fuzzy matching (cutoff=0.4 represents similarity threshold, adjustable)
            # For example: "Corn, grain" and "Corn (grain)" will be perfectly matched, while "Corn" and "Corn (grain)" might have a lower score but still above 0.4.
            # this funcstion returns a list of matches (or an empty list), we take the best one (first in the list) if it exists.
            matches = difflib.get_close_matches(survey_label_str, self.standard_crop_names, n=1, cutoff=0.4)
            if matches:
                result = matches[0]
            else:
                result = f"Unmapped: {survey_label_str}" # Mark unmapped entries
                
        # Store in cache and return
        self.dynamic_mapping_cache[survey_label_str] = result
        return result

    def _parse_remarks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parses the 'Remarks' column to extract:
        1. Evaporation Multiplier (e.g., "80%" -> 0.8)
        """
        # match percentage patterns like "80%" and convert to multiplier (0.8)
        pct_pattern = r'(\d{1,3})\s*%'
        
        def get_multiplier(text):
            if pd.isna(text): return 1.0
            text = str(text)
            match = re.search(pct_pattern, text)
            if match:
                return float(match.group(1)) / 100.0
            # Here you can add more hardcoded replacements based on actual data
            if "half full" in text.lower(): return 0.5
            return 1.0 # Default 100% full

        df['Evapor_Multiplier'] = df['Remarks'].apply(get_multiplier)

        # 2. Extract groundwater well permits or keywords
        well_pattern = r'(?i)LWD-\d+|well|pump'
        df['Has_Groundwater_Well'] = df['Remarks'].astype(str).str.contains(well_pattern, regex=True, na=False)

        return df

    def process_layer(self, layer_name: str) -> RegionalSurveyData:
        """Process a single region layer, executing filtering and aggregation logic"""
        logging.info(f"Processing layer: {layer_name}")
        
        # Use pyogrio to read the specific layer into a GeoDataFrame, then convert to DataFrame
        gdf = gpd.read_file(
            self.gdb_path, 
            layer=layer_name, 
            engine="pyogrio"
        )
        df = pd.DataFrame(gdf.drop(columns='geometry'))
        # print(df.head()) # Debug: Check the columns and sample data to ensure correct loading
        # print(f"Columns in layer '{layer_name}': {df.columns.tolist()}") # Debug: List columns to verify expected structure
        
        # I. Crop and Reservoir Acres for both metered and unmetered categories
        # Base cleanup
        df['Ditch'] = df['Ditch'].fillna('BLANK_UNMETERED').str.strip()
        df['Computed_Acreage'] = pd.to_numeric(df['Computed_Acreage'], errors='coerce').fillna(0)
        df['Irr_Code'] = pd.to_numeric(df['Irr_Code'], errors='coerce').fillna(0).astype(int)
        
        # Parse 'Remarks' for evaporation multipliers and well indicators
        df = self._parse_remarks(df)
        df['Translated_Label'] = df['Crop_Code'].map(self.SURVEY_CODE_TO_LABEL).fillna(df['Crop_Code'])

        # Define reservoir criteria: Crop_Code is RW/SW/STW, or Crop_Type contains reservoir
        is_facility = df['Translated_Label'].astype(str).str.contains('(?i)Reservoir|Tank', regex=True)
        is_wet = df['Translated_Label'].astype(str).str.contains('(?i)Wet|Retaining Water', regex=True)
        df['Is_Reservoir'] = is_facility & is_wet
        
        # Split into Metered vs Unmetered based on Ditch name, then aggregate accordingly
        metered_df = df[df['Ditch'] != 'BLANK_UNMETERED']
        unmetered_df = df[df['Ditch'] == 'BLANK_UNMETERED']
        
        # === 1. Calculate Metered (by Ditch) ===
        ditches_dict = {}
        for ditch_name, group in metered_df.groupby('Ditch'):
            print(f"Processing Ditch: {ditch_name} with {len(group)} records") # Debug: Check group size
            # Line 7: Reservoirs (acreage * evaporation multiplier)
            res_group = group[group['Is_Reservoir']]
            ditch_resv_acres = (res_group['Computed_Acreage'] * res_group['Evapor_Multiplier']).sum()
            
            # Line 9: Crops (Irr_Code 1, 2, 3)
            crop_group = group[group['Irr_Code'].isin([1, 2, 3])]
            ditch_crop_acres = crop_group['Computed_Acreage'].sum()
            
            ditches_dict[ditch_name] = DitchAcreageSummary(
                ditch_name=ditch_name,
                total_crop_acres=float(ditch_crop_acres),
                total_reservoir_acres=float(ditch_resv_acres)
            )
            
        # === 2. Calculate Unmetered (M29, P29, M31, P31) ===
        # M29: Surface water, flood irrigation (Irr_Code 1)
        m29 = unmetered_df[unmetered_df['Irr_Code'] == 1]['Computed_Acreage'].sum()
        
        # P29: Groundwater, sprinkler/drip (Irr_Code 2, 3)
        p29 = unmetered_df[unmetered_df['Irr_Code'].isin([2, 3])]['Computed_Acreage'].sum()
        
        # M31: Surface water reservoirs (Irr_Code 4 + is_reservoir + NO well)
        m31_mask = (unmetered_df['Irr_Code'] == 4) & unmetered_df['Is_Reservoir'] & (~unmetered_df['Has_Groundwater_Well'])
        m31 = (unmetered_df[m31_mask]['Computed_Acreage'] * unmetered_df[m31_mask]['Evapor_Multiplier']).sum()
        
        # P31: Groundwater reservoirs (Irr_Code 4 + is_reservoir + HAS well)
        p31_mask = (unmetered_df['Irr_Code'] == 4) & unmetered_df['Is_Reservoir'] & (unmetered_df['Has_Groundwater_Well'])
        p31 = (unmetered_df[p31_mask]['Computed_Acreage'] * unmetered_df[p31_mask]['Evapor_Multiplier']).sum()
        
        unmetered_summary = RegionalUnmeteredSummary(
            region_name=layer_name,
            surface_flood_acres=float(m29),
            groundwater_sprinkler_acres=float(p29),
            surface_reservoir_acres=float(m31),
            groundwater_reservoir_acres=float(p31)
        )
        # ==============================================================

        # II. Crop and Irrigation Stats
        all_survey_df = df.copy()
        total_survey_acres = all_survey_df['Computed_Acreage'].sum()
        # valid_irrigated_df = df[df['Irr_Code'].isin([1, 2, 3])].copy()
        # total_regional_acres = valid_irrigated_df['Computed_Acreage'].sum()

        # A. Crop Mix (all)
        crop_stats_list = []
        if total_survey_acres > 0:
            crop_groups = all_survey_df.groupby('Translated_Label')['Computed_Acreage'].sum()
            for raw_label, acres in crop_groups.items():
                mapped_name = self._fuzzy_match_crop(raw_label)
                crop_id, crop_type = self.name_to_catalog.get(mapped_name, ("N/A", "N/A"))
                
                pct = (acres / total_survey_acres) * 100.0
                crop_stats_list.append(CropAcreageStat(
                    raw_crop_code=str(raw_label), 
                    mapped_crop_name=mapped_name,
                    crop_id=str(crop_id),
                    crop_type=crop_type,
                    total_acres=float(acres),
                    percentage=float(pct)
                ))
        
        # B. Irrigation Methods (all)
        irr_stats_list = []
        if total_survey_acres > 0:
            irr_groups = all_survey_df.groupby('Irr_Code')['Computed_Acreage'].sum()
            for icode, acres in irr_groups.items():
                method_name = self.IRR_METHOD_MAPPING.get(icode, 0)
                print(f"Processing Irrigation Code: {icode} with total acres: {acres}") # Debug: Check irrigation code groups
                pct = (acres / total_survey_acres) * 100.0
                irr_stats_list.append(IrrigationStat(
                    irr_code=int(icode),
                    irr_method_name=method_name,
                    total_acres=float(acres),
                    percentage=float(pct)
                ))

        # C. Valid irrigation stats (The mapped 30 crops and Irr_Code 1,2,3 only) for CIR estimation
        effective_crop_stats = [
            stat for stat in crop_stats_list 
            if stat.crop_id != "N/A" and "Unmapped" not in stat.mapped_crop_name
        ]
        total_effective_crop_acres = sum(stat.total_acres for stat in effective_crop_stats)
        for stat in effective_crop_stats:
            stat.percentage = (stat.total_acres / total_effective_crop_acres * 100.0) if total_effective_crop_acres > 0 else 0.0

        effective_irr_stats = [
            stat for stat in irr_stats_list 
            if stat.irr_code in [1, 2, 3]
        ]
        total_effective_irr_acres = sum(stat.total_acres for stat in effective_irr_stats)
        for stat in effective_irr_stats:
            stat.percentage = (stat.total_acres / total_effective_irr_acres * 100.0) if total_effective_irr_acres > 0 else 0.0

        # ------------------------------------------------

        return RegionalSurveyData(
            region_name=layer_name,
            ditches=ditches_dict,
            unmetered=unmetered_summary,
            crop_stats=crop_stats_list,
            irrigation_stats=irr_stats_list,
            effective_crop=effective_crop_stats,
            effective_irrigation=effective_irr_stats
        )

    def run_all(self) -> Dict[str, RegionalSurveyData]:
        """Main execution method. Extracts the .ppkx, processes each layer, and returns a dictionary of results keyed by region/layer name."""
        # if not self.gdb_path:
        #     self._extract_ppkx()
        if not os.path.exists(self.gdb_path):
            raise FileNotFoundError(f"Cannot find Geodatabase at: {self.gdb_path}")
            
        layers = pyogrio.list_layers(self.gdb_path)
        results = {}
        for layer_info in layers:
            layer_name = layer_info[0] # layer_info is a tuple like (layer_name, geometry_type, feature_count)
            results[layer_name] = self.process_layer(layer_name)
            
        return results
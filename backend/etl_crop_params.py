"""
Module: backend/etl_crop_params.py
Description: 
ETL pipeline to Extract crop coefficients and dates from raw JSON/Dictionaries,
Transform the data, and Load them into strictly typed CropParameters DataClasses.
"""

import logging
import json
from typing import Dict
from .models import CropParameters

# Configure standard logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

class CropParameterETL:
    def __init__(self, json_file_path: str):
        self.file_path = json_file_path
        self.crop_catalog: Dict[str, CropParameters] = {}

    def run_pipeline(self) -> Dict[str, CropParameters]:
        """Executes the Extract, Transform, Load process for crop parameters."""
        logging.info(f"Extracting crop parameters from: {self.file_path}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            logging.error(f"Crop parameter file not found: {self.file_path}")
            return self.crop_catalog

        for crop_id, data in raw_data.items():
            # Skip invalid or purely date-override dictionaries
            if "name" not in data:
                continue
                
            # Transform and Load into Dataclass
            try:
                crop_param = CropParameters(
                    crop_name=data.get("name"),
                    crop_type=data.get("type", "AN"),
                    spring_start_temp_F=data.get("TEM"),
                    fall_end_temp_F=data.get("TLM"),
                    k_inside_frost_free=data.get("OBC_K_inside", 0.0),
                    k_outside_frost_free=data.get("OBC_K_outside", 0.0),
                    max_growing_season_days=data.get("GSL_days"),
                    date_filter_flag=data.get("date_filter_flag", 0)
                )
                self.crop_catalog[crop_id] = crop_param
            except Exception as e:
                logging.warning(f"Failed to parse crop ID {crop_id}. Reason: {e}")

        logging.info(f"Successfully loaded {len(self.crop_catalog)} crop profiles.")
        return self.crop_catalog
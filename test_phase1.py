"""
Gila River Basin Water Consumption Automated Pipeline
Integration Test: Phase 1 (Backend Core Engine)

Description:
This script performs an End-to-End test of the refactored Phase 1 modules.
It extracts crop parameters, pulls GridMET climate data for a sample polygon, 
and computes the annual Consumptive Irrigation Requirement (CIR) profile.
"""

import os
import sys
import logging
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import the refactored backend modules
from backend.models import CropParameters
from backend.etl_crop_params import CropParameterETL
from backend.etl_climate import ClimateETL
from backend.core_blaney_criddle import BlaneyCriddleEngine

# Define the test dataset
gdb_layer_name = "GSLU_IA_2025" # The layer in the GDB containing irrigated acreage for 2025
test_polygon_id = "GSLU-00014" # a Luna decrede polygon for testing
Polygon_id_column = "Field_ID" # The column in the GDB layer that contains unique polygon identifiers

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

def run_integration_test():
    # 1. Define input paths
    data_dir = os.path.join(current_dir, "data")
    
    json_path = os.path.join(data_dir, "CropCoefficients.json")
    table16_csv_path = os.path.join(data_dir, "table16_norther.csv")
    # shp_path = os.path.join(data_dir, "shapefiles/HydroSurvAreas.shp")
    gdb_path = os.path.join(data_dir, "geodatabase/irrigated_acreage_20251.gdb") # Updated to GDB path for testing
    test_year = 2025
    
    print(f"Looking for JSON at: {json_path}")
    print(f"Looking for GDB at: {gdb_path}")

    # Check if files exist
    if not os.path.exists(json_path) or not os.path.exists(gdb_path):
        logging.error("Input files missing in data/ directory. Test aborted.")
        return

    print("\n" + "="*60)
    print("🚀 STARTING PHASE 1 INTEGRATION TEST")
    print("="*60 + "\n")

    # ---------------------------------------------------------
    # STEP 1: Test Crop Parameter ETL
    # ---------------------------------------------------------
    print(">>> STEP 1: Testing CropParameterETL...")
    crop_etl = CropParameterETL(json_path)
    crop_catalog = crop_etl.run_pipeline()
    
    # test_crop_id = "1" # Defined as Alfalfa
    test_crop_id = "5" # Defined as Pastere (improved)
    if test_crop_id not in crop_catalog:
        logging.error(f"Crop ID {test_crop_id} not found in catalog.")
        return
        
    target_crop = crop_catalog[test_crop_id]
    print(f"✅ Successfully loaded crop: {target_crop.crop_name} (Type: {target_crop.crop_type})")

    # ---------------------------------------------------------
    # STEP 2: Test Climate ETL (GridMET & Zonal Stats)
    # ---------------------------------------------------------
    print("\n>>> STEP 2: Testing ClimateETL (Downloading GridMET Data)...")
    table16 = pd.read_csv(table16_csv_path).set_index("Latitude") #; print(table16.head()) # Verify Table 16 loaded correctly 
    climate_etl = ClimateETL(gdb_path, gdb_layer_name, test_year, table16) # arguments: gdb_path, layer_name, year, table16_df
    
    # Using 'Field_ID' as the assumed Polygon ID column in gdb_layer_name
    monthly_df, daily_tmin, transform = climate_etl.run_pipeline(polygon_id_column=Polygon_id_column)
    
    if monthly_df.empty:
        logging.error("Climate ETL returned empty DataFrame.")
        return
        
    # Pick the polygon of Luna for testing the math engine
    test_poly_id=test_polygon_id # Defined at the top for consistency
    # test_poly_id = monthly_df['Polygon_ID'].iloc[0]
    poly_monthly_df = monthly_df[monthly_df['Polygon_ID'] == test_poly_id]
    
    print(f"✅ Successfully extracted climate data for Polygon: {test_poly_id}")
    print(f"Monthly Data Sample:\n{poly_monthly_df.head()}")

    # ---------------------------------------------------------
    # STEP 3: Test Blaney-Criddle Math Engine
    # ---------------------------------------------------------
    print("\n>>> STEP 3: Testing BlaneyCriddleEngine...")
    engine = BlaneyCriddleEngine(target_crop)
    
    # Run the engine
    profile = engine.compute_annual_profile(
        year=test_year,
        locale_id="Field_ID", # Using Field_ID as locale identifier for testing
        poly_id=test_poly_id,
        monthly_df=poly_monthly_df
    )
    print(f"✅ Successfully computed annual CIR profile for Polygon: {test_poly_id}")
    print(f"Annual CIR: {profile.annual_cir:.2f} inches, Annual ETc: {profile.annual_etc:.2f} inches, Annual Re: {profile.annual_re:.2f} inches")

    # ---------------------------------------------------------
    # STEP 4: Output Verification
    # ---------------------------------------------------------
    print("\n" + "="*60)
    print("📊 INTEGRATION TEST RESULTS")
    print("="*60)
    print(f"Crop:            {profile.crop_name}")
    print(f"Polygon ID:      {profile.polygon_id}")
    print(f"Growing Season:  Day {profile.season_boundary.actual_start_jday:.0f} to Day {profile.season_boundary.actual_end_jday:.0f}")
    print(f"Annual ETc (U):  {profile.annual_etc:.2f} inches")
    print(f"Annual Re:       {profile.annual_re:.2f} inches")
    print(f"Annual CIR:      {profile.annual_cir:.2f} inches")
    
    print("\nExtracting to standardized DataFrame format:")
    flat_dict = profile.to_dataframe_dict()
    df_output = pd.DataFrame([flat_dict])
    print(df_output.to_string(index=False))
    print("="*60 + "\n✅ PHASE 1 TEST COMPLETED SUCCESSFULLY!\n")

if __name__ == "__main__":
    run_integration_test()
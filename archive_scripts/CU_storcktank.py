import pandas as pd
from evaporation_data import PanEvap_CU_areas 

gallon_ACFT = 325851.4 # gallons per acre-foot

Prcp_CU_areas = pd.read_csv("CU_gridMET_Monthly_2025.csv")

EvapRate_CU_areas = {cu: [evap * 0.8 for evap in evap_list] for cu, evap_list in PanEvap_CU_areas.items()}

PanEvapSum_CU_areas = {cu: sum(evap)*12 for cu, evap in PanEvap_CU_areas.items()}
print("Average Annual Pan Evaporation (ft) in each CU area:")
for cu, evap in PanEvapSum_CU_areas.items():
    print(f"{cu}: {evap:.2f}")
import requests

# ---------------------------------------------------------
# Configuration & Mapping
# ---------------------------------------------------------
# Gila National Forest data: Gila National Forest, Gila/San Francisco watershed only
# Gila National Forest Service office – Marjorie (Marge) Williams, Resource Assistant. Phone 575-388-8282. 
# Email marge.williams@usda.gov or Marjorie.williams@usda.gov. Silver City, NM.  Main office number: (575) 388-8201.
num_cattle_GNF = {2024: 96983}
num_sheep_GNF = {2024: 0}

# Dictionary mapping New Mexico County Names to their ANSI codes.
NM_COUNTY_ANSI_MAP = {
    "CATRON": "003",
    "GRANT": "017",
    "HIDALGO": "023",
    # Add more counties here if needed...
}

Basins = {"SFR": [0.488, 0.41, 10], # pct of Gila Nationa Forest, pct Catron County, a per capital use rate (in gallons) for cattle 
         "GR exclusive Vd":[0.512, 0.53, 10],  # pct of Gila Nationa Forest, pct of Grant County, a per capital use rate (in gallons) for cattle
         "Vriden":[0., 0.06, 12],  # pct of Gila Nationa Forest and HIDALGO County, a per capital use rate (in gallons) for cattle
         "SS":[0, 0.07, 12]} # pct of Gila Nationa Forest and HIDALGO County, a per capital use rate (in gallons) for cattle

def get_livestock_inventory(api_key, year, county_names, item, state="NM"):
    """
    Fetches Cattle or Sheep inventory data from the USDA QuickStats API.
    
    Parameters:
    - api_key (str): Your USDA API key.
    - year (int/str): The year of the data (e.g., 2025).
    - county_names (list): A list of county names as strings (e.g., ["CATRON", "GRANT"]).
    - item (str): 'CATTLE' or 'SHEEP'.
    - state (str): 2-letter state abbreviation (default is 'NM').
    
    Returns:
    - list: A list of dictionaries containing county names and their respective inventory values.
    """
    
    # 1. Determine the correct 'short_desc' based on the requested item
    item_upper = item.strip().upper()
    if item_upper == "CATTLE":
        short_desc = "CATTLE, INCL CALVES - INVENTORY"
    elif item_upper == "SHEEP":
        short_desc = "SHEEP, INCL LAMBS - INVENTORY"
    else:
        raise ValueError("Invalid item parameter. Please use 'CATTLE' or 'SHEEP'.")

    # 2. Convert provided County Names to their corresponding ANSI codes
    county_ansi_list = []
    for name in county_names:
        formatted_name = name.strip().upper()
        if formatted_name in NM_COUNTY_ANSI_MAP:
            county_ansi_list.append(NM_COUNTY_ANSI_MAP[formatted_name])
        else:
            print(f"Warning: County '{name}' not found in ANSI mapping. Skipping.")

    if not county_ansi_list:
        print("Error: No valid county ANSI codes found to query.")
        return []

    # 3. Construct the API payload (parameters)
    # Note: requests library handles lists by appending multiple identical keys (e.g., &county_ansi=003&county_ansi=017)
    url = "https://quickstats.nass.usda.gov/api/api_GET/"
    params = {
        "key": api_key,
        "short_desc": short_desc,
        "year": year,
        "state_alpha": state,
        "county_ansi": county_ansi_list,
        "format": "json" # Force JSON output for easier parsing
    }

    # 4. Make the HTTP GET request
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()
        results = []
        
        # 5. Parse the returned JSON and extract specific values
        if "data" in data:
            for record in data["data"]:
                county = record.get("county_name", "UNKNOWN")
                
                # Retrieve the value, remove commas, and convert to integer
                raw_value = record.get("Value", "0")
                numeric_value = int(raw_value.replace(",", "")) if raw_value.replace(",", "").isdigit() else 0
                
                results.append({
                    "county": county,
                    "livestock_type": item_upper,
                    "year": record.get("year"),
                    "head_count": numeric_value
                })
            return results
        else:
            print(f"No data found for {item_upper} in the specified counties for the year {year}.")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        return []

def livestock_in_areas(year):
    """
    In Glia
    In San Francisco River, lviestorcks are from 1) Gila National Forest and 2) Catron County. 
    SFR takes ~48.8% of GNF and ~41% Catron County. 

    """
    livestock_dict = {}
    cattle_data = get_livestock_inventory(API_KEY, year, TARGET_COUNTIES, "CATTLE")
    sheep_data = get_livestock_inventory(API_KEY, year, TARGET_COUNTIES, "SHEEP")
    # print(sheep_data, cattle_data)
    cattle_SFR = next((item['head_count'] for item in cattle_data if item['county'] == 'CATRON'), None)* Basins["SFR"][1]
    sheep_SFR = next((item['head_count'] for item in sheep_data if item['county'] == 'CATRON'), None)* Basins["SFR"][1]
   
    cattle_Gila_aboveVd = next((item['head_count'] for item in cattle_data if item['county'] == 'GRANT'), None)* Basins["GR exclusive Vd"][1]
    sheep_Gila_aboveVd = next((item['head_count'] for item in sheep_data if item['county'] == 'GRANT'), None)* Basins["GR exclusive Vd"][1]  

    cattle_Vd = next((item['head_count'] for item in cattle_data if item['county'] == 'HIDALGO'), None)* Basins["Vriden"][1]
    sheep_Vd = next((item['head_count'] for item in sheep_data if item['county'] == 'HIDALGO'), 0)* Basins["Vriden"][1]

    cattle_SS = next((item['head_count'] for item in cattle_data if item['county'] == 'HIDALGO'), None)* Basins["SS"][1]
    sheep_SS = next((item['head_count'] for item in sheep_data if item['county'] == 'HIDALGO'), 0)* Basins["SS"][1]

    livestock_dict["San Franciscon River"] = [int(cattle_SFR), int(sheep_SFR)]
    livestock_dict["Gila River exclusive Vriden"] = [int(cattle_Gila_aboveVd), int(sheep_Gila_aboveVd)]
    livestock_dict["Gila River, Vriden"] = [int(cattle_Vd), int(sheep_Vd)]
    livestock_dict["San Simon"] = [int(cattle_SS), int(sheep_SS)]
     
    return livestock_dict

def days_in_year(year):
    """Returns the number of days in a given year (365 or 366 for leap years)."""
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return 366
    return 365

def livestock_CU_areas(year):
    """
    In Glia
    In San Francisco River, lviestorcks are from 1) Gila National Forest and 2) Catron County. 
    SFR takes ~48.8% of GNF and ~41% Catron County. 

    """
    days = days_in_year(year)
    sheep_gallon_per_day = 2.2 # Average gallons of water consumed per day by a sheep
    gallon_ACFT = 325851.4 # Gallons in one Acre-Foot
    livestock_in_CUareas = livestock_in_areas(year)

    CU_livestock_dict = {}
    cattle_gallon_per_day = Basins["SFR"][2] 
    CU_cattle_SFR = livestock_in_CUareas["San Franciscon River"][0] * cattle_gallon_per_day * days / gallon_ACFT
    CU_sheep_SFR = livestock_in_CUareas["San Franciscon River"][1] * sheep_gallon_per_day * days / gallon_ACFT

    cattle_gallon_per_day = Basins["GR exclusive Vd"][2] 
    CU_cattle_Gila_aboveVd = livestock_in_CUareas["Gila River exclusive Vriden"][0] * cattle_gallon_per_day * days / gallon_ACFT
    CU_sheep_Gila_aboveVd = livestock_in_CUareas["Gila River exclusive Vriden"][1] * sheep_gallon_per_day * days / gallon_ACFT

    cattle_gallon_per_day = Basins["Vriden"][2] 
    CU_cattle_Vd = livestock_in_CUareas["Gila River, Vriden"][0] * cattle_gallon_per_day * days / gallon_ACFT
    CU_sheep_Vd = livestock_in_CUareas["Gila River, Vriden"][1] * sheep_gallon_per_day * days / gallon_ACFT

    cattle_gallon_per_day = Basins["SS"][2] 
    CU_cattle_SS = livestock_in_CUareas["San Simon"][0] * cattle_gallon_per_day * days / gallon_ACFT
    CU_sheep_SS = livestock_in_CUareas["San Simon"][1] * sheep_gallon_per_day * days / gallon_ACFT

    CU_livestock_dict["San Franciscon River"] = [round(CU_cattle_SFR,3), round(CU_sheep_SFR,3)]
    CU_livestock_dict["Gila River exclusive Vriden"] = [round(CU_cattle_Gila_aboveVd,3), round(CU_sheep_Gila_aboveVd,3)]
    CU_livestock_dict["Gila River, Vriden"] = [round(CU_cattle_Vd,3), round(CU_sheep_Vd,3)]
    CU_livestock_dict["San Simon"] = [round(CU_cattle_SS,3), round(CU_sheep_SS,3)]

    return CU_livestock_dict

# ---------------------------------------------------------
# Example Usage for your CU Tool
# ---------------------------------------------------------
if __name__ == "__main__":
    API_KEY = "153C1A44-28F2-3EA4-8C9B-2128CBAB7911" # Replace this key with yours from https://quickstats.nass.usda.gov/api
    TARGET_YEAR = 2025 # Note: Ensure USDA has released data, otherwise it may return empty
    TARGET_COUNTIES = ["Catron", "Grant", "Hidalgo"] # Mixed case is fine, function handles it

    print(f"Report CU for livestock for {TARGET_YEAR}\n")
    
    # # Fetch Cattle Data
    # print("--- Fetching Cattle Data ---")
    # cattle_data = get_livestock_inventory(API_KEY, TARGET_YEAR, TARGET_COUNTIES, "CATTLE")
    # for row in cattle_data:
    #     print(f"County: {row['county']}, Cattle Count: {row['head_count']}")
        
    # # Fetch Sheep Data
    # print("\n--- Fetching Sheep Data ---")
    # sheep_data = get_livestock_inventory(API_KEY, TARGET_YEAR, TARGET_COUNTIES, "SHEEP")
    # for row in sheep_data:
    #     print(f"County: {row['county']}, Sheep Count: {row['head_count']}")

    # return livestock in four areas
    print("livestock in four areas:")
    livestock_four_areas = livestock_in_areas(TARGET_YEAR)
    for row in livestock_four_areas:
        print(f"{row}: Cattle Count - {livestock_four_areas[row][0]}, Sheep Count - {livestock_four_areas[row][1]}")

    # return CU for livestock in four areas
    print("CU for livestock in the four areas:") 
    CU_livestock_areas = livestock_CU_areas(TARGET_YEAR)
    # print(CU_livestock_areas)
    for row in CU_livestock_areas:
        print(f"{row}: Cattle CU - {CU_livestock_areas[row][0]}, Sheep CU - {CU_livestock_areas[row][1]}")
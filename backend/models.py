"""
Gila River Basin Water Consumption Automated Pipeline
Module: backend/models.py

Description:
This module defines the core data structures (DataClasses) used throughout 
the backend compute engine. It strictly standardizes data flowing between 
the climate data extract-tranform-load (ETL) processes, the Original 
Blaney-Criddle mathematical engine, and the regional aggregation module.

All variable naming conventions are decoupled from legacy software and 
aimed at providing maximum transparency for water resource managers 
and software engineers.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List

@dataclass
class CropAcreageStat:
    """单一作物的统计信息"""
    raw_crop_code: str
    mapped_crop_name: str
    crop_id: str # the unique crop ID from the CropParameters catalog, used for linking to CIR profiles
    crop_type: str # 'PR', 'AN', 'WG' from CropParameters, used for logic in Growing Season Determiner
    total_acres: float
    percentage: float  # the percentage of this crop's acreage relative to a survey region's total acreage

@dataclass
class IrrigationStat:
    """灌溉方式的统计信息"""
    irr_code: int
    irr_method_name: str
    total_acres: float
    percentage: float  # the percentage of this irrigation method's acreage relative to a survey region's total acreage

@dataclass
class DitchAcreageSummary:
    """Summary of acreage served by a specific ditch (corresponds to Lines 7 & 9)"""
    ditch_name: str
    total_crop_acres: float        # Line 9 (irr_code 1,2,3 total acres of crops served by this ditch)
    total_reservoir_acres: float   # Line 7 (irr_code 4 total acres of reservoirs served by this ditch)

@dataclass
class RegionalUnmeteredSummary:
    """Summary of unmetered water use for a specific region, non-Gaged Ditch or Blank Ditch"""
    region_name: str
    surface_flood_acres: float           # M29: irr_code=1
    groundwater_sprinkler_acres: float   # P29: irr_code=2,3
    surface_reservoir_acres: float       # M31: reservoir, surface (with well)
    groundwater_reservoir_acres: float   # P31: reservoir, groundwater (with well)

@dataclass
class RegionalSurveyData:
    """Summary of survey data for a specific region"""
    region_name: str
    ditches: Dict[str, DitchAcreageSummary]
    unmetered: RegionalUnmeteredSummary

    # All-inclusive for checking purposes
    crop_stats: List[CropAcreageStat] = field(default_factory=list)
    irrigation_stats: List[IrrigationStat] = field(default_factory=list)

    # Only 30 crops and 3 irrigation methods for CIR estimation
    effective_crop: List[CropAcreageStat] = field(default_factory=list)
    effective_irrigation: List[IrrigationStat] = field(default_factory=list)
    
@dataclass
class CropParameters:
    """
    Biological and empirical parameters for a specific crop.
    These parameters determine the growing season triggers and water consumption rates.
    """
    crop_name: str
    crop_type: str                         # 'PR' (Perennial), 'AN' (Annual), 'WG' (Winter Grain)
    spring_start_temp_F: Optional[float]   # Fortran: TEM - Temp triggering spring moisture use
    fall_end_temp_F: Optional[float]       # Fortran: TLM - Temp ending fall moisture use
    k_inside_frost_free: float             # Fortran: CIFF - Original Blaney-Criddle K inside frost-free period
    k_outside_frost_free: float            # Fortran: COFF - Original Blaney-Criddle K outside frost-free period
    max_growing_season_days: Optional[float] # Fortran: GSL - Max days to maturity
    date_filter_flag: int = 0              # 1 if historical plant/harvest overrides exist

@dataclass
class CropSeasonBoundary:
    """
    Contains the exact Julian Days defining the growing season for a specific year.
    It records the theoretical climate-driven boundaries, the historical manual overrides,
    and the final 'Actual' boundary which is the most limiting of the two.
    """
    theoretical_start_jday: float
    theoretical_end_jday: float
    override_start_jday: Optional[float] = None
    override_end_jday: Optional[float] = None
    
    # The final limiting dates used for actual CIR calculations
    actual_start_jday: float = 0.0
    actual_end_jday: float = 0.0

@dataclass
class MonthlyCIRResult:
    """
    The calculated Original Blaney-Criddle Consumptive Irrigation Requirement (CIR) 
    for a single month. This structure is designed to exactly match the historical 
    output format for downstream reporting and GUI visualization.
    """
    month: int
    growing_days: int                      # Actual days crop grew in this month
    mean_temp_F: float                     # Mean monthly temperature
    total_precip_in: float                 # Total monthly precipitation
    daylight_percentage_prorated: float    # Daylight percentage scaled by growing days
    consumptive_use_factor: float          # Fortran: F = (T * P) / 100
    
    # Applied K-coefficients dynamically assigned based on frost-free period overlap
    k_inside_applied: Optional[float]      # Fortran: KIFF
    k_outside_applied: Optional[float]     # Fortran: KOFF
    
    theoretical_consumptive_use: float     # Fortran: ETc or U (U_in + U_out)
    effective_precip_prorated: float       # Fortran: Re (USBR Method, prorated by days)
    consumptive_irrigation_req: float      # Fortran: CIR = max(0, ETc - Re)

@dataclass
class AnnualCropCIRProfile:
    """
    The complete annual water consumption profile for a single crop in a specific area.
    This object is passed to the Regional Aggregator to be weighted by the Crop Mix (CMIX).
    """
    crop_name: str
    year: int
    locale_id: str
    polygon_id: str
    season_boundary: CropSeasonBoundary
    
    # Annual Totals (Inches)
    annual_etc: float = 0.0
    annual_re: float = 0.0
    annual_cir: float = 0.0
    
    # Dictionary mapping month (1-12) to its detailed calculation results
    monthly_details: Dict[int, MonthlyCIRResult] = field(default_factory=dict)
    
    def to_dataframe_dict(self) -> Dict:
        """
        Helper method to flatten the annual profile into a dictionary 
        that can be easily ingested by pandas.DataFrame for the GUI or PDF generation.
        """
        return {
            "Year": self.year,
            "Locale_ID": self.locale_id,
            "Polygon_ID": self.polygon_id,
            "Crop_Name": self.crop_name,
            "Growing_Season_Start": self.season_boundary.actual_start_jday,
            "Growing_Season_End": self.season_boundary.actual_end_jday,
            "Annual_ETc_in": self.annual_etc,
            "Annual_Re_in": self.annual_re,
            "Annual_CIR_in": self.annual_cir
        }
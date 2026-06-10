"""
Module: backend/core_blaney_criddle.py
Description: 
The core mathematical engine for calculating Consumptive Irrigation Requirements (CIR) 
using the Original Blaney-Criddle methodology and USBR Effective Precipitation.
It strictly relies on the data structures defined in backend/models.py.
"""

import logging
import calendar
from datetime import datetime
import pandas as pd
from typing import Dict, Optional

from .models import (
    CropParameters,
    CropSeasonBoundary,
    MonthlyCIRResult,
    AnnualCropCIRProfile
)

logger = logging.getLogger(__name__)

class BlaneyCriddleEngine:
    """
    Stateless calculation engine. Evaluates the growing season based on temperatures/frosts, 
    and computes the daily-prorated CIR for a specific crop and location.
    """
    def __init__(self, crop_params: CropParameters):
        self.crop = crop_params

    def _get_julian_day(self, year: int, month: int, day: int) -> float:
        """Converts Calendar date to Julian Day (1-365/366)."""
        return float(datetime(year, month, day).timetuple().tm_yday)

    def _interpolate_temp_julian_day(self, monthly_tmean: list, target_temp: float, 
                                     is_spring: bool, is_leap_year: bool) -> float:
        """
        Interpolates the exact Julian Day when the climate crosses the biological 
        temperature threshold (TEM or TLM) using mid-month days (DAYMP).
        """
        days_in_month = [31, 29 if is_leap_year else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        daymp, daye = [], []
        current_start = 1
        for d in days_in_month:
            current_end = current_start + d - 1
            daye.append(current_end)
            daymp.append(int((current_start + current_end) / 2.0 + 0.5))
            current_start = current_end + 1

        t = monthly_tmean

        if is_spring:
            for k in range(12):
                if t[k] >= target_temp:
                    if t[k] == target_temp: return float(daymp[k])
                    if k == 0: return 1.0  # Simplification: Assume day 1 if January is warm enough
                    # Linear interpolation: B = DAYMP(K-1) + (DAYMP(K)-DAYMP(K-1))*(TEM-T(K-1))/(T(K)-T(K-1))
                    temp_diff = t[k] - t[k-1]
                    if temp_diff == 0: 
                        b = daymp[k-1]  # Avoid division by zero, fallback to previous month
                    else:
                        b = daymp[k-1] + (daymp[k] - daymp[k-1]) * (target_temp - t[k-1]) / temp_diff    
                    # b = daymp[k-1] + (daymp[k] - daymp[k-1]) * (target_temp - t[k-1]) / (t[k] - t[k-1])
                    return float(b)
            return float(daymp[1]) # Fallback to June
        else:
            for k in range(6, 12): # Fall search must start after June
                if t[k] <= target_temp:
                    if t[k] == target_temp: return float(daymp[k])
                    temp_diff = t[k] - t[k-1]
                    if temp_diff == 0: 
                        e = daymp[k-1]  # Avoid division by zero, fallback to previous month
                    else:
                        e = daymp[k-1] + (daymp[k] - daymp[k-1]) * (target_temp - t[k-1]) / (t[k] - t[k-1])
                    return float(e)
            return float(daye[2]) # Fallback to end of year

    def _determine_season(self, year: int, monthly_df: pd.DataFrame, 
                          override_plant_jday: Optional[float] = None, 
                          override_harvest_jday: Optional[float] = None) -> CropSeasonBoundary:
        """
        Determines the limiting growing season by comparing theoretical climate boundaries 
        with historical manual overrides.
        """
        is_leap = calendar.isleap(year)
        tmean_series = monthly_df['T_mean_F'].values.tolist()
        
        tem = self.crop.spring_start_temp_F
        tlm = self.crop.fall_end_temp_F
        
        # Placeholder for Winter Grain (WG) split-season logic
        if self.crop.crop_type == 'WG' or tem is None or tlm is None:
            logger.warning(f"Crop {self.crop.crop_name} is Winter Grain or lacks TEM/TLM. Specific routing needed.")
            return CropSeasonBoundary(0, 0, actual_start_jday=0, actual_end_jday=0)

        # 1. Theoretical Dates (Assuming TEM/TLM are 50 or above, triggering interpolation)
        # Note: In full implementation, 28/32 thresholds will trigger daily frost search here.
        theo_start = self._interpolate_temp_julian_day(tmean_series, tem, True, is_leap)
        theo_end = self._interpolate_temp_julian_day(tmean_series, tlm, False, is_leap)

        # 2. Whichever is Limiting (Actual Season)
        act_start = max(theo_start, override_plant_jday) if override_plant_jday else theo_start
        act_end = min(theo_end, override_harvest_jday) if override_harvest_jday else theo_end
        
        if act_end < act_start:
            act_end = act_start

        return CropSeasonBoundary(
            theoretical_start_jday=theo_start,
            theoretical_end_jday=theo_end,
            override_start_jday=override_plant_jday,
            override_end_jday=override_harvest_jday,
            actual_start_jday=act_start,
            actual_end_jday=act_end
        )

    def _calculate_usbr_effective_precip(self, precip_in: float) -> float:
        """USBR 7-piecewise effective precipitation formula."""
        p = precip_in
        if p <= 1.0: return 0.95 * p
        elif p <= 2.0: return 0.90 * (p - 1.0) + 0.95
        elif p <= 3.0: return 0.82 * (p - 2.0) + 1.85
        elif p <= 4.0: return 0.65 * (p - 3.0) + 2.67
        elif p <= 5.0: return 0.45 * (p - 4.0) + 3.32
        elif p <= 6.0: return 0.25 * (p - 5.0) + 3.77
        else: return 0.05 * (p - 6.0) + 4.02

    def compute_annual_profile(self, year: int, locale_id: str, poly_id: str, 
                               monthly_df: pd.DataFrame, 
                               override_plant_jday: Optional[float] = None, 
                               override_harvest_jday: Optional[float] = None) -> AnnualCropCIRProfile:
        """
        Main execution method. Iterates through 12 months, calculating prorated CIR 
        and packaging results into the AnnualCropCIRProfile Dataclass.
        """
        season = self._determine_season(year, monthly_df, override_plant_jday, override_harvest_jday)
        
        profile = AnnualCropCIRProfile(
            crop_name=self.crop.crop_name,
            year=year,
            locale_id=locale_id,
            polygon_id=poly_id,
            season_boundary=season
        )

        if season.actual_start_jday == 0:
            return profile # Skip if Winter Grain or invalid

        annual_etc, annual_re, annual_cir = 0.0, 0.0, 0.0

        for month in range(1, 13):
            days_in_month = calendar.monthrange(year, month)[1]
            month_start_jday = datetime(year, month, 1).timetuple().tm_yday
            month_end_jday = month_start_jday + days_in_month - 1
            
            row = monthly_df[monthly_df['Month'] == month]
            if row.empty: continue
            
            # Safe parsing
            tmean_F = float(row['T_mean_F'].iloc[0])
            precip_in = float(row['Precip_in'].iloc[0])
            p_pct = float(row['Daylight_pct_p'].iloc[0])

            # Check if out of season
            if season.actual_end_jday < month_start_jday or season.actual_start_jday > month_end_jday:
                result = MonthlyCIRResult(month, 0, tmean_F, precip_in, 0.0, 0.0, None, None, 0.0, 0.0, 0.0)
                profile.monthly_details[month] = result
                continue

            # Calculate Growing Days (GD)
            b = max(season.actual_start_jday, month_start_jday)
            e = min(season.actual_end_jday, month_end_jday)
            gd = int(e - b + 1)

            # Prorate Daylight and calculate F
            pdh = p_pct * (gd / days_in_month)
            f_factor = (tmean_F * pdh) / 100.0

            # Assign DIFF/DOFF (Frost-free matching)
            diff, doff = 0, 0
            for day in range(int(b), int(e) + 1):
                if season.theoretical_start_jday <= day <= season.theoretical_end_jday:
                    diff += 1
                else:
                    doff += 1

            k_in = self.crop.k_inside_frost_free
            k_out = self.crop.k_outside_frost_free
            
            u_in = f_factor * (diff / gd) * k_in if gd > 0 else 0.0
            u_out = f_factor * (doff / gd) * k_out if gd > 0 else 0.0
            u_total = u_in + u_out

            re_full = self._calculate_usbr_effective_precip(precip_in)
            re_prorated = min(re_full * (gd / days_in_month), u_total) # Re cannot exceed ETc
            
            cir = max(0.0, u_total - re_prorated)

            annual_etc += u_total
            annual_re += re_prorated
            annual_cir += cir

            result = MonthlyCIRResult(
                month=month,
                growing_days=gd,
                mean_temp_F=tmean_F,
                total_precip_in=precip_in,
                daylight_percentage_prorated=pdh,
                consumptive_use_factor=f_factor,
                k_inside_applied=k_in if diff > 0 else None,
                k_outside_applied=k_out if doff > 0 else None,
                theoretical_consumptive_use=u_total,
                effective_precip_prorated=re_prorated,
                consumptive_irrigation_req=cir
            )
            profile.monthly_details[month] = result

        profile.annual_etc = annual_etc
        profile.annual_re = annual_re
        profile.annual_cir = annual_cir
        
        return profile
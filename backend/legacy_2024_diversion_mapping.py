"""Reviewed 2024 source-channel mapping used only for baseline validation.

The mapping was established by matching each mapped source's twelve monthly
acre-foot values to the corresponding report workbook diversion block.  It is
not a reusable name-normalization rule for future contractor workbooks.
"""

from __future__ import annotations

from .diversion_mapping import SourceDitchMapping


LEGACY_2024_SOURCE_MAPPINGS: tuple[SourceDitchMapping, ...] = (
    SourceDitchMapping("Gila Hot Springs", "report_ditch", "upper_gila_gila_hot_springs", "UPPER GILA", "Gila Hot Springs Ditch"),
    SourceDitchMapping("Upper Gila", "report_ditch", "cliff_gila_upper_gila", "CLIFF-GILA", "Upper Gila Ditch"),
    SourceDitchMapping("Fort West", "report_ditch", "cliff_gila_fort_west_maldonado", "CLIFF-GILA", "Fort West/Maldonado Ditch"),
    SourceDitchMapping("Gila Farms", "report_ditch", "cliff_gila_gila_farms", "CLIFF-GILA", "Gila Farms Ditch"),
    SourceDitchMapping("Grandpa Harper", "report_ditch", "redrock_grandpa_harper", "REDROCK", "Grandpa Harper - Wright Chavez Smith Ditch"),
    SourceDitchMapping("North Side Luna", "report_ditch", "luna_northside", "LUNA", "Northside Luna Ditch"),
    SourceDitchMapping("Adair-Luna", "report_ditch", "luna_adair", "LUNA", "Adair Luna  Ditch"),
    SourceDitchMapping("L. Laney", "report_ditch", "luna_leslie_laney", "LUNA", "Leslie Laney Ditch"),
    SourceDitchMapping("W.S. Laney", "report_ditch", "luna_william_s_laney", "LUNA", "William S. Laney Ditch"),
    SourceDitchMapping("A. Laney", "report_ditch", "luna_a_laney", "LUNA", "A. Laney Ditch"),
    SourceDitchMapping("Lewis", "report_ditch", "reserve_lewis", "RESERVE", "Lewis Ditch"),
    SourceDitchMapping("Cienega", "report_ditch", "reserve_cienega", "RESERVE", "Cienega Ditch"),
    SourceDitchMapping("Kiehne", "report_ditch", "reserve_kiehne", "RESERVE", "Kiehne Ditch"),
    SourceDitchMapping("Parsons", "report_ditch", "reserve_parsons", "RESERVE", "Parsons Ditch"),
    SourceDitchMapping("Middle Frisco", "report_ditch", "reserve_middle_frisco", "RESERVE", "Middle Frisco Ditch"),
    SourceDitchMapping(
        "Tularosa-Cruzville", "excluded", rationale="Zero-flow source channel with no 2024 report metered-ditch block."
    ),
    SourceDitchMapping("Hightower", "report_ditch", "reserve_hightower", "RESERVE", "Hightower Ditch"),
    SourceDitchMapping(
        "San Francisco", "excluded", rationale="Zero-flow source channel with no 2024 report metered-ditch block."
    ),
    SourceDitchMapping("Thomason Flat", "report_ditch", "glenwood_thomason_flat", "GLENWOOD", "Thomason Flat Ditch"),
    SourceDitchMapping("Spurgeon No. 2", "report_ditch", "glenwood_spurgeon_2", "GLENWOOD", "Spurgeon No. 2 Ditch"),
    SourceDitchMapping("W. S.", "report_ditch", "glenwood_ws_gsf39_supplement", "GLENWOOD", "            W S Ditch (GSF39 supplement)"),
    SourceDitchMapping("Fish Pond", "report_ditch", "glenwood_fish_pond_lower_north", "GLENWOOD", "Fish Pond Ditch/Lower Ditch North"),
    SourceDitchMapping("East Pleasanton", "report_ditch", "glenwood_east_pleasanton", "GLENWOOD", "East Pleasanton Ditch"),
)

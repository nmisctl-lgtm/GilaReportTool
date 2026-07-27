# 2024 baseline data flow

This document records the calculation boundary that replaces the legacy
Fortran program and the hidden formulas in `2024 Gila Report Data_WORKING.xlsx`.
It is intentionally expressed as data records and equations, rather than as
cell addresses, so the 2025 source adapter can be different without changing
the method.

## 1. Raw inputs

| Input | 2024 baseline source | Required fields |
| --- | --- | --- |
| Crop/CIR parameters | `GilaAreaCC'68-'24.DAT` | crop type, temperature limits, OBC coefficients, MBC Kc curves, date overrides |
| Area crop pattern | `GilaAreaCDF'68-'24.DAT` | area, crop acres, crop mix, irrigation application depth, area latitude |
| Climate | `GilaAreaWeather'68-'24.dat` | monthly temperature and precipitation, frost dates, adjacent-year temperatures |
| Daily diversions | `2024 Ditch Diversions_FINAL.xlsx`, `flow` | ditch id, date, daily mean CFS |
| Area assets/policy | 2024 working workbook | crop acres and reservoir acres by ditch; meter/estimated/groundwater/CRP classification; whether a shortage is assessed |
| Non-agricultural use | `stock-dom-com-ind-evap` and `Freeport` worksheets | livestock, municipal/industrial/domestic use, lake and stock-tank evaporation |

## 2. CIR computation and bridge

For every area, crop, and month, the replacement engine calculates:

1. **OBC/USBR CIR** from growing-season dates, temperature/daylight factor,
   frost-period coefficients, and USBR effective precipitation.
2. **MBC/SCS CIR** from the same season dates, a Kc growth curve, Kt, and SCS
   effective precipitation.
3. **Area-weighted CIR** from crop CIR multiplied by crop acreage.
4. **Report monthly CIR** by allocating the annual OBC weighted CIR according
   to the MBC monthly shares:

   `monthly_obc_cir[m] = annual_obc_cir * monthly_mbc_cir[m] / sum(monthly_mbc_cir)`

The calculation is implemented in `backend/fortran_parity.py` and
`backend/cir_bridge.py`.  The bridge reproduces each of the nine 2024 workbook
CIR rows within the workbook's 0.01-inch storage precision.

## 3. Diversion aggregation and QA

Daily mean flow is converted before any shortage calculation:

`monthly_diversion_af = sum(daily_mean_cfs) * 1.98347`

`1.98347` is the legacy workbook's conversion factor and is retained for
baseline parity.  QA reports duplicate dates, values outside the report year,
negative/non-finite CFS, and every missing daily value.  A numeric zero is a
valid observation; a missing value is never silently changed to zero.

## 4. Per-ditch demand and measured shortage

For a ditch and month, with efficiency `e`, crop acres `A_crop`, reservoir
acres `A_res`, monthly report CIR `C`, pan evaporation `E_pan`, precipitation
`P`, and measured diversion `D`:

```text
crop_cu_demand_af       = A_crop * C
reservoir_net_evap_af   = A_res * max(E_pan - P, 0)
crop_diversion_required = crop_cu_demand_af / e
reservoir_div_required  = reservoir_net_evap_af / e
total_diversion_required = crop_diversion_required + reservoir_div_required
assessed_shortage        = max(total_diversion_required - D, 0)
```

The last equation is used only when the input explicitly says that the month
is metered and shortage-assessed.  Estimated, unavailable, and
groundwater-supplied records need an explicit policy classification.

## 5. Area and report aggregation

The area ledger aggregates separately classified acreage (metered and
short-supplied, full-supplied groundwater, reservoir, CRP/natural grassland,
and other area-specific classes).  It then produces:

1. total irrigated acres;
2. full-supply crop/reservoir CU;
3. shortage to CU demand;
4. crop and pond CU after shortage;
5. incidental use; and
6. total irrigated CU.

`Tables1,2,3,4` then consumes the area ledger with the separately calculated
stock, municipal/industrial/domestic, and lake-evaporation components:

| Output | Primary inputs |
| --- | --- |
| Table I — Acreage Survey | total irrigated acres by area |
| Table II — Annual Consumptive Use | irrigated CU, stock tanks, livestock, municipal/industrial/domestic, lake evaporation |
| Table III — Ten-year CU | Table II stream-system totals plus prior nine years |
| Table IV — Diversions | measured and estimated irrigation diversions by stream system |

## Remaining policy reconstruction

The shared numerical equations are now code.  The remaining 2024 work is to
move area-specific classifications currently embedded as constants/manual
decisions in the nine workbook sheets into a versioned, reviewable policy
table.  In particular, each ditch-month must state whether it is metered,
estimated, unavailable, groundwater supplied, or CRP/natural grassland, and
whether a shortage is assessed.  That policy table is necessary before a
fully automated Table I--IV run can faithfully replace the workbook.

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

### Source-channel identity is explicit

`backend/legacy_2024_diversion_mapping.py` records a disposition for every
2024 `flow` column.  It is a baseline validation configuration, not a general
name-cleaning rule.  `backend/diversion_mapping.py` rejects unmapped channels
and duplicate source/canonical mappings; it never guesses from similar names.

This distinction matters in the Luna/Glenwood data: source `W.S. Laney` maps
to **William S. Laney Ditch** in Luna and totals **640.748083 AF** (reported
as 640.75 AF); source `W. S.` is a distinct **W S Ditch (GSF39 supplement)**
in Glenwood and totals 1771.093917 AF.  The 2024 configuration maps 21 source
channels to report ditches and explicitly excludes two zero-flow channels
without report metered-ditch blocks.

`backend/legacy_report_assets.py` reads the crop, reservoir, and pre-plant
acres plus each historical shortage-cell treatment from the report blocks.
It captures those treatments for review but does not infer a future-year
groundwater, estimated-flow, or shortage policy from a formula or zero.
It also flags nonzero requirement cells pasted over formulas and historical
reservoir-net-evaporation constants.  The 2024 baseline contains one
requirement exception (Luna `A. Laney Ditch`, March) and two reservoir
constants (Luna `Leslie Laney Ditch` and `A. Laney Ditch`, both March).
The production calculation uses the documented standard crop/reservoir formula
instead of those constants.  A zero legacy reservoir constant is retained only
as explicit evidence that the small winter reservoir demand is not
shortage-assessed; it does not replace the computed demand.

## 4. Per-ditch demand and measured shortage

For a ditch and month, with efficiency `e`, crop acres `A_crop`, reservoir
acres `A_res`, monthly report CIR `C`, **adjusted** pan evaporation `E_adj`,
precipitation `P`, and measured diversion `D`:

```text
crop_cu_demand_af       = A_crop * C
reservoir_net_evap_af   = A_res * max(E_adj - P, 0)
crop_diversion_required = crop_cu_demand_af / e
reservoir_div_required  = reservoir_net_evap_af / e
total_diversion_required = crop_diversion_required + reservoir_div_required
assessed_shortage        = max(total_diversion_required - D, 0)
```

For the 2024 working workbook, `E_adj` is the sheet's monthly pan evaporation
after its explicit 0.8 coefficient.  The new ledger accepts this adjusted
depth directly; it does not apply 0.8 a second time.

The last equation is used only when the input explicitly says that the month
is metered and shortage-assessed.  Estimated, unavailable, and
groundwater-supplied records need an explicit policy classification.

## 5. Area and report aggregation

For the seven standard 2024 area layouts, `backend/area_consumptive_use.py`
implements the yellow-box logic explicitly.  Metered surface water establishes
the annual shortage fraction `diversion_shortage / diversion_required`; that
same fraction is applied to metered and unmetered **surface-water** crop/pond
CU.  Groundwater crop/pond CU is full supply.  Incidental losses are then
`10% × actual surface CU + 2% × groundwater CU`.  The seven ordinary area
totals reproduce their workbook rows exactly through
`backend/legacy_area_summary.py`; Redrock and San Simon's extra CRP/full-CIR
classes are represented explicitly as special cases.  Their CRP/natural
grassland CU is the recorded metered diversion (rather than a CIR product),
while their metered-full-CIR acreage remains full supply and does not receive
the surface-water shortage fraction.  San Simon's groundwater CU is the total
of Brown-box watermaster well diversions, which is a direct measured-use input
rather than acreage times the area CIR.

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

### Non-agricultural flow added to the automated baseline

`backend/non_agricultural_use.py` now supplies the non-agricultural columns
of Table II.  Its inputs and flow are deliberately separated from Excel:

| Component | Raw/prepared input | Calculation | Table II output |
| --- | --- | --- | --- |
| Livestock | Catron, Grant, and Hidalgo cattle/sheep inventories; Gila National Forest annual cattle head-months | allocate county/forest inventories using the documented basin percentages; `head × gallons/day × 365 / 325,851` | Stock |
| Stock tanks | adjusted annual pan evaporation, annual precipitation, weighted tank area, tank count, 85% in-service fraction | `max(pan - precipitation, 0) / 12 × area × count × 0.85` | Stock Tank Evaporation |
| Lakes | adjusted pan evaporation, precipitation, lake area; Bill Evans NM Game & Fish allocation | `max(pan - precipitation, 0) / 12 × area`, or an approved direct allocation | Lake Surface Evaporation |
| Standard M/I/D | Watermaster metered diversions and any non-consumptive quantity | `(diversion - nonconsumptive) × CU fraction` | Municipal, Industrial & Domestic |
| Cliff-Gila M/I/D | fish-pond diversion/non-consumptive amount, Mimbres export, six Freeport accounting entries, fish-pond evaporation allocation | documented special sum: fish-pond CU + export + Freeport CU + fish-pond allocation | Municipal, Industrial & Domestic |

The 2024 adapter in `backend/legacy_non_agricultural.py` is the sole place
with legacy worksheet-cell knowledge.  It converts the workbook's raw or
prepared inputs into named data classes; formulas are then evaluated only in
the backend calculation module.  `backend/annual_summary.py` combines the
four non-agricultural component vectors with the area CU results to create the
four Table II annual-use rows.  The regression tests reproduce all 2024
component values and annual totals.

The old `archive_scripts` directory remains as historical evidence.  Its
livestock script was not suitable as a compute engine because it omitted the
National Forest allocation during calculation and relied on globals/API state;
its tank script re-applied a time conversion to annual values.  New code must
use the production backend modules instead.

## Remaining policy reconstruction

The shared numerical equations are now code.  The remaining 2024 work is to
move area-specific classifications currently embedded as constants/manual
decisions in the nine workbook sheets into a versioned, reviewable policy
table.  In particular, each ditch-month must state whether it is metered,
estimated, unavailable, groundwater supplied, or CRP/natural grassland, and
whether a shortage is assessed.  That policy table is necessary before a
fully automated Table I--IV run can faithfully replace the workbook.

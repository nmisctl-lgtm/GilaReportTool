# Historical scripts

These scripts are retained as source evidence, not as the production compute
path. Their successor modules are:

- `CU_livestock.py` → `backend/non_agricultural_use.py` (`LivestockInventory`)
- `CU_storcktank.py` and `evaporation_data.py` → `backend/non_agricultural_use.py` (`StockTankSite`)
- `weatherData.py` and `II_ClimateProvider.py` → the existing climate ETL work;
  gridMET processing is intentionally outside the current non-agricultural
  calculation baseline.

The historical scripts have overlapping constants, global configuration,
network calls, and incomplete execution paths. New report calculations must
call the backend modules, which receive validated input data explicitly and
are covered by the 2024 regression tests.

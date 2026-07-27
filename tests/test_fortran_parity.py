import unittest

from backend.fortran_parity import (
    CIRProfile,
    ClimateYear,
    CropDefinition,
    Curve,
    DateLimits,
    FortranParityEngine,
    distribute_obc_annual_by_mbc,
    weighted_cir,
)


def climate(**overrides):
    values = dict(
        year=2024,
        monthly_mean_f=(45, 48, 52, 58, 65, 75, 80, 78, 70, 60, 50, 43),
        monthly_precip_in=(0.0,) * 12,
        daylight_pct=(8.0,) * 12,
        last_spring_32_day=100,
        first_fall_32_day=300,
    )
    values.update(overrides)
    return ClimateYear(**values)


class FortranParityTests(unittest.TestCase):
    def test_obc_uses_explicit_frost_dates_and_maximum_growing_season(self):
        crop = CropDefinition("demo", "Demo perennial", "PR", 32, 32, 0.8, 0.4, 120)
        profile = FortranParityEngine(crop, climate()).run("obc_usbr")
        self.assertEqual((profile.season_start_day, profile.season_end_day), (100, 219))
        self.assertEqual(sum(row.growing_days for row in profile.monthly), 120)
        self.assertEqual(sum(row.inside_frost_free_days for row in profile.monthly), 119)
        self.assertEqual(sum(row.outside_frost_free_days for row in profile.monthly), 1)

    def test_usbr_effective_precipitation_is_prorated_and_capped_at_etc(self):
        crop = CropDefinition("demo", "Demo", "PR", 32, 32, 0.01, 0.01)
        wet = climate(monthly_precip_in=(10.0,) * 12)
        profile = FortranParityEngine(crop, wet).run("obc_usbr")
        for row in profile.monthly:
            self.assertLessEqual(row.effective_precip_in, row.etc_in)
            self.assertEqual(row.cir_in, 0.0)

    def test_mbc_applies_kt_floor_and_curve(self):
        crop = CropDefinition(
            "demo", "Demo", "PR", 32, 32, 0.8, 0.4,
            mbc_curve=Curve((0, 366), (1.0, 1.0)),
        )
        profile = FortranParityEngine(crop, climate(monthly_mean_f=(20.0,) * 12)).run("mbc_scs")
        july = profile.monthly[6]
        self.assertEqual(july.kt, 0.3)  # 0.0173 * interpolated temperature - 0.314 is below 0.3 in this fixture
        self.assertEqual(july.coefficient_or_kc, 1.0)

    def test_winter_grain_keeps_spring_and_fall_seasons(self):
        crop = CropDefinition("wg", "Winter grain", "WG", 32, 32, 0.7, 0.35)
        profile = FortranParityEngine(crop, climate()).run("obc_usbr", DateLimits(plant_day=245, harvest_day=213))
        july, september = profile.monthly[6], profile.monthly[8]
        self.assertGreater(july.growing_days, 0)
        self.assertGreater(september.growing_days, 0)
        self.assertEqual(july.outside_frost_free_days, 0)
        self.assertEqual(september.inside_frost_free_days, 0)

    def test_obc_to_mbc_distribution_and_area_weighting_are_explicit(self):
        self.assertEqual(distribute_obc_annual_by_mbc(12.0, (1.0, 2.0, 3.0)), (2.0, 4.0, 6.0))
        crop = CropDefinition("demo", "Demo", "PR", 32, 32, 0.8, 0.4)
        first = FortranParityEngine(crop, climate()).run("obc_usbr")
        second = FortranParityEngine(crop, climate(monthly_precip_in=(1.0,) * 12)).run("obc_usbr")
        weighted = weighted_cir(((first, 3.0), (second, 1.0)))
        self.assertEqual(len(weighted), 12)
        self.assertLess(sum(weighted), first.annual_cir_in)


if __name__ == "__main__":
    unittest.main()

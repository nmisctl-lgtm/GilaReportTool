# Average Area Monthly Pan *(0.8) Evaporation (ft)
PanEvap_CU_areas = {
    "Luna":          [i/12 for i in [1.49,1.97,4.13,5.38,6.19,7.39,5.66,4.70,4.18,3.50,1.82,1.49]],
    "Apache-Aragon": [i/12 for i in [1.64,2.16,4.54,5.91,6.81,8.13,6.23,5.17,4.59,3.85,2.01,1.64]],
    "Reserve":       [i/12 for i in [1.74,2.30,4.82,6.27,7.22,8.62,6.61,5.49,4.87,4.09,2.13,1.74]],
    "Glenwood":      [i/12 for i in [2.21,2.92,6.12,7.97,9.18,10.96,8.40,6.98,6.19,5.20,2.71,2.21]],
    "Upper Gila":    [i/12 for i in [1.56,2.07,4.33,5.64,6.50,7.76,5.94,4.97,4.39,3.70,1.92,1.56]],
    "Redrock":       [i/12 for i in [2.21,2.92,6.12,7.97,9.18,10.96,8.40,6.98,6.19,5.20,2.71,2.21]],
    "Virden":        [i/12 for i in [2.21,2.92,6.12,7.97,9.18,10.96,8.40,6.98,6.19,5.20,2.71,2.21]],
    "San Simon":     [i/12 for i in [2.48,3.28,6.88,8.96,10.32,12.32,9.44,7.84,6.96,5.84,3.04,2.48]],
}

# Number of tanks and weighted average area (ac) in each CU area
Tanks_CU_areas = {
    "Luna":          (30, 0.31),
    "Apache-Aragon": (11, 0.31),
    "Reserve":       (17, 0.31),
    "Glenwood":      (167, 0.31),
    "Hot Springs in SFR":   (660, 0.10),
    "Upper Gila":    (113, 0.30),
    "Cliff Gila Redrock":   (750, 0.30),
    "Hot Springs in GR":    (416, 0.10),
    "Virden":        (22, 0.30),
    "San Simon":     (96, 0.26)
}
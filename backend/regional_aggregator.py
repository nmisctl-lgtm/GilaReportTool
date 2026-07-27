"""
Module: backend/regional_aggregator.py
Description: 
    遵照 1964 年最高法院法令 (1964 Supreme Court Decree) 规范与 NMOSE 官方水账台账 (luna_irrigation.xlsx)，
    实现从“月度渠首引水与气象蒸发数据”计算全流域缺水率 (J32)，
    并推导计算第 32 行 (S32 面积, T32 潜在需水, U32 缺水量, V32 净消耗, W32 附带损耗) 的核心水耗聚合器。
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


# ==============================================================================
# 1. 结构化数据契约 (Data Contracts)
# ==============================================================================

@dataclass
class DitchMonthlyInput:
    """单个计量水渠 (Metered Ditch) 的月度基础输入数据"""
    ditch_name: str                  # 水渠名称 (例如: Northside Luna Ditch)
    crop_acres_F9: float             # F9: 该水渠测绘农作物总面积 (Acres)
    res_acres_F7: float              # F7: 该水渠测绘水库水面总面积 (Acres)
    measured_diversions_E: List[float] # E12:E23: 12个月渠首实测引水量 (AF)


@dataclass
class ClimateMonthlyInput:
    """气象与蒸发 12 个月基础输入数据 (Jan-Dec)"""
    monthly_cir_inches: List[float]  # 月度农作物 CIR (Inches, 来自 Blaney-Criddle 物理引擎)
    gross_lake_evap_C: List[float]   # C12:C23: 月度自由水面毛蒸发深度 (Feet, 历史常数外推)
    precipitation_D: List[float]      # D12:D23: 月度大气降水深度 (Feet)


# ==============================================================================
# 2. 核心计算聚合器 (Regional Aggregator Engine)
# ==============================================================================

class RegionalWaterAggregator:
    def __init__(
        self,
        climate_input: ClimateMonthlyInput,
        ditches_input: List[DitchMonthlyInput],
        unmetered_surface_crop_acres_M29: float,
        unmetered_ground_crop_acres_P29: float,
        metered_res_acres_F31: float,
        unmetered_surface_res_acres_M31: float,
        unmetered_ground_res_acres_P31: float,
        preplant_crop_acres_F30: float = 0.0,
        canal_farm_efficiency_D3: float = 0.30
    ):
        """
        初始化聚合器并绑定基础物理参数
        
        :param canal_farm_efficiency_D3: $D$3 综合灌溉效率 (0.30 = 农田效率40% * 渠道效率75%)
        """
        self.climate = climate_input
        self.ditches = ditches_input
        self.D3 = canal_farm_efficiency_D3
        
        # --- 面积参数 (S列底层输入) ---
        self.F30_preplant_acres = preplant_crop_acres_F30
        self.M29_unmetered_surface_crop_acres = unmetered_surface_crop_acres_M29
        self.P29_unmetered_ground_crop_acres = unmetered_ground_crop_acres_P29
        
        self.F31_metered_res_acres = metered_res_acres_F31
        self.M31_unmetered_surface_res_acres = unmetered_surface_res_acres_M31
        self.P31_unmetered_ground_res_acres = unmetered_ground_res_acres_P31

        # --- 中间过程计算变量存储 ---
        self.B12_to_B23_monthly_div_req: List[float] = [] # B12:B23 月度单位引水需求 (ft/acre)
        self.B24_annual_div_req: float = 0.0              # B24 年引水需求总和 (ft/acre)
        self.C29_unit_crop_cu_factor: float = 0.0         # C29 单位作物全额耗水因子 (AF/acre)
        
        self.C24_gross_lake_evap: float = 0.0             # C24 年毛蒸发深度 (ft)
        self.D24_annual_precip: float = 0.0               # D24 年总降雨深度 (ft)
        self.E_net_lake_evap: float = 0.0                 # C24-D24 水面年净蒸发率 (ft/acre)
        
        self.H32_total_required_diversion: float = 0.0    # H32 全流域地表水理论渠首总需水量 (AF)
        self.I32_total_headgate_shortage: float = 0.0     # I32 全流域地表水渠首实际缺水总和 (AF)
        self.J32_shortage_ratio: float = 0.0              # J32 地表水统一缺水折扣率 (I32 / H32)

    # --------------------------------------------------------------------------
    # 步骤 A: 气象与单位需水量因子推导 (B24, C29, C24, D24)
    # --------------------------------------------------------------------------
    def _compute_unit_factors(self):
        # 1. 逐月计算作物单位面积引水需求 B_m = Monthly_CIR_m / (12 * D3)
        self.B12_to_B23_monthly_div_req = [
            cir / (12.0 * self.D3) for cir in self.climate.monthly_cir_inches
        ]
        # B24: 年度单位引水需求总和 (ft/acre)
        self.B24_annual_div_req = sum(self.B12_to_B23_monthly_div_req)
        
        # C29: 全额供水下，每英亩农田被作物吸收的净耗水量 (AF/acre) = B24 * $D$3
        self.C29_unit_crop_cu_factor = self.B24_annual_div_req * self.D3
        
        # 2. 水库蒸发因子推导
        self.C24_gross_lake_evap = sum(self.climate.gross_lake_evap_C)
        self.D24_annual_precip = sum(self.climate.precipitation_D)
        # (C24 - D24): 水库自由水面年净蒸发深度 (ft)
        self.E_net_lake_evap = self.C24_gross_lake_evap - self.D24_annual_precip

    # --------------------------------------------------------------------------
    # 步骤 B: 12个月双重循环推导地表水缺水率 J32 (I32 / H32)
    # --------------------------------------------------------------------------
    def _compute_shortage_ratio_J32(self):
        total_required_div_H32 = 0.0
        total_shortage_I32 = 0.0

        for m in range(12):
            C_m = self.climate.gross_lake_evap_C[m]
            D_m = self.climate.precipitation_D[m]
            B_m = self.B12_to_B23_monthly_div_req[m]
            
            # 当月水库蒸发净亏水深度 (若降雨>蒸发则为0)
            res_net_loss_depth = 0.0 if (C_m - D_m) < 0 else abs(C_m - D_m)

            for ditch in self.ditches:
                # F18: 当月水库蒸发引水需求 (ac-ft)
                F18_res_evap_vol = ditch.res_acres_F7 * res_net_loss_depth
                # G18: 水库折算到渠首的总引水需求 = F18 / D3
                G18_res_div_req = F18_res_evap_vol / self.D3
                
                # H18: 作物折算到渠首的总引水需求 = F$9 * B18
                H18_crop_div_req = ditch.crop_acres_F9 * B_m
                
                # I18: 该水渠当月综合渠首引水总需求 = G18 + H18
                I18_total_ditch_req = G18_res_div_req + H18_crop_div_req
                
                # E18: 当月渠首实测引水量
                E18_measured_div = ditch.measured_diversions_E[m]
                
                # J18: 当月实际引水缺口 = IF(E18 - I18 > 0, 0, ABS(E18 - I18))
                J18_monthly_shortage = 0.0 if (E18_measured_div - I18_total_ditch_req) > 0 else abs(E18_measured_div - I18_total_ditch_req)
                
                # 累加到全流域年度总账
                total_required_div_H32 += I18_total_ditch_req
                total_shortage_I32 += J18_monthly_shortage

        self.H32_total_required_diversion = total_required_div_H32
        self.I32_total_headgate_shortage = total_shortage_I32
        
        # J32: 全流域统一地表水缺水率 = I32 / H32
        if self.H32_total_required_diversion > 0:
            self.J32_shortage_ratio = self.I32_total_headgate_shortage / self.H32_total_required_diversion
        else:
            self.J32_shortage_ratio = 0.0

    # --------------------------------------------------------------------------
    # 步骤 C: 推导第 32 行 (S32, T32, U32, V32, W32) 及 Table II 最终汇总
    # --------------------------------------------------------------------------
    def run_decree_aggregation(self) -> Dict[str, float]:
        self._compute_unit_factors()
        self._compute_shortage_ratio_J32()

        # --- 1. S列: 面积台账 (Acres) ---
        # F29: 计量水渠净农作物面积 = 所有水渠测绘作物面积之和 - Preplant缺水面积
        total_metered_raw_crop_acres = sum(d.crop_acres_F9 for d in self.ditches)
        F29_metered_net_crop_acres = total_metered_raw_crop_acres - self.F30_preplant_acres
        
        # S29: 常规农作物总面积 = F29 (计量) + M29 (未计量地表) + P29 (未计量地下水)
        S29_total_crop_acres = F29_metered_net_crop_acres + self.M29_unmetered_surface_crop_acres + self.P29_unmetered_ground_crop_acres
        
        # S31: 水库蒸发总面积 = F31 + M31 + P31
        S31_total_res_acres = self.F31_metered_res_acres + self.M31_unmetered_surface_res_acres + self.P31_unmetered_ground_res_acres
        
        # S32: 全流域总评估面积 = S29 + S30(Preplant) + S31
        S32_total_land_acres = S29_total_crop_acres + self.F30_preplant_acres + S31_total_res_acres

        # --- 2. T列: 潜在全额需水量 (Full Supply CU in AF) ---
        G29_metered_crop_full_cu = F29_metered_net_crop_acres * self.C29_unit_crop_cu_factor
        N29_unmetered_surface_full_cu = self.M29_unmetered_surface_crop_acres * self.C29_unit_crop_cu_factor
        Q29_unmetered_ground_full_cu = self.P29_unmetered_ground_crop_acres * self.C29_unit_crop_cu_factor
        
        # T29: 常规农作物全额潜在耗水总和
        T29_crop_full_supply_cu = G29_metered_crop_full_cu + N29_unmetered_surface_full_cu + Q29_unmetered_ground_full_cu
        
        # 水库全额蒸发量 T31 = G31 + N31 + Q31
        G31_metered_res_full_evap = self.F31_metered_res_acres * self.E_net_lake_evap
        N31_unmetered_surface_res_full_evap = self.M31_unmetered_surface_res_acres * self.E_net_lake_evap
        Q31_unmetered_ground_res_full_evap = self.P31_unmetered_ground_res_acres * self.E_net_lake_evap
        
        T31_res_full_supply_evap = G31_metered_res_full_evap + N31_unmetered_surface_res_full_evap + Q31_unmetered_ground_res_full_evap
        
        # T32: 全流域总潜在耗水量 = T29 + T30(0) + T31
        T32_total_full_supply_cu = T29_crop_full_supply_cu + T31_res_full_supply_evap

        # --- 3. U列: 缺水扣减项 (Shortage to Full Supply in AF) ---
        # 地表水作物的缺水量 (K29:计量水渠缺水, O29:未计量地表水缺水)
        K29_metered_crop_shortage = G29_metered_crop_full_cu * self.J32_shortage_ratio
        O29_unmetered_surface_crop_shortage = N29_unmetered_surface_full_cu * self.J32_shortage_ratio
        # 注: 地下水 (Q29) 随抽随用，缺水量恒等于 0
        U29_crop_total_shortage = K29_metered_crop_shortage + O29_unmetered_surface_crop_shortage
        
        # 地表水水库的缺水量 (K31:计量水库缺水, O31:未计量地表水库缺水)
        K31_metered_res_shortage = G31_metered_res_full_evap * self.J32_shortage_ratio
        O31_unmetered_surface_res_shortage = N31_unmetered_surface_res_full_evap * self.J32_shortage_ratio
        U31_res_total_shortage = K31_metered_res_shortage + O31_unmetered_surface_res_shortage
        
        # U32: 全流域总缺水扣减量 = U29 + U30(0) + U31
        U32_total_shortage = U29_crop_total_shortage + U31_res_total_shortage

        # --- 4. V列: 净实际消耗量 (Net Consumptive Use in AF) ---
        V29_net_crop_cu = T29_crop_full_supply_cu - U29_crop_total_shortage
        V31_net_res_evap = T31_res_full_supply_evap - U31_res_total_shortage
        
        # V32: 全流域总净消耗量 = T32 - U32
        V32_total_net_cu = T32_total_full_supply_cu - U32_total_shortage

        # --- 5. W列: 法定附带消耗量 (Incidental Use in AF) ---
        # Q32: 全区地下水 Consumptive Use 总账 = Q29 + Q30(0) + Q31
        Q32_total_groundwater_cu = Q29_unmetered_ground_full_cu + Q31_unmetered_ground_res_full_evap
        
        # 地表水实际净消耗量 = V32 - Q32
        surface_water_net_cu = V32_total_net_cu - Q32_total_groundwater_cu
        
        # W32 最终公式: 地表水净消耗*10% (渠道/深层渗漏) + 地下水净消耗*2% (管网损耗)
        W32_incidental_use = (surface_water_net_cu * 0.10) + (Q32_total_groundwater_cu * 0.02)

        # --- 6. Table II 最终农业灌溉总耗水量 (Final Decree Irrigation CU) ---
        final_irrigation_cu_af = V32_total_net_cu + W32_incidental_use

        # 返回与 Excel 第 32 行及 Table II 完美对应的结构化结果
        return {
            "S32_Total_Acres": round(S32_total_land_acres, 2),
            "S29_Crop_Acres": round(S29_total_crop_acres, 2),
            "S31_Res_Acres": round(S31_total_res_acres, 2),
            "T32_Full_Supply_CU_AF": round(T32_total_full_supply_cu, 2),
            "U32_Total_Shortage_AF": round(U32_total_shortage, 2),
            "V32_Net_CU_AF": round(V32_total_net_cu, 2),
            "Q32_Groundwater_CU_AF": round(Q32_total_groundwater_cu, 2),
            "W32_Incidental_Use_AF": round(W32_incidental_use, 2),
            "J32_Shortage_Ratio_Pct": round(self.J32_shortage_ratio * 100, 2),
            "Table2_Final_Irrigation_CU_AF": round(final_irrigation_cu_af, 2)
        }


# ==============================================================================
# 3. 本地集成运行测试 (演示基准 Luna 数据)
# ==============================================================================
if __name__ == "__main__":
    # 1. 模拟 Luna 12个月气象输入 (CIR, Gross Evap C, Precip D)
    luna_climate = ClimateMonthlyInput(
        monthly_cir_inches=[0.0, 0.0, 0.0, 0.56, 2.60, 4.38, 2.33, 2.96, 2.92, 1.57, 0.0, 0.0], # 年和 17.32 in
        gross_lake_evap_C=[0.10, 0.12, 0.20, 0.35, 0.45, 0.55, 0.50, 0.40, 0.30, 0.18, 0.10, 0.08], # 年和 3.33 ft
        precipitation_D=[0.08, 0.07, 0.06, 0.04, 0.05, 0.08, 0.25, 0.28, 0.15, 0.08, 0.06, 0.07]    # 年和 1.27 ft
    )

    # 2. 模拟 6 条计量水渠输入
    ditches = [
        DitchMonthlyInput("Northside Luna Ditch", crop_acres_F9=77.00, res_acres_F7=1.22, measured_diversions_E=[10,12,15,20,30,25,20,18,15,12,10,8]),
        DitchMonthlyInput("William S. Laney Ditch", crop_acres_F9=38.58, res_acres_F7=1.25, measured_diversions_E=[5,6,8,10,15,12,10,9,8,6,5,4]),
        DitchMonthlyInput("A. Laney Ditch", crop_acres_F9=14.44, res_acres_F7=0.00, measured_diversions_E=[2,2,3,4,6,5,4,3,3,2,2,1]),
        DitchMonthlyInput("Leslie Laney Ditch", crop_acres_F9=0.00, res_acres_F7=0.06, measured_diversions_E=[0,0,0,0,1,1,0,0,0,0,0,0]),
        DitchMonthlyInput("Adair Luna Ditch", crop_acres_F9=12.23, res_acres_F7=0.00, measured_diversions_E=[1,1,2,3,4,4,3,2,2,1,1,1]),
        DitchMonthlyInput("Ditch 6", crop_acres_F9=0.00, res_acres_F7=0.00, measured_diversions_E=[0]*12),
    ]

    # 3. 运行聚合器
    aggregator = RegionalWaterAggregator(
        climate_input=luna_climate,
        ditches_input=ditches,
        unmetered_surface_crop_acres_M29=15.01,
        unmetered_ground_crop_acres_P29=26.10,
        metered_res_acres_F31=2.53,
        unmetered_surface_res_acres_M31=21.92,
        unmetered_ground_res_acres_P31=0.00
    )
    
    results = aggregator.run_decree_aggregation()
    
    print("\n" + "="*65)
    print(">>> 📊 1964 最高法院法令 Table II (第 32 行) 计算结果汇总 <<<")
    print("="*65)
    for k, v in results.items():
        print(f"  {k:<35}: {v}")
    print("="*65 + "\n")
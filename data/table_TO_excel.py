import arcpy
arcpy.ImportToolbox(r"@\Conversion Tools.tbx")
arcpy.conversion.TableToExcel(
    Input_Table=r"'Irrigated Acreage\VV_IA_2025'",
    Output_Excel_File=r"C:\LocalProjects\GilaReportTool\data\VVIA_IA_2025.xls",
    Use_field_alias_as_column_header="ALIAS",
    Use_domain_and_subtype_description="DESCRIPTION"
)

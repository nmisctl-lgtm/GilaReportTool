"""Command-line entry point / 命令行入口。"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.report_preview import build_2024_table_two_preview


DEFAULT_2024_WORKBOOK = (
    Path(__file__).parent / "OldMethod_Report/Spreadsheet/2024 Gila Report Data_WORKING.xlsx"
)


def main() -> None:
    """Run a friendly, read-only report preview / 运行只读报告预览。"""

    argument_parser = argparse.ArgumentParser(
        description="Gila Report Tool / Gila 报告工具",
    )
    subcommands = argument_parser.add_subparsers(dest="command", required=True)
    validate_2024 = subcommands.add_parser(
        "validate-2024",
        help="calculate and display reviewed 2024 Table II totals / 计算并显示已核对的 2024 Table II 总量",
    )
    validate_2024.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_2024_WORKBOOK,
        help="2024 working workbook path / 2024 工作簿路径",
    )
    arguments = argument_parser.parse_args()

    if arguments.command == "validate-2024":
        preview = build_2024_table_two_preview(arguments.workbook)
        print(f"Table II Annual Consumptive Use / Table II 年耗水量 ({preview.report_year}, acre-feet / 英亩英尺)")
        for row in preview.rows:
            print(f"{row.stream_system}: {row.annual_use_af:.6f}")


if __name__ == "__main__":
    main()

"""Export measurement results to Excel with a summary statistics sheet."""

from __future__ import annotations
from pathlib import Path
import pandas as pd
from ._common import results_to_dataframe


def export_excel(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    df = results_to_dataframe(results, nm_per_pixel)
    ok = df[df["status"] == "OK"]["y_cd_nm"].dropna()

    stats = {
        "Metric": ["Count", "Mean (nm)", "Median (nm)", "Std Dev (nm)",
                   "3-Sigma (nm)", "Min (nm)", "Max (nm)"],
        "Value": [
            len(ok),
            round(ok.mean(), 3) if len(ok) else "N/A",
            round(ok.median(), 3) if len(ok) else "N/A",
            round(ok.std(), 3) if len(ok) else "N/A",
            round(ok.std() * 3, 3) if len(ok) else "N/A",
            round(ok.min(), 3) if len(ok) else "N/A",
            round(ok.max(), 3) if len(ok) else "N/A",
        ],
    }
    df_stats = pd.DataFrame(stats)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Measurements", index=False)
        df_stats.to_excel(writer, sheet_name="Statistics", index=False)

        # Highlight MIN/MAX rows in Measurements sheet
        wb = writer.book
        ws = wb["Measurements"]
        from openpyxl.styles import PatternFill
        red_fill = PatternFill("solid", fgColor="FFAAAA")
        blue_fill = PatternFill("solid", fgColor="AAAAFF")
        flag_col = df.columns.get_loc("flag") + 1  # 1-based

        for row_idx, flag in enumerate(df["flag"], start=2):  # row 1 = header
            if flag == "MIN":
                for cell in ws[row_idx]:
                    cell.fill = red_fill
            elif flag == "MAX":
                for cell in ws[row_idx]:
                    cell.fill = blue_fill

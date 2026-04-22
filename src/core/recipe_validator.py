"""RecipeValidator — 以 golden sample 驗證 Recipe 量測準確度。"""
from __future__ import annotations

import statistics
from pathlib import Path
from typing import Callable

from .models import ImageRecord, GoldenSampleEntry, ValidationResult, MeasurementRecord
from .recipe_base import BaseRecipe


class RecipeValidator:
    """執行 golden sample 驗證並計算 Bias / Precision 統計。"""

    def __init__(self, recipe: BaseRecipe):
        self._recipe = recipe

    def run(
        self,
        entries: list[GoldenSampleEntry],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ValidationResult]:
        """依序量測每張 golden sample，回傳驗證結果清單。"""
        results = []
        total = len(entries)
        for i, entry in enumerate(entries):
            if on_progress:
                on_progress(i, total, Path(entry.file_path).name)
            ir = ImageRecord.from_path(entry.file_path)
            try:
                pr = self._recipe.run_pipeline(ir)
                measured = self._find_measurement(
                    pr.records, entry.cmg_id, entry.col_id
                )
                if measured is not None:
                    bias = measured - entry.reference_nm
                    results.append(ValidationResult(
                        file_path=entry.file_path,
                        reference_nm=entry.reference_nm,
                        measured_nm=measured,
                        bias_nm=bias,
                    ))
                else:
                    results.append(ValidationResult(
                        file_path=entry.file_path,
                        reference_nm=entry.reference_nm,
                        measured_nm=None,
                        bias_nm=None,
                        error=(f"No measurement found for "
                               f"cmg_id={entry.cmg_id}, col_id={entry.col_id}"),
                    ))
            except Exception as exc:
                results.append(ValidationResult(
                    file_path=entry.file_path,
                    reference_nm=entry.reference_nm,
                    measured_nm=None,
                    bias_nm=None,
                    error=str(exc),
                ))
        if on_progress:
            on_progress(total, total, "Done")
        return results

    @staticmethod
    def _find_measurement(
        records: list[MeasurementRecord],
        cmg_id: int,
        col_id: int,
    ) -> float | None:
        for r in records:
            if r.cmg_id == cmg_id and r.col_id == col_id:
                return float(r.calibrated_nm)
        return None

    @staticmethod
    def compute_stats(results: list[ValidationResult]) -> dict:
        """計算 Bias 統計（Mean Bias、Precision、3-Sigma Bias 等）。"""
        ok = [r for r in results if r.success]
        if not ok:
            return {"n": 0, "n_fail": len(results)}
        biases = [r.bias_nm for r in ok]
        n = len(biases)
        mean_bias = statistics.mean(biases)
        precision = statistics.stdev(biases) if n > 1 else 0.0
        return {
            "n": n,
            "n_fail": len(results) - n,
            "mean_bias_nm": round(mean_bias, 4),
            "precision_nm": round(precision, 4),
            "3sigma_nm": round(precision * 3, 4),
            "max_abs_bias_nm": round(max(abs(b) for b in biases), 4),
            "bias_values": biases,
        }

"""Measurement engine — orchestrates single-image and batch pipeline runs.

Batch runs use ProcessPoolExecutor.  All worker args are serialised to plain
dicts to satisfy pickle constraints.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .models import ImageRecord, MeasurementRecord, BatchRunRecord
from .recipe_base import BaseRecipe, PipelineResult
from .recipe_registry import RecipeRegistry


class MeasurementEngine:
    """Runs recipes against images — single shot or parallel batch."""

    def __init__(self, registry: RecipeRegistry):
        self._registry = registry

    # ── Single image ──────────────────────────────────────────────────────────

    def run_single(
        self,
        image_record: ImageRecord,
        recipe: BaseRecipe,
    ) -> PipelineResult:
        return recipe.run_pipeline(image_record)

    # ── Batch ─────────────────────────────────────────────────────────────────

    def run_batch(
        self,
        image_records: list[ImageRecord],
        recipe_ids: list[str],
        on_progress: Callable[[int, int, str, str], None] | None = None,
        max_workers: int | None = None,
    ) -> BatchRunRecord:
        """Run all recipe_ids against all image_records in parallel.

        Results are stored in BatchRunRecord.output_manifest["results"] as a
        list of dicts, each containing both new-format "measurements" and
        legacy-format "cuts" for backward compatibility.
        """
        if max_workers is None:
            max_workers = max(1, (os.cpu_count() or 2) - 1)

        recipes = [self._registry.get(rid) for rid in recipe_ids]
        recipes = [r for r in recipes if r is not None]

        input_folder = str(Path(image_records[0].file_path).parent) if image_records else ""
        batch = BatchRunRecord(
            batch_id=str(uuid.uuid4()),
            input_folder=input_folder,
            recipe_ids=recipe_ids,
            total_images=len(image_records),
            start_time=datetime.now(timezone.utc).isoformat(),
            worker_count=max_workers,
        )

        args_list = [
            _make_worker_args(ir, recipes)
            for ir in image_records
        ]

        results: list[dict] = []
        total = len(args_list)
        done = 0

        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(_worker_run_image, args): args["image_path"]
                for args in args_list
            }
            for future in as_completed(future_map):
                done += 1
                result_dict = future.result()
                results.append(result_dict)
                if on_progress:
                    on_progress(done, total, Path(result_dict["image_path"]).name,
                                result_dict["status"])
                if result_dict["status"] == "OK":
                    batch.success_count += 1
                else:
                    batch.fail_count += 1
                    batch.error_log.append({
                        "image_path": result_dict["image_path"],
                        "error": result_dict.get("error", ""),
                    })

        batch.end_time = datetime.now(timezone.utc).isoformat()
        batch.output_manifest["results"] = results
        return batch


# ── Top-level picklable worker functions ──────────────────────────────────────

def _make_worker_args(image_record: ImageRecord, recipes: list[BaseRecipe]) -> dict:
    """Serialise ImageRecord + recipes to a plain dict for subprocess pickling."""
    return {
        "image_path": image_record.file_path,
        "image_id": image_record.image_id,
        "pixel_size_nm": float(image_record.pixel_size_nm),
        "recipe_descriptors": [r.recipe_descriptor.to_dict() for r in recipes],
    }


def _worker_run_image(args: dict) -> dict:
    """Top-level picklable function that runs inside a subprocess.

    Reconstructs CMGRecipe from descriptor dict, runs pipeline, serialises
    results to plain dicts.
    """
    from .models import ImageRecord, MeasurementRecord
    from .recipes.cmg_recipe import CMGRecipe
    from .recipe_base import MeasurementRecipe

    image_path = args["image_path"]
    result: dict = {
        "image_path": image_path,
        "image_id": args["image_id"],
        "status": "OK",
        "error": "",
        "measurements": [],
        "cuts": [],
    }

    try:
        ir = ImageRecord.from_path(image_path, pixel_size_nm=args["pixel_size_nm"])
        ir.image_id = args["image_id"]

        all_records: list[MeasurementRecord] = []
        all_cuts: list = []
        cmg_id_offset = 0

        for rd_dict in args["recipe_descriptors"]:
            descriptor = MeasurementRecipe.from_dict(rd_dict)
            recipe = CMGRecipe(descriptor=descriptor)
            pr = recipe.run_pipeline(ir)

            # Offset cmg_ids to avoid collisions across recipes
            for rec in pr.records:
                rec.cmg_id += cmg_id_offset
            cuts = pr.context.get("cmg_cuts", [])
            for cut in cuts:
                cut.cmg_id += cmg_id_offset
            if cuts:
                cmg_id_offset += max(c.cmg_id for c in cuts) + 1

            all_records.extend(pr.records)
            all_cuts.extend(cuts)

        if not all_records:
            result["status"] = "FAIL"
            result["error"] = "No measurements detected"
        else:
            result["measurements"] = [r.to_dict() for r in all_records]
            from .._compat import serialise_cuts_from_records
            result["cuts"] = serialise_cuts_from_records(all_records)

    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)

    return result

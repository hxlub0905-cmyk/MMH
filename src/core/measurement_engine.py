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
from typing import Callable, Optional

from .models import ImageRecord, MeasurementRecord, BatchRunRecord, MultiDatasetBatchRun
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
        on_progress: Callable[[int, int, str, str, dict], None] | None = None,
        max_workers: int | None = None,
        output_dir: Path | None = None,
        abort_check: Callable[[], bool] | None = None,
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
            _make_worker_args(ir, recipes, output_dir=output_dir)
            for ir in image_records
        ]

        results: list[dict] = []
        total = len(args_list)
        done = 0

        pool = ProcessPoolExecutor(max_workers=max_workers)
        try:
            future_map = {
                pool.submit(_worker_run_image, args): args["image_path"]
                for args in args_list
            }
            for future in as_completed(future_map):
                if abort_check and abort_check():
                    break
                done += 1
                result_dict = future.result()
                results.append(result_dict)
                if on_progress:
                    on_progress(done, total, Path(result_dict["image_path"]).name,
                                result_dict["status"], result_dict)
                if result_dict["status"] == "OK":
                    batch.success_count += 1
                else:
                    batch.fail_count += 1
                    batch.error_log.append({
                        "image_path": result_dict["image_path"],
                        "error": result_dict.get("error", ""),
                    })
        finally:
            # Set end_time before shutdown so it is always stamped even when
            # abort_check triggers a break or an unhandled exception propagates.
            batch.end_time = datetime.now(timezone.utc).isoformat()
            pool.shutdown(wait=False, cancel_futures=True)

        batch.output_manifest["results"] = results
        return batch


    def run_multi_batch(
        self,
        datasets: list[dict],
        on_dataset_start: Callable[[int, int, str], None] | None = None,
        on_progress: Callable[[int, int, str, str, dict], None] | None = None,
        max_workers: int | None = None,
        output_dir: Path | None = None,
        abort_check: Callable[[], bool] | None = None,
    ) -> MultiDatasetBatchRun:
        """Run run_batch() sequentially for each dataset and aggregate results.

        Each dataset dict must have keys: "label" (str), "image_records" (list),
        "recipe_ids" (list[str]).
        """
        mbr = MultiDatasetBatchRun(
            run_id=str(uuid.uuid4()),
            start_time=datetime.now(timezone.utc).isoformat(),
            worker_count=max_workers or max(1, (os.cpu_count() or 2) - 1),
        )
        total_all = sum(len(ds["image_records"]) for ds in datasets)
        offset = 0
        for i, ds in enumerate(datasets):
            if abort_check and abort_check():
                break
            label = ds.get("label", f"Dataset {i+1}")
            if on_dataset_start:
                on_dataset_start(i + 1, len(datasets), label)

            # Wrap the progress callback so `done` is global across all datasets
            # and `total` reflects the overall image count — preventing the bar
            # from resetting at the start of each dataset.
            ds_offset = offset
            def _wrapped(done, _total, name, status, result_dict=None,
                         _off=ds_offset, _tot=total_all):
                if on_progress:
                    on_progress(done + _off, _tot, name, status, result_dict)

            ds_label = label
            br = self.run_batch(
                image_records=ds["image_records"],
                recipe_ids=ds["recipe_ids"],
                on_progress=_wrapped if on_progress else None,
                max_workers=max_workers,
                output_dir=Path(output_dir) / ds_label if output_dir else None,
                abort_check=abort_check,
            )
            br.dataset_label = label
            mbr.datasets.append(br)
            offset += len(ds["image_records"])
        mbr.end_time = datetime.now(timezone.utc).isoformat()
        return mbr


# ── Top-level picklable worker functions ──────────────────────────────────────

def _make_worker_args(
    image_record: ImageRecord,
    recipes: list[BaseRecipe],
    output_dir: Path | None = None,
) -> dict:
    """Serialise ImageRecord + recipes to a plain dict for subprocess pickling."""
    return {
        "image_path": image_record.file_path,
        "image_id": image_record.image_id,
        "pixel_size_nm": float(image_record.pixel_size_nm),
        "recipe_descriptors": [r.recipe_descriptor.to_dict() for r in recipes],
        "output_dir": str(output_dir) if output_dir else None,
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
        pr_list = []

        for rd_dict in args["recipe_descriptors"]:
            descriptor = MeasurementRecipe.from_dict(rd_dict)
            recipe = CMGRecipe(descriptor=descriptor)
            pr = recipe.run_pipeline(ir)
            pr_list.append(pr)

            # Offset cmg_ids to avoid collisions across recipes
            for rec in pr.records:
                rec.cmg_id += cmg_id_offset
            cuts = pr.context.get("cmg_cuts", [])
            for cut in cuts:
                cut.cmg_id += cmg_id_offset
            if cuts:
                cmg_id_offset += max(c.cmg_id for c in cuts) + 1
            else:
                cmg_id_offset += 1000  # empty recipe; reserve gap to prevent collision

            all_records.extend(pr.records)
            all_cuts.extend(cuts)

        if not all_records:
            result["status"] = "FAIL"
            result["error"] = "No measurements detected"
        else:
            result["measurements"] = [r.to_dict() for r in all_records]
            from .._compat import serialise_cuts_from_records
            result["cuts"] = serialise_cuts_from_records(all_records)

            if args.get("output_dir") and pr_list:
                try:
                    import cv2
                    from .annotator import draw_overlays, OverlayOptions
                    out_dir = Path(args["output_dir"])
                    out_dir.mkdir(parents=True, exist_ok=True)
                    last_pr = pr_list[-1]
                    cuts_last = last_pr.context.get("cmg_cuts", [])
                    raw = last_pr.raw
                    if cuts_last:
                        annotated = draw_overlays(
                            raw, None, cuts_last,
                            OverlayOptions(show_lines=True, show_labels=True,
                                           show_boxes=False, show_legend=True)
                        )
                    else:
                        annotated = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
                    stem = Path(image_path).stem
                    out_path = str(out_dir / f"{stem}_annotated.png")
                    cv2.imwrite(out_path, annotated)
                    result["overlay_path"] = out_path
                except Exception as exc:
                    result["overlay_path"] = None
                    result["overlay_error"] = str(exc)

    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)

    return result

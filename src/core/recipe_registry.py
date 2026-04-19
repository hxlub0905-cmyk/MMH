"""Recipe registry — discovers, loads, saves, and instantiates recipes.

Recipes are stored as JSON files in ~/.mmh/recipes/<recipe_id>.json.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .recipe_base import BaseRecipe, MeasurementRecipe


RECIPE_DIR = Path.home() / ".mmh" / "recipes"


class RecipeRegistry:
    """Maps recipe_id → MeasurementRecipe descriptor; instantiates BaseRecipe on demand."""

    def __init__(self, recipe_dir: Path | None = None):
        self._dir = recipe_dir or RECIPE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._descriptors: dict[str, MeasurementRecipe] = {}
        self._load_all()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                recipe = MeasurementRecipe.from_dict(d)
                self._descriptors[recipe.recipe_id] = recipe
            except Exception:
                pass

    def save(self, descriptor: MeasurementRecipe) -> None:
        descriptor.modified_at = datetime.now(timezone.utc).isoformat()
        path = self._dir / f"{descriptor.recipe_id}.json"
        path.write_text(
            json.dumps(descriptor.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._descriptors[descriptor.recipe_id] = descriptor

    def delete(self, recipe_id: str) -> bool:
        path = self._dir / f"{recipe_id}.json"
        if path.exists():
            path.unlink()
            self._descriptors.pop(recipe_id, None)
            return True
        return False

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_recipes(self) -> list[MeasurementRecipe]:
        return sorted(self._descriptors.values(), key=lambda r: r.recipe_name)

    def get_descriptor(self, recipe_id: str) -> MeasurementRecipe | None:
        return self._descriptors.get(recipe_id)

    def get(self, recipe_id: str) -> BaseRecipe | None:
        """Instantiate and return a BaseRecipe for the given recipe_id."""
        desc = self.get_descriptor(recipe_id)
        if desc is None:
            return None
        if desc.recipe_type in ("CMG_YCD", "CMG_XCD"):
            from .recipes.cmg_recipe import CMGRecipe
            return CMGRecipe(descriptor=desc)
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def import_from_card(self, card: dict) -> MeasurementRecipe:
        """Convert a legacy ControlPanel card dict to a saved MeasurementRecipe."""
        from .recipes.cmg_recipe import CMGRecipe
        desc = CMGRecipe._card_to_descriptor(card)
        desc.created_at = datetime.now(timezone.utc).isoformat()
        self.save(desc)
        return desc

    def create_default_cmg(self) -> MeasurementRecipe:
        """Create and save a default CMG Y-CD recipe."""
        from .recipe_base import RecipeConfig
        desc = MeasurementRecipe(
            recipe_id=str(uuid.uuid4()),
            recipe_name="CMG Y-CD (Default)",
            recipe_type="CMG_YCD",
            feature_family="CMG",
            axis_mode="Y",
            preprocess_config=RecipeConfig(data={
                "gl_min": 100,
                "gl_max": 220,
                "gauss_kernel": 3,
                "morph_open_k": 3,
                "morph_close_k": 5,
                "use_clahe": True,
                "clahe_clip": 2.0,
                "clahe_grid": 8,
            }),
            detector_config=RecipeConfig(data={"min_area": None}),
            edge_locator_config=RecipeConfig(data={
                "x_overlap_ratio": 0.5,
                "y_cluster_tol": 10,
            }),
        )
        desc.created_at = datetime.now(timezone.utc).isoformat()
        self.save(desc)
        return desc

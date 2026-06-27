from __future__ import annotations

import pytest

from llm_geoprocessing.domain.geoprocess import BBox, GeoProcessPlan


def test_bbox_validates_coordinate_order() -> None:
    with pytest.raises(ValueError):
        BBox.from_list([-58.3, -34.7, -58.6, -34.5])


def test_plan_validates_action_references() -> None:
    plan = GeoProcessPlan.model_validate(
        {
            "products": [
                {
                    "id": "A",
                    "name": "COPERNICUS/S2_SR_HARMONIZED",
                    "date": {"initial_date": "2024-01-01", "end_date": "2024-01-31"},
                    "proj": "default",
                    "res": "default",
                }
            ],
            "actions": [
                {
                    "geoprocess_name": "index_composite",
                    "input_json": {"product_id": "A", "bbox": [-58.6, -34.7, -58.3, -34.5]},
                    "output_id": "ndvi_result",
                }
            ],
            "other_params": {},
        }
    )
    assert plan.actions[0].output_id == "ndvi_result"


def test_plan_rejects_unknown_reference() -> None:
    with pytest.raises(ValueError):
        GeoProcessPlan.model_validate(
            {
                "products": [],
                "actions": [
                    {
                        "geoprocess_name": "index_composite",
                        "input_json": {"product_id": "missing"},
                        "output_id": "bad",
                    }
                ],
                "other_params": {},
            }
        )

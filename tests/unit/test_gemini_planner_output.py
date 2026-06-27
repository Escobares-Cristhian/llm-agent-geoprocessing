from llm_geoprocessing.graph.nodes import _parse_geoprocess_plan


def test_parse_geoprocess_plan_strips_markdown_fences() -> None:
    raw = '''```json
{"schema_version":"v1","products":[],"actions":[],"other_params":{},"assumptions":[]}
```'''

    plan = _parse_geoprocess_plan(raw)

    assert plan.schema_version == "v1"
    assert plan.products == []
    assert plan.actions == []


def test_parse_geoprocess_plan_accepts_legacy_gemini_plan_shape() -> None:
    raw = '''```json
{
  "plan": [
    {
      "operation": "index_single_date",
      "id": "NDVI_20240115",
      "cloud_cover": 0.1,
      "date": "2024-01-15",
      "index": "NDVI",
      "sensor": "SENTINEL_2",
      "bbox": {
        "south": -34.6,
        "west": -58.4,
        "north": -34.5,
        "east": -58.3
      }
    }
  ]
}
```'''

    plan = _parse_geoprocess_plan(raw)

    assert plan.products[0].name == "COPERNICUS/S2_SR_HARMONIZED"
    assert plan.actions[0].geoprocess_name == "index_single_date"
    assert plan.actions[0].input_json["bbox"] == [-58.4, -34.6, -58.3, -34.5]
    assert plan.actions[0].input_json["product_id"] == "P1"

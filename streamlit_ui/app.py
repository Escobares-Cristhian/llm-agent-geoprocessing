from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import folium
import numpy as np
import requests
import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
except Exception:  # pragma: no cover - handled in UI at runtime
    rasterio = None  # type: ignore[assignment]
    Resampling = None  # type: ignore[assignment]
    transform_bounds = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    timeout_seconds: int


def _api_config() -> ApiConfig:
    return ApiConfig(
        base_url=os.getenv("GEOLLM_API_URL", "http://geollm-api:8080").rstrip("/"),
        timeout_seconds=int(os.getenv("STREAMLIT_API_TIMEOUT_SECONDS", "900")),
    )


def _init_state() -> None:
    st.session_state.setdefault("thread_id", str(uuid4()))
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("runs", [])
    st.session_state.setdefault("plans", [])
    st.session_state.setdefault("artifacts", [])
    st.session_state.setdefault("pending_run_id", None)


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = _api_config()
    response = requests.post(
        f"{config.base_url}{path}",
        json=payload,
        timeout=config.timeout_seconds,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(json.dumps(body, indent=2, ensure_ascii=False))
    return body


def _run_message(message: str) -> dict[str, Any]:
    pending_run_id = st.session_state.get("pending_run_id")
    if pending_run_id:
        return _post_json(f"/runs/{pending_run_id}/resume", {"answer": message})
    return _post_json(
        "/runs",
        {
            "message": message,
            "thread_id": st.session_state["thread_id"],
            "metadata": {"client": "streamlit-ui"},
        },
    )


def _artifact_label(artifact: dict[str, Any]) -> str:
    uri = artifact.get("uri", "")
    operation = artifact.get("metadata", {}).get("operation")
    artifact_id = artifact.get("id", "artifact")
    name = Path(uri).name if uri else artifact_id
    return f"{name}" + (f" ({operation})" if operation else "")


def _assistant_text(response: dict[str, Any]) -> str:
    if response.get("status") == "needs_input":
        clarification = response.get("clarification") or {}
        questions = clarification.get("questions") or []
        if questions:
            return "I need one more detail:\n" + "\n".join(f"- {q}" for q in questions)
        return "I need one more detail before running this."

    if response.get("error"):
        return "Run failed:\n" + json.dumps(response["error"], indent=2, ensure_ascii=False)

    result = response.get("result") or {}
    answer = result.get("answer") or "Run completed."
    artifacts = result.get("artifacts") or []
    if artifacts:
        answer += "\n\nArtifacts:\n" + "\n".join(f"- {_artifact_label(a)}: {a.get('uri')}" for a in artifacts)
    return answer


def _record_response(response: dict[str, Any]) -> None:
    st.session_state["runs"].append(response)
    if response.get("status") == "needs_input":
        st.session_state["pending_run_id"] = response.get("run_id")
    else:
        st.session_state["pending_run_id"] = None

    result = response.get("result") or {}
    plan = result.get("plan")
    if plan:
        st.session_state["plans"].append({"run_id": response.get("run_id"), "plan": plan})

    for artifact in result.get("artifacts") or []:
        if artifact not in st.session_state["artifacts"]:
            st.session_state["artifacts"].append(artifact)


def _array_to_uint8(data: np.ndarray) -> np.ndarray:
    valid = np.isfinite(data)
    if not valid.any():
        return np.zeros(data.shape, dtype=np.uint8)
    lower = float(np.nanpercentile(data[valid], 2))
    upper = float(np.nanpercentile(data[valid], 98))
    if lower == upper:
        upper = lower + 1.0
    scaled = np.clip((data - lower) / (upper - lower), 0, 1)
    scaled[~valid] = 0
    return (scaled * 255).astype(np.uint8)


def _renderable_raster(path: Path) -> tuple[str, list[list[float]], list[float]]:
    if rasterio is None or Resampling is None or transform_bounds is None:
        raise RuntimeError("rasterio is not installed in the Streamlit container")

    with rasterio.open(path) as src:
        max_side = 1024
        scale = min(max_side / max(src.width, src.height), 1.0)
        out_width = max(1, int(src.width * scale))
        out_height = max(1, int(src.height * scale))
        indexes = [1, 2, 3] if src.count >= 3 else [1]
        data = src.read(indexes, out_shape=(len(indexes), out_height, out_width), resampling=Resampling.bilinear)
        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)

        if src.crs and src.crs.to_string() != "EPSG:4326":
            west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        else:
            west, south, east, north = src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top

    if data.shape[0] >= 3:
        rgb = np.dstack([_array_to_uint8(data[0]), _array_to_uint8(data[1]), _array_to_uint8(data[2])])
        alpha = np.where(np.isfinite(data[0]) | np.isfinite(data[1]) | np.isfinite(data[2]), 255, 0).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
    else:
        gray = _array_to_uint8(data[0])
        alpha = np.where(np.isfinite(data[0]), 220, 0).astype(np.uint8)
        rgba = np.dstack([gray, gray, gray, alpha])

    image = Image.fromarray(rgba, mode="RGBA")
    tmp_dir = Path(tempfile.gettempdir()) / "geollm_streamlit_tiles"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    png_path = tmp_dir / f"{path.stem}.png"
    image.save(png_path)
    bounds = [[float(south), float(west)], [float(north), float(east)]]
    center = [float((south + north) / 2), float((west + east) / 2)]
    return str(png_path), bounds, center


def _png_data_url(path: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _render_map(artifact: dict[str, Any]) -> None:
    uri = artifact.get("uri")
    if not uri:
        st.info("Selected artifact has no URI.")
        return

    path = Path(uri)
    if not path.exists():
        st.warning(f"Artifact path is not visible from the Streamlit container: {uri}")
        st.caption("Mount the same gee_out volume into streamlit-ui at /gee_out.")
        return

    try:
        png_path, bounds, center = _renderable_raster(path)
    except Exception as exc:
        st.warning(f"Could not render this artifact as a GeoTIFF: {exc}")
        st.caption("Mock mode creates placeholder .mock.tif files. Enable real GEE execution to view real rasters.")
        return

    m = folium.Map(location=center, zoom_start=11, control_scale=True)
    folium.raster_layers.ImageOverlay(
        image=_png_data_url(png_path),
        bounds=bounds,
        opacity=0.78,
        name=_artifact_label(artifact),
        interactive=True,
        cross_origin=False,
    ).add_to(m)
    folium.Rectangle(bounds=bounds, tooltip="Raster bounds", fill=False).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, width=None, height=620)


st.set_page_config(page_title="GeoLLM Streamlit", page_icon="🛰️", layout="wide")
_init_state()

st.title("🛰️ GeoLLM Chat + Map Viewer")
st.caption("Streamlit client for the Dockerized LLM geoprocessing API.")

with st.sidebar:
    st.header("Session")
    st.text_input("Thread ID", value=st.session_state["thread_id"], disabled=True)
    if st.button("New session", use_container_width=True):
        for key in ("thread_id", "messages", "runs", "plans", "artifacts", "pending_run_id"):
            st.session_state.pop(key, None)
        st.rerun()

    st.divider()
    show_json = st.toggle("Show JSON instructions", value=False)
    st.caption(f"API: `{_api_config().base_url}`")
    if st.session_state.get("pending_run_id"):
        st.info("The next message will resume the pending run.")

left, right = st.columns([0.9, 1.1], gap="large")

with left:
    st.subheader("Chat")
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask for NDVI, RGB, bands, composites, or imagery availability...")
    if prompt:
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Running geoprocessing agent..."):
                try:
                    response = _run_message(prompt)
                    _record_response(response)
                    text = _assistant_text(response)
                except Exception as exc:
                    text = f"Request failed:\n```json\n{exc}\n```"
                st.markdown(text)
                st.session_state["messages"].append({"role": "assistant", "content": text})

with right:
    st.subheader("Map Viewer")
    geotiffs = [a for a in st.session_state["artifacts"] if str(a.get("kind", "")).lower() == "geotiff"]
    if not geotiffs:
        st.info("No GeoTIFF artifacts in this session yet.")
    else:
        labels = [_artifact_label(a) for a in geotiffs]
        selected_label = st.selectbox("GeoTIFF artifact", labels)
        artifact = geotiffs[labels.index(selected_label)]
        st.code(artifact.get("uri", ""), language="text")
        _render_map(artifact)

    if show_json:
        st.divider()
        st.subheader("JSON instructions for current session")
        if not st.session_state["plans"]:
            st.info("No generated plans yet.")
        for item in reversed(st.session_state["plans"]):
            with st.expander(f"Run {item.get('run_id')}", expanded=True):
                st.json(item["plan"])

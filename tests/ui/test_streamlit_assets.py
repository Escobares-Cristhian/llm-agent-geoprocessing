from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_ui_assets_are_present() -> None:
    assert (ROOT / "Dockerfile.ui").exists()
    app = (ROOT / "streamlit_ui" / "app.py").read_text(encoding="utf-8")
    assert "st.chat_message" in app
    assert "st_folium" in app
    assert "Show JSON instructions" in app
    assert "result.get(\"plan\")" in app


def test_compose_exposes_streamlit_ui_profile() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "streamlit-ui:" in compose
    assert 'profiles: ["ui"]' in compose
    assert "8501:8501" in compose
    assert "gee_out:/gee_out:ro" in compose


def test_ui_optional_dependencies_declared() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ui = [" in pyproject
    assert "streamlit" in pyproject
    assert "streamlit-folium" in pyproject
    assert "rasterio" in pyproject

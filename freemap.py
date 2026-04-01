"""
Australian Aerial Imagery Viewer — Streamlit App
-------------------------------------------------
Install dependencies:
    pip install streamlit folium streamlit-folium

Run:
    streamlit run aerial_imagery_app.py
"""

import folium
import streamlit as st
from streamlit_folium import st_folium

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AU Aerial Imagery Viewer",
    page_icon="🛰️",
    layout="wide",
)

st.title("🛰️ Australian Aerial Imagery Viewer")
st.caption("Free public imagery — no API key required")

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    layer_choice = st.radio(
        "Imagery source",
        options=[
            "ESRI World Imagery (National)",
            "NSW SIX Maps (High-res NSW)",
            "DEA Landsat (Rural/Regional)",
        ],
        index=0,
    )

    show_osm_overlay = st.toggle("Street label overlay (OSM)", value=False)

    st.divider()

    st.subheader("📍 Location")
    preset = st.selectbox(
        "Jump to...",
        options=[
            "Custom",
            "Sydney CBD",
            "Melbourne CBD",
            "Brisbane CBD",
            "Perth CBD",
            "Adelaide CBD",
            "Canberra",
            "Hobart",
            "Darwin",
            "Uluru",
            "Great Barrier Reef (Cairns)",
        ],
    )

    PRESETS = {
        "Sydney CBD":                  (-33.8688, 151.2093, 15),
        "Melbourne CBD":               (-37.8136, 144.9631, 15),
        "Brisbane CBD":                (-27.4705, 153.0260, 15),
        "Perth CBD":                   (-31.9505, 115.8605, 15),
        "Adelaide CBD":                (-34.9285, 138.6007, 15),
        "Canberra":                    (-35.2809, 149.1300, 14),
        "Hobart":                      (-42.8821, 147.3272, 14),
        "Darwin":                      (-12.4634, 130.8456, 14),
        "Uluru":                       (-25.3444, 131.0369, 13),
        "Great Barrier Reef (Cairns)": (-16.9186, 145.7781, 12),
    }

    if preset != "Custom":
        default_lat, default_lon, default_zoom = PRESETS[preset]
    else:
        default_lat, default_lon, default_zoom = -33.8688, 151.2093, 15

    lat  = st.number_input("Latitude",  value=default_lat,  format="%.4f", step=0.01)
    lon  = st.number_input("Longitude", value=default_lon,  format="%.4f", step=0.01)
    zoom = st.slider("Zoom level", min_value=5, max_value=20, value=default_zoom)

    st.divider()
    st.markdown(
        """
        **Sources**
        - [NSW SIX Maps](https://www.spatial.nsw.gov.au)
        - [Digital Earth Australia](https://www.dea.ga.gov.au)
        - [ESRI World Imagery](https://www.esri.com)
        """
    )

# ── Build map ─────────────────────────────────────────────────────────────────
m = folium.Map(
    location=[lat, lon],
    zoom_start=zoom,
    tiles=None,           # No default tiles — we add our own
    control_scale=True,
)

LAYERS = {
    "ESRI World Imagery (National)": {
        "tiles": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":  "© Esri, Maxar, Earthstar Geographics",
        "name":  "ESRI World Imagery",
        "max_zoom": 19,
    },
    "NSW SIX Maps (High-res NSW)": {
        "tiles": "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":  "© NSW Spatial Services (SIX Maps)",
        "name":  "NSW SIX Maps",
        "max_zoom": 19,
    },
    "DEA Landsat (Rural/Regional)": {
        "tiles": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":  "© Digital Earth Australia / Geoscience Australia",
        "name":  "DEA / ESRI Imagery",
        "max_zoom": 13,
    },
}

cfg = LAYERS[layer_choice]
folium.TileLayer(
    tiles=cfg["tiles"],
    attr=cfg["attr"],
    name=cfg["name"],
    max_zoom=cfg["max_zoom"],
).add_to(m)

if show_osm_overlay:
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="© OpenStreetMap contributors",
        name="OSM Street Labels",
        opacity=0.5,
    ).add_to(m)

folium.LayerControl().add_to(m)

# ── Render ────────────────────────────────────────────────────────────────────
map_data = st_folium(m, use_container_width=True, height=650)

# ── Show clicked coordinates ──────────────────────────────────────────────────
if map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    st.info(f"📌 Clicked: **{clicked['lat']:.6f}, {clicked['lng']:.6f}**  — paste into the coordinate fields to centre here")

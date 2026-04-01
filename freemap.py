"""
Australian Aerial Imagery Viewer — Streamlit App
-------------------------------------------------
Install dependencies:
    pip install streamlit folium streamlit-folium requests

Run:
    streamlit run aerial_imagery_app.py
"""

import requests
import folium
import streamlit as st
from streamlit_folium import st_folium
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AU Aerial Imagery Viewer",
    page_icon="🛰️",
    layout="wide",
)

st.title("🛰️ Australian Aerial Imagery Viewer")
st.caption("Free public imagery — no API key required")

# ── Session state ─────────────────────────────────────────────────────────────
# map_center / map_zoom: the authoritative position, updated only by explicit
#   user actions (preset jump, Go button). Never overwritten by reruns.
# map_key: incremented to force a clean remount when layers change.
if "map_key"    not in st.session_state:
    st.session_state.map_key    = 0
if "map_center" not in st.session_state:
    st.session_state.map_center = [-33.8688, 151.2093]
if "map_zoom"   not in st.session_state:
    st.session_state.map_zoom   = 15

def bump_map_key():
    """Increment map key so st_folium remounts with the new layer config."""
    st.session_state.map_key += 1

# ── Constants ─────────────────────────────────────────────────────────────────
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

BASEMAP_LAYERS = {
    "OpenStreetMap": {
        "tiles": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attr":  "© OpenStreetMap contributors",
        "name":  "OpenStreetMap",
    },
    "ESRI Topo": {
        "tiles": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "attr":  "© Esri, HERE, Garmin, FAO, USGS, EPA, NPS",
        "name":  "ESRI Topo",
    },
}

IMAGERY_LAYERS = {
    "ESRI World Imagery (National)": {
        "tiles":    "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":     "© Esri, Maxar, Earthstar Geographics",
        "name":     "ESRI World Imagery",
        "max_zoom": 19,
    },
    "NSW SIX Maps (High-res NSW)": {
        "tiles":    "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":     "© NSW Spatial Services (SIX Maps)",
        "name":     "NSW SIX Maps",
        "max_zoom": 19,
    },
    "DEA Landsat (Rural/Regional)": {
        "tiles":    "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr":     "© Digital Earth Australia / Geoscience Australia",
        "name":     "DEA / ESRI Imagery",
        "max_zoom": 13,
    },
}

STATIC_METADATA = {
    "ESRI World Imagery (National)": {
        "note": "Live metadata queried from ESRI's citation service for the current map centre.",
        "source": "Esri, Maxar, Earthstar Geographics",
        "resolution": "Varies by location",
        "update_cycle": "Irregular — updated as new imagery becomes available",
        "live_query": True,
    },
    "NSW SIX Maps (High-res NSW)": {
        "note": "Imagery varies by area. Urban areas typically captured within 1–3 years. Rural areas may be older.",
        "source": "NSW Spatial Services",
        "resolution": "~12.5 cm (urban) to 50 cm (rural)",
        "update_cycle": "Rolling — urban areas updated most frequently",
        "live_query": False,
    },
    "DEA Landsat (Rural/Regional)": {
        "note": "Annual geomedian composite — a statistical summary of a full calendar year, not a single capture date.",
        "source": "Geoscience Australia / USGS Landsat",
        "resolution": "~25 m",
        "update_cycle": "Annual",
        "live_query": False,
    },
}

# ── ESRI live metadata query ──────────────────────────────────────────────────
def query_esri_metadata(lat: float, lon: float) -> dict | None:
    url = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/4/query"
    params = {
        "geometry":     f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR":         "4326",
        "spatialRel":   "esriSpatialRelIntersects",
        "outFields":    "SRC_DATE2,NICE_DESC,NICE_NAME,SRC_RES,ACCURACY",
        "returnGeometry": "false",
        "f":            "json",
    }
    try:
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None
        attrs = features[0]["attributes"]
        raw_date = attrs.get("SRC_DATE2")
        capture_date = (
            datetime.utcfromtimestamp(raw_date / 1000).strftime("%B %Y")
            if raw_date and raw_date != 99999 else "Not available"
        )
        resolution = attrs.get("SRC_RES")
        res_str = f"{resolution:.2f} m" if resolution and resolution != 99999 else "Not available"
        return {
            "capture_date": capture_date,
            "provider":     attrs.get("NICE_NAME") or attrs.get("NICE_DESC") or "Unknown",
            "resolution":   res_str,
            "accuracy":     attrs.get("ACCURACY"),
        }
    except Exception:
        return None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    # ── Layer controls — each fires bump_map_key on change ────────────────────
    st.subheader("🗺 View mode")
    view_mode = st.radio(
        "View mode",
        options=["Aerial only", "Base map only", "Aerial + street overlay"],
        index=0,
        label_visibility="collapsed",
        on_change=bump_map_key,
    )

    if view_mode in ("Aerial only", "Aerial + street overlay"):
        st.subheader("🛰 Aerial source")
        imagery_choice = st.radio(
            "Aerial source",
            options=list(IMAGERY_LAYERS.keys()),
            index=0,
            label_visibility="collapsed",
            on_change=bump_map_key,
        )
    else:
        imagery_choice = None

    if view_mode in ("Base map only", "Aerial + street overlay"):
        st.subheader("🗺 Base map")
        basemap_choice = st.radio(
            "Base map",
            options=list(BASEMAP_LAYERS.keys()),
            index=0,
            label_visibility="collapsed",
            on_change=bump_map_key,
        )
        if view_mode == "Aerial + street overlay":
            overlay_opacity = st.slider(
                "Street overlay opacity", min_value=0.1, max_value=0.9,
                value=0.4, step=0.05, on_change=bump_map_key,
            )
        else:
            overlay_opacity = 0.4
    else:
        basemap_choice  = None
        overlay_opacity = 0.4

    st.divider()

    # ── Location — explicit Go button; never auto-fires on rerun ─────────────
    st.subheader("📍 Location")
    preset = st.selectbox("Jump to preset", options=["— pick one —"] + list(PRESETS.keys()))

    if preset != "— pick one —":
        plat, plon, pzoom = PRESETS[preset]
    else:
        plat  = st.session_state.map_center[0]
        plon  = st.session_state.map_center[1]
        pzoom = st.session_state.map_zoom

    lat  = st.number_input("Latitude",   value=plat,  format="%.4f", step=0.01)
    lon  = st.number_input("Longitude",  value=plon,  format="%.4f", step=0.01)
    zoom = st.slider("Zoom level", min_value=5, max_value=20, value=pzoom)

    if st.button("Go", use_container_width=True):
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom   = zoom
        st.session_state.map_key   += 1
        st.rerun()

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
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    tiles=None,
    control_scale=True,
)

if view_mode == "Aerial only":
    cfg = IMAGERY_LAYERS[imagery_choice]
    folium.TileLayer(
        tiles=cfg["tiles"], attr=cfg["attr"],
        name=cfg["name"], max_zoom=cfg["max_zoom"],
    ).add_to(m)

elif view_mode == "Base map only":
    bcfg = BASEMAP_LAYERS[basemap_choice]
    folium.TileLayer(
        tiles=bcfg["tiles"], attr=bcfg["attr"], name=bcfg["name"], max_zoom=19,
    ).add_to(m)

elif view_mode == "Aerial + street overlay":
    cfg = IMAGERY_LAYERS[imagery_choice]
    folium.TileLayer(
        tiles=cfg["tiles"], attr=cfg["attr"],
        name=cfg["name"], max_zoom=cfg["max_zoom"], opacity=1.0,
    ).add_to(m)
    bcfg = BASEMAP_LAYERS[basemap_choice]
    folium.TileLayer(
        tiles=bcfg["tiles"], attr=bcfg["attr"],
        name=f"{bcfg['name']} (overlay)",
        max_zoom=19, opacity=overlay_opacity,
    ).add_to(m)

# ── Render ────────────────────────────────────────────────────────────────────
map_col, meta_col = st.columns([3, 1])

with map_col:
    map_data = st_folium(
        m,
        use_container_width=True,
        height=650,
        key=f"map_{st.session_state.map_key}",
        returned_objects=["last_clicked"],  # suppress pan/zoom reruns entirely
    )

with meta_col:
    st.subheader("📅 Imagery info")

    if view_mode == "Base map only":
        st.info("No aerial imagery active.")
    else:
        meta = STATIC_METADATA[imagery_choice]
        if meta["live_query"]:
            with st.spinner("Querying ESRI metadata…"):
                live = query_esri_metadata(
                    st.session_state.map_center[0],
                    st.session_state.map_center[1],
                )
            if live:
                st.success("Live metadata")
                st.metric("Capture date", live["capture_date"])
                st.metric("Resolution",   live["resolution"])
                st.markdown(f"**Provider:** {live['provider']}")
                if live.get("accuracy") and live["accuracy"] != 99999:
                    st.markdown(f"**Positional accuracy:** {live['accuracy']:.1f} m")
            else:
                st.warning("Live query unavailable — showing static info")
                st.markdown(f"**Source:** {meta['source']}")
                st.markdown(f"**Resolution:** {meta['resolution']}")
                st.markdown(f"**Update cycle:** {meta['update_cycle']}")
            st.caption(meta["note"])
        else:
            st.info("Date not queryable for this source")
            st.markdown(f"**Source:** {meta['source']}")
            st.markdown(f"**Resolution:** {meta['resolution']}")
            st.markdown(f"**Update cycle:** {meta['update_cycle']}")
            st.caption(meta["note"])

    st.divider()

    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        st.markdown("**📌 Last clicked**")
        st.code(f"{clicked['lat']:.6f}, {clicked['lng']:.6f}")
        st.caption("Copy into the latitude/longitude fields, then press Go")

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

# ── Session state: track layer selections to detect changes ───────────────────
# st_folium preserves the rendered map between reruns unless we force a new key.
# We do that by incrementing a counter whenever a layer-affecting control changes.
if "map_key" not in st.session_state:
    st.session_state.map_key = 0

def bump_map_key():
    """Called via on_change on any layer-affecting widget."""
    st.session_state.map_key += 1

# ── Static date info (fallback for non-ESRI sources) ─────────────────────────
STATIC_METADATA = {
    "NSW SIX Maps (High-res NSW)": {
        "note": "Imagery varies by area. High-res urban areas typically captured within the last 1–3 years. Rural areas may be older.",
        "source": "NSW Spatial Services",
        "resolution": "~12.5 cm (urban) to 50 cm (rural)",
        "update_cycle": "Rolling — urban areas updated most frequently",
        "live_query": False,
    },
    "DEA Landsat (Rural/Regional)": {
        "note": "Annual geomedian composite — represents a statistical summary of a full calendar year, not a single capture date.",
        "source": "Geoscience Australia / USGS Landsat",
        "resolution": "~25 m",
        "update_cycle": "Annual",
        "live_query": False,
    },
    "ESRI World Imagery (National)": {
        "note": "Live metadata queried from ESRI's citation service for the current map centre.",
        "source": "Esri, Maxar, Earthstar Geographics",
        "resolution": "Varies by location",
        "update_cycle": "Irregular — updated as new imagery becomes available",
        "live_query": True,
    },
}


# ── ESRI live metadata query ──────────────────────────────────────────────────
def query_esri_metadata(lat: float, lon: float) -> dict | None:
    """
    Query ESRI's World Imagery citation layer (MapServer/4) for capture
    date, source, and resolution at a given lat/lon.
    Returns a dict of metadata or None on failure.
    """
    url = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/4/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "SRC_DATE2,NICE_DESC,NICE_NAME,SRC_RES,ACCURACY",
        "returnGeometry": "false",
        "f": "json",
    }

    try:
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            return None

        attrs = features[0]["attributes"]

        # SRC_DATE2 is stored as milliseconds since epoch
        raw_date = attrs.get("SRC_DATE2")
        if raw_date and raw_date != 99999:
            capture_date = datetime.utcfromtimestamp(raw_date / 1000).strftime("%B %Y")
        else:
            capture_date = "Not available"

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


# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    # Three mutually exclusive view modes matching the use cases exactly:
    #   1. Aerial only (choose which source)
    #   2. Base map only (no aerial — street or topo)
    #   3. Aerial + street overlay (aerial underneath, OSM semi-transparent on top)
    st.subheader("🗺 View mode")
    view_mode = st.radio(
        "View mode",
        options=[
            "Aerial only",
            "Base map only",
            "Aerial + street overlay",
        ],
        index=0,
        label_visibility="collapsed",
        on_change=bump_map_key,
    )

    # Aerial source — shown for modes 1 and 3
    if view_mode in ("Aerial only", "Aerial + street overlay"):
        st.subheader("🛰 Aerial source")
        imagery_choice = st.radio(
            "Aerial source",
            options=[
                "ESRI World Imagery (National)",
                "NSW SIX Maps (High-res NSW)",
                "DEA Landsat (Rural/Regional)",
            ],
            index=0,
            label_visibility="collapsed",
            on_change=bump_map_key,
        )
    else:
        imagery_choice = None

    # Base map choice — shown for modes 2 and 3
    if view_mode in ("Base map only", "Aerial + street overlay"):
        st.subheader("🗺 Base map")
        basemap_choice = st.radio(
            "Base map",
            options=[
                "OpenStreetMap",
                "ESRI Topo",
            ],
            index=0,
            label_visibility="collapsed",
            on_change=bump_map_key,
        )
        # Overlay opacity only relevant in mode 3
        if view_mode == "Aerial + street overlay":
            overlay_opacity = st.slider(
                "Street overlay opacity", min_value=0.1, max_value=0.9,
                value=0.4, step=0.05,
                on_change=bump_map_key,
            )
        else:
            overlay_opacity = 0.4
    else:
        basemap_choice  = None
        overlay_opacity = 0.4

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
    tiles=None,
    control_scale=True,
)

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

# Use case 1: Aerial only — just the selected imagery, nothing else
if view_mode == "Aerial only":
    cfg = IMAGERY_LAYERS[imagery_choice]
    folium.TileLayer(
        tiles=cfg["tiles"], attr=cfg["attr"],
        name=cfg["name"], max_zoom=cfg["max_zoom"],
    ).add_to(m)

# Use case 2: Base map only — street or topo, no aerial at all
elif view_mode == "Base map only":
    bcfg = BASEMAP_LAYERS[basemap_choice]
    folium.TileLayer(
        tiles=bcfg["tiles"], attr=bcfg["attr"], name=bcfg["name"], max_zoom=19,
    ).add_to(m)

# Use case 3: Aerial + street overlay — aerial at full opacity, street map on top reduced
elif view_mode == "Aerial + street overlay":
    # Aerial goes on first (bottom)
    cfg = IMAGERY_LAYERS[imagery_choice]
    folium.TileLayer(
        tiles=cfg["tiles"], attr=cfg["attr"],
        name=cfg["name"], max_zoom=cfg["max_zoom"], opacity=1.0,
    ).add_to(m)
    # Street/topo goes on top at reduced opacity
    bcfg = BASEMAP_LAYERS[basemap_choice]
    folium.TileLayer(
        tiles=bcfg["tiles"], attr=bcfg["attr"],
        name=f"{bcfg['name']} (overlay)",
        max_zoom=19, opacity=overlay_opacity,
    ).add_to(m)

# ── Layout: map + metadata panel ──────────────────────────────────────────────
map_col, meta_col = st.columns([3, 1])

with map_col:
    map_data = st_folium(m, use_container_width=True, height=650, key=f"map_{st.session_state.map_key}")

with meta_col:
    st.subheader("📅 Imagery info")

    if view_mode == "Base map only":
        st.info("No aerial imagery active — switch to an aerial mode to see capture metadata.")

    else:
        meta = STATIC_METADATA.get(imagery_choice)

        if meta["live_query"]:
            with st.spinner("Querying ESRI metadata…"):
                live = query_esri_metadata(lat, lon)

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

    # Clicked coordinates
    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        st.markdown("**📌 Last clicked**")
        st.code(f"{clicked['lat']:.6f}, {clicked['lng']:.6f}")
        st.caption("Paste into the sidebar coordinate fields to centre here")

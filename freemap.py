"""
Australian Aerial Imagery Viewer — Streamlit App
-------------------------------------------------
Install dependencies:
    pip install streamlit folium streamlit-folium requests pyproj

Run:
    streamlit run aerial_imagery_app.py
"""

import json
import math
import requests
import folium
from folium.elements import MacroElement
from jinja2 import Template
import streamlit as st
from streamlit_folium import st_folium
from datetime import datetime
from pyproj import Geod

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AU Aerial Imagery Viewer",
    page_icon="🛰️",
    layout="wide",
)

st.title("🛰️ Australian Aerial Imagery Viewer")
st.caption("Free public imagery — no API key required")

# ── Session state ─────────────────────────────────────────────────────────────
if "map_key"      not in st.session_state:
    st.session_state.map_key      = 0
if "map_center"   not in st.session_state:
    st.session_state.map_center   = [-33.8688, 151.2093]
if "map_zoom"     not in st.session_state:
    st.session_state.map_zoom     = 15
if "features"     not in st.session_state:
    st.session_state.features     = []   # list of {id, label, type, geojson}
if "line_count"   not in st.session_state:
    st.session_state.line_count   = 0
if "poly_count"   not in st.session_state:
    st.session_state.poly_count   = 0
if "renaming"     not in st.session_state:
    st.session_state.renaming     = None  # id of feature being renamed

def bump_map_key():
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
        "update_cycle": "Irregular",
        "live_query": True,
    },
    "NSW SIX Maps (High-res NSW)": {
        "note": "Urban areas typically captured within 1–3 years. Rural areas may be older.",
        "source": "NSW Spatial Services",
        "resolution": "~12.5 cm (urban) to 50 cm (rural)",
        "update_cycle": "Rolling",
        "live_query": False,
    },
    "DEA Landsat (Rural/Regional)": {
        "note": "Annual geomedian composite — not a single capture date.",
        "source": "Geoscience Australia / USGS Landsat",
        "resolution": "~25 m",
        "update_cycle": "Annual",
        "live_query": False,
    },
}

# ── Geometry helpers ──────────────────────────────────────────────────────────
geod = Geod(ellps="WGS84")

def haversine_length_m(coords: list) -> float:
    """Total length of a polyline in metres. coords = [[lng, lat], ...]"""
    total = 0.0
    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        _, _, dist = geod.inv(lng1, lat1, lng2, lat2)
        total += dist
    return total

def polygon_area_m2(coords: list) -> float:
    """Area of a polygon ring in square metres. coords = [[lng, lat], ...]"""
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    area, _ = geod.polygon_area_perimeter(lngs, lats)
    return abs(area)

def fmt_length(m: float) -> str:
    if m >= 1000:
        return f"{m/1000:.2f} km  ({m:,.0f} m)"
    return f"{m:,.1f} m"

def fmt_area(m2: float) -> str:
    ha = m2 / 10_000
    if ha >= 1:
        return f"{ha:.2f} ha  ({m2:,.0f} m²)"
    return f"{m2:,.0f} m²  ({ha:.4f} ha)"

def measure_feature(geojson: dict) -> tuple[str, str]:
    """Return (type_label, measurement_string) for a GeoJSON geometry."""
    gtype = geojson.get("geometry", {}).get("type", "")
    coords = geojson.get("geometry", {}).get("coordinates", [])
    if gtype == "LineString":
        return "Line", fmt_length(haversine_length_m(coords))
    elif gtype == "Polygon":
        return "Polygon", fmt_area(polygon_area_m2(coords[0]))
    return gtype, "—"

# ── Leaflet.draw plugin injected as a MacroElement ───────────────────────────
class LeafletDraw(MacroElement):
    """Injects Leaflet.draw toolbar (polyline + polygon only)."""
    _template = Template("""
        {% macro script(this, kwargs) %}
        // Load Leaflet.draw from CDN
        (function() {
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css';
            document.head.appendChild(link);

            var script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js';
            script.onload = function() {
                var map = {{ this._parent.get_name() }};

                var drawnItems = new L.FeatureGroup();
                map.addLayer(drawnItems);

                // Re-inject stored features so they survive layer switches
                var stored = {{ this.stored_geojson }};
                stored.forEach(function(f) {
                    var layer = L.geoJSON(f);
                    layer.eachLayer(function(l) { drawnItems.addLayer(l); });
                });

                var drawControl = new L.Control.Draw({
                    edit: { featureGroup: drawnItems, edit: false, remove: false },
                    draw: {
                        polyline:  { shapeOptions: { color: '#e74c3c', weight: 3 } },
                        polygon:   { shapeOptions: { color: '#3498db', weight: 2 },
                                     showArea: false },
                        rectangle: false,
                        circle:    false,
                        marker:    false,
                        circlemarker: false,
                    }
                });
                map.addControl(drawControl);

                map.on(L.Draw.Event.CREATED, function(e) {
                    drawnItems.addLayer(e.layer);
                    // Send GeoJSON of new feature back to Streamlit via st_folium
                    var geojson = e.layer.toGeoJSON();
                    // st_folium captures last_active_drawing on click — we fake
                    // a map click event to flush the drawn feature through
                    map.fire('click', {latlng: e.layer.getBounds
                        ? e.layer.getBounds().getCenter()
                        : e.layer.getLatLng()});
                });
            };
            document.head.appendChild(script);
        })();
        {% endmacro %}
    """)

    def __init__(self, stored_features: list):
        super().__init__()
        self._name = "LeafletDraw"
        # Pass stored GeoJSON geometries to JS for re-injection
        self.stored_geojson = json.dumps(
            [f["geojson"] for f in stored_features]
        )

# ── ESRI metadata query ───────────────────────────────────────────────────────
def query_esri_metadata(lat: float, lon: float) -> dict | None:
    url = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/4/query"
    params = {
        "geometry":       f"{lon},{lat}",
        "geometryType":   "esriGeometryPoint",
        "inSR":           "4326",
        "spatialRel":     "esriSpatialRelIntersects",
        "outFields":      "SRC_DATE2,NICE_DESC,NICE_NAME,SRC_RES,ACCURACY",
        "returnGeometry": "false",
        "f":              "json",
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

    st.subheader("📍 Location")
    preset = st.selectbox("Jump to preset", options=["— pick one —"] + list(PRESETS.keys()))
    if preset != "— pick one —":
        plat, plon, pzoom = PRESETS[preset]
    else:
        plat  = st.session_state.map_center[0]
        plon  = st.session_state.map_center[1]
        pzoom = st.session_state.map_zoom

    lat  = st.number_input("Latitude",  value=plat, format="%.4f", step=0.01)
    lon  = st.number_input("Longitude", value=plon, format="%.4f", step=0.01)
    zoom = st.slider("Zoom level", min_value=5, max_value=20, value=pzoom)

    if st.button("Go", use_container_width=True):
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom   = zoom
        st.session_state.map_key   += 1
        st.rerun()

    st.divider()

    # ── GeoJSON save / load ───────────────────────────────────────────────────
    st.subheader("💾 Features")

    if st.session_state.features:
        fc = {
            "type": "FeatureCollection",
            "features": [
                {**f["geojson"], "properties": {"label": f["label"], "type": f["type"]}}
                for f in st.session_state.features
            ]
        }
        st.download_button(
            "⬇ Export GeoJSON",
            data=json.dumps(fc, indent=2),
            file_name="measurements.geojson",
            mime="application/json",
            use_container_width=True,
        )

    uploaded = st.file_uploader("⬆ Load GeoJSON", type=["geojson", "json"])
    if uploaded:
        try:
            fc_in = json.load(uploaded)
            new_features = []
            for f in fc_in.get("features", []):
                gtype = f.get("geometry", {}).get("type", "")
                ftype = "Line" if gtype == "LineString" else "Polygon" if gtype == "Polygon" else None
                if ftype is None:
                    continue
                label = f.get("properties", {}).get("label") or ftype
                new_features.append({
                    "id":     id(f),
                    "label":  label,
                    "type":   ftype,
                    "geojson": f,
                })
            if new_features:
                st.session_state.features   = new_features
                st.session_state.map_key   += 1
                st.rerun()
        except Exception as e:
            st.error(f"Could not load file: {e}")

    if st.session_state.features:
        if st.button("🗑 Clear all features", use_container_width=True):
            st.session_state.features   = []
            st.session_state.line_count = 0
            st.session_state.poly_count = 0
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

# Inject Leaflet.draw with stored features for re-display after layer switch
LeafletDraw(st.session_state.features).add_to(m)

# ── Render ────────────────────────────────────────────────────────────────────
map_col, right_col = st.columns([3, 1])

with map_col:
    map_data = st_folium(
        m,
        use_container_width=True,
        height=650,
        key=f"map_{st.session_state.map_key}",
        returned_objects=["last_active_drawing", "last_clicked"],
    )

    # Pick up newly drawn features
    drawing = map_data.get("last_active_drawing") if map_data else None
    if drawing and drawing.get("geometry"):
        # Deduplicate — don't re-add if we already have this exact geometry
        existing_geoms = [f["geojson"].get("geometry") for f in st.session_state.features]
        if drawing["geometry"] not in existing_geoms:
            gtype = drawing["geometry"].get("type", "")
            if gtype == "LineString":
                st.session_state.line_count += 1
                label = f"Line {st.session_state.line_count}"
                ftype = "Line"
            elif gtype == "Polygon":
                st.session_state.poly_count += 1
                label = f"Polygon {st.session_state.poly_count}"
                ftype = "Polygon"
            else:
                label, ftype = gtype, gtype

            st.session_state.features.append({
                "id":      len(st.session_state.features),
                "label":   label,
                "type":    ftype,
                "geojson": drawing,
            })
            st.rerun()

with right_col:
    # ── Tab layout: Measurements | Imagery info ───────────────────────────────
    tab_measure, tab_imagery = st.tabs(["📐 Measurements", "📅 Imagery"])

    with tab_measure:
        features = st.session_state.features
        if not features:
            st.caption("Draw a line or polygon on the map to measure it.")
        else:
            total_length_m  = 0.0
            total_area_m2   = 0.0

            for i, feat in enumerate(features):
                ftype, measurement = measure_feature(feat["geojson"])

                with st.container():
                    # Label / rename flow
                    if st.session_state.renaming == feat["id"]:
                        new_label = st.text_input(
                            "Rename", value=feat["label"],
                            key=f"rename_{feat['id']}",
                            label_visibility="collapsed",
                        )
                        c1, c2 = st.columns(2)
                        if c1.button("✓", key=f"confirm_{feat['id']}", use_container_width=True):
                            st.session_state.features[i]["label"] = new_label
                            st.session_state.renaming = None
                            st.rerun()
                        if c2.button("✕", key=f"cancel_{feat['id']}", use_container_width=True):
                            st.session_state.renaming = None
                            st.rerun()
                    else:
                        col_label, col_edit, col_del = st.columns([5, 1, 1])
                        col_label.markdown(f"**{feat['label']}**")
                        if col_edit.button("✏", key=f"edit_{feat['id']}", help="Rename"):
                            st.session_state.renaming = feat["id"]
                            st.rerun()
                        if col_del.button("🗑", key=f"del_{feat['id']}", help="Delete"):
                            st.session_state.features.pop(i)
                            st.session_state.map_key += 1
                            st.rerun()

                    icon = "📏" if ftype == "Line" else "⬡"
                    st.caption(f"{icon} {measurement}")
                    st.divider()

                    # Accumulate totals
                    gtype = feat["geojson"].get("geometry", {}).get("type", "")
                    coords = feat["geojson"].get("geometry", {}).get("coordinates", [])
                    if gtype == "LineString":
                        total_length_m += haversine_length_m(coords)
                    elif gtype == "Polygon":
                        total_area_m2  += polygon_area_m2(coords[0])

            # Totals
            if total_length_m > 0:
                st.markdown(f"**Total line length:** {fmt_length(total_length_m)}")
            if total_area_m2 > 0:
                st.markdown(f"**Total polygon area:** {fmt_area(total_area_m2)}")

    with tab_imagery:
        if view_mode == "Base map only":
            st.info("No aerial imagery active.")
        else:
            meta = STATIC_METADATA[imagery_choice]
            if meta["live_query"]:
                with st.spinner("Querying…"):
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
                    st.warning("Live query unavailable")
                    st.markdown(f"**Source:** {meta['source']}")
                    st.markdown(f"**Resolution:** {meta['resolution']}")
                st.caption(meta["note"])
            else:
                st.info("Date not queryable for this source")
                st.markdown(f"**Source:** {meta['source']}")
                st.markdown(f"**Resolution:** {meta['resolution']}")
                st.markdown(f"**Update cycle:** {meta['update_cycle']}")
                st.caption(meta["note"])

        if map_data and map_data.get("last_clicked"):
            st.divider()
            clicked = map_data["last_clicked"]
            st.markdown("**📌 Last clicked**")
            st.code(f"{clicked['lat']:.6f}, {clicked['lng']:.6f}")
            st.caption("Copy into sidebar fields, then press Go")

import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
import csv
import io
import time
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components

st.set_page_config(page_title="SafeRoute & Floodboard", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางเลี่ยงน้ำท่วม กทม.")
st.write("ระบบตรวจสอบเส้นทางซิงค์ข้อมูลจาก Google Sheets และหน้าแดชบอร์ดสถานการณ์สด")

# ---------------------------------------------------------------------------
# ตั้งค่า Google Sheet
# ---------------------------------------------------------------------------
SHEET_ID = "1emYaPZT-L-zWOq5Oezr_ZPURy-LTlnzLAPA7HaUjOug"
SHEET_GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

FALLBACK_REPORTS = [
    {"name": "ถนนงามวงศ์วาน (เขตจตุจักร)", "lat": 13.8582, "lon": 100.5447, "status": "ท่วมขัง ~31 cm", "level": "danger"},
    {"name": "ถนนนวมินทร์ (เขตบางกะปิ)", "lat": 13.7850, "lon": 100.6500, "status": "ท่วมขัง ~80 cm", "level": "danger"},
    {"name": "ถนนรามคำแหง (เขตสวนหลวง)", "lat": 13.7580, "lon": 100.6200, "status": "ท่วมขัง ~100 cm", "level": "danger"},
]

FLOOD_PROXIMITY_METERS = 800
COARSE_FILTER_DEGREES = 0.08
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

geolocator = Nominatim(user_agent="saferoute_exact_tabs_v9")


# ---------------------------------------------------------------------------
# โหลดข้อมูลจาก Google Sheet
# ---------------------------------------------------------------------------
@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def geocode_road(name, district):
    province = "นนทบุรี" if "อำเภอ" in district or "นนทบุรี" in district else "กรุงเทพมหานคร"
    for q in [f"{name} {district} {province} ประเทศไทย", f"{name} {province} ประเทศไทย"]:
        try:
            loc = geolocator.geocode(q, timeout=3)
            time.sleep(0.2)
            if loc:
                return (loc.latitude, loc.longitude)
        except Exception:
            continue
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def load_flood_reports_sheet():
    try:
        resp = requests.get(SHEET_CSV_URL, timeout=8)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        
        reports = []
        reader = csv.reader(io.StringIO(resp.text))
        
        for row in reader:
            if not row or not any(row):
                continue
            col0 = row[0].strip()
            if "เขตที่ได้รับผลกระทบ" in col0 or "เขต" == col0:
                break
            if col0 == "ถนน" or "name" in col0.lower() or col0 == "":
                continue
                
            name = col0
            district = row[1].strip() if len(row) > 1 else ""
            distance = row[2].strip() if len(row) > 2 else ""
            depth = row[3].strip() if len(row) > 3 else ""
            level = row[4].strip().lower() if len(row) > 4 else "danger"
            
            if not depth or depth == "nan":
                continue
            if level not in ("danger", "warning"):
                level = "danger"
                
            lat, lon = None, None
            try:
                if len(row) > 6 and row[5].strip() and row[6].strip():
                    lat = float(row[5])
                    lon = float(row[6])
            except ValueError:
                pass
                
            if lat is None or lon is None:
                coords = geocode_road(name, district)
                if coords is None:
                    continue
                lat, lon = coords
                
            status = f"ท่วมขัง {depth}"
            if distance and distance != "nan":
                status += f" (ถนนมีน้ำ {distance})"
                
            reports.append({
                "name": f"{name} ({district})" if district else name,
                "lat": lat,
                "lon": lon,
                "status": status,
                "level": level,
            })
            
        if not reports:
            return FALLBACK_REPORTS, {"source": "fallback", "total": len(FALLBACK_REPORTS)}
        return reports, {"source": "sheet", "total": len(reports)}
    except Exception:
        return FALLBACK_REPORTS, {"source": "fallback", "total": len(FALLBACK_REPORTS)}


def get_lat_lon_free(place_name):
    query = place_name.strip()
    if not query:
        return None
    search_queries = [
        query + ", กรุงเทพมหานคร, ประเทศไทย",
        query + ", นนทบุรี, ประเทศไทย",
        query.replace("MRT", "สถานีรถไฟฟ้า MRT") + ", กรุงเทพมหานคร, ประเทศไทย",
        query.replace("BTS", "สถานีรถไฟฟ้า BTS") + ", กรุงเทพมหานคร, ประเทศไทย",
        query + ", ประเทศไทย",
        query
    ]
    for q in search_queries:
        try:
            loc = geolocator.geocode(q, timeout=3)
            if loc:
                return {"lat": loc.latitude, "lon": loc.longitude}
        except Exception:
            continue
    return {"lat": 13.7563, "lon": 100.5018}


def haversine_meters(lat1, lon1, lat2, lon2):
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def route_passes_flood_zone(route_coords, reports, proximity_m=FLOOD_PROXIMITY_METERS):
    matched = []
    danger_hit = False
    for report in reports:
        r_lat, r_lon = report["lat"], report["lon"]
        for c_lat, c_lon in route_coords:
            if abs(c_lat - r_lat) > COARSE_FILTER_DEGREES or abs(c_lon - r_lon) > COARSE_FILTER_DEGREES:
                continue
            if haversine_meters(c_lat, c_lon, r_lat, r_lon) <= proximity_m:
                matched.append(report)
                if report["level"] == "danger":
                    danger_hit = True
                break
    return danger_hit, matched


def fetch_route(loc_orig, loc_dest):
    straight_line = [[loc_orig["lat"], loc_orig["lon"]], [loc_dest["lat"], loc_dest["lon"]]]
    url = OSRM_URL.format(lon1=loc_orig["lon"], lat1=loc_orig["lat"],
                          lon2=loc_dest["lon"], lat2=loc_dest["lat"])
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return straight_line, "⚠️ ใช้เส้นทางโดยประมาณ (เส้นตรง)"

    if data.get("code") != "Ok" or not data.get("routes"):
        return straight_line, "🚫 ไม่พบเส้นทางถนนจริง แสดงเส้นทางโดยประมาณแทน"

    coords = data["routes"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coords], None


# ---------------------------------------------------------------------------
# UI หลัก (มี 3 แท็บ: เช็กเส้นทาง, Floodboard, BKK Dashboard ตามที่ต้องการ)
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ เช็กเส้นทางปลอดภัย", "📊 Floodboard", "🏛️ BKK Dashboard"])

with tab1:
    st.subheader("วางแผนการเดินทางเลี่ยงน้ำท่วม")

    if "cached_reports" not in st.session_state:
        with st.spinner("กำลังโหลดข้อมูลจุดน้ำท่วมจาก Google Sheet..."):
            st.session_state.cached_reports, st.session_state.cached_info = load_flood_reports_sheet()

    flood_reports = st.session_state.cached_reports
    info = st.session_state.cached_info

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        if info["source"] == "sheet":
            st.caption(f"📄 ข้อมูลจาก Google Sheet: ซิงค์สำเร็จ {info['total']} จุด")
        else:
            st.warning("⚠️ ใช้ข้อมูลสำรองในระบบ")
    with col_btn:
        if st.button("🔄 โหลดใหม่"):
            load_flood_reports_sheet.clear()
            if "cached_reports" in st.session_state:
                del st.session_state.cached_reports
            st.rerun()

    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น แม็คโครสามเสน")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น ถนนงามวงศ์วาน")

    if st.button("🚀 ค้นหาเส้นทาง"):
        if not origin_input or not destination_input:
            st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
        else:
            with st.spinner("กำลังคำนวณเส้นทางและตรวจสอบจุดน้ำท่วมขัง..."):
                loc_orig = get_lat_lon_free(origin_input)
                loc_dest = get_lat_lon_free(destination_input)

            if loc_orig is None or loc_dest is None:
                st.error("❌ ไม่สามารถระบุพิกัดได้ ลองระบุชื่อเขตหรือจังหวัดเพิ่มเติมครับ")
            else:
                route_coords, route_note = fetch_route(loc_orig, loc_dest)

                center_lat = sum(c[0] for c in route_coords) / len(route_coords)
                center_lon = sum(c[1] for c in route_coords) / len(route_coords)
                m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

                is_flooded, matched = route_passes_flood_zone(route_coords, flood_reports)

                folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                                weight=6, opacity=0.8).add_to(m)
                folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip="จุดเริ่มต้น",
                              icon=folium.Icon(color="green", icon="play")).add_to(m)
                folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip="ปลายทาง",
                              icon=folium.Icon(color="red", icon="stop")).add_to(m)

                shown = matched if matched else flood_reports[:60]
                for report in shown:
                    folium.Marker(
                        [report["lat"], report["lon"]],
                        popup=f"<b>{html.escape(report['name'])}</b><br>{html.escape(report['status'])}",
                        tooltip="จุดน้ำท่วมขัง",
                        icon=folium.Icon(color="red" if report["level"] == "danger" else "orange",
                                         icon="warning-sign"),
                    ).add_to(m)

                st_folium(m, width=700, height=450, returned_objects=[], key="route_map")

                if route_note:
                    st.info(route_note)

                if is_flooded:
                    names = ", ".join(html.escape(r["name"]) for r in matched[:8])
                    more = f" และอีก {len(matched) - 8} จุด" if len(matched) > 8 else ""
                    st.error(f"🚨 เส้นทางนี้ผ่านใกล้พื้นที่น้ำท่วมขัง ({names}{more}) แนะนำเปลี่ยนเส้นทาง!")
                elif matched:
                    st.warning("⚠️ เส้นทางผ่านใกล้จุดที่มีน้ำขัง ขับขี่ด้วยความระมัดระวัง")
                else:
                    st.success("✅ ไม่พบจุดน้ำท่วมใกล้เส้นทางนี้ (ควรเช็กข่าวก่อนออกเดินทางด้วยครับ)")

with tab2:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=700, scrolling=True)

with tab3:
    st.subheader("🏛️ รายงานสถานการณ์น้ำท่วม กทม. (BKK Flood Alert)")
    st.markdown("ข้อมูลรายงานสถานการณ์น้ำท่วมและระดับน้ำบนถนนจากกรุงเทพมหานครแบบเรียลไทม์")
    st.markdown("[🔗 เปิดหน้าเว็บรายงานน้ำท่วม กทม. แบบเต็มจอในแท็บใหม่](https://now.bangkok.go.th/flood-alert.html)", unsafe_allow_html=True)
    components.iframe("https://now.bangkok.go.th/flood-alert.html", height=700, scrolling=True)

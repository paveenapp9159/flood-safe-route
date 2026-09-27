import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
from geopy.geocoders import Nominatim

st.set_page_config(page_title="SafeRoute Interactive Flood Map", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางน้ำท่วม & รายงานสด")
st.write("ตรวจสอบเส้นทางและช่วยกันอัปเดตสถานการณ์น้ำท่วมแบบเรียลไทม์จากหน้างานจริง")

# ---------------------------------------------------------------------------
# ระบบเก็บข้อมูลจุดน้ำท่วมใน Session (อัปเดตสดทันทีเมื่อมีคนแจ้งหรือกดยืนยันน้ำแห้ง)
# ---------------------------------------------------------------------------
if "flood_reports" not in st.session_state:
    st.session_state.flood_reports = [
        {"id": 1, "name": "ถนนแจ้งวัฒนะ (ปากเกร็ด)", "lat": 13.9065, "lon": 100.5027,
         "status": "ท่วมสูง 15-20 ซม. รถเล็กควรเลี่ยง", "level": "danger"},
        {"id": 2, "name": "แยกพงษ์เพชร (งามวงศ์วาน)", "lat": 13.8582, "lon": 100.5447,
         "status": "มีน้ำขังรอการระบาย", "level": "warning"},
        {"id": 3, "name": "ถนนรัตนาธิเบศร์", "lat": 13.8590, "lon": 100.5115,
         "status": "ท่วมสูง 15-20 ซม.", "level": "danger"},
    ]

FLOOD_PROXIMITY_METERS = 250
COARSE_FILTER_DEGREES = 0.03
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

geolocator = Nominatim(user_agent="saferoute_crowdsource_app")

def get_lat_lon_free(place_name):
    if not place_name.strip():
        return None
    try:
        query = place_name.strip()
        if "กรุงเทพ" not in query and "นนทบุรี" not in query and "Bangkok" not in query and "Nonthaburi" not in query:
            search_queries = [
                query + ", นนทบุรี, ประเทศไทย",
                query + ", กรุงเทพมหานคร, ประเทศไทย",
                query + ", ประเทศไทย"
            ]
        else:
            search_queries = [query + ", ประเทศไทย"]

        for q in search_queries:
            loc = geolocator.geocode(q, timeout=5)
            if loc:
                return {"lat": loc.latitude, "lon": loc.longitude}
    except Exception:
        pass
    return None

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
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return straight_line, "⚠️ ใช้เส้นทางโดยประมาณ (เส้นตรง)"

    if data.get("code") != "Ok" or not data.get("routes"):
        return straight_line, "🚫 ไม่พบเส้นทางถนนจริง แสดงเส้นทางโดยประมาณแทน"

    coords = data["routes"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coords], None

# ---------------------------------------------------------------------------
# แบ่งหน้าการใช้งาน (Tabs)
# ---------------------------------------------------------------------------
tab1, tab2 = st.tabs(["🗺️ เช็กเส้นทาง & แผนที่", "📢 รายงานน้ำท่วม / กดยืนยันน้ำแห้ง"])

with tab1:
    st.subheader("วางแผนการเดินทางปลอดภัย")
    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น MRT บางรักใหญ่")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น แยกแคราย")

    if st.button("🚀 ค้นหาเส้นทาง"):
        if not origin_input or not destination_input:
            st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
        else:
            with st.spinner("กำลังคำนวณเส้นทาง..."):
                loc_orig = get_lat_lon_free(origin_input)
                loc_dest = get_lat_lon_free(destination_input)

                if not loc_orig or not loc_dest:
                    st.error("❌ ไม่พบสถานที่ที่คุณค้นหา ลองระบุชื่อถนนหรือเขตเพิ่มเติมครับ")
                else:
                    route_coords, route_note = fetch_route(loc_orig, loc_dest)
                    
                    all_lats = [c[0] for c in route_coords]
                    all_lons = [c[1] for c in route_coords]
                    center_lat = sum(all_lats) / len(all_lats)
                    center_lon = sum(all_lons) / len(all_lons)

                    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

                    is_flooded, matched = route_passes_flood_zone(route_coords, st.session_state.flood_reports)
                    
                    # วาดเส้นทาง
                    folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                                     weight=6, opacity=0.8).add_to(m)

                    # ปักหมุด ต้นทาง - ปลายทาง
                    folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip=f"จุดเริ่มต้น: {origin_input}",
                                   icon=folium.Icon(color="green", icon="play")).add_to(m)
                    folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip=f"ปลายทาง: {destination_input}",
                                   icon=folium.Icon(color="red", icon="stop")).add_to(m)

                    # ปักหมุดจุดน้ำท่วมทั้งหมดที่มีอยู่ในระบบปัจจุบัน
                    for report in st.session_state.flood_reports:
                        safe_name = html.escape(report["name"])
                        safe_status = html.escape(report["status"])
                        folium.Marker(
                            [report["lat"], report["lon"]],
                            popup=f"<b>{safe_name}</b><br>{safe_status}",
                            tooltip="จุดน้ำท่วมขัง",
                            icon=folium.Icon(color="red" if report["level"] == "danger" else "orange",
                                              icon="warning-sign"),
                        ).add_to(m)

                    st_folium(m, width=700, height=450, returned_objects=[])

                    if route_note:
                        st.info(route_note)

                    if is_flooded:
                        names = ", ".join(html.escape(r["name"]) for r in matched if r["level"] == "danger")
                        st.error(f"🚨 เส้นทางนี้ผ่านใกล้พื้นที่น้ำท่วมสูง ({names}) แนะนำเปลี่ยนเส้นทาง!")
                    elif matched:
                        st.warning("⚠️ เส้นทางผ่านใกล้จุดที่มีน้ำขังเล็กน้อย ขับขี่ด้วยความระมัดระวัง")
                    else:
                        st.success("✅ ไม่พบจุดเสี่ยงอันตรายในเส้นทางนี้ เดินทางได้ปกติครับ")

with tab2:
    st.subheader("📢 รายงานสถานการณ์ หรือแจ้งว่าน้ำแห้งแล้ว")
    st.write("ช่วยกันอัปเดตข้อมูลเพื่อให้เพื่อนร่วมทางได้รับข้อมูลที่ถูกต้องที่สุด")

    # ส่วนที่ 1: แจ้งจุดน้ำท่วมใหม่
    with st.form("report_form"):
        st.markdown("##### 📍 เพิ่มจุดน้ำท่วมใหม่")
        new_loc = st.text_input("ชื่อสถานที่ / ถนน / ซอย", placeholder="เช่น ซอยงามวงศ์วาน 18")
        new_status = st.text_input("รายละเอียดสถานการณ์", placeholder="น้ำท่วมสูง 10 ซม. รถเล็กผ่านได้")
        new_level = st.selectbox("ระดับความรุนแรง", ["น้ำขังเล็กน้อย (Warning)", "ท่วมสูงอันตราย (Danger)"])
        submitted = st.form_submit_button("📤 ส่งรายงานจุดน้ำท่วม")

        if submitted:
            if new_loc:
                coords = get_lat_lon_free(new_loc)
                if coords:
                    new_id = max([r["id"] for r in st.session_state.flood_reports], default=0) + 1
                    level_key = "danger" if "Danger" in new_level else "warning"
                    st.session_state.flood_reports.append({
                        "id": new_id,
                        "name": new_loc,
                        "lat": coords["lat"],
                        "lon": coords["lon"],
                        "status": new_status,
                        "level": level_key
                    })
                    st.success("🎉 ขอบคุณครับ! เพิ่มหมุดเตือนภัยลงในแผนที่เรียบร้อยแล้ว")
                else:
                    st.error("❌ ไม่พบพิกัดของสถานที่นี้ โปรดระบุชื่อถนนหรือเขตให้ชัดเจนขึ้นครับ")
            else:
                st.warning("⚠️ กรุณากรอกชื่อสถานที่")

    st.markdown("---")
    st.markdown("##### ✅ กดยืนยันว่า 'น้ำแห้งแล้ว' (ลบหมุดออกจากแผนที่)")
    if not st.session_state.flood_reports:
        st.info("ขณะนี้ไม่มีหมุดจุดน้ำท่วมในระบบ")
    else:
        for report in st.session_state.flood_reports:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📍 **{report['name']}** — {report['status']}")
            with col2:
                if st.button("น้ำแห้งแล้ว", key=f"del_{report['id']}"):
                    st.session_state.flood_reports = [r for r in st.session_state.flood_reports if r["id"] != report["id"]]
                    st.success(f"ลบหมุด '{report['name']}' ออกจากแผนที่เรียบร้อยครับ!")
                    st.rerun()

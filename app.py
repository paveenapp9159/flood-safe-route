import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components

st.set_page_config(page_title="SafeRoute & Weather", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางเลี่ยงน้ำท่วม & พยากรณ์ฝน")
st.write("ระบบตรวจสอบเส้นทางอัจฉริยะ พร้อมเช็กพยากรณ์ฝนตกเพื่อเตรียมรับมือสถานการณ์ล่วงหน้า")

# ---------------------------------------------------------------------------
# ฐานข้อมูลถนนน้ำท่วมจริง
# ---------------------------------------------------------------------------
real_flood_reports = [
    {"name": "ถนนพัฒนาการ (สวนหลวง)", "lat": 13.7315, "lon": 100.6120, "status": "ท่วมขัง ~50 ซม. (รถเล็กผ่านไม่ได้)", "level": "danger"},
    {"name": "ถนนงามวงศ์วาน (หลักสี่)", "lat": 13.8582, "lon": 100.5447, "status": "ท่วมขัง ~35 ซม.", "level": "danger"},
    {"name": "ถนนพหลโยธิน (จตุจักร)", "lat": 13.8250, "lon": 100.5740, "status": "ท่วมขัง ~30 ซม.", "level": "warning"},
    {"name": "ถนนหัวหมาก (บางกะปิ)", "lat": 13.7550, "lon": 100.6350, "status": "ท่วมขัง ~80 ซม. (อันตราย)", "level": "danger"},
    {"name": "ถนนนวมินทร์ (บางกะปิ)", "lat": 13.7850, "lon": 100.6500, "status": "ท่วมขัง ~38 ซม.", "level": "warning"},
    {"name": "ถนนศรีนครินทร์ (บางกะปิ)", "lat": 13.7450, "lon": 100.6420, "status": "ท่วมขัง ~45 ซม.", "level": "danger"},
    {"name": "ถนนรามคำแหง (บางกะปิ)", "lat": 13.7580, "lon": 100.6200, "status": "ท่วมขัง ~90 ซม. (รถเล็กห้ามผ่าน)", "level": "danger"},
    {"name": "ถนนลาดพร้าว (บางกะปิ)", "lat": 13.7800, "lon": 100.6000, "status": "ท่วมขัง ~30 ซม.", "level": "warning"},
    {"name": "ถนนลาดกระบัง (ลาดกระบัง)", "lat": 13.7250, "lon": 100.7900, "status": "ท่วมขัง ~100 ซม. (วิกฤต)", "level": "danger"},
]

if "flood_reports" not in st.session_state:
    st.session_state.flood_reports = real_flood_reports

FLOOD_PROXIMITY_METERS = 300
COARSE_FILTER_DEGREES = 0.03
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

geolocator = Nominatim(user_agent="saferoute_weather_app")

def get_lat_lon_free(place_name):
    if not place_name.strip():
        return None
    try:
        query = place_name.strip()
        if "กรุงเทพ" not in query and "นนทบุรี" not in query and "Bangkok" not in query and "Nonthaburi" not in query:
            search_queries = [
                query + ", กรุงเทพมหานคร, ประเทศไทย",
                query + ", นนทบุรี, ประเทศไทย",
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
# Tabs การใช้งาน
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ เช็กเส้นทางปลอดภัย", "🌦️ พยากรณ์ฝนตก", "📊 Floodboard", "📢 แจ้งน้ำท่วม"])

with tab1:
    st.subheader("วางแผนการเดินทางเลี่ยงน้ำท่วม")
    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น มหาวิทยาลัยเกษตรศาสตร์")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น ซอยพัฒนาการ 40")

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
                    
                    folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                                     weight=6, opacity=0.8).add_to(m)

                    folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip=f"จุดเริ่มต้น: {origin_input}",
                                   icon=folium.Icon(color="green", icon="play")).add_to(m)
                    folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip=f"ปลายทาง: {destination_input}",
                                   icon=folium.Icon(color="red", icon="stop")).add_to(m)

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
                        st.error(f"🚨 เส้นทางนี้ผ่านใกล้พื้นที่น้ำท่วมขัง ({names}) แนะนำเปลี่ยนเส้นทาง!")
                    elif matched:
                        st.warning("⚠️ เส้นทางผ่านใกล้จุดที่มีน้ำขังรอการระบาย ระมัดระวังด้วยครับ")
                    else:
                        st.success("✅ ไม่พบจุดเสี่ยงน้ำท่วมในเส้นทางนี้")

with tab2:
    st.subheader("🌦️ เช็กพยากรณ์ฝนและสภาพอากาศ (กรุงเทพฯ และปริมณฑล)")
    st.write("ข้อมูลปริมาณฝนคาดการณ์แบบรายชั่วโมง เพื่อประเมินความเสี่ยงน้ำรอการระบาย")
    
    # ดึงข้อมูลสภาพอากาศฟรีจาก Open-Meteo (พิกัดกลางกรุงเทพฯ 13.7563, 100.5018)
    weather_url = "https://api.open-meteo.com/v1/forecast?latitude=13.7563&longitude=100.5018&hourly=precipitation_probability,precipitation,rain&timezone=Asia%2FBangkok"
    try:
        w_res = requests.get(weather_url, timeout=5).json()
        hourly = w_res.get("hourly", {})
        times = hourly.get("time", [])[:24] # ดู 24 ชม. ข้างหน้า
        precips = hourly.get("precipitation", [])[:24]
        probs = hourly.get("precipitation_probability", [])[:24]

        st.markdown("##### ⏱️ พยากรณ์ปริมาณฝน 24 ชั่วโมงข้างหน้า")
        weather_data = []
        for t, p, pr in zip(times, precips, probs):
            hour_str = t.split("T")[-1]
            weather_data.append({"เวลา": hour_str, "ปริมาณฝน (มม.)": p, "โอกาสฝนตก (%)": pr})
        
        st.dataframe(weather_data, use_container_width=True)
    except Exception:
        st.error("⚠️ ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้ในขณะนี้")

with tab3:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=500, scrolling=True)
    st.markdown("[🔗 เปิดดูหน้าเว็บไซต์หลักแบบเต็มจอ](https://floodboard.org/)", unsafe_allow_html=True)

with tab4:
    st.subheader("📢 เพิ่มจุดรายงานน้ำท่วม หรือกดยืนยันน้ำแห้ง")
    with st.form("report_form"):
        st.markdown("##### 📍 เพิ่มจุดน้ำท่วมใหม่")
        new_loc = st.text_input("ชื่อถนน / ซอย / เขต", placeholder="เช่น ถนนลาดพร้าว ซอย 10")
        new_status = st.text_input("รายละเอียด", placeholder="ท่วมสูงประมาณ 30 ซม.")
        new_level = st.selectbox("ระดับความรุนแรง", ["น้ำขังเล็กน้อย (Warning)", "ท่วมสูงอันตราย (Danger)"])
        submitted = st.form_submit_button("📤 ส่งรายงาน")

        if submitted:
            if new_loc:
                coords = get_lat_lon_free(new_loc)
                if coords:
                    new_id = max([r.get("id", 0) for r in st.session_state.flood_reports], default=0) + 1
                    level_key = "danger" if "Danger" in new_level else "warning"
                    st.session_state.flood_reports.append({
                        "id": new_id,
                        "name": new_loc,
                        "lat": coords["lat"],
                        "lon": coords["lon"],
                        "status": new_status,
                        "level": level_key
                    })
                    st.success("🎉 เพิ่มหมุดเตือนภัยลงในระบบเรียบร้อยแล้ว")
                else:
                    st.error("❌ ไม่พบพิกัดของสถานที่นี้ กรุณาระบุชื่อถนนหรือเขตให้ชัดเจนขึ้นครับ")
            else:
                st.warning("⚠️ กรุณากรอกชื่อสถานที่")

    st.markdown("---")
    st.markdown("##### ✅ รายการจุดน้ำท่วมปัจจุบัน (กดลบออกได้เมื่อน้ำแห้ง)")
    for report in st.session_state.flood_reports:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"📍 **{report['name']}** — {report['status']}")
        with col2:
            rid = report.get("id", id(report))
            if st.button("น้ำแห้งแล้ว", key=f"del_{rid}"):
                st.session_state.flood_reports = [r for r in st.session_state.flood_reports if r.get("id", id(r)) != rid]
                st.success(f"ลบหมุดเรียบร้อยครับ!")
                st.rerun()

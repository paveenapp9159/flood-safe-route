import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components

st.set_page_config(page_title="SafeRoute & Floodboard", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางเลี่ยงน้ำท่วม กทม.")
st.write("ระบบตรวจสอบเส้นทางอัจฉริยะ พร้อมเช็กพยากรณ์ฝนและแผนผัง Floodboard สด")

# ---------------------------------------------------------------------------
# ฐานข้อมูลจุดน้ำท่วมจริงแบบเสถียร (ไม่อ่านจาก Google Sheets)
# ---------------------------------------------------------------------------
stable_flood_reports = [
    {"name": "ถนนรามคำแหง (บางกะปิ)", "lat": 13.7580, "lon": 100.6200, "status": "ท่วมขัง ~60 cm (รถเล็กผ่านไม่ได้)", "level": "danger"},
    {"name": "ถนนพัฒนาการ (สวนหลวง)", "lat": 13.7315, "lon": 100.6120, "status": "ท่วมขัง ~80 cm (วิกฤต)", "level": "danger"},
    {"name": "ถนนงามวงศ์วาน (หลักสี่)", "lat": 13.8582, "lon": 100.5447, "status": "ท่วมขัง ~33 cm", "level": "warning"},
    {"name": "ถนนนวมินทร์ (บางกะปิ)", "lat": 13.7850, "lon": 100.6500, "status": "ท่วมขัง ~80 cm (อันตราย)", "level": "danger"},
    {"name": "ถนนพหลโยธิน (ดอนเมือง)", "lat": 13.8800, "lon": 100.6000, "status": "ท่วมขัง ~80 cm", "level": "danger"},
    {"name": "ถนนศรีนครินทร์ (สวนหลวง)", "lat": 13.7450, "lon": 100.6420, "status": "ท่วมขัง ~47 cm", "level": "danger"},
    {"name": "ถนนลาดพร้าว (บางกะปิ)", "lat": 13.7800, "lon": 100.6000, "status": "ท่วมขัง ~30 cm", "level": "warning"},
    {"name": "ถนนลาดกระบัง (ลาดกระบัง)", "lat": 13.7250, "lon": 100.7900, "status": "ท่วมขัง ~80 cm", "level": "danger"},
    {"name": "ถนนวัชรพล (สายไหม)", "lat": 13.8650, "lon": 100.6380, "status": "ท่วมขัง ~45 cm", "level": "warning"},
    {"name": "ถนนสวนสยาม (คันนายาว)", "lat": 13.8050, "lon": 100.6850, "status": "ท่วมขัง ~25 cm", "level": "warning"},
]

if "flood_reports" not in st.session_state:
    st.session_state.flood_reports = stable_flood_reports

FLOOD_PROXIMITY_METERS = 400
COARSE_FILTER_DEGREES = 0.05
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

geolocator = Nominatim(user_agent="saferoute_stable_app")

def get_lat_lon_free(place_name):
    if not place_name.strip():
        return None
    query = place_name.strip()
    search_queries = [
        query + ", กรุงเทพมหานคร, ประเทศไทย",
        query + ", นนทบุรี, ประเทศไทย",
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
# Tabs หลัก
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ เช็กเส้นทางปลอดภัย", "🌦️ พยากรณ์ฝนตก", "📊 Floodboard"])

with tab1:
    st.subheader("วางแผนการเดินทางเลี่ยงน้ำท่วม")
    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น MRT บางรักใหญ่")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น แม็คโครสามเสน")

    if st.button("🚀 ค้นหาเส้นทาง"):
        if not origin_input or not destination_input:
            st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
        else:
            with st.spinner("กำลังคำนวณเส้นทางและตรวจสอบจุดน้ำท่วม..."):
                loc_orig = get_lat_lon_free(origin_input)
                loc_dest = get_lat_lon_free(destination_input)

                route_coords, route_note = fetch_route(loc_orig, loc_dest)
                
                all_lats = [c[0] for c in route_coords]
                all_lons = [c[1] for c in route_coords]
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)

                m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

                matched = []
                danger_hit = False
                for report in st.session_state.flood_reports:
                    r_lat, r_lon = report["lat"], report["lon"]
                    for c_lat, c_lon in route_coords:
                        if abs(c_lat - r_lat) <= COARSE_FILTER_DEGREES and abs(c_lon - r_lon) <= COARSE_FILTER_DEGREES:
                            matched.append(report)
                            if report["level"] == "danger":
                                danger_hit = True
                            break

                folium.PolyLine(route_coords, color="red" if danger_hit else "blue", weight=6, opacity=0.8).add_to(m)
                folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip="จุดเริ่มต้น", icon=folium.Icon(color="green", icon="play")).add_to(m)
                folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip="ปลายทาง", icon=folium.Icon(color="red", icon="stop")).add_to(m)

                for report in st.session_state.flood_reports:
                    folium.Marker(
                        [report["lat"], report["lon"]],
                        popup=f"<b>{html.escape(report['name'])}</b><br>{html.escape(report['status'])}",
                        tooltip="จุดน้ำท่วมขัง",
                        icon=folium.Icon(color="red" if report["level"] == "danger" else "orange", icon="warning-sign"),
                    ).add_to(m)

                st_folium(m, width=700, height=450, returned_objects=[])

                if route_note:
                    st.info(route_note)

                if danger_hit:
                    names = ", ".join(html.escape(r["name"]) for r in matched if r["level"] == "danger")
                    st.error(f"🚨 เส้นทางนี้ผ่านพื้นที่น้ำท่วมขัง ({names}) แนะนำเปลี่ยนเส้นทาง!")
                elif matched:
                    st.warning("⚠️ เส้นทางผ่านใกล้จุดที่มีน้ำขังรอการระบาย ระมัดระวังด้วยครับ")
                else:
                    st.success("✅ ไม่พบจุดเสี่ยงน้ำท่วมในเส้นทางนี้ เดินทางได้ปกติครับ")

with tab2:
    st.subheader("🌦️ เช็กพยากรณ์ฝนและสภาพอากาศ")
    weather_url = "https://api.open-meteo.com/v1/forecast?latitude=13.7563&longitude=100.5018&hourly=precipitation_probability,precipitation,rain&timezone=Asia%2FBangkok"
    try:
        w_res = requests.get(weather_url, timeout=5).json()
        hourly = w_res.get("hourly", {})
        times = hourly.get("time", [])[:24]
        precips = hourly.get("precipitation", [])[:24]
        probs = hourly.get("precipitation_probability", [])[:24]
        weather_data = [{"เวลา": t.split("T")[-1], "ปริมาณฝน (มม.)": p, "โอกาสฝนตก (%)": pr} for t, p, pr in zip(times, precips, probs)]
        st.dataframe(weather_data, use_container_width=True)
    except Exception:
        st.error("⚠️ ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้")

with tab3:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=500, scrolling=True)

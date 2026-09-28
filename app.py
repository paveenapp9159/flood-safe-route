import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
import pandas as pd
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components

st.set_page_config(page_title="SafeRoute & Auto-Geocoding", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางเลี่ยงน้ำท่วม (Auto-Sync)")
st.write("ระบบดึงข้อมูลจาก Google Sheets และแปลงชื่อถนนเป็นพิกัดบนแผนที่ให้อัตโนมัติ")

# ---------------------------------------------------------------------------
# ลิงก์ CSV จาก Google Sheets ของคุณ
# ---------------------------------------------------------------------------
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1emYaPZT-L-zWOq5Oezr_ZPURy-LTlnzLAPA7HaUjOug/export?format=csv"

geolocator = Nominatim(user_agent="saferoute_auto_geo_app_v2")

@st.cache_data(ttl=60)
def load_and_geolocate_data(url):
    try:
        # อ่านไฟล์ CSV โดยให้แถวแรกเป็นข้อมูลเลย (header=None) เพื่อป้องกันปัญหาชื่อหัวคอลัมน์ไม่ตรง
        df = pd.read_csv(url, header=None)
        
        reports = []
        # วนลูปอ่านทีละแถว
        for index, row in df.iterrows():
            # ข้ามแถวแรกถ้าเป็นหัวตารางภาษาไทยหรือคำว่า 'ถนน'
            col0_val = str(row.iloc[0]).strip()
            if index == 0 and ("ถนน" in col0_val or "name" in col0_val.lower()):
                continue
            
            if not col0_val or col0_val == "nan":
                continue

            road_name = col0_val
            district = str(row.iloc[1]).strip() if len(row) > 1 else ""
            depth = str(row.iloc[3]).strip() if len(row) > 3 else "ไม่ระบุ"
            
            # กรองเฉพาะแถวที่เป็นถนนหรือซอย
            if "ถนน" not in road_name and "ซอย" not in road_name:
                continue

            # ประเมินระดับอันตรายจากความลึก
            level = "danger" if any(x in depth for x in ["50", "60", "70", "80", "90", "100", "110", "140"]) else "warning"
            
            # ค้นหาพิกัดอัตโนมัติ
            query = f"{road_name}, {district}, กรุงเทพมหานคร, ประเทศไทย"
            try:
                loc = geolocator.geocode(query, timeout=3)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
                else:
                    lat, lon = 13.7563, 100.5018
            except Exception:
                lat, lon = 13.7563, 100.5018

            reports.append({
                "name": f"{road_name} ({district})",
                "lat": lat,
                "lon": lon,
                "status": f"ท่วมขัง {depth}",
                "level": level
            })
        return reports
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
        return []

# โหลดและแปลงพิกัดอัตโนมัติ
flood_reports = load_and_geolocate_data(GOOGLE_SHEET_CSV_URL)

FLOOD_PROXIMITY_METERS = 400
COARSE_FILTER_DEGREES = 0.05
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

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

def get_lat_lon_free(place_name):
    if not place_name.strip():
        return None
    try:
        query = place_name.strip()
        if "กรุงเทพ" not in query and "นนทบุรี" not in query:
            query += ", กรุงเทพมหานคร, ประเทศไทย"
        loc = geolocator.geocode(query, timeout=5)
        if loc:
            return {"lat": loc.latitude, "lon": loc.longitude}
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# Tabs การใช้งาน
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ เช็กเส้นทางปลอดภัย", "🌦️ พยากรณ์ฝนตก", "📊 Floodboard"])

with tab1:
    st.subheader("วางแผนการเดินทางเลี่ยงน้ำท่วม")
    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น มหาวิทยาลัยเกษตรศาสตร์")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น นวมินทร์ 36")

    if st.button("🚀 ค้นหาเส้นทาง"):
        if not origin_input or not destination_input:
            st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
        else:
            with st.spinner("กำลังแปลงพิกัดและคำนวณเส้นทาง..."):
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

                    matched = []
                    danger_hit = False
                    for report in flood_reports:
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

                    for report in flood_reports:
                        folium.Marker(
                            [report["lat"], report["lon"]],
                            popup=f"<b>{html.escape(report['name'])}</b><br>{html.escape(report['status'])}",
                            tooltip="จุดน้ำท่วมขัง",
                            icon=folium.Icon(color="red" if report["level"] == "danger" else "orange", icon="warning-sign"),
                        ).add_to(m)

                    st_folium(m, width=700, height=450, returned_objects=[])

                    if danger_hit:
                        st.error("🚨 เส้นทางนี้ผ่านพื้นที่น้ำท่วมขังสูง แนะนำเปลี่ยนเส้นทาง!")
                    else:
                        st.success("✅ ไม่พบจุดเสี่ยงน้ำท่วมรุนแรงในเส้นทางนี้")

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

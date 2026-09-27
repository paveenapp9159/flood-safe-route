import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
from geopy.geocoders import Nominatim

st.set_page_config(page_title="SafeRoute Free Search", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางน้ำท่วม (ค้นหาฟรี ไม่ต้องใช้ API Key)")
st.write("พิมพ์ชื่อสถานที่ คอนโด หรือโรงพยาบาลได้อิสระ ระบบจะค้นหาพิกัดและตรวจสอบเส้นทางให้ทันที")

# ฐานข้อมูลจำลองจุดน้ำท่วมสด
flood_reports = [
    {"name": "ถนนแจ้งวัฒนะ (ปากเกร็ด)", "lat": 13.9065, "lon": 100.5027,
     "status": "ท่วมสูง 15-20 ซม. รถเล็กควรเลี่ยง", "level": "danger"},
    {"name": "แยกพงษ์เพชร (งามวงศ์วาน)", "lat": 13.8582, "lon": 100.5447,
     "status": "มีน้ำขังรอการระบาย", "level": "warning"},
    {"name": "ถนนรัตนาธิเบศร์", "lat": 13.8590, "lon": 100.5115,
     "status": "ท่วมสูง 15-20 ซม.", "level": "danger"},
]

FLOOD_PROXIMITY_METERS = 250
COARSE_FILTER_DEGREES = 0.03
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

# ใช้ Nominatim สำหรับค้นหาพิกัดฟรี
geolocator = Nominatim(user_agent="saferoute_free_app_v3")

def get_lat_lon_free(place_name):
    """ค้นหาพิกัดฟรีผ่าน OpenStreetMap พร้อมช่วยเติมคำค้นให้แคบลงในโซน กทม.-นนทบุรี"""
    if not place_name.strip():
        return None
    try:
        query = place_name.strip()
        # ถ้าผู้ใช้ไม่ได้พิมพ์จังหวัดหรือกรุงเทพพ่วงท้าย ให้ช่วยเติมอัตโนมัติเพื่อให้หาเจอง่ายขึ้น
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
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return straight_line, "⚠️ ใช้เส้นทางโดยประมาณ (เส้นตรง)"

    if data.get("code") != "Ok" or not data.get("routes"):
        return straight_line, "🚫 ไม่พบเส้นทางถนนจริง แสดงเส้นทางโดยประมาณแทน"

    coords = data["routes"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coords], None

# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------
origin_input = st.text_input("📍 จุดเริ่มต้น (พิมพ์ชื่อสถานที่ คอนโด หรือโรงพยาบาล)", placeholder="เช่น เอสเก้าคอนโด หรือ โรงพยาบาลพระราม 9")
destination_input = st.text_input("🏁 จุดปลายทาง (พิมพ์ชื่อสถานที่)", placeholder="เช่น แม็คโคร สามเสน")

if st.button("🚀 ค้นหาเส้นทางปลอดภัย"):
    if not origin_input or not destination_input:
        st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
    else:
        with st.spinner("กำลังค้นหาพิกัดและคำนวณเส้นทาง..."):
            loc_orig = get_lat_lon_free(origin_input)
            loc_dest = get_lat_lon_free(destination_input)

            if not loc_orig or not loc_dest:
                st.error("❌ ไม่พบสถานที่ที่คุณค้นหา ลองระบุชื่อถนน แขวง หรือเขตเพิ่มเติม เช่น 'คอนโด เอสเก้า งามวงศ์วาน'")
            else:
                m = folium.Map(
                    location=[(loc_orig["lat"] + loc_dest["lat"]) / 2,
                              (loc_orig["lon"] + loc_dest["lon"]) / 2],
                    zoom_start=13,
                )

                route_coords, route_note = fetch_route(loc_orig, loc_dest)
                is_flooded, matched = route_passes_flood_zone(route_coords, flood_reports)
                
                # วาดเส้นทาง
                folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                                 weight=6, opacity=0.8).add_to(m)

                # ปักหมุด ต้นทาง - ปลายทาง
                folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip=f"จุดเริ่มต้น: {origin_input}",
                               icon=folium.Icon(color="green", icon="play")).add_to(m)
                folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip=f"ปลายทาง: {destination_input}",
                               icon=folium.Icon(color="red", icon="stop")).add_to(m)

                # ปักหมุดจุดน้ำท่วม
                for report in flood_reports:
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

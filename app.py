import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math

st.set_page_config(page_title="SafeRoute BKK & Nonthaburi", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางน้ำท่วม กทม.-นนทบุรี")
st.write("เลือกสถานที่จากรายการเพื่อตรวจสอบเส้นทางบนแผนที่ และเช็กจุดน้ำท่วมขัง")

# ---------------------------------------------------------------------------
# 1) เพิ่มสถานที่ยอดฮิต รวมถึง "โรงพยาบาลพระราม 9" ไว้ในนี้ชัวร์ที่สุด
# ---------------------------------------------------------------------------
locations_db = {
    "โรงพยาบาลพระราม 9 (กทม.)": {"lat": 13.7547, "lon": 100.5707},
    "บางบัวทอง (นนทบุรี)": {"lat": 13.9130, "lon": 100.4247},
    "ปากเกร็ด (แจ้งวัฒนะ)": {"lat": 13.9065, "lon": 100.5027},
    "งามวงศ์วาน (พันธุ์ทิพย์/พงษ์เพชร)": {"lat": 13.8582, "lon": 100.5447},
    "ประชาชื่น": {"lat": 13.8450, "lon": 100.5430},
    "แม็คโคร สามเสน (กทม.)": {"lat": 13.7801, "lon": 100.5145},
    "อนุสาวรีย์ชัยสมรภูมิ (กทม.)": {"lat": 13.7650, "lon": 100.5383},
    "สยามสแควร์ (กทม.)": {"lat": 13.7444, "lon": 100.5330},
    "บางซื่อ (กทม.)": {"lat": 13.8039, "lon": 100.5398},
    "เซ็นทรัล พระราม 9 (กทม.)": {"lat": 13.7570, "lon": 100.5651},
    "ฟิวเจอร์พาร์ค รังสิต": {"lat": 13.9897, "lon": 100.6178}
}

# ---------------------------------------------------------------------------
# 2) ฐานข้อมูลจุดน้ำท่วม
# ---------------------------------------------------------------------------
flood_reports = [
    {"name": "ถนนแจ้งวัฒนะ (ปากเกร็ด)", "lat": 13.9065, "lon": 100.5027,
     "status": "ท่วมสูง 15-20 ซม. รถเล็กควรเลี่ยง", "level": "danger"},
    {"name": "แยกพงษ์เพชร (งามวงศ์วาน)", "lat": 13.8582, "lon": 100.5447,
     "status": "มีน้ำขังรอการระบาย", "level": "warning"},
    {"name": "ถนนรัตนาธิเบศร์ (ศูนย์ราชการฯ-แยกแคราย)", "lat": 13.8590, "lon": 100.5115,
     "status": "ท่วมสูง 15-20 ซม.", "level": "danger"},
]

FLOOD_PROXIMITY_METERS = 250
COARSE_FILTER_DEGREES = 0.03
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
OSRM_TIMEOUT_SECONDS = 8

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
        response = requests.get(url, timeout=OSRM_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return straight_line, "⚠️ ใช้เส้นทางโดยประมาณ (เส้นตรงเนื่องจากระบบคำนวณถนนขัดข้องชั่วคราว)"

    if data.get("code") != "Ok" or not data.get("routes"):
        return straight_line, "🚫 ไม่พบเส้นทางถนนจริง แสดงเส้นทางโดยประมาณแทน"

    coords = data["routes"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coords], None

# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------
origin_name = st.selectbox("📍 จุดเริ่มต้น", list(locations_db.keys()), index=5)
destination_name = st.selectbox("🏁 จุดปลายทาง", list(locations_db.keys()), index=0)

if st.button("🚀 แสดงเส้นทางและเช็กน้ำท่วม"):
    with st.spinner("กำลังคำนวณเส้นทาง..."):
        loc_orig = locations_db[origin_name]
        loc_dest = locations_db[destination_name]

        m = folium.Map(
            location=[(loc_orig["lat"] + loc_dest["lat"]) / 2,
                      (loc_orig["lon"] + loc_dest["lon"]) / 2],
            zoom_start=13,
        )

        route_coords, route_note = fetch_route(loc_orig, loc_dest)
        is_flooded, matched = route_passes_flood_zone(route_coords, flood_reports)
        
        # วาดเส้นทางถนน
        folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                         weight=6, opacity=0.8).add_to(m)

        # ปักหมุด ต้นทาง - ปลายทาง
        folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip=f"จุดเริ่มต้น: {origin_name}",
                       icon=folium.Icon(color="green", icon="play")).add_to(m)
        folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip=f"ปลายทาง: {destination_name}",
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

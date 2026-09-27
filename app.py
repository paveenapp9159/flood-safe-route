import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

st.set_page_config(page_title="SafeRoute BKK & Nonthaburi", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กน้ำท่วม & เลี่ยงเส้นทาง กทม.-นนทบุรี")
st.write("ระบบวางแผนเดินทางอัจฉริยะ ตรวจสอบจุดเสี่ยงและรายงานสถานการณ์สดเพื่อความปลอดภัย")

# ฐานข้อมูลพิกัดโซนยอดฮิต (ป้องกันปัญหาหาพิกัดไม่เจอ)
locations_db = {
    "บางบัวทอง (นนทบุรี)": {"lat": 13.9130, "lon": 100.4247},
    "ปากเกร็ด (แจ้งวัฒนะ)": {"lat": 13.9065, "lon": 100.5027},
    "งามวงศ์วาน (พันธุ์ทิพย์/พงษ์เพชร)": {"lat": 13.8582, "lon": 100.5447},
    "ประชาชื่น": {"lat": 13.8450, "lon": 100.5430},
    "แม็คโคร สามเสน (กทม.)": {"lat": 13.7801, "lon": 100.5145},
    "อนุสาวรีย์ชัยสมรภูมิ (กทม.)": {"lat": 13.7650, "lon": 100.5383},
    "สยามสแควร์ (กทม.)": {"lat": 13.7444, "lon": 100.5330},
    "บางซื่อ (กทม.)": {"lat": 13.8039, "lon": 100.5398}
}

# ระบบความจำจำลองจุดน้ำท่วม
if "flood_reports" not in st.session_state:
    st.session_state.flood_reports = [
        {"name": "ถนนแจ้งวัฒนะ (ปากเกร็ด)", "lat": 13.9065, "lon": 100.5027, "status": "ท่วมสูง 15-20 ซม. รถเล็กควรเลี่ยง", "level": "danger"},
        {"name": "แยกพงษ์เพชร (งามวงศ์วาน)", "lat": 13.8582, "lon": 100.5447, "status": "มีน้ำขังรอการระบาย", "level": "warning"}
    ]

# แบ่งหน้าการใช้งาน
tab1, tab2 = st.tabs(["🔍 เช็กเส้นทาง & แผนที่", "📢 รายงานจุดน้ำท่วมสด"])

with tab1:
    st.subheader("วางแผนการเดินทางของคุณ")
    
    # เปลี่ยนมาใช้ Selectbox เพื่อความแม่นยำของพิกัด
    origin_name = st.selectbox("📍 เลือกจุดเริ่มต้น", list(locations_db.keys()), index=0)
    destination_name = st.selectbox("🏁 เลือกจุดปลายทาง", list(locations_db.keys()), index=4)

    if st.button("🚀 ค้นหาเส้นทางปลอดภัย"):
        with st.spinner("กำลังคำนวณเส้นทางและตรวจสอบจุดเสี่ยง..."):
            loc_orig = locations_db[origin_name]
            loc_dest = locations_db[destination_name]
            
            center_lat = (loc_orig["lat"] + loc_dest["lat"]) / 2
            center_lon = (loc_orig["lon"] + loc_dest["lon"]) / 2
            m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
            
            # ดึงเส้นทางจาก OSRM API
            url = f"http://router.project-osrm.org/route/v1/driving/{loc_orig['lon']},{loc_orig['lat']};{loc_dest['lon']},{loc_dest['lat']}?overview=full&geometries=geojson"
            response = requests.get(url).json()
            
            is_flooded = False
            if "routes" in response:
                route_coords = response["routes"][0]["geometry"]["coordinates"]
                latlon_coords = [[coord[1], coord[0]] for coord in route_coords]
                
                # เช็กว่าเส้นทางผ่านจุดน้ำท่วมหรือไม่
                for coord in latlon_coords:
                    for report in st.session_state.flood_reports:
                        if abs(coord[0] - report["lat"]) < 0.02 and abs(coord[1] - report["lon"]) < 0.02:
                            if report["level"] == "danger":
                                is_flooded = True
                                break
                    if is_flooded:
                        break
                
                # วาดเส้นทาง (แดง = เสี่ยงน้ำท่วม, ฟ้า = ปลอดภัย)
                line_color = "red" if is_flooded else "blue"
                folium.PolyLine(latlon_coords, color=line_color, weight=6, opacity=0.8).add_to(m)
            
            # ปักหมุด ต้นทาง - ปลายทาง
            folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip="จุดเริ่มต้น", icon=folium.Icon(color="green", icon="play")).add_to(m)
            folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip="ปลายทาง", icon=folium.Icon(color="red", icon="stop")).add_to(m)
            
            # ปักหมุดจุดเสี่ยงทั้งหมด
            for report in st.session_state.flood_reports:
                color = "red" if report["level"] == "danger" else "orange"
                folium.Marker(
                    [report["lat"], report["lon"]],
                    popup=f"<b>{report['name']}</b><br>{report['status']}",
                    tooltip="จุดน้ำท่วมขัง",
                    icon=folium.Icon(color=color, icon="warning-sign")
                ).add_to(m)
            
            # แสดงผลแผนที่
            st_folium(m, width=700, height=450)
            
            if is_flooded:
                st.error("🚨 **คำเตือน:** เส้นทางนี้ผ่านพื้นที่น้ำท่วมสูง แนะนำให้หลีกเลี่ยงหรือเปลี่ยนเส้นทาง!")
            else:
                st.success("✅ **เดินทางได้ปกติ:** ไม่พบจุดเสี่ยงอันตรายในเส้นทางนี้ ขับขี่ด้วยความปลอดภัยครับ!")

with tab2:
    st.subheader("📢 แจ้งเบาะแสสถานการณ์น้ำท่วม (Real-time)")
    st.write("ช่วยกันรายงานเพื่อเตือนเพื่อนร่วมทางคนอื่นๆ บนท้องถนนครับ")
    
    with st.form("report_form"):
        report_location = st.text_input("📍 ชื่อสถานที่ / ถนน / ซอยที่พบน้ำท่วม", placeholder="เช่น ถนนประชาราษฎร์สาย 1")
        report_status = st.text_input("📝 รายละเอียด (เช่น น้ำสูง 10 ซม., รถยังผ่านได้)", placeholder="น้ำขังรอระบาย")
        report_level = st.selectbox("⚠️ ระดับความรุนแรง", ["เฝ้าระวัง (น้ำขังเล็กน้อย)", "อันตราย (รถเล็กผ่านไม่ได้)"])
        submit_report = st.form_submit_button("📤 ส่งรายงานทันที")
        
        if submit_report:
            if report_location:
                # เพิ่มพิกัดจำลองกลาง กทม. สำหรับรายงานสด
                st.session_state.flood_reports.append({
                    "name": report_location,
                    "lat": 13.7563,
                    "lon": 100.5018,
                    "status": report_status,
                    "level": "danger" if "อันตราย" in report_level else "warning"
                })
                st.success("🎉 ขอบคุณสำหรับการแบ่งปันข้อมูล! ระบบได้อัปเดตหมุดเตือนภัยบนแผนที่ให้ทันที")
            else:
                st.warning("กรุณากรอกชื่อสถานที่ก่อนกดส่งรายงานครับ")

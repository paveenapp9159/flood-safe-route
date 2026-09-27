import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import requests

st.set_page_config(page_title="SafeRoute BKK & Nonthaburi", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กน้ำท่วม & เลี่ยงเส้นทาง กทม.-นนทบุรี")
st.write("ระบบวางแผนเดินทางอัจฉริยะ ตรวจสอบจุดเสี่ยงและรายงานสถานการณ์สดเพื่อความปลอดภัย")

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
    origin = st.text_input("📍 จุดเริ่มต้น (เช่น มหาวิทยาลัยเกษตรศาสตร์)", "มหาวิทยาลัยเกษตรศาสตร์")
    destination = st.text_input("🏁 ปลายทาง (เช่น เซ็นทรัล แจ้งวัฒนะ)", "เซ็นทรัล แจ้งวัฒนะ")

    if st.button("🚀 ค้นหาเส้นทางปลอดภัย"):
        if not origin or not destination:
            st.warning("กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วนครับ")
        else:
            with st.spinner("กำลังคำนวณเส้นทางและตรวจสอบพิกัด..."):
                geolocator = Nominatim(user_agent="saferoute_bkk_app")
                loc_orig = geolocator.geocode(origin + ", Bangkok, Thailand")
                loc_dest = geolocator.geocode(destination + ", Bangkok, Thailand")
                
                if loc_orig and loc_dest:
                    # สร้างแผนที่ตรงกลางระหว่างจุดสองจุด
                    center_lat = (loc_orig.latitude + loc_dest.latitude) / 2
                    center_lon = (loc_orig.longitude + loc_dest.longitude) / 2
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
                    
                    # ดึงเส้นทางจาก OSRM API
                    url = f"http://router.project-osrm.org/route/v1/driving/{loc_orig.longitude},{loc_orig.latitude};{loc_dest.longitude},{loc_dest.latitude}?overview=full&geometries=geojson"
                    response = requests.get(url).json()
                    
                    is_flooded = False
                    if "routes" in response:
                        route_coords = response["routes"][0]["geometry"]["coordinates"]
                        latlon_coords = [[coord[1], coord[0]] for coord in route_coords]
                        
                        # เช็กว่าเส้นทางตัดผ่านจุดน้ำท่วมหรือไม่
                        for coord in latlon_coords:
                            for report in st.session_state.flood_reports:
                                if abs(coord[0] - report["lat"]) < 0.015 and abs(coord[1] - report["lon"]) < 0.015:
                                    if report["level"] == "danger":
                                        is_flooded = True
                                        break
                            if is_flooded:
                                break
                        
                        # วาดเส้นทางบนแผนที่ (แดง = เสี่ยง, ฟ้า = ปกติ)
                        line_color = "red" if is_flooded else "blue"
                        folium.PolyLine(latlon_coords, color=line_color, weight=6, opacity=0.8).add_to(m)
                    
                    # ปักหมุด ต้นทาง - ปลายทาง
                    folium.Marker([loc_orig.latitude, loc_orig.longitude], tooltip="จุดเริ่มต้น", icon=folium.Icon(color="green", icon="play")).add_to(m)
                    folium.Marker([loc_dest.latitude, loc_dest.longitude], tooltip="ปลายทาง", icon=folium.Icon(color="red", icon="stop")).add_to(m)
                    
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
                else:
                    st.warning("ไม่พบสถานที่ที่คุณระบุ กรุณาระบุชื่อถนนหรือสถานที่สำคัญให้ชัดเจนขึ้นครับ")

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
                geolocator = Nominatim(user_agent="saferoute_reporter")
                loc_rep = geolocator.geocode(report_location + ", Bangkok, Thailand")
                
                if loc_rep:
                    level_key = "danger" if "อันตราย" in report_level else "warning"
                    st.session_state.flood_reports.append({
                        "name": report_location,
                        "lat": loc_rep.latitude,
                        "lon": loc_rep.longitude,
                        "status": report_status,
                        "level": level_key
                    })
                    st.success("🎉 ขอบคุณสำหรับการแบ่งปันข้อมูล! ระบบได้อัปเดตหมุดเตือนภัยบนแผนที่ให้ทันที")
                else:
                    st.error("ไม่สามารถระบุพิกัดของสถานที่นี้ได้ โปรดระบุชื่อเขตหรือแขวงเพิ่มเติมครับ")
            else:
                st.warning("กรุณากรอกชื่อสถานที่ก่อนกดส่งรายงานครับ")

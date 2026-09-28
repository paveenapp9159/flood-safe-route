import streamlit as st
import requests
import streamlit.components.v1 as components
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta

st.set_page_config(page_title="BKK Flood & Weather Dashboard", page_icon="🌊", layout="centered")

st.title("🚨 BKK Flood & Weather Dashboard")
st.write("ศูนย์รวมข้อมูลสถานการณ์น้ำท่วมและพยากรณ์อากาศอัจฉริยะ")

geolocator = Nominatim(user_agent="bkk_weather_v11")

def get_lat_lon_free(place_name):
    query = place_name.strip()
    if not query:
        return None
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

# ---------------------------------------------------------------------------
# UI หลัก (3 แท็บ)
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 Floodboard", "🏛️ BKK Dashboard", "🌦️ พยากรณ์อากาศ 3 วัน (AI Weather)"])

with tab1:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=700, scrolling=True)

with tab2:
    st.subheader("🏛️ รายงานสถานการณ์น้ำท่วม กทม. (BKK Flood Alert)")
    st.markdown("ข้อมูลรายงานสถานการณ์น้ำท่วมและระดับน้ำบนถนนจากกรุงเทพมหานครแบบเรียลไทม์")
    st.markdown("[🔗 เปิดหน้าเว็บรายงานน้ำท่วม กทม. แบบเต็มจอในแท็บใหม่](https://now.bangkok.go.th/flood-alert.html)", unsafe_allow_html=True)
    components.iframe("https://now.bangkok.go.th/flood-alert.html", height=700, scrolling=True)

with tab3:
    st.subheader("🌦️ พยากรณ์ฝน & อุณหภูมิรายโซน (AI Weather Engine)")
    st.markdown("ระบบวิเคราะห์สภาพอากาศล่วงหน้า 3 วัน แยกตามพื้นที่ที่คุณต้องการตรวจสอบ")
    
    col_zone, col_btn = st.columns([3, 1])
    with col_zone:
        zone_input = st.text_input("📍 ระบุโซนหรือเขต", value="กรุงเทพมหานคร", placeholder="เช่น เขตจตุจักร, บางนา, บางกะปิ")
    with col_btn:
        st.write("")
        search_clicked = st.button("🔍 ตรวจสอบ")
    
    target_zone = zone_input if zone_input.strip() else "กรุงเทพมหานคร"
    loc_zone = get_lat_lon_free(target_zone)
    
    if loc_zone:
        lat, lon = loc_zone["lat"], loc_zone["lon"]
        # ดึงข้อมูลพยากรณ์รายวันจาก Open-Meteo (จำลอง AI Weather Engine)
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,windspeed_10m_max&timezone=Asia%2FBangkok"
        
        try:
            res = requests.get(weather_url, timeout=5).json()
            daily = res.get("daily", {})
            times = daily.get("time", [])[:3]
            t_max = daily.get("temperature_2m_max", [])[:3]
            t_min = daily.get("temperature_2m_min", [])[:3]
            precip = daily.get("precipitation_sum", [])[:3]
            prob = daily.get("precipitation_probability_max", [])[:3]
            wind = daily.get("windspeed_10m_max", [])[:3]
            
            if times:
                d1 = datetime.strptime(times[0], "%Y-%m-%d").strftime("%a %d %b")
                d2 = datetime.strptime(times[1], "%Y-%m-%d").strftime("%a %d %b")
                d3 = datetime.strptime(times[2], "%Y-%m-%d").strftime("%a %d %b")
                
                st.markdown(f"📍 **ศูนย์กลาง: {target_zone}** ({lat:.2f}°N, {lon:.2f}°E) | เวลาไทย")
                
                # ตารางสรุป 3 วัน
                weather_table = {
                    "รายการ": [
                        "🌦️ สภาพอากาศหลัก",
                        "💧 โอกาสฝนตก (%)",
                        "🌧️ ปริมาณฝนรวม",
                        "🌡️ อุณหภูมิ สูง / ต่ำ",
                        "💨 ลมแรงสูงสุด"
                    ],
                    f"วันนี้ ({d1})": [
                        "ฝนฟ้าคะนอง" if prob[0] > 50 else "มีเมฆเป็นส่วนมาก",
                        f"{prob[0]}%",
                        f"{precip[0]} มม.",
                        f"{t_max[0]}°C / {t_min[0]}°C",
                        f"{wind[0]} กม./ชม."
                    ],
                    f"พรุ่งนี้ ({d2})": [
                        "ฝนตกปานกลาง" if prob[1] > 50 else "เมฆกระจาย",
                        f"{prob[1]}%",
                        f"{precip[1]} มม.",
                        f"{t_max[1]}°C / {t_min[1]}°C",
                        f"{wind[1]} กม./ชม."
                    ],
                    f"มะรืนนี้ ({d3})": [
                        "ฟ้าโปร่ง / ฝนเล็กน้อย" if prob[2] < 40 else "ฝนฟ้าคะนอง",
                        f"{prob[2]}%",
                        f"{precip[2]} มม.",
                        f"{t_max[2]}°C / {t_min[2]}°C",
                        f"{wind[2]} กม./ชม."
                    ]
                }
                
                st.table(weather_table)
                
                # กล่องสรุปสถานการณ์
                st.markdown("### 📌 สรุปสถานการณ์ 3 วัน:")
                st.markdown(f"- **วันนี้ ({d1}):** ปริมาณฝน {precip[0]} มม. โอกาสฝนตก **{prob[0]}%** {'→ เตรียมร่ม!' if prob[0]>50 else '→ บรรยากาศปกติ'}")
                st.markdown(f"- **พรุ่งนี้ ({d2}):** ปริมาณฝน {precip[1]} มม. โอกาสฝนตก **{prob[1]}%**")
                st.markdown(f"- **มะรืนนี้ ({d3}):** ปริมาณฝน {precip[2]} มม. โอกาสฝนตก **{prob[2]}%**")
                
                total_rain = sum(precip)
                st.info(f"📊 **ภาพรวม 3 วันในโซน {target_zone}:** ปริมาณฝนสะสมรวม {total_rain:.2f} มม.")
            else:
                st.warning("⚠️ ไม่พบข้อมูลพยากรณ์ในขณะนี้")
        except Exception:
            st.error("⚠️ ไม่สามารถเชื่อมต่อกับระบบพยากรณ์อากาศได้")
    else:
        st.error("❌ ไม่พบพิกัดของโซนที่คุณระบุ")

import streamlit as st
import requests
import streamlit.components.v1 as components
from geopy.geocoders import Nominatim

st.set_page_config(page_title="BKK Flood & Weather Dashboard", page_icon="🌊", layout="centered")

st.title("🚨 BKK Flood & Weather Dashboard")
st.write("ศูนย์รวมข้อมูลสถานการณ์น้ำท่วมและพยากรณ์อากาศรายโซน กทม.")

geolocator = Nominatim(user_agent="bkk_weather_v10")

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
# UI หลัก (3 แท็บตามที่ต้องการ)
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 Floodboard", "🏛️ BKK Dashboard", "🌦️ พยากรณ์ฝนรายโซน"])

with tab1:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=700, scrolling=True)

with tab2:
    st.subheader("🏛️ รายงานสถานการณ์น้ำท่วม กทม. (BKK Flood Alert)")
    st.markdown("ข้อมูลรายงานสถานการณ์น้ำท่วมและระดับน้ำบนถนนจากกรุงเทพมหานครแบบเรียลไทม์")
    st.markdown("[🔗 เปิดหน้าเว็บรายงานน้ำท่วม กทม. แบบเต็มจอในแท็บใหม่](https://now.bangkok.go.th/flood-alert.html)", unsafe_allow_html=True)
    components.iframe("https://now.bangkok.go.th/flood-alert.html", height=700, scrolling=True)

with tab3:
    st.subheader("🌦️ เช็กพยากรณ์ฝนและสภาพอากาศรายโซน")
    st.markdown("พิมพ์ระบุชื่อเขตหรือพื้นที่ที่ต้องการตรวจสอบสภาพอากาศและโอกาสฝนตก")
    
    zone_input = st.text_input("📍 ระบุโซนหรือเขต", placeholder="เช่น เขตจตุจักร, บางนา, บางกะปิ")
    
    if st.button("🔍 ตรวจสอบแนวโน้มฝน"):
        target_zone = zone_input if zone_input.strip() else "กรุงเทพมหานคร"
        loc_zone = get_lat_lon_free(target_zone)
        
        if not loc_zone:
            st.error("❌ ไม่พบพิกัดของโซนที่คุณระบุ ลองพิมพ์ใหม่อีกครั้งครับ")
        else:
            lat, lon = loc_zone["lat"], loc_zone["lon"]
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation_probability,precipitation,rain&timezone=Asia%2FBangkok"
            try:
                w_res = requests.get(weather_url, timeout=5).json()
                hourly = w_res.get("hourly", {})
                times = hourly.get("time", [])[:12]  # 12 ชั่วโมงข้างหน้า
                precips = hourly.get("precipitation", [])[:12]
                probs = hourly.get("precipitation_probability", [])[:12]
                
                st.success(f"📌 ผลพยากรณ์ฝนสำหรับพื้นที่: **{target_zone}**")
                
                weather_data = [{"เวลา": t.split("T")[-1], "ปริมาณฝน (มม.)": p, "โอกาสฝนตก (%)": f"{pr}%"}
                                for t, p, pr in zip(times, precips, probs)]
                st.dataframe(weather_data, use_container_width=True)
                
                max_prob = max(probs) if probs else 0
                if max_prob >= 60:
                    st.error(f"⚠️ มีโอกาสฝนตกสูงถึง {max_prob}% ในช่วงเวลานี้ ควรเตรียมตัวและระวังน้ำขัง")
                elif max_prob >= 30:
                    st.warning(f"⚡ โอกาสฝนตกปานกลางอยู่ที่ {max_prob}% ท้องฟ้าอาจมีเมฆมาก")
                else:
                    st.info(f"✅ โอกาสฝนค่อนข้างต่ำ (สูงสุด {max_prob}%) บรรยากาศปกติ")
            except Exception:
                st.error("⚠️ ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้ในขณะนี้")

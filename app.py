import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import html
import math
import csv
import io
import time
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components

st.set_page_config(page_title="SafeRoute & Floodboard", page_icon="🌊", layout="centered")

st.title("🚨 SafeRoute: เช็กเส้นทางเลี่ยงน้ำท่วม กทม.")
st.write("ระบบตรวจสอบเส้นทางอัจฉริยะ (โหลดข้อมูลครั้งเดียว รวดเร็ว ไม่ต้องรอซ้ำ)")

# ---------------------------------------------------------------------------
# ตั้งค่า
# ---------------------------------------------------------------------------
SHEET_ID = "1emYaPZT-L-zWOq5Oezr_ZPURy-LTlnzLAPA7HaUjOug"
SHEET_GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

TRAFFY_API = "https://publicapi.traffy.in.th/share/teamchadchart/search"
FLOOD_KEYWORDS = ("ท่วม", "น้ำขัง", "น้ำรอระบาย", "ระบายน้ำ")

FALLBACK_REPORTS = [
    {"name": "ถนนงามวงศ์วาน (เขตจตุจักร)", "lat": 13.8582, "lon": 100.5447, "status": "ท่วมขัง ~31 cm", "level": "danger"},
    {"name": "ถนนนวมินทร์ (เขตบางกะปิ)", "lat": 13.7850, "lon": 100.6500, "status": "ท่วมขัง ~80 cm", "level": "danger"},
    {"name": "ถนนรามคำแหง (เขตสวนหลวง)", "lat": 13.7580, "lon": 100.6200, "status": "ท่วมขัง ~100 cm", "level": "danger"},
    {"name": "ถนนพหลโยธิน (เขตดอนเมือง)", "lat": 13.8800, "lon": 100.6000, "status": "ท่วมขัง ~80 cm", "level": "danger"},
    {"name": "ถนนลาดพร้าว (เขตวังทองหลาง)", "lat": 13.7800, "lon": 100.6000, "status": "ท่วมขัง ~70 cm", "level": "danger"},
]

FLOOD_PROXIMITY_METERS = 800
COARSE_FILTER_DEGREES = 0.08
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

geolocator = Nominatim(user_agent="saferoute_fast_cache_v3")


# ---------------------------------------------------------------------------
# โหลดข้อมูลด้วย Cache ระยะยาว (โหลดรอบแรกครั้งเดียว จบเลย)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def load_flood_reports_traffy():
    reports = []
    try:
        for offset in (0, 1000, 2000):
            resp = requests.get(TRAFFY_API, params={"limit": 1000, "offset": offset}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results") or data.get("features") or []
            if not items:
                break

            for it in items:
                props = it.get("properties", it) if isinstance(it, dict) else {}
                text = " ".join(str(props.get(k, "")) for k in
                                ("description", "comment", "type", "problem_type_abdul", "address"))
                if not any(kw in text for kw in FLOOD_KEYWORDS):
                    continue

                coords = props.get("coords") or (it.get("geometry") or {}).get("coordinates")
                if not coords or len(coords) < 2:
                    continue
                try:
                    lon, lat = float(coords[0]), float(coords[1])
                except (TypeError, ValueError):
                    continue
                if not (13.4 < lat < 14.2 and 100.2 < lon < 101.0):
                    continue

                desc = str(props.get("description") or props.get("comment") or "น้ำท่วมขัง")[:120]
                district = str(props.get("district") or props.get("subdistrict") or "")
                addr = str(props.get("address") or "จุดแจ้งน้ำท่วม")[:70]
                reports.append({
                    "name": f"{addr} ({district})" if district else addr,
                    "lat": lat, "lon": lon, "status": desc, "level": "danger",
                })
        return reports
    except Exception:
        return []


def parse_sheet_rows(csv_text):
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for r in reader:
        name = (r.get("name") or "").strip()
        level = (r.get("level") or "").strip().lower()
        if not name or name == "ถนน" or level not in ("danger", "warning"):
            continue
        item = {
            "name": name,
            "district": (r.get("district") or "").strip(),
            "distance": (r.get("distance") or "").strip(),
            "depth": (r.get("depth") or "").strip(),
            "level": level,
            "lat": None, "lon": None,
        }
        try:
            if (r.get("lat") or "").strip() and (r.get("lon") or "").strip():
                item["lat"] = float(r["lat"])
                item["lon"] = float(r["lon"])
        except ValueError:
            pass
        rows.append(item)
    return rows


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def geocode_road(name, district):
    province = "นนทบุรี" if district.startswith("อำเภอ") else "กรุงเทพมหานคร"
    for q in [f"{name} {district} {province} ประเทศไทย", f"{name} {province} ประเทศไทย"]:
        try:
            loc = geolocator.geocode(q, timeout=3)
            time.sleep(0.5)
            if loc:
                return (loc.latitude, loc.longitude)
        except Exception:
            continue
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def load_flood_reports_sheet():
    try:
        resp = requests.get(SHEET_CSV_URL, timeout=8)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        rows = parse_sheet_rows(resp.text)
    except Exception as e:
        return FALLBACK_REPORTS, {"source": "fallback", "total": len(FALLBACK_REPORTS),
                                  "skipped": 0, "error": type(e).__name__}

    if not rows:
        return FALLBACK_REPORTS, {"source": "fallback", "total": len(FALLBACK_REPORTS),
                                  "skipped": 0, "error": "ชีตไม่มีแถวที่อ่านได้"}

    reports, skipped = [], 0
    for r in rows:
        lat, lon = r["lat"], r["lon"]
        if lat is None or lon is None:
            coords = geocode_road(r["name"], r["district"])
            if coords is None:
                skipped += 1
                continue
            lat, lon = coords
        status = f"ท่วมขัง {r['depth']}"
        if r["distance"]:
            status += f" (ถนนมีน้ำ {r['distance']})"
        reports.append({
            "name": f"{r['name']} ({r['district']})" if r["district"] else r["name"],
            "lat": lat, "lon": lon, "status": status, "level": r["level"],
        })

    if not reports:
        return FALLBACK_REPORTS, {"source": "fallback", "total": len(FALLBACK_REPORTS),
                                  "skipped": skipped, "error": "หาพิกัดไม่ได้เลย"}
    return reports, {"source": "sheet", "total": len(reports), "skipped": skipped, "error": None}


def load_flood_reports_combined():
    traffy = load_flood_reports_traffy()
    if traffy:
        return traffy, {"source": "traffy", "total": len(traffy), "skipped": 0, "error": None}
    return load_flood_reports_sheet()


# ---------------------------------------------------------------------------
# ค้นหาพิกัดสถานที่
# ---------------------------------------------------------------------------
def get_lat_lon_free(place_name):
    query = place_name.strip()
    if not query:
        return None
    
    search_queries = [
        query + ", กรุงเทพมหานคร, ประเทศไทย",
        query + ", นนทบุรี, ประเทศไทย",
        query.replace("MRT", "สถานีรถไฟฟ้า MRT") + ", กรุงเทพมหานคร, ประเทศไทย",
        query.replace("BTS", "สถานีรถไฟฟ้า BTS") + ", กรุงเทพมหานคร, ประเทศไทย",
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
            
    if "บางใหญ่" in query or "นนทบุรี" in query:
        return {"lat": 13.8749, "lon": 100.4181}
    return {"lat": 13.7563, "lon": 100.5018}


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
# UI หลัก
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ เช็กเส้นทางปลอดภัย", "🌦️ พยากรณ์ฝนตก", "📊 Floodboard"])

with tab1:
    st.subheader("วางแผนการเดินทางเลี่ยงน้ำท่วม")

    # โหลดข้อมูลครั้งเดียวเก็บไว้ในแคช
    if "cached_reports" not in st.session_state or "cached_info" not in st.session_state:
        with st.spinner("กำลังโหลดข้อมูลจุดน้ำท่วมเข้าระบบครั้งแรก..."):
            st.session_state.cached_reports, st.session_state.cached_info = load_flood_reports_combined()

    flood_reports = st.session_state.cached_reports
    info = st.session_state.cached_info

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        if info["source"] == "traffy":
            st.caption(f"🛰️ ใช้ข้อมูลสดจาก Traffy Fondue: {info['total']} จุด (โหลดเรียบร้อย)")
        elif info["source"] == "sheet":
            st.caption(f"📄 ใช้ข้อมูลจาก Google Sheet: {info['total']} จุด (โหลดเรียบร้อย)")
        else:
            st.warning(f"⚠️ ใช้ข้อมูลสำรองในระบบ ({info['error']})")
    with col_btn:
        if st.button("🔄 โหลดใหม่"):
            load_flood_reports_traffy.clear()
            load_flood_reports_sheet.clear()
            if "cached_reports" in st.session_state:
                del st.session_state.cached_reports
            if "cached_info" in st.session_state:
                del st.session_state.cached_info
            st.rerun()

    origin_input = st.text_input("📍 จุดเริ่มต้น", placeholder="เช่น MRT บางรักใหญ่")
    destination_input = st.text_input("🏁 จุดปลายทาง", placeholder="เช่น แยกพงษ์เพชร")

    if st.button("🚀 ค้นหาเส้นทาง"):
        if not origin_input or not destination_input:
            st.warning("⚠️ กรุณากรอกข้อมูลจุดเริ่มต้นและปลายทางให้ครบถ้วน")
        else:
            with st.spinner("กำลังคำนวณเส้นทางและตรวจสอบจุดน้ำท่วมขัง..."):
                loc_orig = get_lat_lon_free(origin_input)
                loc_dest = get_lat_lon_free(destination_input)

            if loc_orig is None or loc_dest is None:
                st.error("❌ ไม่สามารถระบุพิกัดได้ ลองระบุชื่อเขตหรือจังหวัดเพิ่มเติมครับ")
            else:
                route_coords, route_note = fetch_route(loc_orig, loc_dest)

                center_lat = sum(c[0] for c in route_coords) / len(route_coords)
                center_lon = sum(c[1] for c in route_coords) / len(route_coords)
                m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

                is_flooded, matched = route_passes_flood_zone(route_coords, flood_reports)

                folium.PolyLine(route_coords, color="red" if is_flooded else "blue",
                                weight=6, opacity=0.8).add_to(m)
                folium.Marker([loc_orig["lat"], loc_orig["lon"]], tooltip="จุดเริ่มต้น",
                              icon=folium.Icon(color="green", icon="play")).add_to(m)
                folium.Marker([loc_dest["lat"], loc_dest["lon"]], tooltip="ปลายทาง",
                              icon=folium.Icon(color="red", icon="stop")).add_to(m)

                shown = matched if matched else flood_reports[:60]
                for report in shown:
                    folium.Marker(
                        [report["lat"], report["lon"]],
                        popup=f"<b>{html.escape(report['name'])}</b><br>{html.escape(report['status'])}",
                        tooltip="จุดน้ำท่วมขัง",
                        icon=folium.Icon(color="red" if report["level"] == "danger" else "orange",
                                         icon="warning-sign"),
                    ).add_to(m)

                st_folium(m, width=700, height=450, returned_objects=[], key="route_map")

                if route_note:
                    st.info(route_note)

                if is_flooded:
                    names = ", ".join(html.escape(r["name"]) for r in matched[:8])
                    more = f" และอีกยาวนานกว่า {len(matched) - 8} จุด" if len(matched) > 8 else ""
                    st.error(f"🚨 เส้นทางนี้ผ่านใกล้พื้นที่น้ำท่วมขัง ({names}{more}) แนะนำเปลี่ยนเส้นทาง!")
                elif matched:
                    st.warning("⚠️ เส้นทางผ่านใกล้จุดที่มีน้ำขัง ขับขี่ด้วยความระมัดระวัง")
                else:
                    st.success("✅ ไม่พบจุดน้ำท่วมใกล้เส้นทางนี้ (ควรเช็กข่าวก่อนออกเดินทางด้วยครับ)")

with tab2:
    st.subheader("🌦️ เช็กพยากรณ์ฝนและสภาพอากาศ")
    weather_url = ("https://api.open-meteo.com/v1/forecast?latitude=13.7563&longitude=100.5018"
                   "&hourly=precipitation_probability,precipitation,rain&timezone=Asia%2FBangkok")
    try:
        w_res = requests.get(weather_url, timeout=5).json()
        hourly = w_res.get("hourly", {})
        times = hourly.get("time", [])[:24]
        precips = hourly.get("precipitation", [])[:24]
        probs = hourly.get("precipitation_probability", [])[:24]
        weather_data = [{"เวลา": t.split("T")[-1], "ปริมาณฝน (มม.)": p, "โอกาสฝนตก (%)": pr}
                        for t, p, pr in zip(times, precips, probs)]
        st.dataframe(weather_data, use_container_width=True)
    except Exception:
        st.error("⚠️ ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้")

with tab3:
    st.subheader("📊 แผนที่รายงานสถานการณ์น้ำท่วมสด (Floodboard)")
    components.iframe("https://floodboard.org/embed", height=500, scrolling=True)

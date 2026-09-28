import datetime

TRAFFY_API = "https://publicapi.traffy.in.th/share/teamchadchart/search"
FLOOD_KEYWORDS = ("ท่วม", "น้ำขัง", "น้ำรอระบาย", "ระบายน้ำ")

@st.cache_data(ttl=600, show_spinner=False)
def load_flood_reports_traffy(hours_back=24, limit=1000):
    """ดึงเรื่องร้องเรียนน้ำท่วมจาก Traffy Fondue (มีพิกัดมาให้แล้ว ไม่ต้อง geocode)"""
    reports = []
    try:
        for offset in (0, 1000, 2000):
            resp = requests.get(TRAFFY_API,
                                params={"limit": limit, "offset": offset},
                                timeout=30)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results") or data.get("features") or []
            if not items:
                break

            for it in items:
                props = it.get("properties", it)
                text = " ".join(str(props.get(k, "")) for k in
                                ("description", "comment", "type", "problem_type_abdul", "address"))
                if not any(kw in text for kw in FLOOD_KEYWORDS):
                    continue

                coords = props.get("coords") or (it.get("geometry") or {}).get("coordinates")
                if not coords or len(coords) < 2:
                    continue
                lon, lat = float(coords[0]), float(coords[1])
                if not (13.4 < lat < 14.2 and 100.2 < lon < 101.0):
                    continue  # กรองเฉพาะเขต กทม./ปริมณฑล

                desc = str(props.get("description") or props.get("comment") or "น้ำท่วมขัง")[:120]
                district = str(props.get("district") or props.get("subdistrict") or "")
                reports.append({
                    "name": f"{props.get('address', 'จุดแจ้งน้ำท่วม')} ({district})"[:90],
                    "lat": lat,
                    "lon": lon,
                    "status": desc,
                    "level": "danger",
                })
        return reports
    except Exception:
        return []


def load_flood_reports_combined():
    """ลอง Traffy ก่อน ถ้าไม่ได้ค่อยกลับไปใช้ชีต/ข้อมูลสำรอง"""
    traffy = load_flood_reports_traffy()
    if traffy:
        return traffy, {"source": "traffy", "total": len(traffy), "skipped": 0, "error": None}
    return load_flood_reports()

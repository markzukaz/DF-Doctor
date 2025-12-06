import streamlit as st
import pandas as pd
import json
import datetime as dt
import pytz
from io import BytesIO

# =========================
# Global Config
# =========================
st.set_page_config(page_title="Worldmed Tools – Doctor & Refer Stats", layout="wide")

st.title("🩺 Worldmed Monthly Tools")
st.markdown("เลือกเมนูจาก Sidebar ทางซ้ายเพื่อใช้งานแต่ละโปรแกรมได้เลย")

# =========================
# Common Helpers
# =========================

def parse_time_to_bangkok_iso_str(t: str) -> str:
    """
    สำหรับ time ที่เป็น ISO string เช่น 2025-12-04T17:45:55.707Z
    แปลงจาก UTC -> Asia/Bangkok แล้ว format DD/MM/YYYY HH:mm
    """
    try:
        utc_dt = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
        bkk_tz = pytz.timezone("Asia/Bangkok")
        return utc_dt.astimezone(bkk_tz).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ""

def norm_list(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, list):
        return v
    return [v]

def safe_sheet_name(name: str) -> str:
    if name is None:
        return "Unknown"
    safe = str(name)[:31]
    for ch in ['\\', '/', '*', '?', ':', '[', ']']:
        safe = safe.replace(ch, '-')
    return safe or "Unknown"

# =========================
# PAGE 1 – Doctor Monthly Stats
# (จาก doctor_stats_app.py)
# =========================

def page_doctor_stats():
    st.header("📊 Doctor Monthly Stats – CSV → Excel Converter")

    st.write("อัปโหลดไฟล์ CSV ที่มีคอลัมน์ `treatments` เพื่อแปลงเป็น Excel แยกตามแพทย์ (practice)")

    uploaded = st.file_uploader("Upload CSV for Doctor Monthly Stats", type=["csv"], key="stats_uploader")

    if not uploaded:
        st.info("⬆️ กรุณาอัปโหลดไฟล์ CSV ด้านบน")
        return

    df = pd.read_csv(uploaded)

    st.subheader("👀 Preview – 5 แถวแรก")
    st.dataframe(df.head())

    rows = []

    for _, row in df.iterrows():
        raw = row.get("treatments")
        if pd.isna(raw):
            continue

        try:
            treatments = json.loads(raw)
        except Exception:
            continue

        for t in treatments:
            practice_list = norm_list(t.get("practice"))
            order_list = norm_list(t.get("order"))
            doctor_asst_list = norm_list(t.get("doctor_asst"))

            # นับจำนวนคนที่อยู่ใน practice ถ้าไม่มีให้ใช้ order แทน
            practice_count = len(practice_list) if practice_list else len(order_list)

            # รายชื่อหมอในแต่ละเคส (ใช้ practice ถ้าไม่มีใช้ order)
            doctor_list = practice_list if practice_list else order_list or [None]

            time_fmt = parse_time_to_bangkok_iso_str(str(row.get("time", "")))

            for doc in doctor_list:
                rows.append({
                    "time": time_fmt,
                    "HN": row.get("HN", ""),
                    "patientTitle": row.get("patientTitle", ""),
                    "patientName": row.get("patientName", ""),
                    "nationality": row.get("nationality", ""),
                    "treatment": t.get("treatment", ""),
                    "area": t.get("area", ""),
                    "unit": t.get("unit", ""),
                    "practice": doc,
                    "practice_count": practice_count,
                    "order_raw": ",".join(order_list),
                    "doctor_asst_raw": ",".join(doctor_asst_list),
                })

    if not rows:
        st.error("ไม่พบข้อมูลจากคอลัมน์ treatments เลย")
        return

    exp = pd.DataFrame(rows)

    st.subheader("📋 Preview – Doctor Stats (10 แถวแรก)")
    st.dataframe(exp.head(10))

    # Export to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        exp.to_excel(writer, "All", index=False)
        for doc in sorted(exp["practice"].dropna().unique()):
            sheet = safe_sheet_name(doc)
            exp[exp["practice"] == doc].to_excel(writer, sheet_name=sheet, index=False)

    output.seek(0)

    st.success("แปลงสำเร็จ! ดาวน์โหลดไฟล์ด้านล่าง")
    st.download_button(
        label="⬇ Download Doctor Stats Excel",
        data=output.getvalue(),
        file_name="doctor_stats.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_stats_excel"
    )

# =========================
# PAGE 2 – Doctor Round / Discharge
# (จาก app.py – Doctor Round/Discharge Exporter)
# =========================

def convert_time_round(val):
    if pd.isna(val):
        return None

    # ถ้าเป็น datetime อยู่แล้ว
    if isinstance(val, (dt.datetime, pd.Timestamp)):
        try:
            dt_utc = pd.to_datetime(val).tz_localize("UTC")
            dt_bkk = dt_utc.tz_convert("Asia/Bangkok")
            return dt_bkk.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return val.strftime("%d/%m/%Y %H:%M")

    # ถ้าเป็น string → parse
    try:
        dt_utc = pd.to_datetime(val, utc=True)
        dt_bkk = dt_utc.tz_convert("Asia/Bangkok")
        return dt_bkk.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return val

def build_all_df_round(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for idx, row in df.iterrows():
        treatments_raw = row.get("treatments")
        # parse JSON
        if isinstance(treatments_raw, str):
            try:
                t_list = json.loads(treatments_raw)
            except Exception:
                t_list = []
        else:
            t_list = []

        doctors = []
        for t in t_list or []:
            ord_list = t.get("order") or []
            for d in ord_list:
                if d and d not in doctors:
                    doctors.append(d)

        # ถ้าไม่มีหมอใน order → เก็บใน ALL แบบ order = None, order_count = 0
        if not doctors:
            doctors = [None]
            order_count = 0
        else:
            order_count = len(doctors)

        for d in doctors:
            new_row = {
                "time": row.get("time"),
                "ipd_status": row.get("ipd_status"),
                "patientTitle": row.get("patientTitle"),
                "patientName": row.get("patientName"),
                "room": row.get("room"),
                "nationality": row.get("nationality"),
                "order": d,
                "order_count": order_count,
            }
            rows.append(new_row)

    all_df = pd.DataFrame(rows)
    # แปลง time format → GMT+7
    all_df["time"] = all_df["time"].apply(convert_time_round)
    return all_df

def page_doctor_round():
    st.header("🏨 Doctor Round / Discharge Exporter")

    st.markdown("""
อัปโหลดไฟล์ **CSV** ที่มีคอลัมน์ `treatments`  
ระบบจะแตกชื่อหมอจาก `order` แล้วทำ Excel แยกชีตตามหมอ
""")

    uploaded_file = st.file_uploader("📥 เลือกไฟล์ CSV สำหรับ Doctor Round", type=["csv"], key="round_uploader")

    if uploaded_file is None:
        st.info("⬆️ กรุณาอัปโหลดไฟล์ CSV ด้านบนก่อน")
        return

    # อ่าน CSV
    try:
        df = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        df = pd.read_csv(uploaded_file, encoding="utf-8-sig")

    st.subheader("👀 Preview ข้อมูลจาก CSV (5 แถวแรก)")
    st.dataframe(df.head())

    # ตรวจว่ามีคอลัมน์ที่ต้องใช้ไหม
    required_cols = ["time", "ipd_status", "patientTitle", "patientName",
                     "room", "nationality", "treatments"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"❌ ขาดคอลัมน์จำเป็นใน CSV: {missing}")
        return

    all_df = build_all_df_round(df)

    st.subheader("📋 Preview ตาราง ALL (หลังประมวลผล) - 10 แถวแรก")
    st.dataframe(all_df.head(10))

    # list รายชื่อหมอ
    doctors = sorted([d for d in all_df["order"].dropna().unique()])
    st.markdown(f"👨‍⚕️ พบแพทย์ทั้งหมด: **{len(doctors)} คน**")
    st.write(doctors)

    # สร้าง Excel ในหน่วยความจำ
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        all_df.to_excel(writer, sheet_name="ALL", index=False)
        for doctor in doctors:
            doc_df = all_df[all_df["order"] == doctor]
            sheet_name = safe_sheet_name(doctor)
            doc_df.to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)

    st.subheader("📤 ดาวน์โหลดไฟล์ Excel")
    st.download_button(
        label="⬇️ Download Excel (ALL + แยกตามชื่อหมอ)",
        data=buffer,
        file_name="Doctor_round_discharge_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_round_excel"
    )

# =========================
# PAGE 3 – Refer Summary
# (จาก refer.py)
# =========================

def parse_json_list_str(s):
    """แปลง string แบบ '["NAT","NICE"]' -> 'NAT,NICE'"""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    if isinstance(s, list):
        # เผื่อมีกรณีอ่านมาเป็น list อยู่แล้ว
        return ",".join(map(str, s))
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return ",".join(map(str, data))
        return str(data)
    except Exception:
        # ถ้า parse ไม่ได้ก็ส่งดิบ ๆ กลับไป
        return str(s)

def format_time_gmt7_series(series):
    """
    แปลง ISO string -> GMT+7 แล้ว format เป็น DD/MM/YYYY HH:mm
    เช่น 2025-12-01T19:01:55.634Z -> 02/12/2025 02:01 (ถ้าตีว่าเดิมเป็น UTC)
    """
    dt_ser = pd.to_datetime(series, utc=True, errors="coerce")
    dt_ser = dt_ser + pd.Timedelta(hours=7)
    return dt_ser.dt.strftime("%d/%m/%Y %H:%M")

def expand_refer_rows(df, only_refer=True):
    """
    แตก treatments JSON เป็น 1 row ต่อ 1 treatment ต่อ 1 doctor (practice/order)
    แล้วดึง field refer ที่ต้องใช้ออกมาด้วย
    """
    rows = []
    for _, row in df.iterrows():
        raw_treat = row.get("treatments")
        if pd.isna(raw_treat):
            continue
        try:
            treatments = json.loads(raw_treat)
        except Exception:
            continue

        for t in treatments:
            treatment_name = t.get("treatment", "")

            # ถ้าเลือกให้เอาเฉพาะ refer
            if only_refer and "refer" not in treatment_name.lower():
                continue

            practice_list = norm_list(t.get("practice"))
            order_list = norm_list(t.get("order"))
            doctor_list = practice_list if practice_list else order_list or [None]

            # จำนวนคนใน practice (ถ้า practice ว่าง ใช้จำนวนจาก order)
            practice_count = len(practice_list) if practice_list else len(order_list) if order_list else 0

            # common fields
            time_str = row.get("time", "")
            hn = row.get("HN", "")
            patient_title = row.get("patientTitle", "")
            patient_name = row.get("patientName", "")
            nationality = row.get("nationality", "")
            refer_to = row.get("referTo", "")
            type_of_boat = row.get("typeOfBoat", "")
            shift_val = row.get("shift", "")
            on_duty_raw = row.get("onDuty", "")
            on_call_raw = row.get("onCall", "")

            on_duty = parse_json_list_str(on_duty_raw)
            on_call = parse_json_list_str(on_call_raw)

            order_raw = ",".join(map(str, order_list)) if order_list else ""

            for doc in doctor_list:
                rows.append({
                    "time": time_str,
                    "HN": hn,
                    "patientTitle": patient_title,
                    "patientName": patient_name,
                    "nationality": nationality,
                    "treatment": treatment_name,
                    "practice": doc,
                    "practice_count": practice_count,
                    "order": order_raw,
                    "referTo": refer_to,
                    "typeOfBoat": type_of_boat,
                    "Shift": shift_val,
                    "onDuty": on_duty,
                    "onCall": on_call,
                })

    result = pd.DataFrame(rows)
    if not result.empty:
        result["time"] = format_time_gmt7_series(result["time"])
    return result

def to_excel_with_sheets(df: pd.DataFrame, file_name="refer_summary.xlsx"):
    """
    แปลง DataFrame เป็นไฟล์ Excel แบบมีชีต All + แยกตาม practice
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # ชีต All
        df.to_excel(writer, sheet_name="All", index=False)

        # แยกชีตตาม practice
        practices = sorted(df["practice"].dropna().unique())
        for p in practices:
            sub_df = df[df["practice"] == p]
            safe_name = safe_sheet_name(p)
            sub_df.to_excel(writer, sheet_name=safe_name, index=False)

    output.seek(0)
    return output, file_name

def page_refer_summary():
    st.header("📦 Refer Summary (Practice-based)")

    st.markdown("""
อัปโหลดไฟล์ **Patient_summary_*.csv** (รูปแบบเดียวกับระบบปัจจุบัน)  
ระบบจะแตก `treatments` และสรุปเฉพาะเคสที่เป็น Refer ให้ พร้อม field:
- time (GMT+7, แสดง `DD/MM/YYYY HH:mm`)
- HN, patientTitle, patientName, nationality  
- treatment, practice, practice_count, order  
- referTo, typeOfBoat, Shift, onDuty, onCall  
""")

    uploaded = st.file_uploader("อัปโหลดไฟล์ Patient_summary CSV", type=["csv"], key="refer_uploader")

    only_refer = st.checkbox("เอาเฉพาะ treatment ที่เป็น Refer เท่านั้น", value=True)

    if uploaded is None:
        st.info("โปรดอัปโหลดไฟล์ CSV ทางด้านบนก่อนครับ 🙂")
        return

    # อ่านไฟล์
    try:
        df_raw = pd.read_csv(uploaded, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df_raw = pd.read_csv(uploaded, encoding="latin1")

    st.success(f"โหลดข้อมูลสำเร็จ มี {len(df_raw):,} แถว (raw)")

    # แตก refer rows
    df_refer = expand_refer_rows(df_raw, only_refer=only_refer)

    if df_refer.empty:
        st.warning("ไม่พบข้อมูล refer ตามเงื่อนไขในไฟล์นี้")
        return

    st.info(f"ได้ refer rows ทั้งหมด {len(df_refer):,} แถว")

    # เลือก filter ตาม practice
    all_practices = sorted(df_refer["practice"].dropna().unique())
    selected_practices = st.multiselect(
        "เลือก Practice ที่ต้องการดู (เว้นว่าง = ดูทั้งหมด)",
        options=all_practices,
        default=None,
        key="refer_practice_multi"
    )

    if selected_practices:
        df_view = df_refer[df_refer["practice"].isin(selected_practices)]
    else:
        df_view = df_refer

    st.write("ตัวอย่างข้อมูล (top 200 rows):")
    st.dataframe(df_view.head(200))

    # ดาวน์โหลดเป็น Excel
    excel_buffer, fname = to_excel_with_sheets(df_view, file_name="refer_summary.xlsx")
    st.download_button(
        label="⬇️ ดาวน์โหลด Refer Summary (Excel)",
        data=excel_buffer,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_refer_excel"
    )

# =========================
# SIDEBAR NAVIGATION
# =========================

st.sidebar.title("🧭 เมนู")
page = st.sidebar.radio(
    "เลือกโปรแกรม",
    ["Doctor Stats", "Doctor Round", "Refer Summary"]
)

if page == "Doctor Stats":
    page_doctor_stats()
elif page == "Doctor Round":
    page_doctor_round()
elif page == "Refer Summary":
    page_refer_summary()

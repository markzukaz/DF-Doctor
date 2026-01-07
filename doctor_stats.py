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
def safe_json_loads(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return None

def join_list(v, sep=","):
    if v is None:
        return ""
    if isinstance(v, list):
        return sep.join([str(x) for x in v if x is not None and str(x).strip() != ""])
    return str(v)

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
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
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
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
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
# ---------- Time helpers ----------
def format_time_gmt7(val):
    """
    รองรับทั้ง ISO string, timestamp, datetime
    output: DD/MM/YYYY HH:mm (Asia/Bangkok)
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        ts = pd.to_datetime(val, utc=True, errors="coerce")
        if pd.isna(ts):
            # เผื่อเป็น datetime ที่ไม่มี tz
            ts = pd.to_datetime(val, errors="coerce")
            if pd.isna(ts):
                return str(val)
            # assume local? (fallback)
            return ts.strftime("%d/%m/%Y %H:%M")
        ts = ts.tz_convert("Asia/Bangkok")
        return ts.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(val)

def safe_json_loads(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return None

def norm_list(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, list):
        return v
    return [v]

def join_list(v, sep=","):
    if v is None:
        return ""
    if isinstance(v, list):
        return sep.join([str(x) for x in v if x is not None and str(x).strip() != ""])
    return str(v)
# =========================
# PAGE 4 – Patient Summary Clean Export
# 
# =========================
def beautify_patient_summary(
    df: pd.DataFrame,
    diag_top_n: int = 10,     # top N diagnosis columns
    treat_top_n: int = 6      # top N treatments columns
) -> pd.DataFrame:
    """
    - เพิ่ม time (formatted)
    - diagnosis: ทำทั้ง join string + แตกคอลัมน์แบบ dynamic topN
    - treatments: ทำทั้ง join string + แตกคอลัมน์แบบ dynamic topN
    """
    base_cols = [
        "time",
        "HN", "VN", "visit_type", "patientTitle", "patientName", "patientAge", "nationality",
        "branch", "insurance_name", "assist_insurance", "concessionType",
        "diagnosis", "medLog", "treatments", "payment_status", "billLog", "rejects", "retry", "note"
    ]
    keep = [c for c in base_cols if c in df.columns]
    out = df[keep].copy()

    # ---------- time ----------
    if "time" in out.columns:
        out["time_fmt"] = out["time"].apply(format_time_gmt7)
    else:
        out["time_fmt"] = ""

    # เตรียม list เก็บค่าที่จะใส่กลับเข้า out ทีเดียว
    diag_count = []
    diag_join = []
    diag_codes_join, diag_titles_join, diag_cats_join = [], [], []

    treat_count = []
    treat_join = []
    treat_names_join, treat_areas_join, treat_units_join = [], [], []
    treat_order_join, treat_practice_join, treat_asst_join = [], [], []

    # ---------- payment_status (ของเดิมยังใช้ได้) ----------
    pay_status = []
    pay_invoice_id = []
    pay_total_invoiced = []
    pay_case_type = []
    pay_reason_not_insurance = []

    # ---------- rejects ----------
    has_reject = []
    reject_type = []
    reject_reason = []
    reject_problem = []

    # ---------- logs ----------
    medlog_list = []
    billlog_list = []
    retry_list = []

    # เก็บ diagnosis/treatment สำหรับทำ dynamic columns
    diags_all_rows = []
    treats_all_rows = []

    def first_of(v):
        if isinstance(v, list) and v:
            return v[0]
        return v

    for _, r in out.iterrows():
        # ===== diagnosis =====
        diag = safe_json_loads(r.get("diagnosis"))
        diag_items = [x for x in diag if isinstance(x, dict)] if isinstance(diag, list) else []
        diags_all_rows.append(diag_items)

        diag_count.append(len(diag_items))

        # ทำ join string แบบอ่านง่าย + split ได้
        diag_parts = []
        codes, titles, cats = [], [], []
        for x in diag_items:
            code = str(x.get("code", "") or "").strip()
            title = str(x.get("title", "") or "").strip()
            cat = str(x.get("categoryLabel", "") or "").strip()

            if code: codes.append(code)
            if title: titles.append(title)
            if cat: cats.append(cat)

            # สไตล์เดียวกับ vue: Code:..., Title:...
            if code or title or cat:
                seg = []
                if code:  seg.append(f"Code:{code}")
                if title: seg.append(f"Title:{title}")
                if cat:   seg.append(f"Cat:{cat}")
                diag_parts.append(", ".join(seg))

        diag_join.append(" | ".join(diag_parts))
        diag_codes_join.append(",".join(codes))
        diag_titles_join.append(",".join(titles))
        diag_cats_join.append(",".join(cats))

        # ===== treatments =====
        tr = safe_json_loads(r.get("treatments"))
        tr_items = [x for x in tr if isinstance(x, dict)] if isinstance(tr, list) else []
        treats_all_rows.append(tr_items)

        treat_count.append(len(tr_items))

        tr_parts = []
        names, areas, units = [], [], []
        orders_all, practices_all, assts_all = [], [], []

        for t in tr_items:
            tname = str(t.get("treatment", "") or "").strip()
            area  = str(t.get("area", "") or "").strip()
            unit  = str(t.get("unit", "") or "").strip()

            if tname: names.append(tname)
            if area:  areas.append(area)
            if unit:  units.append(unit)

            ords  = norm_list(t.get("order"))
            pracs = norm_list(t.get("practice"))
            assts = norm_list(t.get("doctor_asst"))

            # รวมเป็น string ราย treatment
            ord_s  = join_list(ords)
            prac_s = join_list(pracs)
            asst_s = join_list(assts)

            if ord_s:  orders_all.append(ord_s)
            if prac_s: practices_all.append(prac_s)
            if asst_s: assts_all.append(asst_s)

            # join แบบคล้าย vue (เอาไป split ด้วย | ได้)
            seg = [
                f"Treatment:{tname}",
                f"Area:{area}",
                f"Unit:{unit}",
                f"Order:{ord_s}",
                f"Practice:{prac_s}",
                f"Asst:{asst_s}",
            ]
            tr_parts.append(", ".join([s for s in seg if not s.endswith(":")]))

        treat_join.append(" | ".join([p for p in tr_parts if p.strip()]))
        treat_names_join.append(",".join(names))
        treat_areas_join.append(",".join(areas))
        treat_units_join.append(",".join(units))
        treat_order_join.append(" | ".join(orders_all))
        treat_practice_join.append(" | ".join(practices_all))
        treat_asst_join.append(" | ".join(assts_all))

        # ===== payment_status =====
        ps = safe_json_loads(r.get("payment_status"))
        ps0 = ps[0] if isinstance(ps, list) and ps and isinstance(ps[0], dict) else {}

        pay_status.append(str(first_of(ps0.get("status")) or ""))
        pay_invoice_id.append(str(first_of(ps0.get("invoice_id")) or ""))
        pay_total_invoiced.append(first_of(ps0.get("total_invoiced")))
        pay_case_type.append(str(first_of(ps0.get("case_type")) or ""))
        pay_reason_not_insurance.append(str(first_of(ps0.get("reasonNotInsurance")) or ""))

        # ===== rejects =====
        rej = safe_json_loads(r.get("rejects"))
        rej0 = rej[0] if isinstance(rej, list) and rej and isinstance(rej[0], dict) else {}
        r_type = str(rej0.get("reject", "") or "").strip()
        r_reason = str(rej0.get("reason", "") or "").strip()
        r_prob = str(rej0.get("problem", "") or "").strip()

        has_reject.append(bool(r_type or r_reason or r_prob))
        reject_type.append(r_type)
        reject_reason.append(r_reason)
        reject_problem.append(r_prob)

        # ===== logs =====
        ml = safe_json_loads(r.get("medLog"))
        bl = safe_json_loads(r.get("billLog"))
        rt = safe_json_loads(r.get("retry"))

        ml_list = ml if isinstance(ml, list) else []
        bl_list = bl if isinstance(bl, list) else []
        rt_list = rt if isinstance(rt, list) else []

        medlog_list.append(join_list(ml_list))
        billlog_list.append(join_list(bl_list))
        retry_list.append(join_list(rt_list))

    # ใส่คอลัมน์ join/summarize
    out["diag_count"] = diag_count
    out["diag_join"] = diag_join
    out["diag_codes"] = diag_codes_join
    out["diag_titles"] = diag_titles_join
    out["diag_categories"] = diag_cats_join

    out["treat_count"] = treat_count
    out["treat_join"] = treat_join
    out["treat_names"] = treat_names_join
    out["treat_areas"] = treat_areas_join
    out["treat_units"] = treat_units_join
    out["treat_orders"] = treat_order_join
    out["treat_practices"] = treat_practice_join
    out["treat_assts"] = treat_asst_join

    out["pay_status"] = pay_status
    out["pay_invoice_id"] = pay_invoice_id
    out["pay_total_invoiced"] = pay_total_invoiced
    out["pay_case_type"] = pay_case_type
    out["pay_reason_not_insurance"] = pay_reason_not_insurance

    out["has_reject"] = has_reject
    out["reject_type"] = reject_type
    out["reject_reason"] = reject_reason
    out["reject_problem"] = reject_problem

    out["medLog_list"] = medlog_list
    out["billLog_list"] = billlog_list
    out["retry_list"] = retry_list

    # ---------- Dynamic TOP-N columns ----------
    # diagnosis: diag_code_1..N, diag_title_1..N, diag_category_1..N
    n_diag = min(diag_top_n, max([len(x) for x in diags_all_rows] or [0]))
    for i in range(n_diag):
        out[f"diag_code_{i+1}"] = [
            str(items[i].get("code", "") or "").strip() if i < len(items) else ""
            for items in diags_all_rows
        ]
        out[f"diag_title_{i+1}"] = [
            str(items[i].get("title", "") or "").strip() if i < len(items) else ""
            for items in diags_all_rows
        ]
        out[f"diag_category_{i+1}"] = [
            str(items[i].get("categoryLabel", "") or "").strip() if i < len(items) else ""
            for items in diags_all_rows
        ]

    # treatments: treat_name_1..N, treat_area_1..N, treat_unit_1..N, treat_order_1..N, treat_practice_1..N
    n_treat = min(treat_top_n, max([len(x) for x in treats_all_rows] or [0]))
    for i in range(n_treat):
        out[f"treat_name_{i+1}"] = [
            str(items[i].get("treatment", "") or "").strip() if i < len(items) else ""
            for items in treats_all_rows
        ]
        out[f"treat_area_{i+1}"] = [
            str(items[i].get("area", "") or "").strip() if i < len(items) else ""
            for items in treats_all_rows
        ]
        out[f"treat_unit_{i+1}"] = [
            str(items[i].get("unit", "") or "").strip() if i < len(items) else ""
            for items in treats_all_rows
        ]
        out[f"treat_order_{i+1}"] = [
            join_list(norm_list(items[i].get("order"))) if i < len(items) else ""
            for items in treats_all_rows
        ]
        out[f"treat_practice_{i+1}"] = [
            join_list(norm_list(items[i].get("practice"))) if i < len(items) else ""
            for items in treats_all_rows
        ]
        out[f"treat_asst_{i+1}"] = [
            join_list(norm_list(items[i].get("doctor_asst"))) if i < len(items) else ""
            for items in treats_all_rows
        ]

    return out
def page_patient_summary_clean_export():
    st.header("🧹 Patient Summary Clean Export – CSV → Excel (Filter-ready)")

    st.write("""
อัปโหลดไฟล์ Patient_summary CSV  
ระบบจะแตกคอลัมน์ JSON/array (diagnosis, treatments, payment_status, rejects) ให้เป็นคอลัมน์ใหม่เพื่อ filter ง่ายใน Excel
""")

    uploaded = st.file_uploader("Upload Patient_summary CSV", type=["csv"], key="ps_clean_uploader")
    if uploaded is None:
        st.info("⬆️ กรุณาอัปโหลดไฟล์ CSV ด้านบน")
        return

    # อ่านไฟล์
    try:
        df_raw = pd.read_csv(uploaded, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df_raw = pd.read_csv(uploaded, encoding="latin1")

    st.subheader("👀 Preview – Raw (5 แถวแรก)")
    st.dataframe(df_raw.head())

    df_clean = beautify_patient_summary(df_raw)

    st.subheader("✨ Preview – Clean (10 แถวแรก)")
    st.dataframe(df_clean.head(10))

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_clean.to_excel(writer, sheet_name="Clean", index=False)

    output.seek(0)
    st.download_button(
        label="⬇ Download Patient Summary Clean Excel",
        data=output.getvalue(),
        file_name="patient_summary_clean.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_ps_clean_excel"
    )

# =========================
# SIDEBAR NAVIGATION
# =========================

st.sidebar.title("🧭 เมนู")
page = st.sidebar.radio(
    "เลือกโปรแกรม",
    ["Doctor Stats", "Doctor Round", "Refer Summary","Patient Summary Clean Export"]
)

if page == "Doctor Stats":
    page_doctor_stats()
elif page == "Doctor Round":
    page_doctor_round()
elif page == "Refer Summary":
    page_refer_summary()
elif page == "Patient Summary Clean Export":
    page_patient_summary_clean_export()

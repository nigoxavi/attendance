"""Sunday Church Class Attendance Monitoring System — CSV edition."""
import io
import hmac
import os
import threading
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String

load_dotenv()
st.set_page_config(page_title="Sunday Class Attendance", page_icon="⛪", layout="wide")

APP_DIR = Path(__file__).resolve().parent
CSV_DIR = Path(os.getenv("CSV_DATA_DIRECTORY", "data"))
if not CSV_DIR.is_absolute():
    CSV_DIR = APP_DIR / CSV_DIR
CSV_DIR.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()  # protects writes in one Streamlit process
SECTION_OPTIONS = ["Section A", "Section B", "Section C", "Section D"]
SERVICE_OPTIONS = ["First Service", "Second Service", "Third Service"]
CHURCH_NAME = "Shaaron Pentecostal Church"
TABLES = {
    "services": ["id", "name", "sort_order"],
    "teachers": ["id", "name", "service_id", "phone", "active"],
    "classes": ["id", "name", "category"],
    "students": ["id", "name", "age", "gender", "mobile_number", "area", "father_name", "mother_name", "class_id", "section", "teacher_id", "service_id", "address", "active", "created_at"],
    "attendance": ["id", "attendance_date", "student_id", "service_id", "teacher_id", "status", "notes", "created_at", "updated_at"],
    "marks": ["id", "exam_date", "exam_name", "student_id", "service_id", "teacher_id", "mark", "maximum_mark", "created_at", "updated_at"],
}


def csv_path(table):
    return CSV_DIR / f"{table}.csv"


def read(table):
    """Read a CSV and always return the complete current table schema."""
    path = csv_path(table)
    if not path.exists():
        return pd.DataFrame(columns=TABLES[table])

    try:
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=TABLES[table])

    # Important: older students.csv files may not contain "section".
    # reindex() adds every missing column, including section, with "".
    data = data.reindex(columns=TABLES[table], fill_value="")
    for column in TABLES[table]:
        if column not in data.columns:
            data[column] = ""
    return data[TABLES[table]].fillna("")


def write(table, data):
    """Atomically replace a CSV, so an interrupted save never leaves a half-written file."""
    clean = data.reindex(columns=TABLES[table], fill_value="").fillna("")
    temporary = csv_path(table).with_suffix(".tmp")
    with LOCK:
        clean.to_csv(temporary, index=False)
        temporary.replace(csv_path(table))


def next_id(table):
    values = pd.to_numeric(read(table)["id"], errors="coerce").dropna()
    return int(values.max()) + 1 if not values.empty else 1


def add_row(table, values):
    data = read(table)
    row = {column: "" for column in TABLES[table]}
    row.update(values); row["id"] = str(next_id(table))
    write(table, pd.concat([data, pd.DataFrame([row])], ignore_index=True))
    return row["id"]


def update_rows(table, mask, changes):
    data = read(table)
    for key, value in changes.items(): data.loc[mask(data), key] = str(value)
    write(table, data)


def initialize():
    for table in TABLES:
        if not csv_path(table).exists(): write(table, pd.DataFrame(columns=TABLES[table]))
    if os.getenv("SEED_DEMO_DATA", "true").lower() == "true" and read("services").empty:
        seed_data()


def seed_data():
    services = [("First Service (8:00 AM)", 1), ("Second Service (10:00 AM)", 2), ("Third Service (5:00 PM)", 3)]
    for name, order in services: add_row("services", {"name": name, "sort_order": order})
    for name, category in [("Beginners", "Beginners"), ("Primary 1", "Primary"), ("Primary 2", "Primary")]: add_row("classes", {"name": name, "category": category})
    service_ids = {r.name: r.id for r in read("services").itertuples()}
    for name, service, phone in [("Sister Mary", services[0][0], "9000000001"), ("Brother John", services[0][0], "9000000002"), ("Sister Ruth", services[1][0], "9000000003"), ("Brother David", services[2][0], "9000000004")]: add_row("teachers", {"name": name, "service_id": service_ids[service], "phone": phone, "active": "1"})
    teacher_ids = {r.name: r.id for r in read("teachers").itertuples()}; class_ids = {r.name: r.id for r in read("classes").itertuples()}
    demo = [("Aarav Joseph",8,"Boy","9000000101","Central","Joseph","Anita","Primary 1","A","Sister Mary",services[0][0],"12 Grace Street"), ("Anna Paul",7,"Girl","9000000102","North","Paul","Lilly","Primary 1","A","Sister Mary",services[0][0],"4 Faith Road"), ("Daniel Thomas",5,"Boy","9000000103","East","Thomas","Sara","Beginners","B","Brother John",services[0][0],"8 Hope Lane"), ("Esther Samuel",9,"Girl","9000000104","West","Samuel","Grace","Primary 2","A","Sister Ruth",services[1][0],"23 Peace Avenue"), ("Joel Mathew",10,"Boy","9000000105","South","Mathew","Reena","Primary 2","B","Brother David",services[2][0],"16 Joy Street")]
    for n, age, gender, mobile, area, father, mother, cl, section, teacher, service, address in demo:
        add_row("students", {"name": n, "age": age, "gender": gender, "mobile_number": mobile, "area": area, "father_name": father, "mother_name": mother, "class_id": class_ids[cl], "section": section, "teacher_id": teacher_ids[teacher], "service_id": service_ids[service], "address": address, "active": "1", "created_at": str(date.today())})


def services():
    data = read("services"); data["sort_order"] = pd.to_numeric(data.sort_order, errors="coerce").fillna(99)
    return data.sort_values(["sort_order", "name"])


def active_teachers(service_id=0):
    data = read("teachers"); data = data[data.active != "0"]
    return data if not service_id else data[data.service_id == str(service_id)]


def select_service(label, key, all_option=False):
    data = services(); ids = data.id.tolist(); labels = dict(zip(data.id, data.name))
    if all_option: ids, labels = ["0"] + ids, {"0": "All services", **labels}
    return st.selectbox(label, ids, format_func=lambda item: labels[item], key=key)


def select_teacher(service_id, label, key, all_option=False):
    data = active_teachers(0 if service_id == "0" else service_id); ids = data.id.tolist(); labels = dict(zip(data.id, data.name))
    if all_option: ids, labels = ["0"] + ids, {"0": "All teachers", **labels}
    if not ids: st.warning("Add a teacher for this service first."); return None
    return st.selectbox(label, ids, format_func=lambda item: labels[item], key=key)


def church_header():
    st.markdown(f"<h2 style='text-align:center; margin-bottom:0;'>⛪ {CHURCH_NAME}</h2><p style='text-align:center; color:#6b7280; margin-top:0;'>Sunday Church Class Attendance Monitoring System</p>", unsafe_allow_html=True)
    st.divider()


def student_view():
    """Return students with teacher, service and class names.

    The section column is explicitly preserved so older CSV files cannot
    cause KeyError: 'section'.
    """
    students = read("students").copy()
    if "section" not in students.columns:
        students["section"] = ""

    teachers = read("teachers").rename(
        columns={"id": "teacher_id", "name": "teacher_name"}
    )
    svcs = read("services").rename(
        columns={"id": "service_id", "name": "service_name"}
    )
    classes = read("classes").rename(
        columns={"id": "class_id", "name": "class_name"}
    )

    result = (
        students
        .merge(teachers[["teacher_id", "teacher_name"]], on="teacher_id", how="left")
        .merge(svcs[["service_id", "service_name"]], on="service_id", how="left")
        .merge(classes[["class_id", "class_name"]], on="class_id", how="left")
    )

    if "section" not in result.columns:
        result["section"] = ""
    result["section"] = result["section"].fillna("").astype(str)

    return result


def student_form(existing=None, form_key="add_student"):
    existing = existing or {}; svc = services()
    service_default = str(existing.get("service_id", svc.id.iloc[0]))
    service_id = st.selectbox("Prayer service *", svc.id.tolist(), index=svc.id.tolist().index(service_default) if service_default in svc.id.tolist() else 0, format_func=lambda i: svc.set_index("id").loc[i, "name"], key=f"{form_key}_service")
    teachers = active_teachers(service_id)
    if teachers.empty: st.warning("Add a teacher for this service in Management."); return
    classes = read("classes"); teacher_default = str(existing.get("teacher_id", teachers.id.iloc[0]))
    with st.form(f"{form_key}_form", clear_on_submit=not bool(existing)):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Student name *", existing.get("name", "")); age = c2.number_input("Age", 0, 25, int(existing.get("age") or 0)); gender = c3.selectbox("Gender", ["", "Boy", "Girl", "Other"], index=["", "Boy", "Girl", "Other"].index(existing.get("gender", "") if existing.get("gender", "") in ["", "Boy", "Girl", "Other"] else ""))
        mobile = c1.text_input("Mobile number", existing.get("mobile_number", "")); area = c2.text_input("Area", existing.get("area", ""))
        saved_section = existing.get("section", "")
        section = c3.selectbox("Section", [""] + SECTION_OPTIONS, index=([""] + SECTION_OPTIONS).index(saved_section) if saved_section in SECTION_OPTIONS else 0)
        father = c1.text_input("Father name", existing.get("father_name", "")); mother = c2.text_input("Mother name", existing.get("mother_name", "")); class_id = c3.selectbox("Class", [""] + classes.id.tolist(), format_func=lambda i: "Not assigned" if not i else classes.set_index("id").loc[i, "name"], index=([""] + classes.id.tolist()).index(str(existing.get("class_id", ""))))
        teacher_id = st.selectbox("Teacher *", teachers.id.tolist(), index=teachers.id.tolist().index(teacher_default) if teacher_default in teachers.id.tolist() else 0, format_func=lambda i: teachers.set_index("id").loc[i, "name"])
        address = st.text_area("Address", existing.get("address", "")); save = st.form_submit_button("Save student", type="primary")
    if save:
        if not name.strip(): st.error("Student name is required."); return
        data = read("students"); duplicate = data[(data.name.str.lower() == name.strip().lower()) & (data.teacher_id == teacher_id) & (data.id != str(existing.get("id", "")))]
        if not duplicate.empty: st.error("This student is already registered under this teacher."); return
        values = {"name": name.strip(), "age": age or "", "gender": gender, "mobile_number": mobile.strip(), "area": area.strip(), "father_name": father.strip(), "mother_name": mother.strip(), "class_id": class_id, "section": section.strip(), "teacher_id": teacher_id, "service_id": service_id, "address": address.strip(), "active": "1", "created_at": existing.get("created_at", str(date.today()))}
        if existing:
            update_rows("students", lambda d: d.id == str(existing["id"]), values)
        else: add_row("students", values)
        st.success("Student saved."); st.rerun()


def dashboard():
    st.title("⛪ Sunday Class Attendance")
    today = str(date.today()); students = read("students"); attendance = read("attendance"); current = attendance[attendance.attendance_date == today]
    active = students[students.active != "0"]; present = (current.status == "Present").sum(); absent = (current.status == "Absent").sum(); recorded = len(current)
    cols = st.columns(4); cols[0].metric("Active students", len(active)); cols[1].metric("Recorded today", recorded); cols[2].metric("Present today", present); cols[3].metric("Attendance rate", f"{present / recorded * 100:.0f}%" if recorded else "—")
    st.subheader("Today: absence by prayer service")
    if current.empty:
        st.info("No attendance has been saved for today yet.")
    else:
        service_names = read("services").rename(columns={"id": "service_id", "name": "Prayer service"})
        by_service = current.groupby("service_id").agg(Recorded=("status", "size"), Present=("status", lambda x: (x == "Present").sum()), Absent=("status", lambda x: (x == "Absent").sum())).reset_index().merge(service_names[["service_id", "Prayer service"]], on="service_id", how="left")
        by_service["Absent %"] = (by_service["Absent"] / by_service["Recorded"] * 100).round(1)
        by_service["Present %"] = (by_service["Present"] / by_service["Recorded"] * 100).round(1)
        st.dataframe(by_service[["Prayer service", "Recorded", "Present", "Absent", "Absent %", "Present %"]], hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(by_service, x="Prayer service", y="Absent", text="Absent %", title="Students absent today by service"), use_container_width=True)
    st.subheader("Overall attendance frequency")
    if attendance.empty:
        st.info("Overall frequency will appear after attendance is recorded.")
    else:
        service_names = read("services").rename(columns={"id": "service_id", "name": "Prayer service"})
        overall = attendance.groupby("service_id").agg(Attendance_records=("status", "size"), Sundays_recorded=("attendance_date", "nunique"), Present=("status", lambda x: (x == "Present").sum()), Absent=("status", lambda x: (x == "Absent").sum())).reset_index().merge(service_names[["service_id", "Prayer service"]], on="service_id", how="left")
        overall["Attendance %"] = (overall.Present / overall.Attendance_records * 100).round(1)
        overall["Absence %"] = (overall.Absent / overall.Attendance_records * 100).round(1)
        st.dataframe(overall[["Prayer service", "Sundays_recorded", "Attendance_records", "Present", "Absent", "Attendance %", "Absence %"]], hide_index=True, use_container_width=True)
    view = attendance_view()
    st.subheader("Recent records"); st.dataframe(view.sort_values("attendance_date", ascending=False).head(12), hide_index=True, use_container_width=True)


def attendance_view():
    att = read("attendance").copy()
    students = student_view().rename(
        columns={"id": "student_id", "name": "student"}
    )
    if "section" not in students.columns:
        students["section"] = ""

    teachers = read("teachers").rename(
        columns={"id": "teacher_id", "name": "teacher"}
    )
    svcs = read("services").rename(
        columns={"id": "service_id", "name": "service"}
    )

    result = (
        att
        .merge(
            students[
                ["student_id", "student", "class_name", "section", "gender", "area"]
            ],
            on="student_id",
            how="left",
        )
        .merge(teachers[["teacher_id", "teacher"]], on="teacher_id", how="left")
        .merge(svcs[["service_id", "service"]], on="service_id", how="left")
    )

    if "section" not in result.columns:
        result["section"] = ""
    result["section"] = result["section"].fillna("").astype(str)
    return result


def build_attendance_pdf(data, start, end):
    """Create a printable, section/service/teacher-wise attendance report."""
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet(); story = []
    story += [Paragraph(CHURCH_NAME, styles["Title"]), Paragraph("Sunday Class Attendance Report", styles["Heading2"]), Paragraph(f"Period: {start} to {end}", styles["Normal"]), Spacer(1, 5 * mm)]
    total = len(data); present = int((data.status == "Present").sum()); absent = int((data.status == "Absent").sum())
    overview = [["Attendance records", "Present", "Absent", "Attendance %", "Absence %"], [str(total), str(present), str(absent), f"{present / total * 100:.1f}%", f"{absent / total * 100:.1f}%"]]
    table = Table(overview, colWidths=[42 * mm] * 5); table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("PADDING", (0, 0), (-1, -1), 6)])); story += [table, Spacer(1, 6 * mm)]
    service = data.groupby("service").agg(Recorded=("status", "size"), Present=("status", lambda x: (x == "Present").sum()), Absent=("status", lambda x: (x == "Absent").sum())).reset_index(); service["Absent %"] = (service.Absent / service.Recorded * 100).round(1)
    story += [Paragraph("Service-wise summary", styles["Heading3"])]
    service_table = [["Prayer service", "Recorded", "Present", "Absent", "Absent %"]] + [[str(row.service), str(row.Recorded), str(row.Present), str(row.Absent), f"{row['Absent %']:.1f}%"] for _, row in service.iterrows()]
    table = Table(service_table, colWidths=[70 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm], repeatRows=1); table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f81bd")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.35, colors.grey), ("ALIGN", (1, 1), (-1, -1), "CENTER"), ("PADDING", (0, 0), (-1, -1), 5)])); story += [table, Spacer(1, 5 * mm)]
    drawing = Drawing(700, 190); chart = VerticalBarChart(); chart.x = 50; chart.y = 35; chart.height = 120; chart.width = 580; chart.data = [service.Absent.tolist()]; chart.categoryAxis.categoryNames = service.service.tolist(); chart.categoryAxis.labels.angle = 20; chart.categoryAxis.labels.fontSize = 7; chart.valueAxis.valueMin = 0; chart.valueAxis.valueStep = 1; chart.bars[0].fillColor = colors.HexColor("#c0504d"); drawing.add(chart); drawing.add(String(50, 168, "Students absent by prayer service", fontSize=11)); story += [drawing, Spacer(1, 4 * mm)]
    if "section" not in data.columns:
        data = data.copy()
        data["section"] = ""
    data["section"] = data["section"].fillna("").astype(str)

    teacher = data.groupby(
        ["service", "teacher", "class_name", "section"],
        dropna=False
    ).agg(
        Recorded=("status", "size"),
        Present=("status", lambda x: (x == "Present").sum()),
        Absent=("status", lambda x: (x == "Absent").sum()),
    ).reset_index()
    teacher["Absent %"] = (teacher.Absent / teacher.Recorded * 100).round(1)
    story += [Paragraph("Service, teacher and section-wise summary", styles["Heading3"])]
    teacher_rows = [["Service", "Teacher", "Class", "Section", "Recorded", "Present", "Absent", "Absent %"]] + [[str(r.service), str(r.teacher), str(r.class_name), str(r.section), str(r.Recorded), str(r.Present), str(r.Absent), f"{r['Absent %']:.1f}%"] for _, r in teacher.iterrows()]
    table = Table(teacher_rows, colWidths=[45 * mm, 42 * mm, 30 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm, 24 * mm], repeatRows=1); table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f81bd")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7), ("PADDING", (0, 0), (-1, -1), 4)])); story += [table, Spacer(1, 5 * mm)]
    story += [Paragraph("Detailed attendance", styles["Heading3"])]
    detailed = data.sort_values(["attendance_date", "service", "teacher", "class_name", "section", "student"])
    detail_rows = [["Date", "Service", "Teacher", "Class", "Section", "Student", "Status"]] + [[str(r.attendance_date), str(r.service), str(r.teacher), str(r.class_name), str(r.section), str(r.student), str(r.status)] for _, r in detailed.iterrows()]
    table = Table(detail_rows, colWidths=[25 * mm, 43 * mm, 38 * mm, 30 * mm, 23 * mm, 48 * mm, 23 * mm], repeatRows=1); table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7), ("PADDING", (0, 0), (-1, -1), 3)])); story += [table]
    document.build(story)
    return output.getvalue()


def take_attendance():
    st.title("Take attendance"); day = st.date_input("Attendance date", date.today()); service_id = select_service("Prayer service", "attendance_service"); teacher_id = select_teacher(service_id, "Teacher", "attendance_teacher")
    if not teacher_id: return
    students = student_view(); students = students[(students.teacher_id == teacher_id) & (students.active != "0")].sort_values("name")
    if students.empty: st.info("No active students are assigned to this teacher."); return
    existing = read("attendance"); existing = existing[existing.attendance_date == str(day)].set_index("student_id").status.to_dict()
    data = students[["id", "name", "class_name", "section", "gender"]].copy(); data["status"] = data.id.map(existing).fillna("Present")
    st.caption("Everyone starts as Present. Change only students who are absent, then save.")
    edited = st.data_editor(data, hide_index=True, disabled=["id", "name", "class_name", "section", "gender"], column_config={"status": st.column_config.SelectboxColumn("Status", options=["Present", "Absent"], required=True)}, use_container_width=True)
    if st.button("Save attendance", type="primary"):
        records = read("attendance"); records = records[~((records.attendance_date == str(day)) & (records.student_id.isin(edited.id.tolist())))]
        now = str(pd.Timestamp.now()); new = pd.DataFrame([{"id": str(next_id("attendance") + i), "attendance_date": str(day), "student_id": str(r.id), "service_id": service_id, "teacher_id": teacher_id, "status": r.status, "notes": "", "created_at": now, "updated_at": now} for i, r in enumerate(edited.itertuples(index=False))])
        write("attendance", pd.concat([records, new], ignore_index=True)); st.success(f"Attendance saved for {len(edited)} students.")


def students_page():
    st.title("Students"); add, browse, transfer = st.tabs(["Add student", "Find / edit", "Import / export"])
    with add: student_form(form_key="add_student")
    with browse:
        query = st.text_input("Search name, area, parent, or mobile").lower(); data = student_view(); data = data[data.active != "0"]
        if query: data = data[data.astype(str).apply(lambda x: x.str.lower().str.contains(query, regex=False)).any(axis=1)]
        show = data[["id", "name", "age", "gender", "mobile_number", "area", "father_name", "mother_name", "class_name", "section", "teacher_name", "service_name", "address"]]; st.dataframe(show, hide_index=True, use_container_width=True)
        if not data.empty:
            picked = st.selectbox("Select a student to edit", data.id.tolist(), format_func=lambda i: data.set_index("id").loc[i, "name"]); row = read("students").set_index("id").loc[picked].to_dict(); row["id"] = picked; student_form(row, form_key=f"edit_student_{picked}")
            if st.button("Deactivate selected student"): update_rows("students", lambda d: d.id == picked, {"active": "0"}); st.success("Student deactivated."); st.rerun()
    with transfer: import_export()


def import_export():
    data = student_view(); out = data[["name", "age", "gender", "mobile_number", "area", "father_name", "mother_name", "class_name", "section", "teacher_name", "service_name", "address"]]
    st.download_button("Download students CSV", out.to_csv(index=False).encode(), "students.csv", "text/csv")
    b = io.BytesIO(); out.to_excel(b, index=False); st.download_button("Download students Excel", b.getvalue(), "students.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    file = st.file_uploader("Import students (CSV or Excel)", type=["csv", "xlsx"])
    if file and st.button("Import uploaded students"):
        incoming = pd.read_csv(file, dtype=str).fillna("") if file.name.lower().endswith("csv") else pd.read_excel(file, dtype=str).fillna(""); incoming.columns = [str(c).strip().lower().replace(" ", "_") for c in incoming.columns]
        if not {"name", "teacher_name"}.issubset(incoming.columns): st.error("Import needs name and teacher_name columns."); return
        added = 0
        for _, r in incoming.iterrows():
            service = r.get("service_name") or "First Service (8:00 AM)"; svc = read("services"); match = svc[svc.name.str.lower() == service.lower()]
            service_id = match.id.iloc[0] if not match.empty else add_row("services", {"name": service, "sort_order": len(svc) + 1})
            teacher = r["teacher_name"]; teachers = read("teachers"); match = teachers[(teachers.name.str.lower() == teacher.lower()) & (teachers.service_id == service_id)]
            teacher_id = match.id.iloc[0] if not match.empty else add_row("teachers", {"name": teacher, "service_id": service_id, "phone": "", "active": "1"})
            cl = r.get("class_name") or "Beginners"; classes = read("classes"); match = classes[classes.name.str.lower() == cl.lower()]; class_id = match.id.iloc[0] if not match.empty else add_row("classes", {"name": cl, "category": "Primary"})
            existing_students = read("students")
            duplicate = existing_students[(existing_students.teacher_id == teacher_id) & (existing_students.name.str.lower() == str(r["name"]).lower())]
            if duplicate.empty:
                add_row("students", {"name": r["name"], "age": r.get("age", ""), "gender": r.get("gender", ""), "mobile_number": r.get("mobile_number", ""), "area": r.get("area", ""), "father_name": r.get("father_name", ""), "mother_name": r.get("mother_name", ""), "class_id": class_id, "section": r.get("section", ""), "teacher_id": teacher_id, "service_id": service_id, "address": r.get("address", ""), "active": "1", "created_at": str(date.today())}); added += 1
        st.success(f"Imported {added} new student(s). Duplicates were skipped.")


def reports():
    st.title("Attendance reports"); start = st.date_input("From", date.today().replace(day=1)); end = st.date_input("To", date.today()); service_id = select_service("Service", "report_service", True); teacher_id = select_teacher(service_id, "Teacher", "report_teacher", True)
    data = attendance_view(); data = data[(data.attendance_date >= str(start)) & (data.attendance_date <= str(end))]
    if service_id != "0": data = data[data.service_id == service_id]
    if teacher_id != "0": data = data[data.teacher_id == teacher_id]
    if data.empty: st.info("No attendance records match these filters."); return
    absent = data[data.status == "Absent"]; a, b, c = st.columns(3); a.metric("Recorded", len(data)); b.metric("Absences", len(absent)); c.metric("Absence percentage", f"{len(absent)/len(data)*100:.1f}%")
    st.subheader("Absentees"); st.dataframe(absent, hide_index=True, use_container_width=True)
    monthly = data.assign(month=pd.to_datetime(data.attendance_date).dt.strftime("%Y-%m")).groupby("month").agg(Recorded=("status", "size"), Absences=("status", lambda x: (x == "Absent").sum())).reset_index(); monthly["Absence %"] = (monthly.Absences / monthly.Recorded * 100).round(1)
    st.subheader("Month-wise absentee summary"); st.dataframe(monthly, hide_index=True, use_container_width=True)
    summary = data.groupby(["service", "class_name"]).agg(Recorded=("status", "size"), Absences=("status", lambda x: (x == "Absent").sum())).reset_index(); summary["Absence %"] = (summary.Absences / summary.Recorded * 100).round(1)
    st.plotly_chart(px.bar(summary, x="service", y="Absence %", color="class_name", barmode="group", title="Absence percentage by service and class"), use_container_width=True)
    frequency = data.groupby("service").agg(Attendance_records=("status", "size"), Sundays_recorded=("attendance_date", "nunique"), Present=("status", lambda x: (x == "Present").sum()), Absent=("status", lambda x: (x == "Absent").sum())).reset_index()
    frequency["Attendance %"] = (frequency.Present / frequency.Attendance_records * 100).round(1)
    frequency["Absence %"] = (frequency.Absent / frequency.Attendance_records * 100).round(1)
    st.subheader("Service-wise attendance frequency")
    st.dataframe(frequency, hide_index=True, use_container_width=True)
    st.download_button("Export filtered report CSV", data.to_csv(index=False).encode(), "attendance_report.csv", "text/csv")
    st.download_button("Download printable attendance PDF", build_attendance_pdf(data, start, end), f"shaaron_pentecostal_church_attendance_{start}_to_{end}.pdf", "application/pdf", type="primary")


def management():
    st.title("Management"); kind = st.radio("Manage", ["Prayer services", "Teachers", "Classes", "📝 Marks entry"], horizontal=True)
    if kind == "Prayer services":
        add_tab, edit_tab = st.tabs(["Add service", "Edit service"])
        with add_tab:
            with st.form("add_service"):
                name = st.selectbox("Service name", SERVICE_OPTIONS)
                save = st.form_submit_button("Add service")
            if save:
                existing = read("services")
                if existing.name.str.lower().str.startswith(name.lower()).any(): st.info("That service already exists.")
                else: add_row("services", {"name": name, "sort_order": SERVICE_OPTIONS.index(name) + 1}); st.rerun()
        with edit_tab:
            data = services()
            selected_id = st.selectbox("Service to edit", data.id.tolist(), format_func=lambda i: data.set_index("id").loc[i, "name"], key="edit_service_id")
            current = data.set_index("id").loc[selected_id]
            options = list(dict.fromkeys(SERVICE_OPTIONS + [current["name"]]))
            with st.form("edit_service"):
                name = st.selectbox("Service name", options, index=options.index(current["name"]))
                update = st.form_submit_button("Update service")
            if update:
                duplicates = data[(data.id != selected_id) & (data.name.str.lower() == name.lower())]
                if not duplicates.empty: st.error("That service name already exists.")
                else: update_rows("services", lambda d: d.id == selected_id, {"name": name, "sort_order": options.index(name) + 1}); st.success("Service updated."); st.rerun()
        st.dataframe(services(), hide_index=True)
    elif kind == "Teachers":
        add_tab, edit_tab = st.tabs(["Add teacher", "Edit teacher"])
        with add_tab:
            service_id = select_service("Prayer service", "manage_service")
            with st.form("add_teacher"): name = st.text_input("Teacher name"); phone = st.text_input("Phone"); save = st.form_submit_button("Add teacher")
            if save and name.strip(): add_row("teachers", {"name": name.strip(), "service_id": service_id, "phone": phone.strip(), "active": "1"}); st.rerun()
        with edit_tab:
            teachers = active_teachers()
            selected_id = st.selectbox("Teacher to edit", teachers.id.tolist(), format_func=lambda i: teachers.set_index("id").loc[i, "name"], key="edit_teacher_id")
            current = teachers.set_index("id").loc[selected_id]; service_data = services()
            with st.form("edit_teacher"):
                service_id = st.selectbox("Prayer service", service_data.id.tolist(), index=service_data.id.tolist().index(current.service_id), format_func=lambda i: service_data.set_index("id").loc[i, "name"])
                name = st.text_input("Teacher name", current["name"]); phone = st.text_input("Phone", current["phone"])
                update = st.form_submit_button("Update teacher")
            if update and name.strip():
                duplicate = teachers[(teachers.id != selected_id) & (teachers.service_id == service_id) & (teachers.name.str.lower() == name.strip().lower())]
                if not duplicate.empty: st.error("That teacher already exists for this service.")
                else: update_rows("teachers", lambda d: d.id == selected_id, {"name": name.strip(), "service_id": service_id, "phone": phone.strip()}); st.success("Teacher updated."); st.rerun()
        st.dataframe(active_teachers().merge(services().rename(columns={"id":"service_id", "name":"service"}), on="service_id")[["name", "service", "phone", "active"]], hide_index=True)
    elif kind == "Classes":
        add_tab, edit_tab = st.tabs(["Add class", "Edit class"])
        with add_tab:
            with st.form("add_class"):
                category = st.selectbox("Class", ["Beginners", "Primary"]); section = st.selectbox("Section", SECTION_OPTIONS); save = st.form_submit_button("Add class")
            name = f"{category} - {section}"
            if save:
                if (read("classes").name.str.lower() == name.lower()).any(): st.error("That class and section already exist.")
                else: add_row("classes", {"name": name, "category": category}); st.rerun()
        with edit_tab:
            classes = read("classes")
            selected_id = st.selectbox("Class to edit", classes.id.tolist(), format_func=lambda i: classes.set_index("id").loc[i, "name"], key="edit_class_id")
            current = classes.set_index("id").loc[selected_id]; current_section = next((s for s in SECTION_OPTIONS if current["name"].endswith(s)), SECTION_OPTIONS[0])
            with st.form("edit_class"):
                category = st.selectbox("Class", ["Beginners", "Primary"], index=["Beginners", "Primary"].index(current.category) if current.category in ["Beginners", "Primary"] else 0)
                section = st.selectbox("Section", SECTION_OPTIONS, index=SECTION_OPTIONS.index(current_section)); update = st.form_submit_button("Update class")
            name = f"{category} - {section}"
            if update:
                duplicate = classes[(classes.id != selected_id) & (classes.name.str.lower() == name.lower())]
                if not duplicate.empty: st.error("That class and section already exist.")
                else: update_rows("classes", lambda d: d.id == selected_id, {"name": name, "category": category}); st.success("Class updated."); st.rerun()
        st.dataframe(read("classes"), hide_index=True)
    else:
        marks_entry()


def marks_entry():
    """Enter or update one exam's marks for the students assigned to a teacher."""
    st.subheader("📝 Mark entry")
    st.caption("Choose the prayer service and teacher. Enter marks beside each student, then save.")
    exam_date = st.date_input("Exam date", date.today(), key="marks_exam_date")
    exam_name = st.text_input("Exam name *", placeholder="Example: Bible Quiz - August", key="marks_exam_name")
    maximum_mark = st.number_input("Maximum mark", min_value=1.0, value=100.0, step=1.0, key="marks_maximum")
    service_id = select_service("Prayer service", "marks_service")
    teacher_id = select_teacher(service_id, "Teacher", "marks_teacher")
    if not teacher_id:
        return
    students = student_view()
    students = students[(students.teacher_id == teacher_id) & (students.active != "0")].sort_values("name")
    if students.empty:
        st.info("No active students are assigned to this teacher.")
        return
    if not exam_name.strip():
        st.info("Enter an exam name to start entering marks.")
        return
    saved = read("marks")
    previous = saved[(saved.exam_date == str(exam_date)) & (saved.exam_name.str.lower() == exam_name.strip().lower())].set_index("student_id").mark.to_dict()
    entry = students[["id", "name", "class_name", "section"]].copy()
    entry["mark"] = pd.to_numeric(entry.id.map(previous), errors="coerce")
    edited = st.data_editor(entry, hide_index=True, disabled=["id", "name", "class_name", "section"], column_config={"mark": st.column_config.NumberColumn("Mark", min_value=0.0, max_value=float(maximum_mark), step=0.5, format="%.1f")}, use_container_width=True, key=f"marks_editor_{exam_date}_{service_id}_{teacher_id}_{exam_name.strip()}")
    if st.button("Save marks", type="primary"):
        invalid = edited[edited.mark.notna() & (edited.mark > maximum_mark)]
        if not invalid.empty:
            st.error("A mark cannot be greater than the maximum mark.")
            return
        mark_data = read("marks")
        selected_ids = edited.id.tolist()
        mark_data = mark_data[~((mark_data.exam_date == str(exam_date)) & (mark_data.exam_name.str.lower() == exam_name.strip().lower()) & (mark_data.student_id.isin(selected_ids)))]
        now = str(pd.Timestamp.now())
        entered = edited[edited.mark.notna()]
        new_rows = pd.DataFrame([{"id": str(next_id("marks") + index), "exam_date": str(exam_date), "exam_name": exam_name.strip(), "student_id": str(row.id), "service_id": service_id, "teacher_id": teacher_id, "mark": row.mark, "maximum_mark": maximum_mark, "created_at": now, "updated_at": now} for index, row in enumerate(entered.itertuples(index=False))])
        write("marks", pd.concat([mark_data, new_rows], ignore_index=True))
        st.success(f"Saved marks for {len(entered)} student(s).")
    existing_marks = read("marks")
    existing_marks = existing_marks[(existing_marks.exam_date == str(exam_date)) & (existing_marks.exam_name.str.lower() == exam_name.strip().lower())]
    if not existing_marks.empty:
        names = student_view().rename(columns={"id": "student_id", "name": "Student"})
        st.caption("Saved marks for this exam")
        st.dataframe(existing_marks.merge(names[["student_id", "Student", "class_name", "section"]], on="student_id", how="left")[["Student", "class_name", "section", "mark", "maximum_mark"]], hide_index=True, use_container_width=True)


def backup():
    st.title("Settings & backup"); st.warning("CSV is easy to use in Excel, but it is best for one teacher saving at a time. Keep regular backups and avoid sharing student contact details publicly.")
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        for table in TABLES: z.write(csv_path(table), arcname=f"church_attendance_csv/{csv_path(table).name}")
    st.download_button("Download all CSV files (ZIP backup)", package.getvalue(), "church_attendance_csv_backup.zip", "application/zip")
    st.caption(f"CSV folder: {CSV_DIR}")


def login_panel():
    """Protect all data-entry and management pages for this Streamlit session."""
    username = os.getenv("APP_USERNAME", "Shaaron")
    password = os.getenv("APP_PASSWORD", "Jesus")
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        st.sidebar.success(f"Signed in as {username}")
        if st.sidebar.button("Sign out"):
            st.session_state.authenticated = False
            st.rerun()
        return True
    with st.sidebar.form("login_form"):
        st.caption("Sign in to enter or manage data")
        entered_name = st.text_input("Username")
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if hmac.compare_digest(entered_name, username) and hmac.compare_digest(entered_password, password):
            st.session_state.authenticated = True
            st.rerun()
        st.sidebar.error("Incorrect username or password.")
    return False


initialize()
st.sidebar.title("⛪ Sunday Class")
signed_in = login_panel()
public_pages = ["Dashboard", "Reports"]
private_pages = ["Take attendance", "Students", "Management", "Settings & backup"]
page = st.sidebar.radio("Menu", public_pages + (private_pages if signed_in else []))
church_header()
{"Dashboard": dashboard, "Take attendance": take_attendance, "Students": students_page, "Reports": reports, "Management": management, "Settings & backup": backup}[page]()
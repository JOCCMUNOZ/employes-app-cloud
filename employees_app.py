import streamlit as st
import sqlite3, os, io, csv, zipfile
from datetime import date, datetime

APP_TITLE = "👷 EMPLOYEES APP — Cloud (Full)"
DB = "employees.db"

st.set_page_config(page_title=APP_TITLE, layout="wide")

def conn(): return sqlite3.connect(DB, check_same_thread=False)

def ensure_db_exists():
    if not os.path.exists(DB) and os.path.exists("employees_empty.db"):
        with open("employees_empty.db","rb") as src, open(DB,"wb") as dst:
            dst.write(src.read())

def q(sql,p=()):
    with conn() as c:
        cur=c.execute(sql,p)
        cols=[d[0] for d in cur.description] if cur.description else []
        rows=cur.fetchall()
    return cols,rows

def exec_sql(sql,p=()):
    with conn() as c:
        c.execute(sql,p); c.commit()

def to_dicts(cols, rows): return [dict(zip(cols, r)) for r in rows]

def csv_bytes(rows):
    if not rows: return b""
    buf=io.StringIO(); w=csv.DictWriter(buf, fieldnames=list(rows[0].keys())); w.writeheader()
    for r in rows: w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")

def init_schema():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS crews(id INTEGER PRIMARY KEY, company_id INT, crew_code TEXT, foreman_name TEXT, UNIQUE(company_id,crew_code));
        CREATE TABLE IF NOT EXISTS workers(
         id INTEGER PRIMARY KEY, full_name TEXT, company_id INT, crew_id INT, start_date TEXT, termination_date TEXT,
         active INT DEFAULT 1, gloves_issued_date TEXT, gloves_returned_date TEXT, sleeves_issued_date TEXT, sleeves_returned_date TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS warnings(id INTEGER PRIMARY KEY, worker_id INT, warn_date TEXT, warn_type TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS accidents(id INTEGER PRIMARY KEY, worker_id INT, accident_date TEXT, injury_type TEXT, description TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS sick_hours(id INTEGER PRIMARY KEY, worker_id INT, sick_date TEXT, hours REAL, notes TEXT);
        CREATE TABLE IF NOT EXISTS ppe_events(id INTEGER PRIMARY KEY, worker_id INT, item TEXT, action TEXT, date TEXT, qty REAL DEFAULT 1, size TEXT, notes TEXT);
        """)

def company_select(lbl="Compañía", key=None):
    _,r=q("SELECT id,name FROM companies ORDER BY name")
    opts=[("— seleccionar —",-1)]+[(x[1],x[0]) for x in r]
    lab=st.selectbox(lbl,[x[0] for x in opts], key=key)
    return dict(opts).get(lab,-1)

def crews_for_company(cid):
    if cid<=0: return []
    _,r=q("SELECT id,crew_code,foreman_name FROM crews WHERE company_id=? ORDER BY crew_code",(cid,))
    return r

# Header
ensure_db_exists(); init_schema()
st.title(APP_TITLE)
st.sidebar.caption(f"DB: {os.path.abspath(DB)}")
try:
    _, r = q("SELECT COUNT(*) FROM workers")
    st.sidebar.caption(f"👥 Workers: {r[0][0]}")
except Exception as e:
    st.sidebar.caption(f"DB error: {e}")

menu = st.sidebar.radio("Menú",[
 "Compañías y Cuadrillas","Trabajadores (Alta/Edición)","Sick Hours (Registro)","Historial Sick Hours",
 "PPE (Gloves/Sleeves & Bajas)","PPE Movimientos (historial)","Warnings","Historial Warnings",
 "Accidentes","Historial Accidentes","Historial trabajadores x cuadrilla","Listado x cuadrilla (imprimible)",
 "Respaldos (Backup/Restore)","Exportar CSV"
])

# --- Compañías & Cuadrillas ---
if menu=="Compañías y Cuadrillas":
    st.subheader("Compañías")
    name=st.text_input("Nueva compañía")
    if st.button("➕ Agregar compañía"):
        if name.strip():
            try: exec_sql("INSERT INTO companies(name) VALUES(?)",(name.strip(),)); st.success("Agregada.")
            except sqlite3.IntegrityError: st.error("Ya existe.")
        else: st.warning("Escribe un nombre.")
    st.markdown("---"); st.subheader("Cuadrillas")
    cid=company_select()
    c1,c2,c3=st.columns(3)
    with c1: code=st.text_input("Crew Code")
    with c2: fore=st.text_input("Foreman (Mayordomo)")
    with c3:
        if st.button("➕ Agregar cuadrilla"):
            if cid<=0: st.warning("Selecciona compañía.")
            elif not code.strip(): st.warning("Escribe Crew Code.")
            else:
                try: exec_sql("INSERT INTO crews(company_id,crew_code,foreman_name) VALUES(?,?,?)",(cid,code.strip(),fore.strip())); st.success("Agregada.")
                except sqlite3.IntegrityError: st.error("Duplicada para esa compañía.")

# --- Trabajadores ---
elif menu=="Trabajadores (Alta/Edición)":
    st.subheader("Alta de trabajador")
    cid=company_select("Compañía del trabajador", key="comp_worker")
    crews=crews_for_company(cid)
    if cid<=0:
        st.info("Selecciona compañía para ver cuadrillas."); crew_id=-1
    else:
        opts=["— seleccionar —"]+[f"{r[1]} — {r[2] or ''}" for r in crews]
        sel=st.selectbox("Cuadrilla",opts, key="crew_sel")
        crew_id=-1 if sel=="— seleccionar —" else crews[opts.index(sel)-1][0]
    name=st.text_input("Nombre completo")
    start=st.date_input("Fecha de alta", value=date.today())
    g_chk=st.checkbox("Registrar entrega de Gloves ahora"); g_date=st.date_input("Fecha Gloves", value=date.today(), key="g_issue")
    s_chk=st.checkbox("Registrar entrega de Sleeves ahora"); s_date=st.date_input("Fecha Sleeves", value=date.today(), key="s_issue")
    if st.button("💾 Guardar trabajador"):
        if cid<=0 or crew_id<=0 or not name.strip(): st.warning("Faltan datos."); 
        else:
            exec_sql("""INSERT INTO workers(full_name,company_id,crew_id,start_date,gloves_issued_date,sleeves_issued_date,active)
                        VALUES(?,?,?,?,?,?,1)""",
                     (name.strip(),cid,crew_id,str(start),str(g_date) if g_chk else None,str(s_date) if s_chk else None))
            st.success("Guardado.")

    st.markdown("---"); st.subheader("Editar / Baja / Borrar")
    search=st.text_input("Buscar (nombre contiene)",value="")
    w="WHERE 1=1"; p=[]
    if search.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{search.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name company,cr.crew_code crew,w.start_date,w.termination_date,w.active
              FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.id DESC LIMIT 200""",tuple(p))
    rows=to_dicts(c,r); st.dataframe(rows,use_container_width=True)
    if rows:
        sel_id=st.selectbox("ID trabajador",[x["id"] for x in rows])
        c2,r2=q("SELECT id,full_name,start_date,termination_date,active,notes FROM workers WHERE id=?",(sel_id,)); w2=to_dicts(c2,r2)[0]
        a,b,cx=st.columns(3)
        with a: new_name=st.text_input("Nombre",value=w2["full_name"])
        with b: new_start=st.date_input("Alta", value=date.fromisoformat(w2["start_date"]) if w2["start_date"] else date.today())
        with cx: new_active=st.checkbox("Activo", value=bool(w2["active"]))
        notes=st.text_input("Notas", value=w2["notes"] or "")
        if st.button("✅ Actualizar"):
            exec_sql("UPDATE workers SET full_name=?,start_date=?,notes=?,active=? WHERE id=?",(new_name.strip(),str(new_start),notes.strip() or None,1 if new_active else 0,sel_id)); st.success("Actualizado.")
        st.error("Zona peligrosa")
        col1,col2=st.columns(2)
        if col1.button("✋ Dar de baja (no borrar)"):
            exec_sql("UPDATE workers SET active=0,termination_date=? WHERE id=?",(str(date.today()),sel_id)); st.success("Baja aplicada."); st.experimental_rerun()
        conf=st.text_input("Escribe BORRAR para eliminar", key=f"conf_{sel_id}")
        if col2.button("🗑️ Borrar trabajador + historial"):
            if conf.strip().upper()=="BORRAR":
                exec_sql("DELETE FROM warnings WHERE worker_id=?", (sel_id,))
                exec_sql("DELETE FROM accidents WHERE worker_id=?", (sel_id,))
                exec_sql("DELETE FROM sick_hours WHERE worker_id=?", (sel_id,))
                exec_sql("DELETE FROM ppe_events WHERE worker_id=?", (sel_id,))
                exec_sql("DELETE FROM workers WHERE id=?", (sel_id,)); st.success("Eliminado."); st.experimental_rerun()
            else: st.warning("Confirmación incorrecta.")

# --- Sick Hours Registro ---
elif menu=="Sick Hours (Registro)":
    st.subheader("Registrar horas de enfermedad")
    s=st.text_input("Buscar trabajador",value="")
    w="WHERE 1=1"; p=[]
    if s.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name,cr.crew_code FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.full_name LIMIT 300""",tuple(p))
    opts=[f"{x[0]} — {x[1]} ({x[2]}/{x[3]})" for x in r]
    sel=st.selectbox("Trabajador",opts) if opts else None; wid=int(sel.split(" — ")[0]) if sel else None
    a,b,cx=st.columns(3)
    with a: d=st.date_input("Fecha", value=date.today())
    with b: h=st.number_input("Horas", min_value=0.0, step=0.5, value=8.0, format="%.1f")
    with cx: notes=st.text_input("Notas (opcional)")
    if st.button("➕ Guardar", disabled=(wid is None)):
        exec_sql("INSERT INTO sick_hours(worker_id,sick_date,hours,notes) VALUES(?,?,?,?)",(wid,str(d),float(h),notes.strip() or None)); st.success("Registro guardado.")

# --- Historial Sick Hours ---
elif menu=="Historial Sick Hours":
    st.subheader("Historial de sick hours")
    s=st.text_input("Buscar (nombre contiene)",value="")
    d1,d2=st.columns(2); f=d1.date_input("Desde",value=date(2025,1,1)); t=d2.date_input("Hasta",value=date.today())
    where="WHERE s.sick_date BETWEEN ? AND ?"; p=[str(f),str(t)]
    if s.strip(): where+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT s.id,s.sick_date,s.hours,s.notes,w.full_name worker,c.name company,cr.crew_code crew
              FROM sick_hours s JOIN workers w ON w.id=s.worker_id JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {where} ORDER BY s.sick_date DESC,s.id DESC""",tuple(p))
    rows=to_dicts(c,r); st.dataframe(rows,use_container_width=True); st.caption(f"Registros: {len(rows)}")
    c2,r2=q(f"""SELECT w.full_name worker,SUM(s.hours) total_hours FROM sick_hours s JOIN workers w ON w.id=s.worker_id
                {where} GROUP BY s.worker_id ORDER BY w.full_name""",tuple(p))
    totals=to_dicts(c2,r2); st.dataframe(totals,use_container_width=True)
    if rows: st.download_button("CSV historial", data=csv_bytes(rows), file_name="sick_historial.csv", mime="text/csv")
    if totals: st.download_button("CSV totales", data=csv_bytes(totals), file_name="sick_totales.csv", mime="text/csv")

# --- PPE básico en ficha ---
elif menu=="PPE (Gloves/Sleeves & Bajas)":
    st.subheader("Registrar/Editar entrega y devolución de Gloves y Sleeves (campos fijos)")
    s=st.text_input("Buscar trabajador",value=""); w="WHERE 1=1"; p=[]
    if s.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name,cr.crew_code,gloves_issued_date,gloves_returned_date,sleeves_issued_date,sleeves_returned_date
              FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.full_name LIMIT 400""",tuple(p))
    opts=[f"{x[0]} - {x[1]} ({x[2]}/{x[3]})" for x in r]
    sel=st.selectbox("Trabajador",opts) if opts else None; wid=int(sel.split(" - ")[0]) if sel else None

    if wid:
        def _d(s): 
            try: return date.fromisoformat(s) if s else date.today()
            except: return date.today()
        gi,gr,si,sr=None,None,None,None
        for row in r:
            if row[0]==wid: gi,gr,si,sr=row[4],row[5],row[6],row[7]; break
        c1,c2=st.columns(2)
        with c1:
            st.markdown("**Gloves**")
            gi_blank=st.checkbox("Vacío (entrega)", value=(gi is None))
            gi_date=st.date_input("Fecha entrega Gloves", value=_d(gi))
            gr_blank=st.checkbox("Vacío (devolución)", value=(gr is None))
            gr_date=st.date_input("Fecha devolución Gloves", value=_d(gr))
        with c2:
            st.markdown("**Sleeves**")
            si_blank=st.checkbox("Vacío (entrega)", value=(si is None))
            si_date=st.date_input("Fecha entrega Sleeves", value=_d(si))
            sr_blank=st.checkbox("Vacío (devolución)", value=(sr is None))
            sr_date=st.date_input("Fecha devolución Sleeves", value=_d(sr))
        if st.button("Guardar cambios PPE"):
            exec_sql("""UPDATE workers SET
                        gloves_issued_date=?, gloves_returned_date=?,
                        sleeves_issued_date=?, sleeves_returned_date=?
                        WHERE id=?""",
                     (None if gi_blank else str(gi_date),
                      None if gr_blank else str(gr_date),
                      None if si_blank else str(si_date),
                      None if sr_blank else str(sr_date),
                      wid))
            st.success("PPE actualizado.")

# --- PPE Movimientos ---
elif menu=="PPE Movimientos (historial)":
    st.subheader("Movimientos PPE (issue/return) — con talla para gloves")
    s=st.text_input("Buscar trabajador",value=""); w="WHERE 1=1"; p=[]
    if s.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name,cr.crew_code FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.full_name LIMIT 500""",tuple(p))
    opts=[f"{x[0]} - {x[1]} ({x[2]}/{x[3]})" for x in r]
    sel=st.selectbox("Trabajador",opts) if opts else None; wid=int(sel.split(" - ")[0]) if sel else None

    a,b,cx,dx=st.columns(4)
    with a: item=st.selectbox("Item",["gloves","sleeves"])
    with b: action=st.selectbox("Acción",["issue","return"])
    with cx: d=st.date_input("Fecha", value=date.today())
    with dx: qty=st.number_input("Cantidad (pares)", min_value=0.0, step=1.0, value=1.0, format="%.0f")
    size=None
    if item=="gloves": size=st.selectbox("Talla (gloves)",["","8.5","9","9.5","10","10.5","11","11.5","12"]) or None
    notes=st.text_input("Notas (opcional)")
    if st.button("Guardar movimiento", disabled=(wid is None)):
        exec_sql("INSERT INTO ppe_events(worker_id,item,action,date,qty,size,notes) VALUES(?,?,?,?,?,?,?)",(wid,item,action,str(d),float(qty),size,notes.strip() or None)); st.success("Guardado.")

    st.markdown("---"); st.subheader("Historial / Filtros")
    s2=st.text_input("Buscar (nombre contiene)",value="")
    f1,f2,f3,f4=st.columns(4); fd=f1.date_input("Desde",value=date(2025,1,1)); td=f2.date_input("Hasta",value=date.today())
    item_f=f3.selectbox("Item filtro",["(todos)","gloves","sleeves"]); act_f=f4.selectbox("Acción filtro",["(todas)","issue","return"])
    where="WHERE pe.date BETWEEN ? AND ?"; p=[str(fd),str(td)]
    if s2.strip(): where+=" AND w.full_name LIKE ?"; p.append(f"%{s2.strip()}%")
    if item_f!="(todos)": where+=" AND pe.item=?"; p.append(item_f)
    if act_f!="(todas)": where+=" AND pe.action=?"; p.append(act_f)
    c,r=q(f"""SELECT pe.id,pe.date,pe.item,pe.action,pe.qty,pe.size,pe.notes,w.full_name worker,c.name company,cr.crew_code crew
              FROM ppe_events pe JOIN workers w ON w.id=pe.worker_id JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {where} ORDER BY pe.date DESC, pe.id DESC""",tuple(p))
    hist=to_dicts(c,r); st.dataframe(hist,use_container_width=True); st.caption(f"Registros: {len(hist)}")
    if hist: st.download_button("CSV PPE", data=csv_bytes(hist), file_name="ppe_historial.csv", mime="text/csv")

# --- Warnings ---
elif menu=="Warnings":
    st.subheader("Registrar Warning")
    s=st.text_input("Buscar trabajador",value=""); w="WHERE 1=1"; p=[]
    if s.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name,cr.crew_code FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.full_name LIMIT 300""",tuple(p))
    opts=[f"{x[0]} — {x[1]} ({x[2]}/{x[3]})" for x in r]
    sel=st.selectbox("Trabajador",opts) if opts else None; wid=int(sel.split(" — ")[0]) if sel else None
    a,b,cx=st.columns(3)
    with a: d=st.date_input("Fecha", value=date.today())
    with b: t=st.selectbox("Tipo",["no_safety_glasses","low_production","other"])
    with cx: notes=st.text_input("Notas (opcional)")
    if st.button("➕ Guardar warning", disabled=(wid is None)):
        exec_sql("INSERT INTO warnings(worker_id,warn_date,warn_type,notes) VALUES(?,?,?,?)",(wid,str(d),t,notes.strip() or None)); st.success("Guardado.")

elif menu=="Historial Warnings":
    st.subheader("Historial Warnings")
    s=st.text_input("Buscar (nombre contiene)",value=""); d1,d2=st.columns(2); fd=d1.date_input("Desde",value=date(2025,1,1)); td=d2.date_input("Hasta",value=date.today())
    where="WHERE wr.warn_date BETWEEN ? AND ?"; p=[str(fd),str(td)]
    if s.strip(): where+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT wr.id,wr.warn_date,wr.warn_type,wr.notes,w.full_name worker,c.name company,cr.crew_code crew
              FROM warnings wr JOIN workers w ON w.id=wr.worker_id JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {where} ORDER BY wr.warn_date DESC, wr.id DESC""",tuple(p))
    rows=to_dicts(c,r); st.dataframe(rows,use_container_width=True); st.caption(f"Registros: {len(rows)}")
    c2,r2=q(f"""SELECT w.full_name worker,COUNT(*) total_warnings FROM warnings wr JOIN workers w ON w.id=wr.worker_id
                {where} GROUP BY wr.worker_id ORDER BY total_warnings DESC, w.full_name""",tuple(p))
    totals=to_dicts(c2,r2); st.dataframe(totals,use_container_width=True)
    if rows: st.download_button("CSV Warnings", data=csv_bytes(rows), file_name="warnings_historial.csv", mime="text/csv")

# --- Accidentes ---
elif menu=="Accidentes":
    st.subheader("Registrar Accidente")
    s=st.text_input("Buscar trabajador",value=""); w="WHERE 1=1"; p=[]
    if s.strip(): w+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT w.id,w.full_name,c.name,cr.crew_code FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {w} ORDER BY w.full_name LIMIT 300""",tuple(p))
    opts=[f"{x[0]} — {x[1]} ({x[2]}/{x[3]})" for x in r]
    sel=st.selectbox("Trabajador",opts) if opts else None; wid=int(sel.split(" — ")[0]) if sel else None
    a,b=st.columns(2)
    with a:
        d=st.date_input("Fecha", value=date.today())
        inj=st.text_input("Tipo de lesión")
    with b:
        desc=st.text_area("Descripción")
        notes=st.text_input("Notas (opcional)")
    if st.button("➕ Guardar accidente", disabled=(wid is None)):
        if not inj.strip(): st.warning("Escribe el tipo de lesión.")
        else:
            exec_sql("INSERT INTO accidents(worker_id,accident_date,injury_type,description,notes) VALUES(?,?,?,?,?)",(wid,str(d),inj,desc.strip() or None,notes.strip() or None)); st.success("Guardado.")

elif menu=="Historial Accidentes":
    st.subheader("Historial Accidentes")
    s=st.text_input("Buscar (nombre contiene)",value=""); d1,d2=st.columns(2); fd=d1.date_input("Desde",value=date(2025,1,1)); td=d2.date_input("Hasta",value=date.today())
    where="WHERE a.accident_date BETWEEN ? AND ?"; p=[str(fd),str(td)]
    if s.strip(): where+=" AND w.full_name LIKE ?"; p.append(f"%{s.strip()}%")
    c,r=q(f"""SELECT a.id,a.accident_date,a.injury_type,a.description,a.notes,w.full_name worker,c.name company,cr.crew_code crew
              FROM accidents a JOIN workers w ON w.id=a.worker_id JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {where} ORDER BY a.accident_date DESC, a.id DESC""",tuple(p))
    rows=to_dicts(c,r); st.dataframe(rows,use_container_width=True); st.caption(f"Registros: {len(rows)}")
    c2,r2=q(f"""SELECT w.full_name worker,COUNT(*) total_accidents FROM accidents a JOIN workers w ON w.id=a.worker_id
                {where} GROUP BY a.worker_id ORDER BY total_accidents DESC, w.full_name""",tuple(p))
    totals=to_dicts(c2,r2); st.dataframe(totals,use_container_width=True)
    if rows: st.download_button("CSV Accidentes", data=csv_bytes(rows), file_name="accidentes_historial.csv", mime="text/csv")

# --- Historial trabajadores x cuadrilla ---
elif menu=="Historial trabajadores x cuadrilla":
    st.subheader("Historial de trabajadores por cuadrilla")
    cid = company_select("Compañía")
    crew_id = -1
    if cid>0:
        crews = crews_for_company(cid)
        if not crews: st.info("Esta compañía no tiene cuadrillas registradas.")
        else:
            labels = [f"{x[1]} — {x[2] or ''}" for x in crews]
            lab = st.selectbox("Cuadrilla", labels)
            crew_id = crews[labels.index(lab)][0]
    c1,c2,c3 = st.columns([1.2,1,1])
    with c1: status = st.selectbox("Mostrar", ["Activos","Inactivos","Todos"])
    with c2: dfrom = st.date_input("Desde (para bajas)", value=date(2025,1,1))
    with c3: dto = st.date_input("Hasta (para bajas)", value=date.today())
    where="WHERE 1=1"; p=[]
    if cid>0: where+=" AND w.company_id=?"; p.append(cid)
    if crew_id>0: where+=" AND w.crew_id=?"; p.append(crew_id)
    if status=="Activos":
        where+=" AND w.active=1"
    elif status=="Inactivos":
        where+=" AND w.active=0 AND w.termination_date BETWEEN ? AND ?"; p.extend([str(dfrom),str(dto)])
    c,r=q(f"""SELECT w.full_name trabajador,w.start_date alta,w.termination_date baja,
                     CASE WHEN w.active=1 THEN 'Sí' ELSE 'No' END activo,
                     c.name company,cr.crew_code crew,cr.foreman_name foreman,
                     w.gloves_issued_date,w.gloves_returned_date,
                     w.sleeves_issued_date,w.sleeves_returned_date,w.notes
              FROM workers w JOIN companies c ON c.id=w.company_id JOIN crews cr ON cr.id=w.crew_id
              {where} ORDER BY w.full_name""",tuple(p))
    rows=to_dicts(c,r)
    st.dataframe(rows,use_container_width=True); st.caption(f"Registros: {len(rows)}")
    if rows: st.download_button("CSV listado x cuadrilla", data=csv_bytes(rows), file_name="listado_cuadrilla.csv", mime="text/csv")

# --- Listado simple imprimible ---
elif menu=="Listado x cuadrilla (imprimible)":
    st.subheader("Listado por cuadrilla (vista para impresión)")
    cid=company_select(); crews=crews_for_company(cid)
    if cid<=0 or not crews: st.info("Selecciona compañía/cuadrilla con datos.")
    else:
        lab=st.selectbox("Cuadrilla",[f"{x[1]} — {x[2] or ''}" for x in crews])
        crew_id=crews[[f"{x[1]} — {x[2] or ''}" for x in crews].index(lab)][0]
        c,r=q("""SELECT w.full_name,w.start_date,w.active,w.gloves_issued_date,w.gloves_returned_date,w.sleeves_issued_date,w.sleeves_returned_date
                 FROM workers w WHERE w.company_id=? AND w.crew_id=? ORDER BY w.full_name""",(cid,crew_id))
        rows=to_dicts(c,r)
        st.table([{
            "Trabajador":x["full_name"],"Alta":x["start_date"] or "","Activo":"Sí" if x["active"] else "No",
            "Gloves entregados":x["gloves_issued_date"] or "","Gloves devueltos":x["gloves_returned_date"] or "",
            "Sleeves entregados":x["sleeves_issued_date"] or "","Sleeves devueltos":x["sleeves_returned_date"] or ""
        } for x in rows])
        st.caption("Usa Ctrl+P para imprimir.")

# --- Exportar CSV ---
elif menu=="Exportar CSV":
    st.subheader("Exportar tablas a CSV")
    tabs=[("companies","SELECT * FROM companies ORDER BY name"),
          ("crews","SELECT * FROM crews ORDER BY company_id,crew_code"),
          ("workers","SELECT * FROM workers ORDER BY id DESC"),
          ("warnings","SELECT * FROM warnings ORDER BY id DESC"),
          ("accidents","SELECT * FROM accidents ORDER BY id DESC"),
          ("sick_hours","SELECT * FROM sick_hours ORDER BY sick_date DESC, id DESC"),
          ("ppe_events","SELECT * FROM ppe_events ORDER BY date DESC, id DESC")]
    for n,sql in tabs:
        try:
            c,r=q(sql); rows=to_dicts(c,r)
            st.write(f"**{n}** — {len(rows)} filas")
            st.download_button(f"CSV — {n}", data=csv_bytes(rows) if rows else b"", file_name=f"{n}.csv", mime="text/csv")
        except Exception as e:
            st.write(f"{n}: (no disponible) {e}")

# --- Respaldos ---
elif menu=="Respaldos (Backup/Restore)":
    st.subheader("📦 Crear respaldo (.zip)")
    if os.path.exists(DB):
        mem=io.BytesIO()
        with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as zf: zf.write(DB, arcname="employees.db")
        mem.seek(0)
        st.download_button(":arrow_down: Descargar respaldo", data=mem.getvalue(), file_name=f"backup_employees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip", mime="application/zip")
    st.markdown("---")
    st.subheader("⬆️ Restaurar desde ZIP")
    up=st.file_uploader("Sube un ZIP que contenga employees.db", type=["zip"])
    if up is not None:
        import zipfile as _z
        try:
            mem=io.BytesIO(up.read())
            with _z.ZipFile(mem,"r") as zf:
                if "employees.db" not in zf.namelist():
                    st.error("El ZIP no contiene employees.db")
                else:
                    data=zf.read("employees.db")
                    with open(DB,"wb") as f: f.write(data)
                    st.success("Base restaurada. Recarga la app.")
        except Exception as e:
            st.error(f"Error: {e}")

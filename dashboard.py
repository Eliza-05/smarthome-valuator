"""
SmartHome Valuator — Dashboard B2B Institucional (Streamlit)
"""
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_URL = "https://smarthome-api-b2b.azurewebsites.net"

TENANTS = {
    "Banco Nacional  (Tenant A)": "tenant_a",
    "Portal Inmobiliario  (Tenant B)": "tenant_b",
}

# Costos mensuales de referencia por estrato (Bogotá) — solo para TCO, no afectan tasación
COSTOS_ESTRATO = {
    1: {"acueducto": 35_000,  "energia": 60_000,  "admin": 0},
    2: {"acueducto": 50_000,  "energia": 90_000,  "admin": 50_000},
    3: {"acueducto": 80_000,  "energia": 130_000, "admin": 150_000},
    4: {"acueducto": 120_000, "energia": 180_000, "admin": 400_000},
    5: {"acueducto": 180_000, "energia": 280_000, "admin": 800_000},
    6: {"acueducto": 250_000, "energia": 400_000, "admin": 1_500_000},
}

LOCALIDADES = [
    "Antonio Nariño", "Barrios Unidos", "Bosa", "Chapinero", "Ciudad Bolívar",
    "Engativá", "Fontibón", "Kennedy", "La Candelaria", "Los Mártires",
    "Puente Aranda", "Rafael Uribe Uribe", "San Cristóbal", "Santa Fe",
    "Suba", "Sumapaz", "Teusaquillo", "Tunjuelito", "Usaquén", "Usme",
]

UPZ_OPTIONS = [
    "", "12 de Octubre", "20 de Julio", "Aeropuerto", "Alcázares", "Alfonso López",
    "Américas", "Andes", "Antonio Nariño", "Apogeo", "Arborizadora", "Bavaria",
    "Bosa Central", "Bosa Occidental", "Britalia", "Candelaria", "Castilla",
    "Chapinero", "Ciudad Jardín", "Ciudad Montes", "Country Club", "El Refugio",
    "El Rincón", "El Tesoro", "Engativá", "Fontibón", "Granjas de Techo",
    "Gustavo Restrepo", "La Alhambra", "La Floresta", "La Sabana", "Las Ferias",
    "Las Nieves", "Los Alcázares", "Lucero", "Luna Park", "Niza", "Patio Bonito",
    "Quinta Paredes", "San Blas", "San Cristóbal Norte", "San José",
    "Santa Bárbara", "Santa Isabel", "Suba", "Teusaquillo", "Tibabuyes",
    "Timiza", "Tintal Norte", "Toberín", "Usaquén", "Usme Centro",
]

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="SmartHome Valuator",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Variables de color ── */
:root {
    --navy:      #1E3A5F;
    --navy-mid:  #2C5282;
    --gold:      #C8A84B;
    --gold-light:#F5EDD3;
    --bg:        #FFFFFF;
    --bg-soft:   #F0F4F8;
    --bg-card:   #FAFBFD;
    --text:      #1A2636;
    --text-muted:#5A6A7E;
    --border:    #D6E0EC;
    --success:   #276749;
    --success-bg:#EBF8F1;
    --shadow:    0 2px 12px rgba(30,58,95,0.08);
}

/* ── Reset Streamlit ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbarActionButton"] { display: none !important; }
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stHeader"] {
    background: var(--bg) !important;
    border-bottom: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
}
.block-container { padding: 4rem 2.5rem 3rem; max-width: 1300px; }

/* ── Topbar institucional ── */
.topbar {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%);
    border-radius: 14px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.8rem;
    display: flex;
    align-items: center;
    gap: 1.2rem;
    box-shadow: var(--shadow);
}
.topbar-icon { font-size: 2.2rem; }
.topbar-title { color: #FFFFFF; font-size: 1.65rem; font-weight: 700; margin: 0; letter-spacing: -0.3px; }
.topbar-sub   { color: rgba(255,255,255,0.72); font-size: 0.85rem; margin: 2px 0 0; }
.topbar-badge {
    margin-left: auto;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.3);
    color: #fff;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 20px;
    letter-spacing: 0.5px;
}

/* ── Secciones del formulario ── */
.section-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.4rem 1.6rem 1rem;
    margin-bottom: 0.5rem;
    box-shadow: var(--shadow);
}
.section-title {
    color: var(--navy);
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 2px solid var(--gold);
    padding-bottom: 6px;
    margin-bottom: 1rem;
}

/* ── Labels del formulario ── */
label, .stSelectbox label, .stSlider label,
.stNumberInput label, .stCheckbox label {
    color: var(--text) !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
}

/* ── Botón principal ── */
.stFormSubmitButton > button {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    padding: 0.75rem 2rem !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 4px 14px rgba(30,58,95,0.35) !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
}
.stFormSubmitButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(30,58,95,0.45) !important;
}

/* ── Tarjetas de resultado ── */
.result-hero {
    background: linear-gradient(135deg, var(--navy) 0%, #274472 100%);
    border-radius: 14px;
    padding: 1.8rem 2rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(30,58,95,0.2);
}
.result-hero-label { color: rgba(255,255,255,0.72); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.result-hero-value { color: #FFFFFF; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px; }
.result-hero-sub   { color: var(--gold); font-size: 0.8rem; margin-top: 4px; font-weight: 500; }

.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    box-shadow: var(--shadow);
    text-align: center;
}
.metric-card-label { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
.metric-card-value { color: var(--navy); font-size: 1.4rem; font-weight: 800; }
.metric-card-sub   { color: var(--text-muted); font-size: 0.72rem; margin-top: 3px; }

/* ── Tabla TCO ── */
.tco-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
}
.tco-row:last-child { border-bottom: none; }
.tco-label { color: var(--text-muted); font-weight: 500; }
.tco-value { color: var(--navy); font-weight: 700; }
.tco-total-row { background: var(--gold-light); border-radius: 8px; padding: 12px 14px; margin-top: 8px; }
.tco-total-label { color: var(--navy); font-weight: 700; font-size: 0.95rem; }
.tco-total-value { color: var(--navy); font-weight: 800; font-size: 1.05rem; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--bg-soft) !important;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .stSelectbox label { color: var(--navy) !important; }

/* ── Divider dorado ── */
.gold-divider {
    height: 3px;
    background: linear-gradient(90deg, var(--gold), transparent);
    border-radius: 2px;
    margin: 1.4rem 0;
}

/* ── Badge tenant ── */
.tenant-badge {
    display: inline-block;
    background: var(--navy);
    color: #fff;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    letter-spacing: 0.5px;
    margin-top: 6px;
}

/* ── Info pill ── */
.info-pill {
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-left: 4px solid var(--gold);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)


GOLD_DIVIDER = '<div class="gold-divider"></div>'

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem;">
        <div style="color:#1E3A5F; font-size:1.1rem; font-weight:800; letter-spacing:-0.3px;">SmartHome Valuator</div>
        <div style="color:#5A6A7E; font-size:0.75rem; margin-top:2px;">Plataforma B2B · Bogotá</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(GOLD_DIVIDER, unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.78rem;font-weight:700;color:#1E3A5F;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">Cliente activo</p>', unsafe_allow_html=True)
    tenant_label = st.selectbox("", list(TENANTS.keys()), label_visibility="collapsed")
    tenant_id = TENANTS[tenant_label]

    nombre_corto = "Banco Nacional" if tenant_id == "tenant_a" else "Portal Inmobiliario"
    st.markdown(f'<div class="tenant-badge">{tenant_id}</div>', unsafe_allow_html=True)

    st.markdown(GOLD_DIVIDER, unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.78rem;font-weight:700;color:#1E3A5F;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">Estrato socioeconómico</p>', unsafe_allow_html=True)
    estrato = st.select_slider("", options=[1, 2, 3, 4, 5, 6], value=4, label_visibility="collapsed")

    costos = COSTOS_ESTRATO[estrato]
    st.markdown(f"""
    <div style="background:#F0F4F8;border-left:3px solid #C8A84B;border-radius:6px;
                padding:10px 12px;margin-top:8px;font-size:0.78rem;color:#1A2636;">
        <strong>Costos estimados · Estrato {estrato}</strong><br>
        <span style="color:#5A6A7E;">Acueducto:</span> $ {costos['acueducto']:,}<br>
        <span style="color:#5A6A7E;">Energía:</span> $ {costos['energia']:,}<br>
        <span style="color:#5A6A7E;">Admin:</span> $ {costos['admin']:,}
    </div>
    <p style="font-size:0.7rem;color:#9aabb8;margin-top:6px;">
        Solo afectan el TCO · no la tasación
    </p>
    """, unsafe_allow_html=True)

    st.markdown(GOLD_DIVIDER, unsafe_allow_html=True)

    st.markdown("""
    <div class="info-pill">
        <strong>¿Cómo usar?</strong><br>
        1. Selecciona el tenant y estrato.<br>
        2. Completa los datos del inmueble.<br>
        3. Presiona <strong>Evaluar inmueble</strong>.<br>
        4. Revisa precio y TCO proyectado.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="position:absolute;bottom:1.5rem;left:0;right:0;text-align:center;">
        <span style="font-size:0.7rem;color:#9aabb8;">API: localhost:8082</span>
    </div>
    """, unsafe_allow_html=True)


# ── Topbar ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="topbar">
    <div>
        <div class="topbar-title">Valoración Inmobiliaria</div>
    </div>
    <div class="topbar-badge">{nombre_corto}</div>
</div>
""", unsafe_allow_html=True)


# ── Formulario ────────────────────────────────────────────────────────────────
with st.form("form_valuacion"):
    col1, col2, col3 = st.columns([1, 1, 1], gap="medium")

    with col1:
        st.markdown('<div class="section-title">Operación y Ubicación</div>', unsafe_allow_html=True)
        tipo_operacion = st.selectbox("Tipo de operación", ["Venta", "Arriendo"])
        tipo_inmueble  = st.selectbox("Tipo de inmueble", ["Apartamento", "Casa"])
        localidad      = st.selectbox("Localidad", LOCALIDADES, index=3)
        upz            = st.selectbox("UPZ (opcional)", UPZ_OPTIONS)

    with col2:
        st.markdown('<div class="section-title">Características Físicas</div>', unsafe_allow_html=True)
        area_m2         = st.number_input("Área (m²)", min_value=20.0, max_value=600.0, value=80.0, step=5.0)
        habitaciones    = st.slider("Habitaciones", 1, 8, 3)
        banos           = st.slider("Baños", 1, 6, 2)
        antiguedad_anos = st.number_input("Antigüedad (años)", min_value=0, max_value=80, value=10)
        col2a, col2b    = st.columns(2)
        parqueadero     = col2a.checkbox("Parqueadero", value=True)
        deposito        = col2b.checkbox("Depósito", value=False)

    with col3:
        st.markdown('<div class="section-title">Entorno</div>', unsafe_allow_html=True)
        latitud          = st.number_input("Latitud", value=4.6500, format="%.4f", step=0.0001)
        longitud         = st.number_input("Longitud", value=-74.0500, format="%.4f", step=0.0001)
        indice_seguridad = st.slider("Índice de seguridad (0 – 10)", 0.0, 10.0, 6.0, 0.5)
        hurto_res_100k   = st.number_input("Hurto residencial / 100k hab", min_value=0.0, value=150.0, step=10.0)

    # Costos derivados del estrato (no editables — solo para TCO)
    acueducto_mes = float(costos["acueducto"])
    energia_mes   = float(costos["energia"])
    admin_mensual = float(costos["admin"])

    st.markdown("<br>", unsafe_allow_html=True)
    submitted = st.form_submit_button(
        "Evaluar inmueble",
        use_container_width=True,
        type="primary",
    )


# ── Resultados ────────────────────────────────────────────────────────────────
if submitted:
    payload = {
        "tipo_operacion":   tipo_operacion,
        "area_m2":          area_m2,
        "habitaciones":     habitaciones,
        "banos":            banos,
        "antiguedad_anos":  float(antiguedad_anos),
        "estrato":          estrato,
        "latitud":          latitud,
        "longitud":         longitud,
        "hurto_res_100k":   hurto_res_100k,
        "indice_seguridad": indice_seguridad,
        "acueducto_mes":    float(acueducto_mes),
        "energia_mes":      float(energia_mes),
        "admin_mensual":    float(admin_mensual),
        "tipo_inmueble":    tipo_inmueble,
        "localidad":        localidad,
        "upz":              upz,
        "parqueadero":      1 if parqueadero else 0,
        "deposito":         1 if deposito else 0,
    }

    with st.spinner("Consultando modelo de valoración..."):
        try:
            resp = requests.post(
                f"{API_URL}/valorar",
                json=payload,
                headers={"x-tenant-id": tenant_id},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            st.error("No se pudo conectar con el backend. Verifica que `uvicorn api:app --port 8082` esté corriendo.")
            st.stop()
        except requests.exceptions.HTTPError:
            st.error(f"Error del API ({resp.status_code}): {resp.json().get('detail', 'Error desconocido')}")
            st.stop()

    det = data["tco_detalle"]
    precio = data["precio_estimado"]
    tco    = data["tco_anual"]

    st.markdown(GOLD_DIVIDER, unsafe_allow_html=True)

    # Encabezado de resultados
    st.markdown(f"""
    <p style="font-size:0.75rem;font-weight:700;color:#5A6A7E;text-transform:uppercase;
    letter-spacing:1px;margin-bottom:0.8rem;">
    Resultado — {data['tenant_nombre']} · {tipo_operacion} · Estrato {estrato} · {localidad}
    </p>
    """, unsafe_allow_html=True)

    # Tarjeta hero — Precio estimado
    st.markdown(f"""
    <div class="result-hero">
        <div class="result-hero-label">Precio Estimado de Mercado</div>
        <div class="result-hero-value">$ {precio:,.0f} COP</div>
        <div class="result-hero-sub">Predicción XGBoost · {tipo_inmueble} · {area_m2:.0f} m² · Estrato {estrato}</div>
    </div>
    """, unsafe_allow_html=True)

    # Tarjetas secundarias
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-card-label">TCO Anual Proyectado</div>
            <div class="metric-card-value">$ {tco:,.0f}</div>
            <div class="metric-card-sub">Costo Total de Propiedad · COP/año</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-card-label">TCO Mensual Equivalente</div>
            <div class="metric-card-value">$ {tco/12:,.0f}</div>
            <div class="metric-card-sub">Promedio mensual · COP/mes</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        ratio = (tco / precio * 100) if precio > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-card-label">Ratio TCO / Precio</div>
            <div class="metric-card-value">{ratio:.1f}%</div>
            <div class="metric-card-sub">Costo anual sobre valor del inmueble</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Desglose TCO
    col_graf, col_tabla = st.columns([3, 2], gap="large")

    with col_graf:
        st.markdown('<p style="font-size:0.78rem;font-weight:700;color:#1E3A5F;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.6rem;">Desglose del TCO Anual</p>', unsafe_allow_html=True)
        valores = [det["servicios_anuales"], det["admin_anual"], det["riesgo_desvalorizacion"]]
        etiquetas = ["Servicios (acueducto + energía)", "Administración", "Riesgo desvalorización"]
        fig = go.Figure(go.Bar(
            x=valores,
            y=etiquetas,
            orientation="h",
            marker_color=["#1E3A5F", "#2C5282", "#C8A84B"],
            text=[f"$ {v:,.0f}" for v in valores],
            textposition="outside",
            textfont={"size": 11, "color": "#1A2636"},
        ))
        fig.update_layout(
            height=240,
            margin={"l": 0, "r": 140, "t": 10, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis={"showgrid": False, "showticklabels": False, "zeroline": False},
            yaxis={"tickfont": {"size": 12, "color": "#1A2636"}, "automargin": True},
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_tabla:
        st.markdown('<p style="font-size:0.78rem;font-weight:700;color:#1E3A5F;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.6rem;">Componentes del TCO</p>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:#FAFBFD;border:1px solid #D6E0EC;border-radius:12px;padding:1.2rem;">
            <div class="tco-row">
                <span class="tco-label">Servicios anuales</span>
                <span class="tco-value">$ {det['servicios_anuales']:,.0f}</span>
            </div>
            <div class="tco-row">
                <span class="tco-label">Administración anual</span>
                <span class="tco-value">$ {det['admin_anual']:,.0f}</span>
            </div>
            <div class="tco-row">
                <span class="tco-label">Riesgo desvalorización</span>
                <span class="tco-value">$ {det['riesgo_desvalorizacion']:,.0f}</span>
            </div>
            <div class="tco-row tco-total-row" style="margin-top:12px;">
                <span class="tco-total-label">Total TCO Anual</span>
                <span class="tco-total-value">$ {det['total']:,.0f} COP</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

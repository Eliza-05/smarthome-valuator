# SmartHome Valuator

**Estudiantes:**
- Elizabeth Correa Suarez
- Juan Sebastián Ortega Muñoz
- Jeimy Alejandra Yaya Martinez

**Curso:** TDSE 2026-1

---

Plataforma analítica multi-tenant para valoración inmobiliaria residencial en Bogotá, Colombia. Sirve simultáneamente a múltiples organizaciones (bancos, portales inmobiliarios) sobre una infraestructura compartida con aislamiento de datos por cliente mediante schema-per-tenant en PostgreSQL, y expone los modelos a clientes B2B a través de una API REST y un dashboard institucional.

---

## Despliegue en producción (Azure)

| Componente | URL |
|---|---|
| Dashboard Streamlit | https://smarthome-dashboard.azurewebsites.net |
| API B2B — Swagger UI | https://smarthome-api-b2b.azurewebsites.net/docs |
| API B2B — Endpoint | https://smarthome-api-b2b.azurewebsites.net/valorar |
| PostgreSQL | smarthome-pg.postgres.database.azure.com:5432 |


---

## Modelos implementados

| Modelo | Propósito | R² | RMSE | MAE |
|---|---|---|---|---|
| XGBoost Venta | Predice precio de mercado para inmuebles en venta | 0.9604 | ~78 M COP | ~29 M COP |
| XGBoost Arriendo | Predice precio de mercado para inmuebles en arriendo | 0.8480 | 1,131,019 COP | 359,988 COP |

Entrenados con partición **70% train / 15% validación / 15% test** sobre el dataset `SmartHome_Valuator_Dataset_CLEAN.csv` (propiedades de Bogotá).

### Features del modelo (14 variables estructurales y locacionales)

| Categoría | Variables |
|---|---|
| Físicas | Área (m²), Habitaciones, Baños, Antigüedad (años), Parqueadero, Depósito |
| Locacionales | Estrato, Latitud, Longitud, Localidad, UPZ, Tipo Inmueble |
| Entorno | Hurto Res./100k hab, Índice Seguridad (0–10) |

> Los costos de servicios públicos (energía, acueducto, administración) se excluyen del modelo para evitar correlación espuria con el estrato. Solo se usan para el cálculo del TCO.

### Módulo TCO

```
TCO anual = (acueducto + energía) × 12
          + administración × 12
          + precio_estimado × (10 − índice_seguridad) / 100
```

Los costos mensuales se estiman automáticamente por estrato según referencias de Bogotá.

---

## Arquitectura

### Despliegue en Azure

```
Tenants
  ├── Banco Nacional ──────────────────────────────────────────┐
  └── Portal Inmobiliario ──────────────────────────────────── HTTPS
                                                               ▼
                                              ┌─────────────────────────┐
                                              │   Azure App Service      │
                                              │   API B2B (FastAPI)      │
                                              │   x-tenant-id auth       │
                                              │   /valorar + TCO         │
                                              └────────────┬────────────┘
                                                           │
                              ┌────────────────────────────┘
                              │
              ┌───────────────▼───────────────────────┐
              │         Azure Container Apps           │
              │  ┌─────────────┐  ┌────────────────┐  │
              │  │ ML Service  │  │  ETL Service   │  │
              │  │ XGBoost·TCO │  │ Pipeline·feat. │  │
              │  └─────────────┘  └───────┬────────┘  │
              └──────────────────────────-┼────────────┘
                                          │ schema_tenant
                              ┌───────────▼────────────┐
                              │  PostgreSQL Flexible    │
                              │  Multi-tenant schemas   │
                              └────────────────────────┘
```

### Ejecución local (Docker Compose)

```
┌──────────────────────────────────────────────────────────────┐
│                       Docker Compose                         │
│                                                              │
│  ┌──────────┐   ┌────────────┐   ┌──────────────────────┐   │
│  │ postgres │   │ etl_service│   │      ml_service       │   │
│  │  :5433   │◄──│  (job)     │   │        :8001          │   │
│  └──────────┘   └────────────┘   └──────────┬───────────┘   │
│       ▲                                     ▲               │
│       └─────────────┬───────────────────────┘               │
│                     │  api_service :8000                     │
│                     └──────────────────────────────────────  │
└──────────────────────────────────────────────────────────────┘
         ▲                        ▲
   tenant_a.py              tenant_b.py
   (banco, 50 req)      (portal, 80 req)

─────────────────────────────────────────────────
              Capa de Exposición B2B
─────────────────────────────────────────────────
  api.py (FastAPI :8082) ◄── dashboard.py (Streamlit)
  • Header X-Tenant-ID         • Interfaz institucional
  • Endpoint /valorar           • Gráfico TCO (Plotly)
  • Respuesta con TCO detallado • Costos por estrato
```

### Servicios Docker

| Servicio | Puerto | Rol |
|---|---|---|
| `postgres` | 5433 (host) | Base de datos con schemas por tenant |
| `etl_service` | — | Job único: limpia el CSV y carga datos en PostgreSQL |
| `ml_service` | 8001 | Inferencia XGBoost (carga modelos .pkl) |
| `api_service` | 8000 | Gateway interno: autenticación, routing, persistencia |

### Capa de Exposición B2B (fuera de Docker)

| Componente | Puerto | Rol |
|---|---|---|
| `api.py` | 8082 | API B2B pública — autenticación por X-Tenant-ID, /valorar, Swagger |
| `dashboard.py` | 8501 | Dashboard Streamlit institucional para usuarios finales |

### Multi-tenancy

Patrón **schema-per-tenant** en PostgreSQL:

```
smarthouse_valuator
├── shared_data.propiedades      ← datos del ETL (compartido, solo lectura)
├── schema_tenant_a.solicitudes  ← exclusivo Banco Nacional
└── schema_tenant_b.solicitudes  ← exclusivo Portal Inmobiliario
```

Autenticación B2B mediante header `X-Tenant-ID`. Un tenant no puede acceder a los datos del otro bajo ninguna circunstancia.

---

## Stack tecnológico

- **Python 3.11** — todos los servicios
- **FastAPI** — API Gateway, ML Service y B2B API
- **Streamlit 1.57** — dashboard institucional B2B
- **Plotly** — visualización interactiva del TCO
- **XGBoost 3.2** — modelos de predicción de precios
- **scikit-learn 1.6** — preprocesamiento y métricas
- **pandas** — ETL y manipulación de datos
- **joblib** — serialización de modelos
- **psycopg2** — conexión a PostgreSQL
- **PostgreSQL 15** — base de datos multi-tenant
- **Docker + Docker Compose** — orquestación local
- **Azure App Service** — hosting API B2B y Dashboard en producción
- **Azure Container Apps** — orquestación de servicios ML y ETL
- **Azure Container Registry** — almacenamiento de imágenes Docker
- **Azure Database for PostgreSQL Flexible Server** — base de datos en producción

---

## Estructura del repositorio

```
smarthome-valuator/
├── api.py                          # API B2B pública (FastAPI)
├── dashboard.py                    # Dashboard Streamlit institucional
├── train_reduced.py                # Script de reentrenamiento (features reducidas)
├── startup.sh                      # Script de inicio para Azure App Service (API)
├── startup-dashboard.sh            # Script de inicio para Azure App Service (Dashboard)
├── docker-compose.yml
├── .env.example
├── .streamlit/
│   └── config.toml                 # Tema visual del dashboard
├── data/
│   ├── raw/
│   │   └── SmartHome_Valuator_Dataset_CLEAN.csv
│   └── processed/
├── docs/
│   ├── azure-deployment.md         # Guía de despliegue en Azure
│   └── resultados-evaluacion.md    # Resultados y conclusiones del artículo
├── notebooks/
│   └── 01_eda_and_training.ipynb   # EDA + entrenamiento XGBoost
├── services/
│   ├── etl/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   ├── ml/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   └── models/
│   │       ├── xgboost_venta.pkl
│   │       ├── xgboost_arriendo.pkl
│   │       ├── encoders_venta.pkl
│   │       └── encoders_arriendo.pkl
│   └── api/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── main.py
├── database/
│   └── init.sql
├── tenants/
│   ├── tenant_a.py                 # Simula Banco Nacional (50 req concurrentes)
│   └── tenant_b.py                 # Simula Portal Inmobiliario (80 req concurrentes)
└── monitoring/
    └── report.py
```

---

## Requisitos previos

- Docker Desktop instalado y corriendo
- Python 3.11+
- Entorno virtual activado:

```powershell
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac
pip install -r services/ml/requirements.txt
pip install streamlit plotly requests
```

---

## Cómo ejecutar (local)

### 1. Configurar variables de entorno

```powershell
cp .env.example .env
# Editar .env con las credenciales de PostgreSQL
```

### 2. Entrenar los modelos

```powershell
# Opción A — notebook
jupyter notebook notebooks/01_eda_and_training.ipynb

# Opción B — script directo
python train_reduced.py
```

Al finalizar se generan 4 artefactos en `services/ml/models/`.

### 3. Levantar la infraestructura Docker

```powershell
docker compose up --build
```

### 4. Iniciar la API B2B pública

```powershell
uvicorn api:app --host 0.0.0.0 --port 8082 --reload
```

Swagger UI disponible en: `http://localhost:8082/docs`

### 5. Iniciar el dashboard

```powershell
streamlit run dashboard.py
```

Dashboard disponible en: `http://localhost:8501`

### 6. Ejecutar los tenants simultáneamente (prueba de carga)

```powershell
# Terminal 1
python tenants/tenant_a.py

# Terminal 2 (al mismo tiempo)
python tenants/tenant_b.py
```

---

## Endpoints de la API B2B

### `POST /valorar`

Valora un inmueble y calcula el TCO.

**Header requerido:** `x-tenant-id: tenant_a` o `tenant_b`

**Body:**
```json
{
  "tipo_operacion": "Venta",
  "area_m2": 80,
  "habitaciones": 3,
  "banos": 2,
  "antiguedad_anos": 10,
  "estrato": 4,
  "latitud": 4.65,
  "longitud": -74.05,
  "localidad": "Chapinero",
  "upz": "El Refugio",
  "tipo_inmueble": "Apartamento",
  "parqueadero": 1,
  "deposito": 0,
  "indice_seguridad": 6.5,
  "hurto_res_100k": 150,
  "acueducto_mes": 120000,
  "energia_mes": 180000,
  "admin_mensual": 400000
}
```

**Respuesta:**
```json
{
  "tenant_id": "tenant_a",
  "tenant_nombre": "Banco Nacional",
  "tipo_operacion": "Venta",
  "precio_estimado": 461120544.0,
  "tco_anual": 24539219.04,
  "tco_detalle": {
    "servicios_anuales": 3600000.0,
    "admin_anual": 4800000.0,
    "riesgo_desvalorizacion": 16139219.04,
    "total": 24539219.04
  }
}
```

### `GET /`

Estado de la API y modelos disponibles.

---

## Resultados de evaluación (Azure)

> Documento completo: [`docs/resultados-evaluacion.md`](docs/resultados-evaluacion.md)

### Modelos de predicción

| Modelo | R² | RMSE | MAE |
|---|---|---|---|
| XGBoost Venta | **0.9604** | ~78 M COP | ~29 M COP |
| XGBoost Arriendo | **0.8480** | 1,131,019 COP | 359,988 COP |

### Pruebas de concurrencia multi-tenant

| Métrica | Tenant A — Banco Nacional | Tenant B — Portal Inmobiliario |
|---|---|---|
| Solicitudes enviadas | 200 | 500 |
| Exitosas | 200 | 500 |
| Fallidas | 0 | 0 |
| Tasa de éxito | 100% | 100% |
| Precio estimado promedio | $416,553,392 COP | $220,748,647 COP |
| Throughput | 6.5 req/s | 5.0 req/s |
| Latencia promedio | 28,225 ms | 77,668 ms |
| Latencia p95 | 30,372 ms | 97,972 ms |

**Aislamiento verificado:** los registros de cada tenant quedan exclusivamente en su propio schema de PostgreSQL (`schema_tenant_a` y `schema_tenant_b`).

### Stress test progresivo

| Oleada | Requests | Tasa éxito | Throughput | Latencia p95 | Estado |
|---|---|---|---|---|---|
| 1 | 50 | 100% | 5.9 req/s | 8,426 ms | ✅ OK |
| 2 | 100 | 100% | 4.9 req/s | 19,673 ms | ✅ OK |
| 3 | 200 | 99.0% | 7.2 req/s | 21,172 ms | ✅ OK |
| 4 | 400 | 100% | 6.0 req/s | 62,808 ms | ✅ OK |
| 5 | 800 | 90.9% | 5.9 req/s | 93,115 ms | ⚠️ DEGRADADO |

El sistema mantiene estabilidad hasta ~400 requests estrictamente simultáneos. La degradación en 800 requests se debe al límite de la instancia única (plan B1); con auto-scaling horizontal escala sin modificar el código.

### Predicciones por estrato (modelo Venta)

| Estrato | Precio estimado |
|---|---|
| 1 | ~103 M COP |
| 2 | ~145 M COP |
| 3 | ~249 M COP |
| 4 | ~461 M COP |
| 5 | ~1,070 M COP |
| 6 | ~1,790 M COP |

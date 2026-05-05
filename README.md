# SmartHome Valuator

Plataforma analítica multi-tenant para valoración inmobiliaria residencial en Bogotá, Colombia. Sirve simultáneamente a múltiples organizaciones (bancos, portales inmobiliarios) sobre una infraestructura compartida con aislamiento de datos por cliente mediante schema-per-tenant en PostgreSQL.

---

## Modelos implementados

| Modelo | Propósito | R² | RMSE | MAE |
|---|---|---|---|---|
| XGBoost Venta | Predice precio de mercado para inmuebles en venta | 0.9375 | 91,414,842 COP | 37,710,680 COP |
| XGBoost Arriendo | Predice precio de mercado para inmuebles en arriendo | 0.8480 | 1,131,019 COP | 359,988 COP |

Entrenados con partición **70% train / 15% validación / 15% test** sobre el dataset `SmartHome_Valuator_Dataset_CLEAN.csv` (propiedades de Bogotá).

El **módulo TCO** (Total Cost of Ownership) calcula el costo anual de habitar un inmueble:

```
TCO anual = (acueducto + energía) × 12 + administración × 12 + precio × factor_riesgo_seguridad
```

---

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                   Docker Compose                    │
│                                                     │
│  ┌──────────┐   ┌────────────┐   ┌───────────────┐ │
│  │ postgres │   │ etl_service│   │   ml_service  │ │
│  │  :5433   │◄──│  (job)     │   │    :8001      │ │
│  └──────────┘   └────────────┘   └───────┬───────┘ │
│       ▲                                  ▲         │
│       │         ┌────────────────────────┘         │
│       └─────────┤      api_service :8000            │
│                 └────────────────────────────────── │
└─────────────────────────────────────────────────────┘
         ▲                      ▲
   tenant_a.py            tenant_b.py
   (banco, 50 req)    (portal, 80 req)
```

### Servicios

| Servicio | Puerto | Rol |
|---|---|---|
| `postgres` | 5433 (host) | Base de datos con schemas por tenant |
| `etl_service` | — | Job único: limpia el CSV y carga datos en PostgreSQL |
| `ml_service` | 8001 | Inferencia XGBoost + cálculo TCO |
| `api_service` | 8000 | Gateway: autenticación, routing, persistencia |

### Multi-tenancy

Patrón **schema-per-tenant** en PostgreSQL:

```
smarthouse_valuator
├── shared_data.propiedades      ← datos del ETL (compartido, solo lectura)
├── schema_tenant_a.solicitudes  ← exclusivo banco
└── schema_tenant_b.solicitudes  ← exclusivo portal inmobiliario
```

Cada request se identifica con un header `X-API-Key`. Un tenant no puede acceder a los datos del otro bajo ninguna circunstancia.

---

## Stack tecnológico

- **Python 3.11** — todos los servicios
- **FastAPI** — API Gateway y ML Service
- **XGBoost 3.x** — modelos de predicción de precios
- **scikit-learn** — preprocesamiento y métricas
- **pandas** — ETL y manipulación de datos
- **joblib** — serialización de modelos
- **psycopg2** — conexión a PostgreSQL
- **PostgreSQL 15** — base de datos multi-tenant
- **Docker + Docker Compose** — orquestación

---

## Estructura del repositorio

```
smarthome-valuator/
├── docker-compose.yml
├── .env.example
├── data/
│   ├── raw/
│   │   └── SmartHome_Valuator_Dataset_CLEAN.csv
│   └── processed/
├── notebooks/
│   └── 01_eda_and_training.ipynb   # EDA + entrenamiento XGBoost
├── services/
│   ├── etl/                        # Pipeline ETL (job único)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   ├── ml/                         # Inferencia XGBoost + TCO
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   └── models/
│   │       ├── xgboost_venta.pkl
│   │       ├── xgboost_arriendo.pkl
│   │       ├── encoders_venta.pkl
│   │       └── encoders_arriendo.pkl
│   └── api/                        # Gateway, autenticación, routing
│       ├── Dockerfile
│       ├── requirements.txt
│       └── main.py
├── database/
│   └── init.sql
├── tenants/
│   ├── tenant_a.py                 # Simula banco (50 req concurrentes)
│   └── tenant_b.py                 # Simula portal (80 req concurrentes)
└── monitoring/
    └── report.py
```

---

## Requisitos previos

- Docker Desktop instalado y corriendo
- Python 3.11+
- Dependencias locales (para notebook y scripts de tenants):

```bash
pip install pandas numpy matplotlib seaborn scikit-learn xgboost joblib httpx psycopg2-binary python-dotenv
```

---

## Cómo ejecutar

### 1. Configurar variables de entorno

```bash
cp .env.example .env
```

### 2. Entrenar los modelos (una sola vez)

Abrir y ejecutar completamente el notebook:

```bash
jupyter notebook notebooks/01_eda_and_training.ipynb
```

Kernel → Restart & Run All. Al finalizar se generan los 4 artefactos en `services/ml/models/`.

### 3. Levantar la infraestructura

```bash
docker compose up --build
```

Esperar hasta que `api_service` y `ml_service` estén corriendo (≈ 3-5 min la primera vez).

### 4. Verificar que la API responde

```bash
curl http://localhost:8000/health
```

Respuesta esperada: `{"status":"ok"}`

### 5. Ejecutar los tenants simultáneamente

```bash
# Terminal 1
python tenants/tenant_a.py

# Terminal 2 (al mismo tiempo)
python tenants/tenant_b.py
```

### 6. Ver el reporte de métricas

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python monitoring/report.py
```

---

## Endpoints de la API

### `POST /avaluo`
Solicita la valoración de un inmueble.

**Header:** `X-API-Key: key-tenant-a` o `key-tenant-b`

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
  "acueducto_mes": 120000,
  "energia_mes": 180000,
  "admin_mensual": 500000
}
```

**Respuesta:**
```json
{
  "precio_estimado": 450000000,
  "tco_anual": 12840000,
  "tenant_id": "tenant_a",
  "latencia_ms": 45
}
```

### `GET /metrics`
Resumen de solicitudes y latencias por tenant.

```json
{
  "tenant_a": { "total_requests": 51, "avg_latency_ms": 180.1 },
  "tenant_b": { "total_requests": 80, "avg_latency_ms": 205.1 }
}
```

---

## Resultados del experimento de concurrencia

| Métrica | Tenant A (Banco) | Tenant B (Portal) |
|---|---|---|
| Solicitudes enviadas | 50 | 80 |
| Exitosas | 50 | 80 |
| Fallidas | 0 | 0 |
| Latencia promedio | ~90 ms | ~76 ms |
| Latencia máxima | ~203 ms | ~201 ms |
| Throughput | ~3.3 req/s | ~5.8 req/s |
| Precio promedio Venta | 122,400,523 COP | 109,425,850 COP |
| Precio promedio Arriendo | — | 660,136 COP |
| TCO anual promedio | 13,621,549 COP | 9,744,826 COP |

**Aislamiento verificado:** los registros de cada tenant quedaron exclusivamente en su propio schema de PostgreSQL (schema_tenant_a y schema_tenant_b).

> **Nota sobre el modelo Venta:** XGBoost asignó ~40% de importancia a `Energía Eléctrica (COP/mes)`, lo que genera extrapolaciones fuera del rango real para propiedades de estrato 2-3 con facturas bajas. Se aplica un piso de 50 M COP en el ML Service para garantizar predicciones válidas.

---

## Fuera del alcance (trabajo futuro)

- Frontend o dashboard visual
- Reentrenamiento automático periódico del modelo
- Onboarding automatizado de nuevos tenants
- Integración en tiempo real con fuentes externas (SIEDCO, CREG)
- Pipeline CI/CD
- Despliegue en nube (Azure)

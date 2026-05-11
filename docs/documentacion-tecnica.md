# Documentación Técnica — SmartHome Valuator

**Curso:** TDSE 2026-1  
**Estudiantes:** Elizabeth Correa Suarez · Juan Sebastián Ortega Muñoz · Jeimy Alejandra Yaya Martinez

---

## Índice

1. [Visión general del sistema](#1-visión-general-del-sistema)
2. [Pipeline de datos — ETL Service](#2-pipeline-de-datos--etl-service)
3. [Modelo de Machine Learning — XGBoost](#3-modelo-de-machine-learning--xgboost)
4. [API B2B Pública — api.py](#4-api-b2b-pública--apipy)
5. [API Gateway interna — services/api](#5-api-gateway-interna--servicesapi)
6. [Base de datos multi-tenant — PostgreSQL](#6-base-de-datos-multi-tenant--postgresql)
7. [Dashboard institucional — dashboard.py](#7-dashboard-institucional--dashboardpy)
8. [Simulación de tenants y pruebas de carga](#8-simulación-de-tenants-y-pruebas-de-carga)
9. [Flujo completo de una solicitud](#9-flujo-completo-de-una-solicitud)

---

## 1. Visión general del sistema

SmartHome Valuator es una plataforma analítica **multi-tenant** para valoración inmobiliaria residencial en Bogotá. El sistema sirve simultáneamente a múltiples organizaciones (un banco y un portal inmobiliario) sobre infraestructura compartida, con aislamiento total de datos por cliente.

### Componentes principales

```
[Tenants externos]
  tenant_a.py  (Banco Nacional)
  tenant_b.py  (Portal Inmobiliario)
       │
       │  HTTPS  x-tenant-id header
       ▼
[api.py — FastAPI :8082 / Azure App Service]
  • Autenticación por X-Tenant-ID
  • Preprocesamiento de features
  • Inferencia XGBoost directa
  • Cálculo de TCO
  • Persistencia en PostgreSQL
       │
       ▼
[PostgreSQL — Azure Flexible Server]
  shared_data.propiedades
  schema_tenant_a.solicitudes
  schema_tenant_b.solicitudes

[dashboard.py — Streamlit / Azure App Service]
  • Interfaz institucional B2B
  • Llama a api.py vía HTTP
```

En entorno local con Docker Compose existe también un **API Gateway** (`services/api`) que enruta al **ML Service** (`services/ml`) como microservicio independiente. En producción Azure esta arquitectura se simplifica: `api.py` carga los modelos directamente en memoria sin necesidad del microservicio intermediario.

---

## 2. Pipeline de datos — ETL Service

**Archivo:** `services/etl/main.py`  
**Ejecuta:** una sola vez como job (no es un servidor)

### Función `load_and_clean()`

Lee el CSV crudo (`SmartHome_Valuator_Dataset_CLEAN.csv`) y aplica las siguientes transformaciones:

| Paso | Acción |
|---|---|
| Filtro de target | Elimina filas sin `PRECIO MERCADO (COP) ★` o con precio ≤ 0 |
| Filtro de features críticos | Elimina filas sin `Área (m²)`, `Habitaciones`, `Baños` o `Estrato` |
| Normalización booleana | `"Sí"` → `True`, `"No"` → `False` en `Parqueadero` y `Depósito` |
| Imputación numérica | Rellena nulos con la mediana de cada columna numérica |
| Guardado | Exporta el dataset limpio a `data/processed/` |

### Función `insert_to_postgres()`

Carga el dataset procesado en la tabla `shared_data.propiedades` usando `execute_values` (inserción en lote, eficiente). La cláusula `ON CONFLICT (id) DO NOTHING` garantiza idempotencia: ejecutar el ETL varias veces no duplica registros.

---

## 3. Modelo de Machine Learning — XGBoost

### 3.1 Algoritmo: Gradient Boosting con XGBoost

XGBoost (Extreme Gradient Boosting) es un algoritmo de ensamble que construye árboles de decisión secuencialmente. Cada árbol nuevo corrige los errores del árbol anterior, minimizando una función de pérdida (error cuadrático medio para regresión).

**¿Por qué XGBoost para este problema?**
- Maneja bien variables mixtas (numéricas + categóricas codificadas)
- Robusto ante outliers en precios inmobiliarios (que tienen distribución muy sesgada)
- No requiere normalización de features
- Alto desempeño empírico en datasets tabulares de tamaño medio

### 3.2 Features del modelo (14 variables)

Los costos de servicios públicos (`acueducto`, `energía`, `admin`) se excluyen deliberadamente del modelo para **evitar correlación espuria** con el estrato: esas variables se usan solo en el cálculo del TCO.

| Categoría | Variable | Descripción |
|---|---|---|
| **Físicas** | `Área (m²)` | Superficie habitable |
| | `Habitaciones` | Número de habitaciones |
| | `Baños` | Número de baños |
| | `Antigüedad (años)` | Años desde construcción |
| | `Parqueadero` | 1 = tiene, 0 = no tiene |
| | `Depósito` | 1 = tiene, 0 = no tiene |
| **Locacionales** | `Estrato` | Estrato socioeconómico (1–6) |
| | `Latitud` | Coordenada geográfica |
| | `Longitud` | Coordenada geográfica |
| | `Localidad` | Localidad de Bogotá (label encoded) |
| | `UPZ` | Unidad de Planeamiento Zonal (label encoded) |
| | `Tipo Inmueble` | Apartamento / Casa (label encoded) |
| **Entorno** | `Hurto Res./100k hab` | Tasa de hurto residencial por zona |
| | `Índice Seguridad (0-10)` | Índice de percepción de seguridad |

### 3.3 Variables categóricas — Label Encoding

Las variables `Localidad`, `UPZ` y `Tipo Inmueble` son strings que XGBoost no puede procesar directamente. Se aplica **Label Encoding** con `sklearn.preprocessing.LabelEncoder`: a cada valor único se le asigna un entero.

Los encoders se serializan junto con el modelo:
```
models/
├── xgboost_venta.pkl      ← modelo entrenado para operaciones de Venta
├── xgboost_arriendo.pkl   ← modelo entrenado para operaciones de Arriendo
├── encoders_venta.pkl     ← dict con LabelEncoders {localidad, upz, tipo_inmueble}
└── encoders_arriendo.pkl  ← ídem para Arriendo
```

Si en inferencia llega un valor de localidad que no existía en el dataset de entrenamiento, se asigna `0` por defecto (evita errores en producción).

### 3.4 Partición del dataset y métricas

| Partición | Proporción | Uso |
|---|---|---|
| Train | 70% | Ajuste de parámetros del modelo |
| Validación | 15% | Early stopping y tuning de hiperparámetros |
| Test | 15% | Evaluación final (no visto durante entrenamiento) |

| Modelo | R² | RMSE | MAE |
|---|---|---|---|
| XGBoost Venta | **0.9604** | ~78,000,000 COP | ~29,000,000 COP |
| XGBoost Arriendo | **0.8480** | 1,131,019 COP | 359,988 COP |

El R² de 0.96 en Venta indica que el modelo explica el 96% de la varianza en los precios de venta — nivel adecuado para soporte a decisiones de crédito hipotecario.

### 3.5 Serialización y carga en producción

Los modelos se serializan con `joblib` (más eficiente que `pickle` para objetos numpy/sklearn). En el arranque de la API se cargan en memoria una sola vez:

```python
# api.py — carga al inicio, no en cada request
@app.on_event("startup")
def load_artifacts():
    for tipo in ("venta", "arriendo"):
        models[tipo] = joblib.load(f"{MODELS_DIR}/xgboost_{tipo}.pkl")
        encoders[tipo] = joblib.load(f"{MODELS_DIR}/encoders_{tipo}.pkl")
```

Los modelos quedan en memoria RAM durante toda la vida del proceso, por lo que la inferencia es O(ms) — no hay I/O en cada predicción.

### 3.6 Módulo TCO (Costo Total de Propiedad)

El TCO no es parte del modelo ML: es una fórmula determinista calculada por la API después de obtener el precio estimado.

```
TCO anual = (acueducto_mes + energía_mes) × 12
          + admin_mensual × 12
          + precio_estimado × (10 − índice_seguridad) / 100
```

El tercer término modela el **riesgo de desvalorización**: a menor índice de seguridad, mayor el costo implícito de poseer el inmueble. El dashboard desglosa este TCO en tres componentes para el usuario final.

---

## 4. API B2B Pública — api.py

**Archivo:** `api.py`  
**Framework:** FastAPI  
**Puerto local:** 8082 | **Azure:** `https://smarthome-api-b2b.azurewebsites.net`

Es el único punto de entrada para los tenants en producción. Maneja autenticación, inferencia y persistencia de forma monolítica (sin microservicio intermediario).

### 4.1 Autenticación por X-Tenant-ID

```python
TENANTS = {
    "tenant_a": "Banco Nacional",
    "tenant_b": "Portal Inmobiliario",
}
```

El header `x-tenant-id` es requerido en cada request. Si el valor no está en `TENANTS`, la API responde `401 Unauthorized`. No se usan API Keys con secreto porque el sistema asume una red privada entre los tenants y la API en Azure; en un entorno de mayor seguridad se añadiría autenticación JWT o mTLS.

### 4.2 Endpoint `POST /valorar`

**Flujo interno:**

```
1. Validar x-tenant-id
2. Extraer tipo_operacion → seleccionar modelo (venta | arriendo)
3. Aplicar Label Encoding a localidad, upz, tipo_inmueble
4. Construir DataFrame con nombres de columnas del dataset original
5. model.predict(X) → precio_estimado
6. _calcular_tco(...) → tco_detalle
7. Persistir solicitud en schema del tenant (PostgreSQL)
8. Retornar ValorarResponse
```

**Modelo de datos entrada (`ValorarRequest`):**

```python
class ValorarRequest(BaseModel):
    tipo_operacion: str          # "Venta" | "Arriendo"
    area_m2: float
    habitaciones: int
    banos: int
    antiguedad_anos: float = 0.0
    estrato: int                 # 1–6
    latitud: float
    longitud: float
    hurto_res_100k: float = 0.0
    indice_seguridad: float = 5.0
    acueducto_mes: float = 0.0   # solo para TCO
    energia_mes: float = 0.0     # solo para TCO
    admin_mensual: float = 0.0   # solo para TCO
    tipo_inmueble: str = "Apartamento"
    localidad: str = "Chapinero"
    upz: str = ""
    parqueadero: int = 0         # 0 | 1
    deposito: int = 0            # 0 | 1
```

**Modelo de datos salida (`ValorarResponse`):**

```python
class ValorarResponse(BaseModel):
    tenant_id: str
    tenant_nombre: str
    tipo_operacion: str
    precio_estimado: float
    tco_anual: float
    tco_detalle: TCODetalle      # {servicios_anuales, admin_anual,
                                 #  riesgo_desvalorizacion, total}
```

### 4.3 Mapeo de columnas

Un detalle crítico de implementación: los modelos XGBoost se entrenaron con los nombres de columna del CSV original (con tildes y espacios). La API mapea los campos snake_case del JSON a esos nombres antes de construir el DataFrame:

```python
COL_MAP = {
    "area_m2":          "Área (m²)",
    "habitaciones":     "Habitaciones",
    "banos":            "Baños",
    "antiguedad_anos":  "Antigüedad (años)",
    # ... etc.
}
X = pd.DataFrame([{COL_MAP[k]: row[k] for k in FEATURE_KEYS}])
```

Si este mapeo faltara, el modelo lanzaría un error por nombres de features desconocidos.

### 4.4 Swagger UI

FastAPI genera automáticamente la documentación interactiva en `/docs`. En producción: `https://smarthome-api-b2b.azurewebsites.net/docs`

---

## 5. API Gateway interna — services/api

**Archivo:** `services/api/main.py`  
**Puerto:** 8000 (interno Docker)  
**Uso:** solo en despliegue local con Docker Compose

En la arquitectura local el API Gateway actúa como intermediario: autentica por `x-api-key`, reenvía la solicitud al ML Service vía HTTP, persiste el resultado en PostgreSQL y retorna la respuesta al cliente.

```
tenant_a.py / tenant_b.py
       │  x-api-key
       ▼
services/api/main.py  :8000
       │  HTTP POST /predict
       ▼
services/ml/main.py   :8001
       │
       ▼
PostgreSQL schema_tenant_x.solicitudes
```

Este servicio también expone `GET /metrics` que agrega estadísticas de ambos tenants desde la base de datos, útil para el `monitoring/report.py`.

---

## 6. Base de datos multi-tenant — PostgreSQL

**Patrón:** schema-per-tenant  
**Motor:** PostgreSQL 15 (local: Docker / producción: Azure Flexible Server, Canada Central)

### 6.1 Estructura de schemas

```sql
smarthouse_valuator
├── shared_data.propiedades       -- Dataset completo (solo lectura para tenants)
├── schema_tenant_a.solicitudes   -- Histórico exclusivo de Banco Nacional
└── schema_tenant_b.solicitudes   -- Histórico exclusivo de Portal Inmobiliario
```

### 6.2 Tabla `shared_data.propiedades`

Cargada por el ETL con todos los inmuebles del dataset. Es de solo lectura para los tenants; ningún tenant puede escribir aquí.

### 6.3 Tabla `schema_tenant_X.solicitudes`

Cada solicitud de valoración queda registrada en el schema exclusivo del tenant que la originó:

```sql
CREATE TABLE schema_tenant_a.solicitudes (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    features        JSONB NOT NULL,      -- payload completo del request
    tipo_operacion  VARCHAR(20),
    precio_estimado NUMERIC,
    tco_anual       NUMERIC,
    latencia_ms     INTEGER
);
```

El campo `features` guarda el JSON completo de la solicitud, permitiendo auditoría y reentrenamiento futuro.

### 6.4 Aislamiento mediante permisos PostgreSQL

Además de la separación por schema, se crean usuarios de base de datos con permisos restringidos:

```sql
-- tenant_a_user solo puede acceder a schema_tenant_a
GRANT USAGE ON SCHEMA schema_tenant_a TO tenant_a_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA schema_tenant_a TO tenant_a_user;

-- tenant_b_user solo puede acceder a schema_tenant_b
GRANT USAGE ON SCHEMA schema_tenant_b TO tenant_b_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA schema_tenant_b TO tenant_b_user;
```

Esto garantiza aislamiento en dos niveles: lógico (la aplicación enruta por schema) y físico (los usuarios de BD no tienen acceso cross-tenant).

---

## 7. Dashboard institucional — dashboard.py

**Archivo:** `dashboard.py`  
**Framework:** Streamlit 1.57  
**Puerto local:** 8501 | **Azure:** `https://smarthome-dashboard.azurewebsites.net`

Interfaz web institucional orientada al usuario final del tenant (analista de banco o asesor inmobiliario).

### 7.1 Funcionalidades

- **Selector de tenant:** el usuario elige entre Banco Nacional o Portal Inmobiliario; el header `x-tenant-id` se ajusta automáticamente
- **Formulario de valoración:** campos para todos los features del modelo, con valores predeterminados por estrato
- **Resultado visual:** precio estimado y TCO anual con desglose en tres componentes
- **Gráfico de barras (Plotly):** comparación visual de los tres componentes del TCO

### 7.2 Costos por estrato

El dashboard incorpora una tabla de costos mensuales de referencia por estrato (Bogotá) para precalcular los valores de `acueducto_mes`, `energia_mes` y `admin_mensual` cuando el usuario no los conoce:

```python
COSTOS_ESTRATO = {
    1: {"acueducto": 35_000,  "energia": 60_000,  "admin": 0},
    2: {"acueducto": 50_000,  "energia": 90_000,  "admin": 50_000},
    3: {"acueducto": 80_000,  "energia": 130_000, "admin": 150_000},
    4: {"acueducto": 120_000, "energia": 180_000, "admin": 400_000},
    5: {"acueducto": 180_000, "energia": 280_000, "admin": 800_000},
    6: {"acueducto": 250_000, "energia": 400_000, "admin": 1_500_000},
}
```

### 7.3 Comunicación con la API

El dashboard llama a `api.py` vía HTTP con `requests.post()`, pasando el header `x-tenant-id` según el tenant seleccionado. Es un cliente HTTP puro — no importa ni usa los modelos directamente.

---

## 8. Simulación de tenants y pruebas de carga

### 8.1 tenant_a.py — Banco Nacional

- **200 requests concurrentes** usando `threading.Thread`
- Filtra el dataset por `Tipo Operación = Venta` y `Estrato ∈ {3, 4, 5}` (perfil bancario)
- Si el dataset no está disponible, genera payloads sintéticos aleatorios como fallback
- Mide latencia por request con `time.perf_counter()`
- Reporta: throughput, latencia promedio, p95 y máxima

### 8.2 tenant_b.py — Portal Inmobiliario

- **500 requests concurrentes** — mix completo de estratos y operaciones (Venta + Arriendo)
- Perfil de portal inmobiliario: mayor volumen, mayor diversidad
- Mismas métricas de latencia que tenant_a

### 8.3 monitoring/stress_test.py — Stress test progresivo

Sube la carga en 5 oleadas para identificar el límite de la infraestructura:

```
Oleada 1:   50 requests
Oleada 2:  100 requests
Oleada 3:  200 requests
Oleada 4:  400 requests
Oleada 5:  800 requests
```

En cada oleada los requests se distribuyen aleatoriamente entre ambos tenants con payloads sintéticos generados en tiempo real. Al finalizar imprime el punto de quiebre si la tasa de error supera el 30%.

### 8.4 monitoring/report.py — Reporte post-experimento

Conecta directamente a PostgreSQL y consulta los schemas de ambos tenants para generar:
- Conteo de solicitudes por tenant
- Latencia promedio y máxima registrada en BD
- Precio estimado promedio por tipo de operación
- TCO anual promedio
- Exporta CSV con todos los datos

---

## 9. Flujo completo de una solicitud

Este es el camino que recorre una solicitud desde que un tenant la envía hasta que recibe respuesta:

```
[tenant_a.py]
  threading.Thread → httpx.post("/valorar", headers={"x-tenant-id": "tenant_a"})
        │
        │  HTTPS
        ▼
[api.py — Azure App Service]
  1. FastAPI recibe el request
  2. Valida x-tenant-id ∈ {"tenant_a", "tenant_b"}  → 401 si no
  3. Determina tipo = req.tipo_operacion.lower()       → "venta" | "arriendo"
  4. Verifica que models[tipo] existe                  → 503 si no
  5. Aplica LabelEncoder a {localidad, upz, tipo_inmueble}
     · Si valor desconocido → asigna 0
  6. Construye DataFrame con nombres originales del dataset (COL_MAP)
  7. precio_estimado = models[tipo].predict(X)[0]
  8. tco = _calcular_tco(acueducto, energia, admin, indice_seguridad, precio)
  9. Persiste en schema_tenant_a.solicitudes (PostgreSQL)
 10. Retorna ValorarResponse
        │
        ▼
[tenant_a.py]
  Recibe {"precio_estimado": 461120544.0, "tco_anual": 24539219.04, ...}
  Registra latencia, acumula en results[]
        │
[Al finalizar los 200 threads]
  Imprime resumen: exitosas, precio promedio, throughput, latencias (avg/p95/máx)
```

**Tiempo de inferencia puro** (solo XGBoost, en memoria): < 5 ms.  
**Latencia observada en producción**: 8,000–30,000 ms bajo carga concurrente — dominada por la cola de atención del plan B1 de Azure App Service (una sola instancia, ~6 req/s de capacidad).

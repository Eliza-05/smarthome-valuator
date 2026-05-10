"""
SmartHome Valuator — Backend B2B (FastAPI)
Carga los modelos XGBoost entrenados y expone el endpoint /valorar
con validación por X-Tenant-ID.

Uso:
    uvicorn api:app --host 0.0.0.0 --port 8080 --reload
Swagger UI disponible en: http://localhost:8080/docs
"""
import os
import joblib
import pandas as pd
from typing import Annotated
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

MODELS_DIR = os.environ.get("MODELS_DIR", "models")

TENANTS = {
    "tenant_a": "Banco Nacional",
    "tenant_b": "Portal Inmobiliario",
}

COL_MAP = {
    "area_m2":          "Área (m²)",
    "habitaciones":     "Habitaciones",
    "banos":            "Baños",
    "antiguedad_anos":  "Antigüedad (años)",
    "estrato":          "Estrato",
    "latitud":          "Latitud",
    "longitud":         "Longitud",
    "hurto_res_100k":   "Hurto Res./100k hab",
    "indice_seguridad": "Índice Seguridad (0-10)",
    "tipo_inmueble":    "Tipo Inmueble",
    "localidad":        "Localidad",
    "upz":              "UPZ",
    "parqueadero":      "Parqueadero",
    "deposito":         "Depósito",
}

FEATURE_KEYS = [
    "area_m2", "habitaciones", "banos", "antiguedad_anos",
    "estrato", "latitud", "longitud", "hurto_res_100k",
    "indice_seguridad",
    "tipo_inmueble", "localidad", "upz", "parqueadero", "deposito",
]

app = FastAPI(
    title="SmartHome Valuator API",
    description=(
        "API B2B multiteniente para valoración de inmuebles residenciales en Bogotá. "
        "Requiere el header **X-Tenant-ID** con valor `tenant_a` o `tenant_b`."
    ),
    version="1.0.0",
)

models: dict = {}
encoders: dict = {}


@app.on_event("startup")
def load_artifacts():
    for tipo in ("venta", "arriendo"):
        m_path = os.path.join(MODELS_DIR, f"xgboost_{tipo}.pkl")
        e_path = os.path.join(MODELS_DIR, f"encoders_{tipo}.pkl")
        if os.path.exists(m_path):
            models[tipo] = joblib.load(m_path)
        if os.path.exists(e_path):
            encoders[tipo] = joblib.load(e_path)
    print(f"[API] Modelos cargados: {list(models.keys())}")


def _calcular_tco(
    acueducto_mes: float,
    energia_mes: float,
    admin_mes: float,
    indice_seguridad: float,
    precio_estimado: float,
) -> dict:
    servicios = (acueducto_mes + energia_mes) * 12
    admin = admin_mes * 12
    riesgo = precio_estimado * (10 - indice_seguridad) / 100
    return {
        "servicios_anuales": round(servicios, 2),
        "admin_anual": round(admin, 2),
        "riesgo_desvalorizacion": round(riesgo, 2),
        "total": round(servicios + admin + riesgo, 2),
    }


class ValorarRequest(BaseModel):
    tipo_operacion: str
    area_m2: float
    habitaciones: int
    banos: int
    antiguedad_anos: float = 0.0
    estrato: int
    latitud: float
    longitud: float
    hurto_res_100k: float = 0.0
    indice_seguridad: float = 5.0
    acueducto_mes: float = 0.0
    energia_mes: float = 0.0
    admin_mensual: float = 0.0
    tipo_inmueble: str = "Apartamento"
    localidad: str = "Chapinero"
    upz: str = ""
    parqueadero: int = 0
    deposito: int = 0

    model_config = {
        "json_schema_extra": {
            "example": {
                "tipo_operacion": "Venta",
                "area_m2": 80,
                "habitaciones": 3,
                "banos": 2,
                "antiguedad_anos": 10,
                "estrato": 4,
                "latitud": 4.65,
                "longitud": -74.05,
                "hurto_res_100k": 150,
                "indice_seguridad": 6.5,
                "acueducto_mes": 120000,
                "energia_mes": 180000,
                "admin_mensual": 500000,
                "tipo_inmueble": "Apartamento",
                "localidad": "Chapinero",
                "upz": "El Refugio",
                "parqueadero": 1,
                "deposito": 0,
            }
        }
    }


class TCODetalle(BaseModel):
    servicios_anuales: float
    admin_anual: float
    riesgo_desvalorizacion: float
    total: float


class ValorarResponse(BaseModel):
    tenant_id: str
    tenant_nombre: str
    tipo_operacion: str
    precio_estimado: float
    tco_anual: float
    tco_detalle: TCODetalle


@app.get("/", tags=["Estado"])
def root():
    return {"status": "ok", "modelos_disponibles": list(models.keys()), "tenants": list(TENANTS.keys())}


@app.post(
    "/valorar",
    response_model=ValorarResponse,
    tags=["Valoración"],
    summary="Valora un inmueble y calcula su TCO",
    responses={
        401: {"description": "Tenant no autorizado"},
        503: {"description": "Modelo no disponible"},
    },
)
def valorar(
    req: ValorarRequest,
    x_tenant_id: Annotated[str, Header(description="ID del tenant: tenant_a o tenant_b")],
):
    if x_tenant_id not in TENANTS:
        raise HTTPException(
            status_code=401,
            detail=f"Tenant '{x_tenant_id}' no autorizado. Valores válidos: {list(TENANTS.keys())}",
        )

    tipo = req.tipo_operacion.lower()
    if tipo not in models:
        raise HTTPException(status_code=503, detail=f"Modelo '{tipo}' no disponible.")

    enc = encoders.get(tipo, {})
    row = req.model_dump()

    for key in ["tipo_inmueble", "localidad", "upz"]:
        le = enc.get(key)
        if le is not None:
            val = row[key]
            row[key] = int(le.transform([val])[0]) if val in le.classes_ else 0
        else:
            row[key] = 0

    X = pd.DataFrame([{COL_MAP[k]: row[k] for k in FEATURE_KEYS}])
    precio_estimado = float(models[tipo].predict(X)[0])

    tco = _calcular_tco(
        acueducto_mes=req.acueducto_mes,
        energia_mes=req.energia_mes,
        admin_mes=req.admin_mensual,
        indice_seguridad=req.indice_seguridad,
        precio_estimado=precio_estimado,
    )

    return ValorarResponse(
        tenant_id=x_tenant_id,
        tenant_nombre=TENANTS[x_tenant_id],
        tipo_operacion=req.tipo_operacion,
        precio_estimado=round(precio_estimado, 2),
        tco_anual=tco["total"],
        tco_detalle=TCODetalle(**tco),
    )

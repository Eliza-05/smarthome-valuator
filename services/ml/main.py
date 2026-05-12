"""ML Service — inferencia XGBoost + cálculo TCO."""
import os
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="ML Service")

MODELS_DIR = "/app/models"

# Solo features estructurales/locacionales — servicios públicos excluidos del modelo
# (acueducto, energía, admin siguen en el request para calcular el TCO)
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

models: dict = {}
encoders: dict = {}


@app.on_event("startup")
def load_artifacts():
    for tipo in ("venta", "arriendo"):
        model_path = os.path.join(MODELS_DIR, f"xgboost_{tipo}.pkl")
        encoder_path = os.path.join(MODELS_DIR, f"encoders_{tipo}.pkl")
        if os.path.exists(model_path):
            models[tipo] = joblib.load(model_path)
        if os.path.exists(encoder_path):
            encoders[tipo] = joblib.load(encoder_path)
    print(f"[ML] Modelos cargados: {list(models.keys())}")


def calcular_tco_anual(
    acueducto_mes: float,
    energia_mes: float,
    admin_mes: float,
    indice_seguridad: float,
    precio_estimado: float,
) -> float:
    servicios_anuales = (acueducto_mes + energia_mes) * 12
    admin_anual = admin_mes * 12
    factor_riesgo = (10 - indice_seguridad) / 100
    riesgo_desvalorizacion = precio_estimado * factor_riesgo
    return servicios_anuales + admin_anual + riesgo_desvalorizacion


class PredictRequest(BaseModel):
    tipo_operacion: str  # "Venta" | "Arriendo"
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
    consumo_energia_kwh: float = 0.0
    energia_mes: float = 0.0
    admin_mensual: float = 0.0
    tipo_inmueble: str = "Apartamento"
    localidad: str = "Chapinero"
    upz: str = ""
    parqueadero: int = 0
    deposito: int = 0


class PredictResponse(BaseModel):
    precio_estimado: float
    tco_anual: float


@app.get("/health")
def health():
    return {"status": "ok", "modelos_cargados": list(models.keys())}


@app.post("/predict", response_model=PredictResponse, responses={503: {"description": "Modelo no disponible"}})
def predict(req: PredictRequest):
    tipo = req.tipo_operacion.lower()
    if tipo not in models:
        raise HTTPException(
            status_code=503,
            detail=f"Modelo '{tipo}' no disponible. Modelos cargados: {list(models.keys())}",
        )

    model = models[tipo]
    enc = encoders.get(tipo, {})
    row = req.model_dump()

    # Aplicar label encoding a categóricas (encoders guardados con clave snake_case)
    for key in ["tipo_inmueble", "localidad", "upz"]:
        le = enc.get(key)
        if le is not None:
            val = row[key]
            row[key] = int(le.transform([val])[0]) if val in le.classes_ else 0
        else:
            row[key] = 0

    # Construir DataFrame con nombres originales del dataset
    X = pd.DataFrame([{COL_MAP[k]: row[k] for k in FEATURE_KEYS}])

    precio_estimado = float(model.predict(X)[0])
    tco_anual = calcular_tco_anual(
        acueducto_mes=req.acueducto_mes,
        energia_mes=req.energia_mes,
        admin_mes=req.admin_mensual,
        indice_seguridad=req.indice_seguridad,
        precio_estimado=precio_estimado,
    )

    return PredictResponse(precio_estimado=precio_estimado, tco_anual=tco_anual)

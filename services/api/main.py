"""API Gateway — autenticación por API Key, routing a ML Service, persistencia."""
import os
import time
import httpx
import psycopg2
import psycopg2.extras
from typing import Annotated
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="API Gateway")

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://ml_service:8001")

API_KEYS = {
    os.getenv("API_KEY_TENANT_A", "key-tenant-a"): "tenant_a",
    os.getenv("API_KEY_TENANT_B", "key-tenant-b"): "tenant_b",
}

TENANT_SCHEMA = {
    "tenant_a": "schema_tenant_a",
    "tenant_b": "schema_tenant_b",
}


def _dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "shv_admin")
    secret = os.getenv("POSTGRES_PASSWORD", "shv_password")
    db = os.getenv("POSTGRES_DB", "smarthouse_valuator")
    return f"host={host} port={port} user={user} dbname={db} password={secret}"


def resolve_tenant(x_api_key: str) -> str:
    tenant = API_KEYS.get(x_api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="API Key invalida")
    return tenant


def get_conn():
    return psycopg2.connect(_dsn())


class AvaluoRequest(BaseModel):
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
    consumo_energia_kwh: float = 0.0
    energia_mes: float = 0.0
    admin_mensual: float = 0.0
    tipo_inmueble: str = "Apartamento"
    localidad: str = "Chapinero"
    upz: str = ""
    parqueadero: int = 0
    deposito: int = 0


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/avaluo",
    responses={401: {"description": "API Key invalida"}, 502: {"description": "Error en ML Service"}},
)
def avaluo(req: AvaluoRequest, x_api_key: Annotated[str, Header()]):
    tenant_id = resolve_tenant(x_api_key)
    schema = TENANT_SCHEMA[tenant_id]

    t0 = time.perf_counter()
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{ML_SERVICE_URL}/predict", json=req.model_dump())
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ML Service error: {resp.text}")
    latencia_ms = int((time.perf_counter() - t0) * 1000)

    result = resp.json()
    precio_estimado = result["precio_estimado"]
    tco_anual = result["tco_anual"]

    features_json = psycopg2.extras.Json(req.model_dump())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {schema}.solicitudes
            (features, tipo_operacion, precio_estimado, tco_anual, latencia_ms)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (features_json, req.tipo_operacion, precio_estimado, tco_anual, latencia_ms),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "precio_estimado": precio_estimado,
        "tco_anual": tco_anual,
        "tenant_id": tenant_id,
        "latencia_ms": latencia_ms,
    }


@app.get("/metrics")
def metrics():
    conn = get_conn()
    cur = conn.cursor()
    result = {}

    for tenant_id, schema in TENANT_SCHEMA.items():
        cur.execute(
            f"""
            SELECT COUNT(*), AVG(latencia_ms)
            FROM {schema}.solicitudes
            """
        )
        row = cur.fetchone()

        cur.execute(
            f"""
            SELECT tipo_operacion, COUNT(*), AVG(precio_estimado)
            FROM {schema}.solicitudes
            GROUP BY tipo_operacion
            ORDER BY tipo_operacion
            """
        )
        by_tipo = {
            r[0]: {
                "total": r[1],
                "avg_precio_estimado": round(r[2], 2) if r[2] else 0.0,
            }
            for r in cur.fetchall()
        }

        result[tenant_id] = {
            "total_requests": row[0] or 0,
            "avg_latency_ms": round(row[1], 2) if row[1] else 0.0,
            "by_tipo_operacion": by_tipo,
        }

    cur.close()
    conn.close()
    return result

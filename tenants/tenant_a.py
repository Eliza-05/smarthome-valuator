"""Tenant A — Banco: 50 solicitudes concurrentes, estrato 3-5, solo Venta."""
import random
import threading
import time
import httpx
import pandas as pd

API_URL = "http://localhost:8000"
HEADERS = {"x-api-key": "key-tenant-a"}
NUM_REQUESTS = 50

DATASET_PATH = "data/processed/SmartHome_Valuator_Dataset_CLEAN_processed.csv"


def load_samples() -> list[dict]:
    df = pd.read_csv(DATASET_PATH, skiprows=0)
    df = df[df["Tipo Operación"] == "Venta"]
    df = df[df["Estrato"].isin([3, 4, 5])]
    sample = df.sample(n=min(NUM_REQUESTS, len(df)), replace=True).reset_index(drop=True)

    records = []
    for _, r in sample.iterrows():
        records.append({
            "tipo_operacion": "Venta",
            "area_m2": float(r.get("Área (m²)", 80)),
            "habitaciones": int(r.get("Habitaciones", 3)),
            "banos": int(r.get("Baños", 2)),
            "antiguedad_anos": float(r.get("Antigüedad (años)", 10)),
            "estrato": int(r.get("Estrato", 4)),
            "latitud": float(r.get("Latitud", 4.65)),
            "longitud": float(r.get("Longitud", -74.05)),
            "hurto_res_100k": float(r.get("Hurto Res./100k hab", 200)),
            "indice_seguridad": float(r.get("Índice Seguridad (0-10)", 5.0)),
            "acueducto_mes": float(r.get("Acueducto+Alcantarillado (COP/mes)", 100000)),
            "consumo_energia_kwh": float(r.get("Consumo Energía (kWh/mes)", 200)),
            "energia_mes": float(r.get("Energía Eléctrica (COP/mes)", 150000)),
            "admin_mensual": float(r.get("Admin. Mensual (COP)", 400000)),
            "tipo_inmueble": str(r.get("Tipo Inmueble", "Apartamento")),
            "localidad": str(r.get("Localidad", "Chapinero")),
            "upz": str(r.get("UPZ", "")),
            "parqueadero": 1 if r.get("Parqueadero") in [True, "Sí", 1] else 0,
            "deposito": 1 if r.get("Depósito") in [True, "Sí", 1] else 0,
        })
    return records


results: list[dict] = []
lock = threading.Lock()


def send_request(payload: dict) -> None:
    try:
        resp = httpx.post(f"{API_URL}/avaluo", json=payload, headers=HEADERS, timeout=30)
        with lock:
            results.append({"ok": resp.status_code == 200, "latencia_ms": resp.json().get("latencia_ms", 0)})
    except Exception as e:
        with lock:
            results.append({"ok": False, "latencia_ms": 0, "error": str(e)})


def main():
    print(f"[Tenant A] Cargando {NUM_REQUESTS} muestras del dataset...")
    try:
        payloads = load_samples()
    except Exception as e:
        print(f"[Tenant A] No se pudo cargar el dataset: {e}. Usando datos sintéticos.")
        payloads = [
            {
                "tipo_operacion": "Venta",
                "area_m2": random.uniform(50, 250),
                "habitaciones": random.randint(2, 5),
                "banos": random.randint(1, 4),
                "antiguedad_anos": random.uniform(0, 40),
                "estrato": random.randint(3, 5),
                "latitud": random.uniform(4.5, 4.8),
                "longitud": random.uniform(-74.2, -74.0),
                "hurto_res_100k": random.uniform(50, 400),
                "indice_seguridad": random.uniform(3, 9),
                "acueducto_mes": random.uniform(80000, 300000),
                "consumo_energia_kwh": random.uniform(100, 600),
                "energia_mes": random.uniform(100000, 600000),
                "admin_mensual": random.uniform(200000, 2000000),
                "tipo_inmueble": random.choice(["Apartamento", "Casa"]),
                "localidad": random.choice(["Usaquén", "Chapinero", "Suba"]),
                "upz": "",
                "parqueadero": random.randint(0, 1),
                "deposito": random.randint(0, 1),
            }
            for _ in range(NUM_REQUESTS)
        ]

    print(f"[Tenant A] Enviando {NUM_REQUESTS} solicitudes concurrentes...")
    t0 = time.perf_counter()
    threads = [threading.Thread(target=send_request, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    exitosos = sum(1 for r in results if r["ok"])
    fallidos = NUM_REQUESTS - exitosos
    latencias = [r["latencia_ms"] for r in results if r["ok"] and r["latencia_ms"]]
    avg_lat = sum(latencias) / len(latencias) if latencias else 0
    max_lat = max(latencias) if latencias else 0

    print("\n=== Tenant A (Banco) — Resumen ===")
    print(f"  Total requests  : {NUM_REQUESTS}")
    print(f"  Exitosos        : {exitosos}")
    print(f"  Fallidos        : {fallidos}")
    print(f"  Latencia prom.  : {avg_lat:.1f} ms")
    print(f"  Latencia máx.   : {max_lat} ms")
    print(f"  Throughput      : {NUM_REQUESTS / elapsed:.1f} req/s")


if __name__ == "__main__":
    main()

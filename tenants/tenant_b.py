"""Tenant B — Portal inmobiliario: 80 solicitudes concurrentes, mix de estratos y operaciones."""
import random
import threading
import time
import httpx
import pandas as pd

API_URL = "https://smarthome-api-b2b.azurewebsites.net"
HEADERS = {"x-tenant-id": "tenant_b"}
NUM_REQUESTS = 500

DATASET_PATH = "data/processed/SmartHome_Valuator_Dataset_CLEAN_processed.csv"


def load_samples() -> list[dict]:
    df = pd.read_csv(DATASET_PATH, skiprows=0)
    sample = df.sample(n=min(NUM_REQUESTS, len(df)), replace=True).reset_index(drop=True)

    records = []
    for _, r in sample.iterrows():
        records.append({
            "tipo_operacion": str(r.get("Tipo Operación", "Venta")),
            "area_m2": float(r.get("Área (m²)", 70)),
            "habitaciones": int(r.get("Habitaciones", 2)),
            "banos": int(r.get("Baños", 1)),
            "antiguedad_anos": float(r.get("Antigüedad (años)", 10)),
            "estrato": int(r.get("Estrato", 3)),
            "latitud": float(r.get("Latitud", 4.65)),
            "longitud": float(r.get("Longitud", -74.05)),
            "hurto_res_100k": float(r.get("Hurto Res./100k hab", 200)),
            "indice_seguridad": float(r.get("Índice Seguridad (0-10)", 5.0)),
            "acueducto_mes": float(r.get("Acueducto+Alcantarillado (COP/mes)", 100000)),
            "consumo_energia_kwh": float(r.get("Consumo Energía (kWh/mes)", 200)),
            "energia_mes": float(r.get("Energía Eléctrica (COP/mes)", 150000)),
            "admin_mensual": float(r.get("Admin. Mensual (COP)", 300000)),
            "tipo_inmueble": str(r.get("Tipo Inmueble", "Apartamento")),
            "localidad": str(r.get("Localidad", "Suba")),
            "upz": str(r.get("UPZ", "")),
            "parqueadero": 1 if r.get("Parqueadero") in [True, "Sí", 1] else 0,
            "deposito": 1 if r.get("Depósito") in [True, "Sí", 1] else 0,
        })
    return records


results: list[dict] = []
lock = threading.Lock()


def send_request(payload: dict) -> None:
    t0 = time.perf_counter()
    try:
        resp = httpx.post(f"{API_URL}/valorar", json=payload, headers=HEADERS, timeout=30)
        latencia = (time.perf_counter() - t0) * 1000
        with lock:
            results.append({"ok": resp.status_code == 200, "precio": resp.json().get("precio_estimado", 0), "latencia_ms": latencia})
    except Exception as e:
        latencia = (time.perf_counter() - t0) * 1000
        with lock:
            results.append({"ok": False, "precio": 0, "latencia_ms": latencia, "error": str(e)})


def main():
    print(f"[Tenant B] Cargando {NUM_REQUESTS} muestras del dataset...")
    try:
        payloads = load_samples()
    except Exception as e:
        print(f"[Tenant B] No se pudo cargar el dataset: {e}. Usando datos sintéticos.")
        operaciones = ["Venta", "Arriendo"]
        payloads = [
            {
                "tipo_operacion": random.choice(operaciones),
                "area_m2": random.uniform(30, 300),
                "habitaciones": random.randint(1, 6),
                "banos": random.randint(1, 4),
                "antiguedad_anos": random.uniform(0, 50),
                "estrato": random.randint(1, 6),
                "latitud": random.uniform(4.5, 4.8),
                "longitud": random.uniform(-74.2, -74.0),
                "hurto_res_100k": random.uniform(50, 500),
                "indice_seguridad": random.uniform(2, 9),
                "acueducto_mes": random.uniform(50000, 300000),
                "energia_mes": random.uniform(80000, 700000),
                "admin_mensual": random.uniform(100000, 3000000),
                "tipo_inmueble": random.choice(["Apartamento", "Casa", "Oficina"]),
                "localidad": random.choice(["Suba", "Kennedy", "Bosa", "Usaquén", "Fontibón"]),
                "upz": "",
                "parqueadero": random.randint(0, 1),
                "deposito": random.randint(0, 1),
            }
            for _ in range(NUM_REQUESTS)
        ]

    print(f"[Tenant B] Enviando {NUM_REQUESTS} solicitudes concurrentes...")
    t0 = time.perf_counter()
    threads = [threading.Thread(target=send_request, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    exitosos = sum(1 for r in results if r["ok"])
    fallidos = NUM_REQUESTS - exitosos
    precios = [r["precio"] for r in results if r["ok"] and r["precio"]]
    avg_precio = sum(precios) / len(precios) if precios else 0
    latencias = sorted(r["latencia_ms"] for r in results if "latencia_ms" in r)
    avg_lat = sum(latencias) / len(latencias) if latencias else 0
    max_lat = max(latencias) if latencias else 0
    p95_lat = latencias[int(len(latencias) * 0.95)] if latencias else 0

    print("\n=== Tenant B (Portal Inmobiliario) — Resumen ===")
    print(f"  Total requests  : {NUM_REQUESTS}")
    print(f"  Exitosos        : {exitosos}")
    print(f"  Fallidos        : {fallidos}")
    print(f"  Precio prom.    : ${avg_precio:,.0f} COP")
    print(f"  Throughput      : {NUM_REQUESTS / elapsed:.1f} req/s")
    print(f"  Latencia prom.  : {avg_lat:.0f} ms")
    print(f"  Latencia p95    : {p95_lat:.0f} ms")
    print(f"  Latencia máx.   : {max_lat:.0f} ms")


if __name__ == "__main__":
    main()

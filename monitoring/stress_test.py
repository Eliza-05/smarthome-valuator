"""
Stress test progresivo — SmartHome Valuator API B2B
Sube la carga en oleadas para encontrar el punto de quiebre.
Oleadas: 50 → 100 → 200 → 400 → 800 requests concurrentes
"""
import random
import threading
import time
import httpx

API_URL = "https://smarthome-api-b2b.azurewebsites.net"
WAVES = [50, 100, 200, 400, 800]
TIMEOUT = 30

TENANTS = [
    {"x-tenant-id": "tenant_a"},
    {"x-tenant-id": "tenant_b"},
]

OPERACIONES = ["Venta", "Arriendo"]
LOCALIDADES = ["Usaquén", "Chapinero", "Suba", "Kennedy", "Bosa", "Fontibón", "Teusaquillo"]


def _payload() -> dict:
    op = random.choice(OPERACIONES)
    estrato = random.randint(1, 6)
    return {
        "tipo_operacion": op,
        "area_m2": round(random.uniform(30, 300), 1),
        "habitaciones": random.randint(1, 6),
        "banos": random.randint(1, 4),
        "antiguedad_anos": round(random.uniform(0, 50), 1),
        "estrato": estrato,
        "latitud": round(random.uniform(4.50, 4.80), 6),
        "longitud": round(random.uniform(-74.20, -74.00), 6),
        "hurto_res_100k": round(random.uniform(50, 500), 1),
        "indice_seguridad": round(random.uniform(2.0, 9.0), 1),
        "acueducto_mes": round(random.uniform(50000, 300000), 0),
        "energia_mes": round(random.uniform(80000, 700000), 0),
        "admin_mensual": round(random.uniform(100000, 3000000), 0),
        "tipo_inmueble": random.choice(["Apartamento", "Casa"]),
        "localidad": random.choice(LOCALIDADES),
        "upz": "",
        "parqueadero": random.randint(0, 1),
        "deposito": random.randint(0, 1),
    }


def run_wave(n: int) -> dict:
    results: list[dict] = []
    lock = threading.Lock()

    def _send(headers: dict) -> None:
        t0 = time.perf_counter()
        try:
            resp = httpx.post(f"{API_URL}/valorar", json=_payload(), headers=headers, timeout=TIMEOUT)
            lat = (time.perf_counter() - t0) * 1000
            with lock:
                results.append({"ok": resp.status_code == 200, "lat": lat, "status": resp.status_code})
        except Exception:
            lat = (time.perf_counter() - t0) * 1000
            with lock:
                results.append({"ok": False, "lat": lat, "status": 0})

    headers_list = [random.choice(TENANTS) for _ in range(n)]
    threads = [threading.Thread(target=_send, args=(h,)) for h in headers_list]

    t_wave = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t_wave

    ok = sum(1 for r in results if r["ok"])
    lats = sorted(r["lat"] for r in results)
    avg_lat = sum(lats) / len(lats) if lats else 0
    p95_lat = lats[int(len(lats) * 0.95)] if lats else 0
    max_lat = lats[-1] if lats else 0
    throughput = n / elapsed

    return {
        "n": n,
        "ok": ok,
        "failed": n - ok,
        "error_rate": (n - ok) / n * 100,
        "throughput": throughput,
        "avg_lat": avg_lat,
        "p95_lat": p95_lat,
        "max_lat": max_lat,
    }


def print_wave(w: dict) -> None:
    status = "OK" if w["error_rate"] < 5 else ("DEGRADADO" if w["error_rate"] < 30 else "CRITICO")
    print(f"\n  Oleada {w['n']:>4} req  [{status}]")
    print(f"    Exitosas     : {w['ok']} / {w['n']}  ({100 - w['error_rate']:.1f}% ok)")
    print(f"    Throughput   : {w['throughput']:.1f} req/s")
    print(f"    Latencia prom: {w['avg_lat']:.0f} ms")
    print(f"    Latencia p95 : {w['p95_lat']:.0f} ms")
    print(f"    Latencia máx : {w['max_lat']:.0f} ms")


def main():
    print("=" * 55)
    print("  SmartHome Valuator — Stress Test Progresivo")
    print(f"  Oleadas: {' → '.join(str(w) for w in WAVES)} requests")
    print("=" * 55)

    breaking_point = None
    for n in WAVES:
        print(f"\n[>>] Iniciando oleada de {n} requests concurrentes...")
        w = run_wave(n)
        print_wave(w)

        if w["error_rate"] >= 30 and breaking_point is None:
            breaking_point = n
            print(f"\n  *** PUNTO DE QUIEBRE detectado en {n} requests ***")
            print("      Tasa de error superó el 30%. Continuando para medir degradación...")

        time.sleep(3)

    print("\n" + "=" * 55)
    print("  Resumen Final")
    print("=" * 55)
    if breaking_point:
        print(f"  Punto de quiebre : ~{breaking_point} requests concurrentes")
        print(f"  Escala estable   : hasta ~{WAVES[WAVES.index(breaking_point) - 1]} requests")
    else:
        print(f"  Sistema estable hasta {WAVES[-1]} requests concurrentes")
        print("  No se detectó punto de quiebre en este rango.")
    print()


if __name__ == "__main__":
    main()

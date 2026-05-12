"""Reporte de métricas post-experimento: aislamiento por schema y latencias."""
import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "shv_admin")
    secret = os.getenv("POSTGRES_PASSWORD", "shv_password")
    db = os.getenv("POSTGRES_DB", "smarthouse_valuator")
    return f"host={host} port={port} user={user} dbname={db} password={secret}"


TENANT_SCHEMAS = {
    "tenant_a": "schema_tenant_a",
    "tenant_b": "schema_tenant_b",
}


def fetch_tenant_stats(cur, tenant_id: str, schema: str) -> dict:
    cur.execute(f"SELECT COUNT(*), AVG(latencia_ms), MAX(latencia_ms) FROM {schema}.solicitudes")
    row = cur.fetchone()
    total = row[0] or 0
    lat_prom = round(row[1], 1) if row[1] else 0
    lat_max = row[2] or 0

    cur.execute(f"SELECT AVG(tco_anual) FROM {schema}.solicitudes")
    tco_row = cur.fetchone()
    tco_prom = round(tco_row[0], 0) if tco_row[0] else 0

    cur.execute(
        f"""
        SELECT tipo_operacion, COUNT(*), AVG(precio_estimado)
        FROM {schema}.solicitudes
        GROUP BY tipo_operacion
        ORDER BY tipo_operacion
        """
    )
    precios_por_tipo = {r[0]: (r[1], round(r[2], 0) if r[2] else 0) for r in cur.fetchall()}

    return {
        "tenant": tenant_id,
        "schema": schema,
        "total": total,
        "lat_prom": lat_prom,
        "lat_max": lat_max,
        "tco_prom": tco_prom,
        "precios_por_tipo": precios_por_tipo,
    }


def print_report(stats: dict) -> None:
    tid = stats["tenant"]
    label = "Banco" if tid == "tenant_a" else "Portal Inmobiliario"
    print(f"\n{tid} ({label}):")
    print(f"  - Total solicitudes        : {stats['total']}")
    print(f"  - Latencia promedio        : {stats['lat_prom']} ms")
    print(f"  - Latencia maxima          : {stats['lat_max']} ms")
    for tipo, (count, avg_precio) in stats["precios_por_tipo"].items():
        print(f"  - Precio estimado prom ({tipo}): {avg_precio:,.0f} COP  [{count} solicitudes]")
    print(f"  - TCO anual promedio       : {stats['tco_prom']:,.0f} COP")


def build_csv_rows(stats: dict) -> list[dict]:
    rows = []
    for tipo, (count, avg_precio) in stats["precios_por_tipo"].items():
        rows.append({
            "tenant": stats["tenant"],
            "schema": stats["schema"],
            "tipo_operacion": tipo,
            "total_solicitudes": count,
            "latencia_prom_ms": stats["lat_prom"],
            "latencia_max_ms": stats["lat_max"],
            "precio_estimado_prom": avg_precio,
            "tco_anual_prom": stats["tco_prom"],
        })
    if not rows:
        rows.append({
            "tenant": stats["tenant"],
            "schema": stats["schema"],
            "tipo_operacion": None,
            "total_solicitudes": 0,
            "latencia_prom_ms": 0,
            "latencia_max_ms": 0,
            "precio_estimado_prom": 0,
            "tco_anual_prom": 0,
        })
    return rows


def main():
    conn = psycopg2.connect(_dsn())
    cur = conn.cursor()

    all_stats = [fetch_tenant_stats(cur, tid, schema) for tid, schema in TENANT_SCHEMAS.items()]

    print("\n=== Verificacion de aislamiento ===")
    for tid, schema in TENANT_SCHEMAS.items():
        cur.execute(f"SELECT COUNT(*) FROM {schema}.solicitudes")
        count = cur.fetchone()[0]
        print(f"  {schema}.solicitudes -> {count} registros (solo {tid})")

    cur.close()
    conn.close()

    print("\n=== SmartHome Valuator -- Reporte de Metricas ===")
    for stats in all_stats:
        print_report(stats)

    csv_rows = []
    for stats in all_stats:
        csv_rows.extend(build_csv_rows(stats))

    df = pd.DataFrame(csv_rows)
    out_path = os.path.join(os.path.dirname(__file__), "report.csv")
    df.to_csv(out_path, index=False)
    print(f"\nReporte guardado en {out_path}")


if __name__ == "__main__":
    main()

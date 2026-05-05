"""ETL Service — job de una sola ejecución (no es un servidor)."""
import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

RAW_PATH = "/app/data/raw/SmartHome_Valuator_Dataset_CLEAN.csv"
PROCESSED_PATH = "/app/data/processed/SmartHome_Valuator_Dataset_CLEAN_processed.csv"

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "user": os.getenv("POSTGRES_USER", "shv_admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "shv_password"),
    "dbname": os.getenv("POSTGRES_DB", "smarthouse_valuator"),
}


def load_and_clean() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH, skiprows=1)

    # Eliminar filas sin target
    df = df.dropna(subset=["PRECIO MERCADO (COP) ★"])
    df = df[df["PRECIO MERCADO (COP) ★"] > 0]

    # Eliminar filas sin features críticos
    df = df.dropna(subset=["Área (m²)", "Habitaciones", "Baños", "Estrato"])

    # Normalizar booleanos
    df["Parqueadero"] = df["Parqueadero"].map({"Sí": True, "No": False})
    df["Depósito"] = df["Depósito"].map({"Sí": True, "No": False})

    # Rellenar nulos numéricos con mediana
    numeric_cols = [
        "Área (m²)", "Habitaciones", "Baños", "Antigüedad (años)",
        "Latitud", "Longitud", "Hurto Res./100k hab",
        "Índice Seguridad (0-10)", "Acueducto+Alcantarillado (COP/mes)",
        "Consumo Energía (kWh/mes)", "Energía Eléctrica (COP/mes)",
        "Admin. Mensual (COP)", "TCO Mensual Est. (COP)",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].fillna(df[col].median())

    df.to_csv(PROCESSED_PATH, index=False)
    print(f"[ETL] Dataset limpio guardado en {PROCESSED_PATH} ({len(df)} filas)")
    return df


def insert_to_postgres(df: pd.DataFrame) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get("ID Registro", "")),
            str(r.get("Fuente", "")),
            str(r.get("Tipo Operación", "")),
            str(r.get("Tipo Inmueble", "")),
            r.get("Área (m²)"),
            int(r["Habitaciones"]) if pd.notna(r.get("Habitaciones")) else None,
            int(r["Baños"]) if pd.notna(r.get("Baños")) else None,
            bool(r["Parqueadero"]) if pd.notna(r.get("Parqueadero")) else None,
            bool(r["Depósito"]) if pd.notna(r.get("Depósito")) else None,
            int(r["Antigüedad (años)"]) if pd.notna(r.get("Antigüedad (años)")) else None,
            str(r.get("Localidad", "")),
            str(r.get("UPZ", "")),
            int(r["Estrato"]) if pd.notna(r.get("Estrato")) else None,
            r.get("Latitud"),
            r.get("Longitud"),
            r.get("Hurto Res./100k hab"),
            r.get("Índice Seguridad (0-10)"),
            r.get("Acueducto+Alcantarillado (COP/mes)"),
            r.get("Consumo Energía (kWh/mes)"),
            r.get("Energía Eléctrica (COP/mes)"),
            r.get("Admin. Mensual (COP)"),
            r.get("TCO Mensual Est. (COP)"),
            r.get("PRECIO MERCADO (COP) ★"),
        ))

    execute_values(
        cur,
        """
        INSERT INTO shared_data.propiedades (
            id, fuente, tipo_operacion, tipo_inmueble, area_m2,
            habitaciones, banos, parqueadero, deposito, antiguedad_anos,
            localidad, upz, estrato, latitud, longitud,
            hurto_res_100k, indice_seguridad, acueducto_mes,
            consumo_energia_kwh, energia_mes, admin_mensual,
            tco_mensual_est, precio_mercado
        ) VALUES %s
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[ETL] {len(rows)} registros cargados en shared_data.propiedades")


def main():
    print("[ETL] Iniciando pipeline...")
    df = load_and_clean()
    insert_to_postgres(df)
    print("[ETL] Pipeline completado exitosamente.")


if __name__ == "__main__":
    main()

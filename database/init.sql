-- Schema compartido para datos de entrenamiento
CREATE SCHEMA IF NOT EXISTS shared_data;

-- Schemas por tenant
CREATE SCHEMA IF NOT EXISTS schema_tenant_a;
CREATE SCHEMA IF NOT EXISTS schema_tenant_b;

-- Tabla de propiedades procesadas (compartida, solo lectura por tenants)
CREATE TABLE IF NOT EXISTS shared_data.propiedades (
    id VARCHAR(20) PRIMARY KEY,
    fuente VARCHAR(50),
    tipo_operacion VARCHAR(20),
    tipo_inmueble VARCHAR(50),
    area_m2 NUMERIC,
    habitaciones INTEGER,
    banos INTEGER,
    parqueadero BOOLEAN,
    deposito BOOLEAN,
    antiguedad_anos INTEGER,
    localidad VARCHAR(100),
    upz VARCHAR(100),
    estrato INTEGER,
    latitud NUMERIC,
    longitud NUMERIC,
    hurto_res_100k NUMERIC,
    indice_seguridad NUMERIC,
    acueducto_mes NUMERIC,
    consumo_energia_kwh NUMERIC,
    energia_mes NUMERIC,
    admin_mensual NUMERIC,
    tco_mensual_est NUMERIC,
    precio_mercado NUMERIC
);

-- Tabla de solicitudes Tenant A (banco)
CREATE TABLE IF NOT EXISTS schema_tenant_a.solicitudes (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    features JSONB NOT NULL,
    tipo_operacion VARCHAR(20),
    precio_estimado NUMERIC,
    tco_anual NUMERIC,
    latencia_ms INTEGER
);

-- Tabla de solicitudes Tenant B (portal inmobiliario)
CREATE TABLE IF NOT EXISTS schema_tenant_b.solicitudes (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    features JSONB NOT NULL,
    tipo_operacion VARCHAR(20),
    precio_estimado NUMERIC,
    tco_anual NUMERIC,
    latencia_ms INTEGER
);

-- Usuarios con permisos restringidos por schema
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tenant_a_user') THEN
        CREATE USER tenant_a_user WITH PASSWORD 'tenant_a_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tenant_b_user') THEN
        CREATE USER tenant_b_user WITH PASSWORD 'tenant_b_pass';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA schema_tenant_a TO tenant_a_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA schema_tenant_a TO tenant_a_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA schema_tenant_a
    GRANT ALL PRIVILEGES ON TABLES TO tenant_a_user;

GRANT USAGE ON SCHEMA schema_tenant_b TO tenant_b_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA schema_tenant_b TO tenant_b_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA schema_tenant_b
    GRANT ALL PRIVILEGES ON TABLES TO tenant_b_user;

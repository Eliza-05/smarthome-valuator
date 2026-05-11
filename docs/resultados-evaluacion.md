# Resultados de Evaluación — SmartHome Valuator

**Curso:** TDSE 2026-1  
**Estudiantes:** Elizabeth Correa Suarez · Juan Sebastián Ortega Muñoz · Jeimy Alejandra Yaya Martinez  
**Fecha:** Mayo 2026  
**Entorno:** Azure App Service (Plan B1) + Azure Container Apps + PostgreSQL Flexible Server (Canada Central)

---

## 1. Modelos de predicción

| Modelo | Propósito | R² | RMSE | MAE |
|---|---|---|---|---|
| XGBoost Venta | Precio de mercado — inmuebles en venta | 0.9604 | ~78 M COP | ~29 M COP |
| XGBoost Arriendo | Precio de mercado — inmuebles en arriendo | 0.8480 | 1,131,019 COP | 359,988 COP |

Entrenados con partición **70% train / 15% validación / 15% test** sobre el dataset `SmartHome_Valuator_Dataset_CLEAN.csv`.

---

## 2. Pruebas de concurrencia multi-tenant (Azure)

Simulación de dos clientes empresariales accediendo simultáneamente a la API B2B en producción.

### Tenant A — Banco Nacional (200 solicitudes)

| Métrica | Valor |
|---|---|
| Solicitudes enviadas | 200 |
| Exitosas | 200 |
| Fallidas | 0 |
| Tasa de éxito | 100% |
| Precio estimado promedio | $416,553,392 COP |
| Throughput | 6.5 req/s |
| Latencia promedio | 28,225 ms |
| Latencia p95 | 30,372 ms |
| Latencia máxima | 30,533 ms |

### Tenant B — Portal Inmobiliario (500 solicitudes)

| Métrica | Valor |
|---|---|
| Solicitudes enviadas | 500 |
| Exitosas | 500 |
| Fallidas | 0 |
| Tasa de éxito | 100% |
| Precio estimado promedio | $220,748,647 COP |
| Throughput | 5.0 req/s |
| Latencia promedio | 77,668 ms |
| Latencia p95 | 97,972 ms |
| Latencia máxima | 99,989 ms |

> **Nota sobre latencias:** Las latencias elevadas (28–100 s) se explican por la naturaleza de la prueba: se disparan todas las solicitudes al mismo tiempo sin rampa de entrada. El plan B1 de App Service tiene una sola instancia activa que atiende ~5–7 req/s; las solicitudes restantes esperan en cola hasta ser procesadas. En un escenario de producción real el tráfico llega distribuido en el tiempo, lo que reduce drásticamente la latencia observada por usuario.

### Aislamiento verificado

Los registros de cada tenant quedan exclusivamente en su propio schema de PostgreSQL:

```
schema_tenant_a.solicitudes  →  200 registros (solo Banco Nacional)
schema_tenant_b.solicitudes  →  500 registros (solo Portal Inmobiliario)
```

Ningún tenant puede acceder a los datos del otro bajo ninguna circunstancia (patrón schema-per-tenant).

---

## 3. Stress test progresivo

Prueba de carga escalonada para identificar el límite de la infraestructura actual. Las solicitudes se distribuyen aleatoriamente entre ambos tenants en cada oleada.

**Endpoint:** `POST https://smarthome-api-b2b.azurewebsites.net/valorar`  
**Script:** `monitoring/stress_test.py`

| Oleada | Requests | Exitosas | Tasa éxito | Throughput | Latencia prom. | Latencia p95 | Latencia máx. | Estado |
|---|---|---|---|---|---|---|---|---|
| 1 | 50 | 50 | 100.0% | 5.9 req/s | 8,015 ms | 8,426 ms | 8,440 ms | ✅ OK |
| 2 | 100 | 100 | 100.0% | 4.9 req/s | 18,858 ms | 19,673 ms | 20,112 ms | ✅ OK |
| 3 | 200 | 198 | 99.0% | 7.2 req/s | 18,724 ms | 21,172 ms | 22,110 ms | ✅ OK |
| 4 | 400 | 400 | 100.0% | 6.0 req/s | 58,978 ms | 62,808 ms | 64,068 ms | ✅ OK |
| 5 | 800 | 727 | 90.9% | 5.9 req/s | 62,581 ms | 93,115 ms | 104,057 ms | ⚠️ DEGRADADO |

### Observaciones clave

- **Throughput estable:** el servidor mantiene ~5–7 req/s en todas las oleadas, lo que confirma que esa es la capacidad de procesamiento de una sola instancia B1.
- **Degradación en 800 req:** en la oleada de 800 requests se producen 73 fallos (9.1%), todos por timeout (>30 s en cola de espera). No es un fallo del modelo ni de la lógica de negocio, sino del límite de cola de la instancia.
- **Punto de degradación:** entre 400 y 800 requests concurrentes simultáneos. La infraestructura actual aguanta sin fallos hasta ~400 requests lanzados al mismo tiempo.

### Solución para escalar

El cuello de botella es la instancia única del plan B1. Con **auto-scaling horizontal** en Azure App Service (plan Standard o Premium), el sistema puede escalar a múltiples instancias sin cambiar una línea de código:

```
Plan B1  →  1 instancia  →  ~6 req/s
Plan S2  →  3 instancias →  ~18 req/s  (auto-scaling)
Plan P2  →  10 instancias → ~60 req/s  (auto-scaling agresivo)
```

---

## 4. Predicciones por estrato (modelo Venta)

| Estrato | Precio estimado promedio |
|---|---|
| 1 | ~103 M COP |
| 2 | ~145 M COP |
| 3 | ~249 M COP |
| 4 | ~461 M COP |
| 5 | ~1,070 M COP |
| 6 | ~1,790 M COP |

---

## 5. Conclusiones

1. **Funcionalidad completa en producción:** 700 solicitudes combinadas (200 Banco + 500 Portal) procesadas con 0 errores bajo carga concurrente real en Azure.
2. **Aislamiento multi-tenant verificado:** el patrón schema-per-tenant garantiza separación total de datos entre clientes.
3. **Límite identificado:** la infraestructura actual (plan B1, 1 instancia) soporta hasta ~400 requests estrictamente simultáneos antes de mostrar degradación.
4. **Arquitectura lista para escalar:** el diseño en Azure App Service permite habilitar auto-scaling horizontal sin modificar el código, pasando de ~6 req/s a decenas de req/s según el plan contratado.
5. **Modelo de alta precisión:** R² de 0.96 en predicción de precios de venta, adecuado para uso en decisiones de crédito hipotecario (Tenant A) y publicación de avalúos (Tenant B).

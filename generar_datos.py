"""
Genera las ventas mensuales ficticias, en cajas, de una embotelladora mediana de
Santa Cruz de la Sierra, entre octubre de 2019 y septiembre de 2026 (84 meses),
para cinco familias de productos.

Salidas (carpeta datos/):
  - ventas_mensuales.csv     una fila por mes y familia: cajas vendidas y precio promedio por caja
  - calendario_carnaval.csv  fechas de Carnaval de 2020 a 2027 (incluye el año del pronóstico)

Todo es inventado, salvo las fechas de Carnaval: son las reales, porque se calculan
con el calendario (el martes de Carnaval cae 47 días antes del domingo de Pascua).

Cada serie se arma con estos componentes (ver SUPUESTOS):
  tendencia propia de cada familia × estacionalidad × efecto de Carnaval
  × caída de la pandemia (abril a junio de 2020) × baja por el aumento de precio
  × ruido (del mercado, común a todas las familias, y propio de cada familia)

Uso:
    python generar_datos.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.easter import easter

SEMILLA = 2026
INICIO = pd.Period("2019-10", freq="M")
FIN = pd.Period("2026-09", freq="M")
ANIOS_CARNAVAL = range(2020, 2028)

# --- SUPUESTOS ---------------------------------------------------------------
# Estacionalidad base (1 = mes promedio). En Santa Cruz, diciembre junta calor,
# fiestas y aguinaldo; enero y febrero siguen calurosos; junio y julio son los
# meses más frescos (frentes fríos).
ESTACIONALIDAD = {1: 1.12, 2: 1.06, 3: 1.00, 4: 0.95, 5: 0.90, 6: 0.84,
                  7: 0.85, 8: 0.92, 9: 0.97, 10: 1.03, 11: 1.07, 12: 1.29}

# Familias de productos:
#   base:        cajas por mes en octubre de 2019, sin estacionalidad
#   crec_antes:  crecimiento anual de la tendencia hasta diciembre de 2022
#   crec_desde:  crecimiento anual de la tendencia desde enero de 2023
#   amplitud:    intensidad de la estacionalidad (1 = la del perfil base)
#   carnaval:    ventas extra de Carnaval, como fracción de las ventas de un mes
#   pandemia:    sensibilidad a la caída de 2020 (1 = la caída base)
#   ruido:       desvío del ruido mensual propio de la familia
#   precio:      precio neto promedio por caja (Bs) antes del aumento de precio
#   aumento:     aumento de precio de julio de 2024
FAMILIAS = {
    "Gaseosas 2 L":    dict(base=180_000, crec_antes=0.025, crec_desde=0.025, amplitud=1.00, carnaval=0.16,
                            pandemia=1.00, ruido=0.035, precio=48.0, aumento=0.10),
    "Gaseosas 600 ml": dict(base=110_000, crec_antes=0.040, crec_desde=0.035, amplitud=1.15, carnaval=0.10,
                            pandemia=1.15, ruido=0.040, precio=42.0, aumento=0.10),
    "Gaseosas 3 L":    dict(base=65_000, crec_antes=0.010, crec_desde=0.010, amplitud=1.30, carnaval=0.24,
                            pandemia=0.90, ruido=0.050, precio=46.0, aumento=0.10),
    "Agua 2 L":        dict(base=55_000, crec_antes=0.090, crec_desde=0.120, amplitud=1.25, carnaval=0.08,
                            pandemia=0.60, ruido=0.045, precio=30.0, aumento=0.08),
    "Jugos 1 L":       dict(base=38_000, crec_antes=0.005, crec_desde=-0.050, amplitud=0.60, carnaval=0.03,
                            pandemia=0.80, ruido=0.060, precio=78.0, aumento=0.12),
}
CAMBIO_TENDENCIA = pd.Period("2023-01", freq="M")

# Carnaval: las ventas extra se reparten entre el viernes previo y el martes de
# Carnaval (5 días): las tiendas se abastecen el viernes y se repone durante el feriado.
# Si esos días caen entre febrero y marzo, el efecto se reparte entre los dos meses.
DIAS_ANTES_DEL_MARTES = 4
VARIACION_CARNAVAL = 0.15   # desvío del tamaño del efecto de un año a otro

# Pandemia: caída de las ventas en 2020 (fracción de las ventas esperadas)
CAIDA_PANDEMIA = {pd.Period("2020-04", freq="M"): 0.36,
                  pd.Period("2020-05", freq="M"): 0.24,
                  pd.Period("2020-06", freq="M"): 0.10}

# Aumento de precio: baja leve de las ventas que se recupera en pocos meses
MES_AUMENTO = pd.Period("2024-07", freq="M")
ELASTICIDAD_CORTO_PLAZO = -0.5   # un aumento de 10% baja las ventas 5% el primer mes
RECUPERACION_MENSUAL = 0.55      # cada mes queda el 55% de la baja del mes anterior

# Ruido
AR_MERCADO = 0.5          # persistencia del componente común (clima, economía)
DESVIO_MERCADO = 0.020    # desvío mensual del componente común
DESVIO_DERIVA = 0.004     # deriva lenta de la tendencia de cada familia (paseo aleatorio)
DESVIO_PRECIO = 0.005     # variación del precio promedio por mezcla de clientes y promociones


def calendario_carnaval(anios=ANIOS_CARNAVAL):
    """Sábado y martes de Carnaval de cada año, calculados desde la fecha de Pascua."""
    filas = []
    for anio in anios:
        pascua = pd.Timestamp(easter(anio))
        filas.append(dict(anio=anio,
                          sabado_carnaval=(pascua - pd.Timedelta(days=50)).date(),
                          martes_carnaval=(pascua - pd.Timedelta(days=47)).date()))
    return pd.DataFrame(filas)


def reparto_carnaval(calendario, periodos):
    """Fracción de las ventas extra de Carnaval de cada año que cae en cada mes."""
    reparto = pd.Series(0.0, index=periodos)
    for martes in pd.to_datetime(calendario["martes_carnaval"]):
        dias = pd.date_range(martes - pd.Timedelta(days=DIAS_ANTES_DEL_MARTES), martes)
        for periodo, cantidad in dias.to_period("M").value_counts().items():
            if periodo in reparto.index:
                reparto[periodo] += cantidad / len(dias)
    return reparto


def generar(semilla=SEMILLA):
    rng = np.random.default_rng(semilla)
    periodos = pd.period_range(INICIO, FIN, freq="M")
    n = len(periodos)
    calendario = calendario_carnaval()
    reparto = reparto_carnaval(calendario, periodos).values
    tamanio_carnaval = {anio: rng.normal(1, VARIACION_CARNAVAL) for anio in ANIOS_CARNAVAL}
    efecto_carnaval_anio = np.array([tamanio_carnaval.get(p.year, 1.0) for p in periodos])

    # Componente común del mercado: un mes caluroso o una economía floja afecta a todas las familias
    mercado = np.zeros(n)
    for i in range(n):
        mercado[i] = (AR_MERCADO * mercado[i - 1] if i else 0) + rng.normal(0, DESVIO_MERCADO)

    meses_desde_aumento = np.array([(p - MES_AUMENTO).n for p in periodos])
    pandemia_base = np.array([CAIDA_PANDEMIA.get(p, 0.0) for p in periodos])
    meses = np.array([p.month for p in periodos])

    tablas = []
    for familia, f in FAMILIAS.items():
        crecimiento = np.where(periodos < CAMBIO_TENDENCIA, f["crec_antes"], f["crec_desde"])
        log_tendencia = np.log(f["base"]) + np.concatenate([[0], np.cumsum(np.log1p(crecimiento[1:]) / 12)])
        deriva = np.cumsum(rng.normal(0, DESVIO_DERIVA, n))
        estacional = 1 + f["amplitud"] * (np.array([ESTACIONALIDAD[m] for m in meses]) - 1)
        carnaval = 1 + f["carnaval"] * reparto * efecto_carnaval_anio
        pandemia = 1 - pandemia_base * f["pandemia"]
        baja_por_precio = np.where(
            meses_desde_aumento >= 0,
            ELASTICIDAD_CORTO_PLAZO * f["aumento"] * RECUPERACION_MENSUAL ** np.clip(meses_desde_aumento, 0, None),
            0.0)
        ruido = rng.normal(0, f["ruido"], n)
        cajas = (np.exp(log_tendencia + deriva + mercado + ruido)
                 * estacional * carnaval * pandemia * (1 + baja_por_precio))

        precio = f["precio"] * np.where(meses_desde_aumento >= 0, 1 + f["aumento"], 1.0)
        precio = precio * (1 + rng.normal(0, DESVIO_PRECIO, n))
        tablas.append(pd.DataFrame({
            "periodo": periodos.astype(str),
            "familia": familia,
            "cajas": np.round(cajas).astype(int),
            "precio_promedio_bs": np.round(precio, 2),
        }))
    return pd.concat(tablas, ignore_index=True), calendario


def main():
    carpeta = Path(__file__).resolve().parent / "datos"
    carpeta.mkdir(exist_ok=True)
    ventas, calendario = generar()
    ventas.to_csv(carpeta / "ventas_mensuales.csv", index=False, encoding="utf-8")
    calendario.to_csv(carpeta / "calendario_carnaval.csv", index=False, encoding="utf-8")
    print(f"ventas_mensuales.csv: {len(ventas):,} filas ({ventas['periodo'].nunique()} meses, "
          f"{ventas['familia'].nunique()} familias)")
    print(f"calendario_carnaval.csv: {len(calendario)} años")


if __name__ == "__main__":
    main()

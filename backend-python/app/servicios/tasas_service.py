from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.modelos import OrigenTasa, TasaDiaria
from app.rutas.tasas import obtener_fecha_hoy, obtener_ultimo_recargo


URL_DOLARAPI_VE = "https://ve.dolarapi.com/v1/dolares"
HORAS_REFRESCO_AUTO = 4


def _a_decimal_4(valor: Any) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def consultar_dolarapi_venezuela(timeout: float = 5.0) -> tuple[Decimal, Decimal, str]:
    """
    Consulta la API pública ve.dolarapi.com/v1/dolares (timeout 5s) y devuelve
    (tasa_bcv, tasa_usdt, fuente). Lanza excepción si no responde o datos inválidos.
    """
    req = urllib.request.Request(
        URL_DOLARAPI_VE,
        headers={"Accept": "application/json", "User-Agent": "TekioAdmin/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        datos = json.loads(raw)

    if not isinstance(datos, list):
        raise ValueError("Respuesta inesperada de ve.dolarapi.com")

    tasa_bcv = Decimal("0")
    tasa_usdt = Decimal("0")

    for entrada in datos:
        if not isinstance(entrada, dict):
            continue
        fuente_item = str(entrada.get("fuente") or "").strip().lower()
        nombre_item = str(entrada.get("nombre") or "").strip().lower()
        promedio = entrada.get("promedio")
        if promedio is None:
            continue
        try:
            valor = _a_decimal_4(promedio)
        except Exception:
            continue
        if valor <= 0:
            continue

        if fuente_item == "oficial" or "oficial" in nombre_item or "bcv" in nombre_item:
            tasa_bcv = valor
        elif fuente_item == "paralelo" or "paralelo" in nombre_item or "usdt" in nombre_item:
            tasa_usdt = valor

    if tasa_bcv <= 0:
        raise ValueError("No se obtuvo tasa BCV válida desde ve.dolarapi.com")
    if tasa_usdt <= 0:
        tasa_usdt = tasa_bcv

    return tasa_bcv, tasa_usdt, "ve.dolarapi.com"


def sincronizar_tasas_dia(bd: Session, forzar: bool = False) -> TasaDiaria | None:
    """
    Obtiene o sincroniza el registro de tasas para hoy (America/Caracas).
    - Si no existe registro para hoy, consulta la API externa (con fallback al último
      registro en BD) y crea la fila con recargo_confirmado_hoy = False.
    - Si ya existe y forzar=True o pasaron más de 4h desde ultima_sincronizacion,
      refresca BCV y USDT conservando recargo_confirmado_hoy y recargo_porcentaje.
    """
    hoy = obtener_fecha_hoy()
    ahora_utc = datetime.now(timezone.utc)

    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha == hoy).first()

    necesita_sync = forzar or tasa is None
    if tasa is not None and not necesita_sync:
        ultima_sync = tasa.ultima_sincronizacion
        if ultima_sync is None:
            necesita_sync = False  # tasa cargada manualmente hoy sin forzar
        else:
            if ultima_sync.tzinfo is None:
                ultima_sync = ultima_sync.replace(tzinfo=timezone.utc)
            if ahora_utc - ultima_sync >= timedelta(hours=HORAS_REFRESCO_AUTO):
                necesita_sync = True

    if not necesita_sync:
        return tasa

    tasa_bcv: Decimal | None = None
    tasa_usdt: Decimal | None = None
    fuente = "ve.dolarapi.com"

    try:
        tasa_bcv, tasa_usdt, fuente = consultar_dolarapi_venezuela(timeout=5.0)
    except Exception:
        # Fallback seguro al último registro guardado en BD
        ultima_bd = (
            bd.query(TasaDiaria)
            .order_by(TasaDiaria.fecha.desc(), TasaDiaria.id.desc())
            .first()
        )
        if ultima_bd is not None:
            tasa_bcv = ultima_bd.tasa_bcv
            tasa_usdt = ultima_bd.tasa_usdt
            fuente = "fallback_db"
        else:
            return tasa

    assert tasa_bcv is not None and tasa_usdt is not None

    if tasa is None:
        recargo_heredado = obtener_ultimo_recargo(bd)
        tasa = TasaDiaria(
            fecha=hoy,
            tasa_bcv=tasa_bcv,
            tasa_usdt=tasa_usdt,
            recargo_porcentaje=recargo_heredado if recargo_heredado is not None else Decimal("0"),
            origen=OrigenTasa.AUTOMATICO.value,
            recargo_confirmado_hoy=False,
            fuente=fuente,
            ultima_sincronizacion=ahora_utc,
            nota="Sincronización automática diaria",
        )
        bd.add(tasa)
    else:
        tasa.tasa_bcv = tasa_bcv
        tasa.tasa_usdt = tasa_usdt
        tasa.fuente = fuente
        tasa.ultima_sincronizacion = ahora_utc

    bd.commit()
    bd.refresh(tasa)
    return tasa

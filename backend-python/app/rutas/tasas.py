from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.configuracion import configuracion
from app.esquemas import (
    TasaActualizarHoyEntrada,
    TasaCrearEntrada,
    TasaHoySalida,
    TasaSalida,
    TasasPaginadasSalida,
)
from app.modelos import OrigenTasa, TasaDiaria, Usuario
from app.seguridad import ROLES_ADMINISTRATIVOS, obtener_usuario_actual, requerir_roles


enrutador = APIRouter(prefix="/api/tasas", tags=["Tasas Diarias"])


def obtener_fecha_hoy() -> date:
    """Obtiene la fecha actual en la zona horaria de Venezuela (America/Caracas)."""
    return datetime.now(ZoneInfo(configuracion.ZONA_HORARIA)).date()


def calcular_brecha_porcentaje(tasa_bcv: Decimal, tasa_usdt: Decimal) -> float:
    if tasa_bcv <= 0:
        return 0.0
    brecha = ((tasa_usdt - tasa_bcv) / tasa_bcv) * Decimal("100")
    return float(round(brecha, 2))


def serializar_tasa(tasa: TasaDiaria) -> TasaSalida:
    return TasaSalida(
        id=tasa.id,
        fecha=tasa.fecha,
        tasa_bcv=float(tasa.tasa_bcv),
        tasa_usdt=float(tasa.tasa_usdt),
        recargo_porcentaje=float(tasa.recargo_porcentaje),
        brecha_porcentaje=calcular_brecha_porcentaje(tasa.tasa_bcv, tasa.tasa_usdt),
        origen=OrigenTasa(tasa.origen),
        nota=tasa.nota or "",
        publicado_por=tasa.publicado_por.nombre if tasa.publicado_por else None,
        actualizado_en=tasa.actualizado_en,
    )


def obtener_ultimo_recargo(bd: Session) -> Decimal | None:
    ultima = bd.query(TasaDiaria).order_by(TasaDiaria.fecha.desc()).first()
    return ultima.recargo_porcentaje if ultima else None


@enrutador.get("/hoy", response_model=TasaHoySalida)
def obtener_tasa_hoy(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> TasaHoySalida:
    hoy = obtener_fecha_hoy()
    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha == hoy).first()

    if tasa is None:
        recargo_heredado = obtener_ultimo_recargo(bd)
        return TasaHoySalida(
            fecha=hoy,
            permite_bolivares=False,
            alerta="Sin tasa del día — Cobros en Bs bloqueados",
            recargo_porcentaje=float(recargo_heredado) if recargo_heredado is not None else None,
        )

    return TasaHoySalida(
        fecha=tasa.fecha,
        permite_bolivares=True,
        alerta=None,
        tasa_bcv=float(tasa.tasa_bcv),
        tasa_usdt=float(tasa.tasa_usdt),
        recargo_porcentaje=float(tasa.recargo_porcentaje),
        brecha_porcentaje=calcular_brecha_porcentaje(tasa.tasa_bcv, tasa.tasa_usdt),
        origen=OrigenTasa(tasa.origen),
        nota=tasa.nota or "",
        actualizado_en=tasa.actualizado_en,
    )


@enrutador.get("", response_model=TasasPaginadasSalida)
def listar_tasas(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> TasasPaginadasSalida:
    consulta = bd.query(TasaDiaria).options(joinedload(TasaDiaria.publicado_por))
    if desde is not None:
        consulta = consulta.filter(TasaDiaria.fecha >= desde)
    if hasta is not None:
        consulta = consulta.filter(TasaDiaria.fecha <= hasta)

    total = consulta.count()
    filas = (
        consulta.order_by(TasaDiaria.fecha.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    return TasasPaginadasSalida(
        elementos=[serializar_tasa(f) for f in filas],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@enrutador.post("", response_model=TasaSalida, status_code=status.HTTP_201_CREATED)
def crear_tasa(
    datos: TasaCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> TasaSalida:
    hoy = obtener_fecha_hoy()
    if datos.fecha < hoy:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No está permitido registrar ni modificar tasas de fechas pasadas.",
        )

    existente = bd.query(TasaDiaria).filter(TasaDiaria.fecha == datos.fecha).first()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una tasa registrada para esa fecha.",
        )

    recargo = datos.recargo_porcentaje
    if recargo is None:
        recargo = obtener_ultimo_recargo(bd)
        if recargo is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar el porcentaje de recargo al registrar la primera tasa.",
            )

    nueva = TasaDiaria(
        fecha=datos.fecha,
        tasa_bcv=datos.tasa_bcv,
        tasa_usdt=datos.tasa_usdt,
        recargo_porcentaje=recargo,
        origen=OrigenTasa.MANUAL.value,
        publicado_por_id=usuario_actual.id,
        nota=datos.nota.strip(),
    )
    bd.add(nueva)
    bd.commit()
    bd.refresh(nueva)

    tasa_completa = (
        bd.query(TasaDiaria)
        .options(joinedload(TasaDiaria.publicado_por))
        .filter(TasaDiaria.id == nueva.id)
        .first()
    )
    return serializar_tasa(tasa_completa)


@enrutador.put("/hoy", response_model=TasaSalida)
def actualizar_tasa_hoy(
    datos: TasaActualizarHoyEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> TasaSalida:
    hoy = obtener_fecha_hoy()
    tasa = (
        bd.query(TasaDiaria)
        .options(joinedload(TasaDiaria.publicado_por))
        .filter(TasaDiaria.fecha == hoy)
        .first()
    )

    if tasa is None:
        if datos.tasa_bcv is None or datos.tasa_usdt is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No existe tasa registrada para hoy. Debes indicar tasa_bcv y tasa_usdt.",
            )
        recargo = datos.recargo_porcentaje
        if recargo is None:
            recargo = obtener_ultimo_recargo(bd)
            if recargo is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Debes indicar el porcentaje de recargo para crear la primera tasa del día.",
                )
        tasa = TasaDiaria(
            fecha=hoy,
            tasa_bcv=datos.tasa_bcv,
            tasa_usdt=datos.tasa_usdt,
            recargo_porcentaje=recargo,
            origen=OrigenTasa.MANUAL.value,
            publicado_por_id=usuario_actual.id,
            nota=(datos.nota or "").strip(),
        )
        bd.add(tasa)
    else:
        if datos.tasa_bcv is not None:
            tasa.tasa_bcv = datos.tasa_bcv
        if datos.tasa_usdt is not None:
            tasa.tasa_usdt = datos.tasa_usdt
        if datos.recargo_porcentaje is not None:
            tasa.recargo_porcentaje = datos.recargo_porcentaje
        if datos.nota is not None:
            tasa.nota = datos.nota.strip()
        tasa.origen = OrigenTasa.MANUAL.value
        tasa.recargo_confirmado_hoy = True
        tasa.publicado_por_id = usuario_actual.id

    bd.commit()
    tasa_actualizada = (
        bd.query(TasaDiaria)
        .options(joinedload(TasaDiaria.publicado_por))
        .filter(TasaDiaria.fecha == hoy)
        .first()
    )
    return serializar_tasa(tasa_actualizada)

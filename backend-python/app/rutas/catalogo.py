from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import (
    ArticuloCatalogoConCostoSalida,
    ArticuloCatalogoPublicoSalida,
    ArticuloCrearEntrada,
    ArticuloEstadoEntrada,
    CatalogoPaginadoConCostoSalida,
    CatalogoPaginadoPublicoSalida,
    PrecioCrearEntrada,
    PrecioHistorialConCostoSalida,
    PrecioHistorialPublicoSalida,
    normalizar_sku,
)
from app.modelos import (
    CatalogoArticulo,
    CatalogoPrecio,
    RolUsuario,
    TasaDiaria,
    TipoArticulo,
    Usuario,
)
from app.core.permisos import Permiso, require_permiso, sanear_respuesta_costos
from app.rutas.tasas import obtener_fecha_hoy
from app.servicios.auditoria_service import registrar_auditoria
from app.seguridad import (
    ROLES_ADMINISTRATIVOS,
    obtener_usuario_actual,
    puede_ver_costos,
    requerir_roles,
)


enrutador = APIRouter(prefix="/api/catalogo", tags=["Catálogo y Precios"])

ROLES_GESTION_CATALOGO: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
)


def redondear_moneda(valor: Decimal) -> float:
    return float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def obtener_contexto_tasa(bd: Session, hoy: date) -> tuple[Decimal, Decimal | None]:
    """Devuelve (recargo_porcentaje, tasa_bcv_hoy)."""
    tasa_hoy = bd.query(TasaDiaria).filter(TasaDiaria.fecha == hoy).first()
    if tasa_hoy is not None:
        return tasa_hoy.recargo_porcentaje, tasa_hoy.tasa_bcv
    ultima = bd.query(TasaDiaria).order_by(TasaDiaria.fecha.desc()).first()
    recargo = ultima.recargo_porcentaje if ultima is not None else Decimal("0")
    return recargo, None


def obtener_precio_vigente(articulo: CatalogoArticulo, hoy: date) -> CatalogoPrecio | None:
    vigentes = [p for p in articulo.precios if p.fecha_vigencia <= hoy]
    if vigentes:
        vigentes.sort(key=lambda p: (p.fecha_vigencia, p.id), reverse=True)
        return vigentes[0]
    if articulo.precios:
        ordenados = sorted(articulo.precios, key=lambda p: (p.fecha_vigencia, p.id), reverse=True)
        return ordenados[0]
    return None


def construir_articulo_salida(
    articulo: CatalogoArticulo,
    precio: CatalogoPrecio | None,
    recargo_pct: Decimal,
    tasa_bcv_hoy: Decimal | None,
    incluir_costo: bool,
) -> dict[str, Any]:
    promo = precio.precio_promo_usd if precio else Decimal("0")
    regular_fijo = precio.precio_regular_fijo_usd if precio else None

    if regular_fijo is not None:
        regular_usd = regular_fijo
    else:
        factor = Decimal("1") + (recargo_pct / Decimal("100"))
        regular_usd = promo * factor

    regular_bs = (
        redondear_moneda(regular_usd * tasa_bcv_hoy)
        if tasa_bcv_hoy is not None and tasa_bcv_hoy > 0
        else None
    )

    datos_base: dict[str, Any] = {
        "id": articulo.id,
        "sku": articulo.sku,
        "descripcion": articulo.descripcion,
        "tipo": TipoArticulo(articulo.tipo),
        "categoria": articulo.categoria,
        "activo": articulo.activo,
        "precio_promo_usd": redondear_moneda(promo),
        "precio_regular_fijo_usd": redondear_moneda(regular_fijo) if regular_fijo is not None else None,
        "precio_regular_usd": redondear_moneda(regular_usd),
        "precio_regular_bs": regular_bs,
        "fecha_vigencia": precio.fecha_vigencia if precio else None,
        "creado_en": articulo.creado_en,
    }

    if incluir_costo:
        datos_base["costo_referencia_usd"] = (
            redondear_moneda(precio.costo_referencia_usd)
            if precio and precio.costo_referencia_usd is not None
            else None
        )
        return ArticuloCatalogoConCostoSalida(**datos_base).model_dump()

    return ArticuloCatalogoPublicoSalida(**datos_base).model_dump()


@enrutador.get("")
def listar_catalogo(
    busqueda: str | None = Query(default=None),
    tipo: TipoArticulo | None = Query(default=None),
    categoria: str | None = Query(default=None),
    incluir_inactivos: bool = Query(default=False),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=1000),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    recargo_pct, tasa_bcv_hoy = obtener_contexto_tasa(bd, hoy)
    incluir_costo = puede_ver_costos(usuario_actual.rol)

    consulta = bd.query(CatalogoArticulo).options(joinedload(CatalogoArticulo.precios))
    if not incluir_inactivos:
        consulta = consulta.filter(CatalogoArticulo.activo.is_(True))
    if tipo is not None:
        consulta = consulta.filter(CatalogoArticulo.tipo == tipo.value)
    if categoria:
        consulta = consulta.filter(CatalogoArticulo.categoria.ilike(f"%{categoria.strip()}%"))
    if busqueda and busqueda.strip():
        texto = busqueda.strip()
        try:
            sku_busqueda = normalizar_sku(texto)
        except ValueError:
            sku_busqueda = texto.upper()
        consulta = consulta.filter(
            or_(
                CatalogoArticulo.sku.ilike(f"%{sku_busqueda}%"),
                CatalogoArticulo.descripcion.ilike(f"%{texto}%"),
            )
        )

    total = consulta.count()
    articulos = (
        consulta.order_by(CatalogoArticulo.sku.asc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    elementos = [
        construir_articulo_salida(
            articulo=art,
            precio=obtener_precio_vigente(art, hoy),
            recargo_pct=recargo_pct,
            tasa_bcv_hoy=tasa_bcv_hoy,
            incluir_costo=incluir_costo,
        )
        for art in articulos
    ]

    esquema_respuesta = (
        CatalogoPaginadoConCostoSalida if incluir_costo else CatalogoPaginadoPublicoSalida
    )
    return sanear_respuesta_costos(
        esquema_respuesta(
            elementos=elementos,
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
            recargo_aplicado_porcentaje=float(recargo_pct),
            tasa_bcv_aplicada=float(tasa_bcv_hoy) if tasa_bcv_hoy is not None else None,
        ).model_dump(),
        usuario_actual.rol,
    )


@enrutador.post("", status_code=status.HTTP_201_CREATED)
def crear_articulo_catalogo(
    datos: ArticuloCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_CATALOGO)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    existente = bd.query(CatalogoArticulo).filter(CatalogoArticulo.sku == datos.sku).first()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El SKU '{datos.sku}' ya existe en el catálogo. No se permiten duplicados.",
        )

    hoy = obtener_fecha_hoy()
    fecha_vigencia = datos.fecha_vigencia or hoy

    nuevo_articulo = CatalogoArticulo(
        sku=datos.sku,
        descripcion=datos.descripcion,
        tipo=datos.tipo.value,
        categoria=datos.categoria,
        activo=True,
    )
    bd.add(nuevo_articulo)
    bd.flush()

    precio_inicial = CatalogoPrecio(
        articulo_id=nuevo_articulo.id,
        precio_promo_usd=datos.precio_promo_usd,
        precio_regular_fijo_usd=datos.precio_regular_fijo_usd,
        costo_referencia_usd=datos.costo_referencia_usd,
        fecha_vigencia=fecha_vigencia,
        creado_por_id=usuario_actual.id,
    )
    bd.add(precio_inicial)
    bd.commit()
    bd.refresh(nuevo_articulo)
    bd.refresh(precio_inicial)

    recargo_pct, tasa_bcv_hoy = obtener_contexto_tasa(bd, hoy)
    return construir_articulo_salida(
        articulo=nuevo_articulo,
        precio=precio_inicial,
        recargo_pct=recargo_pct,
        tasa_bcv_hoy=tasa_bcv_hoy,
        incluir_costo=puede_ver_costos(usuario_actual.rol),
    )


@enrutador.post("/{articulo_id}/precios", status_code=status.HTTP_201_CREATED)
def registrar_nuevo_precio(
    articulo_id: int,
    datos: PrecioCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_CATALOGO)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    articulo = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == articulo_id).first()
    if articulo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado en el catálogo.",
        )

    nuevo_precio = CatalogoPrecio(
        articulo_id=articulo.id,
        precio_promo_usd=datos.precio_promo_usd,
        precio_regular_fijo_usd=datos.precio_regular_fijo_usd,
        costo_referencia_usd=datos.costo_referencia_usd,
        fecha_vigencia=datos.fecha_vigencia,
        creado_por_id=usuario_actual.id,
    )
    bd.add(nuevo_precio)
    registrar_auditoria(
        bd,
        usuario_actual,
        "CATALOGO",
        "ACTUALIZAR_PRECIO_COSTO",
        articulo.sku,
        {},
        {
            "precio_promo_usd": float(datos.precio_promo_usd),
            "costo_referencia_usd": float(datos.costo_referencia_usd) if datos.costo_referencia_usd is not None else None,
        },
    )
    bd.commit()
    bd.refresh(nuevo_precio)

    base = {
        "id": nuevo_precio.id,
        "precio_promo_usd": redondear_moneda(nuevo_precio.precio_promo_usd),
        "precio_regular_fijo_usd": (
            redondear_moneda(nuevo_precio.precio_regular_fijo_usd)
            if nuevo_precio.precio_regular_fijo_usd is not None
            else None
        ),
        "fecha_vigencia": nuevo_precio.fecha_vigencia,
        "creado_por": usuario_actual.nombre,
        "creado_en": nuevo_precio.creado_en,
    }
    if puede_ver_costos(usuario_actual.rol):
        base["costo_referencia_usd"] = (
            redondear_moneda(nuevo_precio.costo_referencia_usd)
            if nuevo_precio.costo_referencia_usd is not None
            else None
        )
        return PrecioHistorialConCostoSalida(**base).model_dump()

    return PrecioHistorialPublicoSalida(**base).model_dump()


@enrutador.get("/{articulo_id}/precios")
def obtener_historial_precios(
    articulo_id: int,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    articulo = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == articulo_id).first()
    if articulo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado en el catálogo.",
        )

    precios = (
        bd.query(CatalogoPrecio)
        .options(joinedload(CatalogoPrecio.creado_por))
        .filter(CatalogoPrecio.articulo_id == articulo_id)
        .order_by(CatalogoPrecio.fecha_vigencia.desc(), CatalogoPrecio.id.desc())
        .all()
    )

    incluir_costo = puede_ver_costos(usuario_actual.rol)
    resultado: list[dict[str, Any]] = []
    for p in precios:
        base: dict[str, Any] = {
            "id": p.id,
            "precio_promo_usd": redondear_moneda(p.precio_promo_usd),
            "precio_regular_fijo_usd": (
                redondear_moneda(p.precio_regular_fijo_usd)
                if p.precio_regular_fijo_usd is not None
                else None
            ),
            "fecha_vigencia": p.fecha_vigencia,
            "creado_por": p.creado_por.nombre if p.creado_por else None,
            "creado_en": p.creado_en,
        }
        if incluir_costo:
            base["costo_referencia_usd"] = (
                redondear_moneda(p.costo_referencia_usd)
                if p.costo_referencia_usd is not None
                else None
            )
            resultado.append(PrecioHistorialConCostoSalida(**base).model_dump())
        else:
            resultado.append(PrecioHistorialPublicoSalida(**base).model_dump())
    return sanear_respuesta_costos(resultado, usuario_actual.rol)


@enrutador.patch("/{articulo_id}/estado")
def cambiar_estado_articulo(
    articulo_id: int,
    datos: ArticuloEstadoEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    articulo = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == articulo_id).first()
    if articulo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado en el catálogo.",
        )
    articulo.activo = datos.activo
    bd.commit()
    return {"id": articulo.id, "sku": articulo.sku, "activo": articulo.activo}

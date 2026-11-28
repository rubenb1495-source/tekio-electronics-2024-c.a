from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_logistica import normalizar_serial
from app.esquemas_taller import (
    CasoActualizarEntrada,
    CasoCrearEntrada,
    ComponentePreparacionAgregarEntrada,
    PreparacionCrearEntrada,
    PresupuestoAprobarEntrada,
    PresupuestoCrearEntrada,
    RecepcionTallerCrearEntrada,
    RepuestoEstadoEntrada,
)
from app.modelos import CatalogoArticulo, CatalogoPrecio, RolUsuario, Sucursal, TipoArticulo, Usuario
from app.modelos_finanzas import EstadoVenta, Venta, VentaDetalle
from app.modelos_logistica import (
    Equipo,
    EstadoEquipo,
    MovimientoInventario,
    Tercero,
    TipoMovimientoInventario,
)
from app.modelos_taller import (
    CasoPostventa,
    CasoPresupuesto,
    CasoRepuestoUsado,
    EstadoCasoPostventa,
    EstadoRepuestoSolicitado,
    OrigenRepuestoSolicitado,
    Preparacion,
    PreparacionComponente,
    RepuestoSolicitado,
    ResultadoPreparacion,
    TipoCasoPostventa,
    TipoPreparacion,
)
from app.rutas.logistica import calcular_stock_componente, obtener_bodega
from app.rutas.tasas import obtener_fecha_hoy
from app.seguridad import obtener_usuario_actual, puede_ver_costos, requerir_roles


enrutador = APIRouter(prefix="/api/taller", tags=["Taller Técnico y Postventa"])

ROLES_TALLER: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.LIDER.value,
    RolUsuario.TECNICO.value,
)

ROLES_ACTUALIZAR_REPUESTOS: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
)


def redondear_usd(valor: Decimal) -> float:
    return float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def obtener_costo_referencia_articulo(bd: Session, articulo_id: int) -> Decimal:
    hoy = obtener_fecha_hoy()
    precio = (
        bd.query(CatalogoPrecio)
        .filter(
            CatalogoPrecio.articulo_id == articulo_id,
            CatalogoPrecio.fecha_vigencia <= hoy,
        )
        .order_by(CatalogoPrecio.fecha_vigencia.desc(), CatalogoPrecio.id.desc())
        .first()
    )
    if precio and precio.costo_referencia_usd is not None:
        return precio.costo_referencia_usd
    return Decimal("0.00")


def generar_numero_caso(bd: Session, tipo: TipoCasoPostventa) -> str:
    prefijo = "GT" if tipo == TipoCasoPostventa.GARANTIA else "ST"
    cantidad = (
        bd.query(func.count(CasoPostventa.id))
        .filter(CasoPostventa.numero_caso.like(f"{prefijo}-%"))
        .scalar()
        or 0
    )
    secuencia = int(cantidad) + 1
    while True:
        candidato = f"{prefijo}-{secuencia:04d}"
        existe = bd.query(CasoPostventa.id).filter(CasoPostventa.numero_caso == candidato).first()
        if not existe:
            return candidato
        secuencia += 1


# ---------------- Cola de Taller y Preparaciones ----------------


@enrutador.get("/preparaciones/{equipo_id}/componentes")
def listar_componentes_equipo_preparacion(
    equipo_id: int,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    from app.core.permisos import sanear_respuesta_costos
    from app.modelos_contabilidad import ComponenteInstaladoEquipo

    eq = bd.query(Equipo).filter(Equipo.id == equipo_id).first()
    if eq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipo no encontrado.",
        )
    filas = (
        bd.query(ComponenteInstaladoEquipo)
        .options(
            joinedload(ComponenteInstaladoEquipo.articulo),
            joinedload(ComponenteInstaladoEquipo.instalado_por),
        )
        .filter(ComponenteInstaladoEquipo.equipo_id == equipo_id)
        .order_by(ComponenteInstaladoEquipo.id.desc())
        .all()
    )
    incluir_costos = puede_ver_costos(usuario_actual.rol)
    respuesta: list[dict[str, Any]] = []
    for f in filas:
        item: dict[str, Any] = {
            "id": f.id,
            "equipo_id": f.equipo_id,
            "articulo_id": f.articulo_id,
            "sku": f.articulo.sku if f.articulo else "",
            "descripcion": f.articulo.descripcion if f.articulo else "",
            "cantidad": f.cantidad,
            "nota": f.nota,
            "instalado_por": f.instalado_por.nombre if f.instalado_por else "",
            "creado_en": f.creado_en.isoformat() if f.creado_en else None,
        }
        if incluir_costos:
            item["costo_unitario_usd"] = redondear_usd(f.costo_unitario_usd)
            item["costo_total_usd"] = redondear_usd(f.costo_total_usd)
        respuesta.append(item)
    return sanear_respuesta_costos(respuesta, usuario_actual.rol)


@enrutador.post("/preparaciones/{equipo_id}/componentes", status_code=status.HTTP_201_CREATED)
def agregar_componente_a_equipo_preparacion(
    equipo_id: int,
    datos: ComponentePreparacionAgregarEntrada,
    usuario_actual: Usuario = Depends(
        requerir_roles(
            RolUsuario.DIRECCION.value,
            RolUsuario.ADMINISTRACION.value,
            RolUsuario.LOGISTICA.value,
            RolUsuario.LIDER.value,
            RolUsuario.TECNICO.value,
            RolUsuario.ENCARGADO.value,
        )
    ),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """
    Agrega un componente del inventario (RAM, SSD, cargador, batería, etc.) a un equipo en preparación:
    - Descuenta del inventario de componentes.
    - Registra el componente instalado en la ficha del equipo y actualiza su configuración.
    - Suma el costo del componente al `costo_taller_usd` (impactando directamente `costo_total_usd`).
    - Genera asiento de reclasificación contable: Debe Inventario Equipos (1.1.04) / Haber Inventario Componentes (1.1.05).
    - RBAC: El técnico jamás recibe campos de costo en USD.
    """
    from app.core.permisos import sanear_respuesta_costos
    from app.modelos_contabilidad import ComponenteInstaladoEquipo
    from app.servicios.auditoria_service import registrar_auditoria
    from app.servicios.contabilidad_service import registrar_asiento

    eq = bd.query(Equipo).filter(Equipo.id == equipo_id).first()
    if eq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipo no encontrado.",
        )
    if eq.estado == EstadoEquipo.VENDIDO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden instalar componentes a un equipo que ya está VENDIDO.",
        )

    art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == datos.articulo_id).first()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Componente no encontrado en el catálogo.",
        )

    # Verificar stock disponible del componente en el inventario (Kardex por SKU: equipo_id IS NULL)
    stock_sucursal = int(
        bd.query(func.coalesce(func.sum(MovimientoInventario.cantidad), 0))
        .filter(
            MovimientoInventario.equipo_id.is_(None),
            MovimientoInventario.articulo_id == art.id,
            MovimientoInventario.sucursal_id == eq.ubicacion_id,
        )
        .scalar()
        or 0
    )
    sucursal_descuento = eq.ubicacion_id
    if stock_sucursal < datos.cantidad:
        # Buscar si hay stock en otra sucursal (ej. Bodega)
        stock_global = int(
            bd.query(func.coalesce(func.sum(MovimientoInventario.cantidad), 0))
            .filter(
                MovimientoInventario.equipo_id.is_(None),
                MovimientoInventario.articulo_id == art.id,
            )
            .scalar()
            or 0
        )
        if stock_global < datos.cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente del componente '{art.descripcion}' (disponible: {stock_global}, requerido: {datos.cantidad}).",
            )
        # Ubicar sucursal con saldo positivo
        filas_suc = (
            bd.query(
                MovimientoInventario.sucursal_id,
                func.sum(MovimientoInventario.cantidad).label("saldo"),
            )
            .filter(
                MovimientoInventario.equipo_id.is_(None),
                MovimientoInventario.articulo_id == art.id,
            )
            .group_by(MovimientoInventario.sucursal_id)
            .all()
        )
        for sid, saldo in filas_suc:
            if int(saldo or 0) >= datos.cantidad:
                sucursal_descuento = sid
                break

    # Determinar costo unitario del componente (último ingreso de inventario o costo referencia)
    ultimo_ing = (
        bd.query(MovimientoInventario)
        .filter(
            MovimientoInventario.equipo_id.is_(None),
            MovimientoInventario.articulo_id == art.id,
            MovimientoInventario.cantidad > 0,
            MovimientoInventario.costo_unitario_usd > Decimal("0"),
        )
        .order_by(MovimientoInventario.id.desc())
        .first()
    )
    costo_unit = (
        ultimo_ing.costo_unitario_usd
        if ultimo_ing is not None
        else obtener_costo_referencia_articulo(bd, art.id)
    )
    costo_unit = Decimal(str(costo_unit)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    costo_total_comp = (costo_unit * datos.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    hoy = obtener_fecha_hoy()
    bd.add(
        MovimientoInventario(
            tipo=TipoMovimientoInventario.TALLER.value,
            articulo_id=art.id,
            equipo_id=None,
            sucursal_id=sucursal_descuento,
            cantidad=-datos.cantidad,
            costo_unitario_usd=costo_unit,
            documento_ref=f"PREP-COMP-{eq.serial}",
            motivo=f"Componente instalado en preparación ({eq.serial}): {datos.cantidad}x {art.descripcion}",
            usuario_id=usuario_actual.id,
        )
    )

    instalado = ComponenteInstaladoEquipo(
        equipo_id=eq.id,
        articulo_id=art.id,
        cantidad=datos.cantidad,
        costo_unitario_usd=costo_unit,
        costo_total_usd=costo_total_comp,
        nota=datos.nota.strip(),
        instalado_por_id=usuario_actual.id,
    )
    bd.add(instalado)
    bd.flush()

    costo_anterior = eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd
    eq.costo_taller_usd = (eq.costo_taller_usd + costo_total_comp).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    costo_nuevo = eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd

    etiqueta_comp = f"+ {datos.cantidad}x {art.descripcion}"
    if etiqueta_comp not in (eq.configuracion or ""):
        eq.configuracion = (
            f"{eq.configuracion} | {etiqueta_comp}".strip(" |")[:255]
        )

    if costo_total_comp > Decimal("0.00"):
        registrar_asiento(
            bd,
            fecha=hoy,
            referencia=f"PREP-COMP-{eq.serial}",
            modulo_origen="TALLER_COMPONENTES",
            entidad_id=instalado.id,
            descripcion=f"Instalación de {datos.cantidad}x {art.descripcion} en equipo {eq.serial}",
            lineas=[
                {
                    "codigo_cuenta": "1.1.04",
                    "debe_usd": costo_total_comp,
                    "descripcion": f"Aumento costo equipo {eq.serial}",
                },
                {
                    "codigo_cuenta": "1.1.05",
                    "haber_usd": costo_total_comp,
                    "descripcion": f"Descarga componente {art.sku}",
                },
            ],
            creado_por_id=usuario_actual.id,
        )

    if eq.primer_costo_usd is None or eq.primer_costo_usd == Decimal("0"):
        eq.primer_costo_usd = (eq.costo_compra_usd or Decimal("0")) + (eq.costo_flete_usd or Decimal("0"))
    eq.costo_final_usd = (
        (eq.primer_costo_usd or Decimal("0"))
        + (eq.costo_taller_usd or Decimal("0"))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="TALLER",
        accion="INSTALAR_COMPONENTE_EQUIPO",
        entidad_id=eq.serial,
        detalle_anterior={"costo_total_usd": float(costo_anterior)},
        detalle_nuevo={
            "articulo": art.descripcion,
            "cantidad": datos.cantidad,
            "costo_componente_usd": float(costo_total_comp),
            "costo_total_usd": float(costo_nuevo),
        },
    )
    bd.commit()

    payload: dict[str, Any] = {
        "id": instalado.id,
        "equipo_id": eq.id,
        "serial": eq.serial,
        "articulo_id": art.id,
        "sku": art.sku,
        "descripcion": art.descripcion,
        "cantidad": datos.cantidad,
        "configuracion_actualizada": eq.configuracion,
        "nota": instalado.nota,
    }
    if puede_ver_costos(usuario_actual.rol):
        payload["costo_unitario_usd"] = redondear_usd(costo_unit)
        payload["costo_total_componente_usd"] = redondear_usd(costo_total_comp)
        payload["costo_total_equipo_usd"] = redondear_usd(costo_nuevo)
    return sanear_respuesta_costos(payload, usuario_actual.rol)

@enrutador.get("/cola")
def obtener_cola_taller(
    estado: str | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    hoy = obtener_fecha_hoy()
    incluir_costos = puede_ver_costos(usuario_actual.rol)

    estados_cola = [
        EstadoEquipo.EN_REVISION.value,
        EstadoEquipo.POR_PREPARAR.value,
        EstadoEquipo.EN_PREPARACION.value,
        EstadoEquipo.HOSPITAL.value,
    ]
    if estado in estados_cola:
        estados_filtro = [estado]
    else:
        estados_filtro = estados_cola

    consulta = (
        bd.query(Equipo)
        .options(joinedload(Equipo.ubicacion))
        .filter(Equipo.estado.in_(estados_filtro))
    )
    if sucursal_id is not None:
        consulta = consulta.filter(Equipo.ubicacion_id == sucursal_id)

    equipos = consulta.order_by(Equipo.id.asc()).all()
    equipos_ids = [e.id for e in equipos]

    repuestos_recibidos_ids: set[int] = set()
    repuestos_pendientes_map: dict[int, list[str]] = {}
    if equipos_ids:
        repuestos = (
            bd.query(RepuestoSolicitado)
            .filter(RepuestoSolicitado.equipo_id.in_(equipos_ids))
            .all()
        )
        for r in repuestos:
            if r.equipo_id is None:
                continue
            if r.estado == EstadoRepuestoSolicitado.RECIBIDO.value:
                repuestos_recibidos_ids.add(r.equipo_id)
            elif r.estado in (
                EstadoRepuestoSolicitado.PENDIENTE.value,
                EstadoRepuestoSolicitado.COMPRADO.value,
            ):
                repuestos_pendientes_map.setdefault(r.equipo_id, []).append(r.descripcion_repuesto)

    salida: list[dict[str, Any]] = []
    for eq in equipos:
        fecha_base = eq.fecha_recepcion or eq.creado_en.date()
        dias = max(0, (hoy - fecha_base).days)
        item: dict[str, Any] = {
            "id": eq.id,
            "serial": eq.serial,
            "modelo": eq.modelo,
            "configuracion": eq.configuracion,
            "categoria": eq.categoria,
            "ubicacion_id": eq.ubicacion_id,
            "ubicacion": eq.ubicacion.nombre if eq.ubicacion else None,
            "estado": eq.estado,
            "dias_en_taller": dias,
            "repuesto_disponible": eq.id in repuestos_recibidos_ids,
            "repuestos_pendientes": repuestos_pendientes_map.get(eq.id, []),
            "condicion_llegada": getattr(eq, "condicion_llegada", "BUENO"),
            "incluye_cargador": getattr(eq, "incluye_cargador", True),
            "observaciones_llegada": getattr(eq, "observaciones_llegada", ""),
            "nota": eq.nota,
        }
        if incluir_costos:
            item["costo_taller_usd"] = redondear_usd(eq.costo_taller_usd)
        salida.append(item)

    return salida


@enrutador.post("/preparaciones", status_code=status.HTTP_201_CREATED)
def registrar_preparacion(
    datos: PreparacionCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    equipo = bd.query(Equipo).filter(Equipo.id == datos.equipo_id).first()
    if equipo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El equipo indicado no existe en el inventario.",
        )

    if datos.tipo == TipoPreparacion.ESPECIAL:
        if datos.pago_tecnico_usd is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para una preparación ESPECIAL debes indicar pago_tecnico_usd.",
            )
        pago_tecnico = datos.pago_tecnico_usd
    else:
        pago_tecnico = (
            datos.pago_tecnico_usd if datos.pago_tecnico_usd is not None else Decimal("1.00")
        )

    if datos.resultado == ResultadoPreparacion.HOSPITAL:
        if not datos.repuestos_faltantes and not datos.nota.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Al enviar un equipo a HOSPITAL debes indicar al menos un repuesto faltante o una nota explicativa.",
            )

    bodega = obtener_bodega(bd)

    # Validar stock en Bodega antes de aplicar descuentos (sin permitir negativo)
    articulos_info: list[tuple[CatalogoArticulo, int, Decimal]] = []
    for comp in datos.componentes_usados:
        art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == comp.articulo_id).first()
        if art is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El componente ID {comp.articulo_id} no existe en el catálogo.",
            )
        disponible = calcular_stock_componente(bd, art.id, bodega.id)
        if disponible < comp.cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente en Bodega para '{art.sku}' (disponible: {disponible}, solicitado: {comp.cantidad}).",
            )
        costo_ref = obtener_costo_referencia_articulo(bd, art.id)
        articulos_info.append((art, comp.cantidad, costo_ref))

    hoy = obtener_fecha_hoy()
    prep = Preparacion(
        equipo_id=equipo.id,
        tecnico_id=usuario_actual.id,
        fecha=hoy,
        tipo=datos.tipo.value,
        pago_tecnico_usd=pago_tecnico,
        resultado=datos.resultado.value,
        nota=datos.nota.strip(),
    )
    bd.add(prep)
    bd.flush()

    costo_componentes_total = Decimal("0.00")
    for art, cant, costo_ref in articulos_info:
        bd.add(
            PreparacionComponente(
                preparacion_id=prep.id,
                articulo_id=art.id,
                cantidad=cant,
                costo_unitario_snapshot_usd=costo_ref,
            )
        )
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.TALLER.value,
                articulo_id=art.id,
                equipo_id=None,
                sucursal_id=bodega.id,
                cantidad=-cant,
                costo_unitario_usd=costo_ref,
                documento_ref=f"PREP-{prep.id}",
                motivo=f"Componente instalado en {equipo.serial} (Taller)",
                usuario_id=usuario_actual.id,
            )
        )
        costo_componentes_total += costo_ref * Decimal(cant)

    # Actualizar estado y costo interno del equipo (Costo Final = Primer Costo + Componentes + Comisión)
    comision_prep = (
        datos.comision_preparacion_usd
        if getattr(datos, "comision_preparacion_usd", None) is not None
        else pago_tecnico
    )
    equipo.comision_preparacion_usd = (equipo.comision_preparacion_usd or Decimal("0.00")) + comision_prep
    equipo.costo_taller_usd = (equipo.costo_taller_usd or Decimal("0.00")) + comision_prep + costo_componentes_total
    primer_base = (
        equipo.primer_costo_usd
        if (equipo.primer_costo_usd or Decimal("0.00")) > Decimal("0.00")
        else (equipo.costo_compra_usd or Decimal("0.00")) + (equipo.costo_flete_usd or Decimal("0.00"))
    )
    equipo.primer_costo_usd = primer_base
    equipo.costo_final_usd = (primer_base + equipo.costo_taller_usd).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    equipo.estado = datos.resultado.value
    if datos.nota.strip():
        equipo.nota = datos.nota.strip()

    bd.add(
        MovimientoInventario(
            tipo=TipoMovimientoInventario.TALLER.value,
            articulo_id=equipo.articulo_id,
            equipo_id=equipo.id,
            sucursal_id=equipo.ubicacion_id,
            cantidad=0,
            costo_unitario_usd=pago_tecnico + costo_componentes_total,
            documento_ref=f"PREP-{prep.id}",
            motivo=f"Preparación {datos.tipo.value} → {datos.resultado.value}",
            usuario_id=usuario_actual.id,
        )
    )

    repuestos_creados: list[int] = []
    if datos.resultado == ResultadoPreparacion.HOSPITAL:
        for rep in datos.repuestos_faltantes:
            nuevo_rep = RepuestoSolicitado(
                origen=OrigenRepuestoSolicitado.HOSPITAL.value,
                equipo_id=equipo.id,
                articulo_id=rep.articulo_id,
                descripcion_repuesto=rep.descripcion.strip(),
                cantidad=rep.cantidad,
                estado=EstadoRepuestoSolicitado.PENDIENTE.value,
                solicitado_por_id=usuario_actual.id,
            )
            bd.add(nuevo_rep)
            bd.flush()
            repuestos_creados.append(nuevo_rep.id)

    bd.commit()

    respuesta: dict[str, Any] = {
        "id": prep.id,
        "equipo_id": equipo.id,
        "serial": equipo.serial,
        "resultado": equipo.estado,
        "pago_tecnico_usd": redondear_usd(pago_tecnico),
        "componentes_descontados": len(articulos_info),
        "repuestos_solicitados_ids": repuestos_creados,
    }
    if puede_ver_costos(usuario_actual.rol):
        respuesta["costo_taller_usd"] = redondear_usd(equipo.costo_taller_usd)
    return respuesta


# ---------------- Conexión Hospital ↔ Repuestos por Comprar ----------------

@enrutador.get("/repuestos-solicitados")
def listar_repuestos_solicitados(
    estado: EstadoRepuestoSolicitado | None = Query(default=None),
    origen: OrigenRepuestoSolicitado | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = bd.query(RepuestoSolicitado).options(
        joinedload(RepuestoSolicitado.equipo),
        joinedload(RepuestoSolicitado.caso),
        joinedload(RepuestoSolicitado.articulo),
        joinedload(RepuestoSolicitado.solicitado_por),
    )
    if estado is not None:
        consulta = consulta.filter(RepuestoSolicitado.estado == estado.value)
    if origen is not None:
        consulta = consulta.filter(RepuestoSolicitado.origen == origen.value)

    filas = consulta.order_by(RepuestoSolicitado.id.desc()).all()
    return [
        {
            "id": r.id,
            "origen": r.origen,
            "equipo_id": r.equipo_id,
            "serial": r.equipo.serial if r.equipo else None,
            "caso_id": r.caso_id,
            "numero_caso": r.caso.numero_caso if r.caso else None,
            "articulo_id": r.articulo_id,
            "sku": r.articulo.sku if r.articulo else None,
            "descripcion_repuesto": r.descripcion_repuesto,
            "cantidad": r.cantidad,
            "estado": r.estado,
            "solicitado_por": r.solicitado_por.nombre if r.solicitado_por else None,
            "fecha_solicitud": r.fecha_solicitud.isoformat(),
            "fecha_recepcion": r.fecha_recepcion.isoformat() if r.fecha_recepcion else None,
            "notificado_tecnico": r.notificado_tecnico,
        }
        for r in filas
    ]


@enrutador.patch("/repuestos-solicitados/{repuesto_id}/estado")
def actualizar_estado_repuesto(
    repuesto_id: int,
    datos: RepuestoEstadoEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ACTUALIZAR_REPUESTOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    repuesto = (
        bd.query(RepuestoSolicitado)
        .filter(RepuestoSolicitado.id == repuesto_id)
        .first()
    )
    if repuesto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud de repuesto no encontrada.",
        )

    repuesto.estado = datos.estado
    if datos.estado == EstadoRepuestoSolicitado.RECIBIDO.value:
        repuesto.fecha_recepcion = datetime.now(timezone.utc)
        repuesto.notificado_tecnico = True

    bd.commit()
    return {
        "id": repuesto.id,
        "estado": repuesto.estado,
        "notificado_tecnico": repuesto.notificado_tecnico,
        "fecha_recepcion": repuesto.fecha_recepcion.isoformat() if repuesto.fecha_recepcion else None,
    }


# ---------------- Casos de Garantía (GT) y Servicio Técnico (ST) ----------------

def serializar_caso(caso: CasoPostventa, hoy_date) -> dict[str, Any]:
    fecha_fin = caso.fecha_cierre.date() if caso.fecha_cierre else hoy_date
    dias_abiertos = max(0, (fecha_fin - caso.fecha_ingreso.date()).days)

    ultimo_presupuesto = caso.presupuestos[0] if caso.presupuestos else None
    presupuesto_dict = None
    if ultimo_presupuesto is not None:
        try:
            repuestos_lista = json.loads(ultimo_presupuesto.repuestos_json)
        except json.JSONDecodeError:
            repuestos_lista = []
        presupuesto_dict = {
            "id": ultimo_presupuesto.id,
            "mano_obra_usd": redondear_usd(ultimo_presupuesto.mano_obra_usd),
            "repuestos": repuestos_lista,
            "total_promo_usd": redondear_usd(ultimo_presupuesto.total_promo_usd),
            "aprobado_cliente": ultimo_presupuesto.aprobado_cliente,
            "fecha_envio": ultimo_presupuesto.fecha_envio.isoformat(),
            "fecha_respuesta": (
                ultimo_presupuesto.fecha_respuesta.isoformat()
                if ultimo_presupuesto.fecha_respuesta
                else None
            ),
            "nota_cliente": ultimo_presupuesto.nota_cliente,
        }

    return {
        "id": caso.id,
        "numero_caso": caso.numero_caso,
        "tipo": caso.tipo,
        "sucursal_id": caso.sucursal_id,
        "sucursal": caso.sucursal.nombre if caso.sucursal else None,
        "cliente_id": caso.cliente_id,
        "cliente": caso.cliente.nombre if caso.cliente else "Cliente general",
        "equipo_id": caso.equipo_id,
        "serial_o_codigo": caso.serial_o_codigo,
        "descripcion_equipo": caso.descripcion_equipo,
        "tipo_marca_color": caso.tipo_marca_color,
        "accesorios_recibidos": caso.accesorios_recibidos,
        "estado_fisico": caso.estado_fisico,
        "clave_equipo": caso.clave_equipo,
        "falla_reportada": caso.falla_reportada,
        "tecnico_id": caso.tecnico_id,
        "tecnico": caso.tecnico.nombre if caso.tecnico else None,
        "diagnostico": caso.diagnostico,
        "trabajo_realizado": caso.trabajo_realizado,
        "estado": caso.estado,
        "alerta_garantia": caso.alerta_garantia,
        "dias_abiertos": dias_abiertos,
        "fecha_ingreso": caso.fecha_ingreso.isoformat(),
        "fecha_cierre": caso.fecha_cierre.isoformat() if caso.fecha_cierre else None,
        "presupuesto": presupuesto_dict,
    }


@enrutador.get("/casos")
def listar_casos(
    tipo: TipoCasoPostventa | None = Query(default=None),
    estado: EstadoCasoPostventa | None = Query(default=None),
    busqueda: str | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    hoy = obtener_fecha_hoy()
    consulta = bd.query(CasoPostventa).options(
        joinedload(CasoPostventa.sucursal),
        joinedload(CasoPostventa.cliente),
        joinedload(CasoPostventa.tecnico),
        joinedload(CasoPostventa.presupuestos),
    )
    if tipo is not None:
        consulta = consulta.filter(CasoPostventa.tipo == tipo.value)
    if estado is not None:
        consulta = consulta.filter(CasoPostventa.estado == estado.value)
    if busqueda and busqueda.strip():
        txt = busqueda.strip()
        consulta = consulta.filter(
            or_(
                CasoPostventa.numero_caso.ilike(f"%{txt}%"),
                CasoPostventa.serial_o_codigo.ilike(f"%{txt}%"),
                CasoPostventa.descripcion_equipo.ilike(f"%{txt}%"),
            )
        )

    casos = consulta.order_by(CasoPostventa.id.desc()).all()
    return [serializar_caso(c, hoy) for c in casos]


@enrutador.post("/casos", status_code=status.HTTP_201_CREATED)
def crear_caso(
    datos: CasoCrearEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    sucursal = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La sucursal seleccionada no existe.",
        )

    if datos.cliente_id is not None:
        cliente = bd.query(Tercero).filter(Tercero.id == datos.cliente_id).first()
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El cliente seleccionado no existe.",
            )

    serial_norm = ""
    equipo_encontrado: Equipo | None = None
    alerta_garantia: str | None = None
    hoy = obtener_fecha_hoy()

    if datos.serial_o_codigo.strip():
        serial_norm = normalizar_serial(datos.serial_o_codigo)
        equipo_encontrado = bd.query(Equipo).filter(Equipo.serial == serial_norm).first()

        if datos.tipo == TipoCasoPostventa.GARANTIA and equipo_encontrado is not None:
            mov_venta = (
                bd.query(MovimientoInventario)
                .filter(
                    MovimientoInventario.equipo_id == equipo_encontrado.id,
                    MovimientoInventario.tipo == TipoMovimientoInventario.VENTA.value,
                )
                .order_by(MovimientoInventario.fecha.desc())
                .first()
            )
            fecha_ref = (
                mov_venta.fecha.date()
                if mov_venta
                else (equipo_encontrado.fecha_recepcion or equipo_encontrado.creado_en.date())
            )
            dias_transcurridos = (hoy - fecha_ref).days
            if dias_transcurridos > 180:
                alerta_garantia = (
                    f"Garantía vencida: han transcurrido {dias_transcurridos} días "
                    "(límite de cobertura: 180 días)."
                )

    numero_caso = generar_numero_caso(bd, datos.tipo)
    nuevo = CasoPostventa(
        numero_caso=numero_caso,
        tipo=datos.tipo.value,
        sucursal_id=datos.sucursal_id,
        cliente_id=datos.cliente_id,
        equipo_id=equipo_encontrado.id if equipo_encontrado else None,
        serial_o_codigo=serial_norm,
        descripcion_equipo=datos.descripcion_equipo.strip(),
        tipo_marca_color=datos.tipo_marca_color.strip(),
        accesorios_recibidos=datos.accesorios_recibidos.strip(),
        estado_fisico=datos.estado_fisico.strip(),
        clave_equipo=datos.clave_equipo.strip(),
        falla_reportada=datos.falla_reportada.strip(),
        estado=EstadoCasoPostventa.RECIBIDO.value,
        alerta_garantia=alerta_garantia,
    )
    bd.add(nuevo)
    bd.commit()

    caso_completo = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.sucursal),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.tecnico),
            joinedload(CasoPostventa.presupuestos),
        )
        .filter(CasoPostventa.id == nuevo.id)
        .first()
    )
    return serializar_caso(caso_completo, hoy)


@enrutador.post("/casos/{caso_id}/presupuesto", status_code=status.HTTP_201_CREATED)
def crear_presupuesto_caso(
    caso_id: int,
    datos: PresupuestoCrearEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    caso = bd.query(CasoPostventa).filter(CasoPostventa.id == caso_id).first()
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado.")
    if caso.tipo != TipoCasoPostventa.SERVICIO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los presupuestos solo aplican para casos de Servicio Técnico (ST).",
        )

    repuestos_serializados = [
        {
            "articulo_id": r.articulo_id,
            "descripcion": r.descripcion.strip(),
            "cantidad": r.cantidad,
            "precio_promo_usd": redondear_usd(r.precio_promo_usd),
        }
        for r in datos.repuestos
    ]
    total_repuestos = sum(
        (r.precio_promo_usd * Decimal(r.cantidad) for r in datos.repuestos),
        Decimal("0.00"),
    )
    total_promo = datos.mano_obra_usd + total_repuestos

    presupuesto = CasoPresupuesto(
        caso_id=caso.id,
        mano_obra_usd=datos.mano_obra_usd,
        repuestos_json=json.dumps(repuestos_serializados, ensure_ascii=False),
        total_promo_usd=total_promo,
        aprobado_cliente=None,
    )
    bd.add(presupuesto)
    caso.estado = EstadoCasoPostventa.ESPERANDO_APROBACION.value
    bd.commit()
    bd.refresh(presupuesto)

    return {
        "id": presupuesto.id,
        "caso_id": caso.id,
        "numero_caso": caso.numero_caso,
        "estado_caso": caso.estado,
        "mano_obra_usd": redondear_usd(presupuesto.mano_obra_usd),
        "repuestos": repuestos_serializados,
        "total_promo_usd": redondear_usd(presupuesto.total_promo_usd),
    }


@enrutador.patch("/casos/{caso_id}/aprobar-presupuesto")
def aprobar_presupuesto_caso(
    caso_id: int,
    datos: PresupuestoAprobarEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    caso = (
        bd.query(CasoPostventa)
        .options(joinedload(CasoPostventa.presupuestos))
        .filter(CasoPostventa.id == caso_id)
        .first()
    )
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado.")
    if not caso.presupuestos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este caso aún no tiene un presupuesto enviado.",
        )

    presupuesto = caso.presupuestos[0]
    presupuesto.aprobado_cliente = datos.aprobado
    presupuesto.fecha_respuesta = datetime.now(timezone.utc)
    presupuesto.nota_cliente = datos.nota_cliente.strip()

    caso.estado = (
        EstadoCasoPostventa.AUTORIZADO.value
        if datos.aprobado
        else EstadoCasoPostventa.LISTO_PARA_ENTREGAR.value
    )
    bd.commit()

    return {
        "caso_id": caso.id,
        "numero_caso": caso.numero_caso,
        "aprobado_cliente": presupuesto.aprobado_cliente,
        "estado": caso.estado,
    }


@enrutador.patch("/casos/{caso_id}/actualizar")
def actualizar_caso(
    caso_id: int,
    datos: CasoActualizarEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    caso = (
        bd.query(CasoPostventa)
        .options(joinedload(CasoPostventa.presupuestos))
        .filter(CasoPostventa.id == caso_id)
        .first()
    )
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado.")

    # Regla estricta: ST no puede pasar a TERMINADO sin presupuesto aprobado
    presupuesto_aprobado = next(
        (p for p in caso.presupuestos if p.aprobado_cliente is True),
        None,
    )
    if (
        caso.tipo == TipoCasoPostventa.SERVICIO.value
        and datos.resultado_estado == EstadoCasoPostventa.TERMINADO
        and presupuesto_aprobado is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede marcar como TERMINADO un Servicio Técnico (ST) sin presupuesto aprobado por el cliente.",
        )

    if datos.tecnico_id is not None:
        caso.tecnico_id = datos.tecnico_id
    elif caso.tecnico_id is None:
        caso.tecnico_id = usuario_actual.id

    if datos.diagnostico.strip():
        caso.diagnostico = datos.diagnostico.strip()
    if datos.trabajo_realizado.strip():
        caso.trabajo_realizado = datos.trabajo_realizado.strip()

    # Si termina, descontar repuestos usados de Bodega (o los del presupuesto aprobado si no se pasaron)
    if datos.resultado_estado == EstadoCasoPostventa.TERMINADO:
        repuestos_a_descontar: list[tuple[int, int]] = [
            (r.articulo_id, r.cantidad) for r in datos.repuestos_usados
        ]
        if not repuestos_a_descontar and presupuesto_aprobado is not None:
            try:
                lista_pres = json.loads(presupuesto_aprobado.repuestos_json)
            except json.JSONDecodeError:
                lista_pres = []
            for item in lista_pres:
                if item.get("articulo_id"):
                    repuestos_a_descontar.append((int(item["articulo_id"]), int(item.get("cantidad", 1))))

        if repuestos_a_descontar:
            bodega = obtener_bodega(bd)
            for art_id, cant in repuestos_a_descontar:
                disponible = calcular_stock_componente(bd, art_id, bodega.id)
                if disponible < cant:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Stock insuficiente en Bodega para el repuesto ID {art_id} (disponible: {disponible}).",
                    )
                costo_ref = obtener_costo_referencia_articulo(bd, art_id)
                bd.add(
                    CasoRepuestoUsado(
                        caso_id=caso.id,
                        articulo_id=art_id,
                        cantidad=cant,
                        costo_unitario_snapshot_usd=costo_ref,
                    )
                )
                bd.add(
                    MovimientoInventario(
                        tipo=TipoMovimientoInventario.TALLER.value,
                        articulo_id=art_id,
                        equipo_id=None,
                        sucursal_id=bodega.id,
                        cantidad=-cant,
                        costo_unitario_usd=costo_ref,
                        documento_ref=caso.numero_caso,
                        motivo=f"Repuesto usado en caso {caso.numero_caso}",
                        usuario_id=usuario_actual.id,
                    )
                )
        caso.fecha_cierre = datetime.now(timezone.utc)

    for rep in datos.repuestos_faltantes:
        bd.add(
            RepuestoSolicitado(
                origen=OrigenRepuestoSolicitado.CASO_TECNICO.value,
                caso_id=caso.id,
                equipo_id=caso.equipo_id,
                articulo_id=rep.articulo_id,
                descripcion_repuesto=rep.descripcion.strip(),
                cantidad=rep.cantidad,
                estado=EstadoRepuestoSolicitado.PENDIENTE.value,
                solicitado_por_id=usuario_actual.id,
            )
        )

    caso.estado = datos.resultado_estado.value
    bd.commit()

    hoy = obtener_fecha_hoy()
    caso_actualizado = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.sucursal),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.tecnico),
            joinedload(CasoPostventa.presupuestos),
        )
        .filter(CasoPostventa.id == caso.id)
        .first()
    )
    return serializar_caso(caso_actualizado, hoy)


# ---------------- Resumen Mensual del Técnico (sin costos) ----------------

@enrutador.get("/resumen-tecnico")
def obtener_resumen_tecnico(
    mes: int | None = Query(default=None, ge=1, le=12),
    anio: int | None = Query(default=None, ge=2020, le=2100),
    tecnico_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    mes_obj = mes or hoy.month
    anio_obj = anio or hoy.year

    # Si es técnico, solo puede consultar su propio resumen
    if usuario_actual.rol == RolUsuario.TECNICO.value:
        id_objetivo = usuario_actual.id
    else:
        id_objetivo = tecnico_id or usuario_actual.id

    tecnico = bd.query(Usuario).filter(Usuario.id == id_objetivo).first()
    if tecnico is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado.")

    preparaciones = (
        bd.query(Preparacion)
        .options(joinedload(Preparacion.equipo))
        .filter(
            Preparacion.tecnico_id == id_objetivo,
            extract("month", Preparacion.fecha) == mes_obj,
            extract("year", Preparacion.fecha) == anio_obj,
        )
        .order_by(Preparacion.fecha.desc(), Preparacion.id.desc())
        .all()
    )
    pago_preparaciones = sum((p.pago_tecnico_usd for p in preparaciones), Decimal("0.00"))

    estados_comisionables = {
        EstadoCasoPostventa.TERMINADO.value,
        EstadoCasoPostventa.LISTO_PARA_ENTREGAR.value,
        EstadoCasoPostventa.ENTREGADO.value,
    }
    casos_st = (
        bd.query(CasoPostventa)
        .options(joinedload(CasoPostventa.presupuestos))
        .filter(
            CasoPostventa.tecnico_id == id_objetivo,
            CasoPostventa.tipo == TipoCasoPostventa.SERVICIO.value,
            CasoPostventa.estado.in_(estados_comisionables),
            extract("month", CasoPostventa.fecha_ingreso) == mes_obj,
            extract("year", CasoPostventa.fecha_ingreso) == anio_obj,
        )
        .all()
    )

    comision_servicios = Decimal("0.00")
    detalle_servicios: list[dict[str, Any]] = []
    for c in casos_st:
        pres_aprobado = next((p for p in c.presupuestos if p.aprobado_cliente is True), None)
        if pres_aprobado is None:
            continue
        comision = (pres_aprobado.mano_obra_usd * Decimal("0.50")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        comision_servicios += comision
        detalle_servicios.append(
            {
                "numero_caso": c.numero_caso,
                "descripcion_equipo": c.descripcion_equipo,
                "mano_obra_usd": redondear_usd(pres_aprobado.mano_obra_usd),
                "comision_50_usd": redondear_usd(comision),
                "estado": c.estado,
            }
        )

    # Servicios técnicos cobrados desde el POS (50% sobre Precio Promo USD de líneas de servicio)
    ventas_servicios_pos = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles).joinedload(VentaDetalle.articulo))
        .filter(
            Venta.estado != EstadoVenta.ANULADA.value,
            Venta.tecnico_id == id_objetivo,
            extract("month", Venta.fecha) == mes_obj,
            extract("year", Venta.fecha) == anio_obj,
        )
        .order_by(Venta.fecha.desc(), Venta.id.desc())
        .all()
    )
    for v in ventas_servicios_pos:
        for det in v.detalles:
            if det.articulo is not None and det.articulo.tipo == TipoArticulo.SERVICIO.value:
                subtotal_promo = det.precio_promo_usd * Decimal(det.cantidad)
                comision = (subtotal_promo * Decimal("0.50")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                comision_servicios += comision
                detalle_servicios.append(
                    {
                        "numero_caso": v.numero_venta,
                        "descripcion_equipo": (det.descripcion_servicio or det.descripcion),
                        "mano_obra_usd": redondear_usd(subtotal_promo),
                        "comision_50_usd": redondear_usd(comision),
                        "estado": v.estado,
                    }
                )

    # Ventas donde el técnico figura como asesor (1% sobre Precio Promo USD de productos/equipos/componentes)
    ventas_como_asesor = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles).joinedload(VentaDetalle.articulo))
        .filter(
            Venta.estado != EstadoVenta.ANULADA.value,
            Venta.asesor_id == id_objetivo,
            extract("month", Venta.fecha) == mes_obj,
            extract("year", Venta.fecha) == anio_obj,
        )
        .all()
    )
    base_ventas_asesor = Decimal("0.00")
    for v in ventas_como_asesor:
        for det in v.detalles:
            es_servicio = det.articulo is not None and det.articulo.tipo == TipoArticulo.SERVICIO.value
            if not es_servicio:
                base_ventas_asesor += det.precio_promo_usd * Decimal(det.cantidad)

    comision_asesor = (base_ventas_asesor * Decimal("0.01")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_mes = pago_preparaciones + comision_servicios + comision_asesor

    return {
        "tecnico_id": tecnico.id,
        "tecnico_nombre": tecnico.nombre,
        "mes": mes_obj,
        "anio": anio_obj,
        "cantidad_preparaciones": len(preparaciones),
        "pago_preparaciones_usd": redondear_usd(pago_preparaciones),
        "cantidad_servicios": len(detalle_servicios),
        "comision_servicios_usd": redondear_usd(comision_servicios),
        "comision_asesor_usd": redondear_usd(comision_asesor),
        "total_mes_usd": redondear_usd(total_mes),
        "detalle_preparaciones": [
            {
                "id": p.id,
                "fecha": p.fecha.isoformat(),
                "serial": p.equipo.serial if p.equipo else None,
                "tipo": p.tipo,
                "resultado": p.resultado,
                "pago_tecnico_usd": redondear_usd(p.pago_tecnico_usd),
            }
            for p in preparaciones
        ],
        "detalle_servicios": detalle_servicios,
    }


# ---------------- Recepción de Garantías y Servicio Técnico (Líder/Encargado -> Técnico) ----------------

ROLES_RECEPCION_TALLER: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LIDER.value,
    RolUsuario.ENCARGADO.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.TECNICO.value,
)


def _serializar_recepcion(c: CasoPostventa) -> dict[str, Any]:
    tipo_salida = "SERVICIO_TECNICO" if c.tipo in (TipoCasoPostventa.SERVICIO.value, "SERVICIO_TECNICO") else "GARANTIA"
    cliente_nom = c.cliente.nombre if c.cliente else (c.cliente_nombre_manual or "Cliente general")
    cliente_tel = (c.cliente.telefono if c.cliente else "") or c.cliente_telefono_manual or ""
    return {
        "id": c.id,
        "numero_caso": c.numero_caso,
        "tipo": tipo_salida,
        "sucursal_id": c.sucursal_id,
        "sucursal": c.sucursal.nombre if c.sucursal else "",
        "numero_nota_entrega": c.numero_nota_entrega,
        "venta_id": c.venta_id,
        "cliente_id": c.cliente_id,
        "cliente_nombre": cliente_nom,
        "cliente_telefono": cliente_tel,
        "serial_o_codigo": c.serial_o_codigo,
        "descripcion_equipo": c.descripcion_equipo,
        "tipo_marca_color": c.tipo_marca_color,
        "accesorios_recibidos": c.accesorios_recibidos,
        "estado_fisico": c.estado_fisico,
        "clave_equipo": c.clave_equipo,
        "ingresa_apagado": bool(c.ingresa_apagado),
        "falla_reportada": c.falla_reportada,
        "estado": c.estado,
        "tecnico_id": c.tecnico_id,
        "tecnico": c.tecnico.nombre if c.tecnico else "Cola general de Taller",
        "recibido_por": c.recibido_por.nombre if c.recibido_por else "",
        "fecha_ingreso": c.fecha_ingreso.isoformat() if c.fecha_ingreso else None,
    }


@enrutador.get("/recepciones")
def listar_recepciones_taller(
    tipo: str | None = Query(default=None),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_RECEPCION_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    q = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.sucursal),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.tecnico),
            joinedload(CasoPostventa.recibido_por),
        )
        .order_by(CasoPostventa.id.desc())
    )
    if tipo and tipo.strip():
        t_norm = tipo.strip().upper()
        if t_norm == "SERVICIO_TECNICO":
            q = q.filter(CasoPostventa.tipo.in_([TipoCasoPostventa.SERVICIO.value, "SERVICIO_TECNICO"]))
        else:
            q = q.filter(CasoPostventa.tipo == t_norm)
    return [_serializar_recepcion(c) for c in q.limit(150).all()]


@enrutador.post("/recepciones", status_code=status.HTTP_201_CREATED)
def crear_recepcion_taller(
    datos: RecepcionTallerCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_RECEPCION_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    from app.modelos_finanzas import Venta
    from app.servicios.auditoria_service import registrar_auditoria

    suc = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_id).first()
    if suc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada.")

    venta_id: int | None = None
    cliente_id = datos.cliente_id
    nota_norm = datos.numero_nota_entrega.strip().upper()

    if datos.tipo == "GARANTIA":
        if not nota_norm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para recepciones por GARANTIA es obligatorio indicar el Nro. de Nota de Entrega (ej. N-0001).",
            )
        venta = (
            bd.query(Venta)
            .filter(func.upper(Venta.numero_venta) == nota_norm)
            .first()
        )
        if venta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La Nota de Entrega '{nota_norm}' no existe en el registro de ventas.",
            )
        venta_id = venta.id
        if cliente_id is None:
            cliente_id = venta.cliente_id

    tipo_enum = TipoCasoPostventa.GARANTIA if datos.tipo == "GARANTIA" else TipoCasoPostventa.SERVICIO
    numero_caso = generar_numero_caso(bd, tipo_enum)

    serial_norm = datos.serial_o_codigo.strip().upper()
    eq_encontrado = (
        bd.query(Equipo).filter(Equipo.serial == serial_norm).first()
        if serial_norm
        else None
    )

    caso = CasoPostventa(
        numero_caso=numero_caso,
        tipo=tipo_enum.value,
        sucursal_id=datos.sucursal_id,
        cliente_id=cliente_id,
        equipo_id=eq_encontrado.id if eq_encontrado else None,
        serial_o_codigo=serial_norm,
        descripcion_equipo=datos.descripcion_equipo.strip(),
        tipo_marca_color=datos.tipo_marca_color.strip(),
        accesorios_recibidos=datos.accesorios_recibidos.strip(),
        estado_fisico=datos.estado_fisico.strip(),
        clave_equipo=datos.clave_equipo.strip(),
        falla_reportada=datos.falla_reportada.strip(),
        tecnico_id=datos.tecnico_id,
        estado=EstadoCasoPostventa.RECIBIDO.value,
        numero_nota_entrega=nota_norm,
        venta_id=venta_id,
        ingresa_apagado=bool(datos.ingresa_apagado) if datos.tipo == "SERVICIO_TECNICO" else False,
        recibido_por_id=usuario_actual.id,
        cliente_nombre_manual=datos.cliente_nombre.strip(),
        cliente_telefono_manual=datos.cliente_telefono.strip(),
    )
    bd.add(caso)
    bd.flush()
    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="TALLER",
        accion="RECEPCION_EQUIPO",
        entidad_id=caso.numero_caso,
        detalle_anterior={},
        detalle_nuevo={
            "tipo": datos.tipo,
            "numero_nota_entrega": nota_norm,
            "ingresa_apagado": caso.ingresa_apagado,
            "serial": serial_norm,
        },
    )
    bd.commit()

    caso_full = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.sucursal),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.tecnico),
            joinedload(CasoPostventa.recibido_por),
        )
        .filter(CasoPostventa.id == caso.id)
        .first()
    )
    return _serializar_recepcion(caso_full)


@enrutador.get("/recepciones/{caso_id}/pdf")
def descargar_pdf_recepcion_taller(
    caso_id: int,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_RECEPCION_TALLER)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    import io
    from zoneinfo import ZoneInfo
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from app.utils.pdf_branding import dibujar_marca_de_agua

    caso = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.sucursal),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.tecnico),
            joinedload(CasoPostventa.recibido_por),
        )
        .filter(CasoPostventa.id == caso_id)
        .first()
    )
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recepción no encontrada.")

    es_servicio = caso.tipo in (TipoCasoPostventa.SERVICIO.value, "SERVICIO_TECNICO")
    titulo_doc = "COMPROBANTE DE RECEPCIÓN · SERVICIO TÉCNICO" if es_servicio else "COMPROBANTE DE RECEPCIÓN · GARANTÍA"
    cliente_nom = caso.cliente.nombre if caso.cliente else (caso.cliente_nombre_manual or "Cliente general")
    cliente_tel = (caso.cliente.telefono if caso.cliente else "") or caso.cliente_telefono_manual or "N/D"
    recibido_por = caso.recibido_por.nombre if caso.recibido_por else "Equipo Tekio"
    tecnico_nom = caso.tecnico.nombre if caso.tecnico else "Cola de Taller Técnico"

    fecha_caracas = (
        caso.fecha_ingreso.astimezone(ZoneInfo("America/Caracas")).strftime("%d/%m/%Y %I:%M %p")
        if caso.fecha_ingreso and caso.fecha_ingreso.tzinfo
        else obtener_fecha_hoy().strftime("%d/%m/%Y")
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    base = getSampleStyleSheet()
    st_sub = ParagraphStyle("RecSub", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=4)
    st_tit = ParagraphStyle("RecTit", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=14, textColor=colors.HexColor("#191818"), spaceAfter=8)
    st_clausula = ParagraphStyle("RecCla", parent=base["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#191818"), spaceAfter=6)

    elementos: list[Any] = [
        Paragraph("TEKIO ELECTRONICS 2024, C.A. · RIF J-50637518-4", st_sub),
        Paragraph(f"{titulo_doc} ({caso.numero_caso})", st_tit),
        Paragraph(
            f"Fecha y hora (America/Caracas): {fecha_caracas} · Sucursal: {caso.sucursal.nombre if caso.sucursal else 'Tekio'}",
            st_sub,
        ),
        Spacer(1, 0.2 * cm),
    ]

    filas_datos = [
        ["Campo", "Detalle"],
        ["Cliente", f"{cliente_nom} (Tel: {cliente_tel})"],
        ["Tipo de Ingreso", "SERVICIO TÉCNICO" if es_servicio else f"GARANTÍA (Nota: {caso.numero_nota_entrega or 'N/D'})"],
        ["Equipo / Modelo", f"{caso.descripcion_equipo} {f'({caso.tipo_marca_color})' if caso.tipo_marca_color else ''}"],
        ["Serial / Código", caso.serial_o_codigo or "Sin serial"],
        ["Condición al Ingreso", "INGRESA APAGADO (sin verificación de encendido)" if caso.ingresa_apagado else "Ingresa encendido / operativo"],
        ["Estado Físico", caso.estado_fisico or "Sin observaciones físicas registradas"],
        ["Accesorios Recibidos", caso.accesorios_recibidos or "Ninguno"],
        ["Falla Reportada", caso.falla_reportada],
        ["Recibido Por / Técnico", f"Recibió: {recibido_por} · Asignado a: {tecnico_nom}"],
    ]
    tabla = Table(filas_datos, colWidths=[4.8 * cm, 13.0 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#191818")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F6F6F6")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDDDDD")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.4 * cm))

    if es_servicio:
        elementos.append(
            Paragraph(
                "<b>CONDICIONES Y CLÁUSULAS DE SERVICIO TÉCNICO:</b>",
                ParagraphStyle("RecHdr", parent=base["Normal"], fontSize=9.5, textColor=colors.HexColor("#E85A28"), spaceAfter=4),
            )
        )
        elementos.append(
            Paragraph(
                "1. El diagnóstico y revisión técnica tiene un costo de <b>$10 USD</b>, los cuales serán "
                "<b>100% exonerados</b> en caso de que el cliente apruebe la reparación.",
                st_clausula,
            )
        )
        elementos.append(
            Paragraph(
                "2. Si el equipo ingresa <b>apagado</b> o sin posibilidad de verificación previa de encendido, "
                "Tekio Electronics <b>no se hace responsable</b> por fallas ocultas, pantalla, teclado, batería "
                "o componentes internos que no pudieron ser probados al momento de la recepción.",
                st_clausula,
            )
        )
        elementos.append(Spacer(1, 0.5 * cm))

    firmas = Table(
        [
            ["_______________________________", "_______________________________"],
            [f"Firma del Cliente: {cliente_nom}", f"Recibido por: {recibido_por}"],
        ],
        colWidths=[8.9 * cm, 8.9 * cm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elementos.append(firmas)
    doc.build(elementos, onFirstPage=dibujar_marca_de_agua, onLaterPages=dibujar_marca_de_agua)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recepcion_{caso.numero_caso}.pdf"'},
    )

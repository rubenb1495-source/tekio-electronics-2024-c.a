from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_logistica import normalizar_serial
from app.esquemas_taller import (
    CasoActualizarEntrada,
    CasoCrearEntrada,
    PreparacionCrearEntrada,
    PresupuestoAprobarEntrada,
    PresupuestoCrearEntrada,
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

    # Actualizar estado y costo interno del equipo
    equipo.costo_taller_usd = (equipo.costo_taller_usd or Decimal("0.00")) + pago_tecnico + costo_componentes_total
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

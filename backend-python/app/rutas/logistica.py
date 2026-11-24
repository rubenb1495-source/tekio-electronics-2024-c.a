from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from openpyxl import load_workbook
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import normalizar_sku
from app.esquemas_logistica import (
    AjusteCrearEntrada,
    AjusteRevisarEntrada,
    CompraCrearEntrada,
    FilaValidacionArchivo,
    GuiaCrearEntrada,
    GuiaRecibirEntrada,
    TerceroCrearEntrada,
    TerceroSalida,
    TrasladoAnularEntrada,
    TrasladoConfirmarEntrada,
    TrasladoCrearEntrada,
    ValidacionArchivoSalida,
    normalizar_serial,
)
from app.modelos import CatalogoArticulo, EstadoSucursal, RolUsuario, Sucursal, Usuario
from app.modelos_logistica import (
    AjusteInventario,
    Compra,
    CompraComponente,
    Equipo,
    EstadoAjusteInventario,
    EstadoCompra,
    EstadoEquipo,
    EstadoGuia,
    EstadoTraslado,
    GuiaImportacion,
    MovimientoInventario,
    OrigenCompra,
    Tercero,
    TipoAjusteInventario,
    TipoMovimientoInventario,
    Traslado,
    TrasladoDetalle,
)
from app.rutas.tasas import obtener_fecha_hoy
from app.seguridad import obtener_usuario_actual, puede_ver_costos, requerir_roles


enrutador = APIRouter(prefix="/api/logistica", tags=["Logística e Inventario"])

ROLES_LOGISTICA: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.LIDER.value,
)

ROLES_SOLICITAR_AJUSTE: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.LIDER.value,
    RolUsuario.TECNICO.value,
)


def redondear_usd(valor: Decimal) -> float:
    return float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generar_correlativo(bd: Session, modelo: type, columna: Any, prefijo: str) -> str:
    hoy_str = obtener_fecha_hoy().strftime("%Y%m%d")
    base = f"{prefijo}-{hoy_str}-"
    cantidad = bd.query(func.count(modelo.id)).filter(columna.like(f"{base}%")).scalar() or 0
    secuencia = int(cantidad) + 1
    while True:
        candidato = f"{base}{secuencia:04d}"
        existe = bd.query(modelo.id).filter(columna == candidato).first()
        if not existe:
            return candidato
        secuencia += 1


def obtener_bodega(bd: Session) -> Sucursal:
    bodega = bd.query(Sucursal).filter(Sucursal.nombre == "Bodega").first()
    if bodega is None:
        bodega = bd.query(Sucursal).filter(Sucursal.estado == EstadoSucursal.ACTIVA.value).first()
    if bodega is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existe una sucursal Bodega activa en el sistema.",
        )
    return bodega


def calcular_stock_componente(bd: Session, articulo_id: int, sucursal_id: int) -> int:
    total = (
        bd.query(func.coalesce(func.sum(MovimientoInventario.cantidad), 0))
        .filter(
            MovimientoInventario.articulo_id == articulo_id,
            MovimientoInventario.sucursal_id == sucursal_id,
            MovimientoInventario.equipo_id.is_(None),
        )
        .scalar()
    )
    return int(total or 0)


def serializar_equipo(equipo: Equipo, incluir_costos: bool) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": equipo.id,
        "serial": equipo.serial,
        "articulo_id": equipo.articulo_id,
        "sku": equipo.articulo.sku if equipo.articulo else None,
        "compra_id": equipo.compra_id,
        "numero_compra": equipo.compra.numero_compra if equipo.compra else None,
        "guia_id": equipo.guia_id,
        "numero_guia": equipo.guia.numero_guia if equipo.guia else None,
        "modelo": equipo.modelo,
        "configuracion": equipo.configuracion,
        "categoria": equipo.categoria,
        "ubicacion_id": equipo.ubicacion_id,
        "ubicacion": equipo.ubicacion.nombre if equipo.ubicacion else None,
        "estado": equipo.estado,
        "precio_promo_usd": redondear_usd(equipo.precio_promo_usd),
        "recibido_por": equipo.recibido_por.nombre if equipo.recibido_por else None,
        "verificado_por": equipo.verificado_por.nombre if equipo.verificado_por else None,
        "fecha_recepcion": equipo.fecha_recepcion.isoformat() if equipo.fecha_recepcion else None,
        "nota": equipo.nota,
    }
    if incluir_costos:
        costo_total = equipo.costo_compra_usd + equipo.costo_flete_usd + equipo.costo_taller_usd
        datos["costo_compra_usd"] = redondear_usd(equipo.costo_compra_usd)
        datos["costo_flete_usd"] = redondear_usd(equipo.costo_flete_usd)
        datos["costo_taller_usd"] = redondear_usd(equipo.costo_taller_usd)
        datos["costo_total_usd"] = redondear_usd(costo_total)
    return datos


# ---------------- Terceros y Verificadores ----------------

@enrutador.get("/terceros", response_model=list[TerceroSalida])
def listar_terceros(
    tipo: str | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[TerceroSalida]:
    consulta = bd.query(Tercero).filter(Tercero.activo.is_(True))
    if tipo:
        consulta = consulta.filter(Tercero.tipo == tipo)
    filas = consulta.order_by(Tercero.nombre.asc()).all()
    return [TerceroSalida.model_validate(f) for f in filas]


@enrutador.post("/terceros", response_model=TerceroSalida, status_code=status.HTTP_201_CREATED)
def crear_tercero(
    datos: TerceroCrearEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> TerceroSalida:
    nuevo = Tercero(
        nombre=datos.nombre.strip(),
        tipo=datos.tipo.value,
        rif_cedula=datos.rif_cedula.strip().upper(),
        telefono=datos.telefono.strip(),
        activo=True,
    )
    bd.add(nuevo)
    bd.commit()
    bd.refresh(nuevo)
    return TerceroSalida.model_validate(nuevo)


@enrutador.get("/verificadores")
def listar_verificadores(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    usuarios = (
        bd.query(Usuario)
        .filter(Usuario.activo.is_(True), Usuario.id != usuario_actual.id)
        .order_by(Usuario.nombre.asc())
        .all()
    )
    return [{"id": u.id, "nombre": u.nombre, "rol": u.rol} for u in usuarios]


# ---------------- Compras y Validación Excel/CSV ----------------

@enrutador.get("/compras")
def listar_compras(
    origen: OrigenCompra | None = Query(default=None),
    estado: EstadoCompra | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    incluir_costos = puede_ver_costos(usuario_actual.rol)
    consulta = bd.query(Compra).options(
        joinedload(Compra.proveedor),
        joinedload(Compra.creado_por),
        joinedload(Compra.equipos),
        joinedload(Compra.componentes),
    )
    if origen is not None:
        consulta = consulta.filter(Compra.origen == origen.value)
    if estado is not None:
        consulta = consulta.filter(Compra.estado == estado.value)

    total = consulta.count()
    filas = (
        consulta.order_by(Compra.fecha.desc(), Compra.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    elementos = []
    for c in filas:
        item: dict[str, Any] = {
            "id": c.id,
            "numero_compra": c.numero_compra,
            "origen": c.origen,
            "proveedor_id": c.proveedor_id,
            "proveedor": c.proveedor.nombre if c.proveedor else "Sin proveedor",
            "fecha": c.fecha.isoformat(),
            "factura_orden": c.factura_orden,
            "llega_preparada": c.llega_preparada,
            "estado": c.estado,
            "nota": c.nota,
            "creado_por": c.creado_por.nombre if c.creado_por else None,
            "total_equipos": len(c.equipos),
            "total_componentes": sum(comp.cantidad for comp in c.componentes),
        }
        if incluir_costos:
            item["monto_mercancia_usd"] = redondear_usd(c.monto_mercancia_usd)
            item["envio_usd"] = redondear_usd(c.envio_usd)
            item["otros_gastos_usd"] = redondear_usd(c.otros_gastos_usd)
        elementos.append(item)

    return {
        "elementos": elementos,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


@enrutador.post("/compras", status_code=status.HTTP_201_CREATED)
def crear_compra(
    datos: CompraCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    if datos.proveedor_id is not None:
        prov = bd.query(Tercero).filter(Tercero.id == datos.proveedor_id).first()
        if prov is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El proveedor seleccionado no existe.",
            )

    # Validar seriales duplicados en el mismo envío y en la base de datos
    vistos: set[str] = set()
    for eq in datos.equipos:
        if eq.serial in vistos:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El serial '{eq.serial}' está repetido dentro de la misma compra.",
            )
        vistos.add(eq.serial)
        existe = bd.query(Equipo.id).filter(Equipo.serial == eq.serial).first()
        if existe is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El serial '{eq.serial}' ya existe en el inventario. No se permiten duplicados.",
            )

        if datos.origen == OrigenCompra.INVENTARIO_EXISTENTE:
            if eq.costo_compra_usd is None or eq.ubicacion_id is None or eq.estado is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Para INVENTARIO_EXISTENTE, el serial '{eq.serial}' requiere "
                        "costo_compra_usd, ubicacion_id y estado obligatorios."
                    ),
                )

    for comp in datos.componentes:
        art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == comp.articulo_id).first()
        if art is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El artículo ID {comp.articulo_id} no existe en el catálogo.",
            )
        if datos.origen == OrigenCompra.INVENTARIO_EXISTENTE:
            if comp.costo_unitario_usd is None or comp.ubicacion_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Para INVENTARIO_EXISTENTE, el componente '{art.sku}' requiere "
                        "costo_unitario_usd y ubicacion_id obligatorios."
                    ),
                )

    bodega = obtener_bodega(bd)
    es_inmediata = datos.origen != OrigenCompra.IMPORTACION
    estado_compra = EstadoCompra.RECIBIDA.value if es_inmediata else EstadoCompra.PENDIENTE.value

    numero_compra = generar_correlativo(bd, Compra, Compra.numero_compra, "CMP")
    compra = Compra(
        numero_compra=numero_compra,
        origen=datos.origen.value,
        proveedor_id=datos.proveedor_id,
        fecha=datos.fecha,
        factura_orden=datos.factura_orden.strip(),
        monto_mercancia_usd=datos.monto_mercancia_usd,
        envio_usd=datos.envio_usd,
        otros_gastos_usd=datos.otros_gastos_usd,
        llega_preparada=datos.llega_preparada,
        estado=estado_compra,
        nota=datos.nota.strip(),
        creado_por_id=usuario_actual.id,
    )
    bd.add(compra)
    bd.flush()

    equipos_creados: list[Equipo] = []
    for eq in datos.equipos:
        ubicacion_id = eq.ubicacion_id or bodega.id
        if datos.origen == OrigenCompra.IMPORTACION:
            estado_eq = EstadoEquipo.EN_TRANSITO.value
        elif datos.origen == OrigenCompra.INVENTARIO_EXISTENTE and eq.estado is not None:
            estado_eq = eq.estado.value
        else:
            estado_eq = (
                EstadoEquipo.LISTO.value if datos.llega_preparada else EstadoEquipo.POR_PREPARAR.value
            )

        nuevo_eq = Equipo(
            serial=eq.serial,
            articulo_id=eq.articulo_id,
            compra_id=compra.id,
            modelo=eq.modelo.strip(),
            configuracion=eq.configuracion.strip(),
            categoria=eq.categoria.strip() or "Laptop",
            ubicacion_id=ubicacion_id,
            estado=estado_eq,
            costo_compra_usd=eq.costo_compra_usd or Decimal("0"),
            costo_flete_usd=Decimal("0"),
            costo_taller_usd=Decimal("0"),
            precio_promo_usd=eq.precio_promo_usd,
            recibido_por_id=usuario_actual.id if es_inmediata else None,
            fecha_recepcion=datos.fecha if es_inmediata else None,
            nota=eq.nota.strip(),
        )
        bd.add(nuevo_eq)
        bd.flush()
        equipos_creados.append(nuevo_eq)

        if es_inmediata:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.COMPRA.value,
                    articulo_id=nuevo_eq.articulo_id,
                    equipo_id=nuevo_eq.id,
                    sucursal_id=ubicacion_id,
                    cantidad=1,
                    costo_unitario_usd=nuevo_eq.costo_compra_usd,
                    documento_ref=numero_compra,
                    motivo=f"Ingreso por {datos.origen.value}",
                    usuario_id=usuario_actual.id,
                )
            )

    for comp in datos.componentes:
        ubicacion_id = comp.ubicacion_id or bodega.id
        costo_unit = comp.costo_unitario_usd or Decimal("0")
        bd.add(
            CompraComponente(
                compra_id=compra.id,
                articulo_id=comp.articulo_id,
                cantidad=comp.cantidad,
                cantidad_recibida=comp.cantidad if es_inmediata else 0,
                costo_unitario_usd=costo_unit,
            )
        )
        if es_inmediata:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.COMPRA.value,
                    articulo_id=comp.articulo_id,
                    equipo_id=None,
                    sucursal_id=ubicacion_id,
                    cantidad=comp.cantidad,
                    costo_unitario_usd=costo_unit,
                    documento_ref=numero_compra,
                    motivo=f"Ingreso de componentes ({datos.origen.value})",
                    usuario_id=usuario_actual.id,
                )
            )

    bd.commit()
    return {
        "id": compra.id,
        "numero_compra": compra.numero_compra,
        "origen": compra.origen,
        "estado": compra.estado,
        "total_equipos": len(equipos_creados),
        "total_componentes": sum(c.cantidad for c in datos.componentes),
    }


def _leer_filas_archivo(nombre: str, contenido: bytes) -> list[dict[str, str]]:
    extension = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if extension == "csv":
        texto = contenido.decode("utf-8-sig", errors="replace")
        muestra = texto[:2048]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
        filas: list[dict[str, str]] = []
        for fila in lector:
            normalizada = {
                (k or "").strip().lower(): (str(v).strip() if v is not None else "")
                for k, v in fila.items()
            }
            if any(normalizada.values()):
                filas.append(normalizada)
        return filas

    if extension in ("xlsx", "xlsm"):
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        hoja = libro.active
        iter_filas = hoja.iter_rows(values_only=True)
        encabezados_raw = next(iter_filas, None)
        if not encabezados_raw:
            return []
        encabezados = [str(c).strip().lower() if c is not None else "" for c in encabezados_raw]
        filas = []
        for valores in iter_filas:
            fila_dict: dict[str, str] = {}
            for idx, col in enumerate(encabezados):
                if not col:
                    continue
                val = valores[idx] if idx < len(valores) else None
                fila_dict[col] = str(val).strip() if val is not None else ""
            if any(fila_dict.values()):
                filas.append(fila_dict)
        return filas

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato no soportado. Sube un archivo .xlsx o .csv.",
    )


@enrutador.post("/compras/validar-archivo", response_model=ValidacionArchivoSalida)
async def validar_archivo_compras(
    archivo: UploadFile = File(...),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> ValidacionArchivoSalida:
    nombre = archivo.filename or "carga.csv"
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío.",
        )

    filas_raw = _leer_filas_archivo(nombre, contenido)
    seriales_en_bd = {s[0] for s in bd.query(Equipo.serial).all()}
    skus_en_bd = {s[0] for s in bd.query(CatalogoArticulo.sku).all()}
    seriales_archivo: set[str] = set()

    resultados: list[FilaValidacionArchivo] = []
    validas = 0

    for indice, fila in enumerate(filas_raw, start=2):
        errores: list[str] = []
        raw_serial = fila.get("serial") or fila.get("nro_serial") or ""
        raw_sku = fila.get("sku") or fila.get("codigo") or ""
        modelo = fila.get("modelo") or fila.get("descripcion") or ""
        configuracion = fila.get("configuracion") or ""
        categoria = fila.get("categoria") or "Laptop"
        ubicacion = fila.get("ubicacion") or fila.get("sucursal") or None
        estado_fila = fila.get("estado") or None

        serial_norm: str | None = None
        if raw_serial:
            serial_norm = normalizar_serial(raw_serial)
            if serial_norm in seriales_en_bd:
                errores.append(f"Serial '{serial_norm}' ya existe en inventario.")
            elif serial_norm in seriales_archivo:
                errores.append(f"Serial '{serial_norm}' repetido en el archivo.")
            seriales_archivo.add(serial_norm)

        sku_norm: str | None = None
        if raw_sku:
            try:
                sku_norm = normalizar_sku(raw_sku)
                if sku_norm not in skus_en_bd:
                    errores.append(f"SKU '{sku_norm}' no existe en el catálogo maestro.")
            except ValueError:
                errores.append("SKU inválido.")

        if not serial_norm and not sku_norm:
            errores.append("La fila debe indicar un serial o un SKU.")

        raw_costo = fila.get("costo_compra_usd") or fila.get("costo") or fila.get("costo_usd") or ""
        costo_val: float | None = None
        if not raw_costo:
            errores.append("Falta costo_compra_usd.")
        else:
            try:
                costo_val = float(raw_costo.replace(",", "."))
                if costo_val < 0:
                    errores.append("El costo no puede ser negativo.")
            except ValueError:
                errores.append(f"Costo inválido: '{raw_costo}'.")

        raw_promo = fila.get("precio_promo_usd") or fila.get("precio_promo") or "0"
        try:
            promo_val = float(raw_promo.replace(",", ".")) if raw_promo else 0.0
        except ValueError:
            promo_val = 0.0
            errores.append(f"Precio promo inválido: '{raw_promo}'.")

        raw_cant = fila.get("cantidad") or "1"
        try:
            cantidad_val = int(float(raw_cant))
            if cantidad_val <= 0:
                errores.append("La cantidad debe ser mayor a 0.")
        except ValueError:
            cantidad_val = 1
            errores.append(f"Cantidad inválida: '{raw_cant}'.")

        es_valida = len(errores) == 0
        if es_valida:
            validas += 1

        resultados.append(
            FilaValidacionArchivo(
                fila=indice,
                serial=serial_norm,
                sku=sku_norm,
                modelo=modelo,
                configuracion=configuracion,
                categoria=categoria,
                cantidad=cantidad_val,
                costo_compra_usd=costo_val,
                precio_promo_usd=promo_val,
                ubicacion=ubicacion,
                estado=estado_fila,
                valida=es_valida,
                errores=errores,
            )
        )

    con_error = len(resultados) - validas
    return ValidacionArchivoSalida(
        nombre_archivo=nombre,
        total_filas=len(resultados),
        filas_validas=validas,
        filas_con_error=con_error,
        puede_confirmar=len(resultados) > 0 and con_error == 0,
        filas=resultados,
    )


# ---------------- Guías y Recepción con Prorrateo ----------------

@enrutador.get("/guias")
def listar_guias(
    estado: EstadoGuia | None = Query(default=None),
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    incluir_costos = puede_ver_costos(usuario_actual.rol)
    consulta = bd.query(GuiaImportacion).options(
        joinedload(GuiaImportacion.compras).joinedload(Compra.equipos)
    )
    if estado is not None:
        consulta = consulta.filter(GuiaImportacion.estado == estado.value)
    guias = consulta.order_by(GuiaImportacion.id.desc()).all()

    salida = []
    for g in guias:
        equipos_guia = [
            e
            for c in g.compras
            for e in c.equipos
            if e.guia_id is None or e.guia_id == g.id
        ]
        item: dict[str, Any] = {
            "id": g.id,
            "numero_guia": g.numero_guia,
            "casillero": g.casillero,
            "modalidad": g.modalidad,
            "fecha_salida": g.fecha_salida.isoformat() if g.fecha_salida else None,
            "fecha_llegada_estimada": g.fecha_llegada_estimada.isoformat() if g.fecha_llegada_estimada else None,
            "fecha_llegada_real": g.fecha_llegada_real.isoformat() if g.fecha_llegada_real else None,
            "estado": g.estado,
            "nota": g.nota,
            "compras": [{"id": c.id, "numero_compra": c.numero_compra} for c in g.compras],
            "seriales_esperados": [e.serial for e in equipos_guia],
        }
        if incluir_costos:
            item["flete_usd"] = redondear_usd(g.flete_usd)
            item["otros_gastos_usd"] = redondear_usd(g.otros_gastos_usd)
            item["costo_total_guia_usd"] = redondear_usd(g.flete_usd + g.otros_gastos_usd)
        salida.append(item)
    return salida


@enrutador.post("/guias", status_code=status.HTTP_201_CREATED)
def crear_guia(
    datos: GuiaCrearEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    existente = (
        bd.query(GuiaImportacion)
        .filter(GuiaImportacion.numero_guia == datos.numero_guia)
        .first()
    )
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La guía '{datos.numero_guia}' ya existe.",
        )

    compras = (
        bd.query(Compra)
        .options(joinedload(Compra.equipos))
        .filter(Compra.id.in_(datos.compras_ids))
        .all()
    )
    if len(compras) != len(set(datos.compras_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Una o más compras indicadas no existen.",
        )

    guia = GuiaImportacion(
        numero_guia=datos.numero_guia,
        casillero=datos.casillero.strip(),
        modalidad=datos.modalidad.value,
        fecha_salida=datos.fecha_salida,
        fecha_llegada_estimada=datos.fecha_llegada_estimada,
        flete_usd=datos.flete_usd,
        otros_gastos_usd=datos.otros_gastos_usd,
        estado=EstadoGuia.EN_TRANSITO.value,
        nota=datos.nota.strip(),
    )
    guia.compras = compras
    bd.add(guia)
    bd.flush()

    for compra in compras:
        for eq in compra.equipos:
            if eq.guia_id is None:
                eq.guia_id = guia.id

    bd.commit()
    return {
        "id": guia.id,
        "numero_guia": guia.numero_guia,
        "estado": guia.estado,
        "flete_usd": redondear_usd(guia.flete_usd),
        "otros_gastos_usd": redondear_usd(guia.otros_gastos_usd),
        "compras_asociadas": len(compras),
    }


@enrutador.post("/guias/{guia_id}/recibir")
def recibir_guia(
    guia_id: int,
    datos: GuiaRecibirEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    # Regla estricta: Doble verificación obligatoria
    if datos.verificado_por_id == usuario_actual.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doble control obligatorio: el usuario que recibe y el verificador deben ser personas distintas.",
        )

    verificador = (
        bd.query(Usuario)
        .filter(Usuario.id == datos.verificado_por_id, Usuario.activo.is_(True))
        .first()
    )
    if verificador is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario verificador seleccionado no existe o está inactivo.",
        )

    guia = (
        bd.query(GuiaImportacion)
        .options(
            joinedload(GuiaImportacion.compras).joinedload(Compra.equipos),
            joinedload(GuiaImportacion.compras).joinedload(Compra.componentes),
        )
        .filter(GuiaImportacion.id == guia_id)
        .first()
    )
    if guia is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guía no encontrada.")
    if guia.estado == EstadoGuia.RECIBIDA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta guía ya fue recibida anteriormente.",
        )

    bodega = obtener_bodega(bd)
    mapa_compras = {c.id: c for c in guia.compras}
    equipos_candidatos = [
        e for c in guia.compras for e in c.equipos if e.estado == EstadoEquipo.EN_TRANSITO.value
    ]

    if datos.seriales_recibidos:
        conjunto_seriales = set(datos.seriales_recibidos)
        equipos_recibidos = [e for e in equipos_candidatos if e.serial in conjunto_seriales]
        faltantes = conjunto_seriales - {e.serial for e in equipos_recibidos}
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Seriales no encontrados en tránsito para esta guía: {', '.join(sorted(faltantes))}.",
            )
    else:
        equipos_recibidos = equipos_candidatos

    # Componentes a recibir
    componentes_recibidos_pares: list[tuple[CompraComponente, int]] = []
    if datos.componentes_recibidos:
        comp_por_articulo = {
            cc.articulo_id: cc for c in guia.compras for cc in c.componentes
        }
        for item_comp in datos.componentes_recibidos:
            cc = comp_por_articulo.get(item_comp.articulo_id)
            if cc is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El artículo ID {item_comp.articulo_id} no pertenece a las compras de esta guía.",
                )
            componentes_recibidos_pares.append((cc, item_comp.cantidad))

    # Prorrateo de flete por valor: costo_total_guia * (costo_item / suma_costos_guia)
    costo_total_guia = guia.flete_usd + guia.otros_gastos_usd
    suma_costos_equipos = sum((e.costo_compra_usd for e in equipos_recibidos), Decimal("0"))
    suma_costos_componentes = sum(
        (cc.costo_unitario_usd * Decimal(cant) for cc, cant in componentes_recibidos_pares),
        Decimal("0"),
    )
    suma_costos_guia = suma_costos_equipos + suma_costos_componentes

    detalle_prorrateo: list[dict[str, Any]] = []

    for eq in equipos_recibidos:
        if suma_costos_guia > 0:
            flete_asignado = (costo_total_guia * eq.costo_compra_usd / suma_costos_guia).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            flete_asignado = Decimal("0.00")

        compra_eq = mapa_compras.get(eq.compra_id) if eq.compra_id else None
        nuevo_estado = (
            EstadoEquipo.LISTO.value
            if (compra_eq and compra_eq.llega_preparada)
            else EstadoEquipo.POR_PREPARAR.value
        )

        eq.guia_id = guia.id
        eq.ubicacion_id = bodega.id
        eq.costo_flete_usd = flete_asignado
        eq.estado = nuevo_estado
        eq.recibido_por_id = usuario_actual.id
        eq.verificado_por_id = verificador.id
        eq.fecha_recepcion = datos.fecha_llegada_real

        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.COMPRA.value,
                articulo_id=eq.articulo_id,
                equipo_id=eq.id,
                sucursal_id=bodega.id,
                cantidad=1,
                costo_unitario_usd=eq.costo_compra_usd + flete_asignado,
                documento_ref=guia.numero_guia,
                motivo=f"Recepción de guía {guia.numero_guia} (verificado por {verificador.nombre})",
                usuario_id=usuario_actual.id,
            )
        )
        detalle_prorrateo.append(
            {
                "serial": eq.serial,
                "estado": eq.estado,
                "costo_compra_usd": redondear_usd(eq.costo_compra_usd),
                "costo_flete_usd": redondear_usd(flete_asignado),
            }
        )

    for cc, cant in componentes_recibidos_pares:
        valor_linea = cc.costo_unitario_usd * Decimal(cant)
        if suma_costos_guia > 0:
            flete_linea = (costo_total_guia * valor_linea / suma_costos_guia).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            flete_unitario = (flete_linea / Decimal(cant)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            flete_unitario = Decimal("0.00")

        cc.cantidad_recibida += cant
        cc.costo_flete_unitario_usd = flete_unitario
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.COMPRA.value,
                articulo_id=cc.articulo_id,
                equipo_id=None,
                sucursal_id=bodega.id,
                cantidad=cant,
                costo_unitario_usd=cc.costo_unitario_usd + flete_unitario,
                documento_ref=guia.numero_guia,
                motivo=f"Recepción de componentes guía {guia.numero_guia}",
                usuario_id=usuario_actual.id,
            )
        )

    guia.fecha_llegada_real = datos.fecha_llegada_real
    guia.estado = EstadoGuia.RECIBIDA.value

    for compra in guia.compras:
        pendientes_eq = any(e.estado == EstadoEquipo.EN_TRANSITO.value for e in compra.equipos)
        pendientes_comp = any(cc.cantidad_recibida < cc.cantidad for cc in compra.componentes)
        compra.estado = (
            EstadoCompra.RECIBIDA_PARCIAL.value
            if (pendientes_eq or pendientes_comp)
            else EstadoCompra.RECIBIDA.value
        )

    bd.commit()
    return {
        "guia_id": guia.id,
        "numero_guia": guia.numero_guia,
        "estado": guia.estado,
        "equipos_recibidos": len(equipos_recibidos),
        "componentes_recibidos": sum(cant for _, cant in componentes_recibidos_pares),
        "verificado_por": verificador.nombre,
        "prorrateo": detalle_prorrateo,
    }


# ---------------- Traslados en 2 Pasos ----------------

@enrutador.get("/traslados")
def listar_traslados(
    estado: EstadoTraslado | None = Query(default=None),
    destino_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = bd.query(Traslado).options(
        joinedload(Traslado.origen),
        joinedload(Traslado.destino),
        joinedload(Traslado.enviado_por),
        joinedload(Traslado.recibido_por),
        joinedload(Traslado.detalles).joinedload(TrasladoDetalle.equipo),
        joinedload(Traslado.detalles).joinedload(TrasladoDetalle.articulo),
    )
    if estado is not None:
        consulta = consulta.filter(Traslado.estado == estado.value)
    if destino_id is not None:
        consulta = consulta.filter(Traslado.destino_id == destino_id)

    filas = consulta.order_by(Traslado.id.desc()).all()
    return [
        {
            "id": t.id,
            "numero_traslado": t.numero_traslado,
            "origen_id": t.origen_id,
            "origen": t.origen.nombre if t.origen else None,
            "destino_id": t.destino_id,
            "destino": t.destino.nombre if t.destino else None,
            "estado": t.estado,
            "enviado_por": t.enviado_por.nombre if t.enviado_por else None,
            "recibido_por": t.recibido_por.nombre if t.recibido_por else None,
            "fecha_envio": t.fecha_envio.isoformat(),
            "fecha_recepcion": t.fecha_recepcion.isoformat() if t.fecha_recepcion else None,
            "nota": t.nota,
            "nota_recepcion": t.nota_recepcion,
            "motivo_anulacion": t.motivo_anulacion,
            "detalles": [
                {
                    "id": d.id,
                    "equipo_id": d.equipo_id,
                    "serial": d.equipo.serial if d.equipo else None,
                    "modelo": d.equipo.modelo if d.equipo else None,
                    "articulo_id": d.articulo_id,
                    "sku": d.articulo.sku if d.articulo else None,
                    "cantidad": d.cantidad,
                }
                for d in t.detalles
            ],
        }
        for t in filas
    ]


@enrutador.post("/traslados", status_code=status.HTTP_201_CREATED)
def crear_traslado(
    datos: TrasladoCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    if datos.origen_id == datos.destino_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La sucursal de origen y destino deben ser distintas.",
        )
    if not datos.equipos_ids and not datos.componentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes incluir al menos un equipo o componente en el traslado.",
        )

    origen = bd.query(Sucursal).filter(Sucursal.id == datos.origen_id).first()
    destino = bd.query(Sucursal).filter(Sucursal.id == datos.destino_id).first()
    if origen is None or destino is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sucursal de origen o destino no encontrada.",
        )
    if destino.estado != EstadoSucursal.ACTIVA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pueden enviar traslados a la sucursal cerrada '{destino.nombre}'.",
        )

    equipos = (
        bd.query(Equipo).filter(Equipo.id.in_(datos.equipos_ids)).all()
        if datos.equipos_ids
        else []
    )
    if len(equipos) != len(set(datos.equipos_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uno o más equipos seleccionados no existen.",
        )

    estados_bloqueados = {
        EstadoEquipo.EN_TRANSITO.value,
        EstadoEquipo.VENDIDO.value,
        EstadoEquipo.CEMENTERIO.value,
    }
    for eq in equipos:
        if eq.ubicacion_id != datos.origen_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El equipo '{eq.serial}' no se encuentra en la sucursal de origen.",
            )
        if eq.estado in estados_bloqueados:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El equipo '{eq.serial}' está en estado '{eq.estado}' y no puede trasladarse.",
            )

    for comp in datos.componentes:
        disponible = calcular_stock_componente(bd, comp.articulo_id, datos.origen_id)
        if disponible < comp.cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente en '{origen.nombre}' para el artículo ID {comp.articulo_id} (disponible: {disponible}).",
            )

    numero_traslado = generar_correlativo(bd, Traslado, Traslado.numero_traslado, "TRS")
    traslado = Traslado(
        numero_traslado=numero_traslado,
        origen_id=datos.origen_id,
        destino_id=datos.destino_id,
        estado=EstadoTraslado.EN_TRANSITO.value,
        enviado_por_id=usuario_actual.id,
        nota=datos.nota.strip(),
    )
    bd.add(traslado)
    bd.flush()

    for eq in equipos:
        eq.estado_previo_traslado = eq.estado
        eq.estado = EstadoEquipo.EN_TRANSITO.value
        bd.add(TrasladoDetalle(traslado_id=traslado.id, equipo_id=eq.id, cantidad=1))
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.TRASLADO_SALIDA.value,
                articulo_id=eq.articulo_id,
                equipo_id=eq.id,
                sucursal_id=datos.origen_id,
                cantidad=-1,
                costo_unitario_usd=eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd,
                documento_ref=numero_traslado,
                motivo=f"Salida en tránsito hacia {destino.nombre}",
                usuario_id=usuario_actual.id,
            )
        )

    for comp in datos.componentes:
        bd.add(
            TrasladoDetalle(
                traslado_id=traslado.id,
                articulo_id=comp.articulo_id,
                cantidad=comp.cantidad,
            )
        )
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.TRASLADO_SALIDA.value,
                articulo_id=comp.articulo_id,
                equipo_id=None,
                sucursal_id=datos.origen_id,
                cantidad=-comp.cantidad,
                costo_unitario_usd=Decimal("0"),
                documento_ref=numero_traslado,
                motivo=f"Salida de componentes hacia {destino.nombre}",
                usuario_id=usuario_actual.id,
            )
        )

    bd.commit()
    return {
        "id": traslado.id,
        "numero_traslado": traslado.numero_traslado,
        "estado": traslado.estado,
        "equipos_en_transito": len(equipos),
        "componentes_en_transito": sum(c.cantidad for c in datos.componentes),
    }


@enrutador.post("/traslados/{traslado_id}/confirmar")
def confirmar_traslado(
    traslado_id: int,
    datos: TrasladoConfirmarEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    traslado = (
        bd.query(Traslado)
        .options(
            joinedload(Traslado.destino),
            joinedload(Traslado.detalles).joinedload(TrasladoDetalle.equipo),
        )
        .filter(Traslado.id == traslado_id)
        .first()
    )
    if traslado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado.")
    if traslado.estado != EstadoTraslado.EN_TRANSITO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden confirmar traslados EN_TRANSITO (estado actual: {traslado.estado}).",
        )

    ahora = datetime.now(timezone.utc)
    traslado.estado = EstadoTraslado.RECIBIDO.value
    traslado.recibido_por_id = usuario_actual.id
    traslado.fecha_recepcion = ahora
    traslado.nota_recepcion = datos.nota_recepcion.strip()

    for det in traslado.detalles:
        if det.equipo is not None:
            eq = det.equipo
            eq.ubicacion_id = traslado.destino_id
            eq.estado = eq.estado_previo_traslado or EstadoEquipo.LISTO.value
            eq.estado_previo_traslado = None
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TRASLADO_ENTRADA.value,
                    articulo_id=eq.articulo_id,
                    equipo_id=eq.id,
                    sucursal_id=traslado.destino_id,
                    cantidad=1,
                    costo_unitario_usd=eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd,
                    documento_ref=traslado.numero_traslado,
                    motivo=f"Recepción confirmada en {traslado.destino.nombre}",
                    usuario_id=usuario_actual.id,
                )
            )
        elif det.articulo_id is not None:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TRASLADO_ENTRADA.value,
                    articulo_id=det.articulo_id,
                    equipo_id=None,
                    sucursal_id=traslado.destino_id,
                    cantidad=det.cantidad,
                    costo_unitario_usd=Decimal("0"),
                    documento_ref=traslado.numero_traslado,
                    motivo=f"Recepción de componentes en {traslado.destino.nombre}",
                    usuario_id=usuario_actual.id,
                )
            )

    bd.commit()
    return {
        "id": traslado.id,
        "numero_traslado": traslado.numero_traslado,
        "estado": traslado.estado,
        "recibido_por": usuario_actual.nombre,
    }


@enrutador.post("/traslados/{traslado_id}/anular")
def anular_traslado(
    traslado_id: int,
    datos: TrasladoAnularEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    traslado = (
        bd.query(Traslado)
        .options(
            joinedload(Traslado.origen),
            joinedload(Traslado.detalles).joinedload(TrasladoDetalle.equipo),
        )
        .filter(Traslado.id == traslado_id)
        .first()
    )
    if traslado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado.")
    if traslado.estado != EstadoTraslado.EN_TRANSITO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden anular traslados EN_TRANSITO (estado actual: {traslado.estado}).",
        )

    traslado.estado = EstadoTraslado.ANULADO.value
    traslado.motivo_anulacion = datos.motivo.strip()

    for det in traslado.detalles:
        if det.equipo is not None:
            eq = det.equipo
            eq.ubicacion_id = traslado.origen_id
            eq.estado = eq.estado_previo_traslado or EstadoEquipo.POR_PREPARAR.value
            eq.estado_previo_traslado = None
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TRASLADO_ENTRADA.value,
                    articulo_id=eq.articulo_id,
                    equipo_id=eq.id,
                    sucursal_id=traslado.origen_id,
                    cantidad=1,
                    costo_unitario_usd=eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd,
                    documento_ref=traslado.numero_traslado,
                    motivo=f"Reverso por anulación: {datos.motivo.strip()}",
                    usuario_id=usuario_actual.id,
                )
            )
        elif det.articulo_id is not None:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TRASLADO_ENTRADA.value,
                    articulo_id=det.articulo_id,
                    equipo_id=None,
                    sucursal_id=traslado.origen_id,
                    cantidad=det.cantidad,
                    costo_unitario_usd=Decimal("0"),
                    documento_ref=traslado.numero_traslado,
                    motivo=f"Reverso componentes por anulación: {datos.motivo.strip()}",
                    usuario_id=usuario_actual.id,
                )
            )

    bd.commit()
    return {
        "id": traslado.id,
        "numero_traslado": traslado.numero_traslado,
        "estado": traslado.estado,
        "motivo_anulacion": traslado.motivo_anulacion,
    }


# ---------------- Inventario, Kardex, Trazabilidad y Ajustes ----------------

@enrutador.get("/inventario/equipos")
def listar_inventario_equipos(
    sucursal_id: int | None = Query(default=None),
    estado: EstadoEquipo | None = Query(default=None),
    busqueda: str | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    incluir_costos = puede_ver_costos(usuario_actual.rol)
    consulta = bd.query(Equipo).options(
        joinedload(Equipo.articulo),
        joinedload(Equipo.compra),
        joinedload(Equipo.guia),
        joinedload(Equipo.ubicacion),
        joinedload(Equipo.recibido_por),
        joinedload(Equipo.verificado_por),
    )
    if sucursal_id is not None:
        consulta = consulta.filter(Equipo.ubicacion_id == sucursal_id)
    if estado is not None:
        consulta = consulta.filter(Equipo.estado == estado.value)
    if busqueda and busqueda.strip():
        texto = busqueda.strip()
        consulta = consulta.filter(
            or_(
                Equipo.serial.ilike(f"%{texto.upper()}%"),
                Equipo.modelo.ilike(f"%{texto}%"),
                Equipo.configuracion.ilike(f"%{texto}%"),
            )
        )

    equipos = consulta.order_by(Equipo.id.desc()).all()
    return [serializar_equipo(e, incluir_costos) for e in equipos]


@enrutador.get("/inventario/kardex")
def consultar_kardex_componentes(
    sucursal_id: int | None = Query(default=None),
    articulo_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    incluir_costos = puede_ver_costos(usuario_actual.rol)

    consulta_saldos = (
        bd.query(
            MovimientoInventario.articulo_id,
            MovimientoInventario.sucursal_id,
            func.coalesce(func.sum(MovimientoInventario.cantidad), 0).label("stock"),
        )
        .filter(
            MovimientoInventario.equipo_id.is_(None),
            MovimientoInventario.articulo_id.isnot(None),
        )
        .group_by(MovimientoInventario.articulo_id, MovimientoInventario.sucursal_id)
    )
    if sucursal_id is not None:
        consulta_saldos = consulta_saldos.filter(MovimientoInventario.sucursal_id == sucursal_id)
    if articulo_id is not None:
        consulta_saldos = consulta_saldos.filter(MovimientoInventario.articulo_id == articulo_id)

    articulos_map = {a.id: a for a in bd.query(CatalogoArticulo).all()}
    sucursales_map = {s.id: s for s in bd.query(Sucursal).all()}

    saldos = []
    for art_id, suc_id, stock in consulta_saldos.all():
        art = articulos_map.get(art_id)
        suc = sucursales_map.get(suc_id)
        saldos.append(
            {
                "articulo_id": art_id,
                "sku": art.sku if art else "",
                "descripcion": art.descripcion if art else "",
                "sucursal_id": suc_id,
                "sucursal": suc.nombre if suc else "",
                "stock_actual": int(stock),
            }
        )

    consulta_movs = (
        bd.query(MovimientoInventario)
        .options(
            joinedload(MovimientoInventario.articulo),
            joinedload(MovimientoInventario.sucursal),
            joinedload(MovimientoInventario.usuario),
        )
        .filter(MovimientoInventario.equipo_id.is_(None))
    )
    if sucursal_id is not None:
        consulta_movs = consulta_movs.filter(MovimientoInventario.sucursal_id == sucursal_id)
    if articulo_id is not None:
        consulta_movs = consulta_movs.filter(MovimientoInventario.articulo_id == articulo_id)

    movimientos = []
    for m in consulta_movs.order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.id.desc()).limit(100).all():
        item: dict[str, Any] = {
            "id": m.id,
            "fecha": m.fecha.isoformat(),
            "tipo": m.tipo,
            "sku": m.articulo.sku if m.articulo else None,
            "sucursal": m.sucursal.nombre if m.sucursal else None,
            "cantidad": m.cantidad,
            "documento_ref": m.documento_ref,
            "motivo": m.motivo,
            "usuario": m.usuario.nombre if m.usuario else None,
        }
        if incluir_costos:
            item["costo_unitario_usd"] = redondear_usd(m.costo_unitario_usd)
        movimientos.append(item)

    return {"saldos": saldos, "movimientos": movimientos}


@enrutador.get("/trazabilidad/{serial}")
def obtener_trazabilidad_serial(
    serial: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    serial_norm = normalizar_serial(serial)
    incluir_costos = puede_ver_costos(usuario_actual.rol)

    equipo = (
        bd.query(Equipo)
        .options(
            joinedload(Equipo.articulo),
            joinedload(Equipo.compra),
            joinedload(Equipo.guia),
            joinedload(Equipo.ubicacion),
            joinedload(Equipo.recibido_por),
            joinedload(Equipo.verificado_por),
        )
        .filter(Equipo.serial == serial_norm)
        .first()
    )
    if equipo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún equipo registrado con el serial '{serial_norm}'.",
        )

    movimientos = (
        bd.query(MovimientoInventario)
        .options(
            joinedload(MovimientoInventario.sucursal),
            joinedload(MovimientoInventario.usuario),
        )
        .filter(MovimientoInventario.equipo_id == equipo.id)
        .order_by(MovimientoInventario.fecha.asc(), MovimientoInventario.id.asc())
        .all()
    )

    linea_tiempo = []
    for m in movimientos:
        evento: dict[str, Any] = {
            "fecha": m.fecha.isoformat(),
            "tipo": m.tipo,
            "sucursal": m.sucursal.nombre if m.sucursal else None,
            "documento_ref": m.documento_ref,
            "motivo": m.motivo,
            "usuario": m.usuario.nombre if m.usuario else None,
        }
        if incluir_costos:
            evento["costo_unitario_usd"] = redondear_usd(m.costo_unitario_usd)
        linea_tiempo.append(evento)

    return {
        "equipo": serializar_equipo(equipo, incluir_costos),
        "linea_tiempo": linea_tiempo,
    }


@enrutador.get("/ajustes")
def listar_ajustes(
    estado: EstadoAjusteInventario | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = bd.query(AjusteInventario).options(
        joinedload(AjusteInventario.sucursal),
        joinedload(AjusteInventario.equipo),
        joinedload(AjusteInventario.articulo),
        joinedload(AjusteInventario.solicitado_por),
        joinedload(AjusteInventario.revisado_por),
    )
    if estado is not None:
        consulta = consulta.filter(AjusteInventario.estado == estado.value)

    filas = consulta.order_by(AjusteInventario.id.desc()).all()
    return [
        {
            "id": a.id,
            "numero_ajuste": a.numero_ajuste,
            "sucursal_id": a.sucursal_id,
            "sucursal": a.sucursal.nombre if a.sucursal else None,
            "tipo": a.tipo,
            "equipo_id": a.equipo_id,
            "serial": a.equipo.serial if a.equipo else None,
            "articulo_id": a.articulo_id,
            "sku": a.articulo.sku if a.articulo else None,
            "cantidad": a.cantidad,
            "motivo": a.motivo,
            "estado": a.estado,
            "solicitado_por": a.solicitado_por.nombre if a.solicitado_por else None,
            "revisado_por": a.revisado_por.nombre if a.revisado_por else None,
            "fecha_revision": a.fecha_revision.isoformat() if a.fecha_revision else None,
            "comentario_revision": a.comentario_revision,
            "creado_en": a.creado_en.isoformat(),
        }
        for a in filas
    ]


@enrutador.post("/ajustes", status_code=status.HTTP_201_CREATED)
def crear_ajuste_inventario(
    datos: AjusteCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_SOLICITAR_AJUSTE)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    if datos.tipo == TipoAjusteInventario.BAJA_EQUIPO and datos.equipo_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para BAJA_EQUIPO debes indicar el equipo_id.",
        )
    if datos.tipo != TipoAjusteInventario.BAJA_EQUIPO and datos.articulo_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para correcciones de stock debes indicar el articulo_id.",
        )

    numero_ajuste = generar_correlativo(bd, AjusteInventario, AjusteInventario.numero_ajuste, "AJU")
    ajuste = AjusteInventario(
        numero_ajuste=numero_ajuste,
        sucursal_id=datos.sucursal_id,
        tipo=datos.tipo.value,
        equipo_id=datos.equipo_id,
        articulo_id=datos.articulo_id,
        cantidad=datos.cantidad,
        motivo=datos.motivo.strip(),
        estado=EstadoAjusteInventario.PENDIENTE.value,
        solicitado_por_id=usuario_actual.id,
    )
    bd.add(ajuste)
    bd.commit()
    bd.refresh(ajuste)
    return {
        "id": ajuste.id,
        "numero_ajuste": ajuste.numero_ajuste,
        "estado": ajuste.estado,
    }


@enrutador.patch("/ajustes/{ajuste_id}/revisar")
def revisar_ajuste_inventario(
    ajuste_id: int,
    datos: AjusteRevisarEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(RolUsuario.DIRECCION.value)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    ajuste = (
        bd.query(AjusteInventario)
        .options(joinedload(AjusteInventario.equipo))
        .filter(AjusteInventario.id == ajuste_id)
        .first()
    )
    if ajuste is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ajuste no encontrado.")
    if ajuste.estado != EstadoAjusteInventario.PENDIENTE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Este ajuste ya fue procesado (estado actual: {ajuste.estado}).",
        )

    ajuste.estado = datos.decision
    ajuste.revisado_por_id = usuario_actual.id
    ajuste.fecha_revision = datetime.now(timezone.utc)
    ajuste.comentario_revision = datos.comentario.strip()

    if datos.decision == EstadoAjusteInventario.APROBADO.value:
        if ajuste.tipo == TipoAjusteInventario.BAJA_EQUIPO.value and ajuste.equipo is not None:
            ajuste.equipo.estado = EstadoEquipo.CEMENTERIO.value
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.BAJA.value,
                    articulo_id=ajuste.equipo.articulo_id,
                    equipo_id=ajuste.equipo.id,
                    sucursal_id=ajuste.sucursal_id,
                    cantidad=-1,
                    costo_unitario_usd=ajuste.equipo.costo_compra_usd,
                    documento_ref=ajuste.numero_ajuste,
                    motivo=f"Baja aprobada por Dirección: {ajuste.motivo}",
                    usuario_id=usuario_actual.id,
                )
            )
        elif ajuste.articulo_id is not None:
            es_positivo = ajuste.tipo == TipoAjusteInventario.CORRECCION_MAS.value
            delta = ajuste.cantidad if es_positivo else -ajuste.cantidad
            tipo_mov = (
                TipoMovimientoInventario.AJUSTE_POSITIVO.value
                if es_positivo
                else TipoMovimientoInventario.AJUSTE_NEGATIVO.value
            )
            bd.add(
                MovimientoInventario(
                    tipo=tipo_mov,
                    articulo_id=ajuste.articulo_id,
                    equipo_id=None,
                    sucursal_id=ajuste.sucursal_id,
                    cantidad=delta,
                    costo_unitario_usd=Decimal("0"),
                    documento_ref=ajuste.numero_ajuste,
                    motivo=f"Ajuste aprobado por Dirección: {ajuste.motivo}",
                    usuario_id=usuario_actual.id,
                )
            )

    bd.commit()
    return {
        "id": ajuste.id,
        "numero_ajuste": ajuste.numero_ajuste,
        "estado": ajuste.estado,
        "revisado_por": usuario_actual.nombre,
    }

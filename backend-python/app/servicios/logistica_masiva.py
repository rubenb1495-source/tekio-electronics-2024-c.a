from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modelos import CatalogoArticulo, EstadoSucursal, Sucursal, Usuario
from app.modelos_logistica import (
    Compra,
    Equipo,
    EstadoCompra,
    EstadoEquipo,
    EstadoTraslado,
    MovimientoInventario,
    OrigenCompra,
    Tercero,
    TipoMovimientoInventario,
    TipoTercero,
    Traslado,
    TrasladoDetalle,
)
from app.rutas.tasas import obtener_fecha_hoy


FLUJOS_PLANTILLAS: dict[str, dict[str, Any]] = {
    "compras_nacionales": {
        "titulo": "Compras Nacionales",
        "columnas": [
            "serial",
            "sku",
            "modelo",
            "configuracion",
            "categoria",
            "sucursal",
            "costo_compra_usd",
            "precio_promo_usd",
            "proveedor",
            "factura_orden",
            "llega_preparada",
            "nota",
        ],
        "ejemplo": [
            "SN-NAC-0001",
            "LAP-HP-840",
            "HP EliteBook 840 G7",
            "Core i5 10ma / 16GB RAM / 256GB SSD",
            "Laptop",
            "Bodega",
            "240.00",
            "380.00",
            "Proveedor Nacional CA",
            "FAC-001",
            "NO",
            "Ingreso nacional",
        ],
    },
    "compras_internacionales": {
        "titulo": "Compras Internacionales",
        "columnas": [
            "serial",
            "sku",
            "modelo",
            "configuracion",
            "categoria",
            "sucursal",
            "costo_compra_usd",
            "precio_promo_usd",
            "proveedor",
            "numero_guia",
            "flete_total_usd",
            "aduana_total_usd",
            "moneda",
            "llega_preparada",
            "nota",
        ],
        "ejemplo": [
            "SN-INT-0001",
            "LAP-DELL-5420",
            "Dell Latitude 5420",
            "Core i5 11va / 16GB RAM / 512GB SSD",
            "Laptop",
            "Bodega",
            "260.00",
            "450.00",
            "Miami Tech Wholesale",
            "GUIA-MIA-2026-01",
            "60.00",
            "40.00",
            "USD",
            "NO",
            "Importación aérea",
        ],
    },
    "consignacion": {
        "titulo": "Mercancía en Consignación",
        "columnas": [
            "serial",
            "sku",
            "modelo",
            "configuracion",
            "categoria",
            "sucursal",
            "precio_promo_usd",
            "proveedor_consignacion",
            "factura_orden",
            "llega_preparada",
            "nota",
        ],
        "ejemplo": [
            "SN-CON-0001",
            "LAP-LEN-T14",
            "Lenovo ThinkPad T14",
            "Core i7 / 16GB RAM / 512GB SSD",
            "Laptop",
            "Tekio central",
            "520.00",
            "Aliado Consignacion",
            "CON-001",
            "SI",
            "Equipo en consignación",
        ],
    },
    "traslados_universales": {
        "titulo": "Traslados Universales",
        "columnas": [
            "tipo_item",
            "serial",
            "sku",
            "cantidad",
            "sucursal_origen",
            "sucursal_destino",
            "nota",
        ],
        "ejemplo": [
            "EQUIPO",
            "SN-NAC-0001",
            "",
            "1",
            "Bodega",
            "Tekio central",
            "Despacho diario",
        ],
    },
    "cambio_estado": {
        "titulo": "Cambio de Estado",
        "columnas": [
            "serial",
            "nuevo_estado",
            "motivo",
        ],
        "ejemplo": [
            "SN-NAC-0001",
            "LISTO",
            "Equipo preparado y verificado en taller",
        ],
    },
}

ESTADOS_CAMBIO_VALIDOS = {
    EstadoEquipo.POR_PREPARAR.value,
    EstadoEquipo.LISTO.value,
    EstadoEquipo.HOSPITAL.value,
    EstadoEquipo.CEMENTERIO.value,
}


def _normalizar_serial(valor: Any) -> str:
    return str(valor or "").strip().upper()


def _parse_decimal(valor: Any, default: Decimal = Decimal("0")) -> Decimal:
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if not texto:
        return default
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico inválido: '{valor}'") from exc


def _parse_bool(valor: Any) -> bool:
    return str(valor or "").strip().upper() in {"SI", "SÍ", "TRUE", "1", "YES", "X"}


def generar_plantilla_xlsx(flujo: str) -> bytes:
    """Genera la plantilla oficial .xlsx de Tekio Electronics para el flujo solicitado."""
    if flujo not in FLUJOS_PLANTILLAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Flujo de plantilla no soportado: '{flujo}'.",
        )
    spec = FLUJOS_PLANTILLAS[flujo]
    wb = Workbook()
    ws = wb.active
    ws.title = spec["titulo"][:31]

    relleno_cab = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fuente_cab = Font(color="FFFFFF", bold=True, size=10)
    relleno_ej = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")

    for col_idx, nombre_col in enumerate(spec["columnas"], start=1):
        celda = ws.cell(row=1, column=col_idx, value=nombre_col)
        celda.fill = relleno_cab
        celda.font = fuente_cab
        celda.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[celda.column_letter].width = max(16, len(nombre_col) + 4)

    for col_idx, val_ej in enumerate(spec["ejemplo"], start=1):
        celda = ws.cell(row=2, column=col_idx, value=val_ej)
        celda.fill = relleno_ej

    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def _leer_filas_archivo(contenido: bytes, nombre_archivo: str) -> tuple[list[str], list[dict[str, Any]]]:
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".csv"):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        lector = csv.DictReader(io.StringIO(texto))
        cabeceras = [str(c).strip().lower() for c in (lector.fieldnames or []) if c is not None]
        filas: list[dict[str, Any]] = []
        for idx, fila in enumerate(lector, start=2):
            limpia = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in fila.items() if k is not None}
            if not any(str(v or "").strip() for v in limpia.values()):
                continue
            limpia["_fila"] = idx
            filas.append(limpia)
        return cabeceras, filas

    if nombre.endswith(".xlsx") or nombre.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        ws = wb.active
        iter_filas = ws.iter_rows(values_only=True)
        try:
            primera = next(iter_filas)
        except StopIteration:
            return [], []
        cabeceras = [str(c).strip().lower() if c is not None else "" for c in primera]
        filas = []
        for idx, valores in enumerate(iter_filas, start=2):
            if not any(v is not None and str(v).strip() != "" for v in valores):
                continue
            reg: dict[str, Any] = {"_fila": idx}
            for col_idx, nombre_col in enumerate(cabeceras):
                if nombre_col:
                    val = valores[col_idx] if col_idx < len(valores) else None
                    reg[nombre_col] = str(val).strip() if val is not None else ""
            filas.append(reg)
        wb.close()
        return [c for c in cabeceras if c], filas

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato de archivo no soportado. Sube un archivo .xlsx o .csv.",
    )


def _resolver_sucursal(sucursales_por_nombre: dict[str, Sucursal], valor: str, default: Sucursal) -> Sucursal | None:
    if not valor:
        return default
    return sucursales_por_nombre.get(valor.strip().lower())


def previsualizar_importacion(
    bd: Session,
    *,
    flujo: str,
    contenido: bytes,
    nombre_archivo: str,
) -> dict[str, Any]:
    """Paso 1: valida columnas, seriales, SKUs y sucursales fila por fila sin modificar BD."""
    if flujo not in FLUJOS_PLANTILLAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Flujo no soportado: '{flujo}'.",
        )

    cabeceras, filas = _leer_filas_archivo(contenido, nombre_archivo)
    if not filas:
        return {
            "flujo": flujo,
            "total_filas": 0,
            "filas_validas": 0,
            "filas_con_error": 1,
            "puede_confirmar": False,
            "filas": [
                {
                    "fila": 1,
                    "valida": False,
                    "errores": ["El archivo no contiene filas de datos para importar."],
                    "datos": {},
                }
            ],
        }

    sucursales = bd.query(Sucursal).all()
    suc_por_nombre = {s.nombre.strip().lower(): s for s in sucursales}
    bodega = suc_por_nombre.get("bodega") or next((s for s in sucursales if s.estado == EstadoSucursal.ACTIVA.value), None)
    articulos = bd.query(CatalogoArticulo).all()
    art_por_sku = {a.sku.strip().upper(): a for a in articulos}
    seriales_bd = {r[0].upper() for r in bd.query(Equipo.serial).all()}

    seriales_vistos: set[str] = set()
    resultados: list[dict[str, Any]] = []
    validas = 0

    for fila in filas:
        num_fila = int(fila.get("_fila", 0))
        errores: list[str] = []

        if flujo in {"compras_nacionales", "compras_internacionales", "consignacion"}:
            serial = _normalizar_serial(fila.get("serial"))
            if len(serial) < 2:
                errores.append("Serial obligatorio (mínimo 2 caracteres).")
            elif serial in seriales_vistos:
                errores.append(f"Serial '{serial}' duplicado dentro del archivo.")
            elif serial in seriales_bd:
                errores.append(f"Serial '{serial}' ya existe en el inventario.")
            else:
                seriales_vistos.add(serial)

            sku = str(fila.get("sku") or "").strip().upper()
            if sku and sku not in art_por_sku:
                errores.append(f"SKU '{sku}' no existe en el catálogo.")

            suc_nombre = str(fila.get("sucursal") or "").strip()
            suc = _resolver_sucursal(suc_por_nombre, suc_nombre, bodega) if bodega else None
            if suc is None:
                errores.append(f"Sucursal '{suc_nombre}' no encontrada.")
            elif suc.estado != EstadoSucursal.ACTIVA.value:
                errores.append(f"La sucursal '{suc.nombre}' está cerrada.")

            try:
                if flujo != "consignacion":
                    costo = _parse_decimal(fila.get("costo_compra_usd"), Decimal("0"))
                    if costo < 0:
                        errores.append("costo_compra_usd no puede ser negativo.")
                precio = _parse_decimal(fila.get("precio_promo_usd"), Decimal("0"))
                if precio < 0:
                    errores.append("precio_promo_usd no puede ser negativo.")
                if flujo == "compras_internacionales":
                    _parse_decimal(fila.get("flete_total_usd"), Decimal("0"))
                    _parse_decimal(fila.get("aduana_total_usd"), Decimal("0"))
            except ValueError as exc:
                errores.append(str(exc))

        elif flujo == "traslados_universales":
            tipo_item = str(fila.get("tipo_item") or "").strip().upper()
            if tipo_item not in {"EQUIPO", "COMPONENTE", "ACCESORIO", "REPUESTO"}:
                errores.append("tipo_item debe ser EQUIPO o COMPONENTE.")
            origen_nom = str(fila.get("sucursal_origen") or "").strip()
            dest_nom = str(fila.get("sucursal_destino") or "").strip()
            origen = suc_por_nombre.get(origen_nom.lower())
            destino = suc_por_nombre.get(dest_nom.lower())
            if origen is None:
                errores.append(f"Sucursal origen '{origen_nom}' no existe.")
            if destino is None:
                errores.append(f"Sucursal destino '{dest_nom}' no existe.")
            elif destino.estado != EstadoSucursal.ACTIVA.value:
                errores.append(f"Sucursal destino '{destino.nombre}' está cerrada.")
            if origen and destino and origen.id == destino.id:
                errores.append("Sucursal origen y destino deben ser distintas.")

            if tipo_item == "EQUIPO":
                serial = _normalizar_serial(fila.get("serial"))
                if not serial or serial not in seriales_bd:
                    errores.append(f"Equipo con serial '{serial}' no encontrado en inventario.")
            else:
                sku = str(fila.get("sku") or "").strip().upper()
                if not sku or sku not in art_por_sku:
                    errores.append(f"SKU '{sku}' no encontrado en el catálogo.")
                try:
                    cant = int(str(fila.get("cantidad") or "0").strip())
                    if cant <= 0:
                        errores.append("Cantidad debe ser mayor a 0.")
                except ValueError:
                    errores.append("Cantidad inválida.")

        elif flujo == "cambio_estado":
            serial = _normalizar_serial(fila.get("serial"))
            if not serial or serial not in seriales_bd:
                errores.append(f"Equipo con serial '{serial}' no encontrado.")
            nuevo_est = str(fila.get("nuevo_estado") or "").strip().upper()
            if nuevo_est not in ESTADOS_CAMBIO_VALIDOS:
                errores.append(
                    f"Estado '{nuevo_est}' inválido. Permitidos: {', '.join(sorted(ESTADOS_CAMBIO_VALIDOS))}."
                )

        es_valida = len(errores) == 0
        if es_valida:
            validas += 1
        datos_limpios = {k: v for k, v in fila.items() if k != "_fila"}
        resultados.append(
            {
                "fila": num_fila,
                "valida": es_valida,
                "errores": errores,
                "datos": datos_limpios,
            }
        )

    con_error = len(resultados) - validas
    return {
        "flujo": flujo,
        "cabeceras_detectadas": cabeceras,
        "total_filas": len(resultados),
        "filas_validas": validas,
        "filas_con_error": con_error,
        "puede_confirmar": len(resultados) > 0 and con_error == 0,
        "filas": resultados,
    }


def _generar_correlativo_masivo(bd: Session, modelo: type, columna: Any, prefijo: str) -> str:
    hoy_str = obtener_fecha_hoy().strftime("%Y%m%d")
    base = f"{prefijo}-{hoy_str}-"
    cantidad = bd.query(func.count(modelo.id)).filter(columna.like(f"{base}%")).scalar() or 0
    secuencia = int(cantidad) + 1
    while True:
        candidato = f"{base}{secuencia:04d}"
        if not bd.query(modelo.id).filter(columna == candidato).first():
            return candidato
        secuencia += 1


def _obtener_o_crear_proveedor(bd: Session, nombre: str) -> Tercero | None:
    limpio = nombre.strip()
    if not limpio:
        return None
    existente = (
        bd.query(Tercero)
        .filter(func.lower(Tercero.nombre) == limpio.lower())
        .first()
    )
    if existente is not None:
        return existente
    nuevo = Tercero(
        nombre=limpio,
        tipo=TipoTercero.PROVEEDOR.value,
        rif_cedula="",
        telefono="",
        activo=True,
    )
    bd.add(nuevo)
    bd.flush()
    return nuevo


def confirmar_importacion_atomica(
    bd: Session,
    *,
    flujo: str,
    contenido: bytes,
    nombre_archivo: str,
    usuario: Usuario,
) -> dict[str, Any]:
    """Paso 2: aplica todas las filas en una sola transacción atómica (rollback total ante error)."""
    preview = previsualizar_importacion(
        bd,
        flujo=flujo,
        contenido=contenido,
        nombre_archivo=nombre_archivo,
    )
    if not preview["puede_confirmar"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "mensaje": "La importación contiene filas con errores. Corrige el archivo antes de confirmar.",
                "filas_con_error": preview["filas_con_error"],
                "filas": [f for f in preview["filas"] if not f["valida"]],
            },
        )

    hoy = obtener_fecha_hoy()
    sucursales = bd.query(Sucursal).all()
    suc_por_nombre = {s.nombre.strip().lower(): s for s in sucursales}
    bodega = suc_por_nombre.get("bodega") or next(s for s in sucursales if s.estado == EstadoSucursal.ACTIVA.value)
    art_por_sku = {a.sku.strip().upper(): a for a in bd.query(CatalogoArticulo).all()}

    filas_datos = [f["datos"] for f in preview["filas"]]

    try:
        if flujo in {"compras_nacionales", "compras_internacionales", "consignacion"}:
            primera = filas_datos[0]
            es_inter = flujo == "compras_internacionales"
            es_consig = flujo == "consignacion"
            prov_nom = str(
                primera.get("proveedor_consignacion") if es_consig else primera.get("proveedor") or ""
            ).strip()
            proveedor = _obtener_o_crear_proveedor(bd, prov_nom) if prov_nom else None

            flete_total = _parse_decimal(primera.get("flete_total_usd"), Decimal("0")) if es_inter else Decimal("0")
            aduana_total = _parse_decimal(primera.get("aduana_total_usd"), Decimal("0")) if es_inter else Decimal("0")
            gastos_extra = flete_total + aduana_total

            costos_base = [
                Decimal("0") if es_consig else _parse_decimal(f.get("costo_compra_usd"), Decimal("0"))
                for f in filas_datos
            ]
            monto_mercancia = sum(costos_base, Decimal("0"))

            numero_compra = _generar_correlativo_masivo(bd, Compra, Compra.numero_compra, "CMP")
            compra = Compra(
                numero_compra=numero_compra,
                origen=(
                    OrigenCompra.INTERNACIONAL.value
                    if es_inter
                    else OrigenCompra.CONSIGNACION.value
                    if es_consig
                    else OrigenCompra.NACIONAL.value
                ),
                tipo_compra=(
                    "INTERNACIONAL" if es_inter else "CONSIGNACION" if es_consig else "NACIONAL"
                ),
                moneda=str(primera.get("moneda") or "USD").strip().upper() or "USD",
                proveedor_id=proveedor.id if proveedor else None,
                fecha=hoy,
                factura_orden=str(primera.get("factura_orden") or "").strip(),
                numero_guia=str(primera.get("numero_guia") or "").strip(),
                monto_mercancia_usd=monto_mercancia,
                envio_usd=flete_total,
                aduana_usd=aduana_total,
                otros_gastos_usd=Decimal("0"),
                llega_preparada=_parse_bool(primera.get("llega_preparada")),
                estado=EstadoCompra.RECIBIDA.value,
                nota=f"Importación masiva ({flujo}): {nombre_archivo}",
                creado_por_id=usuario.id,
            )
            bd.add(compra)
            bd.flush()

            creados = 0
            total_unidades = len(filas_datos)
            for idx_f, f in enumerate(filas_datos):
                serial = _normalizar_serial(f.get("serial"))
                sku = str(f.get("sku") or "").strip().upper()
                art = art_por_sku.get(sku) if sku else None
                suc = _resolver_sucursal(suc_por_nombre, str(f.get("sucursal") or ""), bodega) or bodega
                costo_unit = costos_base[idx_f]
                if es_inter and gastos_extra > 0:
                    if monto_mercancia > 0:
                        flete_unit = (gastos_extra * costo_unit / monto_mercancia).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    else:
                        flete_unit = (gastos_extra / Decimal(total_unidades)).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                else:
                    flete_unit = Decimal("0")

                llega_prep = _parse_bool(f.get("llega_preparada"))
                eq = Equipo(
                    serial=serial,
                    articulo_id=art.id if art else None,
                    compra_id=compra.id,
                    modelo=str(f.get("modelo") or (art.descripcion if art else "")).strip(),
                    configuracion=str(f.get("configuracion") or "").strip(),
                    categoria=str(f.get("categoria") or "Laptop").strip() or "Laptop",
                    ubicacion_id=suc.id,
                    estado=EstadoEquipo.LISTO.value if llega_prep else EstadoEquipo.POR_PREPARAR.value,
                    costo_compra_usd=costo_unit,
                    costo_flete_usd=flete_unit,
                    costo_taller_usd=Decimal("0"),
                    precio_promo_usd=_parse_decimal(f.get("precio_promo_usd"), Decimal("0")),
                    es_consignacion=es_consig,
                    proveedor_consignacion_id=proveedor.id if (es_consig and proveedor) else None,
                    recibido_por_id=usuario.id,
                    fecha_recepcion=hoy,
                    nota=str(f.get("nota") or "").strip(),
                )
                bd.add(eq)
                bd.flush()
                bd.add(
                    MovimientoInventario(
                        tipo=TipoMovimientoInventario.COMPRA.value,
                        articulo_id=eq.articulo_id,
                        equipo_id=eq.id,
                        sucursal_id=suc.id,
                        cantidad=1,
                        costo_unitario_usd=Decimal("0") if es_consig else (costo_unit + flete_unit),
                        documento_ref=numero_compra,
                        motivo=f"Importación masiva ({flujo})",
                        usuario_id=usuario.id,
                    )
                )
                creados += 1

            bd.commit()
            return {
                "flujo": flujo,
                "procesados": creados,
                "documento_ref": numero_compra,
                "mensaje": f"Se importaron {creados} equipos correctamente ({numero_compra}).",
            }

        if flujo == "traslados_universales":
            # Agrupar por (origen_id, destino_id)
            grupos: dict[tuple[int, int], list[dict[str, Any]]] = {}
            for f in filas_datos:
                origen = suc_por_nombre[str(f.get("sucursal_origen") or "").strip().lower()]
                destino = suc_por_nombre[str(f.get("sucursal_destino") or "").strip().lower()]
                grupos.setdefault((origen.id, destino.id), []).append(f)

            traslados_creados: list[str] = []
            total_items = 0
            for (orig_id, dest_id), items in grupos.items():
                num_trs = _generar_correlativo_masivo(bd, Traslado, Traslado.numero_traslado, "TRS")
                trs = Traslado(
                    numero_traslado=num_trs,
                    origen_id=orig_id,
                    destino_id=dest_id,
                    estado=EstadoTraslado.EN_TRANSITO.value,
                    enviado_por_id=usuario.id,
                    nota=str(items[0].get("nota") or f"Traslado masivo: {nombre_archivo}").strip(),
                )
                bd.add(trs)
                bd.flush()
                for f in items:
                    tipo_item = str(f.get("tipo_item") or "").strip().upper()
                    if tipo_item == "EQUIPO":
                        serial = _normalizar_serial(f.get("serial"))
                        eq = bd.query(Equipo).filter(Equipo.serial == serial).first()
                        if eq is None or eq.ubicacion_id != orig_id or eq.estado in {EstadoEquipo.VENDIDO.value, EstadoEquipo.EN_TRANSITO.value}:
                            raise ValueError(
                                f"El equipo '{serial}' no está disponible en la sucursal origen."
                            )
                        eq.estado_previo_traslado = eq.estado
                        eq.estado = EstadoEquipo.EN_TRANSITO.value
                        bd.add(TrasladoDetalle(traslado_id=trs.id, equipo_id=eq.id, cantidad=1))
                        bd.add(
                            MovimientoInventario(
                                tipo=TipoMovimientoInventario.TRASLADO_SALIDA.value,
                                articulo_id=eq.articulo_id,
                                equipo_id=eq.id,
                                sucursal_id=orig_id,
                                cantidad=-1,
                                costo_unitario_usd=eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd,
                                documento_ref=num_trs,
                                motivo=f"Traslado masivo hacia sucursal #{dest_id}",
                                usuario_id=usuario.id,
                            )
                        )
                    else:
                        sku = str(f.get("sku") or "").strip().upper()
                        art = art_por_sku[sku]
                        cant = int(str(f.get("cantidad") or "0").strip())
                        stock_actual = int(
                            bd.query(func.coalesce(func.sum(MovimientoInventario.cantidad), 0))
                            .filter(
                                MovimientoInventario.articulo_id == art.id,
                                MovimientoInventario.sucursal_id == orig_id,
                                MovimientoInventario.equipo_id.is_(None),
                            )
                            .scalar()
                            or 0
                        )
                        if stock_actual < cant:
                            raise ValueError(
                                f"Stock insuficiente de '{sku}' en origen (disponible: {stock_actual}, solicitado: {cant})."
                            )
                        bd.add(TrasladoDetalle(traslado_id=trs.id, articulo_id=art.id, cantidad=cant))
                        bd.add(
                            MovimientoInventario(
                                tipo=TipoMovimientoInventario.TRASLADO_SALIDA.value,
                                articulo_id=art.id,
                                equipo_id=None,
                                sucursal_id=orig_id,
                                cantidad=-cant,
                                costo_unitario_usd=Decimal("0"),
                                documento_ref=num_trs,
                                motivo=f"Traslado masivo hacia sucursal #{dest_id}",
                                usuario_id=usuario.id,
                            )
                        )
                    total_items += 1
                traslados_creados.append(num_trs)

            bd.commit()
            return {
                "flujo": flujo,
                "procesados": total_items,
                "documento_ref": ", ".join(traslados_creados),
                "mensaje": f"Se crearon {len(traslados_creados)} traslados ({total_items} ítems) en estado EN_TRANSITO.",
            }

        # flujo == "cambio_estado"
        actualizados = 0
        for f in filas_datos:
            serial = _normalizar_serial(f.get("serial"))
            nuevo_est = str(f.get("nuevo_estado") or "").strip().upper()
            motivo = str(f.get("motivo") or "Cambio de estado masivo").strip()
            eq = bd.query(Equipo).filter(Equipo.serial == serial).first()
            if eq is None or eq.estado == EstadoEquipo.VENDIDO.value:
                raise ValueError(f"El equipo '{serial}' no puede cambiar de estado (vendido o inexistente).")
            estado_anterior = eq.estado
            eq.estado = nuevo_est
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TALLER.value,
                    articulo_id=eq.articulo_id,
                    equipo_id=eq.id,
                    sucursal_id=eq.ubicacion_id,
                    cantidad=0,
                    costo_unitario_usd=Decimal("0"),
                    documento_ref="ESTADO-MASIVO",
                    motivo=f"Cambio de estado {estado_anterior} -> {nuevo_est}: {motivo}",
                    usuario_id=usuario.id,
                )
            )
            actualizados += 1

        bd.commit()
        return {
            "flujo": flujo,
            "procesados": actualizados,
            "documento_ref": "ESTADO-MASIVO",
            "mensaje": f"Se actualizó el estado de {actualizados} equipos correctamente.",
        }

    except HTTPException:
        bd.rollback()
        raise
    except Exception as exc:
        bd.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error durante la importación atómica (se revirtieron todos los cambios): {exc}",
        ) from exc

from __future__ import annotations

import csv
import io
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.core.empresa import RAZON_SOCIAL, RIF
from app.core.validacion import ModeloEntradaLimpio
from app.esquemas_logistica import normalizar_serial
from app.modelos import CatalogoArticulo, Sucursal, Usuario
from app.modelos_logistica import (
    Compra,
    CompraComponente,
    CompraTracking,
    Equipo,
    EstadoCompra,
    EstadoEquipo,
    MovimientoInventario,
    TipoMovimientoInventario,
)
from app.rutas.logistica import ROLES_LOGISTICA
from app.rutas.tasas import obtener_fecha_hoy
from app.seguridad import puede_ver_costos, requerir_roles
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.contabilidad_service import registrar_asiento


enrutador = APIRouter(prefix="/api/logistica", tags=["Recepción de Compras (Escáner y Masiva)"])

CONDICIONES_VALIDAS = frozenset({"EXCELENTE", "BUENO", "CON_DETALLES", "CON_FALLA"})
ESTADOS_INICIALES_VALIDOS = frozenset({EstadoEquipo.POR_PREPARAR.value, EstadoEquipo.HOSPITAL.value, EstadoEquipo.LISTO.value})


def _d2(val: Decimal | float | int) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _r2(val: Decimal | float | int) -> float:
    return float(_d2(val))


def _norm_header(texto: Any) -> str:
    s = str(texto or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _parse_bool(valor: Any, default: bool = True) -> bool:
    if isinstance(valor, bool):
        return valor
    s = str(valor or "").strip().lower()
    if not s:
        return default
    if s in ("no", "n", "false", "0", "falso"):
        return False
    return True


class EquipoRecepcionEntrada(ModeloEntradaLimpio):
    serial: str = Field(min_length=2, max_length=100)
    modelo: str = Field(default="", max_length=160)
    articulo_id: int | None = None
    ram: str = Field(default="", max_length=60)
    almacenamiento: str = Field(default="", max_length=60)
    categoria: str = Field(default="Laptop", max_length=100)
    condicion_llegada: Literal["EXCELENTE", "BUENO", "CON_DETALLES", "CON_FALLA"] = "BUENO"
    incluye_cargador: bool = True
    observaciones_llegada: str = Field(default="", max_length=500)
    estado_inicial: Literal["POR_PREPARAR", "HOSPITAL", "LISTO"] = "POR_PREPARAR"
    costo_compra_usd: Decimal | None = Field(default=None, ge=0)
    precio_promo_usd: Decimal | None = Field(default=None, ge=0)


class ComponenteRecepcionEntrada(ModeloEntradaLimpio):
    articulo_id: int
    cantidad: int = Field(gt=0)
    costo_unitario_usd: Decimal = Field(default=Decimal("0"), ge=0)


class RecepcionCompraEntrada(ModeloEntradaLimpio):
    sucursal_destino_id: int
    tracking_id: int | None = None
    cerrar_compra: bool = False
    equipos: list[EquipoRecepcionEntrada] = Field(default_factory=list)
    componentes: list[ComponenteRecepcionEntrada] = Field(default_factory=list)


@enrutador.get("/compras/pendientes-recepcion")
def listar_compras_pendientes_recepcion(
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    """Lista compras en estado PENDIENTE, PENDIENTE_RECEPCION, EN_TRANSITO o RECIBIDA_PARCIAL."""
    estados_abiertos = [
        EstadoCompra.PENDIENTE.value,
        "PENDIENTE_RECEPCION",
        "EN_TRANSITO",
        EstadoCompra.RECIBIDA_PARCIAL.value,
    ]
    compras = (
        bd.query(Compra)
        .options(
            joinedload(Compra.proveedor),
            joinedload(Compra.equipos),
            joinedload(Compra.componentes),
            joinedload(Compra.trackings),
        )
        .filter(Compra.estado.in_(estados_abiertos))
        .order_by(Compra.id.desc())
        .all()
    )
    ver_costos = puede_ver_costos(usuario_actual.rol)
    salida: list[dict[str, Any]] = []
    for c in compras:
        recibidos_eq = len(c.equipos or [])
        esperada = int(getattr(c, "cantidad_esperada", 0) or 0)
        if esperada <= 0:
            esperada = max(recibidos_eq, 1)
        fila: dict[str, Any] = {
            "id": c.id,
            "numero_compra": c.numero_compra,
            "origen": c.origen,
            "tipo_compra": getattr(c, "tipo_compra", "NACIONAL"),
            "proveedor": c.proveedor.nombre if c.proveedor else "Sin proveedor",
            "fecha": c.fecha.isoformat(),
            "factura_orden": c.factura_orden,
            "numero_guia": getattr(c, "numero_guia", ""),
            "estado": c.estado,
            "equipos_recibidos": recibidos_eq,
            "cantidad_esperada": esperada,
            "trackings": [
                {
                    "id": t.id,
                    "numero_tracking": t.numero_tracking,
                    "courier": t.courier,
                    "estado": t.estado,
                }
                for t in (c.trackings or [])
            ],
        }
        if ver_costos:
            fila["monto_mercancia_usd"] = _r2(c.monto_mercancia_usd or 0)
            fila["envio_usd"] = _r2(c.envio_usd or 0)
            fila["aduana_usd"] = _r2(getattr(c, "aduana_usd", 0) or 0)
            fila["otros_gastos_usd"] = _r2(c.otros_gastos_usd or 0)
        salida.append(fila)
    return salida


@enrutador.get("/compras/plantilla-recepcion.xlsx")
def descargar_plantilla_recepcion_xlsx(
    _usuario: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
) -> StreamingResponse:
    """Descarga la plantilla Excel (.xlsx) oficial de Tekio para recepción masiva de compras."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Recepción Compras"

    fill_banner = PatternFill(start_color="E85A28", end_color="E85A28", fill_type="solid")
    fill_hdr = PatternFill(start_color="F6F6F6", end_color="F6F6F6", fill_type="solid")
    font_banner = Font(bold=True, color="FFFFFF", size=11)
    font_hdr = Font(bold=True, color="191818", size=10)

    ws.merge_cells("A1:I1")
    ws["A1"] = f"{RAZON_SOCIAL} (RIF {RIF}) — Plantilla Oficial de Recepción Masiva de Compras"
    ws["A1"].fill = fill_banner
    ws["A1"].font = font_banner
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    headers = [
        "serial",
        "sku_o_modelo",
        "ram",
        "almacenamiento",
        "condicion_llegada",
        "incluye_cargador",
        "observaciones_llegada",
        "estado_inicial",
        "cantidad",
    ]
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        c = ws.cell(row=2, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    ws.append(["SN-EJEMPLO-001", "Lenovo ThinkPad T14", "16GB", "512GB SSD", "EXCELENTE", "SI", "Sin detalles", "POR_PREPARAR", 1])
    ws.append(["SN-EJEMPLO-002", "Dell Latitude 5420", "8GB", "256GB SSD", "CON_DETALLES", "NO", "Rayón leve en tapa, sin cargador", "POR_PREPARAR", 1])
    ws.append(["", "RAM-8GB-DDR4", "", "", "EXCELENTE", "NO", "Accesorio/Componente por cantidad", "LISTO", 5])

    for idx_col, col in enumerate(ws.iter_cols(min_row=2, max_row=5, min_col=1, max_col=len(headers)), start=1):
        max_len = max((len(str(cell.value or "")) for cell in col), default=12)
        ws.column_dimensions[get_column_letter(idx_col)].width = min(max(max_len + 3, 14), 36)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="tekio_plantilla_recepcion_compras.xlsx"'},
    )


def _ejecutar_recepcion_compra_atomica(
    bd: Session,
    *,
    compra_id: int,
    datos: RecepcionCompraEntrada,
    usuario_actual: Usuario,
    modo: str,
) -> dict[str, Any]:
    if not datos.equipos and not datos.componentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes incluir al menos un equipo serializado o un componente para recibir.",
        )

    compra = (
        bd.query(Compra)
        .options(joinedload(Compra.equipos), joinedload(Compra.trackings))
        .filter(Compra.id == compra_id)
        .first()
    )
    if compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    sucursal = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_destino_id).first()
    if sucursal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede destino no encontrada.")

    hoy = obtener_fecha_hoy()

    # Validar seriales duplicados en lote y contra la BD
    seriales_lote: set[str] = set()
    seriales_norm: list[str] = []
    for eq_in in datos.equipos:
        sn = normalizar_serial(eq_in.serial)
        if sn in seriales_lote:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Serial duplicado dentro del mismo lote de recepción: '{sn}'.",
            )
        seriales_lote.add(sn)
        seriales_norm.append(sn)

    if seriales_norm:
        existentes = (
            bd.query(Equipo.serial)
            .filter(func.upper(Equipo.serial).in_(seriales_norm))
            .all()
        )
        if existentes:
            dups = ", ".join(r[0] for r in existentes[:5])
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Los siguientes seriales ya existen en el inventario: {dups}.",
            )

    # Prorrateo automático de flete + aduana + otros gastos
    gastos_log = _d2(
        Decimal(compra.envio_usd or 0)
        + Decimal(getattr(compra, "aduana_usd", 0) or 0)
        + Decimal(compra.otros_gastos_usd or 0)
    )
    total_unidades_base = max(
        int(getattr(compra, "cantidad_esperada", 0) or 0),
        len(compra.equipos or []) + len(datos.equipos),
        1,
    )
    flete_unitario = _d2(gastos_log / Decimal(total_unidades_base)) if gastos_log > 0 else Decimal("0.00")
    costo_base_auto = (
        _d2(Decimal(compra.monto_mercancia_usd or 0) / Decimal(total_unidades_base))
        if Decimal(compra.monto_mercancia_usd or 0) > 0
        else Decimal("0.00")
    )

    equipos_creados: list[Equipo] = []
    valor_total_equipos = Decimal("0.00")
    valor_total_componentes = Decimal("0.00")

    try:
        for eq_in, sn in zip(datos.equipos, seriales_norm):
            art: CatalogoArticulo | None = None
            if eq_in.articulo_id is not None:
                art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == eq_in.articulo_id).first()

            modelo_final = eq_in.modelo.strip() or (art.descripcion if art else sn)
            specs_partes = [p for p in [eq_in.ram.strip(), eq_in.almacenamiento.strip()] if p]
            config_final = " / ".join(specs_partes)
            costo_compra = _d2(eq_in.costo_compra_usd) if eq_in.costo_compra_usd is not None else costo_base_auto
            precio_promo = _d2(eq_in.precio_promo_usd) if eq_in.precio_promo_usd is not None else Decimal("0.00")
            estado_dest = (
                EstadoEquipo.LISTO.value
                if (compra.llega_preparada and eq_in.estado_inicial == EstadoEquipo.POR_PREPARAR.value)
                else eq_in.estado_inicial
            )

            nuevo_eq = Equipo(
                serial=sn,
                articulo_id=art.id if art else None,
                compra_id=compra.id,
                modelo=modelo_final,
                configuracion=config_final,
                categoria=eq_in.categoria.strip() or "Laptop",
                ubicacion_id=sucursal.id,
                estado=estado_dest,
                costo_compra_usd=costo_compra,
                costo_flete_usd=flete_unitario,
                costo_taller_usd=Decimal("0.00"),
                precio_promo_usd=precio_promo,
                recibido_por_id=usuario_actual.id,
                fecha_recepcion=hoy,
                condicion_llegada=eq_in.condicion_llegada,
                incluye_cargador=bool(eq_in.incluye_cargador),
                observaciones_llegada=eq_in.observaciones_llegada.strip(),
                nota=eq_in.observaciones_llegada.strip(),
            )
            bd.add(nuevo_eq)
            bd.flush()

            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.COMPRA.value,
                    equipo_id=nuevo_eq.id,
                    articulo_id=nuevo_eq.articulo_id,
                    cantidad=1,
                    sucursal_id=sucursal.id,
                    documento_ref=compra.numero_compra,
                    usuario_id=usuario_actual.id,
                    motivo=f"Recepción {modo} compra {compra.numero_compra} ({eq_in.condicion_llegada})",
                )
            )
            equipos_creados.append(nuevo_eq)
            valor_total_equipos += costo_compra + flete_unitario

        componentes_recibidos = 0
        for comp_in in datos.componentes:
            art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == comp_in.articulo_id).first()
            if art is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Artículo/componente ID {comp_in.articulo_id} no encontrado.",
                )
            bd.add(
                CompraComponente(
                    compra_id=compra.id,
                    articulo_id=art.id,
                    cantidad=comp_in.cantidad,
                    cantidad_recibida=comp_in.cantidad,
                    costo_unitario_usd=_d2(comp_in.costo_unitario_usd),
                    costo_flete_unitario_usd=Decimal("0.00"),
                )
            )
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.COMPRA.value,
                    equipo_id=None,
                    articulo_id=art.id,
                    cantidad=comp_in.cantidad,
                    sucursal_id=sucursal.id,
                    documento_ref=compra.numero_compra,
                    usuario_id=usuario_actual.id,
                    motivo=f"Recepción {modo} componente compra {compra.numero_compra}",
                )
            )
            componentes_recibidos += comp_in.cantidad
            valor_total_componentes += _d2(comp_in.costo_unitario_usd) * Decimal(comp_in.cantidad)

        # Actualizar estado de compra (RECIBIDA_PARCIAL vs RECIBIDA)
        total_eq_compra = len(compra.equipos or []) + len(equipos_creados)
        esperada = int(getattr(compra, "cantidad_esperada", 0) or 0)
        estado_anterior = compra.estado
        if datos.cerrar_compra or (esperada > 0 and total_eq_compra >= esperada):
            compra.estado = EstadoCompra.RECIBIDA.value
        else:
            compra.estado = EstadoCompra.RECIBIDA_PARCIAL.value

        # Marcar tracking asociado como RECIBIDO_ALMACEN si se seleccionó
        if datos.tracking_id is not None:
            trk = (
                bd.query(CompraTracking)
                .filter(CompraTracking.id == datos.tracking_id, CompraTracking.compra_id == compra.id)
                .first()
            )
            if trk is not None:
                trk.estado = "RECIBIDO_ALMACEN"

        # Asiento contable de reclasificación cuadrado (Debe == Haber)
        total_asiento = _d2(valor_total_equipos + valor_total_componentes)
        asiento_id: int | None = None
        if total_asiento > Decimal("0.00"):
            lineas: list[dict[str, Any]] = []
            if valor_total_equipos > Decimal("0.00"):
                lineas.append(
                    {
                        "codigo_cuenta": "1.1.04",
                        "debe_usd": _d2(valor_total_equipos),
                        "descripcion": f"Ingreso inventario equipos recepción {compra.numero_compra}",
                    }
                )
            if valor_total_componentes > Decimal("0.00"):
                lineas.append(
                    {
                        "codigo_cuenta": "1.1.05",
                        "debe_usd": _d2(valor_total_componentes),
                        "descripcion": f"Ingreso componentes recepción {compra.numero_compra}",
                    }
                )
            lineas.append(
                {
                    "codigo_cuenta": "1.1.04",
                    "haber_usd": total_asiento,
                    "descripcion": f"Reclasificación tránsito/recepción {compra.numero_compra}",
                }
            )
            asiento = registrar_asiento(
                bd,
                fecha=hoy,
                referencia=f"REC-{compra.numero_compra}",
                modulo_origen="RECEPCION_COMPRA",
                entidad_id=str(compra.id),
                descripcion=f"Recepción {modo} de compra {compra.numero_compra} ({len(equipos_creados)} equipos)",
                creado_por_id=usuario_actual.id,
                lineas=lineas,
            )
            asiento_id = asiento.id

        registrar_auditoria(
            bd,
            usuario=usuario_actual,
            modulo="LOGISTICA_RECEPCION",
            accion="RECEPCION_COMPRA",
            entidad_id=compra.numero_compra,
            detalle_anterior={"estado_compra": estado_anterior},
            detalle_nuevo={
                "modo": modo,
                "estado_compra": compra.estado,
                "sucursal_destino": sucursal.nombre,
                "equipos_recibidos": len(equipos_creados),
                "componentes_recibidos": componentes_recibidos,
                "seriales": seriales_norm[:20],
                "asiento_id": asiento_id,
            },
        )
        bd.commit()
    except HTTPException:
        bd.rollback()
        raise
    except Exception as exc:
        bd.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al procesar la recepción: {exc}",
        ) from exc

    ver_costos = puede_ver_costos(usuario_actual.rol)
    respuesta: dict[str, Any] = {
        "compra_id": compra.id,
        "numero_compra": compra.numero_compra,
        "estado_compra": compra.estado,
        "sucursal_destino": sucursal.nombre,
        "equipos_recibidos": len(equipos_creados),
        "componentes_recibidos": componentes_recibidos,
        "total_equipos_compra": total_eq_compra,
        "asiento_id": asiento_id,
        "equipos": [
            {
                "id": e.id,
                "serial": e.serial,
                "modelo": e.modelo,
                "configuracion": e.configuracion,
                "estado": e.estado,
                "condicion_llegada": e.condicion_llegada,
                "incluye_cargador": e.incluye_cargador,
                "observaciones_llegada": e.observaciones_llegada,
                **(
                    {
                        "costo_compra_usd": _r2(e.costo_compra_usd),
                        "costo_flete_usd": _r2(e.costo_flete_usd),
                        "costo_total_usd": _r2(e.costo_compra_usd + e.costo_flete_usd),
                    }
                    if ver_costos
                    else {}
                ),
            }
            for e in equipos_creados
        ],
    }
    return respuesta


@enrutador.post("/compras/{compra_id}/recibir", status_code=status.HTTP_201_CREATED)
def recibir_compra_uno_a_uno(
    compra_id: int,
    datos: RecepcionCompraEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Modo 1: Recepción uno a uno (escáner / manual) parcial o total de una compra."""
    return _ejecutar_recepcion_compra_atomica(
        bd,
        compra_id=compra_id,
        datos=datos,
        usuario_actual=usuario_actual,
        modo="UNO_A_UNO",
    )


def _leer_archivo_recepcion(contenido: bytes, nombre: str) -> list[dict[str, Any]]:
    ext = (nombre or "").lower()
    if ext.endswith(".csv"):
        texto = contenido.decode("utf-8-sig", errors="replace")
        delim = ";" if texto[:2048].count(";") > texto[:2048].count(",") else ","
        filas_raw = list(csv.reader(io.StringIO(texto), delimiter=delim))
        if not filas_raw:
            return []
        headers = [_norm_header(h) for h in filas_raw[0]]
        salida: list[dict[str, Any]] = []
        for row in filas_raw[1:]:
            if not any(str(c or "").strip() for c in row):
                continue
            salida.append({headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))})
        return salida

    wb = load_workbook(io.BytesIO(contenido), data_only=True)
    ws = wb.active
    todas = list(ws.iter_rows(values_only=True))
    if not todas:
        return []
    idx_h = 0
    for i, row in enumerate(todas[:8]):
        norm_row = [_norm_header(c) for c in row]
        if "serial" in norm_row or "sku_o_modelo" in norm_row or "modelo" in norm_row:
            idx_h = i
            break
    headers = [_norm_header(h) for h in todas[idx_h]]
    salida = []
    for row in todas[idx_h + 1 :]:
        if not any(c is not None and str(c).strip() for c in row):
            continue
        salida.append({headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))})
    return salida


@enrutador.post("/compras/{compra_id}/recibir/preview")
async def preview_recepcion_masiva_compra(
    compra_id: int,
    archivo: UploadFile = File(...),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Modo 2 — Paso 1: Valida archivo .xlsx/.csv de recepción masiva contra inventario y catálogo."""
    compra = bd.query(Compra).filter(Compra.id == compra_id).first()
    if compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío.")

    try:
        filas_raw = _leer_archivo_recepcion(contenido, archivo.filename or "recepcion.xlsx")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo leer el archivo: {exc}",
        ) from exc

    if not filas_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no contiene filas de datos.",
        )

    articulos = bd.query(CatalogoArticulo).all()
    mapa_sku = {a.sku.strip().upper(): a for a in articulos}

    seriales_bd = {r[0].upper() for r in bd.query(Equipo.serial).all()}
    seriales_archivo: set[str] = set()

    filas_validacion: list[dict[str, Any]] = []
    validas = 0
    con_errores = 0

    for idx, row in enumerate(filas_raw, start=1):
        errores: list[str] = []
        serial_crudo = str(row.get("serial") or "").strip()
        sku_o_modelo = str(row.get("sku_o_modelo") or row.get("modelo") or row.get("sku") or "").strip()
        ram = str(row.get("ram") or "").strip()
        almacenamiento = str(row.get("almacenamiento") or row.get("ssd") or "").strip()
        cond = str(row.get("condicion_llegada") or "BUENO").strip().upper() or "BUENO"
        incluye_cargador = _parse_bool(row.get("incluye_cargador"), True)
        obs = str(row.get("observaciones_llegada") or row.get("observaciones") or "").strip()
        estado_ini = str(row.get("estado_inicial") or "POR_PREPARAR").strip().upper() or "POR_PREPARAR"
        try:
            cantidad = int(float(row.get("cantidad") or 1))
        except (TypeError, ValueError):
            cantidad = 1

        if cond not in CONDICIONES_VALIDAS:
            errores.append(f"Condición inválida '{cond}' (usa EXCELENTE, BUENO, CON_DETALLES o CON_FALLA).")
            cond = "BUENO"
        if estado_ini not in ESTADOS_INICIALES_VALIDOS:
            errores.append(f"Estado inicial inválido '{estado_ini}' (usa POR_PREPARAR o HOSPITAL).")
            estado_ini = "POR_PREPARAR"

        art_match = mapa_sku.get(sku_o_modelo.upper())

        if serial_crudo:
            sn = normalizar_serial(serial_crudo)
            if sn in seriales_bd:
                errores.append(f"Serial '{sn}' ya existe en inventario.")
            if sn in seriales_archivo:
                errores.append(f"Serial '{sn}' repetido en este archivo.")
            seriales_archivo.add(sn)
            if not sku_o_modelo:
                errores.append("Falta sku_o_modelo.")
            tipo_fila = "EQUIPO"
        else:
            sn = ""
            tipo_fila = "COMPONENTE"
            if art_match is None:
                errores.append(f"SKU '{sku_o_modelo}' no encontrado en el catálogo para componente/accesorio.")
            if cantidad <= 0:
                errores.append("La cantidad debe ser mayor a 0.")

        es_valida = len(errores) == 0
        if es_valida:
            validas += 1
        else:
            con_errores += 1

        filas_validacion.append(
            {
                "fila": idx,
                "tipo": tipo_fila,
                "valida": es_valida,
                "errores": errores,
                "serial": sn,
                "sku_o_modelo": sku_o_modelo,
                "articulo_id": art_match.id if art_match else None,
                "ram": ram,
                "almacenamiento": almacenamiento,
                "condicion_llegada": cond,
                "incluye_cargador": incluye_cargador,
                "observaciones_llegada": obs,
                "estado_inicial": estado_ini,
                "cantidad": cantidad,
            }
        )

    return {
        "compra_id": compra.id,
        "numero_compra": compra.numero_compra,
        "total_filas": len(filas_validacion),
        "validas": validas,
        "con_errores": con_errores,
        "filas": filas_validacion,
    }


@enrutador.post("/compras/{compra_id}/recibir/confirmar", status_code=status.HTTP_201_CREATED)
def confirmar_recepcion_masiva_compra(
    compra_id: int,
    datos: RecepcionCompraEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_LOGISTICA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Modo 2 — Paso 2: Confirmación atómica de recepción masiva (rollback completo si falla cualquier fila)."""
    return _ejecutar_recepcion_compra_atomica(
        bd,
        compra_id=compra_id,
        datos=datos,
        usuario_actual=usuario_actual,
        modo="MASIVA_XLSX",
    )

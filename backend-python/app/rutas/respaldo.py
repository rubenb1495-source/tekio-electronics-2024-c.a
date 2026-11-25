from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.modelos import CatalogoArticulo, RolUsuario, Usuario
from app.modelos_admin_finanzas import AuditoriaSistema
from app.modelos_finanzas import (
    CuentaPorCobrar,
    InstrumentoFinanciero,
    Pago,
    TipoMovimientoPago,
    Venta,
)
from app.modelos_logistica import Compra, Equipo, MovimientoInventario
from app.seguridad import requerir_roles
from app.servicios.auditoria_service import registrar_auditoria


enrutador = APIRouter(prefix="/api/admin/respaldo", tags=["Respaldo y Copias de Seguridad"])
ZONA_CARACAS = ZoneInfo("America/Caracas")


def _serializar_valor(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace")
    return val


def _generar_excel_resumen(bd: Session) -> bytes:
    """Genera libro Excel legible con las 7 pestañas clave para auditoría rápida."""
    wb = Workbook()
    fill_hdr = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    font_hdr = Font(bold=True, color="FFFFFF")

    def _preparar_hoja(ws: Any, headers: list[str], widths: list[int]) -> None:
        ws.append(headers)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = fill_hdr
            cell.font = font_hdr
        for idx, w in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + idx)].width = w

    # 1. Saldos de Cajas y Bancos
    ws1 = wb.active
    ws1.title = "Saldos Cajas y Bancos"
    _preparar_hoja(
        ws1,
        ["ID", "Instrumento", "Moneda", "Saldo Moneda Origen", "Estado"],
        [8, 30, 12, 22, 14],
    )
    instrumentos = bd.query(InstrumentoFinanciero).order_by(InstrumentoFinanciero.id.asc()).all()
    pagos = bd.query(Pago).filter(Pago.anulado.is_(False)).all()
    saldos_inst: dict[int, Decimal] = {i.id: Decimal("0.00") for i in instrumentos}
    for p in pagos:
        if p.instrumento_id in saldos_inst:
            signo = Decimal("1") if p.tipo_movimiento == TipoMovimientoPago.INGRESO.value else Decimal("-1")
            saldos_inst[p.instrumento_id] += signo * p.monto_moneda_origen
    for inst in instrumentos:
        saldo = saldos_inst.get(inst.id, Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ws1.append([inst.id, inst.nombre, inst.moneda, float(saldo), "ACTIVO" if inst.activo else "INACTIVO"])

    # 2. Inventario Equipos
    ws2 = wb.create_sheet(title="Inventario Equipos")
    _preparar_hoja(
        ws2,
        ["ID", "Serial", "Modelo", "Configuración", "Sucursal", "Estado", "Costo Total USD", "Promo USD"],
        [8, 20, 26, 30, 18, 16, 16, 16],
    )
    equipos = bd.query(Equipo).options(joinedload(Equipo.ubicacion)).order_by(Equipo.id.asc()).all()
    for eq in equipos:
        costo_tot = (eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        ws2.append([
            eq.id,
            eq.serial,
            eq.modelo,
            eq.configuracion,
            eq.ubicacion.nombre if eq.ubicacion else "",
            eq.estado,
            float(costo_tot),
            float(eq.precio_promo_usd),
        ])

    # 3. Inventario Componentes y Repuestos
    ws3 = wb.create_sheet(title="Inventario Componentes")
    _preparar_hoja(
        ws3,
        ["Artículo ID", "SKU", "Descripción", "Tipo", "Stock Actual"],
        [12, 20, 34, 16, 14],
    )
    articulos = {a.id: a for a in bd.query(CatalogoArticulo).all()}
    saldos_comp = (
        bd.query(
            MovimientoInventario.articulo_id,
            func.coalesce(func.sum(MovimientoInventario.cantidad), 0).label("stock"),
        )
        .filter(
            MovimientoInventario.equipo_id.is_(None),
            MovimientoInventario.articulo_id.isnot(None),
        )
        .group_by(MovimientoInventario.articulo_id)
        .all()
    )
    for art_id, stock in saldos_comp:
        art = articulos.get(art_id)
        ws3.append([
            art_id,
            art.sku if art else "",
            art.descripcion if art else "",
            art.tipo if art else "",
            int(stock or 0),
        ])

    # 4. Ventas y Servicios Técnicos
    ws4 = wb.create_sheet(title="Ventas y Servicios")
    _preparar_hoja(
        ws4,
        ["Nota", "Fecha", "Sucursal", "Cliente", "Asesor", "Estado", "Promo USD", "Regular USD"],
        [12, 14, 18, 26, 22, 14, 15, 15],
    )
    ventas = (
        bd.query(Venta)
        .options(
            joinedload(Venta.sucursal),
            joinedload(Venta.cliente),
            joinedload(Venta.asesor),
        )
        .order_by(Venta.id.desc())
        .all()
    )
    for v in ventas:
        ws4.append([
            v.numero_venta,
            v.fecha.isoformat(),
            v.sucursal.nombre if v.sucursal else "",
            v.cliente.nombre if v.cliente else "Cliente general",
            v.asesor.nombre if v.asesor else "Tienda",
            v.estado,
            float(v.total_promo_usd),
            float(v.total_regular_usd),
        ])

    # 5. CxC / Cashea
    ws5 = wb.create_sheet(title="CxC y Cashea")
    _preparar_hoja(
        ws5,
        ["ID", "Tipo", "Nota", "Cliente", "Monto Original USD", "Saldo Pendiente USD", "Estado"],
        [8, 12, 14, 26, 18, 20, 14],
    )
    cxcs = (
        bd.query(CuentaPorCobrar)
        .options(joinedload(CuentaPorCobrar.venta), joinedload(CuentaPorCobrar.cliente))
        .order_by(CuentaPorCobrar.id.desc())
        .all()
    )
    for c in cxcs:
        ws5.append([
            c.id,
            c.tipo,
            c.venta.numero_venta if c.venta else "",
            c.cliente.nombre if c.cliente else "Cliente general",
            float(c.monto_original_usd),
            float(c.saldo_pendiente_usd),
            c.estado,
        ])

    # 6. CxP Proveedores
    ws6 = wb.create_sheet(title="CxP Proveedores")
    _preparar_hoja(
        ws6,
        ["Compra", "Origen", "Proveedor", "Fecha", "Vencimiento", "Saldo Pendiente USD", "Estado"],
        [16, 16, 26, 14, 14, 20, 16],
    )
    compras = bd.query(Compra).options(joinedload(Compra.proveedor)).order_by(Compra.id.desc()).all()
    for cmp in compras:
        ws6.append([
            cmp.numero_compra,
            cmp.origen,
            cmp.proveedor.nombre if cmp.proveedor else "Sin proveedor",
            cmp.fecha.isoformat(),
            cmp.fecha_vencimiento.isoformat() if cmp.fecha_vencimiento else "",
            float(cmp.saldo_pendiente_usd),
            cmp.estado,
        ])

    # 7. Personal
    ws7 = wb.create_sheet(title="Personal")
    _preparar_hoja(
        ws7,
        ["ID", "Nombre", "Usuario", "Correo", "Rol", "Sucursal", "Acceso", "Activo", "Bloqueado"],
        [8, 26, 20, 28, 16, 18, 10, 10, 12],
    )
    usuarios = bd.query(Usuario).options(joinedload(Usuario.sucursal)).order_by(Usuario.id.asc()).all()
    for u in usuarios:
        ws7.append([
            u.id,
            u.nombre,
            u.username or "",
            u.correo or "",
            u.rol,
            u.sucursal.nombre if u.sucursal else "Multi-tienda",
            "SÍ" if u.tiene_acceso else "NO",
            "SÍ" if u.activo else "NO",
            "SÍ" if u.cuenta_bloqueada else "NO",
        ])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@enrutador.get("/descargar")
def descargar_respaldo_completo(
    usuario_actual: Usuario = Depends(requerir_roles(RolUsuario.ADMINISTRACION.value)),
    bd: Session = Depends(obtener_bd),
) -> StreamingResponse:
    """
    Genera en memoria un respaldo completo (.zip) con:
    - backup_completo.json (todas las tablas del esquema público + metadatos)
    - resumen_legible_tekio.xlsx (7 hojas clave para auditoría rápida)
    Exclusivo para rol ADMINISTRACION (403 para cualquier otro rol).
    """
    ahora_caracas = datetime.now(ZONA_CARACAS)
    nombre_zip = f"respaldo_tekio_{ahora_caracas.strftime('%Y-%m-%d_%H%M')}.zip"

    bind = bd.get_bind()
    insp = inspect(bind)
    nombres_tablas = sorted(insp.get_table_names())

    tablas_volcado: dict[str, list[dict[str, Any]]] = {}
    conteo_por_tabla: dict[str, int] = {}

    for tabla in nombres_tablas:
        # Evitar comillas peligrosas: nombres vienen directamente del catálogo del motor
        tabla_segura = tabla.replace('"', '""')
        filas_raw = bd.execute(text(f'SELECT * FROM "{tabla_segura}"')).mappings().all()
        filas_limpias = [
            {str(k): _serializar_valor(v) for k, v in fila.items()}
            for fila in filas_raw
        ]
        tablas_volcado[tabla] = filas_limpias
        conteo_por_tabla[tabla] = len(filas_limpias)

    payload_json = {
        "metadatos": {
            "empresa": "TEKIO ELECTRONICS 2024, C.A.",
            "rif": "J-50637518-4",
            "fecha_generacion": ahora_caracas.isoformat(),
            "zona_horaria": "America/Caracas",
            "usuario": usuario_actual.nombre,
            "usuario_rol": usuario_actual.rol,
            "total_tablas": len(nombres_tablas),
            "total_registros": sum(conteo_por_tabla.values()),
            "conteo_por_tabla": conteo_por_tabla,
        },
        "tablas": tablas_volcado,
    }
    bytes_json = json.dumps(payload_json, ensure_ascii=False, indent=2).encode("utf-8")
    bytes_xlsx = _generar_excel_resumen(bd)

    buffer_zip = io.BytesIO()
    with zipfile.ZipFile(buffer_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup_completo.json", bytes_json)
        zf.writestr("resumen_legible_tekio.xlsx", bytes_xlsx)
    bytes_zip = buffer_zip.getvalue()

    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="RESPALDO",
        accion="DESCARGA_RESPALDO",
        entidad_id=nombre_zip,
        detalle_anterior={},
        detalle_nuevo={
            "archivo": nombre_zip,
            "tamano_bytes": len(bytes_zip),
            "tamano_kb": round(len(bytes_zip) / 1024, 2),
            "total_tablas": len(nombres_tablas),
            "total_registros": sum(conteo_por_tabla.values()),
            "fecha_caracas": ahora_caracas.isoformat(),
        },
    )
    bd.commit()

    return StreamingResponse(
        io.BytesIO(bytes_zip),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_zip}"',
            "Content-Length": str(len(bytes_zip)),
        },
    )


@enrutador.get("/historial")
def listar_historial_respaldos(
    _usuario: Usuario = Depends(requerir_roles(RolUsuario.ADMINISTRACION.value)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    """Devuelve las últimas 10 descargas de respaldo registradas en auditoria_sistema."""
    eventos = (
        bd.query(AuditoriaSistema)
        .filter(AuditoriaSistema.accion == "DESCARGA_RESPALDO")
        .order_by(AuditoriaSistema.id.desc())
        .limit(10)
        .all()
    )
    salida: list[dict[str, Any]] = []
    for ev in eventos:
        try:
            det = json.loads(ev.detalle_nuevo_json or "{}")
        except Exception:
            det = {}
        fecha_iso = (
            det.get("fecha_caracas")
            or (
                ev.fecha_hora.astimezone(ZONA_CARACAS).isoformat()
                if ev.fecha_hora and ev.fecha_hora.tzinfo
                else (ev.fecha_hora.isoformat() if ev.fecha_hora else None)
            )
        )
        salida.append(
            {
                "id": ev.id,
                "archivo": det.get("archivo") or ev.entidad_id,
                "usuario": ev.usuario_nombre,
                "fecha_hora": fecha_iso,
                "tamano_kb": det.get("tamano_kb", 0),
                "total_tablas": det.get("total_tablas", 0),
                "total_registros": det.get("total_registros", 0),
            }
        )
    return salida

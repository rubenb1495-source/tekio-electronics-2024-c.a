from __future__ import annotations

import io
import secrets
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from openpyxl import load_workbook
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.base_datos import obtener_bd
from app.core.empresa import FECHA_CORTE_APERTURA as FECHA_APERTURA_OFICIAL
from app.core.permisos import Permiso, require_permiso
from app.modelos import (
    CatalogoArticulo,
    CatalogoPrecio,
    RolUsuario,
    Sucursal,
    TasaDiaria,
    TipoArticulo,
    Usuario,
)
from app.modelos_admin_finanzas import NominaEmpleado
from app.modelos_contabilidad import AsientoContable, Prestamo, PrestamoCuota, Socio
from app.modelos_finanzas import (
    CuentaPorCobrar,
    EstadoCuentaPorCobrar,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoCuentaPorCobrar,
    TipoDocumentoPago,
    TipoMovimientoPago,
)
from app.modelos_logistica import (
    Compra,
    Equipo,
    EstadoCompra,
    EstadoEquipo,
    MovimientoInventario,
    OrigenCompra,
    Tercero,
    TipoMovimientoInventario,
    TipoTercero,
)
from app.rutas.contabilidad_prestamos import (
    _calcular_balance_general,
    _calcular_pl_escalonado,
    generar_plantilla_apertura_xlsx,
)
from app.seguridad import generar_hash_clave, requerir_roles, verificar_clave
from app.servicios.apertura_plantillas import (
    PLANTILLAS_APERTURA_META,
    generar_plantilla_oficial_apertura,
    generar_zip_plantillas_apertura,
)
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.contabilidad_service import registrar_asiento
from app.servicios.reset_apertura_service import (
    FRASE_CONFIRMACION_RESET,
    ejecutar_reset_apertura,
)

enrutador = APIRouter(tags=["Apertura 01/12/2026"])

FECHA_CORTE_APERTURA = date(2026, 12, 1)


def _q2(val: Decimal | float | int | str) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_dec(val: Any, default: Decimal | None = None) -> Decimal | None:
    if val is None or str(val).strip() == "":
        return default
    limpio = str(val).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(limpio)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(val: Any, default: date | None = None) -> date | None:
    if val is None or str(val).strip() == "":
        return default
    if isinstance(val, date):
        return val
    txt = str(val).strip()[:10]
    try:
        return date.fromisoformat(txt)
    except ValueError:
        return default


def _parse_bool(val: Any, default: bool = False) -> bool:
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().upper() in ("SI", "SÍ", "S", "YES", "TRUE", "1")


def _resolver_sucursal(bd: Session, nombre_raw: str) -> Sucursal | None:
    txt = (nombre_raw or "").strip().lower()
    if not txt:
        return None
    sucursales = bd.query(Sucursal).filter(Sucursal.estado == "ACTIVA").all()
    for s in sucursales:
        if s.nombre.strip().lower() == txt:
            return s
    # Matching flexible para las 3 sedes oficiales y Administración
    if "central" in txt or "administraci" in txt:
        for s in sucursales:
            if "central" in s.nombre.lower():
                return s
    if "bazar" in txt:
        for s in sucursales:
            if "bazar" in s.nombre.lower():
                return s
    if "dep" in txt or "support" in txt or "taller" in txt:
        for s in sucursales:
            if "support" in s.nombre.lower() or "dep" in s.nombre.lower() or s.tipo == "DEPOSITO_TALLER":
                return s
    return None


def _leer_hoja_dict(ws: Any) -> list[tuple[int, dict[str, Any]]]:
    """Lee filas a partir de la fila 3 (fila 1 = encabezados, fila 2 = instrucciones)."""
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []
    encabezados = [str(c or "").strip().lower() for c in filas[0]]
    resultado: list[tuple[int, dict[str, Any]]] = []
    # Si la fila 2 parece ser una instrucción (contiene '|' o 'ej.' o 'obligatorio'), saltarla
    inicio = 2
    if len(filas) >= 2:
        texto_f2 = " ".join(str(c or "").lower() for c in filas[1])
        if "|" in texto_f2 or "ej." in texto_f2 or "obligatorio" in texto_f2 or "aaaa-mm-dd" in texto_f2:
            inicio = 3
    for idx, row in enumerate(filas[inicio - 1 :], start=inicio):
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        item = {encabezados[i]: row[i] if i < len(row) else None for i in range(len(encabezados)) if encabezados[i]}
        resultado.append((idx, item))
    return resultado


# =============================================================================
# 1. RESET A CERO PROTEGIDO (EXCLUSIVO DIRECCION + CONTRASEÑA + FRASE EXACTA)
# =============================================================================


class ResetAperturaEntrada(BaseModel):
    password: str = Field(min_length=1)
    frase_confirmacion: str = Field(min_length=1)


@enrutador.post("/api/admin/reset-apertura")
def endpoint_reset_apertura(
    datos: ResetAperturaEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(RolUsuario.DIRECCION)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    if not verificar_clave(datos.password, usuario_actual.clave_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta. Confirmación de Dirección rechazada.",
        )
    if datos.frase_confirmacion.strip() != FRASE_CONFIRMACION_RESET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Frase de confirmación inválida. Debe escribir exactamente: "{FRASE_CONFIRMACION_RESET}".',
        )
    resultado = ejecutar_reset_apertura(bd)
    registrar_auditoria(
        bd,
        usuario_actual,
        "APERTURA",
        "RESET_APERTURA_01_12",
        FECHA_APERTURA_OFICIAL,
        f"Reinicio a cero ejecutado por {usuario_actual.nombre}. Respaldo: {resultado['respaldo_previo']['nombre_archivo']}",
    )
    bd.commit()
    return resultado


# =============================================================================
# 2. ESTADO EN VIVO Y TASA BCV DE APERTURA (01/12/2026)
# =============================================================================


class TasaAperturaEntrada(BaseModel):
    tasa_bcv: Decimal = Field(gt=0)
    tasa_usdt: Decimal | None = Field(default=None, gt=0)


@enrutador.post("/api/finanzas/apertura/tasa-bcv")
def fijar_tasa_apertura(
    datos: TasaAperturaEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    tasa_usdt = datos.tasa_usdt or datos.tasa_bcv
    recargo = (
        ((tasa_usdt - datos.tasa_bcv) / datos.tasa_bcv * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if tasa_usdt > datos.tasa_bcv
        else Decimal("0.00")
    )
    existente = bd.query(TasaDiaria).filter(TasaDiaria.fecha == FECHA_CORTE_APERTURA).first()
    if existente is None:
        existente = TasaDiaria(
            fecha=FECHA_CORTE_APERTURA,
            tasa_bcv=datos.tasa_bcv,
            tasa_usdt=tasa_usdt,
            recargo_porcentaje=recargo,
        )
        bd.add(existente)
    else:
        existente.tasa_bcv = datos.tasa_bcv
        existente.tasa_usdt = tasa_usdt
        existente.recargo_porcentaje = recargo
    bd.commit()
    return {
        "fecha": FECHA_CORTE_APERTURA.isoformat(),
        "tasa_bcv": float(existente.tasa_bcv),
        "tasa_usdt": float(existente.tasa_usdt),
    }


@enrutador.get("/api/finanzas/apertura/estado")
def obtener_estado_apertura(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha == FECHA_CORTE_APERTURA).first()
    balance = _calcular_balance_general(bd, FECHA_CORTE_APERTURA)
    pl_dic = _calcular_pl_escalonado(
        bd, fecha_inicio=date(2026, 12, 1), fecha_fin=date(2026, 12, 31)
    )

    asientos_apertura = {
        a.modulo_origen
        for a in bd.query(AsientoContable)
        .filter(AsientoContable.fecha == FECHA_CORTE_APERTURA)
        .all()
    }

    pasos = [
        {
            "tipo": "saldos_cajas_bancos",
            "paso": 1,
            "titulo": PLANTILLAS_APERTURA_META["saldos_cajas_bancos"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["saldos_cajas_bancos"]["archivo"],
            "cargado": "APERTURA_CAJAS_BANCOS" in asientos_apertura
            or balance["activos"]["cajas_bancos_usd"] > 0,
        },
        {
            "tipo": "inventario_equipos",
            "paso": 2,
            "titulo": PLANTILLAS_APERTURA_META["inventario_equipos"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["inventario_equipos"]["archivo"],
            "cargado": "APERTURA_INV_EQUIPOS" in asientos_apertura
            or bd.query(Equipo).count() > 0,
        },
        {
            "tipo": "inventario_componentes",
            "paso": 3,
            "titulo": PLANTILLAS_APERTURA_META["inventario_componentes"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["inventario_componentes"]["archivo"],
            "cargado": "APERTURA_INV_COMPONENTES" in asientos_apertura
            or balance["activos"]["inventario_componentes_usd"] > 0,
        },
        {
            "tipo": "cxc_cashea",
            "paso": 4,
            "titulo": PLANTILLAS_APERTURA_META["cxc_cashea"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["cxc_cashea"]["archivo"],
            "cargado": "APERTURA_CXC_CASHEA" in asientos_apertura
            or bd.query(CuentaPorCobrar).count() > 0,
        },
        {
            "tipo": "cxp_prestamos",
            "paso": 5,
            "titulo": PLANTILLAS_APERTURA_META["cxp_prestamos"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["cxp_prestamos"]["archivo"],
            "cargado": "APERTURA_CXP_PRESTAMOS" in asientos_apertura
            or balance["pasivos"]["total_pasivos_usd"] > 0,
        },
        {
            "tipo": "personal_nomina_socios",
            "paso": 6,
            "titulo": PLANTILLAS_APERTURA_META["personal_nomina_socios"]["titulo"],
            "archivo": PLANTILLAS_APERTURA_META["personal_nomina_socios"]["archivo"],
            "cargado": bd.query(Socio).filter(Socio.activo.is_(True)).count() > 0
            and bd.query(NominaEmpleado).count() > 0,
        },
    ]

    return {
        "fecha_apertura": FECHA_CORTE_APERTURA.isoformat(),
        "tasa_bcv_apertura": float(tasa.tasa_bcv) if tasa else None,
        "tasa_usdt_apertura": float(tasa.tasa_usdt) if tasa else None,
        "pasos": pasos,
        "cuadre": {
            "cajas_bancos_usd": balance["activos"]["cajas_bancos_usd"],
            "inventario_equipos_usd": balance["activos"]["inventario_equipos_usd"],
            "inventario_componentes_usd": balance["activos"]["inventario_componentes_usd"],
            "cxc_clientes_usd": balance["activos"]["cxc_clientes_usd"],
            "cashea_por_cobrar_usd": balance["activos"]["cashea_por_cobrar_usd"],
            "total_activos_usd": balance["activos"]["total_activos_usd"],
            "cxp_proveedores_usd": balance["pasivos"]["cxp_proveedores_usd"],
            "prestamos_por_pagar_usd": balance["pasivos"]["prestamos_por_pagar_usd"],
            "total_pasivos_usd": balance["pasivos"]["total_pasivos_usd"],
            "patrimonio_capital_inicial_usd": balance["patrimonio"]["total_patrimonio_usd"],
            "varianza_usd": balance["diferencia_cuadre_usd"],
            "cuadrado": balance["cuadrado"],
            "pl_diciembre_utilidad_neta_usd": pl_dic["utilidad_neta_usd"],
            "pl_diciembre_ingresos_usd": pl_dic["ingresos_netos_usd"],
        },
    }


# =============================================================================
# 3. DESCARGA DE LAS 6 PLANILLAS EXCEL (.xlsx) Y PAQUETE COMPLETO (.zip)
# =============================================================================


@enrutador.get("/api/finanzas/apertura/plantillas/zip")
def descargar_zip_plantillas(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
) -> Response:
    contenido = generar_zip_plantillas_apertura()
    return Response(
        content=contenido,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="tekio_apertura_01_12_2026_planillas.zip"'
        },
    )


@enrutador.get("/api/finanzas/apertura/plantillas/{tipo}")
def descargar_plantilla_individual(
    tipo: str,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
) -> Response:
    if tipo in PLANTILLAS_APERTURA_META:
        contenido = generar_plantilla_oficial_apertura(tipo)
        nombre = PLANTILLAS_APERTURA_META[tipo]["archivo"]
        return Response(
            content=contenido,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
        )
    if tipo in ("saldos_iniciales", "inventario_inicial", "cxc_cxp_iniciales"):
        contenido = generar_plantilla_apertura_xlsx(tipo)
        return Response(
            content=contenido,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="tekio_apertura_{tipo}.xlsx"'},
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Tipo de plantilla inválido: {tipo}.",
    )


# =============================================================================
# 4. IMPORTACIÓN EN 2 PASOS (PREVIEW Y CONFIRMACIÓN ATÓMICA CON CONTABILIDAD)
# =============================================================================


def _validar_planilla(tipo: str, contenido: bytes, bd: Session) -> dict[str, Any]:
    if tipo not in PLANTILLAS_APERTURA_META:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de importación inválido: {tipo}.",
        )
    try:
        wb = load_workbook(io.BytesIO(contenido), data_only=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo leer el archivo .xlsx: {exc}",
        ) from exc

    filas_out: list[dict[str, Any]] = []
    errores_globales: list[str] = []

    if tipo == "saldos_cajas_bancos":
        ws = wb.active
        for nro, d in _leer_hoja_dict(ws):
            errs: list[str] = []
            suc_txt = str(d.get("sucursal") or "").strip()
            inst_txt = str(d.get("instrumento_o_cuenta") or "").strip()
            moneda = str(d.get("moneda") or "USD").strip().upper()
            saldo = _parse_dec(d.get("saldo_inicial"))
            tasa = _parse_dec(d.get("tasa_bcv_apertura"))
            if not inst_txt:
                errs.append("Falta instrumento_o_cuenta")
            if moneda not in ("USD", "BS"):
                errs.append("moneda debe ser USD o BS")
            if saldo is None or saldo < 0:
                errs.append("saldo_inicial debe ser un número >= 0")
            if moneda == "BS" and (tasa is None or tasa <= 0):
                errs.append("tasa_bcv_apertura obligatoria (> 0) para cuentas en BS")
            equiv_usd = Decimal("0.00")
            if saldo is not None and saldo >= 0:
                if moneda == "BS" and tasa and tasa > 0:
                    equiv_usd = _q2(saldo / tasa)
                else:
                    equiv_usd = _q2(saldo)
            filas_out.append(
                {
                    "fila": nro,
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"{inst_txt} ({moneda}) · {suc_txt or 'Administración'}",
                    "monto_usd": float(equiv_usd),
                    "datos": {
                        "sucursal": suc_txt,
                        "instrumento_o_cuenta": inst_txt,
                        "tipo": str(d.get("tipo") or "OTRO").strip().upper(),
                        "moneda": moneda,
                        "saldo_inicial": float(saldo or 0),
                        "tasa_bcv_apertura": float(tasa or 0),
                        "equiv_usd": float(equiv_usd),
                        "observaciones": str(d.get("observaciones") or "").strip(),
                    },
                }
            )

    elif tipo == "inventario_equipos":
        ws = wb.active
        seriales_archivo: set[str] = set()
        seriales_bd = {r[0].upper() for r in bd.query(Equipo.serial).all() if r[0]}
        for nro, d in _leer_hoja_dict(ws):
            errs = []
            suc_txt = str(d.get("sucursal") or "").strip()
            suc = _resolver_sucursal(bd, suc_txt)
            sn = str(d.get("serial") or "").strip().upper()
            modelo = " ".join(
                p for p in (str(d.get("marca") or "").strip(), str(d.get("modelo") or "").strip()) if p
            )
            estado = str(d.get("estado_actual") or "LISTO").strip().upper()
            costo = _parse_dec(d.get("costo_acumulado_usd"), Decimal("0"))
            promo = _parse_dec(d.get("precio_promo_usd"), Decimal("0"))
            es_consig = _parse_bool(d.get("es_consignacion"), False)
            if suc is None:
                errs.append(f"Sucursal no reconocida: '{suc_txt}'")
            if len(sn) < 2:
                errs.append("Serial obligatorio")
            elif sn in seriales_archivo:
                errs.append(f"Serial duplicado en el archivo: {sn}")
            elif sn in seriales_bd:
                errs.append(f"Serial ya existe en inventario: {sn}")
            seriales_archivo.add(sn)
            if estado not in ("LISTO", "POR_PREPARAR", "HOSPITAL"):
                errs.append("estado_actual debe ser LISTO, POR_PREPARAR o HOSPITAL")
            if costo is None or costo < 0:
                errs.append("costo_acumulado_usd inválido")
            config = " / ".join(
                p
                for p in (
                    str(d.get("procesador") or "").strip(),
                    str(d.get("ram") or "").strip(),
                    str(d.get("almacenamiento") or "").strip(),
                    str(d.get("pantalla") or "").strip(),
                )
                if p
            )
            filas_out.append(
                {
                    "fila": nro,
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"{sn} · {modelo or 'Equipo'} ({estado}){' [CONSIGNACIÓN]' if es_consig else ''}",
                    "monto_usd": 0.0 if es_consig else float(_q2(costo or 0)),
                    "datos": {
                        "sucursal_id": suc.id if suc else None,
                        "serial": sn,
                        "modelo": modelo or "Equipo",
                        "configuracion": config,
                        "estado_actual": estado,
                        "condicion_fisica": str(d.get("condicion_fisica") or "BUENO").strip().upper(),
                        "incluye_cargador": _parse_bool(d.get("incluye_cargador"), True),
                        "costo_acumulado_usd": float(_q2(costo or 0)),
                        "precio_promo_usd": float(_q2(promo or 0)),
                        "es_consignacion": es_consig,
                        "proveedor_consignacion": str(d.get("proveedor_consignacion") or "").strip(),
                        "observaciones": str(d.get("observaciones") or "").strip(),
                    },
                }
            )

    elif tipo == "inventario_componentes":
        ws = wb.active
        for nro, d in _leer_hoja_dict(ws):
            errs = []
            suc_txt = str(d.get("sucursal") or "").strip()
            suc = _resolver_sucursal(bd, suc_txt)
            sku = str(d.get("sku") or "").strip().upper()
            nombre = str(d.get("nombre") or "").strip()
            cant_dec = _parse_dec(d.get("cantidad_inicial"))
            costo = _parse_dec(d.get("costo_unitario_usd"), Decimal("0"))
            precio = _parse_dec(d.get("precio_venta_usd"), Decimal("0"))
            if suc is None:
                errs.append(f"Sucursal no reconocida: '{suc_txt}'")
            if not sku:
                errs.append("SKU obligatorio")
            if not nombre:
                errs.append("Nombre obligatorio")
            if cant_dec is None or int(cant_dec) <= 0:
                errs.append("cantidad_inicial debe ser entero > 0")
            if costo is None or costo < 0:
                errs.append("costo_unitario_usd inválido")
            cant = int(cant_dec) if cant_dec and cant_dec > 0 else 0
            total_linea = _q2((costo or Decimal("0")) * cant)
            filas_out.append(
                {
                    "fila": nro,
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"{sku} — {nombre} (x{cant})",
                    "monto_usd": float(total_linea),
                    "datos": {
                        "sucursal_id": suc.id if suc else None,
                        "sku": sku,
                        "nombre": nombre,
                        "categoria": str(d.get("categoria") or "REPUESTO").strip().upper(),
                        "cantidad_inicial": cant,
                        "costo_unitario_usd": float(_q2(costo or 0)),
                        "precio_venta_usd": float(_q2(precio or 0)),
                        "observaciones": str(d.get("observaciones") or "").strip(),
                    },
                }
            )

    elif tipo == "cxc_cashea":
        ws = wb.active
        for nro, d in _leer_hoja_dict(ws):
            errs = []
            tipo_cxc = str(d.get("tipo") or "").strip().upper()
            suc_txt = str(d.get("sucursal") or "").strip()
            suc = _resolver_sucursal(bd, suc_txt)
            cli_nom = str(d.get("cliente_nombre") or "").strip()
            orden_cashea = str(d.get("cashea_numero_orden") or "").strip().upper()
            monto = _parse_dec(d.get("monto_financiado_usd"))
            neto = _parse_dec(d.get("neto_esperado_usd"), monto)
            if tipo_cxc not in ("CASHEA_PENDIENTE", "CLIENTE_CXC"):
                errs.append("tipo debe ser CASHEA_PENDIENTE o CLIENTE_CXC")
            if suc is None:
                errs.append(f"Sucursal no reconocida: '{suc_txt}'")
            if not cli_nom:
                errs.append("cliente_nombre obligatorio")
            if tipo_cxc == "CASHEA_PENDIENTE" and not orden_cashea:
                errs.append("cashea_numero_orden obligatorio para CASHEA_PENDIENTE")
            if monto is None or monto <= 0:
                errs.append("monto_financiado_usd debe ser > 0")
            filas_out.append(
                {
                    "fila": nro,
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"{tipo_cxc} · {cli_nom} ({orden_cashea or d.get('nro_nota_anterior') or 'Saldo'})",
                    "monto_usd": float(_q2(monto or 0)),
                    "datos": {
                        "tipo": tipo_cxc,
                        "sucursal_id": suc.id if suc else None,
                        "cliente_nombre": cli_nom,
                        "cliente_documento": str(d.get("cliente_documento") or "").strip(),
                        "nro_nota_anterior": str(d.get("nro_nota_anterior") or "").strip(),
                        "cashea_numero_orden": orden_cashea,
                        "fecha_venta_original": (
                            _parse_date(d.get("fecha_venta_original"), FECHA_CORTE_APERTURA).isoformat()
                            if _parse_date(d.get("fecha_venta_original"), FECHA_CORTE_APERTURA)
                            else FECHA_CORTE_APERTURA.isoformat()
                        ),
                        "monto_financiado_usd": float(_q2(monto or 0)),
                        "neto_esperado_usd": float(_q2(neto or monto or 0)),
                        "fecha_vencimiento": (
                            _parse_date(d.get("fecha_vencimiento")).isoformat()
                            if _parse_date(d.get("fecha_vencimiento"))
                            else None
                        ),
                        "observaciones": str(d.get("observaciones") or "").strip(),
                    },
                }
            )

    elif tipo == "cxp_prestamos":
        ws_cxp = wb["CxP_Proveedores"] if "CxP_Proveedores" in wb.sheetnames else wb.worksheets[0]
        for nro, d in _leer_hoja_dict(ws_cxp):
            errs = []
            prov = str(d.get("proveedor") or "").strip()
            monto = _parse_dec(d.get("monto_pendiente_usd"))
            if not prov:
                errs.append("proveedor obligatorio")
            if monto is None or monto <= 0:
                errs.append("monto_pendiente_usd debe ser > 0")
            filas_out.append(
                {
                    "fila": nro,
                    "hoja": "CxP_Proveedores",
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"CxP · {prov} ({d.get('documento_o_factura') or 'S/N'})",
                    "monto_usd": float(_q2(monto or 0)),
                    "datos": {
                        "subtipo": "CXP",
                        "proveedor": prov,
                        "documento_o_factura": str(d.get("documento_o_factura") or "").strip(),
                        "concepto": str(d.get("concepto") or "").strip(),
                        "monto_pendiente_usd": float(_q2(monto or 0)),
                        "observaciones": str(d.get("observaciones") or "").strip(),
                    },
                }
            )
        if "Prestamos_Activos" in wb.sheetnames:
            ws_pr = wb["Prestamos_Activos"]
            for nro, d in _leer_hoja_dict(ws_pr):
                errs = []
                acreedor = str(d.get("acreedor") or "").strip()
                cap = _parse_dec(d.get("capital_pendiente_usd"))
                tasa = _parse_dec(d.get("tasa_interes_anual_pct"), Decimal("0"))
                cuotas = _parse_dec(d.get("cuotas_restantes"))
                if not acreedor:
                    errs.append("acreedor obligatorio")
                if cap is None or cap <= 0:
                    errs.append("capital_pendiente_usd debe ser > 0")
                if cuotas is None or int(cuotas) < 1:
                    errs.append("cuotas_restantes debe ser >= 1")
                filas_out.append(
                    {
                        "fila": nro,
                        "hoja": "Prestamos_Activos",
                        "valida": len(errs) == 0,
                        "errores": errs,
                        "resumen": f"Préstamo · {acreedor} ({int(cuotas or 0)} cuotas)",
                        "monto_usd": float(_q2(cap or 0)),
                        "datos": {
                            "subtipo": "PRESTAMO",
                            "acreedor": acreedor,
                            "capital_pendiente_usd": float(_q2(cap or 0)),
                            "tasa_interes_anual_pct": float(tasa or 0),
                            "cuotas_restantes": int(cuotas or 1),
                            "proximo_vencimiento": (
                                _parse_date(d.get("proximo_vencimiento"), date(2027, 1, 1)).isoformat()
                            ),
                            "observaciones": str(d.get("observaciones") or "").strip(),
                        },
                    }
                )

    elif tipo == "personal_nomina_socios":
        ws_per = wb["Personal"] if "Personal" in wb.sheetnames else wb.worksheets[0]
        roles_validos = {"ASESORA", "LIDER_COMERCIAL", "LIDER", "TECNICO", "ADMINISTRACION", "DIRECCION", "LOGISTICA"}
        for nro, d in _leer_hoja_dict(ws_per):
            errs = []
            nom = str(d.get("nombre") or "").strip()
            rol = str(d.get("rol") or "ASESORA").strip().upper()
            if rol == "LIDER_COMERCIAL":
                rol = RolUsuario.LIDER.value
            suc_txt = str(d.get("sucursal") or "").strip()
            suc = _resolver_sucursal(bd, suc_txt) if suc_txt else None
            sueldo = _parse_dec(d.get("sueldo_base_usd"), Decimal("0"))
            if not nom:
                errs.append("nombre obligatorio")
            if rol not in roles_validos:
                errs.append(f"rol inválido: {rol}")
            if suc_txt and suc is None:
                errs.append(f"Sucursal no reconocida: '{suc_txt}'")
            filas_out.append(
                {
                    "fila": nro,
                    "hoja": "Personal",
                    "valida": len(errs) == 0,
                    "errores": errs,
                    "resumen": f"Personal · {nom} ({rol})",
                    "monto_usd": float(_q2(sueldo or 0)),
                    "datos": {
                        "subtipo": "PERSONAL",
                        "nombre": nom,
                        "username": str(d.get("username") or "").strip().lower(),
                        "rol": rol,
                        "categoria_nomina": str(d.get("categoria_nomina") or "ASESOR").strip().upper(),
                        "sucursal_id": suc.id if suc else None,
                        "telefono": str(d.get("telefono") or "").strip(),
                        "email_opcional": str(d.get("email_opcional") or "").strip().lower(),
                        "tiene_acceso_sistema": _parse_bool(d.get("tiene_acceso_sistema"), False),
                        "sueldo_base_usd": float(_q2(sueldo or 0)),
                    },
                }
            )
        if "Socios" in wb.sheetnames:
            ws_soc = wb["Socios"]
            suma_pct = Decimal("0.00")
            for nro, d in _leer_hoja_dict(ws_soc):
                errs = []
                nom = str(d.get("nombre_socio") or "").strip()
                pct = _parse_dec(d.get("porcentaje_participacion"))
                activo = _parse_bool(d.get("activo"), True)
                if not nom:
                    errs.append("nombre_socio obligatorio")
                if pct is None or pct <= 0 or pct > 100:
                    errs.append("porcentaje_participacion debe estar entre 0 y 100")
                elif activo:
                    suma_pct += _q2(pct)
                filas_out.append(
                    {
                        "fila": nro,
                        "hoja": "Socios",
                        "valida": len(errs) == 0,
                        "errores": errs,
                        "resumen": f"Socio · {nom} ({float(pct or 0):.2f}%)",
                        "monto_usd": 0.0,
                        "datos": {
                            "subtipo": "SOCIO",
                            "nombre_socio": nom,
                            "porcentaje_participacion": float(_q2(pct or 0)),
                            "activo": activo,
                        },
                    }
                )
            if any(f["datos"]["subtipo"] == "SOCIO" and f["datos"]["activo"] for f in filas_out):
                if suma_pct != Decimal("100.00"):
                    errores_globales.append(
                        f"La suma de porcentajes de socios activos debe ser exactamente 100.00% (actual: {suma_pct}%)."
                    )

    validas = sum(1 for f in filas_out if f["valida"])
    con_errores = len(filas_out) - validas + len(errores_globales)
    total_monto = round(sum(float(f["monto_usd"]) for f in filas_out if f["valida"]), 2)
    return {
        "tipo": tipo,
        "total_filas": len(filas_out),
        "validas": validas,
        "con_errores": con_errores,
        "errores_globales": errores_globales,
        "total_monto_usd": total_monto,
        "filas": filas_out,
    }


@enrutador.post("/api/finanzas/apertura/importar/{tipo}/preview")
async def preview_importar_apertura(
    tipo: str,
    archivo: UploadFile = File(...),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    contenido = await archivo.read()
    return _validar_planilla(tipo, contenido, bd)


@enrutador.post("/api/finanzas/apertura/importar/{tipo}/confirmar", status_code=status.HTTP_201_CREATED)
async def confirmar_importar_apertura(
    tipo: str,
    archivo: UploadFile = File(...),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    contenido = await archivo.read()
    prev = _validar_planilla(tipo, contenido, bd)
    if prev["con_errores"] > 0 or prev["validas"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No se puede confirmar la carga: existen errores de validación o el archivo está vacío. "
                + "; ".join(prev["errores_globales"])
            ).strip(),
        )

    filas_validas = [f["datos"] for f in prev["filas"] if f["valida"]]
    total_asiento = Decimal("0.00")

    try:
        if tipo == "saldos_cajas_bancos":
            tasa_encontrada: Decimal | None = None
            for d in filas_validas:
                if d["tasa_bcv_apertura"] > 0:
                    tasa_encontrada = Decimal(str(d["tasa_bcv_apertura"]))
                    break
            if tasa_encontrada is not None and tasa_encontrada > 0:
                tasa_row = bd.query(TasaDiaria).filter(TasaDiaria.fecha == FECHA_CORTE_APERTURA).first()
                if tasa_row is None:
                    bd.add(
                        TasaDiaria(
                            fecha=FECHA_CORTE_APERTURA,
                            tasa_bcv=tasa_encontrada,
                            tasa_usdt=tasa_encontrada,
                            recargo_porcentaje=Decimal("0.00"),
                        )
                    )
                else:
                    tasa_row.tasa_bcv = tasa_encontrada
                    tasa_row.tasa_usdt = tasa_encontrada
                bd.flush()

            for d in filas_validas:
                nombre_inst = d["instrumento_o_cuenta"]
                inst = (
                    bd.query(InstrumentoFinanciero)
                    .filter(func.lower(InstrumentoFinanciero.nombre) == nombre_inst.lower())
                    .first()
                )
                if inst is None:
                    inst = InstrumentoFinanciero(
                        nombre=nombre_inst,
                        moneda=(
                            MonedaInstrumento.BS.value
                            if d["moneda"] == "BS"
                            else MonedaInstrumento.USD.value
                        ),
                        tipo_precio="REGULAR" if d["moneda"] == "BS" else "PROMO",
                        requiere_verificacion=False,
                        liquida_en_bs=(d["moneda"] == "BS"),
                        saldo_inicial=_q2(d["saldo_inicial"]),
                        activo=True,
                    )
                    bd.add(inst)
                    bd.flush()
                else:
                    inst.saldo_inicial = _q2(inst.saldo_inicial + Decimal(str(d["saldo_inicial"])))

                monto_orig = _q2(d["saldo_inicial"])
                equiv_usd = _q2(d["equiv_usd"])
                if monto_orig > 0:
                    tasa_uso = Decimal(str(d["tasa_bcv_apertura"] or tasa_encontrada or 1))
                    bd.add(
                        Pago(
                            venta_id=None,
                            instrumento_id=inst.id,
                            fecha=FECHA_CORTE_APERTURA,
                            tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                            tipo_documento="APERTURA",
                            monto_moneda_origen=monto_orig,
                            moneda=inst.moneda,
                            tasa_bcv_dia=tasa_uso,
                            tasa_usdt_dia=tasa_uso,
                            usd_nominal=equiv_usd,
                            usd_real=equiv_usd,
                            cubre_promo_usd=equiv_usd,
                            referencia=f"APERTURA-{FECHA_APERTURA_OFICIAL}",
                            estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                            verificado_por_id=usuario_actual.id,
                            nota=d["observaciones"] or f"Saldo inicial apertura {FECHA_APERTURA_OFICIAL}",
                        )
                    )
                    total_asiento += equiv_usd

            if total_asiento > 0:
                registrar_asiento(
                    bd,
                    fecha=FECHA_CORTE_APERTURA,
                    referencia=f"APERTURA-CAJAS-{FECHA_APERTURA_OFICIAL}",
                    modulo_origen="APERTURA_CAJAS_BANCOS",
                    entidad_id=FECHA_APERTURA_OFICIAL,
                    descripcion="Saldos iniciales de Cajas y Bancos al 01/12/2026",
                    lineas=[
                        {"codigo_cuenta": "1.1.01", "debe_usd": total_asiento, "haber_usd": Decimal("0")},
                        {"codigo_cuenta": "3.1.01", "debe_usd": Decimal("0"), "haber_usd": total_asiento},
                    ],
                    creado_por_id=usuario_actual.id,
                )

        elif tipo == "inventario_equipos":
            for d in filas_validas:
                costo = _q2(d["costo_acumulado_usd"])
                eq = Equipo(
                    serial=d["serial"],
                    modelo=d["modelo"],
                    configuracion=d["configuracion"],
                    ubicacion_id=d["sucursal_id"],
                    estado=d["estado_actual"],
                    condicion_llegada=d["condicion_fisica"],
                    incluye_cargador=bool(d["incluye_cargador"]),
                    observaciones_llegada=d["observaciones"],
                    costo_compra_usd=costo,
                    costo_flete_usd=Decimal("0.00"),
                    costo_taller_usd=Decimal("0.00"),
                    precio_promo_usd=_q2(d["precio_promo_usd"]),
                    es_consignacion=bool(d["es_consignacion"]),
                )
                bd.add(eq)
                bd.flush()
                bd.add(
                    MovimientoInventario(
                        tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                        articulo_id=None,
                        equipo_id=eq.id,
                        sucursal_id=d["sucursal_id"],
                        cantidad=1,
                        costo_unitario_usd=costo,
                        documento_ref=f"APERTURA-{FECHA_APERTURA_OFICIAL}",
                        motivo="Inventario inicial de apertura 01/12/2026",
                        usuario_id=usuario_actual.id,
                    )
                )
                if not d["es_consignacion"] and costo > 0:
                    total_asiento += costo

            if total_asiento > 0:
                registrar_asiento(
                    bd,
                    fecha=FECHA_CORTE_APERTURA,
                    referencia=f"APERTURA-EQUIPOS-{FECHA_APERTURA_OFICIAL}",
                    modulo_origen="APERTURA_INV_EQUIPOS",
                    entidad_id=FECHA_APERTURA_OFICIAL,
                    descripcion="Inventario inicial de equipos propios al 01/12/2026",
                    lineas=[
                        {"codigo_cuenta": "1.1.04", "debe_usd": total_asiento, "haber_usd": Decimal("0")},
                        {"codigo_cuenta": "3.1.01", "debe_usd": Decimal("0"), "haber_usd": total_asiento},
                    ],
                    creado_por_id=usuario_actual.id,
                )

        elif tipo == "inventario_componentes":
            for d in filas_validas:
                art = (
                    bd.query(CatalogoArticulo)
                    .filter(func.upper(CatalogoArticulo.sku) == d["sku"].upper())
                    .first()
                )
                tipo_art = (
                    TipoArticulo.ACCESORIO.value
                    if d["categoria"] == "ACCESORIO"
                    else TipoArticulo.COMPONENTE.value
                )
                if art is None:
                    art = CatalogoArticulo(
                        sku=d["sku"],
                        descripcion=d["nombre"],
                        tipo=tipo_art,
                        categoria=d["categoria"],
                        activo=True,
                    )
                    bd.add(art)
                    bd.flush()
                    bd.add(
                        CatalogoPrecio(
                            articulo_id=art.id,
                            fecha_vigencia=FECHA_CORTE_APERTURA,
                            costo_referencia_usd=_q2(d["costo_unitario_usd"]),
                            precio_promo_usd=_q2(d["precio_venta_usd"]),
                            creado_por_id=usuario_actual.id,
                        )
                    )
                costo_u = _q2(d["costo_unitario_usd"])
                cant = int(d["cantidad_inicial"])
                bd.add(
                    MovimientoInventario(
                        tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                        articulo_id=art.id,
                        equipo_id=None,
                        sucursal_id=d["sucursal_id"],
                        cantidad=cant,
                        costo_unitario_usd=costo_u,
                        documento_ref=f"APERTURA-{FECHA_APERTURA_OFICIAL}",
                        motivo=d["observaciones"] or "Stock inicial de componentes 01/12/2026",
                        usuario_id=usuario_actual.id,
                    )
                )
                total_asiento += _q2(costo_u * cant)

            if total_asiento > 0:
                registrar_asiento(
                    bd,
                    fecha=FECHA_CORTE_APERTURA,
                    referencia=f"APERTURA-COMP-{FECHA_APERTURA_OFICIAL}",
                    modulo_origen="APERTURA_INV_COMPONENTES",
                    entidad_id=FECHA_APERTURA_OFICIAL,
                    descripcion="Inventario inicial de componentes y accesorios al 01/12/2026",
                    lineas=[
                        {"codigo_cuenta": "1.1.05", "debe_usd": total_asiento, "haber_usd": Decimal("0")},
                        {"codigo_cuenta": "3.1.01", "debe_usd": Decimal("0"), "haber_usd": total_asiento},
                    ],
                    creado_por_id=usuario_actual.id,
                )

        elif tipo == "cxc_cashea":
            total_cxc = Decimal("0.00")
            total_cashea = Decimal("0.00")
            for d in filas_validas:
                cli = (
                    bd.query(Tercero)
                    .filter(func.lower(Tercero.nombre) == d["cliente_nombre"].lower())
                    .first()
                )
                if cli is None:
                    cli = Tercero(
                        nombre=d["cliente_nombre"],
                        tipo=TipoTercero.CLIENTE.value,
                        rif_cedula=d["cliente_documento"],
                        activo=True,
                    )
                    bd.add(cli)
                    bd.flush()

                monto = _q2(d["monto_financiado_usd"])
                es_cashea = d["tipo"] == "CASHEA_PENDIENTE"
                bd.add(
                    CuentaPorCobrar(
                        venta_id=None,
                        sucursal_id=d["sucursal_id"],
                        tipo=TipoCuentaPorCobrar.CASHEA.value if es_cashea else TipoCuentaPorCobrar.CLIENTE.value,
                        cliente_id=cli.id,
                        nro_nota_anterior=d["nro_nota_anterior"],
                        cashea_numero_orden=d["cashea_numero_orden"],
                        fecha_venta_original=_parse_date(d["fecha_venta_original"]),
                        fecha_vencimiento=_parse_date(d["fecha_vencimiento"]),
                        monto_original_usd=monto,
                        neto_esperado_usd=_q2(d["neto_esperado_usd"]),
                        saldo_pendiente_usd=monto,
                        observaciones=d["observaciones"],
                        estado=EstadoCuentaPorCobrar.PENDIENTE.value,
                    )
                )
                if es_cashea:
                    total_cashea += monto
                else:
                    total_cxc += monto

            total_asiento = _q2(total_cxc + total_cashea)
            if total_asiento > 0:
                lineas = []
                if total_cxc > 0:
                    lineas.append({"codigo_cuenta": "1.1.02", "debe_usd": total_cxc, "haber_usd": Decimal("0")})
                if total_cashea > 0:
                    lineas.append({"codigo_cuenta": "1.1.03", "debe_usd": total_cashea, "haber_usd": Decimal("0")})
                lineas.append({"codigo_cuenta": "3.1.01", "debe_usd": Decimal("0"), "haber_usd": total_asiento})
                registrar_asiento(
                    bd,
                    fecha=FECHA_CORTE_APERTURA,
                    referencia=f"APERTURA-CXC-{FECHA_APERTURA_OFICIAL}",
                    modulo_origen="APERTURA_CXC_CASHEA",
                    entidad_id=FECHA_APERTURA_OFICIAL,
                    descripcion="Saldos iniciales CxC y Cashea por cobrar al 01/12/2026",
                    lineas=lineas,
                    creado_por_id=usuario_actual.id,
                )

        elif tipo == "cxp_prestamos":
            total_cxp = Decimal("0.00")
            total_prest = Decimal("0.00")
            seq_cxp = bd.query(Compra).count()
            for d in filas_validas:
                if d["subtipo"] == "CXP":
                    prov = (
                        bd.query(Tercero)
                        .filter(func.lower(Tercero.nombre) == d["proveedor"].lower())
                        .first()
                    )
                    if prov is None:
                        prov = Tercero(
                            nombre=d["proveedor"],
                            tipo=TipoTercero.PROVEEDOR.value,
                            activo=True,
                        )
                        bd.add(prov)
                        bd.flush()
                    seq_cxp += 1
                    monto = _q2(d["monto_pendiente_usd"])
                    bd.add(
                        Compra(
                            numero_compra=f"CXP-AP-{seq_cxp:04d}",
                            origen=OrigenCompra.NACIONAL.value,
                            proveedor_id=prov.id,
                            fecha=FECHA_CORTE_APERTURA,
                            factura_orden=d["documento_o_factura"],
                            monto_mercancia_usd=monto,
                            saldo_pendiente_usd=monto,
                            estado=EstadoCompra.RECIBIDA.value,
                            nota=f"{d['concepto']} {d['observaciones']}".strip(),
                            creado_por_id=usuario_actual.id,
                        )
                    )
                    total_cxp += monto
                else:
                    cap = _q2(d["capital_pendiente_usd"])
                    cuotas_n = max(1, int(d["cuotas_restantes"]))
                    tasa_anual = Decimal(str(d["tasa_interes_anual_pct"] or 0))
                    prox_venc = _parse_date(d["proximo_vencimiento"], date(2027, 1, 1)) or date(2027, 1, 1)
                    pr = Prestamo(
                        acreedor=d["acreedor"],
                        monto_principal_usd=cap,
                        tasa_interes_anual_pct=tasa_anual,
                        plazo_meses=cuotas_n,
                        fecha_inicio=FECHA_CORTE_APERTURA,
                        estado="ACTIVO",
                        notas=d["observaciones"] or "Saldo inicial de apertura 01/12/2026",
                        creado_por_id=usuario_actual.id,
                    )
                    bd.add(pr)
                    bd.flush()
                    cap_cuota = _q2(cap / Decimal(cuotas_n))
                    acum = Decimal("0.00")
                    for idx_c in range(1, cuotas_n + 1):
                        c_cap = _q2(cap - acum) if idx_c == cuotas_n else cap_cuota
                        acum += c_cap
                        bd.add(
                            PrestamoCuota(
                                prestamo_id=pr.id,
                                nro_cuota=idx_c,
                                fecha_vencimiento=prox_venc + timedelta(days=30 * (idx_c - 1)),
                                capital_usd=c_cap,
                                interes_usd=Decimal("0.00"),
                                cuota_total_usd=c_cap,
                                estado="PENDIENTE",
                            )
                        )
                    total_prest += cap

            total_asiento = _q2(total_cxp + total_prest)
            if total_asiento > 0:
                lineas = [{"codigo_cuenta": "3.1.01", "debe_usd": total_asiento, "haber_usd": Decimal("0")}]
                if total_cxp > 0:
                    lineas.append({"codigo_cuenta": "2.1.01", "debe_usd": Decimal("0"), "haber_usd": total_cxp})
                if total_prest > 0:
                    lineas.append({"codigo_cuenta": "2.1.03", "debe_usd": Decimal("0"), "haber_usd": total_prest})
                registrar_asiento(
                    bd,
                    fecha=FECHA_CORTE_APERTURA,
                    referencia=f"APERTURA-PASIVOS-{FECHA_APERTURA_OFICIAL}",
                    modulo_origen="APERTURA_CXP_PRESTAMOS",
                    entidad_id=FECHA_APERTURA_OFICIAL,
                    descripcion="Saldos iniciales CxP Proveedores y Préstamos al 01/12/2026",
                    lineas=lineas,
                    creado_por_id=usuario_actual.id,
                )

        elif tipo == "personal_nomina_socios":
            for d in filas_validas:
                if d["subtipo"] == "PERSONAL":
                    u = (
                        bd.query(Usuario)
                        .filter(func.lower(Usuario.nombre) == d["nombre"].lower())
                        .first()
                    )
                    if u is None:
                        tiene_acc = bool(d["tiene_acceso_sistema"])
                        uname = d["username"] or d["nombre"].lower().replace(" ", ".")
                        if tiene_acc:
                            dup = bd.query(Usuario).filter(func.lower(Usuario.username) == uname).first()
                            if dup is not None:
                                uname = f"{uname}.{secrets.token_hex(2)}"
                        u = Usuario(
                            nombre=d["nombre"],
                            username=uname if tiene_acc else None,
                            correo=d["email_opcional"] or None,
                            clave_hash=generar_hash_clave("Tekio2026!") if tiene_acc else None,
                            rol=d["rol"],
                            sucursal_id=d["sucursal_id"],
                            telefono=d["telefono"],
                            tiene_acceso=tiene_acc,
                            activo=True,
                        )
                        bd.add(u)
                        bd.flush()
                    emp = bd.query(NominaEmpleado).filter(NominaEmpleado.usuario_id == u.id).first()
                    if emp is None:
                        bd.add(
                            NominaEmpleado(
                                usuario_id=u.id,
                                cargo=d["rol"],
                                categoria_laboral=d["categoria_nomina"],
                                sucursal_id=d["sucursal_id"],
                                fecha_ingreso=FECHA_CORTE_APERTURA,
                                salario_base_usd=_q2(d["sueldo_base_usd"]),
                                activo=True,
                            )
                        )
                    else:
                        emp.categoria_laboral = d["categoria_nomina"]
                        emp.salario_base_usd = _q2(d["sueldo_base_usd"])
                else:
                    soc = (
                        bd.query(Socio)
                        .filter(func.lower(Socio.nombre) == d["nombre_socio"].lower())
                        .first()
                    )
                    if soc is None:
                        bd.add(
                            Socio(
                                nombre=d["nombre_socio"],
                                porcentaje_participacion=_q2(d["porcentaje_participacion"]),
                                activo=bool(d["activo"]),
                            )
                        )
                    else:
                        soc.porcentaje_participacion = _q2(d["porcentaje_participacion"])
                        soc.activo = bool(d["activo"])

        registrar_auditoria(
            bd,
            usuario_actual,
            "APERTURA",
            f"IMPORTAR_{tipo.upper()}",
            FECHA_APERTURA_OFICIAL,
            f"Carga inicial '{tipo}' confirmada ({len(filas_validas)} filas, asiento USD {float(total_asiento):.2f})",
        )
        bd.commit()
    except HTTPException:
        bd.rollback()
        raise
    except Exception as exc:
        bd.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error atómico al confirmar la carga de apertura '{tipo}': {exc}",
        ) from exc

    return {
        "estado": "CONFIRMADO",
        "tipo": tipo,
        "filas_importadas": len(filas_validas),
        "monto_asiento_usd": float(_q2(total_asiento)),
        "fecha_contable": FECHA_CORTE_APERTURA.isoformat(),
    }

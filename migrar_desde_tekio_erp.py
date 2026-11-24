#!/usr/bin/env python3
"""
Script de migración histórica idempotente para Tekio Electronics.
Origen (SOLO LECTURA): ../tekio-erp/data/tekio_erp.db + ./salida_limpia/*
Destino: Base de datos SQLAlchemy de /backend-python (PostgreSQL o SQLite local).

Uso:
    python migrar_desde_tekio_erp.py --dry-run
    python migrar_desde_tekio_erp.py --aplicar
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# Permitir importar el paquete `app` desde /backend-python
RAIZ_PROYECTO = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ_PROYECTO / "backend-python"))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.base_datos import Base, SesionLocal, motor  # noqa: E402
from app.esquemas import normalizar_sku  # noqa: E402
from app.esquemas_logistica import normalizar_serial  # noqa: E402
from app.modelos import (  # noqa: E402
    CatalogoArticulo,
    CatalogoPrecio,
    OrigenTasa,
    Sucursal,
    TasaDiaria,
    TipoArticulo,
    Usuario,
)
from app.modelos_finanzas import (  # noqa: E402
    CuentaPorCobrar,
    EstadoCuentaPorCobrar,
    EstadoVenta,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    Pago,
    TipoCuentaPorCobrar,
    TipoDocumentoPago,
    TipoMovimientoPago,
    Venta,
    VentaDetalle,
)
from app.modelos_logistica import (  # noqa: E402
    Equipo,
    EstadoEquipo,
    Tercero,
    TipoTercero,
)
from app import modelos_taller as _modelos_taller  # noqa: F401, E402
from app.semilla import ejecutar_semilla  # noqa: E402
from app.semilla_finanzas import ejecutar_semilla_finanzas  # noqa: E402


RUTA_ORIGEN_DEFAULT = RAIZ_PROYECTO.parent / "tekio-erp" / "data" / "tekio_erp.db"
RUTA_CATALOGO_CSV = RAIZ_PROYECTO / "salida_limpia" / "catalogo_limpio.csv"
RUTA_MAPA_SKU_JSON = RAIZ_PROYECTO / "salida_limpia" / "mapa_equivalencias_sku.json"
RUTA_INCIDENCIAS_CSV = RAIZ_PROYECTO / "salida_limpia" / "incidencias_migracion.csv"

MAPA_INSTRUMENTOS: dict[str, str] = {
    "efectivo divisas": "Efectivo divisas",
    "efectivo usd": "Efectivo divisas",
    "zelle": "Zelle",
    "zinli": "Zinli",
    "paypal": "PayPal",
    "banesco panamá": "Banesco Panamá",
    "bancamiga (usd)": "Bancamiga (USD)",
    "binance (usdt)": "Binance (USDT)",
    "binance": "Binance (USDT)",
    "punto de venta banesco (bs)": "Punto de venta Banesco (Bs)",
    "punto de venta banesco": "Punto de venta Banesco (Bs)",
    "pago móvil mercantil (bs)": "Pago móvil Mercantil (Bs)",
    "pago móvil mercantil": "Pago móvil Mercantil (Bs)",
    "bnc jurídico (bs)": "BNC Jurídico (Bs)",
    "bnc jurídico": "BNC Jurídico (Bs)",
    "bancamiga (bs)": "Bancamiga (Bs)",
    "bancamiga pago móvil": "Bancamiga (Bs)",
    "bancamiga jurídica": "Bancamiga (Bs)",
    "cashea · financiado": "Cashea · financiado",
    "cashea": "Cashea · financiado",
    "equipo como parte de pago": "Equipo como parte de pago",
    "equipo en parte de pago": "Equipo como parte de pago",
    "cuenta por cobrar": "Cuenta por cobrar",
}


def dec(valor: Any, default: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(default)
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default)


def dec4(valor: Any, default: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(default)
    try:
        return Decimal(str(valor)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default)


def parsear_fecha(valor: Any, fallback: date | None = None) -> date:
    if valor:
        texto = str(valor).strip()[:10]
        try:
            return date.fromisoformat(texto)
        except ValueError:
            pass
    return fallback or date.today()


def normalizar_tipo_articulo(valor: str) -> str:
    txt = (valor or "").strip().lower()
    if "serv" in txt:
        return TipoArticulo.SERVICIO.value
    if "acces" in txt:
        return TipoArticulo.ACCESORIO.value
    if "equip" in txt:
        return TipoArticulo.EQUIPO.value
    return TipoArticulo.COMPONENTE.value


def mapear_estado_equipo(estado_origen: str, revision_origen: str, ubicacion_origen: str) -> str:
    ub = (ubicacion_origen or "").strip().lower()
    est = (estado_origen or "").strip().lower()
    rev = (revision_origen or "").strip().lower()

    if ub == "baja" or est == "baja" or rev == "cementerio":
        return EstadoEquipo.CEMENTERIO.value
    if est == "vendido":
        return EstadoEquipo.VENDIDO.value
    if rev == "hospital":
        return EstadoEquipo.HOSPITAL.value
    if rev in ("por revisar", "por preparar"):
        return EstadoEquipo.POR_PREPARAR.value
    return EstadoEquipo.LISTO.value


def resolver_sucursal_id(nombre: str, sucursales_map: dict[str, int], bodega_id: int) -> int:
    clave = (nombre or "").strip().lower()
    if clave == "baja":
        return bodega_id
    if clave in sucursales_map:
        return sucursales_map[clave]
    if "central" in clave:
        return sucursales_map.get("tekio central", bodega_id)
    if "bazar" in clave:
        return sucursales_map.get("gran bazar", bodega_id)
    if "infot" in clave:
        return sucursales_map.get("infot", bodega_id)
    if "c13" in clave or "free market" in clave:
        return sucursales_map.get("free market c13", bodega_id)
    return bodega_id


def conectar_origen_solo_lectura(ruta_origen: Path) -> sqlite3.Connection:
    if not ruta_origen.exists():
        raise FileNotFoundError(f"No se encontró la base de datos origen: {ruta_origen}")
    uri = f"file:{ruta_origen.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def ejecutar_migracion(ruta_origen: Path, aplicar: bool) -> None:
    modo = "APLICAR (escritura atómica)" if aplicar else "DRY-RUN (simulación sin escritura)"
    print(f"=== MIGRACIÓN HISTÓRICA TEKIO ELECTRONICS | MODO: {modo} ===\n")

    Base.metadata.create_all(bind=motor)
    con_origen = conectar_origen_solo_lectura(ruta_origen)
    mapa_equivalencias: dict[str, str] = (
        json.loads(RUTA_MAPA_SKU_JSON.read_text(encoding="utf-8"))
        if RUTA_MAPA_SKU_JSON.exists()
        else {}
    )
    incidencias: list[dict[str, str]] = []

    bd: Session = SesionLocal()
    try:
        # Asegurar semillas base (5 sucursales, usuario DIRECCION, instrumentos financieros)
        ejecutar_semilla(bd)
        ejecutar_semilla_finanzas(bd)

        # Trabajar dentro de una transacción explícita (rollback en dry-run)
        admin = bd.query(Usuario).filter(Usuario.rol == "DIRECCION").first()
        admin_id = admin.id if admin else 1

        sucursales_map = {s.nombre.strip().lower(): s.id for s in bd.query(Sucursal).all()}
        bodega_id = sucursales_map["bodega"]
        instrumentos_map = {i.nombre.strip().lower(): i for i in bd.query(InstrumentoFinanciero).all()}

        # ------------------------------------------------------------------
        # 1. CATÁLOGO LIMPIO (27 SKUs canónicos desde catalogo_limpio.csv)
        # ------------------------------------------------------------------
        skus_creados = 0
        articulos_por_sku: dict[str, CatalogoArticulo] = {
            a.sku: a for a in bd.query(CatalogoArticulo).all()
        }
        with RUTA_CATALOGO_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                sku = normalizar_sku(fila.get("sku_canonico") or fila.get("Código") or "")
                if not sku:
                    continue
                if sku in articulos_por_sku:
                    continue
                art = CatalogoArticulo(
                    sku=sku,
                    descripcion=(fila.get("Descripción") or sku).strip(),
                    tipo=normalizar_tipo_articulo(fila.get("Tipo") or ""),
                    categoria=(fila.get("Categoría") or "General").strip() or "General",
                    activo=True,
                )
                bd.add(art)
                bd.flush()

                promo = dec(fila.get("Precio promo USD"))
                reg_raw = fila.get("Precio regular USD (opcional)")
                reg_fijo = dec(reg_raw) if reg_raw not in (None, "") else None
                vigencia = parsear_fecha(fila.get("Vigente desde"), date(2026, 10, 1))
                bd.add(
                    CatalogoPrecio(
                        articulo_id=art.id,
                        precio_promo_usd=promo,
                        precio_regular_fijo_usd=reg_fijo,
                        costo_referencia_usd=None,
                        fecha_vigencia=vigencia,
                        creado_por_id=admin_id,
                    )
                )
                articulos_por_sku[sku] = art
                skus_creados += 1

        # ------------------------------------------------------------------
        # 2. TERCEROS Y TASAS HISTÓRICAS
        # ------------------------------------------------------------------
        terceros_map: dict[str, Tercero] = {
            t.nombre.strip().upper(): t for t in bd.query(Tercero).all()
        }
        terceros_creados = 0
        for r in con_origen.execute("SELECT nombre, rif, tipo, telefono FROM terceros"):
            nombre = (r["nombre"] or "").strip()
            if not nombre:
                continue
            clave = nombre.upper()
            if clave in terceros_map:
                continue
            tipo_raw = (r["tipo"] or "Cliente").strip().lower()
            tipo_t = (
                TipoTercero.PROVEEDOR.value
                if "prov" in tipo_raw
                else (TipoTercero.AMBOS.value if "ambo" in tipo_raw else TipoTercero.CLIENTE.value)
            )
            nuevo_t = Tercero(
                nombre=nombre,
                tipo=tipo_t,
                rif_cedula=(r["rif"] or "").strip(),
                telefono=(r["telefono"] or "").strip(),
                activo=True,
            )
            bd.add(nuevo_t)
            bd.flush()
            terceros_map[clave] = nuevo_t
            terceros_creados += 1

        tasas_existentes = {t.fecha for t in bd.query(TasaDiaria).all()}
        tasas_creadas = 0
        for r in con_origen.execute(
            "SELECT fecha, tasa_bcv, tasa_usdt, recargo_regular, publico, nota FROM tasas ORDER BY fecha ASC"
        ):
            f_tasa = parsear_fecha(r["fecha"])
            if f_tasa in tasas_existentes:
                continue
            rec_raw = float(r["recargo_regular"] or 0)
            rec_pct = rec_raw * 100.0 if 0 < rec_raw <= 1.0 else rec_raw
            bd.add(
                TasaDiaria(
                    fecha=f_tasa,
                    tasa_bcv=dec4(r["tasa_bcv"]),
                    tasa_usdt=dec4(r["tasa_usdt"]),
                    recargo_porcentaje=dec(rec_pct),
                    origen=OrigenTasa.MANUAL.value,
                    publicado_por_id=admin_id,
                    nota=(r["nota"] or "Migrado desde tekio_erp.db").strip(),
                )
            )
            tasas_existentes.add(f_tasa)
            tasas_creadas += 1
        bd.flush()
        tasas_por_fecha = {t.fecha: t for t in bd.query(TasaDiaria).all()}

        # ------------------------------------------------------------------
        # 3. EQUIPOS POR SERIAL (recepcion -> equipos)
        # ------------------------------------------------------------------
        equipos_por_serial: dict[str, Equipo] = {
            e.serial: e for e in bd.query(Equipo).all()
        }
        equipos_creados = 0
        for r in con_origen.execute("SELECT * FROM recepcion"):
            serial_raw = (r["serial"] or "").strip()
            if not serial_raw:
                incidencias.append(
                    {"tabla": "recepcion", "clave": str(r["id"]), "detalle": "Serial vacío omitido."}
                )
                continue
            serial = normalizar_serial(serial_raw)
            if serial in equipos_por_serial:
                continue

            sku_raw = (r["sku"] or "").strip()
            sku_eq = mapa_equivalencias.get(sku_raw, "")
            if not sku_eq and sku_raw:
                try:
                    sku_cand = normalizar_sku(sku_raw)
                    sku_eq = mapa_equivalencias.get(sku_cand, sku_cand)
                except ValueError:
                    sku_eq = ""

            articulo = articulos_por_sku.get(sku_eq)
            if sku_raw and articulo is None:
                incidencias.append(
                    {
                        "tabla": "recepcion",
                        "clave": serial,
                        "detalle": f"SKU/modelo '{sku_raw}' no está en los 27 SKUs de catálogo (migrado como modelo de equipo).",
                    }
                )

            ubicacion_id = resolver_sucursal_id(r["ubicacion"] or "", sucursales_map, bodega_id)
            estado_eq = mapear_estado_equipo(r["estado"] or "", r["revision"] or "", r["ubicacion"] or "")

            eq = Equipo(
                serial=serial,
                articulo_id=articulo.id if articulo else None,
                modelo=(r["descripcion"] or sku_raw or serial).strip()[:160],
                configuracion=(r["configuracion"] or "").strip()[:255],
                categoria="Laptop",
                ubicacion_id=ubicacion_id,
                estado=estado_eq,
                costo_compra_usd=dec(r["costo_usd"]),
                costo_flete_usd=Decimal("0"),
                costo_taller_usd=Decimal("0"),
                precio_promo_usd=dec(r["precio_promo"]),
                fecha_recepcion=parsear_fecha(r["fecha_recepcion"], date(2026, 10, 1)),
                nota=f"Grado: {r['grado'] or ''} | Migrado desde tekio_erp.db",
            )
            bd.add(eq)
            bd.flush()
            equipos_por_serial[serial] = eq
            equipos_creados += 1

        # ------------------------------------------------------------------
        # 4. VENTAS, PAGOS Y CUENTAS POR COBRAR (agrupadas por nro_venta)
        # ------------------------------------------------------------------
        ventas_existentes = {v.numero_venta for v in bd.query(Venta).all()}
        filas_ventas = list(con_origen.execute("SELECT * FROM ventas ORDER BY fecha ASC, id ASC"))
        grupos_ventas: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for fila in filas_ventas:
            nro = (fila["nro_venta"] or f"MIG-{fila['id']}").strip()
            grupos_ventas[nro].append(fila)

        ventas_creadas = 0
        detalles_creados = 0
        pagos_creados = 0
        cxc_creadas = 0

        for nro_venta, lineas in grupos_ventas.items():
            if nro_venta in ventas_existentes:
                continue
            primera = lineas[0]
            f_venta = parsear_fecha(primera["fecha"])
            suc_id = resolver_sucursal_id(primera["tienda"] or "", sucursales_map, bodega_id)

            cliente_nombre = (primera["cliente"] or "").strip()
            cliente_obj = terceros_map.get(cliente_nombre.upper())
            if cliente_nombre and cliente_obj is None:
                cliente_obj = Tercero(
                    nombre=cliente_nombre,
                    tipo=TipoTercero.CLIENTE.value,
                    rif_cedula=(primera["rif"] or "").strip(),
                    activo=True,
                )
                bd.add(cliente_obj)
                bd.flush()
                terceros_map[cliente_nombre.upper()] = cliente_obj

            tasa_ref = tasas_por_fecha.get(f_venta)
            tasa_bcv = tasa_ref.tasa_bcv if tasa_ref else Decimal("0")
            tasa_usdt = tasa_ref.tasa_usdt if tasa_ref else Decimal("0")
            recargo_pct = tasa_ref.recargo_porcentaje if tasa_ref else Decimal("30.00")

            total_promo = sum((dec(l["precio_promo_base_usd"]) for l in lineas), Decimal("0"))
            total_regular = sum((dec(l["total_usd"]) for l in lineas), Decimal("0"))
            saldo_cxc_cliente = sum(
                (dec(l["saldo_por_cobrar_usd"]) for l in lineas if int(l["es_cuenta_por_cobrar"] or 0) == 1),
                Decimal("0"),
            )
            es_anulada = all((l["estado"] or "").strip().lower() == "anulada" for l in lineas)
            if es_anulada:
                estado_v = EstadoVenta.ANULADA.value
            elif saldo_cxc_cliente > 0:
                estado_v = EstadoVenta.CON_SALDO.value
            else:
                estado_v = EstadoVenta.CUADRADA.value

            venta = Venta(
                numero_venta=nro_venta,
                sucursal_id=suc_id,
                fecha=f_venta,
                cliente_id=cliente_obj.id if cliente_obj else None,
                asesor_id=None,
                canal_visita=(primera["canal_venta"] or "Tienda").strip()[:60],
                tipo_entrega="Tienda",
                tasa_bcv_snapshot=tasa_bcv,
                tasa_usdt_snapshot=tasa_usdt,
                recargo_porcentaje_snapshot=recargo_pct,
                total_promo_usd=total_promo,
                total_regular_usd=total_regular,
                estado=estado_v,
                nota=(primera["notas"] or "").strip(),
                creado_por_id=admin_id,
            )
            bd.add(venta)
            bd.flush()
            ventas_creadas += 1

            for l in lineas:
                ser_raw = (l["serial"] or "").strip()
                ser_norm = normalizar_serial(ser_raw) if ser_raw else ""
                eq_obj = equipos_por_serial.get(ser_norm) if ser_norm else None

                sku_l = (l["sku"] or "").strip()
                sku_canon = mapa_equivalencias.get(sku_l, "")
                if not sku_canon and sku_l:
                    try:
                        c = normalizar_sku(sku_l)
                        sku_canon = mapa_equivalencias.get(c, c)
                    except ValueError:
                        sku_canon = ""
                art_obj = articulos_por_sku.get(sku_canon)

                bd.add(
                    VentaDetalle(
                        venta_id=venta.id,
                        equipo_id=eq_obj.id if eq_obj else None,
                        articulo_id=art_obj.id if art_obj else None,
                        descripcion=(l["descripcion"] or sku_l or ser_raw or "Ítem migrado")[:255],
                        cantidad=max(1, int(float(l["cantidad"] or 1))),
                        precio_promo_usd=dec(l["precio_promo_base_usd"]),
                        precio_regular_usd=dec(l["total_usd"]),
                        costo_total_snapshot_usd=dec(l["costo_usd"]),
                    )
                )
                detalles_creados += 1

                # Pago asociado a la línea
                inst_raw = (l["instrumento_pago"] or "").strip().lower()
                inst_canon = MAPA_INSTRUMENTOS.get(inst_raw)
                inst_obj = instrumentos_map.get(inst_canon.lower()) if inst_canon else None
                monto_linea = dec(l["total_usd"])
                if inst_obj is not None and monto_linea > 0 and not es_anulada:
                    bd.add(
                        Pago(
                            venta_id=venta.id,
                            instrumento_id=inst_obj.id,
                            fecha=f_venta,
                            tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                            tipo_documento=TipoDocumentoPago.VENTA.value,
                            monto_moneda_origen=monto_linea,
                            moneda=inst_obj.moneda,
                            tasa_bcv_dia=tasa_bcv,
                            tasa_usdt_dia=tasa_usdt,
                            usd_nominal=monto_linea,
                            usd_real=monto_linea,
                            cubre_promo_usd=dec(l["precio_promo_base_usd"]),
                            referencia=(l["nro_documento"] or "").strip(),
                            estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                        )
                    )
                    pagos_creados += 1

                # Cuenta por cobrar Cashea (por línea si es_cashea == 1)
                if int(l["es_cashea"] or 0) == 1 and not es_anulada:
                    monto_cashea = dec(l["monto_cashea_usd"])
                    est_cashea = (l["estado_cashea"] or "").strip().lower()
                    es_pagada = est_cashea == "cobrado"
                    if monto_cashea > 0:
                        bd.add(
                            CuentaPorCobrar(
                                venta_id=venta.id,
                                tipo=TipoCuentaPorCobrar.CASHEA.value,
                                cliente_id=cliente_obj.id if cliente_obj else None,
                                monto_original_usd=monto_cashea,
                                saldo_pendiente_usd=Decimal("0") if es_pagada else monto_cashea,
                                estado=(
                                    EstadoCuentaPorCobrar.PAGADA.value
                                    if es_pagada
                                    else EstadoCuentaPorCobrar.PENDIENTE.value
                                ),
                            )
                        )
                        cxc_creadas += 1

            # Cuenta por cobrar Cliente (consolidada por venta)
            if saldo_cxc_cliente > 0 and not es_anulada:
                bd.add(
                    CuentaPorCobrar(
                        venta_id=venta.id,
                        tipo=TipoCuentaPorCobrar.CLIENTE.value,
                        cliente_id=cliente_obj.id if cliente_obj else None,
                        monto_original_usd=saldo_cxc_cliente,
                        saldo_pendiente_usd=saldo_cxc_cliente,
                        estado=EstadoCuentaPorCobrar.PENDIENTE.value,
                    )
                )
                cxc_creadas += 1

        bd.flush()

        # ------------------------------------------------------------------
        # 5. VALIDACIÓN DE CUADRE ORIGEN VS DESTINO
        # ------------------------------------------------------------------
        origen_skus = 27
        destino_skus = bd.query(func.count(CatalogoArticulo.id)).filter(CatalogoArticulo.activo.is_(True)).scalar() or 0

        origen_eq_estados: dict[str, int] = defaultdict(int)
        for r in con_origen.execute("SELECT estado, revision, ubicacion FROM recepcion"):
            est_m = mapear_estado_equipo(r["estado"] or "", r["revision"] or "", r["ubicacion"] or "")
            origen_eq_estados[est_m] += 1

        destino_eq_estados = dict(
            bd.query(Equipo.estado, func.count(Equipo.id)).group_by(Equipo.estado).all()
        )

        origen_ventas_promo = dec(
            con_origen.execute("SELECT COALESCE(SUM(precio_promo_base_usd), 0) FROM ventas WHERE estado != 'Anulada'").fetchone()[0]
        )
        destino_ventas_promo = dec(
            bd.query(func.coalesce(func.sum(Venta.total_promo_usd), 0))
            .filter(Venta.estado != EstadoVenta.ANULADA.value)
            .scalar()
        )

        origen_cxc_cli = dec(
            con_origen.execute(
                "SELECT COALESCE(SUM(saldo_por_cobrar_usd), 0) FROM ventas WHERE es_cuenta_por_cobrar = 1 AND estado != 'Anulada'"
            ).fetchone()[0]
        )
        destino_cxc_cli = dec(
            bd.query(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente_usd), 0))
            .filter(
                CuentaPorCobrar.tipo == TipoCuentaPorCobrar.CLIENTE.value,
                CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            )
            .scalar()
        )

        origen_cxc_cashea = dec(
            con_origen.execute(
                "SELECT COALESCE(SUM(monto_cashea_usd), 0) FROM ventas WHERE es_cashea = 1 AND estado_cashea = 'Por cobrar' AND estado != 'Anulada'"
            ).fetchone()[0]
        )
        destino_cxc_cashea = dec(
            bd.query(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente_usd), 0))
            .filter(
                CuentaPorCobrar.tipo == TipoCuentaPorCobrar.CASHEA.value,
                CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            )
            .scalar()
        )

        # Guardar reporte de incidencias
        RUTA_INCIDENCIAS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with RUTA_INCIDENCIAS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["tabla", "clave", "detalle"])
            writer.writeheader()
            writer.writerows(incidencias)

        print("Registros a insertar en esta ejecución:")
        print(f"  - SKUs catálogo:   {skus_creados}")
        print(f"  - Terceros:        {terceros_creados}")
        print(f"  - Tasas diarias:   {tasas_creadas}")
        print(f"  - Equipos serial:  {equipos_creados}")
        print(f"  - Ventas cabecera: {ventas_creadas} ({detalles_creados} líneas detalle)")
        print(f"  - Pagos:           {pagos_creados}")
        print(f"  - Cuentas x Cobr.: {cxc_creadas}")
        print(f"  - Incidencias SKU: {len(incidencias)} (ver {RUTA_INCIDENCIAS_CSV.name})\n")

        print("=== TABLA COMPARATIVA DE CUADRE (ORIGEN vs DESTINO) ===")
        print(f"{'Métrica':38s} | {'Origen':>14s} | {'Destino':>14s} | {'Estado':>8s}")
        print("-" * 83)

        def fila_cuadre(nombre: str, val_o: Any, val_d: Any, es_usd: bool = False) -> None:
            ok = "OK" if val_o == val_d else "DIF"
            s_o = f"${float(val_o):,.2f}" if es_usd else str(val_o)
            s_d = f"${float(val_d):,.2f}" if es_usd else str(val_d)
            print(f"{nombre:38s} | {s_o:>14s} | {s_d:>14s} | {ok:>8s}")

        fila_cuadre("SKUs activos (Catálogo limpio)", origen_skus, destino_skus)
        for est in ("LISTO", "VENDIDO", "POR_PREPARAR", "HOSPITAL", "CEMENTERIO"):
            fila_cuadre(f"Equipos estado {est}", origen_eq_estados.get(est, 0), destino_eq_estados.get(est, 0))
        fila_cuadre("Ventas totales Precio Promo USD", origen_ventas_promo, destino_ventas_promo, es_usd=True)
        fila_cuadre("CxC Clientes pendientes USD", origen_cxc_cli, destino_cxc_cli, es_usd=True)
        fila_cuadre("CxC Cashea pendientes USD", origen_cxc_cashea, destino_cxc_cashea, es_usd=True)

        if aplicar:
            bd.commit()
            print("\n[APLICADO] Transacción confirmada exitosamente en la base de datos destino.")
        else:
            bd.rollback()
            print("\n[DRY-RUN] Simulación completada y revertida (ningún dato fue escrito en destino).")
    except Exception:
        bd.rollback()
        raise
    finally:
        bd.close()
        con_origen.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migración histórica desde tekio_erp.db")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--dry-run", action="store_true", help="Simula la migración sin escribir en destino")
    grupo.add_argument("--aplicar", action="store_true", help="Aplica la migración en una transacción atómica")
    parser.add_argument("--origen", default=str(RUTA_ORIGEN_DEFAULT), help="Ruta a tekio_erp.db (solo lectura)")
    args = parser.parse_args()

    ejecutar_migracion(Path(args.origen), aplicar=args.aplicar)


if __name__ == "__main__":
    main()

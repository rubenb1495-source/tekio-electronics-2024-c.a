from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.modelos_finanzas import Pago  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _extraer_texto_pdf,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_logistica_5_flujos_prorrateo_consignacion_traslado_mixto_estado_y_masiva(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # Crear proveedor
    r_prov = cliente.post(
        "/api/logistica/terceros",
        headers=cab_dir,
        json={"nombre": "Miami Tech Global", "tipo": "PROVEEDOR", "rif_cedula": "J-999999"},
    )
    assert r_prov.status_code == 201, r_prov.text
    prov_id = r_prov.json()["id"]

    # 1. Compra INTERNACIONAL con prorrateo automático de flete ($60) + aduana ($40) = $100
    r_int = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "INTERNACIONAL",
            "tipo_compra": "INTERNACIONAL",
            "moneda": "USD",
            "proveedor_id": prov_id,
            "fecha": hoy_str,
            "numero_guia": "GUIA-INT-01",
            "monto_mercancia_usd": 500.0,
            "envio_usd": 60.0,
            "aduana_usd": 40.0,
            "equipos": [
                {
                    "serial": "SN-INT-A1",
                    "articulo_id": ctx["art_base_id"],
                    "modelo": "HP 840",
                    "costo_compra_usd": 200.0,
                    "precio_promo_usd": 420.0,
                },
                {
                    "serial": "SN-INT-A2",
                    "articulo_id": ctx["art_pro_id"],
                    "modelo": "Dell 5420",
                    "costo_compra_usd": 300.0,
                    "precio_promo_usd": 620.0,
                },
            ],
        },
    )
    assert r_int.status_code == 201, r_int.text

    eq_a1 = cliente.get("/api/logistica/inventario/equipos?busqueda=SN-INT-A1", headers=cab_dir).json()[0]
    eq_a2 = cliente.get("/api/logistica/inventario/equipos?busqueda=SN-INT-A2", headers=cab_dir).json()[0]
    assert eq_a1["costo_flete_usd"] == 40.0
    assert eq_a1["costo_total_usd"] == 240.0
    assert eq_a2["costo_flete_usd"] == 60.0
    assert eq_a2["costo_total_usd"] == 360.0

    # 2. Ingreso en CONSIGNACION y venta en POS sin afectar costo propio
    r_cons = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "CONSIGNACION",
            "es_consignacion": True,
            "proveedor_id": prov_id,
            "fecha": hoy_str,
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "SN-CONS-01",
                    "articulo_id": ctx["art_base_id"],
                    "modelo": "Lenovo Consignada",
                    "ubicacion_id": 1,
                    "precio_promo_usd": 500.0,
                }
            ],
        },
    )
    assert r_cons.status_code == 201, r_cons.text
    eq_cons = cliente.get("/api/logistica/inventario/equipos?busqueda=SN-CONS-01", headers=cab_dir).json()[0]
    assert eq_cons["es_consignacion"] is True
    assert eq_cons["proveedor_consignacion_id"] == prov_id
    assert eq_cons["costo_total_usd"] == 0.0

    r_venta_cons = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "items": [{"equipo_id": eq_cons["id"], "cantidad": 1}],
            "pagos": [
                {
                    "instrumento_id": ctx["inst_usd_id"],
                    "monto_moneda_origen": 500.0,
                    "referencia": "CONS-PAY-1",
                }
            ],
        },
    )
    assert r_venta_cons.status_code == 201, r_venta_cons.text
    assert r_venta_cons.json()["detalles"][0]["costo_total_snapshot_usd"] == 0.0

    # 3. Cambio de estado masivo (POR_PREPARAR -> LISTO)
    r_mas = cliente.post(
        "/api/logistica/equipos/estado-masivo",
        headers=cab_dir,
        json={
            "equipo_ids": [eq_a1["id"], eq_a2["id"]],
            "nuevo_estado": "LISTO",
            "motivo": "Lote revisado en taller",
        },
    )
    assert r_mas.status_code == 200, r_mas.text
    assert r_mas.json()["actualizados"] == 2
    assert (
        cliente.get("/api/logistica/inventario/equipos?busqueda=SN-INT-A1", headers=cab_dir).json()[0]["estado"]
        == "LISTO"
    )

    # 4. Traslado Universal mixto (1 equipo con serial + 2 unidades de componente por SKU)
    r_art_comp = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "ACC-CARG-65W",
            "descripcion": "Cargador USB-C 65W",
            "tipo": "ACCESORIO",
            "categoria": "Accesorios",
            "precio_promo_usd": 25.0,
            "costo_referencia_usd": 12.0,
        },
    )
    assert r_art_comp.status_code == 201, r_art_comp.text
    art_comp_id = r_art_comp.json()["id"]

    r_comp_stock = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "componentes": [
                {
                    "articulo_id": art_comp_id,
                    "cantidad": 5,
                    "costo_unitario_usd": 12.0,
                    "ubicacion_id": eq_a1["ubicacion_id"],
                }
            ],
        },
    )
    assert r_comp_stock.status_code == 201, r_comp_stock.text

    dest_id = 2 if eq_a1["ubicacion_id"] != 2 else 1
    r_trs = cliente.post(
        "/api/logistica/traslados",
        headers=cab_dir,
        json={
            "origen_id": eq_a1["ubicacion_id"],
            "destino_id": dest_id,
            "equipos_ids": [eq_a1["id"]],
            "componentes": [{"articulo_id": art_comp_id, "cantidad": 2}],
            "nota": "Traslado mixto prueba",
        },
    )
    assert r_trs.status_code == 201, r_trs.text
    trs_id = r_trs.json()["id"]

    r_conf = cliente.post(
        f"/api/logistica/traslados/{trs_id}/confirmar",
        headers=cab_dir,
        json={"nota_recepcion": "Recibido completo"},
    )
    assert r_conf.status_code == 200, r_conf.text
    eq_a1_post = cliente.get("/api/logistica/inventario/equipos?busqueda=SN-INT-A1", headers=cab_dir).json()[0]
    assert eq_a1_post["ubicacion_id"] == dest_id
    assert eq_a1_post["estado"] == "LISTO"

    # 5. Plantillas .xlsx para los 5 flujos + Preview y Confirmación Atómica CSV
    for flujo in (
        "compras_nacionales",
        "compras_internacionales",
        "consignacion",
        "traslados_universales",
        "cambio_estado",
    ):
        r_pl = cliente.get(f"/api/logistica/plantillas/{flujo}", headers=cab_dir)
        assert r_pl.status_code == 200
        assert r_pl.content.startswith(b"PK")

    # CSV con 1 fila válida y 1 fila inválida (serial duplicado SN-INT-A1) -> rollback completo
    csv_invalido = (
        "serial,sku,modelo,configuracion,categoria,sucursal,costo_compra_usd,precio_promo_usd,proveedor,factura_orden,llega_preparada,nota\n"
        "SN-CSV-OK1,,Laptop CSV OK,i5/8GB,Laptop,Depósito / Tekio Support (Taller),200,350,Prov CSV,F-1,SI,ok\n"
        "SN-INT-A1,,Duplicada,i5/8GB,Laptop,Depósito / Tekio Support (Taller),200,350,Prov CSV,F-1,SI,dup\n"
    ).encode("utf-8")

    r_prev_bad = cliente.post(
        "/api/logistica/importar/preview",
        headers=cab_dir,
        data={"flujo": "compras_nacionales"},
        files={"archivo": ("lote_bad.csv", csv_invalido, "text/csv")},
    )
    assert r_prev_bad.status_code == 200, r_prev_bad.text
    assert r_prev_bad.json()["puede_confirmar"] is False
    assert r_prev_bad.json()["filas_con_error"] == 1

    r_conf_bad = cliente.post(
        "/api/logistica/importar/confirmar",
        headers=cab_dir,
        data={"flujo": "compras_nacionales"},
        files={"archivo": ("lote_bad.csv", csv_invalido, "text/csv")},
    )
    assert r_conf_bad.status_code == 400
    # Confirmar que SN-CSV-OK1 NO se guardó (atomicidad)
    assert cliente.get("/api/logistica/inventario/equipos?busqueda=SN-CSV-OK1", headers=cab_dir).json() == []

    # CSV válido -> preview OK + confirmar OK
    csv_valido = (
        "serial,sku,modelo,configuracion,categoria,sucursal,costo_compra_usd,precio_promo_usd,proveedor,factura_orden,llega_preparada,nota\n"
        "SN-CSV-OK1,,Laptop CSV OK,i5/8GB,Laptop,Depósito / Tekio Support (Taller),200,350,Prov CSV,F-1,SI,ok\n"
        "SN-CSV-OK2,,Laptop CSV OK 2,i7/16GB,Laptop,Depósito / Tekio Support (Taller),300,500,Prov CSV,F-1,NO,ok\n"
    ).encode("utf-8")

    r_prev_ok = cliente.post(
        "/api/logistica/importar/preview",
        headers=cab_dir,
        data={"flujo": "compras_nacionales"},
        files={"archivo": ("lote_ok.csv", csv_valido, "text/csv")},
    )
    assert r_prev_ok.status_code == 200
    assert r_prev_ok.json()["puede_confirmar"] is True

    r_conf_ok = cliente.post(
        "/api/logistica/importar/confirmar",
        headers=cab_dir,
        data={"flujo": "compras_nacionales"},
        files={"archivo": ("lote_ok.csv", csv_valido, "text/csv")},
    )
    assert r_conf_ok.status_code == 201, r_conf_ok.text
    assert r_conf_ok.json()["procesados"] == 2
    assert len(cliente.get("/api/logistica/inventario/equipos?busqueda=SN-CSV-OK", headers=cab_dir).json()) == 2


def test_cierre_diario_ampliado_y_anulacion_liquidacion_comisiones(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # Crear Encargado en Sucursal 1
    r_enc = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Andrea Encargada",
            "correo": "andrea.enc@tekio.com",
            "clave": "Password123!",
            "rol": "ENCARGADO",
            "sucursal_id": 1,
        },
    )
    assert r_enc.status_code == 201

    # Crear caso de garantía (GT) hoy en Sucursal 1
    r_caso = cliente.post(
        "/api/taller/casos",
        headers=cab_dir,
        json={
            "tipo": "GARANTIA",
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "serial_o_codigo": "SN-GT-01",
            "descripcion_equipo": "Laptop HP",
            "falla_reportada": "Teclado con falla",
        },
    )
    assert r_caso.status_code == 201, r_caso.text

    # Emitir venta en Sucursal 1 con la asesora
    r_venta = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [
                {
                    "instrumento_id": ctx["inst_usd_id"],
                    "monto_moneda_origen": 400.0,
                    "referencia": "EFE-CIERRE-1",
                }
            ],
        },
    )
    assert r_venta.status_code == 201, r_venta.text

    # 1. Liquidar comisiones de la asesora
    r_liq = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": ctx["inst_usd_id"],
            "referencia": "LIQ-TEST-1",
        },
    )
    assert r_liq.status_code == 201, r_liq.text
    liq_data = r_liq.json()
    liq_id = liq_data["id"]
    pago_egreso_id = liq_data["pago_egreso_id"]
    assert liq_data["estado"] == "ACTIVA"

    # Reintentar liquidar mientras está ACTIVA -> 409 Conflict
    r_dup = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": ctx["inst_usd_id"],
            "referencia": "LIQ-TEST-DUP",
        },
    )
    assert r_dup.status_code == 409

    # 2. Cierre Diario Ampliado (excluyendo LIQUIDACION_COMISION)
    r_prev = cliente.get(f"/api/finanzas/cierre-caja/preview?fecha={hoy_str}&sucursal_id=1", headers=cab_dir)
    assert r_prev.status_code == 200, r_prev.text
    prev = r_prev.json()
    assert prev["lider_encargado"] == "Andrea Encargada"
    assert prev["tasas_dia"]["tasa_bcv"] > 0
    assert prev["total_egresos_usd"] == 0.0  # LIQUIDACION_COMISION excluida
    assert prev["inventario"]["unidades_vendidas_dia"] == 1
    assert prev["inventario"]["stock_disponible_listo"] >= 1
    assert prev["taller"]["recibidos_dia"] == 1
    assert prev["taller"]["gt_pendientes"] == 1

    r_cierre = cliente.post(
        "/api/finanzas/cierre-caja",
        headers=cab_dir,
        json={"fecha": hoy_str, "sucursal_id": 1, "efectivo_declarado_usd": 400.0},
    )
    assert r_cierre.status_code == 201, r_cierre.text
    cierre_id = r_cierre.json()["id"]
    r_pdf = cliente.get(f"/api/finanzas/cierre-caja/{cierre_id}/pdf", headers=cab_dir)
    assert r_pdf.status_code == 200
    texto_pdf = _extraer_texto_pdf(r_pdf.content)
    assert "Andrea Encargada" in texto_pdf
    assert "Taller y Garant" in texto_pdf

    # 3. Anular liquidación -> revierte egreso y libera comisiones a PENDIENTE
    r_anular = cliente.post(
        f"/api/finanzas/liquidaciones/{liq_id}/anular",
        headers=cab_dir,
        json={"motivo_anulacion": "Error en instrumento de pago"},
    )
    assert r_anular.status_code == 200, r_anular.text
    anulada = r_anular.json()
    assert anulada["estado"] == "ANULADA"
    assert anulada["motivo_anulacion"] == "Error en instrumento de pago"

    # Verificar que el pago de egreso quedó marcado anulado=True en BD
    gen_bd = app.dependency_overrides[obtener_bd]()
    bd = next(gen_bd)
    try:
        pago_db = bd.query(Pago).filter(Pago.id == pago_egreso_id).first()
        assert pago_db is not None
        assert pago_db.anulado is True
    finally:
        bd.close()

    # Verificar que la comisión volvió a PENDIENTE y se puede volver a liquidar sin 409
    r_com_pend = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}&usuario_id={ctx['asesora_id']}&estado=PENDIENTE",
        headers=cab_dir,
    )
    assert r_com_pend.status_code == 200
    assert len(r_com_pend.json()["comisiones"]) == 1

    r_re_liq = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": ctx["inst_usd_id"],
            "referencia": "LIQ-TEST-CORREGIDA",
        },
    )
    assert r_re_liq.status_code == 201, r_re_liq.text

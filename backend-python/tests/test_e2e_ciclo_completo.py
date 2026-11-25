from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.modelos_logistica import Equipo  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _contiene_claves_costo(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "costo" in str(k).lower():
                return True
            if _contiene_claves_costo(v):
                return True
    elif isinstance(obj, list):
        return any(_contiene_claves_costo(x) for x in obj)
    return False


def test_e2e_ciclo_completo_ingreso_preparacion_venta_y_estados_financieros(
    cliente: TestClient,
) -> None:
    """
    Escenario E2E completo de principio a fin:
    1. ADMINISTRACION: Ingresa laptop ($120, POR_PREPARAR) + componente RAM ($20) sin 422 y con asiento de compra.
    2. TECNICO: Instala RAM ($20) -> stock -1, sin exposición de costos, costo_total_usd = $140 + asiento reclasificación,
       cambia estado POR_PREPARAR -> LISTO con registro en auditoria_sistema.
    3. ASESORA: Confirma tasa/recargo y vende laptop en POS ($250 Promo) -> VENDIDO, PDF Nota de Entrega OK,
       asientos automáticos de Ingreso ($250) y Costo de Ventas ($140).
    4. DIRECCION: Verifica comisiones (1% asesora = $2.50, 0.5% líder = $1.25), margen neto real ($106.25),
       P&L Escalonado y Balance General cuadrado exacto al centavo (Activo == Pasivo + Patrimonio).
    """
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy = obtener_fecha_hoy()
    hoy_str = hoy.isoformat()

    # Crear usuarios reales para los roles ADMINISTRACION, TECNICO y LIDER
    for payload_usr in (
        {
            "nombre": "Ana Administración E2E",
            "correo": "ana.admin.e2e@tekio.com",
            "clave": "Password123!",
            "rol": "ADMINISTRACION",
            "sucursal_id": 1,
        },
        {
            "nombre": "Pedro Técnico E2E",
            "correo": "pedro.tec.e2e@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
        {
            "nombre": "Laura Líder E2E",
            "correo": "laura.lider.e2e@tekio.com",
            "clave": "Password123!",
            "rol": "LIDER",
            "sucursal_id": 1,
        },
    ):
        r_u = cliente.post("/api/usuarios", headers=cab_dir, json=payload_usr)
        assert r_u.status_code == 201, r_u.text

    cab_adm = _login(cliente, "ana.admin.e2e@tekio.com", "Password123!")
    cab_tec = _login(cliente, "pedro.tec.e2e@tekio.com", "Password123!")

    # =========================================================================
    # PASO 1: INGRESO DE INVENTARIO (como ADMINISTRACION)
    # =========================================================================
    r_art = cliente.post(
        "/api/catalogo",
        headers=cab_adm,
        json={
            "sku": "RAM-8GB-DDR4-E2E",
            "descripcion": "Memoria RAM 8GB DDR4",
            "tipo": "COMPONENTE",
            "categoria": "Memoria",
            "precio_promo_usd": 35,
            "costo_referencia_usd": 20,
        },
    )
    assert r_art.status_code == 201, r_art.text
    ram_id = r_art.json()["id"]

    # Envío con strings vacíos "" en campos opcionales para validar blindaje anti-422
    r_compra = cliente.post(
        "/api/logistica/compras",
        headers=cab_adm,
        json={
            "origen": "NACIONAL",
            "tipo_compra": "",
            "proveedor_id": "",
            "fecha": hoy_str,
            "fecha_vencimiento": "",
            "saldo_pendiente_usd": "",
            "factura_orden": "FAC-E2E-001",
            "numero_guia": "",
            "monto_mercancia_usd": 140,
            "envio_usd": "",
            "aduana_usd": "",
            "otros_gastos_usd": "",
            "llega_preparada": False,
            "nota": "",
            "equipos": [
                {
                    "serial": "E2E-LAPTOP-001",
                    "articulo_id": "",
                    "modelo": "Dell Latitude 7420",
                    "configuracion": "Core i5 / 8GB / 256GB",
                    "ubicacion_id": 1,
                    "estado": "POR_PREPARAR",
                    "costo_compra_usd": 120,
                    "precio_promo_usd": 250,
                    "nota": "",
                }
            ],
            "componentes": [
                {
                    "articulo_id": ram_id,
                    "cantidad": 1,
                    "costo_unitario_usd": 20,
                    "ubicacion_id": 1,
                }
            ],
        },
    )
    assert r_compra.status_code == 201, r_compra.text
    compra_data = r_compra.json()
    assert compra_data["total_equipos"] == 1
    assert compra_data["total_componentes"] == 1

    # Verificar existencia en inventario y kardex
    inv_adm = cliente.get("/api/logistica/inventario/equipos", headers=cab_adm).json()
    laptop = next(e for e in inv_adm if e["serial"] == "E2E-LAPTOP-001")
    laptop_id = laptop["id"]
    assert laptop["estado"] == "POR_PREPARAR"
    assert laptop["costo_total_usd"] == 120.0

    kardex_antes = cliente.get("/api/logistica/inventario/kardex", headers=cab_adm).json()
    saldo_ram_antes = sum(
        s["stock_actual"] for s in kardex_antes["saldos"] if s["articulo_id"] == ram_id
    )
    assert saldo_ram_antes == 1

    # Verificar asiento contable de compra ($140 cuadrado)
    asientos_compra = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=COMPRAS", headers=cab_adm
    ).json()
    asiento_c = next(
        a for a in asientos_compra if a["referencia"] == compra_data["numero_compra"]
    )
    assert asiento_c["cuadrado"] is True
    assert asiento_c["total_debe_usd"] == 140.0
    assert asiento_c["total_haber_usd"] == 140.0

    # =========================================================================
    # PASO 2: PREPARACIÓN CON COMPONENTES Y CAMBIO DE ESTADO (como TECNICO)
    # =========================================================================
    r_inst = cliente.post(
        f"/api/taller/preparaciones/{laptop_id}/componentes",
        headers=cab_tec,
        json={"articulo_id": ram_id, "cantidad": 1, "nota": "Upgrade RAM a 16GB"},
    )
    assert r_inst.status_code == 201, r_inst.text
    resp_tec = r_inst.json()
    assert not _contiene_claves_costo(resp_tec), f"Fuga de costos a TECNICO: {resp_tec}"
    assert "Memoria RAM 8GB DDR4" in resp_tec["configuracion_actualizada"]

    # Verificar stock del componente disminuyó en 1 (1 -> 0)
    kardex_despues = cliente.get("/api/logistica/inventario/kardex", headers=cab_adm).json()
    saldo_ram_despues = sum(
        s["stock_actual"] for s in kardex_despues["saldos"] if s["articulo_id"] == ram_id
    )
    assert saldo_ram_despues == 0

    # Verificar directamente en BD que costo_total_usd pasó a $140.00
    override_bd = app.dependency_overrides[obtener_bd]
    gen_bd = override_bd()
    bd = next(gen_bd)
    try:
        eq_db = bd.query(Equipo).filter(Equipo.id == laptop_id).first()
        assert eq_db is not None
        costo_total_bd = float(eq_db.costo_compra_usd + eq_db.costo_flete_usd + eq_db.costo_taller_usd)
        assert costo_total_bd == 140.0
    finally:
        try:
            next(gen_bd)
        except StopIteration:
            pass

    # Verificar asiento de reclasificación (Debe 1.1.04 $20 / Haber 1.1.05 $20)
    asientos_taller = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=TALLER_COMPONENTES", headers=cab_adm
    ).json()
    asiento_comp = next(
        a for a in asientos_taller if "E2E-LAPTOP-001" in a["referencia"]
    )
    assert asiento_comp["cuadrado"] is True
    assert asiento_comp["total_debe_usd"] == 20.0
    assert any(l["cuenta_codigo"] == "1.1.04" and l["debe_usd"] == 20.0 for l in asiento_comp["lineas"])
    assert any(l["cuenta_codigo"] == "1.1.05" and l["haber_usd"] == 20.0 for l in asiento_comp["lineas"])

    # Técnico cambia estado POR_PREPARAR -> LISTO
    r_est = cliente.patch(
        f"/api/inventario/equipos/{laptop_id}/estado",
        headers=cab_tec,
        json={"nuevo_estado": "LISTO", "motivo": "Pruebas técnicas aprobadas"},
    )
    assert r_est.status_code == 200, r_est.text
    assert r_est.json()["nuevo_estado"] == "LISTO"

    # Verificar registro en auditoria_sistema
    aud_inv = cliente.get(
        "/api/finanzas/auditoria?modulo=INVENTARIO", headers=cab_dir
    ).json()
    assert any(
        ev["accion"] == "CAMBIAR_ESTADO_EQUIPO" and ev["entidad_id"] == "E2E-LAPTOP-001"
        for ev in aud_inv
    )

    # =========================================================================
    # PASO 3: VENTA EN POS (como ASESORA)
    # =========================================================================
    # Confirmar recargo del día si es necesario
    r_tasa = cliente.get("/api/tasas/hoy", headers=cab_as)
    assert r_tasa.status_code == 200

    inst_usd = next(
        i
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_as).json()
        if i["moneda"] == "USD" and "parte de pago" not in i["nombre"].lower()
    )

    r_venta = cliente.post(
        "/api/ventas",
        headers=cab_as,
        json={
            "sucursal_id": 1,
            "fecha": hoy_str,
            "asesor_id": ctx["asesora_id"],
            "canal_visita": "Tienda",
            "entrega": "Tienda",
            "items": [
                {
                    "equipo_id": laptop_id,
                    "cantidad": 1,
                    "precio_pactado_usd": 250,
                }
            ],
            "pagos": [
                {
                    "instrumento_id": inst_usd["id"],
                    "monto_moneda_origen": 250,
                    "referencia": "POS-E2E-250",
                }
            ],
        },
    )
    assert r_venta.status_code == 201, r_venta.text
    venta_as = r_venta.json()
    venta_id = venta_as["id"]
    num_venta = venta_as["numero_venta"]
    assert not _contiene_claves_costo(venta_as), "No debe exponer costos a ASESORA"

    # Verificar que la laptop pasó a VENDIDO
    inv_post = cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
    laptop_post = next(e for e in inv_post if e["id"] == laptop_id)
    assert laptop_post["estado"] == "VENDIDO"

    # Verificar generación de PDF Nota de Entrega sin errores
    r_pdf = cliente.get(f"/api/ventas/{venta_id}/nota-pdf", headers=cab_as)
    assert r_pdf.status_code == 200, r_pdf.text
    assert r_pdf.headers.get("content-type", "").startswith("application/pdf")
    assert r_pdf.content.startswith(b"%PDF")

    # Verificar asientos automáticos de Ingreso ($250) y Costo de Ventas ($140)
    asientos_vta = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=VENTAS", headers=cab_dir
    ).json()
    as_ing = next(a for a in asientos_vta if a["referencia"] == num_venta)
    assert as_ing["cuadrado"] is True
    assert as_ing["total_debe_usd"] == 250.0
    assert as_ing["total_haber_usd"] == 250.0

    asientos_cogs = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=VENTAS_COGS", headers=cab_dir
    ).json()
    as_cogs = next(a for a in asientos_cogs if a["referencia"] == num_venta)
    assert as_cogs["cuadrado"] is True
    assert as_cogs["total_debe_usd"] == 140.0
    assert as_cogs["total_haber_usd"] == 140.0

    # =========================================================================
    # PASO 4: COMISIONES, MARGEN REAL Y ESTADOS FINANCIEROS (como DIRECCION)
    # =========================================================================
    r_com = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
        headers=cab_dir,
    )
    assert r_com.status_code == 200, r_com.text
    com_data = r_com.json()
    lista_com = com_data["comisiones"]
    com_asesora = next(
        u for u in lista_com if u.get("usuario_id") == ctx["asesora_id"]
    )
    # 1% sobre $250 Promo = $2.50
    assert com_asesora["total_comision_usd"] == 2.5

    com_lider = next(
        (u for u in lista_com if u.get("rol") == "LIDER"), None
    )
    if com_lider is not None:
        # 0.5% sobre $250 Promo = $1.25
        assert com_lider["total_comision_usd"] == 1.25

    # Verificar margen neto real en la venta vista por DIRECCION
    ventas_dir = cliente.get("/api/ventas", headers=cab_dir).json()
    lista_v = ventas_dir["elementos"] if isinstance(ventas_dir, dict) else ventas_dir
    venta_dir = next(v for v in lista_v if v["id"] == venta_id)
    assert venta_dir["costo_equipo_final_usd"] == 140.0
    assert venta_dir["comision_total_venta_usd"] == 3.75  # 1% ($2.50) + 0.5% ($1.25)
    assert venta_dir["margen_neto_real_usd"] == 106.25  # 250 - 140 - 3.75
    assert venta_dir["margen_neto_real_pct"] == 42.5

    # Verificar P&L Escalonado
    r_pl = cliente.get(
        f"/api/finanzas/estados/pl-escalonado?fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
        headers=cab_dir,
    )
    assert r_pl.status_code == 200, r_pl.text
    pl = r_pl.json()
    assert pl["ingresos_netos_usd"] == 250.0
    assert pl["costo_ventas_usd"] == 140.0
    assert pl["utilidad_bruta_usd"] == 110.0
    assert pl["comisiones_venta_usd"] == 3.75
    assert pl["utilidad_operativa_ebit_usd"] == 106.25
    assert pl["utilidad_neta_usd"] == 106.25

    # Verificar Balance General cuadrado exacto al centavo (Activo == Pasivo + Patrimonio)
    r_bal = cliente.get(
        f"/api/finanzas/estados/balance-general?fecha_corte={hoy_str}",
        headers=cab_dir,
    )
    assert r_bal.status_code == 200, r_bal.text
    bal = r_bal.json()
    assert bal["cuadrado"] is True
    assert bal["diferencia_cuadre_usd"] == 0.0
    assert bal["activos"]["total_activos_usd"] == bal["total_pasivo_mas_patrimonio_usd"]

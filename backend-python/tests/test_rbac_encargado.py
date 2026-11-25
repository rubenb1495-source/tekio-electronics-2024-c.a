from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _contiene_claves_sensibles(objeto: Any) -> list[str]:
    """Busca recursivamente claves costo_*, margen_* o proveedor_* en cualquier JSON."""
    hallazgos: list[str] = []
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            kn = str(k).lower()
            if (
                kn.startswith("costo_")
                or kn.startswith("margen_")
                or kn.startswith("proveedor_")
                or kn in {"costo", "margen", "proveedor", "ganancia_usd", "utilidad_usd"}
            ):
                hallazgos.append(str(k))
            hallazgos.extend(_contiene_claves_sensibles(v))
    elif isinstance(objeto, list):
        for item in objeto:
            hallazgos.extend(_contiene_claves_sensibles(item))
    return hallazgos


def _crear_y_autenticar(
    cliente: TestClient,
    cab_dir: dict[str, str],
    nombre: str,
    correo: str,
    clave: str,
    rol: str,
    sucursal_id: int = 1,
) -> tuple[dict[str, str], int]:
    resp = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": nombre,
            "correo": correo,
            "clave": clave,
            "rol": rol,
            "sucursal_id": sucursal_id,
            "tiene_acceso": True,
        },
    )
    assert resp.status_code == 201, resp.text
    uid = resp.json()["id"]
    login = cliente.post("/api/auth/login", json={"correo": correo, "clave": clave})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}, uid


def test_rbac_estricto_encargado_vs_administracion(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # Crear usuarios ENCARGADO (Sucursal 1) y ADMINISTRACION
    cab_enc, enc_id = _crear_y_autenticar(
        cliente,
        cab_dir,
        "Carlos Encargado",
        "encargado@tekioelectronics.com",
        "Encargado2026!",
        "ENCARGADO",
        sucursal_id=1,
    )
    cab_adm, _adm_id = _crear_y_autenticar(
        cliente,
        cab_dir,
        "María Administración",
        "admin@tekioelectronics.com",
        "Admin2026!",
        "ADMINISTRACION",
        sucursal_id=1,
    )

    # ==========================================================
    # 1. ACCIONES PERMITIDAS (200/201) PARA ENCARGADO
    # ==========================================================

    # 1.1 Confirmar recargo diario (sin modificar BCV/USDT manualmente)
    r_rec = cliente.post(
        "/api/finanzas/tasas/recargo-diario",
        headers=cab_enc,
        json={"porcentaje_recargo": 10.0},
    )
    assert r_rec.status_code == 200, r_rec.text

    # 1.2 Crear cotización
    r_cot = cliente.post(
        "/api/cotizaciones",
        headers=cab_enc,
        json={
            "sucursal_id": 1,
            "asesor_id": enc_id,
            "cliente_id": ctx["cliente_id"],
            "cliente_nombre": "Cliente Encargado",
            "validez_dias": 3,
            "items": [
                {
                    "articulo_id": ctx["art_base_id"],
                    "descripcion": "Laptop Prueba RBAC",
                    "cantidad": 1,
                    "precio_promo_usd": 400.0,
                }
            ],
        },
    )
    assert r_cot.status_code == 201, r_cot.text

    # 1.3 Descargar lista de precios (JSON y PDF)
    r_lp = cliente.get("/api/catalogo/lista-precios", headers=cab_enc)
    assert r_lp.status_code == 200, r_lp.text
    r_lp_pdf = cliente.get("/api/catalogo/lista-precios-pdf?tipo_precio=PROMO", headers=cab_enc)
    assert r_lp_pdf.status_code == 200
    assert r_lp_pdf.content.startswith(b"%PDF-")

    # 1.4 Emitir venta POS
    r_venta = cliente.post(
        "/api/ventas",
        headers=cab_enc,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": enc_id,
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [
                {
                    "instrumento_id": ctx["inst_usd_id"],
                    "monto_moneda_origen": 400.0,
                    "referencia": "EFE-ENC-001",
                }
            ],
        },
    )
    assert r_venta.status_code == 201, r_venta.text
    venta_id = r_venta.json()["id"]
    assert _contiene_claves_sensibles(r_venta.json()) == []

    # 1.5 Consultar y guardar Cierre de Caja de SU PROPIA sucursal (1)
    r_prev = cliente.get("/api/finanzas/cierre-caja/preview?sucursal_id=1", headers=cab_enc)
    assert r_prev.status_code == 200, r_prev.text
    r_cierre = cliente.post(
        "/api/finanzas/cierre-caja",
        headers=cab_enc,
        json={
            "sucursal_id": 1,
            "efectivo_declarado_usd": 400.0,
            "observaciones": "Cierre de turno Encargado",
        },
    )
    assert r_cierre.status_code == 201, r_cierre.text

    # 1.6 Consultar comisiones en modo lectura (su sucursal)
    r_com = cliente.get("/api/finanzas/comisiones", headers=cab_enc)
    assert r_com.status_code == 200, r_com.text

    # ==========================================================
    # 2. BLOQUEOS ESTRICTOS (403 Forbidden) PARA ENCARGADO
    # ==========================================================

    # 2.1 Anular venta -> 403
    r_anular_enc = cliente.post(
        f"/api/ventas/{venta_id}/anular",
        headers=cab_enc,
        json={"motivo": "Intento de anulación por encargado"},
    )
    assert r_anular_enc.status_code == 403, r_anular_enc.text

    # 2.2 Reembolso Total -> 403
    r_reemb = cliente.post(
        "/api/devoluciones-garantias",
        headers=cab_enc,
        json={
            "venta_id": venta_id,
            "tipo_resolucion": "REEMBOLSO_TOTAL",
            "equipo_origen_id": ctx["eq_hp_1"],
            "instrumento_id": ctx["inst_usd_id"],
            "motivo": "Intento de reembolso total por encargado",
        },
    )
    assert r_reemb.status_code == 403, r_reemb.text

    # 2.3 Liquidar comisiones -> 403
    r_liq = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=cab_enc,
        json={
            "usuario_id": enc_id,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
            "instrumento_id": ctx["inst_usd_id"],
            "referencia": "LIQ-NO-AUTORIZADA",
        },
    )
    assert r_liq.status_code == 403, r_liq.text

    # 2.4 Crear/listar usuarios -> 403
    r_usr = cliente.post(
        "/api/usuarios",
        headers=cab_enc,
        json={"nombre": "Intruso", "rol": "ASESORA", "tiene_acceso": False},
    )
    assert r_usr.status_code == 403, r_usr.text
    assert cliente.get("/api/usuarios", headers=cab_enc).status_code == 403

    # 2.5 Crear compras / consultar proveedores -> 403
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_enc,
        json={
            "proveedor_id": 1,
            "fecha": "2026-11-24",
            "moneda": "USD",
            "items": [],
        },
    )
    assert r_comp.status_code == 403, r_comp.text
    assert cliente.get("/api/logistica/compras", headers=cab_enc).status_code == 403
    assert cliente.get("/api/logistica/terceros?tipo=PROVEEDOR", headers=cab_enc).status_code == 403

    # 2.6 Consulta de bancos/pagos/saldos globales -> 403
    assert cliente.get("/api/finanzas/pagos", headers=cab_enc).status_code == 403
    assert cliente.get("/api/finanzas/tablero", headers=cab_enc).status_code == 403
    assert cliente.get("/api/finanzas/cuentas-por-cobrar", headers=cab_enc).status_code == 403

    # 2.7 Cierre de caja de OTRA sucursal (2) -> 403
    assert (
        cliente.get("/api/finanzas/cierre-caja/preview?sucursal_id=2", headers=cab_enc).status_code
        == 403
    )

    # 2.8 Editar catálogo o tasas manuales -> 403
    assert (
        cliente.post(
            "/api/catalogo",
            headers=cab_enc,
            json={
                "sku": "NO-PERMITIDO",
                "descripcion": "No permitido",
                "tipo": "EQUIPO",
                "precio_promo_usd": 100.0,
            },
        ).status_code
        == 403
    )
    assert (
        cliente.put(
            "/api/tasas/hoy",
            headers=cab_enc,
            json={"tasa_bcv": 50.0, "tasa_usdt": 60.0, "recargo_porcentaje": 10.0},
        ).status_code
        == 403
    )

    # ==========================================================
    # 3. ANTI-FUGA DE COSTOS EN INVENTARIO, CATÁLOGO Y VENTAS
    # ==========================================================
    resp_inv_enc = cliente.get("/api/logistica/inventario/equipos", headers=cab_enc)
    assert resp_inv_enc.status_code == 200
    assert _contiene_claves_sensibles(resp_inv_enc.json()) == []

    resp_cat_enc = cliente.get("/api/catalogo", headers=cab_enc)
    assert resp_cat_enc.status_code == 200
    assert _contiene_claves_sensibles(resp_cat_enc.json()) == []

    resp_ven_enc = cliente.get("/api/ventas", headers=cab_enc)
    assert resp_ven_enc.status_code == 200
    assert _contiene_claves_sensibles(resp_ven_enc.json()) == []

    # ==========================================================
    # 4. ADMINISTRACION SÍ TIENE ACCESO COMPLETO Y VE COSTOS
    # ==========================================================
    assert cliente.get("/api/usuarios", headers=cab_adm).status_code == 200
    assert cliente.get("/api/finanzas/pagos", headers=cab_adm).status_code == 200
    assert cliente.get("/api/finanzas/tablero", headers=cab_adm).status_code == 200
    assert cliente.get("/api/finanzas/cuentas-por-cobrar", headers=cab_adm).status_code == 200

    resp_inv_adm = cliente.get("/api/logistica/inventario/equipos", headers=cab_adm)
    assert resp_inv_adm.status_code == 200
    assert len(_contiene_claves_sensibles(resp_inv_adm.json())) > 0

    r_anular_adm = cliente.post(
        f"/api/ventas/{venta_id}/anular",
        headers=cab_adm,
        json={"motivo": "Anulación autorizada por Administración"},
    )
    assert r_anular_adm.status_code == 200, r_anular_adm.text

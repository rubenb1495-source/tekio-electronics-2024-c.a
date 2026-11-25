from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.modelos_finanzas import Pago, TipoDocumentoPago  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_modulo_integral_administracion_finanzas_y_rbac(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy = obtener_fecha_hoy()
    hoy_str = hoy.isoformat()

    # Crear técnico para verificar RBAC 403
    r_tec = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Luis Téc Admin",
            "correo": "luis.tec.af@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert r_tec.status_code == 201
    cab_tec = _login(cliente, "luis.tec.af@tekio.com", "Password123!")

    # 1. RBAC 403 en todos los endpoints nuevos para ASESORA y TECNICO
    rutas_admin = [
        "/api/finanzas/gastos",
        "/api/finanzas/estado-resultados",
        "/api/finanzas/fiscal/documentos",
        "/api/finanzas/fiscal/obligaciones",
        "/api/finanzas/nomina/empleados",
        "/api/finanzas/nomina/periodos",
        "/api/finanzas/conciliacion/partidas",
        "/api/finanzas/auditoria",
        "/api/finanzas/admin-plantillas/gastos_operativos",
    ]
    for cab_op in (cab_as, cab_tec):
        for ruta in rutas_admin:
            assert cliente.get(ruta, headers=cab_op).status_code == 403, f"Falló RBAC en {ruta}"

    # Emitir 1 venta hoy ($400 Promo, costo $260 -> utilidad bruta $140)
    r_vta = cliente.post(
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
                    "referencia": "REF-CONC-400",
                }
            ],
        },
    )
    assert r_vta.status_code == 201, r_vta.text

    # 2. Contabilidad: Gasto Operativo ($50) + Estado de Resultados (P&L) + PDF/XLSX
    r_gasto = cliente.post(
        "/api/finanzas/gastos",
        headers=cab_dir,
        json={
            "fecha": hoy_str,
            "categoria": "ALQUILER",
            "sucursal_id": 1,
            "proveedor": "CC Free Market",
            "factura_comprobante": "FAC-ALQ-01",
            "descripcion": "Alquiler mensual",
            "moneda": "USD",
            "monto_origen": 50.0,
            "instrumento_id": ctx["inst_usd_id"],
        },
    )
    assert r_gasto.status_code == 201, r_gasto.text
    assert r_gasto.json()["pago_egreso_id"] is not None

    # 3. Gestión Fiscal SENIAT: Factura compra (IVA 16%, IGTF 3%, Ret. IVA 75%) + Libro XLSX/PDF + Obligación en alertas
    r_doc = cliente.post(
        "/api/finanzas/fiscal/documentos",
        headers=cab_dir,
        json={
            "tipo_libro": "COMPRA",
            "fecha": hoy_str,
            "numero_factura": "0001-00055",
            "numero_control": "00-99123",
            "rif_tercero": "J-40123456-7",
            "nombre_tercero": "Suplidora Fiscal CA",
            "base_imponible": 100.0,
            "monto_exento": 0.0,
            "iva_pct": 16.0,
            "igtf_pct": 3.0,
            "retencion_iva_pct": 75.0,
            "moneda": "USD",
        },
    )
    assert r_doc.status_code == 201, r_doc.text
    assert r_doc.json()["iva_monto"] == 16.0
    assert r_doc.json()["retencion_iva_monto"] == 12.0

    r_lib_xlsx = cliente.get(f"/api/finanzas/fiscal/libro/COMPRA/xlsx?fecha_inicio={hoy_str}&fecha_fin={hoy_str}", headers=cab_dir)
    assert r_lib_xlsx.status_code == 200 and r_lib_xlsx.content.startswith(b"PK")
    r_lib_pdf = cliente.get(f"/api/finanzas/fiscal/libro/COMPRA/pdf?fecha_inicio={hoy_str}&fecha_fin={hoy_str}", headers=cab_dir)
    assert r_lib_pdf.status_code == 200 and r_lib_pdf.content.startswith(b"%PDF-")

    r_ob = cliente.post(
        "/api/finanzas/fiscal/obligaciones",
        headers=cab_dir,
        json={
            "tipo": "IVA",
            "periodo": hoy_str[:7],
            "fecha_vencimiento": (hoy + timedelta(days=2)).isoformat(),
            "monto_estimado_usd": 120.0,
        },
    )
    assert r_ob.status_code == 201
    r_al = cliente.get("/api/alertas", headers=cab_dir)
    assert any(c["origen"] == "FISCAL" for c in r_al.json()["cxp_por_vencer"])

    # 4. Nómina: Ficha laboral + Período + Aprobar/Pagar (crea EGRESO automático) + Recibo PDF
    r_emp = cliente.post(
        "/api/finanzas/nomina/empleados",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "cedula": "V-24111222",
            "cargo": "Asesora Comercial",
            "salario_base_usd": 200.0,
            "bono_cestaticket_usd": 40.0,
            "datos_bancarios": "Pago Móvil 0414-1112233",
        },
    )
    assert r_emp.status_code == 201, r_emp.text

    r_per = cliente.post(
        "/api/finanzas/nomina/periodos",
        headers=cab_dir,
        json={
            "tipo_periodo": "QUINCENAL",
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "porcentaje_ivss": 0.0,
            "porcentaje_faov": 0.0,
            "porcentaje_rpe": 0.0,
        },
    )
    assert r_per.status_code == 201, r_per.text
    periodo_id = r_per.json()["id"]
    assert r_per.json()["total_neto_usd"] == 120.0  # (200 + 40) * 0.5

    r_pagar = cliente.post(
        f"/api/finanzas/nomina/periodos/{periodo_id}/pagar",
        headers=cab_dir,
        json={"instrumento_id": ctx["inst_usd_id"], "referencia_pago": "NOM-PAY-01"},
    )
    assert r_pagar.status_code == 200, r_pagar.text
    pago_nom_id = r_pagar.json()["pago_egreso_id"]

    # Confirmar EGRESO de nómina en tabla pagos
    gen_bd = app.dependency_overrides[obtener_bd]()
    bd = next(gen_bd)
    try:
        pago_nom = bd.query(Pago).filter(Pago.id == pago_nom_id).first()
        assert pago_nom is not None
        assert pago_nom.tipo_documento == TipoDocumentoPago.NOMINA.value
    finally:
        bd.close()

    periodos = cliente.get("/api/finanzas/nomina/periodos", headers=cab_dir).json()
    recibo_id = periodos[0]["recibos"][0]["id"]
    r_rec_pdf = cliente.get(f"/api/finanzas/nomina/recibos/{recibo_id}/pdf", headers=cab_dir)
    assert r_rec_pdf.status_code == 200 and r_rec_pdf.content.startswith(b"%PDF-")

    # Verificar Estado de Resultados (P&L): Ingresos 400 - COGS 260 = Bruta 140 - Gastos 50 - Nómina 120 = Neta -30
    r_pyl = cliente.get(f"/api/finanzas/estado-resultados?fecha_inicio={hoy_str}&fecha_fin={hoy_str}", headers=cab_dir)
    assert r_pyl.status_code == 200, r_pyl.text
    pyl = r_pyl.json()
    assert pyl["ingresos_ventas_usd"] == 400.0
    assert pyl["gastos_operativos_usd"] == 50.0
    assert pyl["nomina_pagada_usd"] == 120.0
    assert cliente.get(f"/api/finanzas/estado-resultados/pdf?fecha_inicio={hoy_str}&fecha_fin={hoy_str}", headers=cab_dir).content.startswith(b"%PDF-")
    assert cliente.get(f"/api/finanzas/estado-resultados/xlsx?fecha_inicio={hoy_str}&fecha_fin={hoy_str}", headers=cab_dir).content.startswith(b"PK")

    # 5. Conciliación Bancaria + Carga Masiva Atómica (Extracto CSV)
    csv_ext = (
        f"fecha,referencia,descripcion,tipo_movimiento,monto\n"
        f"{hoy_str},REF-CONC-400,Pago cliente laptop,CREDITO,400.00\n"
        f"{hoy_str},REF-NO-EXISTE,Cargo bancario no registrado,DEBITO,15.00\n"
    ).encode("utf-8")

    r_prev_ext = cliente.post(
        "/api/finanzas/admin-importar/preview",
        headers=cab_dir,
        data={"flujo": "extractos_bancarios", "instrumento_id": str(ctx["inst_usd_id"])},
        files={"archivo": ("extracto.csv", csv_ext, "text/csv")},
    )
    assert r_prev_ext.status_code == 200 and r_prev_ext.json()["puede_confirmar"] is True

    r_conf_ext = cliente.post(
        "/api/finanzas/admin-importar/confirmar",
        headers=cab_dir,
        data={"flujo": "extractos_bancarios", "instrumento_id": str(ctx["inst_usd_id"])},
        files={"archivo": ("extracto.csv", csv_ext, "text/csv")},
    )
    assert r_conf_ext.status_code == 201, r_conf_ext.text

    partidas = cliente.get(
        f"/api/finanzas/conciliacion/partidas?instrumento_id={ctx['inst_usd_id']}",
        headers=cab_dir,
    ).json()["partidas"]
    assert any(p["referencia"] == "REF-CONC-400" and p["estado"] == "CONCILIADO" for p in partidas)
    assert any(p["referencia"] == "REF-NO-EXISTE" and p["estado"] == "PENDIENTE_SISTEMA" for p in partidas)
    assert cliente.get("/api/finanzas/conciliacion/pdf", headers=cab_dir).content.startswith(b"%PDF-")

    # 6. Auditoría Interna Inmutable
    r_aud = cliente.get("/api/finanzas/auditoria", headers=cab_dir)
    assert r_aud.status_code == 200
    acciones = [a["accion"] for a in r_aud.json()]
    assert "REGISTRAR_GASTO" in acciones
    assert "APROBAR_PAGAR_NOMINA" in acciones
    assert cliente.get("/api/finanzas/auditoria/exportar/xlsx", headers=cab_dir).content.startswith(b"PK")
    assert cliente.get("/api/finanzas/auditoria/exportar/pdf", headers=cab_dir).content.startswith(b"%PDF-")

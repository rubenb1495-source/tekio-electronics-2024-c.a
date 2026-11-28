from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_seguridad_login_username_cambio_clave_bloqueo_423_y_desbloqueo(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # 1. Crear usuario con username explícito
    r_u = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Sofía Seguridad",
            "username": "sofia.seg",
            "correo": "sofia.seg@tekio.com",
            "clave": "ClaveInicial123",
            "rol": "ENCARGADO",
            "sucursal_id": 1,
        },
    )
    assert r_u.status_code == 201, r_u.text
    uid = r_u.json()["id"]
    assert r_u.json()["username"] == "sofia.seg"

    # 2. Login por username (sin usar correo)
    r_log = cliente.post(
        "/api/auth/login",
        json={"identificador": "sofia.seg", "clave": "ClaveInicial123"},
    )
    assert r_log.status_code == 200, r_log.text
    cab_sofia = {"Authorization": f"Bearer {r_log.json()['token']}"}

    # 3. Cambio de contraseña propio (mínimo 8 caracteres)
    r_chg = cliente.post(
        "/api/auth/cambiar-password",
        headers=cab_sofia,
        json={"clave_actual": "ClaveInicial123", "clave_nueva": "NuevaClaveSegura99"},
    )
    assert r_chg.status_code == 200, r_chg.text

    # 4. 5 intentos fallidos -> 401 los primeros 4 y 423 Locked al 5to
    for intento in range(1, 5):
        r_bad = cliente.post(
            "/api/auth/login",
            json={"identificador": "sofia.seg", "clave": "clave-incorrecta"},
        )
        assert r_bad.status_code == 401, f"Intento {intento}: {r_bad.text}"

    r_lock = cliente.post(
        "/api/auth/login",
        json={"identificador": "sofia.seg", "clave": "clave-incorrecta"},
    )
    assert r_lock.status_code == 423, r_lock.text

    # 5. Alerta de seguridad creada en /api/alertas y auditoria_sistema
    r_al = cliente.get("/api/alertas", headers=cab_dir)
    assert r_al.status_code == 200
    assert any(a["username"] == "sofia.seg" for a in r_al.json()["alertas_seguridad"])

    r_aud = cliente.get("/api/finanzas/auditoria?modulo=SEGURIDAD", headers=cab_dir)
    assert r_aud.status_code == 200
    assert any(ev["accion"] in ("BLOQUEO_ACCESO", "CUENTA_BLOQUEADA_LOGIN") for ev in r_aud.json())

    # 6. Desbloqueo por DIRECCION y login exitoso con nueva clave
    r_un = cliente.post(f"/api/usuarios/{uid}/desbloquear", headers=cab_dir)
    assert r_un.status_code == 200, r_un.text
    assert r_un.json()["cuenta_bloqueada"] is False

    r_ok = cliente.post(
        "/api/auth/login",
        json={"identificador": "sofia.seg", "clave": "NuevaClaveSegura99"},
    )
    assert r_ok.status_code == 200, r_ok.text


def test_matematica_cashea_trackings_recepcion_pdf_nomina_y_utilidades(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy_str = obtener_fecha_hoy().isoformat()
    mes_actual = hoy_str[:7]

    # 1. Crear compra internacional + trackings
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "INTERNACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 400,
            "envio_usd": 40,
            "aduana_usd": 10,
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "CASHEA-EQ-500",
                    "modelo": "MacBook Air M2",
                    "costo_compra_usd": 400,
                    "precio_promo_usd": 500,
                    "ubicacion_id": 1,
                }
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    compra_id = r_comp.json()["id"]

    r_trk = cliente.post(
        f"/api/logistica/compras/{compra_id}/trackings",
        headers=cab_dir,
        json={
            "numero_tracking": "1Z999TEKIO001",
            "courier": "UPS",
            "estado": "EN_ORIGEN",
            "peso_lb": 4.5,
        },
    )
    assert r_trk.status_code == 201, r_trk.text
    trk_id = r_trk.json()["id"]

    r_trk_upd = cliente.patch(
        f"/api/logistica/trackings/{trk_id}/estado",
        headers=cab_dir,
        json={"estado": "EN_ADUANA", "notas": "Llegó a aduana Maiquetía"},
    )
    assert r_trk_upd.status_code == 200, r_trk_upd.text
    assert r_trk_upd.json()["estado"] == "EN_ADUANA"

    r_trk_bus = cliente.get("/api/logistica/trackings?busqueda=1Z999TEKIO", headers=cab_dir)
    assert r_trk_bus.status_code == 200
    assert len(r_trk_bus.json()) == 1

    # 2. Matemática Financiera Detallada de Cashea (equipo LISTO, promo $500)
    eq = next(
        e
        for e in cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
        if e["serial"] == "CASHEA-EQ-500"
    )
    cliente.patch(
        f"/api/inventario/equipos/{eq['id']}/estado",
        headers=cab_dir,
        json={"nuevo_estado": "LISTO"},
    )

    insts = cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    inst_usd = next(i for i in insts if i["moneda"] == "USD" and "parte de pago" not in i["nombre"].lower())
    inst_cashea = next(i for i in insts if "cashea" in i["nombre"].lower())

    # Simular para obtener total_regular exacto
    r_sim = cliente.post(
        "/api/ventas/simular",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "items": [{"equipo_id": eq["id"], "cantidad": 1, "precio_pactado_usd": 500}],
            "pagos": [{"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300}],
        },
    )
    assert r_sim.status_code == 200, r_sim.text
    total_regular = r_sim.json()["total_regular_usd"]
    inicial = round(total_regular - 300.0, 2)

    r_vta = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "fecha": hoy_str,
            "asesor_id": ctx["asesora_id"],
            "cashea_numero_orden": "CSH-5MOD-001",
            "sin_cargador": True,
            "items": [{"equipo_id": eq["id"], "cantidad": 1, "precio_pactado_usd": 500}],
            "pagos": [
                {"instrumento_id": inst_usd["id"], "monto_moneda_origen": inicial},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300},
            ],
        },
    )
    assert r_vta.status_code == 201, r_vta.text
    vta = r_vta.json()
    num_nota = vta["numero_venta"]

    # Verificar matemática exacta: 4% sobre Total Regular, 4% sobre Financiado (300), 16% IVA y 2% ISLR sobre 4% Total
    esp_com_total = round(total_regular * 0.04, 2)
    esp_com_fin = round(300.0 * 0.04, 2)
    esp_iva = round(esp_com_total * 0.16, 2)
    esp_islr = round(esp_com_total * 0.02, 2)
    esp_total_ded = round(esp_com_total + esp_com_fin + esp_iva + esp_islr, 2)
    esp_neto = round(300.0 - esp_total_ded, 2)

    assert vta["comision_cashea_venta_total_usd"] == esp_com_total
    assert vta["comision_cashea_financiado_usd"] == esp_com_fin
    assert vta["iva_cashea_usd"] == esp_iva
    assert vta["islr_cashea_usd"] == esp_islr
    assert vta["total_deducciones_cashea_usd"] == esp_total_ded
    assert vta["neto_esperado_cashea_usd"] == esp_neto

    # Verificar asiento CASHEA_DEDUCCIONES cuadrado
    as_cashea = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=CASHEA_DEDUCCIONES", headers=cab_dir
    ).json()
    assert any(a["referencia"] == num_nota and a["total_debe_usd"] == esp_total_ded and a["cuadrado"] for a in as_cashea)

    # 3. Recepción GARANTIA (exige nota válida) vs SERVICIO_TECNICO (sin nota + PDF cláusulas)
    r_gar_err = cliente.post(
        "/api/taller/recepciones",
        headers=cab_dir,
        json={
            "tipo": "GARANTIA",
            "sucursal_id": 1,
            "numero_nota_entrega": "",
            "descripcion_equipo": "MacBook Air M2",
            "falla_reportada": "No carga batería",
        },
    )
    assert r_gar_err.status_code == 400

    r_gar_ok = cliente.post(
        "/api/taller/recepciones",
        headers=cab_dir,
        json={
            "tipo": "GARANTIA",
            "sucursal_id": 1,
            "numero_nota_entrega": num_nota,
            "descripcion_equipo": "MacBook Air M2",
            "serial_o_codigo": "CASHEA-EQ-500",
            "falla_reportada": "Teclado falla tecla espacio",
        },
    )
    assert r_gar_ok.status_code == 201, r_gar_ok.text
    assert r_gar_ok.json()["numero_nota_entrega"] == num_nota

    r_st = cliente.post(
        "/api/taller/recepciones",
        headers=cab_dir,
        json={
            "tipo": "SERVICIO_TECNICO",
            "sucursal_id": 1,
            "cliente_nombre": "Carlos Cliente ST",
            "cliente_telefono": "04141234567",
            "descripcion_equipo": "Laptop Asus VivoBook",
            "ingresa_apagado": True,
            "accesorios_recibidos": "Cargador original",
            "falla_reportada": "Equipo no enciende tras caída",
        },
    )
    assert r_st.status_code == 201, r_st.text
    st_id = r_st.json()["id"]
    assert r_st.json()["ingresa_apagado"] is True

    r_pdf = cliente.get(f"/api/taller/recepciones/{st_id}/pdf", headers=cab_dir)
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF")

    # 4. Catálogo detallado de gastos, nómina segmentada y reparto de utilidades
    r_cats = cliente.get("/api/finanzas/gastos/categorias", headers=cab_dir)
    assert r_cats.status_code == 200
    cods = {c["codigo"] for c in r_cats.json()}
    assert {"ALQUILER_TIENDA", "ALQUILER_ALMACEN", "CONDOMINIO", "COMISIONES_BANCARIAS"}.issubset(cods)

    r_emp = cliente.post(
        "/api/finanzas/nomina/empleados",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "cedula": "V-20111222",
            "cargo": "Asesora Comercial",
            "categoria_laboral": "LIDER_ENCARGADO",
            "salario_base_usd": 350,
            "bono_cestaticket_usd": 40,
        },
    )
    assert r_emp.status_code == 201, r_emp.text
    assert r_emp.json()["categoria_laboral"] == "LIDER_ENCARGADO"

    r_res_nom = cliente.get("/api/finanzas/nomina/resumen-categorias", headers=cab_dir)
    assert r_res_nom.status_code == 200
    assert any(
        c["categoria_laboral"] == "LIDER_ENCARGADO" and c["cantidad_empleados"] == 1
        for c in r_res_nom.json()
    )

    # Socios (60% + 40%) + Reparto de Utilidades ($1000) + Asiento 3.1.03 / 1.1.01 + PDF
    assert (
        cliente.post(
            "/api/finanzas/socios",
            headers=cab_dir,
            json={"nombre": "Socio A", "porcentaje_participacion": 60, "activo": True},
        ).status_code
        == 201
    )
    assert (
        cliente.post(
            "/api/finanzas/socios",
            headers=cab_dir,
            json={"nombre": "Socio B", "porcentaje_participacion": 40, "activo": True},
        ).status_code
        == 201
    )

    r_rep = cliente.post(
        "/api/finanzas/utilidades/repartos",
        headers=cab_dir,
        json={
            "periodo_mes": mes_actual,
            "monto_distribuido_usd": 1000,
            "fecha_pago": hoy_str,
            "instrumento_id": inst_usd["id"],
            "referencia_base": "DIV-TEST-01",
            "notas": "Reparto mensual",
        },
    )
    assert r_rep.status_code == 201, r_rep.text
    rep = r_rep.json()
    assert rep["monto_distribuido_usd"] == 1000.0
    montos = {d["socio_nombre"]: d["monto_usd"] for d in rep["detalles"]}
    assert montos == {"Socio A": 600.0, "Socio B": 400.0}

    # Verificar asiento cuadrado REPARTO_UTILIDADES
    as_rep = cliente.get(
        "/api/finanzas/contabilidad/asientos?modulo=REPARTO_UTILIDADES", headers=cab_dir
    ).json()
    assert any(a["referencia"] == "DIV-TEST-01" and a["total_debe_usd"] == 1000.0 and a["cuadrado"] for a in as_rep)

    # Verificar PDF comprobante de reparto
    r_rep_pdf = cliente.get(f"/api/finanzas/utilidades/repartos/{rep['id']}/pdf", headers=cab_dir)
    assert r_rep_pdf.status_code == 200
    assert r_rep_pdf.content.startswith(b"%PDF")

    # RBAC: ASESORA bloqueada (403) en utilidades y socios
    assert cliente.get("/api/finanzas/socios", headers=cab_as).status_code == 403
    assert cliente.get("/api/finanzas/utilidades/repartos", headers=cab_as).status_code == 403

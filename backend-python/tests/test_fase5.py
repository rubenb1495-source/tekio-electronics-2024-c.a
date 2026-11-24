from __future__ import annotations

import base64
import re
import zlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.base_datos import Base, obtener_bd
from app.main import app
from app.modelos import CatalogoArticulo, CatalogoPrecio, Sucursal, TipoArticulo
from app.modelos_logistica import Equipo, EstadoEquipo, MovimientoInventario, Tercero, TipoMovimientoInventario
from app.rutas.tasas import obtener_fecha_hoy
from app.semilla import ejecutar_semilla
from app.semilla_finanzas import ejecutar_semilla_finanzas


@pytest.fixture()
def cliente() -> TestClient:
    motor_pruebas = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SesionPruebas = sessionmaker(autocommit=False, autoflush=False, bind=motor_pruebas)
    Base.metadata.create_all(bind=motor_pruebas)

    bd_seed = SesionPruebas()
    try:
        ejecutar_semilla(bd_seed)
        ejecutar_semilla_finanzas(bd_seed)
    finally:
        bd_seed.close()

    def obtener_bd_prueba():
        bd = SesionPruebas()
        try:
            yield bd
        finally:
            bd.close()

    app.dependency_overrides[obtener_bd] = obtener_bd_prueba
    with TestClient(app) as client:
        client.sesion_factory = SesionPruebas  # type: ignore[attr-defined]
        yield client
    app.dependency_overrides.clear()


def _extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto legible de streams comprimidos de ReportLab."""
    texto = pdf_bytes.decode("latin-1", errors="ignore")
    for bloque in re.findall(rb"stream\r?\n(.*?)\s*endstream", pdf_bytes, flags=re.S):
        crudo = bloque.strip()
        if crudo.endswith(b"~>"):
            crudo = base64.a85decode(crudo, adobe=True)
        try:
            texto += zlib.decompress(crudo).decode("latin-1", errors="ignore")
        except zlib.error:
            pass
    return texto.replace("\\(", "(").replace("\\)", ")")


def _login(cliente: TestClient, correo: str, clave: str) -> dict[str, str]:
    resp = cliente.post(
        "/api/auth/login",
        json={"correo": correo, "clave": clave},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _preparar_escenario_base(cliente: TestClient) -> dict:
    headers_dir = _login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")

    # Crear asesora y asegurar tasa del día
    resp_as = cliente.post(
        "/api/usuarios",
        headers=headers_dir,
        json={
            "nombre": "Valeria Asesora",
            "correo": "valeria.f5@tekio.com",
            "clave": "Password123!",
            "rol": "ASESORA",
            "sucursal_id": 1,
        },
    )
    assert resp_as.status_code == 201, resp_as.text
    asesora_id = resp_as.json()["id"]
    headers_as = _login(cliente, "valeria.f5@tekio.com", "Password123!")

    hoy = obtener_fecha_hoy().isoformat()
    cliente.post(
        "/api/tasas",
        headers=headers_dir,
        json={"fecha": hoy, "tasa_bcv": 50.0, "tasa_usdt": 60.0},
    )

    # Crear cliente Natural
    resp_cli = cliente.post(
        "/api/clientes",
        headers=headers_as,
        json={
            "tipo_persona": "NATURAL",
            "tipo_documento": "V",
            "documento": "20445566",
            "nombre": "Carlos Mendoza",
            "telefono": "0414-5550011",
            "direccion": "Valencia, Carabobo",
        },
    )
    assert resp_cli.status_code == 201, resp_cli.text
    cliente_id = resp_cli.json()["id"]

    # Crear 2 SKUs de equipo (uno $400 y uno $600) + 1 componente repuesto ($25 promo, $12 costo)
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        suc = bd.query(Sucursal).filter(Sucursal.id == 1).first()
        assert suc is not None

        art_base = CatalogoArticulo(
            sku="LAP-HP-400",
            descripcion="HP EliteBook 840 G7 i5 16GB 256GB",
            tipo=TipoArticulo.EQUIPO.value,
            categoria="Laptops",
        )
        art_pro = CatalogoArticulo(
            sku="LAP-DELL-600",
            descripcion="Dell Latitude 7420 i7 16GB 512GB",
            tipo=TipoArticulo.EQUIPO.value,
            categoria="Laptops",
        )
        art_cargador = CatalogoArticulo(
            sku="REP-CARG-65W",
            descripcion="Cargador USB-C 65W Original",
            tipo=TipoArticulo.COMPONENTE.value,
            categoria="Repuestos",
        )
        bd.add_all([art_base, art_pro, art_cargador])
        bd.flush()

        hoy_d = obtener_fecha_hoy()
        bd.add_all(
            [
                CatalogoPrecio(
                    articulo_id=art_base.id,
                    precio_promo_usd=Decimal("400.00"),
                    costo_referencia_usd=Decimal("260.00"),
                    fecha_vigencia=hoy_d,
                ),
                CatalogoPrecio(
                    articulo_id=art_pro.id,
                    precio_promo_usd=Decimal("600.00"),
                    costo_referencia_usd=Decimal("390.00"),
                    fecha_vigencia=hoy_d,
                ),
                CatalogoPrecio(
                    articulo_id=art_cargador.id,
                    precio_promo_usd=Decimal("25.00"),
                    costo_referencia_usd=Decimal("12.00"),
                    fecha_vigencia=hoy_d,
                ),
            ]
        )

        # Equipos LISTO + 1 equipo en HOSPITAL (no debe aparecer en lista de precios)
        eq_hp_1 = Equipo(
            serial="SN-HP-001",
            articulo_id=art_base.id,
            modelo=art_base.descripcion,
            ubicacion_id=1,
            estado=EstadoEquipo.LISTO.value,
            precio_promo_usd=Decimal("400.00"),
            costo_compra_usd=Decimal("260.00"),
        )
        eq_hp_2 = Equipo(
            serial="SN-HP-002",
            articulo_id=art_base.id,
            modelo=art_base.descripcion,
            ubicacion_id=1,
            estado=EstadoEquipo.LISTO.value,
            precio_promo_usd=Decimal("400.00"),
            costo_compra_usd=Decimal("260.00"),
        )
        eq_hp_3 = Equipo(
            serial="SN-HP-003",
            articulo_id=art_base.id,
            modelo=art_base.descripcion,
            ubicacion_id=1,
            estado=EstadoEquipo.LISTO.value,
            precio_promo_usd=Decimal("400.00"),
            costo_compra_usd=Decimal("260.00"),
        )
        eq_dell_1 = Equipo(
            serial="SN-DELL-001",
            articulo_id=art_pro.id,
            modelo=art_pro.descripcion,
            ubicacion_id=1,
            estado=EstadoEquipo.LISTO.value,
            precio_promo_usd=Decimal("600.00"),
            costo_compra_usd=Decimal("390.00"),
        )
        eq_dell_2 = Equipo(
            serial="SN-DELL-002",
            articulo_id=art_pro.id,
            modelo=art_pro.descripcion,
            ubicacion_id=1,
            estado=EstadoEquipo.LISTO.value,
            precio_promo_usd=Decimal("600.00"),
            costo_compra_usd=Decimal("390.00"),
        )
        eq_hosp = Equipo(
            serial="SN-HOSP-999",
            articulo_id=art_pro.id,
            modelo="Equipo En Hospital No Disponible",
            ubicacion_id=1,
            estado=EstadoEquipo.HOSPITAL.value,
            costo_compra_usd=Decimal("390.00"),
        )
        bd.add_all([eq_hp_1, eq_hp_2, eq_hp_3, eq_dell_1, eq_dell_2, eq_hosp])
        bd.flush()

        # Stock de 5 cargadores en sucursal 1
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.COMPRA.value,
                articulo_id=art_cargador.id,
                sucursal_id=1,
                cantidad=5,
                costo_unitario_usd=Decimal("12.00"),
                documento_ref="CMP-INIT",
                motivo="Stock inicial cargadores",
                usuario_id=1,
            )
        )
        bd.commit()
        ids = {
            "art_base_id": art_base.id,
            "art_pro_id": art_pro.id,
            "art_cargador_id": art_cargador.id,
            "eq_hp_1": eq_hp_1.id,
            "eq_hp_2": eq_hp_2.id,
            "eq_hp_3": eq_hp_3.id,
            "eq_dell_1": eq_dell_1.id,
            "eq_dell_2": eq_dell_2.id,
        }
    finally:
        bd.close()

    insts = cliente.get("/api/finanzas/instrumentos", headers=headers_dir).json()
    inst_usd = next(i for i in insts if i["moneda"] == "USD" and "parte" not in i["nombre"].lower())

    return {
        "headers_dir": headers_dir,
        "headers_as": headers_as,
        "asesora_id": asesora_id,
        "cliente_id": cliente_id,
        "inst_usd_id": inst_usd["id"],
        **ids,
    }


def _crear_venta_rapida(cliente: TestClient, headers: dict[str, str], ctx: dict, equipo_id: int, monto: float) -> dict:
    resp = cliente.post(
        "/api/ventas",
        headers=headers,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "items": [{"equipo_id": equipo_id, "cantidad": 1}],
            "pagos": [{"instrumento_id": ctx["inst_usd_id"], "monto_moneda_origen": monto}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_devoluciones_5_escenarios_rbac_comisiones_y_pdf(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    h_dir = ctx["headers_dir"]
    h_as = ctx["headers_as"]

    # Venta 1: HP $400 (para CAMBIO_IGUAL y GARANTIA_COMPONENTE)
    v1 = _crear_venta_rapida(cliente, h_as, ctx, ctx["eq_hp_1"], 400.0)

    # 1. CAMBIO_IGUAL (SN-HP-001 -> HOSPITAL, SN-HP-002 -> VENDIDO, $0 diff)
    r_igual = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v1["id"],
            "equipo_origen_id": ctx["eq_hp_1"],
            "equipo_destino_id": ctx["eq_hp_2"],
            "tipo_resolucion": "CAMBIO_IGUAL",
            "estado_reingreso_origen": "HOSPITAL",
            "motivo": "Falla en puerto USB dentro de garantía",
        },
    )
    assert r_igual.status_code == 201, r_igual.text
    d_igual = r_igual.json()
    assert d_igual["diferencia_usd"] == 0.0
    assert "costo_garantia_usd" not in d_igual  # RBAC asesora

    # PDF del comprobante de cambio
    pdf_dev = cliente.get(f"/api/devoluciones-garantias/{d_igual['id']}/pdf", headers=h_as)
    assert pdf_dev.status_code == 200
    assert pdf_dev.headers["content-type"] == "application/pdf"
    txt_dev = _extraer_texto_pdf(pdf_dev.content)
    assert d_igual["numero_operacion"] in txt_dev
    assert "SN-HP-001" in txt_dev
    assert "SN-HP-002" in txt_dev

    # 2. GARANTIA_COMPONENTE (crea caso GT + descuenta cargador a $0 cliente + registra costo $12 oculto a asesora)
    r_gt = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v1["id"],
            "tipo_resolucion": "GARANTIA_COMPONENTE",
            "componente_afectado": "Cargador 65W",
            "articulo_repuesto_id": ctx["art_cargador_id"],
            "cantidad_repuesto": 1,
            "motivo": "Cargador dejó de suministrar corriente",
        },
    )
    assert r_gt.status_code == 201, r_gt.text
    d_gt = r_gt.json()
    assert d_gt["caso_taller_numero"].startswith("GT-")
    assert d_gt["diferencia_usd"] == 0.0
    assert "costo_garantia_usd" not in d_gt

    # Dirección SÍ ve el costo interno de garantía ($12.00)
    lista_dir = cliente.get("/api/devoluciones-garantias", headers=h_dir).json()
    reg_gt_dir = next(x for x in lista_dir if x["id"] == d_gt["id"])
    assert reg_gt_dir["costo_garantia_usd"] == 12.0

    # 3. CAMBIO_UPGRADE (Venta 2: HP $400 -> Dell $600 => +$200 diferencia + sube base comisión)
    v2 = _crear_venta_rapida(cliente, h_as, ctx, ctx["eq_hp_3"], 400.0)
    r_up = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v2["id"],
            "equipo_origen_id": ctx["eq_hp_3"],
            "equipo_destino_id": ctx["eq_dell_1"],
            "tipo_resolucion": "CAMBIO_UPGRADE",
            "estado_reingreso_origen": "LISTO",
            "instrumento_id": ctx["inst_usd_id"],
            "referencia_pago": "UPG-777",
            "motivo": "Cliente desea subir a Core i7",
        },
    )
    assert r_up.status_code == 201, r_up.text
    assert r_up.json()["diferencia_usd"] == 200.0
    assert r_up.json()["diferencia_promo_usd"] == 200.0

    # 4. CAMBIO_DOWNGRADE (Venta 3: Dell $600 -> HP $400 => -$200)
    v3 = _crear_venta_rapida(cliente, h_as, ctx, ctx["eq_dell_2"], 600.0)
    # Asesora NO puede reembolsar efectivo en Downgrade (403)
    r_down_403 = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v3["id"],
            "equipo_origen_id": ctx["eq_dell_2"],
            "equipo_destino_id": ctx["eq_hp_3"],  # volvió a LISTO tras el upgrade anterior
            "tipo_resolucion": "CAMBIO_DOWNGRADE",
            "estado_reingreso_origen": "LISTO",
            "dejar_saldo_favor": False,
            "instrumento_id": ctx["inst_usd_id"],
            "motivo": "Intento de egreso por asesora",
        },
    )
    assert r_down_403.status_code == 403

    # Asesora SÍ puede dejar Saldo a Favor ($200)
    r_down_ok = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v3["id"],
            "equipo_origen_id": ctx["eq_dell_2"],
            "equipo_destino_id": ctx["eq_hp_3"],
            "tipo_resolucion": "CAMBIO_DOWNGRADE",
            "estado_reingreso_origen": "LISTO",
            "dejar_saldo_favor": True,
            "motivo": "Cliente prefiere equipo más liviano y deja saldo a favor",
        },
    )
    assert r_down_ok.status_code == 201, r_down_ok.text
    assert r_down_ok.json()["diferencia_usd"] == -200.0

    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        ter = bd.query(Tercero).filter(Tercero.id == ctx["cliente_id"]).first()
        assert ter is not None and float(ter.saldo_favor_usd) == 200.0
    finally:
        bd.close()

    # 5. REEMBOLSO_TOTAL: 403 para ASESORA, 201 para DIRECCION, marca venta DEVUELTA y excluye comisión
    r_reemb_403 = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_as,
        json={
            "venta_id": v1["id"],
            "tipo_resolucion": "REEMBOLSO_TOTAL",
            "estado_reingreso_origen": "POR_PREPARAR",
            "instrumento_id": ctx["inst_usd_id"],
            "motivo": "Cliente solicita devolución total",
        },
    )
    assert r_reemb_403.status_code == 403

    r_reemb_dir = cliente.post(
        "/api/devoluciones-garantias",
        headers=h_dir,
        json={
            "venta_id": v1["id"],
            "tipo_resolucion": "REEMBOLSO_TOTAL",
            "estado_reingreso_origen": "POR_PREPARAR",
            "instrumento_id": ctx["inst_usd_id"],
            "referencia_pago": "EGR-901",
            "motivo": "Devolución total autorizada por Dirección",
        },
    )
    assert r_reemb_dir.status_code == 201, r_reemb_dir.text

    # Comisiones: v1 ($400) DEVUELTA (excluida), v2 ($400 + $200 upgrade = $600), v3 ($600 - $200 downgrade = $400) -> Total = $1000 -> 1% = $10.00
    hoy_d = obtener_fecha_hoy()
    rep_com = cliente.get(
        f"/api/finanzas/comisiones?mes={hoy_d.month}&anio={hoy_d.year}",
        headers=h_dir,
    )
    assert rep_com.status_code == 200, rep_com.text
    fila_as = next(c for c in rep_com.json()["comisiones"] if c["usuario_id"] == ctx["asesora_id"])
    assert fila_as["ventas_promo_usd"] == 1000.0
    assert fila_as["comision_ventas_1_usd"] == 10.0


def test_lista_precios_solo_listo_sin_costos_y_pdf(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    h_as = ctx["headers_as"]

    resp_json = cliente.get("/api/catalogo/lista-precios?sucursal_id=1", headers=h_as)
    assert resp_json.status_code == 200, resp_json.text
    data = resp_json.json()
    assert data["total_modelos"] == 2
    assert data["total_unidades"] == 5  # 3 HP + 2 Dell LISTO (excluye 1 HOSPITAL)
    for item in data["items"]:
        assert "costo" not in str(item).lower()
        assert "margen" not in str(item).lower()
        assert "proveedor" not in str(item).lower()
        assert "Hospital" not in item["modelo"]

    resp_pdf = cliente.get("/api/catalogo/lista-precios-pdf?sucursal_id=1", headers=h_as)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    texto_pdf = _extraer_texto_pdf(resp_pdf.content)
    assert "LISTA DE PRECIOS DISPONIBLES" in texto_pdf
    assert "HP EliteBook 840 G7" in texto_pdf
    assert "Dell Latitude 7420" in texto_pdf
    assert "Equipo En Hospital" not in texto_pdf
    assert "260.00" not in texto_pdf  # costo interno nunca expuesto


def test_cotizacion_asesora_pdf_sin_descontar_stock_y_conversion_a_venta(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    h_as = ctx["headers_as"]

    # Crear cotización por ASESORA
    resp_cot = cliente.post(
        "/api/cotizaciones",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "vigencia_horas": 48,
            "modalidad_precio": "CASHEA",
            "nota": "Incluye bolso de cortesía",
            "items": [
                {"equipo_id": ctx["eq_hp_1"], "cantidad": 1},
                {"articulo_id": ctx["art_cargador_id"], "cantidad": 1, "precio_pactado_usd": 0},
            ],
        },
    )
    assert resp_cot.status_code == 201, resp_cot.text
    cot = resp_cot.json()
    assert cot["numero_cotizacion"].startswith("COT-")
    assert cot["estado"] == "VIGENTE"
    assert cot["total_promo_usd"] == 400.0

    # Verificar que el equipo SIGUE en estado LISTO (no descontó inventario)
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        eq = bd.query(Equipo).filter(Equipo.id == ctx["eq_hp_1"]).first()
        assert eq is not None and eq.estado == EstadoEquipo.LISTO.value
    finally:
        bd.close()

    # Descargar PDF de cotización y verificar disclaimer y Cédula de Identidad
    resp_pdf = cliente.get(f"/api/cotizaciones/{cot['id']}/pdf", headers=h_as)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    txt_pdf = _extraer_texto_pdf(resp_pdf.content)
    assert cot["numero_cotizacion"] in txt_pdf
    assert "Cédula de Identidad" in txt_pdf or "dula de Identidad" in txt_pdf
    assert "Presupuesto sujeto a disponibilidad de inventario" in txt_pdf

    # Convertir cotización a venta enviando cotizacion_id
    resp_vta = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "cotizacion_id": cot["id"],
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [{"instrumento_id": ctx["inst_usd_id"], "monto_moneda_origen": 400.0}],
        },
    )
    assert resp_vta.status_code == 201, resp_vta.text
    vta = resp_vta.json()

    # Verificar que la cotización pasó a CONVERTIDA y quedó vinculada a la venta
    cot_post = cliente.get(f"/api/cotizaciones/{cot['id']}", headers=h_as).json()
    assert cot_post["estado"] == "CONVERTIDA"
    assert cot_post["venta_id"] == vta["id"]

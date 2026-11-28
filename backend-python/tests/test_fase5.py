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
from app.modelos import CatalogoArticulo, CatalogoPrecio, Sucursal, TasaDiaria, TipoArticulo
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
        if not bd.query(TasaDiaria).filter(TasaDiaria.fecha == hoy_d).first():
            bd.add(
                TasaDiaria(
                    fecha=hoy_d,
                    tasa_bcv=Decimal("50.00"),
                    tasa_usdt=Decimal("60.00"),
                    recargo_porcentaje=Decimal("20.00"),
                )
            )
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
            "sin_cargador": True,
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

    # Configurar 2 HP con 8GB/256GB ($400) y 1 HP con 16GB/512GB ($460) para validar agrupación por características
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        hp1 = bd.query(Equipo).filter(Equipo.id == ctx["eq_hp_1"]).first()
        hp2 = bd.query(Equipo).filter(Equipo.id == ctx["eq_hp_2"]).first()
        hp3 = bd.query(Equipo).filter(Equipo.id == ctx["eq_hp_3"]).first()
        assert hp1 and hp2 and hp3
        hp1.modelo = "HP EliteBook 840 G7"
        hp1.configuracion = "Core i5 · 8GB RAM · 256GB SSD"
        hp2.modelo = "HP EliteBook 840 G7"
        hp2.configuracion = "Core i5 · 8GB RAM · 256GB SSD"
        hp3.modelo = "HP EliteBook 840 G7"
        hp3.configuracion = "Core i5 · 16GB RAM · 512GB SSD"
        hp3.precio_promo_usd = Decimal("460.00")
        bd.commit()
    finally:
        bd.close()

    # 1. Modo PROMO (solo USD Divisas, sin Regular ni Bs, sin seriales ni costos)
    resp_promo = cliente.get(
        "/api/catalogo/lista-precios?sucursal_id=1&tipo_precio=PROMO", headers=h_as
    )
    assert resp_promo.status_code == 200, resp_promo.text
    data_promo = resp_promo.json()
    assert data_promo["tipo_precio"] == "PROMO"
    assert "tasa_bcv" not in data_promo
    assert data_promo["total_modelos"] == 3  # 2 configs de HP + 1 Dell
    assert data_promo["total_unidades"] == 5  # excluye 1 HOSPITAL
    hp_8gb = next(i for i in data_promo["items"] if "8GB RAM" in i["caracteristicas"])
    hp_16gb = next(i for i in data_promo["items"] if "16GB RAM" in i["caracteristicas"])
    assert hp_8gb["disponibles"] == 2 and hp_8gb["precio_usd"] == 400.0
    assert hp_16gb["disponibles"] == 1 and hp_16gb["precio_usd"] == 460.0
    for item in data_promo["items"]:
        assert "precio_bs" not in item
        assert "serial" not in str(item).lower()
        assert "costo" not in str(item).lower()
        assert "margen" not in str(item).lower()
        assert "proveedor" not in str(item).lower()
        assert "Hospital" not in item["modelo"]

    pdf_promo = cliente.get(
        "/api/catalogo/lista-precios-pdf?sucursal_id=1&tipo_precio=PROMO", headers=h_as
    )
    assert pdf_promo.status_code == 200
    assert pdf_promo.headers["content-type"] == "application/pdf"
    txt_promo = _extraer_texto_pdf(pdf_promo.content)
    assert "LISTA DE PRECIOS DISPONIBLES" in txt_promo
    assert "8GB RAM" in txt_promo
    assert "16GB RAM" in txt_promo
    assert "$400.00" in txt_promo
    assert "$460.00" in txt_promo
    assert "Bs." not in txt_promo
    assert "Precio Regular" not in txt_promo
    assert "SN-HP-001" not in txt_promo
    assert "SN-DELL-001" not in txt_promo
    assert "Equipo En Hospital" not in txt_promo
    assert "260.00" not in txt_promo

    # 2. Modo REGULAR (solo Regular en USD y Bs a tasa BCV, sin seriales ni costos)
    resp_reg = cliente.get(
        "/api/catalogo/lista-precios?sucursal_id=1&tipo_precio=REGULAR", headers=h_as
    )
    assert resp_reg.status_code == 200, resp_reg.text
    data_reg = resp_reg.json()
    assert data_reg["tipo_precio"] == "REGULAR"
    assert data_reg["tasa_bcv"] == 50.0
    hp_8gb_reg = next(i for i in data_reg["items"] if "8GB RAM" in i["caracteristicas"])
    assert hp_8gb_reg["precio_usd"] == 480.0  # 400 * 1.20
    assert hp_8gb_reg["precio_bs"] == 24000.0  # 480 * 50

    pdf_reg = cliente.get(
        "/api/catalogo/lista-precios-pdf?sucursal_id=1&tipo_precio=REGULAR", headers=h_as
    )
    assert pdf_reg.status_code == 200
    txt_reg = _extraer_texto_pdf(pdf_reg.content)
    assert "Tasa BCV ref." in txt_reg
    assert "$480.00" in txt_reg
    assert "Bs. 24,000.00" in txt_reg
    assert "SN-HP-001" not in txt_reg
    assert "260.00" not in txt_reg


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
            "sin_cargador": True,
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


def test_comisiones_filtros_rango_usuario_lider_multitienda_y_tecnico(cliente: TestClient) -> None:
    from datetime import timedelta

    ctx = _preparar_escenario_base(cliente)
    h_dir = ctx["headers_dir"]
    h_as = ctx["headers_as"]

    # Crear Líder multi-tienda y Técnico
    r_lider = cliente.post(
        "/api/usuarios",
        headers=h_dir,
        json={
            "nombre": "Mariana Líder",
            "correo": "mariana.lider.f5@tekio.com",
            "clave": "Password123!",
            "rol": "LIDER",
            "sucursal_id": 1,
        },
    )
    assert r_lider.status_code == 201, r_lider.text
    lider_id = r_lider.json()["id"]

    r_tec = cliente.post(
        "/api/usuarios",
        headers=h_dir,
        json={
            "nombre": "Luis Técnico",
            "correo": "luis.tec.f5@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert r_tec.status_code == 201, r_tec.text
    tecnico_id = r_tec.json()["id"]

    # Crear artículo SERVICIO (Mano de Obra $80 Promo)
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        hoy_d = obtener_fecha_hoy()
        art_st = CatalogoArticulo(
            sku="ST-MANT-80",
            descripcion="Mantenimiento Preventivo Completo",
            tipo=TipoArticulo.SERVICIO.value,
            categoria="Servicios",
        )
        bd.add(art_st)
        bd.flush()
        bd.add(
            CatalogoPrecio(
                articulo_id=art_st.id,
                precio_promo_usd=Decimal("80.00"),
                costo_referencia_usd=Decimal("0.00"),
                fecha_vigencia=hoy_d,
            )
        )
        bd.commit()
        art_st_id = art_st.id
    finally:
        bd.close()

    # Venta 1 hoy: Asesora vende equipo $400 + Servicio Técnico $80 con Luis Técnico
    r_v1 = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "tecnico_id": tecnico_id,
            "sin_cargador": True,
            "items": [
                {"equipo_id": ctx["eq_hp_1"], "cantidad": 1},
                {"articulo_id": art_st_id, "cantidad": 1, "descripcion_servicio": "Limpieza y pasta térmica"},
            ],
            "pagos": [{"instrumento_id": ctx["inst_usd_id"], "monto_moneda_origen": 480.0}],
        },
    )
    assert r_v1.status_code == 201, r_v1.text

    # Venta 2 hoy: Líder vende equipo $600
    r_v2 = cliente.post(
        "/api/ventas",
        headers=h_dir,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": lider_id,
            "sin_cargador": True,
            "items": [{"equipo_id": ctx["eq_dell_1"], "cantidad": 1}],
            "pagos": [{"instrumento_id": ctx["inst_usd_id"], "monto_moneda_origen": 600.0}],
        },
    )
    assert r_v2.status_code == 201, r_v2.text

    hoy_str = obtener_fecha_hoy().isoformat()

    # 1. Filtrar exactamente por fecha_inicio=hoy & fecha_fin=hoy (todos)
    resp_all = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
        headers=h_dir,
    )
    assert resp_all.status_code == 200, resp_all.text
    body = resp_all.json()
    assert body["fecha_inicio"] == hoy_str
    assert body["fecha_fin"] == hoy_str
    assert len(body["operaciones"]) == 4  # venta asesora + ST técnico + venta líder + líder 0.5% equipo
    assert "costo" not in str(body).lower()

    fila_as = next(c for c in body["comisiones"] if c["usuario_id"] == ctx["asesora_id"])
    assert fila_as["ventas_promo_usd"] == 400.0
    assert fila_as["comision_ventas_1_usd"] == 4.0  # 1% de $400 (excluye ST $80)

    fila_tec = next(c for c in body["comisiones"] if c["usuario_id"] == tecnico_id)
    assert fila_tec["comision_servicios_50_usd"] == 40.0  # 50% de $80
    assert fila_tec["total_comision_usd"] == 40.0

    # 2. Filtrar por usuario_id=lider_id: mantiene 1% propio ($6) + 0.5% del equipo ($400 * 0.5% = $2) = $8
    resp_lider = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}&usuario_id={lider_id}",
        headers=h_dir,
    )
    assert resp_lider.status_code == 200, resp_lider.text
    body_l = resp_lider.json()
    assert len(body_l["comisiones"]) == 1
    fila_l = body_l["comisiones"][0]
    assert fila_l["ventas_promo_usd"] == 600.0
    assert fila_l["comision_ventas_1_usd"] == 6.0
    assert fila_l["comision_lider_05_usd"] == 2.0
    assert fila_l["total_comision_usd"] == 8.0
    assert "telefono" in fila_l

    # 3. Rango pasado sin ventas debe devolver 0 operaciones y $0
    ayer = (obtener_fecha_hoy() - timedelta(days=5)).isoformat()
    resp_vacio = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={ayer}&fecha_fin={ayer}&usuario_id={ctx['asesora_id']}",
        headers=h_dir,
    )
    assert resp_vacio.status_code == 200
    assert resp_vacio.json()["comisiones"][0]["total_comision_usd"] == 0.0
    assert len(resp_vacio.json()["operaciones"]) == 0


def test_personal_sin_acceso_pos_comisiones_bloqueo_login_y_validacion(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    h_dir = ctx["headers_dir"]
    h_as = ctx["headers_as"]

    # 1. Crear asesora ONLINE sin correo ni contraseña (tiene_acceso = False)
    r_crear = cliente.post(
        "/api/usuarios",
        headers=h_dir,
        json={
            "nombre": "Sofía Online",
            "rol": "ASESORA",
            "modalidad": "ONLINE",
            "telefono": "0412-9998877",
            "cedula": "V-27111222",
            "tiene_acceso": False,
            "sucursal_id": 1,
        },
    )
    assert r_crear.status_code == 201, r_crear.text
    sofia = r_crear.json()
    assert sofia["tiene_acceso"] is False
    assert sofia["correo"] is None
    assert sofia["modalidad"] == "ONLINE"
    assert sofia["telefono"] == "0412-9998877"

    # Crear una segunda asesora sin correo para verificar múltiples NULL en columna unique
    r_crear2 = cliente.post(
        "/api/usuarios",
        headers=h_dir,
        json={
            "nombre": "Andrea Online",
            "rol": "ASESORA",
            "modalidad": "ONLINE",
            "tiene_acceso": False,
        },
    )
    assert r_crear2.status_code == 201, r_crear2.text

    # 2. Verificar que aparece en /api/usuarios/operativos (selector POS) y genera comisión 1%
    ops = cliente.get("/api/usuarios/operativos", headers=h_as).json()
    sofia_op = next((u for u in ops if u["id"] == sofia["id"]), None)
    assert sofia_op is not None
    assert sofia_op["tiene_acceso"] is False
    assert sofia_op["modalidad"] == "ONLINE"

    r_vta = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": sofia["id"],
            "sin_cargador": True,
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [{"instrumento_id": ctx["inst_usd_id"], "monto_moneda_origen": 400.0}],
        },
    )
    assert r_vta.status_code == 201, r_vta.text

    hoy_str = obtener_fecha_hoy().isoformat()
    rep = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}&usuario_id={sofia['id']}",
        headers=h_dir,
    )
    assert rep.status_code == 200, rep.text
    fila_sofia = rep.json()["comisiones"][0]
    assert fila_sofia["ventas_promo_usd"] == 400.0
    assert fila_sofia["comision_ventas_1_usd"] == 4.0
    assert fila_sofia["telefono"] == "0412-9998877"

    # 3. Confirmar que un colaborador sin acceso NO puede iniciar sesión en /api/auth/login
    r_login_fail = cliente.post(
        "/api/auth/login",
        json={"correo": "sofia@tekio.com", "clave": "Password123!"},
    )
    assert r_login_fail.status_code == 401

    # Incluso si se le asignara acceso y luego se desactiva tiene_acceso, el login es rechazado
    r_con_acc = cliente.put(
        f"/api/usuarios/{sofia['id']}",
        headers=h_dir,
        json={
            "nombre": "Sofía Online",
            "rol": "ASESORA",
            "modalidad": "ONLINE",
            "telefono": "0412-9998877",
            "tiene_acceso": True,
            "correo": "sofia.online@tekio.com",
            "clave": "Password123!",
            "sucursal_id": 1,
        },
    )
    assert r_con_acc.status_code == 200, r_con_acc.text
    r_revocar = cliente.put(
        f"/api/usuarios/{sofia['id']}",
        headers=h_dir,
        json={
            "nombre": "Sofía Online",
            "rol": "ASESORA",
            "modalidad": "ONLINE",
            "telefono": "0412-9998877",
            "tiene_acceso": False,
            "sucursal_id": 1,
        },
    )
    assert r_revocar.status_code == 200
    r_login_rev = cliente.post(
        "/api/auth/login",
        json={"correo": "sofia.online@tekio.com", "clave": "Password123!"},
    )
    assert r_login_rev.status_code in (401, 403)

    # 4. Si tiene_acceso = True sin correo -> 422 de validación
    r_422 = cliente.post(
        "/api/usuarios",
        headers=h_dir,
        json={
            "nombre": "Sin Correo Con Acceso",
            "rol": "ASESORA",
            "tiene_acceso": True,
            "clave": "Password123!",
        },
    )
    assert r_422.status_code == 422


def test_tasas_automaticas_fallback_bloqueo_y_recargo_diario_en_pos(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta
    from app.servicios import tasas_service

    ctx = _preparar_escenario_base(cliente)
    h_dir = ctx["headers_dir"]
    h_as = ctx["headers_as"]

    # Eliminar la tasa de hoy y dejar solo una tasa de ayer para probar cambio de día + fallback
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        hoy_d = obtener_fecha_hoy()
        bd.query(TasaDiaria).filter(TasaDiaria.fecha == hoy_d).delete()
        bd.add(
            TasaDiaria(
                fecha=hoy_d - timedelta(days=1),
                tasa_bcv=Decimal("52.5000"),
                tasa_usdt=Decimal("63.0000"),
                recargo_porcentaje=Decimal("18.00"),
                recargo_confirmado_hoy=True,
                fuente="ve.dolarapi.com",
            )
        )
        bd.commit()
    finally:
        bd.close()

    # 1. Simular caída de red en ve.dolarapi.com -> debe hacer fallback a la última tasa de BD
    #    y arrancar con recargo_confirmado_hoy = False
    def _fallo_red(*_args, **_kwargs):
        raise RuntimeError("Timeout de red simulado")

    monkeypatch.setattr(tasas_service, "consultar_dolarapi_venezuela", _fallo_red)
    r_fb = cliente.get("/api/finanzas/tasas/hoy", headers=h_as)
    assert r_fb.status_code == 200, r_fb.text
    d_fb = r_fb.json()
    assert d_fb["fuente"] == "fallback_db"
    assert d_fb["tasa_bcv"] == 52.5
    assert d_fb["tasa_usdt"] == 63.0
    assert d_fb["recargo_confirmado_hoy"] is False

    # 2. Mientras recargo_confirmado_hoy == False, venta Regular (Bs) y cotización Regular deben bloquearse con 400
    insts = cliente.get("/api/finanzas/instrumentos", headers=h_dir).json()
    inst_bs = next(i for i in insts if i["moneda"] == "BS" and "cashea" not in i["nombre"].lower())

    r_vta_bloq = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "sin_cargador": True,
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [{"instrumento_id": inst_bs["id"], "monto_moneda_origen": 25000.0}],
        },
    )
    assert r_vta_bloq.status_code == 400
    assert "recargo del día" in r_vta_bloq.json()["detail"].lower()

    r_cot_bloq = cliente.post(
        "/api/cotizaciones",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "modalidad_precio": "REGULAR",
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
        },
    )
    assert r_cot_bloq.status_code == 400

    # 3. Mockear respuesta exitosa de ve.dolarapi.com y forzar sincronización (BCV 60, USDT 72)
    monkeypatch.setattr(
        tasas_service,
        "consultar_dolarapi_venezuela",
        lambda timeout=5.0: (Decimal("60.0000"), Decimal("72.0000"), "ve.dolarapi.com"),
    )
    r_sync = cliente.post("/api/finanzas/tasas/sincronizar", headers=h_as)
    assert r_sync.status_code == 200, r_sync.text
    d_sync = r_sync.json()
    assert d_sync["fuente"] == "ve.dolarapi.com"
    assert d_sync["tasa_bcv"] == 60.0
    assert d_sync["tasa_usdt"] == 72.0
    assert d_sync["recargo_confirmado_hoy"] is False

    # 4. Confirmar recargo diario del 25% -> recargo_confirmado_hoy pasa a True
    r_conf = cliente.post(
        "/api/finanzas/tasas/recargo-diario",
        headers=h_as,
        json={"porcentaje_recargo": 25.0},
    )
    assert r_conf.status_code == 200, r_conf.text
    d_conf = r_conf.json()
    assert d_conf["recargo_confirmado_hoy"] is True
    assert d_conf["porcentaje_recargo"] == 25.0

    # 5. POS calcula Precio Regular USD ($400 * 1.25 = $500) y Bs ($500 * 60 = Bs 30,000) automáticamente
    r_sim = cliente.post(
        "/api/ventas/simular",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [],
        },
    )
    assert r_sim.status_code == 200, r_sim.text
    sim = r_sim.json()
    assert sim["total_promo_usd"] == 400.0
    assert sim["total_regular_usd"] == 500.0
    assert sim["falta_bs"] == 30000.0


def test_liquidacion_comisiones_egreso_antiduplicados_y_cierre_caja_pdf(cliente: TestClient) -> None:
    from app.modelos_finanzas import Pago

    ctx = _preparar_escenario_base(cliente)
    h_dir = ctx["headers_dir"]
    h_as = ctx["headers_as"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # 1. Crear venta 1 en USD Efectivo ($400 -> comisión 1% = $4.00)
    insts = cliente.get("/api/finanzas/instrumentos", headers=h_dir).json()
    inst_ef_usd = next(i for i in insts if i["moneda"] == "USD" and "efectivo" in i["nombre"].lower())
    inst_cashea = next(i for i in insts if "cashea" in i["nombre"].lower())

    r_v1 = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "sin_cargador": True,
            "items": [{"equipo_id": ctx["eq_hp_1"], "cantidad": 1}],
            "pagos": [{"instrumento_id": inst_ef_usd["id"], "monto_moneda_origen": 400.0}],
        },
    )
    assert r_v1.status_code == 201, r_v1.text

    # 2. Crear venta 2 con Cashea ($600 Promo -> $720 Regular: $288 inicial USD + $432 Cashea)
    r_v2 = cliente.post(
        "/api/ventas",
        headers=h_as,
        json={
            "sucursal_id": 1,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "cashea_numero_orden": "CSH-FASE5-001",
            "sin_cargador": True,
            "items": [{"equipo_id": ctx["eq_dell_1"], "cantidad": 1}],
            "pagos": [
                {"instrumento_id": inst_ef_usd["id"], "monto_moneda_origen": 288.0},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 432.0},
            ],
        },
    )
    assert r_v2.status_code == 201, r_v2.text

    # Verificar que comisiones pendientes suman $10.00 ($4 + $6)
    r_pend = cliente.get(
        f"/api/finanzas/comisiones?fecha_inicio={hoy_str}&fecha_fin={hoy_str}&usuario_id={ctx['asesora_id']}&estado=PENDIENTE",
        headers=h_dir,
    )
    assert r_pend.status_code == 200, r_pend.text
    fila_pend = r_pend.json()["comisiones"][0]
    assert fila_pend["estado_comision"] == "PENDIENTE"
    assert fila_pend["monto_pendiente_usd"] == 10.0

    # 3. Liquidar comisiones pendientes -> crea LIQ-0001 + EGRESO automático de $10.00
    r_liq = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=h_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": inst_ef_usd["id"],
            "referencia": "PAG-COM-01",
            "notas": "Pago quincena",
        },
    )
    assert r_liq.status_code == 201, r_liq.text
    liq = r_liq.json()
    assert liq["codigo"].startswith("LIQ-")
    assert liq["monto_total_usd"] == 10.0
    assert liq["pago_egreso_id"] is not None

    # Verificar EGRESO real en tabla pagos con tipo LIQUIDACION_COMISION
    bd = cliente.sesion_factory()  # type: ignore[attr-defined]
    try:
        egreso = bd.query(Pago).filter(Pago.id == liq["pago_egreso_id"]).first()
        assert egreso is not None
        assert egreso.tipo_movimiento == "EGRESO"
        assert egreso.tipo_documento == "LIQUIDACION_COMISION"
        assert float(egreso.usd_nominal) == 10.0
    finally:
        bd.close()

    # 4. Anti-duplicados: intentar liquidar de nuevo el mismo rango debe fallar con 400
    r_liq_dup = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=h_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": inst_ef_usd["id"],
        },
    )
    assert r_liq_dup.status_code == 409

    # PDF de comprobante de liquidación
    r_liq_pdf = cliente.get(f"/api/finanzas/liquidaciones/{liq['id']}/pdf", headers=h_dir)
    assert r_liq_pdf.status_code == 200
    assert r_liq_pdf.headers["content-type"] == "application/pdf"
    txt_liq = _extraer_texto_pdf(r_liq_pdf.content)
    assert liq["codigo"] in txt_liq
    assert "COMPROBANTE DE LIQUID" in txt_liq

    # 5. Preview de Cierre de Caja Diario:
    #    - Incluye ventas ($1000), ingresos ($688), Cashea ($432) y desglose por asesor
    #    - Excluye automáticamente el egreso LIQUIDACION_COMISION ($10) del cuadre diario
    r_prev = cliente.get(
        f"/api/finanzas/cierre-caja/preview?fecha={hoy_str}&sucursal_id=1",
        headers=h_dir,
    )
    assert r_prev.status_code == 200, r_prev.text
    prev = r_prev.json()
    assert prev["cantidad_ventas"] == 2
    assert prev["total_ventas_usd"] == 1000.0
    assert prev["total_ingresos_usd"] == 688.0
    assert prev["total_cashea_usd"] == 432.0
    assert prev["total_egresos_usd"] == 0.0  # LIQUIDACION_COMISION excluida del cierre diario
    assert prev["efectivo_esperado_usd"] == 688.0  # 400 + 288
    assert len(prev["desglose_asesores"]) == 1
    assert prev["desglose_asesores"][0]["cantidad_ventas"] == 2
    assert prev["desglose_asesores"][0]["total_promo_usd"] == 1000.0

    # 6. Guardar Cierre de Caja declarando $690 (+$2 sobrante) y descargar PDF
    r_cierre = cliente.post(
        "/api/finanzas/cierre-caja",
        headers=h_dir,
        json={
            "fecha": hoy_str,
            "sucursal_id": 1,
            "efectivo_declarado_usd": 690.0,
            "observaciones": "Cierre verificado al final de la jornada",
        },
    )
    assert r_cierre.status_code == 201, r_cierre.text
    cierre = r_cierre.json()
    assert cierre["diferencia_usd"] == 2.0

    r_cierre_pdf = cliente.get(f"/api/finanzas/cierre-caja/{cierre['id']}/pdf", headers=h_dir)
    assert r_cierre_pdf.status_code == 200
    assert r_cierre_pdf.headers["content-type"] == "application/pdf"
    txt_cierre = _extraer_texto_pdf(r_cierre_pdf.content)
    assert "CIERRE DE CAJA DIARIO" in txt_cierre
    assert "Ventas por Asesor" in txt_cierre
    assert "$690.00" in txt_cierre

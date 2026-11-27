from __future__ import annotations

import io
import zipfile
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# Colores oficiales del Manual de Marca Tekio Electronics (Light-First, sin negro)
FILL_ENCABEZADO = PatternFill(start_color="F6F6F6", end_color="F6F6F6", fill_type="solid")
FILL_INSTRUCCION = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
FONT_ENCABEZADO = Font(name="Calibri", size=11, bold=True, color="191818")
FONT_INSTRUCCION = Font(name="Calibri", size=9.5, italic=True, color="9A3412")
FONT_DATO = Font(name="Calibri", size=10.5, color="191818")
BORDE_NARANJA = Border(
    left=Side(style="thin", color="E5E7EB"),
    right=Side(style="thin", color="E5E7EB"),
    top=Side(style="thin", color="E5E7EB"),
    bottom=Side(style="medium", color="E85A28"),
)
BORDE_SUAVE = Border(
    left=Side(style="thin", color="E5E7EB"),
    right=Side(style="thin", color="E5E7EB"),
    top=Side(style="thin", color="E5E7EB"),
    bottom=Side(style="thin", color="E5E7EB"),
)

PLANTILLAS_APERTURA_META: dict[str, dict[str, str]] = {
    "saldos_cajas_bancos": {
        "paso": "1",
        "archivo": "01_Saldos_Cajas_Bancos.xlsx",
        "titulo": "Saldos Iniciales de Efectivo, Cajas y Bancos",
    },
    "inventario_equipos": {
        "paso": "2",
        "archivo": "02_Inventario_Equipos_Serial.xlsx",
        "titulo": "Inventario Inicial de Equipos por Serial",
    },
    "inventario_componentes": {
        "paso": "3",
        "archivo": "03_Inventario_Componentes_Accesorios.xlsx",
        "titulo": "Inventario de Componentes, Repuestos y Accesorios",
    },
    "cxc_cashea": {
        "paso": "4",
        "archivo": "04_CxC_y_Cashea_Pendiente.xlsx",
        "titulo": "Cuentas por Cobrar y Órdenes Cashea Pendientes",
    },
    "cxp_prestamos": {
        "paso": "5",
        "archivo": "05_CxP_y_Prestamos_Iniciales.xlsx",
        "titulo": "Cuentas por Pagar Proveedores y Préstamos Activos",
    },
    "personal_nomina_socios": {
        "paso": "6",
        "archivo": "06_Personal_Nomina_Socios.xlsx",
        "titulo": "Personal, Estructura de Nómina y Socios",
    },
}


def _estilizar_hoja(
    ws: Any,
    encabezados: list[str],
    instrucciones: list[str],
    ejemplos: list[list[Any]],
    validaciones: dict[int, list[str]] | None = None,
) -> None:
    ws.append(encabezados)
    ws.append(instrucciones)
    for fila in ejemplos:
        ws.append(fila)

    ws.freeze_panes = "A3"
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 22

    for col_idx, titulo in enumerate(encabezados, start=1):
        c1 = ws.cell(row=1, column=col_idx)
        c1.fill = FILL_ENCABEZADO
        c1.font = FONT_ENCABEZADO
        c1.border = BORDE_NARANJA
        c1.alignment = Alignment(horizontal="center", vertical="center")

        c2 = ws.cell(row=2, column=col_idx)
        c2.fill = FILL_INSTRUCCION
        c2.font = FONT_INSTRUCCION
        c2.border = BORDE_SUAVE
        c2.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        ancho = max(len(titulo) + 6, 18)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(ancho, 36)

    for row_idx in range(3, ws.max_row + 1):
        for col_idx in range(1, len(encabezados) + 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.font = FONT_DATO
            c.border = BORDE_SUAVE

    if validaciones:
        for col_idx, opciones in validaciones.items():
            letra = get_column_letter(col_idx)
            formula = '"' + ",".join(opciones) + '"'
            dv = DataValidation(type="list", formula1=formula, allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{letra}3:{letra}500")


def generar_plantilla_oficial_apertura(tipo: str) -> bytes:
    """Genera cualquiera de las 6 planillas oficiales .xlsx de Apertura 01/12/2026."""
    wb = Workbook()
    ws = wb.active

    if tipo == "saldos_cajas_bancos":
        ws.title = "Saldos_Cajas_Bancos"
        _estilizar_hoja(
            ws,
            encabezados=[
                "sucursal",
                "instrumento_o_cuenta",
                "tipo",
                "moneda",
                "saldo_inicial",
                "tasa_bcv_apertura",
                "observaciones",
            ],
            instrucciones=[
                "Tekio Central | Tekio Gran Bazar | Depósito / Tekio Support | Administración",
                "Nombre exacto de la caja, banco o billetera",
                "EFECTIVO_USD | CAJA_CHICA | BANCO_BS | PAGO_MOVIL | ZELLE | USDT | OTRO",
                "USD | BS",
                "Monto exacto al 01/12/2026 (>= 0)",
                "Tasa BCV oficial del 01/12/2026 (ej. 52.50)",
                "Nota o referencia de conteo físico",
            ],
            ejemplos=[
                ["Tekio Central", "Efectivo divisas", "EFECTIVO_USD", "USD", 500.00, 52.50, "Conteo físico bóveda Tekio Central"],
                ["Tekio Gran Bazar", "Efectivo divisas", "EFECTIVO_USD", "USD", 350.00, 52.50, "Conteo físico bóveda Gran Bazar"],
                ["Tekio Central", "Caja Chica Tekio Central", "CAJA_CHICA", "USD", 60.00, 52.50, "Fondo fijo oficial de apertura"],
                ["Tekio Gran Bazar", "Caja Chica Tekio Gran Bazar", "CAJA_CHICA", "USD", 60.00, 52.50, "Fondo fijo oficial de apertura"],
                ["Administración", "Zelle", "ZELLE", "USD", 1200.00, 52.50, "Saldo conciliado al 01/12/2026"],
                ["Administración", "Binance (USDT)", "USDT", "USD", 800.00, 52.50, "Billetera corporativa"],
                ["Administración", "BNC Jurídico (Bs)", "BANCO_BS", "BS", 52500.00, 52.50, "Equivalente USD calculado a tasa BCV"],
            ],
            validaciones={
                1: ["Tekio Central", "Tekio Gran Bazar", "Depósito / Tekio Support", "Administración"],
                3: ["EFECTIVO_USD", "CAJA_CHICA", "BANCO_BS", "PAGO_MOVIL", "ZELLE", "USDT", "OTRO"],
                4: ["USD", "BS"],
            },
        )

    elif tipo == "inventario_equipos":
        ws.title = "Inventario_Equipos"
        _estilizar_hoja(
            ws,
            encabezados=[
                "sucursal",
                "serial",
                "marca",
                "modelo",
                "procesador",
                "ram",
                "almacenamiento",
                "pantalla",
                "estado_actual",
                "condicion_fisica",
                "incluye_cargador",
                "costo_acumulado_usd",
                "precio_promo_usd",
                "precio_regular_usd",
                "es_consignacion",
                "proveedor_consignacion",
                "observaciones",
            ],
            instrucciones=[
                "Tekio Central | Tekio Gran Bazar | Depósito / Tekio Support",
                "Serial único irrepetible (en mayúsculas)",
                "Ej. Lenovo, Dell, HP, Apple",
                "Modelo exacto (ej. ThinkPad T14 Gen 2)",
                "Ej. Core i5-1145G7",
                "Ej. 16GB",
                "Ej. 512GB NVMe",
                "Ej. 14 FHD",
                "LISTO | POR_PREPARAR | HOSPITAL",
                "EXCELENTE | BUENO | CON_DETALLES | CON_FALLA",
                "SI | NO",
                "Costo total acumulado USD (propio)",
                "Precio Promo divisas USD",
                "Precio Regular USD",
                "NO | SI (Si es SI no infla Patrimonio)",
                "Obligatorio si es_consignacion = SI",
                "Observaciones físicas o técnicas",
            ],
            ejemplos=[
                [
                    "Tekio Central",
                    "SN-APERTURA-0001",
                    "Lenovo",
                    "ThinkPad T14 Gen 2",
                    "Core i5-1145G7",
                    "16GB",
                    "512GB NVMe",
                    "14 FHD",
                    "LISTO",
                    "EXCELENTE",
                    "SI",
                    280.00,
                    420.00,
                    490.00,
                    "NO",
                    "",
                    "Listo en vitrina Tekio Central",
                ],
                [
                    "Depósito / Tekio Support",
                    "SN-APERTURA-0002",
                    "Dell",
                    "Latitude 5420",
                    "Core i7-1185G7",
                    "16GB",
                    "512GB NVMe",
                    "14 FHD",
                    "POR_PREPARAR",
                    "BUENO",
                    "SI",
                    310.00,
                    460.00,
                    530.00,
                    "NO",
                    "",
                    "Pendiente mantenimiento preventivo",
                ],
                [
                    "Tekio Gran Bazar",
                    "SN-CONSIG-0001",
                    "Apple",
                    "MacBook Air M1",
                    "M1",
                    "8GB",
                    "256GB SSD",
                    "13.3 Retina",
                    "LISTO",
                    "EXCELENTE",
                    "SI",
                    520.00,
                    680.00,
                    760.00,
                    "SI",
                    "Aliado Importador C.A.",
                    "Equipo en consignación (no infla capital)",
                ],
            ],
            validaciones={
                1: ["Tekio Central", "Tekio Gran Bazar", "Depósito / Tekio Support"],
                9: ["LISTO", "POR_PREPARAR", "HOSPITAL"],
                10: ["EXCELENTE", "BUENO", "CON_DETALLES", "CON_FALLA"],
                11: ["SI", "NO"],
                15: ["NO", "SI"],
            },
        )

    elif tipo == "inventario_componentes":
        ws.title = "Componentes_Accesorios"
        _estilizar_hoja(
            ws,
            encabezados=[
                "sucursal",
                "sku",
                "nombre",
                "categoria",
                "cantidad_inicial",
                "stock_minimo",
                "costo_unitario_usd",
                "precio_venta_usd",
                "observaciones",
            ],
            instrucciones=[
                "Tekio Central | Tekio Gran Bazar | Depósito / Tekio Support",
                "SKU único normalizado (ej. RAM-DDR4-8GB)",
                "Descripción clara del componente o accesorio",
                "RAM | SSD | CARGADOR | BATERIA | ACCESORIO | REPUESTO",
                "Cantidad física entera (> 0)",
                "Alerta de reposición (ej. 5)",
                "Costo unitario USD",
                "Precio de venta USD",
                "Ubicación o detalles",
            ],
            ejemplos=[
                ["Depósito / Tekio Support", "RAM-DDR4-8GB", "Memoria RAM DDR4 8GB 3200MHz", "RAM", 12, 4, 18.00, 35.00, "Estante Taller A1"],
                ["Depósito / Tekio Support", "SSD-NVME-512", "Disco Sólido M.2 NVMe 512GB", "SSD", 10, 3, 32.00, 60.00, "Estante Taller A2"],
                ["Tekio Central", "CARG-USBC-65W", "Cargador USB-C 65W Original", "CARGADOR", 8, 2, 15.00, 30.00, "Vitrina Central"],
            ],
            validaciones={
                1: ["Tekio Central", "Tekio Gran Bazar", "Depósito / Tekio Support"],
                4: ["RAM", "SSD", "CARGADOR", "BATERIA", "ACCESORIO", "REPUESTO"],
            },
        )

    elif tipo == "cxc_cashea":
        ws.title = "CxC_y_Cashea"
        _estilizar_hoja(
            ws,
            encabezados=[
                "tipo",
                "sucursal",
                "cliente_nombre",
                "cliente_documento",
                "nro_nota_anterior",
                "cashea_numero_orden",
                "fecha_venta_original",
                "monto_financiado_usd",
                "neto_esperado_usd",
                "fecha_vencimiento",
                "observaciones",
            ],
            instrucciones=[
                "CASHEA_PENDIENTE | CLIENTE_CXC",
                "Tekio Central | Tekio Gran Bazar | Depósito / Tekio Support",
                "Nombre del cliente",
                "Cédula o RIF (ej. V-20111222)",
                "Nro. de nota previa al 01/12/2026",
                "Obligatorio si tipo = CASHEA_PENDIENTE",
                "AAAA-MM-DD (fecha original de venta)",
                "Monto total financiado o saldo pendiente USD",
                "Neto esperado USD tras deducciones (o igual al saldo)",
                "AAAA-MM-DD (vencimiento estimado)",
                "No crea ventas nuevas ni comisiones falsas",
            ],
            ejemplos=[
                ["CASHEA_PENDIENTE", "Tekio Central", "Ana Rodríguez", "V-22334455", "N-0988", "CSH-2026-8812", "2026-11-28", 320.00, 294.40, "2026-12-05", "Liquidación pendiente Cashea"],
                ["CLIENTE_CXC", "Tekio Gran Bazar", "Inversiones Sol C.A.", "J-40112233-4", "N-0991", "", "2026-11-29", 150.00, 150.00, "2026-12-10", "Saldo restante por cancelar"],
            ],
            validaciones={
                1: ["CASHEA_PENDIENTE", "CLIENTE_CXC"],
                2: ["Tekio Central", "Tekio Gran Bazar", "Depósito / Tekio Support"],
            },
        )

    elif tipo == "cxp_prestamos":
        ws.title = "CxP_Proveedores"
        _estilizar_hoja(
            ws,
            encabezados=[
                "proveedor",
                "documento_o_factura",
                "concepto",
                "monto_pendiente_usd",
                "fecha_emision",
                "fecha_vencimiento",
                "observaciones",
            ],
            instrucciones=[
                "Nombre del proveedor",
                "Factura, orden o nota",
                "Descripción de la deuda",
                "Saldo pendiente en USD (> 0)",
                "AAAA-MM-DD",
                "AAAA-MM-DD",
                "Notas adicionales",
            ],
            ejemplos=[
                ["Miami Tech Wholesale LLC", "INV-2026-441", "Lote 10 laptops ThinkPad en tránsito", 1400.00, "2026-11-20", "2026-12-20", "Saldo pendiente por pagar"],
            ],
        )
        ws2 = wb.create_sheet(title="Prestamos_Activos")
        _estilizar_hoja(
            ws2,
            encabezados=[
                "acreedor",
                "capital_pendiente_usd",
                "tasa_interes_anual_pct",
                "cuotas_restantes",
                "proximo_vencimiento",
                "observaciones",
            ],
            instrucciones=[
                "Nombre del banco, socio o acreedor",
                "Capital pendiente USD al 01/12/2026 (> 0)",
                "Tasa anual % (0 si es sin interés)",
                "Número entero de cuotas pendientes (>= 1)",
                "AAAA-MM-DD",
                "Condiciones del préstamo",
            ],
            ejemplos=[
                ["Socio Financista A", 2000.00, 12.0, 6, "2027-01-01", "Préstamo capital de trabajo"],
            ],
        )

    elif tipo == "personal_nomina_socios":
        ws.title = "Personal"
        _estilizar_hoja(
            ws,
            encabezados=[
                "nombre",
                "username",
                "rol",
                "categoria_nomina",
                "sucursal",
                "telefono",
                "email_opcional",
                "tiene_acceso_sistema",
                "sueldo_base_usd",
            ],
            instrucciones=[
                "Nombre completo",
                "Usuario de inicio de sesión (si tiene acceso)",
                "ASESORA | LIDER_COMERCIAL | TECNICO | ADMINISTRACION | DIRECCION",
                "ASESOR | LIDER_ENCARGADO | ADMINISTRADORA | ACCIONISTA | CHOFER_MENSAJERO",
                "Tekio Central | Tekio Gran Bazar | Depósito / Tekio Support",
                "Teléfono WhatsApp (ej. 0414-1234567)",
                "Opcional (puede quedar vacío)",
                "SI | NO",
                "Sueldo base mensual USD",
            ],
            ejemplos=[
                ["Laura Pérez", "laura.perez", "ASESORA", "ASESOR", "Tekio Central", "0412-1112233", "", "SI", 220.00],
                ["Miguel Torres", "miguel.torres", "TECNICO", "ASESOR", "Depósito / Tekio Support", "0422-4445566", "", "SI", 280.00],
                ["José Chofer", "", "ASESORA", "CHOFER_MENSAJERO", "Tekio Central", "0414-7778899", "", "NO", 180.00],
            ],
            validaciones={
                3: ["ASESORA", "LIDER_COMERCIAL", "TECNICO", "ADMINISTRACION", "DIRECCION"],
                4: ["ASESOR", "LIDER_ENCARGADO", "ADMINISTRADORA", "ACCIONISTA", "CHOFER_MENSAJERO"],
                5: ["Tekio Central", "Tekio Gran Bazar", "Depósito / Tekio Support"],
                8: ["SI", "NO"],
            },
        )
        ws2 = wb.create_sheet(title="Socios")
        _estilizar_hoja(
            ws2,
            encabezados=[
                "nombre_socio",
                "porcentaje_participacion",
                "activo",
            ],
            instrucciones=[
                "Nombre del accionista / socio",
                "Porcentaje (la suma de socios activos debe ser exactamente 100)",
                "SI | NO",
            ],
            ejemplos=[
                ["Socio Principal A", 50.0, "SI"],
                ["Socio Principal B", 50.0, "SI"],
            ],
            validaciones={3: ["SI", "NO"]},
        )

    else:
        raise ValueError(f"Tipo de plantilla de apertura no soportado: {tipo}")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generar_zip_plantillas_apertura() -> bytes:
    """Empaqueta las 6 planillas oficiales .xlsx de Apertura 01/12/2026 en un solo .zip en memoria."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for tipo, meta in PLANTILLAS_APERTURA_META.items():
            zf.writestr(meta["archivo"], generar_plantilla_oficial_apertura(tipo))
    return buf.getvalue()

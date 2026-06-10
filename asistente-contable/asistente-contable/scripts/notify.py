#!/usr/bin/env python3
"""
Asistente Contable - Bot de Notificaciones Telegram
Envía alertas de pagos pendientes a través de Telegram.
Ejecutado automáticamente por GitHub Actions.
"""

import json
import os
import sys
import requests
from datetime import datetime, date
import pytz

# ── Configuración ──────────────────────────────────────────────────────────────
TIMEZONE = pytz.timezone("America/Asuncion")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PAYMENTS_FILE = "payments.json"

CATEGORIAS_EMOJI = {
    "impuesto": "🏛️",
    "nomina": "👥",
    "gasto_fijo": "🏢",
    "servicio": "📡",
    "proveedor": "📦",
    "otro": "📌",
}

CATEGORIA_NOMBRE = {
    "impuesto": "Impuesto",
    "nomina": "Nómina",
    "gasto_fijo": "Gasto Fijo",
    "servicio": "Servicio",
    "proveedor": "Proveedor",
    "otro": "Otro",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def cargar_pagos():
    with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def formatear_monto(monto, config):
    simbolo = config.get("currency_symbol", "₲")
    return f"{simbolo} {monto:,.0f}"

def dias_para_vencer(dia_vencimiento):
    hoy = datetime.now(TIMEZONE).date()
    año = hoy.year
    mes = hoy.month
    try:
        fecha_venc = date(año, mes, dia_vencimiento)
    except ValueError:
        import calendar
        ultimo_dia = calendar.monthrange(año, mes)[1]
        fecha_venc = date(año, mes, min(dia_vencimiento, ultimo_dia))
    if fecha_venc < hoy:
        siguiente_mes = mes + 1 if mes < 12 else 1
        siguiente_año = año if mes < 12 else año + 1
        try:
            fecha_venc = date(siguiente_año, siguiente_mes, dia_vencimiento)
        except ValueError:
            import calendar
            ultimo_dia = calendar.monthrange(siguiente_año, siguiente_mes)[1]
            fecha_venc = date(siguiente_año, siguiente_mes, min(dia_vencimiento, ultimo_dia))
    return (fecha_venc - hoy).days, fecha_venc

def dias_para_vencer_anual(fecha_str):
    hoy = datetime.now(TIMEZONE).date()
    fecha_venc = date.fromisoformat(fecha_str)
    return (fecha_venc - hoy).days, fecha_venc

def send_telegram(chat_id, mensaje):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=10)
    if not resp.ok:
        print(f"❌ Error Telegram: {resp.status_code} - {resp.text}")
        return False
    print(f"✅ Mensaje enviado al chat {chat_id}")
    return True

# ── Generadores de mensajes ────────────────────────────────────────────────────

def msg_urgente(pago, dias, fecha_venc, config):
    emoji = CATEGORIAS_EMOJI.get(pago.get("categoria", "otro"), "📌")
    monto = formatear_monto(pago["monto"], config)
    if dias < 0:
        estado = f"🚨 <b>VENCIDO hace {abs(dias)} día(s)</b>"
    elif dias == 0:
        estado = "🔴 <b>VENCE HOY</b>"
    else:
        estado = f"⚠️ <b>Vence en {dias} día(s)</b> ({fecha_venc.strftime('%d/%m/%Y')})"
    return (
        f"{emoji} <b>{pago['nombre']}</b>\n"
        f"{estado}\n"
        f"💰 Monto: <b>{monto}</b>\n"
        f"📂 Categoría: {CATEGORIA_NOMBRE.get(pago.get('categoria','otro'), 'Otro')}\n"
        f"📝 {pago.get('descripcion','')}"
    )

def msg_resumen_diario(pagos_urgentes, pagos_proximos, pagos_ok, config):
    hoy = datetime.now(TIMEZONE)
    lineas = [
        f"📊 <b>Resumen Contable — {hoy.strftime('%d/%m/%Y')}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━",
    ]
    if pagos_urgentes:
        lineas.append(f"\n🚨 <b>URGENTES / VENCIDOS ({len(pagos_urgentes)})</b>")
        for p, dias, fv in pagos_urgentes:
            emoji = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            monto = formatear_monto(p["monto"], config)
            if dias < 0:
                lineas.append(f"  {emoji} {p['nombre']} — {monto} <i>(vencido {abs(dias)}d)</i>")
            else:
                lineas.append(f"  {emoji} {p['nombre']} — {monto} <i>(HOY)</i>")
    if pagos_proximos:
        lineas.append(f"\n⚠️ <b>PRÓXIMOS ({len(pagos_proximos)})</b>")
        for p, dias, fv in pagos_proximos:
            emoji = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            monto = formatear_monto(p["monto"], config)
            lineas.append(f"  {emoji} {p['nombre']} — {monto} <i>(en {dias}d, {fv.strftime('%d/%m')})</i>")
    if pagos_ok:
        lineas.append(f"\n✅ <b>AL DÍA ({len(pagos_ok)})</b>")
        for p in pagos_ok:
            emoji = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            lineas.append(f"  {emoji} {p['nombre']}")
    total_pendiente = sum(p["monto"] for p, _, __ in (pagos_urgentes + pagos_proximos))
    lineas.append(f"\n━━━━━━━━━━━━━━━━━━━━━")
    lineas.append(f"💸 <b>Total pendiente próximo:</b> {formatear_monto(total_pendiente, config)}")
    lineas.append(f"\n<i>🤖 Asistente Contable vía GitHub Actions</i>")
    return "\n".join(lineas)

# ── Lógica principal ───────────────────────────────────────────────────────────

def analizar_pagos(data):
    config = data["config"]
    pagos = [p for p in data["payments"] if p.get("activo", True)]
    urgentes, proximos, ok = [], [], []

    for pago in pagos:
        # Saltar si ya fue pagado este mes
        if pago.get("frecuencia") == "mensual" and pago.get("pagado_mes_actual"):
            ok.append(pago)
            continue
        if pago.get("frecuencia") == "anual" and pago.get("pagado"):
            ok.append(pago)
            continue

        if pago.get("frecuencia") == "anual":
            if "fecha_vencimiento" not in pago:
                continue
            dias, fv = dias_para_vencer_anual(pago["fecha_vencimiento"])
        else:
            dias, fv = dias_para_vencer(pago.get("dia_vencimiento", 30))

        if dias <= 0:
            urgentes.append((pago, dias, fv))
        elif dias <= 3:
            proximos.append((pago, dias, fv))
        else:
            ok.append(pago)

    return urgentes, proximos, ok, config

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "resumen"
    print(f"🚀 Iniciando notificador — modo: {modo}")

    if not BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN no configurado")
        sys.exit(1)

    data = cargar_pagos()
    config = data["config"]
    chat_id = config.get("telegram_chat_id")

    if not chat_id or chat_id == "TU_CHAT_ID_AQUI":
        print("❌ Error: telegram_chat_id no configurado en payments.json")
        sys.exit(1)

    urgentes, proximos, ok, config = analizar_pagos(data)

    if modo == "urgentes":
        # Solo envía alertas urgentes (ejecutado más frecuentemente)
        if not urgentes and not proximos:
            print("✅ No hay pagos urgentes. Sin notificaciones.")
            return
        for pago, dias, fv in urgentes:
            msg = msg_urgente(pago, dias, fv, config)
            send_telegram(chat_id, msg)
        for pago, dias, fv in proximos:
            msg = msg_urgente(pago, dias, fv, config)
            send_telegram(chat_id, msg)

    elif modo == "resumen":
        # Resumen diario completo
        msg = msg_resumen_diario(urgentes, proximos, ok, config)
        send_telegram(chat_id, msg)

    print(f"\n📈 Resumen: {len(urgentes)} urgentes, {len(proximos)} próximos, {len(ok)} al día")

if __name__ == "__main__":
    main()

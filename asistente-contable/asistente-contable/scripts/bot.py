#!/usr/bin/env python3
"""
Asistente Contable & Organizador Personal — Bot Telegram Interactivo
Maneja pagos pendientes Y tareas del día, todo desde Telegram.

Comandos disponibles:
  /start        — Bienvenida
  /hoy          — Resumen del día (pagos + tareas)
  /tarea <text> — Agregar tarea nueva
  /tareas       — Ver todas las tareas de hoy
  /pagos        — Ver pagos pendientes
  /listo <id>   — Marcar tarea como completada
  /borrar <id>  — Borrar una tarea
  /limpiar      — Borrar todas las tareas completadas
  /ayuda        — Ver todos los comandos
"""

import json
import os
import sys
import time
import uuid
import requests
from datetime import datetime, date
import pytz

# ── Config ─────────────────────────────────────────────────────────────────────
TIMEZONE       = pytz.timezone("America/Asuncion")
BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN")
PAYMENTS_FILE  = "payments.json"
TASKS_FILE     = "tasks.json"
OFFSET_FILE    = ".telegram_offset"

CATEGORIAS_EMOJI = {
    "impuesto":   "🏛️",
    "nomina":     "👥",
    "gasto_fijo": "🏢",
    "servicio":   "📡",
    "proveedor":  "📦",
    "otro":       "📌",
}

PRIORIDAD_EMOJI = {
    "alta":   "🔴",
    "media":  "🟡",
    "baja":   "🟢",
}

# ── I/O de archivos ────────────────────────────────────────────────────────────

def cargar_pagos():
    with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def cargar_tareas():
    if not os.path.exists(TASKS_FILE):
        return {"tareas": []}
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_tareas(data):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Telegram API ───────────────────────────────────────────────────────────────

def api(method, payload=None):
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    resp = requests.post(url, json=payload or {}, timeout=15)
    return resp.json()

def send(chat_id, texto, teclado=None):
    payload = {
        "chat_id":    chat_id,
        "text":       texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if teclado:
        payload["reply_markup"] = teclado
    return api("sendMessage", payload)

def edit_msg(chat_id, msg_id, texto, teclado=None):
    payload = {
        "chat_id":    chat_id,
        "message_id": msg_id,
        "text":       texto,
        "parse_mode": "HTML",
    }
    if teclado:
        payload["reply_markup"] = teclado
    return api("editMessageText", payload)

def answer_callback(callback_id, texto=""):
    api("answerCallbackQuery", {"callback_id": callback_id, "text": texto})

def get_updates(offset=None):
    params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    return api("getUpdates", params)

# ── Helpers ────────────────────────────────────────────────────────────────────

def ahora():
    return datetime.now(TIMEZONE)

def hoy_str():
    return ahora().strftime("%Y-%m-%d")

def fmt_monto(monto, config):
    simbolo = config.get("currency_symbol", "₲")
    return f"{simbolo} {monto:,.0f}"

def dias_vencer_mensual(dia):
    hoy   = ahora().date()
    año, mes = hoy.year, hoy.month
    import calendar
    ultimo = calendar.monthrange(año, mes)[1]
    fv = date(año, mes, min(dia, ultimo))
    if fv < hoy:
        mes2 = mes + 1 if mes < 12 else 1
        año2 = año if mes < 12 else año + 1
        ultimo2 = calendar.monthrange(año2, mes2)[1]
        fv = date(año2, mes2, min(dia, ultimo2))
    return (fv - hoy).days, fv

def dias_vencer_anual(fecha_str):
    hoy = ahora().date()
    fv  = date.fromisoformat(fecha_str)
    return (fv - hoy).days, fv

# ── Análisis de pagos ──────────────────────────────────────────────────────────

def analizar_pagos(data):
    config = data["config"]
    pagos  = [p for p in data["payments"] if p.get("activo", True)]
    urgentes, proximos, ok = [], [], []
    for p in pagos:
        if p.get("frecuencia") == "mensual" and p.get("pagado_mes_actual"):
            ok.append(p); continue
        if p.get("frecuencia") == "anual" and p.get("pagado"):
            ok.append(p); continue
        if p.get("frecuencia") == "anual":
            if "fecha_vencimiento" not in p: continue
            dias, fv = dias_vencer_anual(p["fecha_vencimiento"])
        else:
            dias, fv = dias_vencer_mensual(p.get("dia_vencimiento", 30))
        if dias <= 0:    urgentes.append((p, dias, fv))
        elif dias <= 5:  proximos.append((p, dias, fv))
        else:            ok.append(p)
    return urgentes, proximos, ok, config

# ── Construcción de mensajes ───────────────────────────────────────────────────

def msg_pagos(urgentes, proximos, ok, config):
    lineas = ["💳 <b>Pagos pendientes</b>\n"]
    if urgentes:
        lineas.append("🚨 <b>URGENTE / VENCIDO</b>")
        for p, dias, fv in urgentes:
            e = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            m = fmt_monto(p["monto"], config)
            tag = "HOY" if dias == 0 else (f"vencido {abs(dias)}d" if dias < 0 else f"en {dias}d")
            lineas.append(f"  {e} <b>{p['nombre']}</b> — {m} <i>({tag})</i>")
    if proximos:
        lineas.append("\n⚠️ <b>PRÓXIMOS (≤5 días)</b>")
        for p, dias, fv in proximos:
            e = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            m = fmt_monto(p["monto"], config)
            lineas.append(f"  {e} {p['nombre']} — {m} <i>(en {dias}d, {fv.strftime('%d/%m')})</i>")
    if ok:
        lineas.append(f"\n✅ <b>Al día:</b> {len(ok)} pagos sin urgencia")
    if not urgentes and not proximos:
        lineas.append("✅ ¡Todo al día! Sin pagos urgentes.")
    return "\n".join(lineas)

def msg_tareas(tareas_hoy, todas=False):
    if not tareas_hoy:
        return "📋 No tenés tareas por hacer hoy.\n\nUsá <code>/tarea Texto de la tarea</code> para agregar una."

    pendientes  = [t for t in tareas_hoy if not t.get("completada")]
    completadas = [t for t in tareas_hoy if t.get("completada")]

    lineas = [f"📋 <b>Tareas del día — {ahora().strftime('%d/%m/%Y')}</b>\n"]

    if pendientes:
        lineas.append(f"⏳ <b>Pendientes ({len(pendientes)})</b>")
        for t in pendientes:
            pri = PRIORIDAD_EMOJI.get(t.get("prioridad","media"), "🟡")
            hora = f" <i>· {t['hora']}</i>" if t.get("hora") else ""
            lineas.append(f"  {pri} [{t['id_corto']}] {t['texto']}{hora}")

    if completadas:
        lineas.append(f"\n✅ <b>Completadas ({len(completadas)})</b>")
        for t in completadas:
            lineas.append(f"  ✓ <s>{t['texto']}</s>")

    lineas.append(f"\n<i>Usá /listo ID para marcar completada · /borrar ID para eliminar</i>")
    return "\n".join(lineas)

def msg_resumen_dia(urgentes, proximos, ok, config, tareas_hoy):
    hora = ahora().strftime("%H:%M")
    fecha = ahora().strftime("%d/%m/%Y")
    pendientes  = [t for t in tareas_hoy if not t.get("completada")]
    completadas = [t for t in tareas_hoy if t.get("completada")]

    lineas = [
        f"🗓️ <b>Resumen del día — {fecha}</b>",
        f"<i>Generado a las {hora} hs</i>",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Tareas
    lineas.append(f"\n📋 <b>TAREAS ({len(pendientes)} pendientes / {len(completadas)} hechas)</b>")
    if pendientes:
        for t in pendientes[:5]:
            pri = PRIORIDAD_EMOJI.get(t.get("prioridad","media"), "🟡")
            hora_t = f" · {t['hora']}" if t.get("hora") else ""
            lineas.append(f"  {pri} {t['texto']}{hora_t}")
        if len(pendientes) > 5:
            lineas.append(f"  <i>... y {len(pendientes)-5} más</i>")
    else:
        lineas.append("  ✅ ¡Sin tareas pendientes!")

    # Pagos
    lineas.append(f"\n💳 <b>PAGOS</b>")
    if urgentes:
        lineas.append(f"  🚨 {len(urgentes)} urgente(s):")
        for p, dias, fv in urgentes[:3]:
            e = CATEGORIAS_EMOJI.get(p.get("categoria","otro"),"📌")
            m = fmt_monto(p["monto"], config)
            lineas.append(f"    {e} {p['nombre']} — {m}")
    if proximos:
        lineas.append(f"  ⚠️ {len(proximos)} próximo(s) (≤5 días)")
    if not urgentes and not proximos:
        lineas.append("  ✅ Todo al día, sin urgencias")

    total = sum(p["monto"] for p, *_ in (urgentes + proximos))
    if total:
        lineas.append(f"\n💸 <b>Total por pagar pronto:</b> {fmt_monto(total, config)}")

    lineas.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lineas.append("<i>🤖 Tu Asistente Contable Personal</i>")
    return "\n".join(lineas)

# ── Teclados inline ────────────────────────────────────────────────────────────

def teclado_tarea(tarea_id):
    return {
        "inline_keyboard": [[
            {"text": "✅ Marcar hecha", "callback_data": f"done:{tarea_id}"},
            {"text": "🗑️ Borrar",       "callback_data": f"del:{tarea_id}"},
        ]]
    }

def teclado_prioridad(texto_tarea):
    # Escapa el texto para usarlo en callback (máx 64 chars total)
    txt = texto_tarea[:40]
    return {
        "inline_keyboard": [[
            {"text": "🔴 Alta",  "callback_data": f"pri:alta:{txt}"},
            {"text": "🟡 Media", "callback_data": f"pri:media:{txt}"},
            {"text": "🟢 Baja",  "callback_data": f"pri:baja:{txt}"},
        ]]
    }

# ── Lógica de tareas ───────────────────────────────────────────────────────────

def tareas_de_hoy(data):
    hoy = hoy_str()
    return [t for t in data["tareas"] if t.get("fecha") == hoy]

def agregar_tarea(data, texto, prioridad="media", hora=None):
    uid  = str(uuid.uuid4())[:8]
    # ID corto legible (2 letras + número)
    existentes = [t["id_corto"] for t in data["tareas"] if t.get("fecha") == hoy_str()]
    num = len(existentes) + 1
    id_corto = f"T{num:02d}"
    tarea = {
        "id":         uid,
        "id_corto":   id_corto,
        "texto":      texto,
        "prioridad":  prioridad,
        "hora":       hora,
        "fecha":      hoy_str(),
        "completada": False,
        "creada_en":  ahora().isoformat(),
        "completada_en": None,
    }
    data["tareas"].append(tarea)
    guardar_tareas(data)
    return tarea

def marcar_completada(data, id_ref):
    """Busca por id_corto o uuid parcial."""
    hoy = hoy_str()
    for t in data["tareas"]:
        if t.get("fecha") == hoy and (
            t["id_corto"].upper() == id_ref.upper() or
            t["id"].startswith(id_ref)
        ):
            t["completada"]    = True
            t["completada_en"] = ahora().isoformat()
            guardar_tareas(data)
            return t
    return None

def borrar_tarea(data, id_ref):
    hoy = hoy_str()
    antes = len(data["tareas"])
    data["tareas"] = [
        t for t in data["tareas"]
        if not (
            t.get("fecha") == hoy and (
                t["id_corto"].upper() == id_ref.upper() or
                t["id"].startswith(id_ref)
            )
        )
    ]
    if len(data["tareas"]) < antes:
        guardar_tareas(data)
        return True
    return False

def limpiar_completadas(data):
    hoy = hoy_str()
    antes = len(data["tareas"])
    data["tareas"] = [t for t in data["tareas"] if not (t.get("fecha") == hoy and t.get("completada"))]
    guardar_tareas(data)
    return antes - len(data["tareas"])

# ── Procesador de comandos ─────────────────────────────────────────────────────

def procesar_mensaje(msg, pago_data):
    chat_id = msg["chat"]["id"]
    texto   = msg.get("text", "").strip()
    tareas  = cargar_tareas()
    hoy_tareas = tareas_de_hoy(tareas)

    if texto.startswith("/start") or texto.startswith("/ayuda"):
        send(chat_id,
            "👋 <b>¡Hola! Soy tu Asistente Contable Personal</b>\n\n"
            "Puedo ayudarte con tus pagos y organizar tu día. Comandos:\n\n"
            "📋 <b>Tareas</b>\n"
            "  /hoy — Resumen completo del día\n"
            "  /tareas — Ver tareas de hoy\n"
            "  /tarea Comprar insumos — Agregar tarea\n"
            "  /tarea 14:00 Reunión con cliente — Con hora\n"
            "  /listo T01 — Marcar tarea como hecha\n"
            "  /borrar T01 — Borrar una tarea\n"
            "  /limpiar — Borrar tareas completadas\n\n"
            "💳 <b>Pagos</b>\n"
            "  /pagos — Ver pagos urgentes y próximos\n\n"
            "💡 <b>Tip:</b> Podés escribir directamente el texto de una tarea sin comando y te preguntaré la prioridad."
        )

    elif texto.startswith("/hoy"):
        urgentes, proximos, ok, config = analizar_pagos(pago_data)
        msg_d = msg_resumen_dia(urgentes, proximos, ok, config, hoy_tareas)
        send(chat_id, msg_d)

    elif texto.startswith("/pagos"):
        urgentes, proximos, ok, config = analizar_pagos(pago_data)
        send(chat_id, msg_pagos(urgentes, proximos, ok, config))

    elif texto.startswith("/tareas"):
        send(chat_id, msg_tareas(hoy_tareas))

    elif texto.startswith("/tarea "):
        contenido = texto[7:].strip()
        if not contenido:
            send(chat_id, "⚠️ Escribí el texto de la tarea. Ej: <code>/tarea Llamar al contador</code>")
            return

        # Detectar hora al inicio: ej "14:30 Reunión"
        hora_detectada = None
        import re
        match = re.match(r'^(\d{1,2}:\d{2})\s+(.+)', contenido)
        if match:
            hora_detectada = match.group(1)
            contenido      = match.group(2)

        # Pedir prioridad con botones inline
        send(chat_id,
            f"📝 <b>Nueva tarea:</b> {contenido}"
            + (f"\n⏰ Hora: {hora_detectada}" if hora_detectada else "")
            + "\n\n¿Qué prioridad tiene?",
            teclado_prioridad(f"{'⏰'+hora_detectada+'|' if hora_detectada else ''}{contenido}")
        )

    elif texto.startswith("/listo "):
        id_ref = texto[7:].strip().upper()
        t = marcar_completada(tareas, id_ref)
        if t:
            send(chat_id, f"✅ <b>{t['texto']}</b>\n¡Tarea completada! 🎉")
        else:
            send(chat_id, f"⚠️ No encontré la tarea <code>{id_ref}</code>. Usá /tareas para ver los IDs.")

    elif texto.startswith("/borrar "):
        id_ref = texto[8:].strip().upper()
        ok2 = borrar_tarea(tareas, id_ref)
        if ok2:
            send(chat_id, f"🗑️ Tarea <code>{id_ref}</code> eliminada.")
        else:
            send(chat_id, f"⚠️ No encontré la tarea <code>{id_ref}</code>.")

    elif texto.startswith("/limpiar"):
        n = limpiar_completadas(tareas)
        send(chat_id, f"🧹 Se eliminaron <b>{n}</b> tarea(s) completada(s).")

    else:
        # Texto libre — ofrecemos agregar como tarea
        if texto and not texto.startswith("/"):
            send(chat_id,
                f"💡 ¿Querés agregar esto como tarea?\n\n<i>{texto}</i>\n\nElegí la prioridad:",
                teclado_prioridad(texto[:40])
            )
        else:
            send(chat_id, "¿No entendí ese comando. Enviá /ayuda para ver todo lo que puedo hacer.")

def procesar_callback(cb, pago_data):
    chat_id    = cb["message"]["chat"]["id"]
    msg_id     = cb["message"]["message_id"]
    data_cb    = cb["data"]
    callback_id = cb["id"]
    tareas     = cargar_tareas()

    if data_cb.startswith("pri:"):
        # pri:alta:texto o pri:alta:⏰14:00|texto
        partes = data_cb.split(":", 2)
        if len(partes) < 3:
            answer_callback(callback_id, "Error al procesar")
            return
        prioridad = partes[1]
        contenido = partes[2]

        # Separar hora del texto si viene
        hora_t = None
        import re
        match = re.match(r'^⏰(\d{1,2}:\d{2})\|(.+)', contenido)
        if match:
            hora_t    = match.group(1)
            contenido = match.group(2)

        t = agregar_tarea(tareas, contenido, prioridad=prioridad, hora=hora_t)
        emoji_pri = PRIORIDAD_EMOJI.get(prioridad, "🟡")
        hora_str  = f"\n⏰ Hora: {hora_t}" if hora_t else ""
        edit_msg(chat_id, msg_id,
            f"✅ Tarea agregada\n\n"
            f"{emoji_pri} <b>{contenido}</b>{hora_str}\n"
            f"🆔 ID: <code>{t['id_corto']}</code>\n\n"
            f"Usá <code>/listo {t['id_corto']}</code> cuando la completes.",
        )
        answer_callback(callback_id, "¡Tarea agregada!")

    elif data_cb.startswith("done:"):
        id_ref = data_cb[5:]
        t = marcar_completada(tareas, id_ref)
        if t:
            edit_msg(chat_id, msg_id, f"✅ <s>{t['texto']}</s>\n¡Completada! 🎉")
            answer_callback(callback_id, "¡Marcada como hecha!")
        else:
            answer_callback(callback_id, "No se encontró la tarea")

    elif data_cb.startswith("del:"):
        id_ref = data_cb[4:]
        ok2 = borrar_tarea(tareas, id_ref)
        if ok2:
            edit_msg(chat_id, msg_id, "🗑️ Tarea eliminada.")
            answer_callback(callback_id, "Eliminada")
        else:
            answer_callback(callback_id, "No se encontró")

# ── Loop principal (modo servidor) ─────────────────────────────────────────────

def cargar_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            try: return int(f.read().strip())
            except: return None
    return None

def guardar_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))

def modo_servidor(pago_data):
    print("🤖 Bot iniciado en modo interactivo. Esperando mensajes...")
    chat_id_autorizado = pago_data["config"].get("telegram_chat_id")
    offset = cargar_offset()
    while True:
        try:
            result = get_updates(offset)
            updates = result.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                guardar_offset(offset)
                # Mensajes de texto
                if "message" in upd:
                    msg = upd["message"]
                    chat_id = str(msg["chat"]["id"])
                    if chat_id_autorizado and chat_id != str(chat_id_autorizado):
                        continue
                    procesar_mensaje(msg, pago_data)
                # Botones inline
                elif "callback_query" in upd:
                    cb = upd["callback_query"]
                    chat_id = str(cb["message"]["chat"]["id"])
                    if chat_id_autorizado and chat_id != str(chat_id_autorizado):
                        answer_callback(cb["id"], "No autorizado")
                        continue
                    procesar_callback(cb, pago_data)
        except KeyboardInterrupt:
            print("\n👋 Bot detenido.")
            break
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)

# ── Modo notificación automática (GitHub Actions) ──────────────────────────────

def modo_notificacion(modo, pago_data):
    from scripts.notify import analizar_pagos as analizar, msg_resumen_diario, msg_urgente, send_telegram
    # Reutiliza notify.py para no duplicar lógica
    urgentes, proximos, ok, config = analizar(pago_data)
    chat_id = pago_data["config"].get("telegram_chat_id")
    tareas  = cargar_tareas()
    hoy_t   = tareas_de_hoy(tareas)
    pendientes = [t for t in hoy_t if not t.get("completada")]

    if modo == "resumen":
        msg = msg_resumen_dia(urgentes, proximos, ok, config, hoy_t)
        send_telegram(chat_id, msg)
        # Si hay tareas pendientes, enviar lista
        if pendientes:
            msg_t = msg_tareas(hoy_t)
            send_telegram(chat_id, msg_t)
    elif modo == "urgentes":
        if urgentes or proximos:
            for p, dias, fv in urgentes:
                send_telegram(chat_id, msg_urgente(p, dias, fv, config))
            for p, dias, fv in proximos:
                send_telegram(chat_id, msg_urgente(p, dias, fv, config))

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN no configurado")
        sys.exit(1)

    pago_data = cargar_pagos()
    modo = sys.argv[1] if len(sys.argv) > 1 else "servidor"

    if modo == "servidor":
        modo_servidor(pago_data)
    elif modo in ("resumen", "urgentes"):
        # Llamado desde GitHub Actions (notificación automática)
        from scripts import notify as n_mod
        urgentes, proximos, ok, config = analizar_pagos(pago_data)
        chat_id = pago_data["config"].get("telegram_chat_id")
        tareas  = cargar_tareas()
        hoy_t   = tareas_de_hoy(tareas)
        if modo == "resumen":
            msg = msg_resumen_dia(urgentes, proximos, ok, config, hoy_t)
            n_mod.send_telegram(chat_id, msg)
            pendientes = [t for t in hoy_t if not t.get("completada")]
            if pendientes:
                n_mod.send_telegram(chat_id, msg_tareas(hoy_t))
        elif modo == "urgentes":
            if urgentes or proximos:
                for p, dias, fv in urgentes:
                    n_mod.send_telegram(chat_id, n_mod.msg_urgente(p, dias, fv, config))
                for p, dias, fv in proximos:
                    n_mod.send_telegram(chat_id, n_mod.msg_urgente(p, dias, fv, config))
            else:
                print("✅ Sin urgencias.")
    else:
        print(f"Modo desconocido: {modo}")

if __name__ == "__main__":
    main()

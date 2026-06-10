# 🤖 Asistente Contable & Organizador Personal

Bot de Telegram con gestión de pagos + tareas del día, automatizado vía GitHub Actions.

---

## ✨ Funciones

| Módulo | Qué hace |
|--------|----------|
| 💳 Pagos | Alerta de IVA, salarios, alquileres, servicios con monto y días restantes |
| 📋 Tareas | Agregar, priorizar y completar tareas del día desde Telegram |
| 📊 Resumen | Reporte diario a las 8AM con pagos + tareas |
| 🔔 Alertas | Notificaciones automáticas de urgentes 3 veces al día |

---

## 📱 Comandos del Bot

```
/hoy              → Resumen completo: tareas pendientes + pagos urgentes
/tareas           → Ver todas las tareas de hoy
/tarea Texto      → Agregar tarea (te pregunta la prioridad con botones)
/tarea 14:00 Texto → Agregar tarea con hora específica
/listo T01        → Marcar tarea T01 como completada
/borrar T01       → Borrar tarea T01
/limpiar          → Eliminar todas las tareas ya completadas
/pagos            → Ver pagos urgentes y próximos
/ayuda            → Ver todos los comandos
```

> 💡 **Tip**: También podés escribir texto libre y el bot te ofrece agregarlo como tarea directamente.

---

## 🚀 Configuración

### 1. Crear el bot en Telegram

1. Abrí Telegram → buscá **@BotFather**
2. Enviá `/newbot` → seguí los pasos
3. Copiá el **TOKEN** que te da

### 2. Obtener tu Chat ID

Opción A: Enviá `/start` a tu bot, luego entrá a:
```
https://api.telegram.org/botTU_TOKEN/getUpdates
```
Buscá `"chat": {"id": 123456789}` — ese número es tu Chat ID.

Opción B: Escribile a [@userinfobot](https://t.me/userinfobot) en Telegram.

### 3. GitHub Secret

En tu repo: **Settings → Secrets → Actions → New repository secret**
- Nombre: `TELEGRAM_BOT_TOKEN`  
- Valor: el token del BotFather

### 4. Configurar payments.json

```json
{
  "config": {
    "currency_symbol": "₲",
    "telegram_chat_id": "123456789",   ← Tu Chat ID acá
    ...
  }
}
```

---

## ⏰ Horarios automáticos

| Hora Paraguay | Tipo | Descripción |
|--------------|------|-------------|
| 8:00 AM | 📊 Resumen | Reporte del día: pagos + tareas |
| 9:00 AM | ⚠️ Urgentes | Solo si hay pagos urgentes |
| 1:00 PM | ⚠️ Urgentes | Solo si hay pagos urgentes |
| 4:00 PM | ⚠️ Urgentes | Solo si hay pagos urgentes |
| Lun-Sáb 8AM-6PM | 🤖 Bot activo | Responde comandos en tiempo real |

---

## 📁 Estructura del proyecto

```
asistente-contable/
├── .github/workflows/
│   ├── notificaciones.yml     # Resumen diario + alertas de pagos
│   └── bot-interactivo.yml    # Bot escuchando mensajes en tiempo real
├── scripts/
│   ├── bot.py                 # Bot interactivo principal
│   └── notify.py              # Notificaciones automáticas
├── payments.json              # Lista de pagos a seguir
├── tasks.json                 # Tareas del día (se actualiza sola)
└── README.md
```

---

## 💬 Ejemplo de uso

```
Vos:  /tarea 10:00 Llamar al contador
Bot:  📝 Nueva tarea: Llamar al contador
      ⏰ Hora: 10:00
      ¿Qué prioridad tiene?
      [🔴 Alta] [🟡 Media] [🟢 Baja]

Vos:  [clic en 🔴 Alta]
Bot:  ✅ Tarea agregada
      🔴 Llamar al contador · 10:00
      🆔 ID: T01

Vos:  /listo T01
Bot:  ✅ Llamar al contador
      ¡Tarea completada! 🎉
```

---

## 📝 Agregar pagos

Editá `payments.json` y agregá un objeto al array `payments`:

```json
{
  "id": "7",
  "nombre": "Factura Proveedor XYZ",
  "monto": 2500000,
  "categoria": "proveedor",
  "frecuencia": "mensual",
  "dia_vencimiento": 25,
  "descripcion": "Pago mensual insumos",
  "activo": true,
  "pagado_mes_actual": false,
  "ultimo_pago": null
}
```

Cuando pagues, cambiá `"pagado_mes_actual": true`.

---

*🤖 Asistente Contable Personal · GitHub Actions + Telegram Bot API*

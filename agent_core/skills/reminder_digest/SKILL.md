---
name: reminder_digest
description: Cómo redactar el recordatorio de tareas vencidas y próximas a vencer, tanto el correo diario automático como cuando el usuario lo pide en el chat.
---

# Recordatorio de tareas

## Cuándo usarla
- El recordatorio diario automático (el mensaje lo envía el programador de tareas, no el usuario).
- Cuando el usuario pregunta "¿Qué tengo pendiente?", "¿Qué se me vence?" o "Recuérdame mis tareas".

## Pasos
1. Llama a `get_current_datetime` para obtener la fecha local de hoy.
2. Vencidas: `list_tasks(overdue_only=true)`.
3. Próximas: `list_tasks(status=["todo", "in_progress", "blocked"], due_after=<hoy>, due_before=<mañana>)`.
4. Si no hay ninguna tarea en los pasos 2 y 3, responde exactamente: `No tienes tareas vencidas ni próximas a vencer.`

## Formato
El recordatorio diario se envía por correo electrónico como **texto plano**: no uses tablas ni Markdown.

```
Recordatorio de tareas – YYYY-MM-DD

VENCIDAS (n)
- [T-xxxxxxxx] Título – venció el YYYY-MM-DD – prioridad alta

VENCEN HOY O MAÑANA (n)
- [T-xxxxxxxx] Título – vence el YYYY-MM-DD – prioridad media

Sugerencia: <una sola frase indicando con qué tarea empezar y por qué>.
```

## Reglas
- Ordena cada sección por fecha límite y luego por prioridad (urgente primero).
- Máximo 15 tareas por sección; si hay más, agrega "… y N más".
- Muestra prioridades en español (baja, media, alta, urgente).
- No incluyas descripciones largas ni datos sensibles.
- Respeta las preferencias del usuario en memoria (tono, nivel de detalle).
- En el chat (no en el correo) puedes usar una tabla en lugar de la lista.

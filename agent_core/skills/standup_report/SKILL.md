---
name: standup_report
description: Pasos y formato para generar un reporte de standup (ayer / hoy / bloqueos) o un reporte de estado del avance de las tareas.
---

# Reporte de standup y reporte de estado

## Cuándo usarla
- Standup: "Dame mi standup", "¿Qué hice ayer y qué hago hoy?".
- Estado: "¿Cómo voy?", "Hazme un reporte de avance de la materia X".

## Pasos para el standup
1. Llama a `get_current_datetime`. Calcula "ayer" como el día anterior; si hoy es lunes, usa el viernes anterior.
2. Lo completado: `list_tasks(completed_after=<ayer>, status=["done"])`.
3. El plan de hoy: `list_tasks(status=["in_progress"])` y `list_tasks(status=["todo"], due_before=<hoy + 2 días>)`.
4. Bloqueos y riesgos: `list_tasks(status=["blocked"])` y `list_tasks(overdue_only=true)`.

## Formato del standup
```
## Standup – YYYY-MM-DD

**Ayer completé**
- T-xxxxxxxx Título

**Hoy trabajaré en**
- T-xxxxxxxx Título (vence YYYY-MM-DD)

**Bloqueos y riesgos**
- T-xxxxxxxx Título – bloqueada / vencida el YYYY-MM-DD
```
Si una sección está vacía escribe "Nada" (o "Sin bloqueos"). Máximo 7 tareas por sección.

## Pasos para el reporte de estado
1. Llama a `summarize_progress` (con `tag` si el usuario pidió una materia o proyecto).
2. Complementa con `list_tasks` solo si necesitas más detalle.

## Formato del reporte de estado
1. **Resumen**: total de tareas, % completado y tareas completadas en los últimos 7 días.
2. **Por estado**: tabla Estado | Cantidad.
3. **Vencidas**: tabla ID | Título | Fecha límite | Prioridad.
4. **Próximas a vencer**: tabla ID | Título | Fecha límite | Prioridad.
5. **Recomendaciones**: máximo 3 acciones concretas (por ejemplo, "Empieza por T-… porque vence mañana y es urgente").

Respeta las preferencias del usuario en memoria (por ejemplo, si prefiere respuestas más cortas o solo tablas).

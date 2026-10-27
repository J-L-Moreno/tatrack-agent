---
name: goal_breakdown
description: Guía para dividir un objetivo grande (proyecto, examen, entrega, tesis) en tareas pequeñas, accionables y con fechas escalonadas.
---

# Dividir un objetivo en tareas

## Cuándo usarla
Cuando el usuario quiera planear un objetivo grande, por ejemplo: "Ayúdame a preparar el examen final de Cálculo del 15 de diciembre" o "Divide mi proyecto de base de datos en tareas".

## Pasos
1. Llama a `get_current_datetime` para conocer la fecha local de hoy.
2. Identifica el objetivo y su fecha límite final. Si el usuario no dio una fecha, propón una razonable y menciónala.
3. Divide el objetivo en **3 a 10 tareas**:
   - Cada título empieza con un verbo en infinitivo: "Leer", "Resolver", "Redactar", "Revisar", "Entregar".
   - Cada tarea debe poder hacerse en una sola sesión de trabajo (máximo ~3 horas). Si no, divídela.
   - Ordena las tareas de forma lógica (investigar → hacer → revisar → entregar).
   - Reparte las fechas entre hoy y la fecha límite. Deja 1–2 días de margen antes de la entrega final. Nunca uses fechas pasadas.
   - Prioridad: `urgent` solo si vence en 2 días o menos; `high` para las tareas críticas; `medium` por defecto; `low` para las opcionales.
   - Etiquetas: una etiqueta común para el objetivo (por ejemplo `calculo-2` o `proyecto-bd`), más las etiquetas que el usuario suele usar según su memoria.
4. Respeta las preferencias del usuario en memoria (prioridad por defecto, días en que estudia, nivel de detalle).
5. Muestra la propuesta en una tabla: Título | Fecha límite | Prioridad | Etiquetas.
6. Pregunta si quiere crearlas, salvo que el usuario ya haya pedido crearlas directamente.
7. Cuando confirme, créalas con `create_tasks_bulk` (máximo 15 por llamada).
8. Responde con la tabla final, incluyendo los `task_id` devueltos por la herramienta.

## Errores comunes que debes evitar
- Tareas vagas como "Trabajar en el proyecto" o "Estudiar".
- Poner todas las tareas con la misma fecha.
- Crear más de 10 tareas sin que el usuario lo pida.
- Decir que se crearon las tareas antes de recibir la respuesta de `create_tasks_bulk`.

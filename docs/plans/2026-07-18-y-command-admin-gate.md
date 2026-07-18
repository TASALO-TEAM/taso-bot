# Plan: separar permisos en /y (público vs admin)

## Problema

`y_command` en `src/handlers/y.py` despacha `add` / `edit` / `del` sin ningún
chequeo de permisos. Cualquier usuario puede agregar, editar o borrar frases
del año. Solo el estado del año (sin args) y la suscripción a la alerta
diaria deben ser públicos; `add` / `edit` / `del` deben quedar restringidos
a administradores.

## Cambio propuesto

En `src/handlers/y.py`:

1. Importar `is_admin` desde `src.utils.permissions` (mismo patrón ya usado
   en `admin.py` y `ads.py`).
2. En `y_command`, agrupar `add` / `edit` / `del` bajo un chequeo de admin
   antes de invocar la función correspondiente:

```python
elif sub in ("add", "edit", "del"):
    if not is_admin(user_id):
        await update.message.reply_text(
            "🔑 Este subcomando es solo para administradores."
        )
        return
    if sub == "add":
        await _cmd_add(update, context, args[1:])
    elif sub == "edit":
        await _cmd_edit(update, context, args[1:])
    else:
        await _cmd_del(update, context, args[1:])
```

3. `show` y el flujo sin args (estado del año + teclado de suscripción)
   quedan exactamente igual, sin restricción — cualquier usuario puede
   verlos y suscribirse/desuscribirse a la alerta diaria.
4. El mensaje de ayuda de subcomandos (rama `else` del dispatcher) no
   cambia — sigue listando los 4 subcomandos; quien no sea admin verá el
   texto pero recibirá el rechazo al ejecutar `add`/`edit`/`del`.

## Fuera de alcance

- No se toca `_cmd_add`, `_cmd_edit`, `_cmd_del`, `_cmd_show`,
  `year_sub_callback` ni `handle_year_hour_input` — su lógica interna no
  cambia, solo se les impide el acceso desde el dispatcher.
- No se mueven las funciones admin a un archivo separado (`y_admin.py`) en
  esta iteración — ya están separadas como funciones independientes, el gate
  centralizado en el dispatcher es suficiente y consistente con cómo se
  maneja en `admin.py`.

## Validación

- `py -3 -m py_compile src/handlers/y.py` en Windows.
- Prueba manual: usuario no-admin ejecuta `/y add prueba` → debe recibir el
  mensaje de rechazo. Admin ejecuta lo mismo → debe funcionar como antes.
- `/y` y `/y show` sin restricciones, para cualquier usuario.

# TASALO Bot - reglas para agentes

Prioridades de diseno, en orden: Funcional > Robusto > Seguro > Util > Minimalista. Cambios minimos y dirigidos.
Hay un objetivo vigente de reducir el consumo de recursos en el VPS: nada que lo empeore sin justificarlo.

## Reglas operativas
- Nunca leer, editar ni imprimir `.env` ni valores de claves; solo nombres de variables.
- Tests primero (rojo, luego verde) y suite completa antes de proponer un PR.
- No reiniciar servicios entre las 8:10 y las 9:00 hora de Cuba (captura de la imagen de El Toque).
- Despliegue: `git pull` en el VPS y reinicio con confirmacion del propietario.

## Skills en cada sesion (el propietario las pide siempre)
- Al empezar: `claude-mem:mem-search` (o `cmem-pro:mem-search`) para recuperar trabajo previo; luego leer `task/registro/` (PLAN, BOARD, ultimos handoffs).
- Al escribir codigo: `ponytail:ponytail` (cambio minimo), `andrej-karpathy-skills:karpathy-guidelines` (supuestos explicitos, cambios quirurgicos, criterio verificable) y `ecc:python-review` antes de abrir el PR.
- Trabajo multiagente: `ecc:dev-team`, `ecc:claude-devfleet`, `ecc:team-agent-orchestration` (ver la regla Jefe + ayudante abajo).
- Al cerrar: `claude-mem:handoff` y dejar BOARD, LOG y handoff al dia en `task/registro/`.
- Si una skill o herramienta no esta disponible en la sesion, decirlo y seguir sin ella; no inventar su resultado.

## Jefe + ayudante (regla permanente, todos los repos y sesiones de TASALO)

- **Jefe (modelo principal):** escribe el codigo y los tests, piensa, investiga a fondo, decide, abre PR y despliega.
- **Ayudante (`ayudante-haiku`, modelo Haiku, solo lectura):** lee codigo y archivos, revisa logs, busca en la web y en Context7. No edita ni ejecuta nada.
- Delegar al ayudante: barridos de lectura (grep de usos, inventarios, quien llama a que), conteos en logs con IDs enmascarados, investigacion de APIs/limites/licencias con fuente. Varias lecturas independientes en paralelo.
- No delegar: escribir codigo, commits, PR, despliegues, decisiones de diseno, severidad de hallazgos.
- El jefe verifica lo critico antes de apoyarse en lo que devuelva el ayudante. Lo no verificado se marca como tal.
- Skills de trabajo en equipo: `ecc:dev-team`, `ecc:claude-devfleet`, `ecc:team-agent-orchestration`. Abrir con `claude-mem:mem-search`, cerrar con `claude-mem:handoff`.
- Si el entorno no puede lanzar subagentes, el jefe hace la lectura el mismo y lo dice.

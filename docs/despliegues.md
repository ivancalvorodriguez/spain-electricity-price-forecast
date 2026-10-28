# Despliegues

Qué se rompió en cada despliegue público y por qué. Se relee antes del
siguiente.

## Antes de desplegar

- `main` despliega sola: cualquier push que pase las comprobaciones llama
  al gancho de Render, también si solo cambia el README (el `Dockerfile`
  lo copia, así que la imagen cambia igual).
- Si el despliegue falla en Render, la CI sigue en verde: el gancho solo
  pide el despliegue y no espera a que termine. Hay que mirar *Deploys* en
  Render y abrir `/health` a mano.
- Si `/health` no responde en 15 minutos, Render da el despliegue por
  fallido y deja la versión anterior. El error está en el log del
  despliegue, en *Deploys*; el del servicio en marcha, en *Logs* (duran
  7 días).
- Las variables de entorno de Render llegan también al build como
  argumentos de Docker. No declarar nunca un `ARG` con un secreto.
- Para cambiar `DATABASE_URL`: *Environment* → *Save and deploy*.
  *Save only* no la aplica hasta el siguiente despliegue.

## 27/10/2026 · primer despliegue (`6fd5433`, PR #4)

**Qué se hizo.** Web Service `epf-spain` en Render (Docker, Frankfurt,
plan gratuito), con `DATABASE_URL` del *pooler* de Neon, *Health Check
Path* `/health` y *Auto-Deploy* en *Off*. La URL del gancho, en los
secrets de Actions como `RENDER_DEPLOY_HOOK_URL`. Al fusionar el PR, los
dos trabajos en verde y el gancho llamado con el commit comprobado.

**Qué se rompió.** Nada: el primer despliegue salió a la primera.

**Lo que podía haberse roto:**

- *Auto-Deploy* viene en *On Commit* al crear el servicio. Si se queda
  así, cada push despliega dos veces: una por Render y otra por el gancho.
- En el primer despliegue no hay versión anterior. Si `/health` hubiera
  fallado, el servicio se habría quedado sin nada.
- Al fusionar un PR con *squash*, GitHub propone como título el nombre de
  la rama («Ci/deploy (#4)»). Se corrige a mano antes de fusionar.
- Render pone `PORT=10000` y pide escuchar en `0.0.0.0`. `web.py` ya lo
  hacía, y se probó en local el 26/10 con la imagen de producción.

## 28/10/2026 · la URL desde fuera

**Qué se comprobó.** `https://epf-spain.onrender.com/health` desde el
móvil, con datos: responde `{"status":"ok"}`, con el certificado válido.
Por HTTP redirige a HTTPS (301). Con el servicio dormido, la primera
respuesta tarda alrededor de un minuto.

**Qué se rompió.** Nada.

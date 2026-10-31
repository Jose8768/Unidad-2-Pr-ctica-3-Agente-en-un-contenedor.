# Guía de Práctica 3: Contenedorización del Agente con Docker

---

## Objetivo
Empaquetar la solución del agente de soporte dentro de una imagen de Docker basada en Linux (`python:3.12-slim`) para:
1. Garantizar la reproducibilidad estricta del entorno de ejecución con independencia del sistema operativo anfitrión.
2. Aplicar el principio de separación entre código e infraestructura inmutable.
3. Inyectar secretos en tiempo de ejecución a través de archivos de entorno (`--env-file`), previniendo la persistencia de credenciales en las capas de la imagen.
4. Gestionar el ciclo de vida del contenedor tanto en ejecuciones por lotes (`--una-vez`) como en modo daemon continuo con políticas de reinicio automático (`--restart unless-stopped`).

---

## Requisitos Técnicos y Entorno
* Práctica 2 finalizada y validada.
* Docker Desktop instalado con motor activo (WSL 2 en Windows o Hypervisor nativo en macOS/Linux).
* Terminal de línea de comandos.
* Archivo de token de Google OAuth 2.0 vigente.

---

## Procedimiento de Implementación

### Fase 1: Verificación del Entorno Docker

1. Iniciar Docker Desktop y comprobar que el motor de ejecución reporte estado "Engine running".
2. Ejecutar la validación inicial en la terminal:
   ```bash
   docker --version
   docker run hello-world
   ```

---

### Fase 2: Análisis de la Infraestructura de Empaquetado

La carpeta contiene los artefactos de definición:
1. **Dockerfile**:
   * Imagen base: `python:3.12-slim`.
   * Variable de entorno: `ENV PYTHONUNBUFFERED=1` para asegurar la transmisión de streams de stdout/stderr a los logs sin retención en búfer.
   * Optimización de capas: Copia de `requirements.txt` previa a la copia del código fuente para maximizar el uso de caché durante reconstrucciones.
   * Invocación: `ENTRYPOINT ["python", "agente_soporte.py"]`.
2. **.dockerignore**: Excluye `.env`, `token.env`, `client_secrets.json`, `.git` y artefactos temporales del contexto de compilación.
3. **.gitignore**: Garantiza la protección del repositorio frente a secretos locales.

---

### Fase 3: Compilación de la Imagen

1. Situarse en la raíz del proyecto y compilar la imagen:
   ```bash
   docker build -t agente-soporte .
   ```
2. Verificar el registro local de imágenes:
   ```bash
   docker images
   ```
   *(La imagen `agente-soporte` debe reflejar un tamaño aproximado de 270 MB).*
3. **Auditoría de Seguridad de la Imagen**:
   Validar que la imagen carezca de credenciales residuales:
   ```bash
   docker run --rm --entrypoint ls agente-soporte -A /app
   ```
   *El listado debe contener únicamente `agente_soporte.py` y `requirements.txt`.*

---

### Fase 4: Suministro de Credenciales y Ejecución Aislada

1. **Definir el archivo de entorno general (.env)**:
   Asegurar la existencia del archivo `.env`:
   ```env
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL=gemini-3.8-flash
   ```
2. **Definir el archivo de token serializado (token.env)**:
   * Crear el archivo `token.env`.
   * Asignar la variable `GOOGLE_TOKEN_JSON=` seguida inmediatamente del objeto JSON completo obtenido de `authorized_user.json` en una sola línea.
3. **Ejecución en ciclo único**:
   ```bash
   docker run --rm --env-file .env --env-file token.env agente-soporte --una-vez
   ```
   *El contenedor procesa los registros pendientes y se destruye de forma automática al finalizar.*

---

### Fase 5: Ejecución en Modo Daemon Persistente

1. **Desactivación temporal de GitHub Actions**:
   Para prevenir concurrencia sobre la hoja de cálculo, deshabilitar el workflow de GitHub Actions en la pestaña Actions del repositorio remoto.
2. **Instanciación del contenedor en segundo plano**:
   ```bash
   docker run -d --name agente --restart unless-stopped --env-file .env --env-file token.env agente-soporte
   ```
3. **Inspección de estado y registros**:
   ```bash
   docker ps
   docker logs -f agente
   ```
   *(Presionar Ctrl + C para liberar la terminal; el proceso en el contenedor permanece activo).*
4. **Validación funcional**:
   * Emitir un nuevo registro desde el formulario de Google.
   * Monitorear en los logs la detección y procesamiento de la fila.
5. **Comandos de control operativo**:
   ```bash
   # Detención del servicio
   docker stop agente

   # Reactivación del servicio
   docker start agente

   # Eliminación forzada del contenedor
   docker rm -f agente
   ```

---

### Fase 6: Control de Versiones con Git

Para versionar los archivos de configuración:
* **Si se utiliza un repositorio nuevo**:
  ```bash
  git init
  git add .
  git status
  git commit -m "Practica 3: Empaquetamiento de agente en contenedor Docker"
  git branch -M main
  git remote add origin https://github.com/TU_USUARIO/practica3-agente-docker.git
  git push -u origin main
  ```
* **Si se integra sobre el repositorio de la Práctica 2**:
  ```bash
  git add Dockerfile .dockerignore .gitignore README.md
  git commit -m "Incorporacion de soporte de contenedorizacion con Docker"
  git push
  ```

---

## Evidencias para Entrega
1. Repositorio en GitHub con `Dockerfile` y `.dockerignore` integrados.
2. Captura de salida del comando `docker run hello-world`.
3. Captura del proceso de compilación `docker build` e imagen en `docker images`.
4. Captura del comando de inspección de archivos sin secretos en `/app`.
5. Captura de ejecución en modo `--una-vez`.
6. Captura de `docker logs agente` y hoja de cálculo reflejando la actualización del registro.
7. Cuestionario de reflexión respondido formalmente.

---

## Cuestionario de Reflexión y Análisis Técnico

### 1. Explicar con un ejemplo propio la diferencia entre una imagen y un contenedor.
Una imagen es un paquete de solo lectura e inmutable que consolida el sistema de archivos base, el runtime de Python, las dependencias y el código fuente; equivale a un plano de construcción o clase en programación orientada a objetos. El contenedor es la instancia en memoria y tiempo de ejecución generada a partir de dicha imagen, poseyendo su propio espacio de nombres de procesos, interfaces de red y capa de almacenamiento temporal de lectura/escritura.

### 2. Si el .dockerignore no excluyera el archivo .env y la imagen se publicara en Docker Hub, ¿qué podría hacer otra persona con ella?
Cualquier usuario podría descargar la imagen mediante `docker pull` y extraer los archivos contenidos mediante inspección de capas o levantando un shell interactivo. Con ello tendría acceso a la clave `GEMINI_API_KEY`, pudiendo utilizar indebidamente la cuota y generar afectaciones en la cuenta del propietario.

### 3. ¿Por qué el Dockerfile copia requirements.txt antes que el script? ¿Qué se observó en el Paso 3.1 al reconstruir la imagen?
Docker evalúa la validez de su memoria caché instrucción por instrucción. La instalación de paquetes vía pip es una operación de alta latencia. Al separar la copia de las dependencias de la copia del código fuente, cualquier modificación sobre `agente_soporte.py` invalida únicamente la capa final, permitiendo que Docker reutilice la capa de dependencias compilada (`CACHED`), completando la reconstrucción en fracciones de segundo.

### 4. ¿Por qué la misma imagen puede ejecutarse en modo continuo o con --una-vez sin construir dos imágenes distintas?
La directiva `ENTRYPOINT ["python", "agente_soporte.py"]` define el ejecutable principal. Cualquier parámetro suplementario declarado en el comando `docker run` se anexa al final del vector de argumentos. Así, omitir argumentos ejecuta el bucle continuo predeterminado, mientras que especificar `--una-vez` invoca el script con dicha bandera, resolviendo ambos casos mediante un único artefacto.

### 5. Si el token de Google se renueva, ¿por qué no basta con docker restart agente?
El comando `docker restart` únicamente reinicia el proceso del sistema operativo sin reevaluar la configuración de entorno con la que fue creado el contenedor. Las variables pasadas por `--env-file` se asignan de forma fija durante la creación. Para incorporar un nuevo token, se debe eliminar el contenedor (`docker rm -f`) y crearlo nuevamente apuntando al archivo actualizado.

### 6. Para este agente, ¿cuándo convendría usar GitHub Actions y cuándo un contenedor en un servidor? Considerar costo, frecuencia de revisión y facilidad de mantenimiento.
GitHub Actions resulta óptimo cuando se prioriza la operación sin costo dentro de la cuota mensual gratuita de 2,000 minutos y se toleran tiempos de respuesta de 15 a 30 minutos, sin carga de gestión de infraestructura. Por el contrario, un contenedor persistente en servidor resulta indispensable cuando se demanda latencia cercana al tiempo real (revisión cada 60 segundos), el volumen de transacciones agotaría la cuota de un servicio de CI/CD, o se requiere integración con sistemas de métricas y observabilidad continua.

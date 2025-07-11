# 🚀 INSTRUCCIONES DE DESPLIEGUE - AI Innovation App

## 📋 REQUISITOS PREVIOS
- ✅ Docker instalado en el servidor
- ✅ Acceso a internet para descargar dependencias
- ✅ Puerto 7860 disponible (o cambiar según necesidades)
- ✅ **CLAVES DE AZURE OPENAI** (obligatorio)

## 🔑 CONFIGURACIÓN DE API KEYS (¡OBLIGATORIO!)

### ⚠️ IMPORTANTE: Variables de Entorno
Esta aplicación requiere configurar las siguientes variables de entorno con tus claves de Azure OpenAI:

```bash
AZURE_OPENAI_ENDPOINT="tu-endpoint-aqui"
AZURE_OPENAI_API_KEY="tu-clave-api-aqui"
DEPLOYMENT_NAME="gpt-o3-mini"  # Opcional, valor por defecto
API_VERSION="2025-01-31-preview"  # Opcional, valor por defecto
```

## 🐳 CONSTRUCCIÓN DE LA IMAGEN

### 1. Construir la imagen Docker:
```bash
docker build -t ai-innovation-sener .
```

### 2. Verificar que se creó correctamente:
```bash
docker images | grep ai-innovation-sener
```

## 🚀 EJECUCIÓN CON VARIABLES DE ENTORNO

### ⚠️ MÉTODO OBLIGATORIO: Con variables de entorno
```bash
docker run \
  -e AZURE_OPENAI_ENDPOINT="https://tu-endpoint.openai.azure.com/" \
  -e AZURE_OPENAI_API_KEY="tu-clave-real-aqui" \
  -e DEPLOYMENT_NAME="gpt-o3-mini" \
  -e API_VERSION="2025-01-31-preview" \
  -p 7860:7860 \
  ai-innovation-sener
```

### 🔄 MÉTODO ALTERNATIVO: Con archivo .env
1. Crear archivo `.env`:
```bash
echo "AZURE_OPENAI_ENDPOINT=https://tu-endpoint.openai.azure.com/" > .env
echo "AZURE_OPENAI_API_KEY=tu-clave-real-aqui" >> .env
echo "DEPLOYMENT_NAME=gpt-o3-mini" >> .env
echo "API_VERSION=2025-01-31-preview" >> .env
```

2. Ejecutar con archivo .env:
```bash
docker run --env-file .env -p 7860:7860 ai-innovation-sener
```

## 🔍 VERIFICACIÓN

### Acceder a la aplicación:
- Abrir navegador: `http://localhost:7860`
- Verificar que aparece la interfaz de Gradio
- Verificar en logs que dice "✅ Cliente Azure OpenAI inicializado correctamente"

## ☁️ DESPLIEGUE EN SERVIDOR

### 1. Ejecución en background:
```bash
docker run -d \
  --name ai-innovation-prod \
  -e AZURE_OPENAI_ENDPOINT="https://tu-endpoint.openai.azure.com/" \
  -e AZURE_OPENAI_API_KEY="tu-clave-real-aqui" \
  -e DEPLOYMENT_NAME="gpt-o3-mini" \
  -p 7860:7860 \
  --restart unless-stopped \
  ai-innovation-sener
```

### 2. Ver logs:
```bash
docker logs ai-innovation-prod
```

### 3. Parar la aplicación:
```bash
docker stop ai-innovation-prod
docker rm ai-innovation-prod
```

## 🔧 TROUBLESHOOTING

### ❌ Error: "AZURE_OPENAI_ENDPOINT no está configurada"
**Solución:** Asegúrate de pasar las variables de entorno con `-e`

### ❌ Error: "Error inicializando cliente Azure OpenAI"
**Causas posibles:**
- Clave API incorrecta
- Endpoint incorrecto 
- Problemas de conectividad

**Verificar configuración:**
```bash
# Ver configuración actual:
docker run --rm \
  -e AZURE_OPENAI_ENDPOINT="tu-endpoint" \
  -e AZURE_OPENAI_API_KEY="tu-clave" \
  ai-innovation-sener \
  python -c "import openai_config"
```

### ❌ Error: "Puerto 7860 ya en uso"
**Solución:** Cambiar puerto:
```bash
docker run ... -p 8080:7860 ai-innovation-sener
# Acceder via: http://localhost:8080
```

## 🛡️ SEGURIDAD

### ✅ Buenas prácticas implementadas:
- ✅ Claves NO hardcodeadas en el código
- ✅ Variables de entorno para configuración sensible
- ✅ Verificación de configuración al inicio
- ✅ Logs con claves parcialmente ocultadas

### ⚠️ Recomendaciones:
- No commits las claves en Git
- Usar archivos .env solo en desarrollo
- En producción, usar servicios de secrets (Azure Key Vault, etc.)

## 📞 SOPORTE

Si encuentras problemas, revisa:
1. Logs del contenedor: `docker logs [container-name]`
2. Variables de entorno configuradas correctamente
3. Conectividad a Azure OpenAI
4. Puertos disponibles

## 🌐 CONFIGURACIÓN DE PUERTOS

### Para cambiar el puerto (ejemplo: puerto 80):
```bash
docker run -d \
  --name ai-innovation-prod \
  -p 80:7860 \
  --restart unless-stopped \
  ai-innovation-sener
```

## 🔧 VARIABLES DE ENTORNO (SI ES NECESARIO)

Si la app necesita variables específicas:
```bash
docker run -d \
  --name ai-innovation-prod \
  -p 7860:7860 \
  -e VARIABLE_NAME=valor \
  --restart unless-stopped \
  ai-innovation-sener
```

## ✅ VERIFICACIÓN DE FUNCIONAMIENTO

1. ✅ Contenedor ejecutándose: `docker ps`
2. ✅ Logs sin errores: `docker logs ai-innovation-prod`
3. ✅ Puerto accesible: `curl http://localhost:7860`
4. ✅ Interfaz web carga correctamente

---

## 📞 CONTACTO
Si hay problemas, contactar con el desarrollador de la aplicación. 
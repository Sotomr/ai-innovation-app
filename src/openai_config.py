# Silenciar todos los warnings
import warnings
warnings.filterwarnings('ignore')

import os
from openai import AzureOpenAI

# Configuración de Azure OpenAI
#AZURE_OPENAI_ENDPOINT = "end pointt"
#AZURE_OPENAI_API_KEY = "key"
#DEPLOYMENT_NAME = "gpt-4o"
#API_VERSION = "2024-05-01-preview"

# Configuración de Azure OpenAI
#AZURE_OPENAI_ENDPOINT = "end point"
#AZURE_OPENAI_API_KEY = "key"
#DEPLOYMENT_NAME = "gpt-o3-mini"
#API_VERSION = "2025-01-31-preview"

# ⚠️ CONFIGURACIÓN CON VARIABLES DE ENTORNO (SEGURO) ⚠️
# Las claves se pasan al ejecutar Docker, no están en el código

# Leer configuración desde variables de entorno
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY") 
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "gpt-o3-mini")  # Valor por defecto
API_VERSION = os.getenv("API_VERSION", "2025-01-31-preview")   # Valor por defecto

# Verificar que las variables obligatorias estén configuradas
if not AZURE_OPENAI_ENDPOINT:
    raise ValueError("❌ ERROR: La variable de entorno AZURE_OPENAI_ENDPOINT no está configurada")

if not AZURE_OPENAI_API_KEY:
    raise ValueError("❌ ERROR: La variable de entorno AZURE_OPENAI_API_KEY no está configurada")

# Mostrar configuración (sin mostrar la clave completa por seguridad)
print(f"🔧 Configuración Azure OpenAI:")
print(f"   - Endpoint: {AZURE_OPENAI_ENDPOINT}")
print(f"   - API Key: {AZURE_OPENAI_API_KEY[:10]}...{AZURE_OPENAI_API_KEY[-4:] if len(AZURE_OPENAI_API_KEY) > 14 else '***'}")
print(f"   - Deployment: {DEPLOYMENT_NAME}")
print(f"   - API Version: {API_VERSION}")

# Inicializar el cliente de Azure OpenAI
try:
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_deployment=DEPLOYMENT_NAME,
        max_retries=3
    )
    print("✅ Cliente Azure OpenAI inicializado correctamente")
except Exception as e:
    print(f"❌ Error inicializando cliente Azure OpenAI: {str(e)}")
    raise

def get_openai_client():
    """Retorna el cliente de OpenAI configurado"""
    return client

def get_deployment_name():
    """Retorna el nombre del deployment"""
    return DEPLOYMENT_NAME 
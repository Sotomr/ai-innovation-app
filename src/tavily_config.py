"""
Configuración para el uso de la API de Tavily
"""

# Silenciar warnings
import warnings
warnings.filterwarnings('ignore')

import os

# API Key para Tavily (puede estar hardcodeada si así lo deseas)
TAVILY_API_KEY = "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"

# Nombre de la API
TAVILY_API_NAME = "Sener2"

def get_tavily_api_key():
    """
    Retorna la API key de Tavily, primero buscando en variables de entorno
    
    Returns:
        str: API key de Tavily
    """
    env_key = os.environ.get("TAVILY_API_KEY")
    if env_key:
        print(f"✅ Usando TAVILY_API_KEY de entorno: {env_key[:12]}... (longitud: {len(env_key)})")
        return env_key
    
    # Si no hay variable de entorno, usar la key hardcodeada
    if not TAVILY_API_KEY:
        raise RuntimeError("❌ No se ha configurado una API key válida para Tavily. Debes poner TAVILY_API_KEY en el entorno o en el código fuente.")
    print(f"⚠️ Usando TAVILY_API_KEY hardcodeada: {TAVILY_API_KEY[:12]}... (longitud: {len(TAVILY_API_KEY)})")
    return TAVILY_API_KEY

def set_tavily_api_key():
    """
    Configura la API key de Tavily como variable de entorno
    """
    key = get_tavily_api_key()
    if key:
        os.environ["TAVILY_API_KEY"] = key
        print(f"✅ API key de Tavily configurada: {TAVILY_API_NAME}")
        return True
    else:
        print("⚠️ No se ha configurado la API key de Tavily") 
        return False 
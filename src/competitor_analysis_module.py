import os
import json
import time
import concurrent.futures
import traceback
import time
from datetime import datetime
import random
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple, Union
import re
import tempfile
import unicodedata
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
import uuid
import PyPDF2
import spacy
import subprocess
import pprint
import hashlib
import functools
import dotenv
from sentence_transformers import SentenceTransformer, util
dotenv.load_dotenv()

# Importaciones de LangChain actualizadas
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Importar AzureChatOpenAI desde langchain_openai en lugar de langchain.chat_models
from langchain_openai import AzureChatOpenAI
# Importar DuckDuckGo para búsqueda web
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

# Importaciones para OpenAI directo
from openai import OpenAI, AzureOpenAI
from openai_config import get_openai_client, get_deployment_name

# Configuración global para forzar response_format en formato JSON
JSON_RESPONSE_FORMAT = {"type": "json_object"}
# Temperatura más baja para respuestas determinísticas en JSON
SAFE_TEMPERATURE = 0.0

# Cliente de OpenAI para uso directo
client = get_openai_client()
DEPLOYMENT_NAME = get_deployment_name()

# Importar el nuevo módulo de PDF
from competition_pdf_module import generate_competition_analysis_pdf, generate_professional_report_pdf

# Importar langchain_tavily y tavily_config
from langchain_tavily import TavilySearch
from tavily_config import get_tavily_api_key, set_tavily_api_key

from llm_utils import get_llm_keywords

from query_generator import generate_queries

# --- Carga robusta de Spacy ---
try:
    nlp = spacy.load("es_core_news_sm")
except Exception as e:
    print(f"⚠️ No se pudo cargar 'es_core_news_sm': {e}. Usando modelo en blanco.")
    nlp = spacy.blank("es")

STOPWORDS = {"el","la","los","las","de","del","para","con","un","una","en","por","que","y"}

# --- SECTION_SCHEMAS global inmutable para AI-only ---
SECTION_SCHEMAS = {
    'COMPETITOR_MAPPING': '{"competidores_directos":[],"competidores_indirectos":[],"emergentes":[]}',
    'BENCHMARK_MATRIX': '{"tabla_comparativa":[{"nombre":"","ingresos_anuales_millones_eur":0,"empleados_total":0,"años_en_mercado":0,"paises_presencia":0,"proyectos_anuales_estimados":0,"precio_promedio_proyecto_millones":0,"cuota_mercado_sector_porcentaje":0,"gasto_id_porcentaje_ingresos":0,"certificaciones_principales":0,"patentes_activas_estimadas":0}],"metricas_comparativas":{"lider_ingresos":{"empresa":"","valor":0},"lider_empleados":{"empresa":"","valor":0},"lider_cuota_mercado":{"empresa":"","valor":0},"promedio_sector_ingresos":0,"promedio_sector_empleados":0},"gaps_cuantitativos":[{"metrica":"","brecha_identificada":"","oportunidad_sener":""}]}',
    'TECH_IP_LANDSCAPE': '{"patentes_destacadas":[{"titulo":"","numero_patente":"","titular":"","año":"","pais":"","descripcion":"","relevancia_competitiva":"","url":""}],"publicaciones_clave":[{"titulo":"","autores":"","revista":"","año":"","tipo":"","resumen":"","relevancia_tecnologica":"","url":""}],"gaps_tecnologicos":[{"area_tecnologica":"","descripcion_gap":"","impacto_competitivo":"","oportunidad_sener":""}],"tendencias_emergentes":[{"tecnologia":"","estado_madurez":"","potencial_disruptivo":"","plazo_adopcion":""}]}',
    'MARKET_ANALYSIS': '{"TAM_2025":0,"CAGR_2025_2030":0,"segmentos":[],"geografias":[],"drivers":[],"restrictores":[],"analisis_cualitativo":{"gaps_identificados":[],"oportunidades_sener":[]}}',
    'SWOT_POSITIONING': '{"swot":{"fortalezas":[],"debilidades":[],"oportunidades":[],"amenazas":[]},"mapa_posicionamiento":{"eje_x":"","eje_y":"","comentario":""}}',
    'REGULATORY_ESG_RISK': '{"normativas_clave":[],"certificaciones":[],"riesgos":[],"oportunidades_ESG":[]}',
    'STRATEGIC_ROADMAP': '{"acciones_90_dias":[],"acciones_12_meses":[],"acciones_36_meses":[],"KPIs_clave":[]}',
    'APPENDIX': '{"glosario":{},"metodologia":"","limitaciones":""}',
    'EXEC_SUMMARY': '{"resumen":"","bullets":[]}'
}

def _extract_keywords(text: str, k: int = 3) -> str:
    """Devuelve ≤k lemas relevantes (NOUN, PROPN, ADJ)."""
    doc = nlp(text[:120])  # analiza solo la 1.ª frase
    tokens = [t.lemma_.lower() for t in doc
              if t.pos_ in {"NOUN", "PROPN", "ADJ"}
              and len(t) > 3
              and t.lemma_.lower() not in STOPWORDS]
    seen, kw = set(), []
    for tok in tokens:
        if tok not in seen:
            seen.add(tok)
            kw.append(tok)
        if len(kw) == k:
            break
    return " ".join(kw) if kw else " ".join(text.split()[:k])

def extract_json_block(text):
    """
    Extrae el primer bloque JSON válido de un texto, incluso si está dentro de un bloque de código.
    Intenta limpiar y reparar el JSON si está malformado, incluyendo la inserción de comas faltantes entre pares clave-valor.
    """
    import re, json, os, traceback
    
    # Validar tipo de entrada
    if text is None:
        raise ValueError("El texto de entrada es None")
    
    if not isinstance(text, str):
        # Si ya es un diccionario, devolverlo directamente
        if isinstance(text, dict):
            print("⚠️ La entrada ya es un diccionario, no requiere extracción.")
            return text
        else:
            print(f"⚠️ La entrada no es una cadena, es un {type(text)}. Intentando convertir...")
            text = str(text)
    
    # Guardar entrada original para depuración
    try:
        os.makedirs("output", exist_ok=True)
        with open("output/extract_json_input.txt", "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"⚠️ No se pudo guardar entrada para depuración: {e}")
    
    # Buscar bloques de código con json
    code_block = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    candidate = code_block.group(1) if code_block else text
    
    # Buscar el primer objeto JSON en el texto
    json_match = re.search(r"(\{[\s\S]*\})", candidate)
    json_str = json_match.group(1) if json_match else candidate
    
    # Limpieza básica
    json_str = json_str.replace("\n", " ")
    json_str = re.sub(r"\s+", " ", json_str)
    json_str = re.sub(r"//.*", "", json_str)  # Eliminar comentarios
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)  # Eliminar comas colgantes
    
    # Reparar problemas comunes de sintaxis JSON
    # Insertar comas entre líneas que parecen pares clave-valor
    lines = json_str.split("\n")
    fixed_json = ""
    for i, line in enumerate(lines):
        fixed_json += line
        if i < len(lines) - 1:
            current_line = line.strip()
            next_line = lines[i+1].strip()
            if ('"' in current_line and ':' in current_line and 
                not current_line.endswith(",") and 
                next_line.startswith('"')):
                fixed_json += ","
    
    json_str = fixed_json
    
    # Intentar cargar el JSON con diferentes estrategias
    last_exception = None
    try_count = 0
    
    # Estrategia 1: JSON original limpiado
    try:
        return json.loads(json_str)
    except Exception as e:
        last_exception = e
        try_count += 1
    
    # Estrategia 2: Eliminar espacios
    try:
        cleaned = re.sub(r"\s+", "", json_str)
        return json.loads(cleaned)
    except Exception as e:
        last_exception = e
        try_count += 1
    
    # Estrategia 3: Envolver en llaves si no están
    try:
        if not json_str.startswith("{"):
            wrapped = "{" + json_str + "}"
            return json.loads(wrapped)
    except Exception as e:
        last_exception = e
        try_count += 1
    
    # Si todo falla, guardar para depuración y lanzar error
    try:
        with open("output/llm_json_error.txt", "w", encoding="utf-8") as f:
            f.write(text)
        with open("output/llm_json_cleaned.txt", "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception:
        pass
    print(f"❌ Error al analizar JSON: {last_exception}")
    traceback.print_exc()
    # --- MEJORA ROBUSTA: nunca romper el flujo, devolver objeto vacío profesional ---
    return {"error": "No se pudo extraer JSON", "detalle": str(last_exception)}

class CompetitorAnalysis:
    """
    Análisis competitivo LLM-first: el LLM genera el informe completo, y solo si lo pide se hace scraping puntual.
    """
    _init_logged = False
    SENER_CONTEXT = '''Sener: Ingeniería, tecnología e innovación con visión global

Sener es un grupo privado de ingeniería y tecnología fundado en 1956, con sede en España y una sólida proyección internacional. A lo largo de sus más de seis décadas de trayectoria, Sener se ha consolidado como un referente en la ejecución de proyectos de alta complejidad técnica, aportando soluciones innovadoras en sectores estratégicos clave para el desarrollo sostenible y el progreso tecnológico.

Áreas de especialización:

Sener combina ingeniería avanzada, desarrollo tecnológico y capacidad constructiva para ofrecer soluciones integrales que abarcan desde la consultoría y diseño hasta la implementación y operación de sistemas complejos. Sus principales áreas de enfoque incluyen:

Ingeniería y construcción en sectores críticos, aplicando altos estándares de calidad, seguridad y sostenibilidad.

Desarrollo de sistemas y software a medida para sectores de alto valor estratégico, como defensa, energía y transporte.

Innovación tecnológica, con una fuerte inversión en I+D para el desarrollo de soluciones avanzadas que aporten valor diferencial a sus clientes.

Sectores clave de actividad:

Aeroespacial: Sener participa en misiones espaciales internacionales con el diseño, integración y fabricación de componentes y sistemas para satélites, vehículos espaciales y estaciones orbitales.

Infraestructuras y Transporte: Especialista en proyectos de gran escala como ferrocarriles, metros, carreteras y obras hidráulicas, incluyendo diseño de trazados, estructuras, sistemas y gestión del transporte. Las líneas estratégicas que se estan abriendo y explorando en innovación son hospital adaptable, transformación de instalaciones deportivas y de entretenimiento en espacios multifuncionales, infraestructura para el vehículo autónomo, puertos flotantes, centrales hidroeléctricas reversibles usando agua de mar, hiper-aprovechamiento de la infraestructura del metro.

Energía: Impulsa la transición energética mediante proyectos en energías renovables (solar, eólica, hidrógeno verde), eficiencia energética, almacenamiento y soluciones inteligentes de red.

Digitalización: Lidera procesos de transformación digital con soluciones de automatización, gemelos digitales, inteligencia artificial y sistemas ciberfísicos aplicados a sectores industriales complejos.

Centros de datos: Infraestructura para los centros de datos

# -----------------------------------------------------------------------------
# COMPETIDORES BASE MONITORIZADOS (DEBEN VERIFICARSE PARA CADA IDEA)
# -----------------------------------------------------------------------------
# IMPORTANTE PARA EL LLM: La siguiente lista constituye una base de referencia
# de compañías que históricamente compiten con Sener.  NO significa que deban
# aparecer automáticamente como competidores en todos los análisis.  Para cada
# nueva idea o sector analizado, SOLO deben incluirse aquellos que presenten
# evidencia real (proyectos, patentes, soluciones, comunicación oficial)
# alineada con la idea concreta.  Si la evidencia no existe o es débil, el LLM
# deberá omitirlos y buscar otros actores más pertinentes.
#  •  NUNCA incluyas a Sener como competidor.
#  •  Justifica internamente (no en la respuesta) la inclusión de cada empresa.
#  •  Prefiere siempre datos verificados sobre tamaño, país y foco tecnológico.
#
# 1) IDOM:  Movilidad sostenible; big-data/IA; soluciones energéticas; optimización de procesos; innovación y digitalización.
# 2) Abengoa:  Infraestructura ferroviaria; redes inteligentes 5E reversibles; proyectos de hidrógeno.
# 3) Typsa: Ingeniería multidisciplinar; participación ocasional en infraestructuras de transporte (baja relevancia tecnológica actual).
# 4) AECOM: Servicios globales de ingeniería y consultoría; proyectos de transporte y energía (revisar caso a caso).
# 5) Elecnor: Ingeniería y construcción de grandes infraestructuras; presencia internacional (datos públicos limitados en áreas deep-tech).
# 6) Atkins: Desarrollo de software y servicios de ingeniería; experiencia en movilidad y planificación.
# 7) ARUP: Diseño de infraestructuras; asset-management; mantenimiento; consultoría digital avanzada.
# 8) Jacobs: Climate response; data solutions; consultoría y advisory en grandes proyectos de infraestructura.
# 9) Indra: Automatización aérea; navegación; drones; comunicaciones críticas y sistemas de información.
# 10) Ineco: Cambio climático; renovables; optimización de procesos; innovación y digitalización en transporte.
#
# El modelo debe evaluar críticamente esta base y complementar O SUSTITUIR los
# nombres con otros competidores más adecuados si el ámbito tecnológico o de
# mercado de la IDEA lo requiere. MUY IMPORTANTE ANALIZARLO CRITICAMENTE
# -----------------------------------------------------------------------------
 '''
    def __init__(self, max_workers=4):
        print("🟢 [CompetitorAnalysis] Inicializando clase CompetitorAnalysis...")
        self.max_workers = max_workers
        self.llm = None
        self.completion_llm = None
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)
        self.public_downloads_dir = "public_downloads"
        os.makedirs(self.public_downloads_dir, exist_ok=True)
        self._initialize_llm()
    def _initialize_llm(self):
        print("🔄 [CompetitorAnalysis] Inicializando modelo de lenguaje...")
        try:
            from openai_config import get_openai_client, get_deployment_name, AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, API_VERSION
            self.openai_client = get_openai_client()
            self.deployment_name = get_deployment_name()
            try:
                import os
                os.environ["AZURE_OPENAI_API_KEY"] = AZURE_OPENAI_API_KEY
                os.environ["OPENAI_API_VERSION"] = API_VERSION
                os.environ["OPENAI_API_KEY"] = AZURE_OPENAI_API_KEY
                from langchain_openai import AzureChatOpenAI
                config = {
                    "deployment_name": self.deployment_name,
                    "model_name": self.deployment_name,
                    "azure_endpoint": AZURE_OPENAI_ENDPOINT,
                    "api_version": API_VERSION,
                    "api_key": AZURE_OPENAI_API_KEY,
                    "temperature": 0.7,
                    "max_retries": 3
                }
                llm = AzureChatOpenAI(**config)
                if not CompetitorAnalysis._init_logged:
                    print(f"✅ Modelo LangChain inicializado correctamente: {self.deployment_name}")
                    print("✅ self.llm y self.completion_llm asignados al modelo Azure/OpenAI")
                    CompetitorAnalysis._init_logged = True
                self.llm = llm
                self.completion_llm = llm
                return llm
            except Exception as langchain_error:
                if not CompetitorAnalysis._init_logged:
                    print(f"⚠️ No se pudo inicializar LangChain: {str(langchain_error)}")
                traceback.print_exc()
                print("ℹ️ Se utilizará llamada directa a la API")
                self.llm = None
                self.completion_llm = None
                return None
        except Exception as e:
            if not CompetitorAnalysis._init_logged:
                print(f"❌ Error al inicializar LLM: {str(e)}")
            traceback.print_exc()
            self.llm = None
            self.completion_llm = None
            return None
    
    # --- NUEVO: caché muy pequeña para no llamar al LLM dos veces con la misma idea
    _sector_cache: dict = {}

    def _sector_terms(self, idea_text: str, k: int = 10) -> list[str]:
        """
        Devuelve la lista de keywords sectoriales usando un mini-LLM.
        - k = nº máximo de keywords que quieres.
        - Si el LLM falla, usa fallback heurístico.
        """
        import hashlib
        key = hashlib.sha1(idea_text.encode()).hexdigest()
        # 1. ¿ya lo tenemos cacheado?
        if key in self._sector_cache:
            return self._sector_cache[key]

        try:
            prompt = (
                "Eres analista competitivo. Devuelve SOLO un objeto JSON con esta forma:\n"
                '{ "sector": "<nombre-sector>", "keywords": ["kw1","kw2",...]} \n'
                "- sector debe ser 1-3 palabras y en minúsculas.\n"
                f"- keywords: entre 4 y {k} palabras/frases típicas para buscar competidores.\n"
                "- No pongas texto fuera del JSON.\n\n"
                "IDEA:\n" + idea_text[:600]
            )

            resp = self.openai_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system",
                     "content": "Eres un analista experto en detectar sectores y palabras clave."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=120,
                response_format={"type": "json_object"}
            )
            import json
            data = json.loads(resp.choices[0].message.content)
            kws  = [kw.strip() for kw in data.get("keywords", []) if kw.strip()]
            # mínimo 3 keywords: si no, forzamos fallback
            if len(kws) >= 3:
                self._sector_cache[key] = kws[:k]
                # LRU manual: si supera 128 entradas, elimina la más antigua
                if len(self._sector_cache) > 128:
                    oldest = next(iter(self._sector_cache))
                    del self._sector_cache[oldest]
                return kws[:k]

        except Exception as e:
            print(f"⚠️ _sector_terms LLM falló: {e}")

        # --- Fallback: heurística ligera que ya tenías
        basic = _extract_keywords(idea_text, k=3).split()
        fallback = basic + ["technology","market","solution"]
        return fallback[:k]

    @functools.lru_cache(maxsize=128)
    def llm_short_queries(self, idea: str, k: int = 6) -> list[str]:
        """
        Devuelve ≤k queries cortísimas (≤5 palabras, ≤40 chars),
        en ≥3 idiomas distintos, e incluye al menos 1 con 'filetype:pdf'.
        """
        # --- NUEVO: Usa function-calling y JsonOutputParser para queries robustas ---
        schema = JsonOutputParser()
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Eres analista competitivo. Devuelve SOLO una lista JSON "
             f"con máx {k} strings (2-5 palabras, ≤40 car.). Usa ≥3 idiomas "
             "y al menos la mitad incluyen 'filetype:pdf'. Nada fuera del JSON."),
            ("user", idea[:400])
        ])
        try:
            chain = prompt | self.llm | schema
            result = chain.invoke({})
            uniq = list(dict.fromkeys(s.strip() for s in result if s.strip()))
            with_pdf = [q for q in uniq if "filetype:pdf" in q.lower()]
            if not with_pdf:
                kw = _extract_keywords(idea, k=1) or "market"
                uniq.append(f"{kw} filetype:pdf")
            return uniq[:k]
        except Exception as e:
            print(f"⚠️ generate_search_queries fallback: {e}")
            # --- Heurística propia si falla el LLM ---
            kw = _extract_keywords(idea, k=3)
            queries = []
            if kw:
                queries.append(kw)
                queries.append(f"{kw} filetype:pdf")
            try:
                from deep_translator import GoogleTranslator
                kw_en = GoogleTranslator(source='auto', target='en').translate(kw)
                queries.append(kw_en)
                queries.append(f"{kw_en} filetype:pdf")
                kw_fr = GoogleTranslator(source='auto', target='fr').translate(kw)
                queries.append(kw_fr)
                queries.append(f"{kw_fr} filetype:pdf")
            except Exception:
                pass
            if not queries:
                queries = ["market filetype:pdf", "competitors", "benchmarking filetype:pdf"]
            uniq = list(dict.fromkeys(q for q in queries if q and isinstance(q, str)))
            return uniq[:k]

    def generate_search_queries(self, idea_text: str, k: int = 6) -> list[str]:
        """
        Genera queries cortas y multi-idioma para búsqueda competitiva. Usa LLM y heurística como fallback.
        """
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser
        schema = JsonOutputParser()
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Eres analista competitivo. Devuelve SOLO una lista JSON "
             f"con máx {k} strings (2-5 palabras, ≤40 car.). Usa ≥3 idiomas "
             "y al menos la mitad incluyen 'filetype:pdf'. Nada fuera del JSON."),
            ("user", idea_text[:400])
        ])
        try:
            chain = prompt | self.llm | schema
            result = chain.invoke({})
            uniq = list(dict.fromkeys(s.strip() for s in result if s.strip()))
            with_pdf = [q for q in uniq if "filetype:pdf" in q.lower()]
            if not with_pdf:
                kw = _extract_keywords(idea_text, k=1) or "market"
                uniq.append(f"{kw} filetype:pdf")
            return uniq[:k]
        except Exception as e:
            print("⚠️ LLM queries falló, usando heurística.")
            # --- Heurística propia si falla el LLM ---
            kw = _extract_keywords(idea_text, k=3)
            queries = []
            if kw:
                queries.append(kw)
                queries.append(f"{kw} filetype:pdf")
            try:
                from deep_translator import GoogleTranslator
                kw_en = GoogleTranslator(source='auto', target='en').translate(kw)
                queries.append(kw_en)
                queries.append(f"{kw_en} filetype:pdf")
                kw_fr = GoogleTranslator(source='auto', target='fr').translate(kw)
                queries.append(kw_fr)
                queries.append(f"{kw_fr} filetype:pdf")
            except Exception:
                pass
            if not queries:
                queries = ["market filetype:pdf", "competitors", "benchmarking filetype:pdf"]
            uniq = list(dict.fromkeys(q for q in queries if q and isinstance(q, str)))
            return uniq[:k]

    def _extract_competitors_from_mapping(self, report_dict):
        """
        Extrae todos los competidores identificados en COMPETITOR_MAPPING
        para usar en BENCHMARK_MATRIX (evitar duplicación y asegurar consistencia)
        """
        competitors_list = []
        
        print(f"🔍 [BENCHMARK-EXTRACT] Iniciando extracción de competidores...")
        print(f"🔍 [BENCHMARK-EXTRACT] report_dict keys disponibles: {list(report_dict.keys()) if report_dict else 'None'}")
        
        if 'COMPETITOR_MAPPING' in report_dict and isinstance(report_dict['COMPETITOR_MAPPING'], dict):
            # 🚨 CRITICAL FIX: Handle both direct data and wrapped data structure
            raw_mapping = report_dict['COMPETITOR_MAPPING']
            if 'datos' in raw_mapping and isinstance(raw_mapping['datos'], dict):
                mapping_data = raw_mapping['datos']  # Unwrap from {'datos': ..., 'texto': ...} structure
                print(f"🔍 [BENCHMARK-EXTRACT] Using wrapped data structure")
            else:
                mapping_data = raw_mapping  # Direct data structure
                print(f"🔍 [BENCHMARK-EXTRACT] Using direct data structure")
            print(f"🔍 [BENCHMARK-EXTRACT] COMPETITOR_MAPPING keys: {list(mapping_data.keys())}")
            
            # Extraer de las 3 categorías tradicionales
            categories = ['competidores_directos', 'competidores_indirectos', 'emergentes']
            for category in categories:
                if category in mapping_data and isinstance(mapping_data[category], list):
                    print(f"🔍 [BENCHMARK-EXTRACT] Procesando categoría '{category}' con {len(mapping_data[category])} items")
                    for i, comp in enumerate(mapping_data[category]):
                        if isinstance(comp, dict) and comp.get('nombre'):
                            competitors_list.append({
                                'nombre': comp['nombre'],
                                'categoria': category,
                                'sector': comp.get('sector', ''),
                                'tamano': comp.get('tamano', ''),
                                'pais': comp.get('pais', ''),
                                'descripcion': comp.get('descripcion', '')
                            })
                            print(f"  ✅ Extraído: {comp['nombre']} ({category})")
                        else:
                            print(f"  ⚠️ Item {i} en {category} no válido: {comp}")
                else:
                    print(f"🔍 [BENCHMARK-EXTRACT] Categoría '{category}' no encontrada o no es lista")
            
            # 🔧 NUEVA BÚSQUEDA: También buscar en estructuras alternativas
            alternative_keys = ['empresas_competidoras', 'competidores_principales', 'main_competitors', 'competidores']
            for alt_key in alternative_keys:
                if alt_key in mapping_data and isinstance(mapping_data[alt_key], list):
                    print(f"🔍 [BENCHMARK-EXTRACT] Encontrada estructura alternativa '{alt_key}' con {len(mapping_data[alt_key])} items")
                    for comp in mapping_data[alt_key]:
                        if isinstance(comp, dict) and comp.get('nombre'):
                            # Evitar duplicados
                            if not any(existing['nombre'] == comp['nombre'] for existing in competitors_list):
                                competitors_list.append({
                                    'nombre': comp['nombre'],
                                    'categoria': 'extraido_alternativo',
                                    'sector': comp.get('sector', ''),
                                    'tamano': comp.get('tamano', ''),
                                    'pais': comp.get('pais', ''),
                                    'descripcion': comp.get('descripcion', '')
                                })
                                print(f"  ✅ Extraído (alternativo): {comp['nombre']}")
                        elif isinstance(comp, str):
                            # Casos donde el competidor es solo un string
                            if not any(existing['nombre'] == comp for existing in competitors_list):
                                competitors_list.append({
                                    'nombre': comp,
                                    'categoria': 'extraido_alternativo',
                                    'sector': '',
                                    'tamano': '',
                                    'pais': '',
                                    'descripcion': ''
                                })
                                print(f"  ✅ Extraído (string): {comp}")
        else:
            print(f"⚠️ [BENCHMARK-EXTRACT] No se encontró COMPETITOR_MAPPING válido")
        
        print(f"✅ [BENCHMARK-EXTRACT] TOTAL extraídos: {len(competitors_list)} competidores de COMPETITOR_MAPPING")
        for i, comp in enumerate(competitors_list):
            print(f"  {i+1}. {comp['nombre']} ({comp['categoria']})")
        
        return competitors_list

    def _generate_benchmark_prompt_with_competitors(self, competitors_list, shared_inputs):
        """
        Genera prompt específico de BENCHMARK_MATRIX incluyendo los competidores ya identificados
        para asegurar consistencia y evitar duplicación
        """
        if not competitors_list:
            print("⚠️ [BENCHMARK] No hay competidores disponibles, usando prompt genérico")
            # Retornar prompt genérico básico
            return """
            Genera tabla comparativa CUANTITATIVA para BENCHMARK_MATRIX.
            ESTRUCTURA JSON REQUERIDA: 'tabla_comparativa', 'metricas_comparativas', 'gaps_cuantitativos'
            USA SOLO métricas numéricas específicas. NO texto descriptivo largo.
            """
        
        # Crear lista detallada de competidores para el prompt
        competitors_text = "\n".join([
            f"- {comp['nombre']} (Categoría: {comp['categoria']}, Tamaño: {comp['tamano']}, Sector: {comp['sector']}, País: {comp['pais']})"
            for comp in competitors_list
        ])
        
        # Usar las instrucciones básicas de BENCHMARK_MATRIX con FORZADO ABSOLUTO
        competitors_names = [comp.get('nombre', '') for comp in competitors_list if comp.get('nombre')]
        competitors_names_simple = ", ".join(competitors_names[:8])  # Límite de 8 para no saturar
        
        base_prompt = f"""
        Instrucciones para la tabla comparativa:

        • Utiliza únicamente las siguientes empresas como filas de la tabla: {competitors_names_simple}
        • No incluyas empresas genéricas (por ejemplo Siemens, GE, ABB, Schneider, etc.) salvo que aparezcan en la lista anterior.
        • Elabora métricas cuantitativas realistas para cada compañía; si no dispones de un dato fiable, escribe "N/D".
        • Devuelve siempre un objeto JSON con tres claves: 'tabla_comparativa', 'metricas_comparativas', 'gaps_cuantitativos'.
        • No introduzcas ningún otro texto fuera del JSON.

        Recuerda que Sener no debe figurar como competidor.
        """
        
        # Prompt específico con los competidores extraídos
        enhanced_prompt = f"""
COMPETIDORES ESPECÍFICOS A ANALIZAR (usar EXACTAMENTE estos {len(competitors_list)} competidores):

{competitors_text}

IDEA ANALIZADA: {shared_inputs.get('idea_brief', shared_inputs.get('idea_text', ''))[:300]}...
SECTOR ESPECÍFICO: {shared_inputs.get('brief', '')}
CONTEXTO: {shared_inputs.get('contexto_usuario', shared_inputs.get('context', ''))[:200]}...

INSTRUCCIONES ESPECÍFICAS PARA ESTA IDEA:

{base_prompt}

🚨🚨🚨 FORMATO JSON OBLIGATORIO - NO USAR 'tabla' 🚨🚨🚨
CRÍTICO: Tu respuesta JSON debe incluir TODOS los competidores listados arriba en 'tabla_comparativa'.
🚫 PROHIBIDO: NO usar campo 'tabla' - SOLO 'tabla_comparativa' 
✅ OBLIGATORIO: Usar exactamente 'tabla_comparativa', 'metricas_comparativas', 'gaps_cuantitativos'
Para cada empresa, estima las métricas basándote en:
1. Su categoría (directos/indirectos/emergentes)  
2. Su tamaño declarado (Pequeña/Mediana/Grande/Multinacional)
3. Su sector específico
4. El contexto de la idea analizada

EJEMPLO DE ESTRUCTURA DE RESPUESTA:
{{
  "tabla_comparativa": [
    {{"nombre": "Primer competidor de la lista", "ingresos_anuales_millones_eur": [cifra estimada], "empleados_total": [cifra estimada], ...}},
    {{"nombre": "Segundo competidor de la lista", "ingresos_anuales_millones_eur": [cifra estimada], "empleados_total": [cifra estimada], ...}},
    ... (continuar con TODOS los competidores listados)
  ],
  "metricas_comparativas": {{
    "lider_ingresos": {{"empresa": "[nombre del líder]", "valor": [cifra]}},
    ...
  }},
  "gaps_cuantitativos": [...]
}}

🔥 VERIFICACIÓN FINAL: Tu JSON DEBE contener 'tabla_comparativa' (NO 'tabla') 🔥
"""
        
        print(f"✅ [BENCHMARK] Prompt generado con {len(competitors_list)} competidores específicos")
        return enhanced_prompt

    def _validate_benchmark_competitor_coherence(self, benchmark_data, report_dict):
        """
        🎯 NUEVA FUNCIÓN ROBUSTA: Valida que las empresas del benchmark sean coherentes con COMPETITOR_MAPPING
        Si hay inconsistencias críticas, regenera usando competidores específicos.
        """
        try:
            if not report_dict or not isinstance(benchmark_data, dict):
                print("⚠️ [BENCHMARK-COHERENCE] No hay datos suficientes para validación de coherencia")
                return benchmark_data
            
            # 1. Extraer competidores del COMPETITOR_MAPPING si existe
            mapping_competitors = []
            if 'COMPETITOR_MAPPING' in report_dict:
                mapping_data = report_dict['COMPETITOR_MAPPING']
                if isinstance(mapping_data, dict):
                    # Extraer de diferentes campos posibles
                    for key in ['empresas_competidoras', 'competidores_principales', 'main_competitors']:
                        if key in mapping_data and isinstance(mapping_data[key], list):
                            for comp in mapping_data[key]:
                                if isinstance(comp, dict) and 'nombre' in comp:
                                    mapping_competitors.append(comp['nombre'].strip())
                                elif isinstance(comp, str):
                                    mapping_competitors.append(comp.strip())
                    
                    # También buscar en estructura plana
                    if 'competidores' in mapping_data and isinstance(mapping_data['competidores'], list):
                        for comp in mapping_data['competidores']:
                            if isinstance(comp, str):
                                mapping_competitors.append(comp.strip())
            
            # Limpiar competidores extraídos
            mapping_competitors = [comp for comp in mapping_competitors if comp and len(comp) > 2]
            # ---- NUEVO: si la lista sigue vacía, extraer de las claves estándar ----
            if not mapping_competitors and 'COMPETITOR_MAPPING' in report_dict:
                try:
                    full_list = self._extract_competitors_from_mapping(report_dict)
                    mapping_competitors = [c['nombre'] for c in full_list if c.get('nombre')]
                except Exception:
                    pass
            # -----------------------------------------------------------------------
            
            if not mapping_competitors:
                print("ℹ️ [BENCHMARK-COHERENCE] No se encontraron competidores específicos en COMPETITOR_MAPPING")
                return benchmark_data
            
            print(f"📋 [BENCHMARK-COHERENCE] Competidores del mapping: {mapping_competitors}")
            
            # 2. Extraer competidores del benchmark actual
            benchmark_competitors = []
            tabla_key = 'tabla_comparativa' if 'tabla_comparativa' in benchmark_data else 'tabla'
            
            if tabla_key in benchmark_data and isinstance(benchmark_data[tabla_key], list):
                for comp in benchmark_data[tabla_key]:
                    if isinstance(comp, dict) and 'nombre' in comp:
                        nombre = comp['nombre'].strip()
                        if 'sener' not in nombre.lower():
                            benchmark_competitors.append(nombre)
            
            print(f"📊 [BENCHMARK-COHERENCE] Competidores en benchmark: {benchmark_competitors}")
            
            # 3. Calcular coincidencias usando comparación fuzzy
            import difflib
            
            coincidencias = 0
            mapping_lower = [comp.lower() for comp in mapping_competitors]
            
            for bench_comp in benchmark_competitors:
                bench_lower = bench_comp.lower()
                
                # Buscar coincidencias exactas
                if bench_lower in mapping_lower:
                    coincidencias += 1
                    continue
                
                # Buscar coincidencias fuzzy (>= 0.8 de similitud)
                for map_comp_lower in mapping_lower:
                    similarity = difflib.SequenceMatcher(None, bench_lower, map_comp_lower).ratio()
                    if similarity >= 0.8:
                        coincidencias += 1
                        break
            
            coherence_ratio = coincidencias / len(benchmark_competitors) if benchmark_competitors else 0
            print(f"📈 [BENCHMARK-COHERENCE] Ratio de coherencia: {coherence_ratio:.2f} ({coincidencias}/{len(benchmark_competitors)})")
            
            # 4. Si la coherencia es baja (< 50%), intentar corrección automática
            if coherence_ratio < 0.5 and len(mapping_competitors) >= 3:
                print(f"🔧 [BENCHMARK-COHERENCE] Coherencia baja ({coherence_ratio:.2f}), aplicando corrección automática...")
                
                # Mantener estructura pero reemplazar empresas
                if tabla_key in benchmark_data and isinstance(benchmark_data[tabla_key], list):
                    tabla_original = benchmark_data[tabla_key]
                    
                    # Tomar hasta los primeros N competidores del mapping
                    max_competitors = min(len(tabla_original), len(mapping_competitors), 5)
                    
                    for i in range(max_competitors):
                        if i < len(tabla_original) and isinstance(tabla_original[i], dict):
                            # Reemplazar nombre pero mantener estructura de métricas
                            tabla_original[i]['nombre'] = mapping_competitors[i]
                            print(f"✅ [BENCHMARK-COHERENCE] Competidor {i+1} corregido: {mapping_competitors[i]}")
                    
                    # Si hay menos competidores en el mapping, truncar la tabla
                    if len(mapping_competitors) < len(tabla_original):
                        benchmark_data[tabla_key] = tabla_original[:len(mapping_competitors)]
                        print(f"📊 [BENCHMARK-COHERENCE] Tabla truncada a {len(mapping_competitors)} competidores")
                
                print(f"✅ [BENCHMARK-COHERENCE] Corrección automática aplicada usando competidores del mapping")
            
            elif coherence_ratio >= 0.5:
                print(f"✅ [BENCHMARK-COHERENCE] Coherencia aceptable ({coherence_ratio:.2f}), manteniendo benchmark actual")
            
            else:
                print(f"ℹ️ [BENCHMARK-COHERENCE] Coherencia baja pero pocos competidores en mapping, manteniendo benchmark")
            
            return benchmark_data
            
        except Exception as e:
            print(f"⚠️ [BENCHMARK-COHERENCE] Error en validación de coherencia: {str(e)}")
            return benchmark_data

    def _validate_benchmark_metrics(self, benchmark_data):
        """
        Valida y normaliza datos cuantitativos de benchmarking
        Convierte strings a números y asegura consistencia de datos
        """
        if not isinstance(benchmark_data, dict):
            return benchmark_data
        
        # Campos numéricos requeridos
        numeric_fields = [
            'ingresos_anuales_millones_eur',
            'empleados_total', 
            'años_en_mercado',
            'paises_presencia',
            'proyectos_anuales_estimados',
            'precio_promedio_proyecto_millones',
            'cuota_mercado_sector_porcentaje',
            'gasto_id_porcentaje_ingresos',
            'certificaciones_principales',
            'patentes_activas_estimadas'
        ]
        
        # 🔧 NOTA: La conversión 'tabla' → 'tabla_comparativa' ya se hizo antes de llamar esta función
        
        # 🚨 DETECTAR Y RECHAZAR DATOS PLACEHOLDER GENÉRICOS
        if 'tabla_comparativa' in benchmark_data and isinstance(benchmark_data['tabla_comparativa'], list):
            placeholders_detectados = []
            for i, comp in enumerate(benchmark_data['tabla_comparativa']):
                if isinstance(comp, dict):
                    nombre = comp.get('nombre', '').lower()
                    enfoque = comp.get('enfoque_estrategico', '').lower()
                    
                    # Detectar texto placeholder/genérico
                    placeholders = [
                        'análisis comparativo en desarrollo',
                        'requiere estudio específico',
                        'evaluación de modelos en proceso',
                        'análisis en desarrollo',
                        'pendiente de análisis',
                        'información en desarrollo',
                        'requiere investigación',
                        'datos en proceso',
                        'por determinar'
                    ]
                    
                    es_placeholder = any(placeholder in nombre or placeholder in enfoque for placeholder in placeholders)
                    
                    if es_placeholder:
                        placeholders_detectados.append(f"'{nombre}' (índice {i})")
            
            if placeholders_detectados:
                print(f"🚨 [BENCHMARK] DATOS PLACEHOLDER DETECTADOS: {', '.join(placeholders_detectados)}")
                print(f"🚨 [BENCHMARK] ¡EL LLM ESTÁ GENERANDO DATOS GENÉRICOS EN LUGAR DE EMPRESAS REALES!")
                # Limpiar datos placeholder
                benchmark_data['tabla_comparativa'] = [
                    comp for comp in benchmark_data['tabla_comparativa']
                    if not any(placeholder in comp.get('nombre', '').lower() or 
                             placeholder in comp.get('enfoque_estrategico', '').lower() 
                             for placeholder in placeholders)
                ]
                print(f"🧹 [BENCHMARK] Competidores válidos restantes: {len(benchmark_data['tabla_comparativa'])}")
                
                # Si no quedan competidores válidos, marcar como fallo
                if not benchmark_data['tabla_comparativa']:
                    print("❌ [BENCHMARK] NO HAY COMPETIDORES VÁLIDOS - LLM falló completamente")
                    return None
        
        # Validar tabla_comparativa
        if 'tabla_comparativa' in benchmark_data and isinstance(benchmark_data['tabla_comparativa'], list):
            for i, comp in enumerate(benchmark_data['tabla_comparativa']):
                if isinstance(comp, dict):
                    # Asegurar que existe el nombre
                    if not comp.get('nombre'):
                        comp['nombre'] = f"Competidor {i+1}"
                    
                    # Convertir campos numéricos
                    for field in numeric_fields:
                        if field in comp:
                            try:
                                # Manejar explícitamente N/D y valores faltantes
                                value = comp[field]
                                if isinstance(value, str):
                                    value_clean = value.strip()
                                    # Permitir N/D explícitamente
                                    if value_clean.upper() in ['N/D', 'N/A', 'DESCONOCIDO', 'NO DISPONIBLE']:
                                        comp[field] = 'N/D'
                                    else:
                                        # Intentar extraer número del texto
                                        import re
                                        numbers = re.findall(r'[\d.]+', value.replace(',', ''))
                                        if numbers:
                                            comp[field] = float(numbers[0])
                                        else:
                                            comp[field] = 'N/D'
                                else:
                                    comp[field] = float(value) if value else 'N/D'
                            except (ValueError, TypeError):
                                comp[field] = 'N/D'
                        else:
                            comp[field] = 'N/D'
        
        # Validar métricas comparativas
        if 'metricas_comparativas' in benchmark_data:
            metrics = benchmark_data['metricas_comparativas']
            for metric_key in ['lider_ingresos', 'lider_empleados', 'lider_cuota_mercado']:
                if metric_key in metrics and isinstance(metrics[metric_key], dict):
                    if 'valor' in metrics[metric_key]:
                        try:
                            value = metrics[metric_key]['valor']
                            if isinstance(value, str) and value.strip().upper() in ['N/D', 'N/A', 'DESCONOCIDO', 'NO DISPONIBLE']:
                                metrics[metric_key]['valor'] = 'N/D'
                            else:
                                metrics[metric_key]['valor'] = float(value)
                        except:
                            metrics[metric_key]['valor'] = 'N/D'
            
            # Promedios del sector
            for avg_key in ['promedio_sector_ingresos', 'promedio_sector_empleados']:
                if avg_key in metrics:
                    try:
                        value = metrics[avg_key]
                        if isinstance(value, str) and value.strip().upper() in ['N/D', 'N/A', 'DESCONOCIDO', 'NO DISPONIBLE']:
                            metrics[avg_key] = 'N/D'
                        else:
                            metrics[avg_key] = float(value)
                    except:
                        metrics[avg_key] = 'N/D'
        
        print(f"✅ [BENCHMARK] Datos métricos validados y normalizados")
        return benchmark_data

    def _validate_and_filter_competitors(self, data):
        """
        Valida y filtra automáticamente los datos de competidores para excluir a Sener
        y mejorar la calidad de los competidores identificados.
        """
        def should_exclude_competitor(company_name):
            """Determina si un competidor debe ser excluido"""
            if not company_name or not isinstance(company_name, str):
                return True
            
            name_lower = company_name.lower().strip()
            
            # Excluir Sener automáticamente
            if 'sener' in name_lower:
                return True
            
            # Excluir nombres muy genéricos o sospechosos
            generic_names = [
                'ejemplo', 'company', 'corporation', 'inc', 'ltd', 'limited',
                'business', 'enterprise', 'group', 'holdings', 'unknown'
            ]
            
            if any(generic in name_lower for generic in generic_names):
                return True
                
            # Excluir nombres muy cortos (probablemente incompletos)
            if len(name_lower) < 3:
                return True
                
            return False
        
        def clean_competitor_list(competitors_list):
            """Limpia una lista de competidores"""
            if not isinstance(competitors_list, list):
                return []
            
            cleaned = []
            for comp in competitors_list:
                if isinstance(comp, dict):
                    name_fields = ['nombre', 'empresa', 'name', 'company']
                    company_name = None
                    
                    for field in name_fields:
                        if field in comp and comp[field]:
                            company_name = comp[field]
                            break
                    
                    if not should_exclude_competitor(company_name):
                        cleaned.append(comp)
                        
                elif isinstance(comp, str):
                    if not should_exclude_competitor(comp):
                        cleaned.append(comp)
            
            return cleaned
        
        if isinstance(data, dict):
            # Filtrar competidores directos
            if 'competidores_directos' in data:
                data['competidores_directos'] = clean_competitor_list(data['competidores_directos'])
            
            # Filtrar competidores indirectos
            if 'competidores_indirectos' in data:
                data['competidores_indirectos'] = clean_competitor_list(data['competidores_indirectos'])
            
            # Filtrar emergentes
            if 'emergentes' in data:
                data['emergentes'] = clean_competitor_list(data['emergentes'])
        
        return data

    def _extract_section_data_llm(self, section_id, shared_inputs, report_dict=None):
        """
        Llama al LLM para extraer SOLO datos objetivos y estructurados para la sección, con máxima exigencia consultiva.
        ✅ MEJORADO: Búsqueda real de patentes para TECH_IP_LANDSCAPE
        ✅ NUEVO: Lógica especial para BENCHMARK_MATRIX usando competidores de COMPETITOR_MAPPING
        """
        import json
        
        # ✅ INICIALIZAR: prompt específico para BENCHMARK_MATRIX
        specific_benchmark_prompt = None
        
        # ✅ NUEVA LÓGICA: Manejar BENCHMARK_MATRIX de forma especial
        print(f"🚨🚨🚨 [DEBUG-SECTION] section_id recibido: '{section_id}' (tipo: {type(section_id)})")
        print(f"🚨🚨🚨 [DEBUG-SECTION] ¿Es BENCHMARK_MATRIX?: {section_id == 'BENCHMARK_MATRIX'}")
        print(f"🚨🚨🚨 [DEBUG-SECTION] ¿Contiene BENCHMARK?: {'BENCHMARK' in str(section_id)}")
        
        if section_id == "BENCHMARK_MATRIX":
            print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] === INICIANDO BENCHMARK_MATRIX ESPECIAL ===")
            print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] report_dict keys: {list(report_dict.keys()) if report_dict else 'None'}")
            print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] report_dict es None?: {report_dict is None}")
            print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Tipo de report_dict: {type(report_dict)}")
            
            if report_dict and 'COMPETITOR_MAPPING' in report_dict:
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] COMPETITOR_MAPPING encontrado! Tipo: {type(report_dict['COMPETITOR_MAPPING'])}")
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Contenido COMPETITOR_MAPPING: {str(report_dict['COMPETITOR_MAPPING'])[:300]}...")
            else:
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] COMPETITOR_MAPPING NO ENCONTRADO!")
                if report_dict:
                    print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Keys disponibles: {list(report_dict.keys())}")
            
            competitors_list = self._extract_competitors_from_mapping(report_dict or {})
            print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Competitors extraídos: {len(competitors_list)}")
            
            if competitors_list:
                print(f"🔄 [BENCHMARK] Generando análisis cuantitativo para {len(competitors_list)} competidores específicos")
                for i, comp in enumerate(competitors_list):
                    print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Competidor {i+1}: {comp.get('nombre', 'SIN_NOMBRE')}")
                
                specific_benchmark_prompt = self._generate_benchmark_prompt_with_competitors(competitors_list, shared_inputs)
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Prompt específico generado: {len(specific_benchmark_prompt)} caracteres")
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] === PROMPT FINAL PARA LLM ===")
                print(f"🚨🚨🚨 [BENCHMARK-EXTRACT] Primeros 200 chars: {specific_benchmark_prompt[:200]}...")
                
                # Verificar si contiene competidores específicos
                competitor_names = [comp.get('nombre', '') for comp in competitors_list if comp.get('nombre')]
                found_competitors = [name for name in competitor_names if name in specific_benchmark_prompt]
                
                if found_competitors or 'Blue Ocean' in specific_benchmark_prompt:
                    print(f"✅✅✅ [BENCHMARK-EXTRACT] PROMPT CONTIENE COMPETIDORES: {found_competitors}")
                else:
                    print(f"❌❌❌ [BENCHMARK-EXTRACT] PROMPT NO CONTIENE COMPETIDORES DE: {competitor_names}")
                    print(f"❌❌❌ [BENCHMARK-EXTRACT] Contenido del prompt: {specific_benchmark_prompt[-500:]}")  # Últimos 500 chars
            else:
                print(f"⚠️⚠️⚠️ [BENCHMARK-EXTRACT] No hay competidores disponibles, usando prompt genérico")
        
        schema = SECTION_SCHEMAS.get(section_id, '{}')
        other_context = shared_inputs.get('contexto_usuario', '')
        if report_dict:
            context_parts = []
            for k, v in report_dict.items():
                if k != section_id and isinstance(v, dict):
                    context_parts.append(f"[{k}]: {json.dumps(v, ensure_ascii=False)[:400]}")
            if context_parts:
                other_context += "\n\n" + "\n".join(context_parts)
        
        # 🚫 ELIMINADA: Búsqueda externa de patentes (no funciona bien)
        # Nuevo enfoque: Solo análisis basado en conocimiento específico del LLM
        real_patents_context = ""
        
        extraction_instructions = {
            "EXEC_SUMMARY": "No extraigas datos, solo redacta al final.",
            "COMPETITOR_MAPPING": (
                "Identifica competidores REALES del sector específico de la idea analizada. "
                "CRÍTICO: NO uses listas predefinidas de empresas - analiza el sector específico de cada idea. "
                "Devuelve JSON con 3 categorías: competidores_directos (mismo mercado y solución), "
                "competidores_indirectos (mercado relacionado), emergentes (startups y nuevos entrantes). "
                
                "CAMPOS OBLIGATORIOS para cada competidor: "
                "- nombre: Nombre oficial de la empresa "
                "- pais: País donde tiene su sede principal "
                "- sector: Sector específico (ej: 'Infraestructura', 'Energía renovable', 'Aeroespacial', 'Construcción', 'Tecnología') "
                "- tamano: Tamaño de la empresa ('Pequeña', 'Mediana', 'Grande', 'Multinacional') "
                "- descripcion: Breve descripción de qué hace la empresa "
                "- website: URL si disponible "
                
                "FORMATO JSON POR COMPETIDOR: "
                "{\"nombre\":\"Empresa Real\", \"pais\":\"País\", \"sector\":\"Sector específico\", "
                "\"tamano\":\"Tamaño real\", \"descripcion\":\"Qué hace\", \"website\":\"URL\"} "
                
                "CRITERIOS DE TAMAÑO (usar información real): "
                "- 'Pequeña': <100 empleados, local/regional "
                "- 'Mediana': 100-1000 empleados, nacional "
                "- 'Grande': >1000 empleados, multinacional "
                "- 'Multinacional': >5000 empleados, presencia global "
                
                "MÁXIMO 3-4 empresas por categoría. "
                "SOLO empresas REALES verificables - NO inventar nombres ni usar ejemplos genéricos. "
                "PROHIBIDO: incluir Sener como competidor (es quien hace el análisis). "
                "Enfócate en empresas que realmente operan en el sector específico de la idea analizada."
            ),
            "BENCHMARK_MATRIX": (
                "Genera tabla comparativa CUANTITATIVA usando los MISMOS competidores identificados en COMPETITOR_MAPPING. "
                "CRÍTICO: Reutiliza EXACTAMENTE las empresas listadas en las 3 categorías de COMPETITOR_MAPPING (directos, indirectos, emergentes). "
                "NUNCA incluyas a Sener - Sener es quien hace el análisis, NO un competidor. "
                "ENFOQUE: SOLO métricas numéricas y cifras específicas, NO texto descriptivo largo. "
                
                "ESTRUCTURA JSON REQUERIDA: "
                "- 'tabla_comparativa': lista de competidores con métricas cuantitativas "
                "- 'metricas_comparativas': rankings y estadísticas del sector "
                "- 'gaps_cuantitativos': brechas identificadas con datos numéricos "
                
                "CAMPOS OBLIGATORIOS por competidor en 'tabla_comparativa' (SOLO NÚMEROS): "
                "- nombre: Nombre de la empresa (EXACTAMENTE igual que en COMPETITOR_MAPPING) "
                "- ingresos_anuales_millones_eur: Facturación anual en millones EUR (estimar basándose en tamaño) "
                "- empleados_total: Número total de empleados (aproximación realista) "
                "- años_en_mercado: Años operando en el sector específico "
                "- paises_presencia: Número de países donde tiene operaciones "
                "- proyectos_anuales_estimados: Grandes proyectos ejecutados por año "
                "- precio_promedio_proyecto_millones: Valor promedio de proyectos en millones EUR "
                "- cuota_mercado_sector_porcentaje: Porcentaje estimado de cuota en el sector específico "
                "- gasto_id_porcentaje_ingresos: Porcentaje de ingresos destinado a I+D+i "
                "- certificaciones_principales: Número de certificaciones ISO/técnicas relevantes "
                "- patentes_activas_estimadas: Número aproximado de patentes activas en el sector "
                
                "GUÍAS DE ESTIMACIÓN INTELIGENTE ( SOLO Y EXCLUSIVEMNETE si no conoces datos exactos): "
                
                "Para empresas categorizadas como 'Pequeña': "
                "- ingresos_anuales_millones_eur: 10-80 (estimar según sector) "
                "- empleados_total: 50-300 "
                "- años_en_mercado: 5-20 "
                "- paises_presencia: 1-3 "
                "- cuota_mercado_sector_porcentaje: 0.5-3 "
                
                "Para empresas categorizadas como 'Mediana': "
                "- ingresos_anuales_millones_eur: 80-800 "
                "- empleados_total: 300-3000 "
                "- años_en_mercado: 15-40 "
                "- paises_presencia: 3-15 "
                "- cuota_mercado_sector_porcentaje: 3-12 "
                
                "Para empresas categorizadas como 'Grande': "
                "- ingresos_anuales_millones_eur: 800-8000 "
                "- empleados_total: 3000-50000 "
                "- años_en_mercado: 25-80 "
                "- paises_presencia: 10-50 "
                "- cuota_mercado_sector_porcentaje: 8-25 "
                
                "Para empresas categorizadas como 'Multinacional': "
                "- ingresos_anuales_millones_eur: 5000-150000 "
                "- empleados_total: 20000-400000 "
                "- años_en_mercado: 30-150 "
                "- paises_presencia: 25-100 "
                "- cuota_mercado_sector_porcentaje: 15-40 "
                
                "ESTRUCTURA 'metricas_comparativas' OBLIGATORIA: "
                "- lider_ingresos: {empresa: nombre, valor: cifra} "
                "- lider_empleados: {empresa: nombre, valor: cifra} "
                "- lider_cuota_mercado: {empresa: nombre, valor: cifra} "
                "- promedio_sector_ingresos: cifra promedio "
                "- promedio_sector_empleados: cifra promedio "
                
                "ESTRUCTURA 'gaps_cuantitativos' (2-4 elementos): "
                "- metrica: Nombre específico de la métrica (ej: 'Inversión I+D', 'Presencia internacional') "
                "- brecha_identificada: Descripción cuantitativa del gap (ej: 'Promedio sector 3.2%, líder 8.1%') "
                "- oportunidad_sener: Ventaja numérica específica para Sener (ej: 'Incrementar I+D al 5% puede captar 15% más proyectos') "
                
                "PRINCIPIOS DE ESTIMACIÓN INTELIGENTE: "
                "1. DATOS CONOCIDOS: Si tienes conocimiento real de una empresa, úsalo "
                "2. ESTIMACIÓN CONTEXTUAL: Para empresas que no conoces, estima basándote en el tamaño/sector "
                "3. HONESTIDAD: Si no tienes datos confiables, usar 'N/D' es OBLIGATORIO "
                
                "CATEGORÍAS DE ESTIMACIÓN POR TAMAÑO: "
                "- Multinacional Grande (Siemens, GE): ingresos 30000-80000M€, empleados 200000-400000 "
                "- Empresa Grande (10000+ empleados): ingresos 5000-30000M€, empleados 10000-50000 "
                "- Empresa Mediana (1000-10000 empleados): ingresos 500-5000M€, empleados 1000-10000 "
                "- Empresa Pequeña (<1000 empleados): ingresos 10-500M€, empleados 50-1000 "
                
                "VALORES REQUERIDOS CUANDO NO HAY DATOS CONFIABLES: "
                "- ingresos_anuales_millones_eur: 'N/D' "
                "- empleados_total: 'N/D' "
                "- cuota_mercado_sector_porcentaje: 'N/D' "
                "- gasto_id_porcentaje_ingresos: 'N/D' "
                "- patentes_activas_estimadas: 'N/D' "
                
                "PROHIBICIONES CRÍTICAS: "
                "- NO inventar empresas que no estén en COMPETITOR_MAPPING "
                "- NO inventar números específicos sin base factual sólida "
                "- NO usar rangos (ej: '100-200') - usar número específico O 'N/D' "
                "- NO incluir Sener o variaciones de Sener "
                "- SÍ usar 'N/D' cuando no tengas datos confiables - ES OBLIGATORIO "
                "- 🚫 PROHIBIDO usar textos como: 'Análisis comparativo en desarrollo', 'Requiere estudio específico', 'Evaluación de modelos en proceso' "
                "- 🚫 PROHIBIDO usar nombres de empresa placeholder o genéricos - SOLO empresas reales de COMPETITOR_MAPPING "
                
                "RESPONDE SIEMPRE EN ESPAÑOL CON JSON VÁLIDO. USA NÚMEROS ESPECÍFICOS SOLO SI TIENES DATOS CONFIABLES, SI NO USA 'N/D'."
            ),
            "TECH_IP_LANDSCAPE": (
                "ENFOQUE MEJORADO: Analiza SOLO áreas tecnológicas específicas de la idea, NO generes contenido genérico. "
                "Si no tienes información específica de patentes, enfócate en GAPS y TENDENCIAS basadas en la idea. "
                
                "PRIORIDADES: "
                "1. Identifica GAPS tecnológicos específicos que la idea podría resolver "
                "2. Analiza TENDENCIAS emergentes relevantes para la idea específica "
                "3. SOLO incluye patentes si tienes información específica y relevante "
                "4. NO uses frases genéricas como 'tecnologías del sector' o 'investigación relevante' "
                
                "ESTRUCTURA JSON REQUERIDA: "
                
                "1. PATENTES_DESTACADAS (2-4): ANÁLISIS TÉCNICO PROFUNDO - usar conocimiento específico "
                "BUSCAR EN TU CONOCIMIENTO: patentes de empresas como IBM, Google, Microsoft, Samsung, Siemens, "
                "General Electric, Philips, Sony, etc. relacionadas con la tecnología específica de la idea. "
                ""
                "Si CONOCES patentes específicas: "
                "- titulo: Título técnico exacto de la patente conocida "
                "- numero_patente: Número real de patente (US, EP, WO, etc.) "
                "- titular: Empresa titular específica conocida "
                "- año: Año de presentación/concesión conocido "
                "- descripcion: Descripción técnica detallada de la invención "
                "- relevancia_competitiva: Análisis específico de cómo afecta a la idea "
                ""
                "Si NO CONOCES patentes específicas: "
                "- titulo: 'BÚSQUEDA ULTRASONIDO: Sistemas anti-biofouling Panasonic/Siemens 40-80 kHz patentes 2018-2024' "
                "- numero_patente: 'GOOGLE PATENTS: keywords ultrasonic biofouling prevention marine surfaces' "
                "- titular: 'EMPRESAS OBJETIVO: Panasonic Corp, Siemens AG, General Electric, Bosch Sensortec' "
                "- descripcion: 'ANÁLISIS IP: Transductores piezoeléctricos, frecuencias anti-fouling, sistemas bajo consumo' "
                "- relevancia_competitiva: 'CRÍTICA - Libertad operación en ultrasonido 40-80 kHz para aplicaciones marinas' "
                
                "2. PUBLICACIONES_CLAVE (2-4): LITERATURA CIENTÍFICA ESPECÍFICA CON MÁXIMO DETALLE TÉCNICO "
                "🔬 BUSCAR EN TU CONOCIMIENTO PUBLICACIONES REALES: "
                "- Papers específicos de Nature, Science, Nature Materials, Science Advances "
                "- IEEE Transactions específicos del área (IEEE Trans Ultrasonics, IEEE Trans Marine Tech, etc.) "
                "- Autores RECONOCIDOS específicos (ej: Joseph Paradiso del MIT, Daniel Rus del MIT, etc.) "
                "- DOIs específicos si los conoces "
                ""
                "✅ SI CONOCES PUBLICACIONES ESPECÍFICAS REALES (PREFERIDO): "
                "- titulo: '[Título exacto del paper que conoces]' "
                "- autores: '[Nombres reales de autores que conoces]' "
                "- revista: '[Revista específica: Nature Materials, Science, IEEE Trans X, etc.]' "
                "- año: '[Año exacto que conoces]' "
                "- doi: '[DOI específico si lo conoces]' "
                "- resumen: '[Resumen técnico de hallazgos específicos que conoces]' "
                "- relevancia_tecnologica: '[Impacto específico conocido]' "
                "- url: '[URL del DOI o paper si la conoces]' "
                ""
                "🔍 SI NO CONOCES PUBLICACIONES ESPECÍFICAS (MÁS PROBABLE): "
                "⚠️ IMPORTANTE: SER MUY ESPECÍFICO EN BÚSQUEDAS REQUERIDAS: "
                ""
                "EJEMPLO 1 - Literatura sobre frecuencias ultrasónicas: "
                "- titulo: 'REVISIÓN LITERATURA REQUERIDA: Optimización frecuencias ultrasónicas 20-80 kHz para control biofouling marino' "
                "- autores: 'INVESTIGACIÓN NECESARIA: Prof. Joseph Paradiso (MIT Media Lab), equipos de Marine Acoustics Lab MIT, Stanford Ocean Engineering Dept' "
                "- revista: 'BÚSQUEDA OBLIGATORIA: Nature Materials vol 2019-2024, IEEE Transactions on Ultrasonics vol 2020-2024, Applied Physics Letters últimos números' "
                "- año: 'PERÍODO CRÍTICO: 2019-2024 (últimos 5 años de avances)' "
                "- resumen: 'ESTADO ARTE REQUERIDO: Métodos de calibración frecuencia 40-80 kHz, eficacia contra Pseudomonas aeruginosa, consumo energético < 10W/m², durabilidad transductores piezoeléctricos' "
                "- relevancia_tecnologica: 'CRÍTICA - Validación científica parámetros para diseño sistema SENER ultrasonido anti-fouling' "
                "- url: 'https://doi.org/ [búsqueda requerida en literatura especializada]' "
                ""
                "EJEMPLO 2 - Literatura sobre materiales avanzados: "
                "- titulo: 'CONSULTA BIBLIOGRÁFICA ESPECIALIZADA: Materiales piezoeléctricos para transductores marinos alta eficiencia' "
                "- autores: 'EXPERTOS A CONSULTAR: Prof. Yet-Ming Chiang (MIT Materials), investigadores ETH Zurich Soft Robotics Lab, Delft University Marine Technology' "
                "- revista: 'JOURNALS OBJETIVO: Nature Materials, Advanced Materials, Journal of Marine Science and Engineering, IEEE Trans Marine Technology' "
                "- año: 'PUBLICACIONES RECIENTES: 2020-2024' "
                "- resumen: 'CONOCIMIENTO REQUERIDO: Cerámicas piezoeléctricas PZT modificadas, polímeros conductores flexibles, degradación por agua salada, temperatura operativa -20°C a +60°C' "
                "- relevancia_tecnologica: 'ALTA - Selección materiales para durabilidad 20+ años en ambiente marino' "
                "- url: 'https://doi.org/ [identificar DOIs específicos en búsqueda dirigida]' "
                ""
                "🚨 REQUISITOS DE ESPECIFICIDAD OBLIGATORIOS: "
                "1. FRECUENCIAS ESPECÍFICAS: Siempre mencionar rangos exactos (ej: 40-80 kHz, no 'frecuencias apropiadas') "
                "2. ORGANISMOS ESPECÍFICOS: Usar nombres completos (Pseudomonas aeruginosa, no 'microorganismos marinos') "
                "3. UNIVERSIDADES ESPECÍFICAS: Nombrar labs exactos (MIT Media Lab, no 'centros de investigación') "
                "4. REVISTAS ESPECÍFICAS: Títulos completos (IEEE Trans Ultrasonics, no 'revistas especializadas') "
                "5. PERÍODOS ESPECÍFICOS: Años exactos (2019-2024, no 'período reciente') "
                "6. PARÁMETROS TÉCNICOS: Valores cuantificados (< 10W/m², 20+ años, no 'bajo consumo', 'larga duración') "
                
                "3. GAPS_TECNOLOGICOS (2-4): ANÁLISIS TÉCNICO ESPECÍFICO de limitaciones actuales "
                "- area_tecnologica: Área técnica específica con nomenclatura precisa "
                "- descripcion_gap: Descripción técnica detallada del vacío o limitación "
                "- impacto_competitivo: Análisis específico de cómo afecta a competidores "
                "- oportunidad_sener: Ventaja competitiva específica y cuantificable para SENER "
                "- barreras_tecnicas: Barreras técnicas específicas que existen actualmente "
                
                "4. TENDENCIAS_EMERGENTES (2-3): Tendencias tecnológicas con impacto específico "
                "- tecnologia: Tecnología emergente con descripción técnica específica "
                "- estado_madurez: TRL (Technology Readiness Level) específico o estado detallado "
                "- potencial_disruptivo: Análisis cuantitativo del potencial disruptivo "
                "- plazo_adopcion: Timeframe específico con justificación técnica "
                "- empresas_lideres: Empresas específicas que lideran esta tendencia "
                
                "EJEMPLOS ESPECÍFICOS vs BÚSQUEDA REQUERIDA: "
                
                "EJEMPLOS DE ANÁLISIS TÉCNICO PROFUNDO: "
                
                "🚨 EJEMPLOS DE FORMATO CORRECTO (SIN INVENTAR DATOS): "
                
                "SI CONOCES PATENTE REAL (poco probable): "
                "titulo: '[Título real de patente que conozcas]' "
                "numero_patente: '[Número real que conozcas]' "
                "titular: '[Empresa real]' "
                
                "SI NO CONOCES PATENTE REAL (más probable - LO NORMAL): "
                "titulo: 'Se requiere búsqueda específica en tecnologías ultrasónicas para prevención de biofouling' "
                "numero_patente: 'BÚSQUEDA REQUERIDA: Google Patents con keywords ultrasonic+biofouling+prevention' "
                "titular: 'INVESTIGACIÓN NECESARIA: Panasonic Corp, Siemens AG, General Electric, Samsung Electronics' "
                "año: 'PERÍODO BÚSQUEDA: 2018-2024' "
                "descripcion: 'TECNOLOGÍAS A BUSCAR: Transductores piezoeléctricos, frecuencias 20-80 kHz, aplicaciones marinas' "
                
                "SI CONOCES PUBLICACIÓN REAL (poco probable): "
                "titulo: '[Título real de artículo que conozcas]' "
                "autores: '[Autores reales]' "
                "revista: '[Journal real]' "
                
                "SI NO CONOCES PUBLICACIÓN REAL (más probable - LO NORMAL): "
                "titulo: 'Se requiere revisión bibliográfica en ultrasonido y control de biofouling marino' "
                "autores: 'Investigación necesaria en universidades: MIT, Stanford, ETH Zurich, Delft University' "
                "revista: 'Búsqueda en journals: Nature Materials, Science, IEEE Transactions on Ultrasonics' "
                
                "🚨 REGLAS ANTI-GENÉRICO - CONTENIDO ESPECÍFICO OBLIGATORIO 🚨 "
                ""
                "🚨 PROHIBICIONES CRÍTICAS - CAUSA RECHAZO AUTOMÁTICO: "
                ""
                "❌ NUNCA INVENTAR NÚMEROS DE PATENTE: "
                "- NO generes números como 'US20190234567A1', 'EP3456789A1', 'US10123456B2' "
                "- Si no conoces el número real, usa: 'BÚSQUEDA REQUERIDA: Google Patents + keywords específicos' "
                "- SIEMPRE usa indicaciones de búsqueda en lugar de números inventados "
                ""
                "❌ FRASES GENÉRICAS PROHIBIDAS: "
                "- 'área tecnológica específica' → Especifica: 'sistemas ultrasónicos anti-biofouling' "
                "- 'bases de datos especializadas' → Especifica: 'Google Patents, USPTO.gov, EPO.org' "
                "- 'empresas del sector' → Especifica: 'Panasonic Corp, Siemens AG, Bosch Sensortec' "
                "- 'universidades del área' → Especifica: 'MIT Marine Lab, Stanford Ocean Engineering' "
                "- 'investigadores por identificar' → Especifica: 'Research teams at ETH Zurich Bio-interfaces' "
                ""
                "✅ CONTENIDO OBLIGATORIO: "
                "1. PATENTES: SI NO conoces números reales, di 'Búsqueda requerida en Google Patents para [empresa específica]' "
                "2. REVISTAS: Nature Materials, Science Advances, IEEE Trans Marine Technology (NO 'revistas especializadas') "
                "3. EMPRESAS: Nombrar específicamente Panasonic, Siemens, General Electric, IBM, etc. "
                "4. UNIVERSIDADES: MIT, Stanford, ETH, Delft (NO 'centros de investigación del área') "
                "5. FECHAS: 2019-2024, últimos 5 años (NO 'período reciente') "
                "6. FRECUENCIAS: 40-80 kHz específicos (NO 'rangos apropiados') "
                
                "FORMATO: JSON válido sin texto adicional. "
                "OBJETIVO: Máximo contenido técnico específico O búsqueda transparente bien dirigida. "
                "PROHIBIDO: Contenido genérico, vago, o datos inventados. "
                "RESPONDE SIEMPRE EN ESPAÑOL."
            ),
            "MARKET_ANALYSIS": (
                "Extrae datos estructurados del mercado Y genera gaps y oportunidades específicas. "
                "Devuelve JSON con la estructura exacta del schema proporcionado. "
                
                "CAMPOS OBLIGATORIOS DEL JSON: "
                "- TAM_2025: Tamaño del mercado en dólares/euros (número) "
                "- CAGR_2025_2030: Tasa de crecimiento anual compuesta (número decimal) "
                "- segmentos: Lista de segmentos de mercado específicos "
                "- geografias: Lista de regiones/países objetivo "
                "- drivers: Lista de factores que impulsan el crecimiento "
                "- restrictores: Lista de barreras o limitaciones del mercado "
                
                "ANÁLISIS CUALITATIVO (CRÍTICO): "
                "- gaps_identificados: Lista de 3-4 vacíos específicos del mercado actual "
                "- oportunidades_sener: Lista de 3-4 oportunidades específicas para Sener "
                
                "EJEMPLO FORMATO gaps_identificados: "
                "[\"Falta de soluciones modulares en hospitales urbanos\", \"Limitada integración tecnológica en infraestructuras\"] "
                
                "EJEMPLO FORMATO oportunidades_sener: "
                "[\"Liderar mercado de hospitales modulares verticales\", \"Aprovechar experiencia en ingeniería para infraestructura sanitaria\"] "
                
                "CRITERIOS: "
                "- Los gaps deben ser necesidades NO cubiertas por competidores actuales "
                "- Las oportunidades deben conectar con capacidades de Sener en ingeniería "
                "- Ser específicos y accionables, no genéricos "
                
                "FORMATO: JSON válido sin texto adicional. "
                "ENFOQUE: Datos específicos del sector de la idea analizada. "
                "RESPONDE SIEMPRE EN ESPAÑOL."
            ),
            "SWOT_POSITIONING": (
                "Realiza un análisis DAFO específico para la idea analizada en el contexto del mercado y competidores identificados. "
                "Devuelve JSON válido con la estructura exacta especificada. "
                
                "ESTRUCTURA OBLIGATORIA: "
                "{\"swot\":{\"fortalezas\":[\"item1\",\"item2\",\"item3\"],\"debilidades\":[\"item1\",\"item2\",\"item3\"],\"oportunidades\":[\"item1\",\"item2\",\"item3\"],\"amenazas\":[\"item1\",\"item2\",\"item3\"]},"
                "\"mapa_posicionamiento\":{\"eje_x\":\"descripción del eje X\",\"eje_y\":\"descripción del eje Y\",\"comentario\":\"posicionamiento de la idea\"}} "
                
                "ANÁLISIS DAFO ESPECÍFICO: "
                
                "1. FORTALEZAS (3-4 elementos): "
                "- Capacidades de Sener que encajan con la idea analizada "
                "- Ventajas técnicas o de mercado específicas para esta idea "
                "- Recursos y experiencia aplicables al sector identificado "
                "- Diferenciadores competitivos únicos para esta oportunidad "
                
                "2. DEBILIDADES (3-4 elementos): "
                "- Limitaciones específicas para desarrollar esta idea "
                "- Gaps de capacidades o recursos para el sector analizado "
                "- Aspectos donde los competidores identificados tienen ventaja "
                "- Barreras internas para implementar esta solución "
                
                "3. OPORTUNIDADES (3-4 elementos): "
                "- Tendencias del mercado que favorecen esta idea específica "
                "- Gaps de mercado identificados que la idea puede cubrir "
                "- Sinergias con otros proyectos o líneas de negocio de Sener "
                "- Oportunidades regulatorias o tecnológicas del sector "
                
                "4. AMENAZAS (3-4 elementos): "
                "- Competidores específicos que podrían adelantarse "
                "- Riesgos del sector o mercado identificado "
                "- Barreras regulatorias o tecnológicas "
                "- Factores que podrían hacer la idea menos viable "
                
                "MAPA DE POSICIONAMIENTO: "
                "- eje_x: Dimensión competitiva relevante (ej: 'Especialización técnica', 'Cobertura geográfica') "
                "- eje_y: Segunda dimensión estratégica (ej: 'Tamaño de mercado', 'Grado de innovación') "
                "- comentario: Posición de la idea en este mapa competitivo específico "
                
                "CRITERIOS DE CALIDAD: "
                "- Cada elemento debe ser específico y relacionado con la idea analizada "
                "- Conectar con los competidores y mercado ya identificados "
                "- Evitar elementos genéricos, ser concreto y accionable "
                "- Si hay información limitada, inferir basándose en el sector y competidores "
                
                "FORMATO: JSON válido sin texto adicional. "
                "OBLIGATORIO: Siempre incluir exactamente 3-4 elementos por categoría DAFO. "
                "RESPONDE SIEMPRE EN ESPAÑOL."
            ),
            "REGULATORY_ESG_RISK": (
                "Extrae SOLO datos reales sobre normativas, certificaciones, riesgos regulatorios y oportunidades ESG. "
                "🚨 PROHIBIDO INVENTAR: números de normativas, códigos de certificación, URLs de reguladores "
                "✅ OBLIGATORIO USAR REALES: ISO 9001, ISO 14001, REACH, RoHS, FDA, CE, UL, IEC "
                "✅ ORGANISMOS REALES: Comisión Europea, EPA, OSHA, FDA, BSI, TÜV, DNV, Lloyd's "
                "✅ Si NO conoces específico: 'Se requiere consulta en [organismo específico] para [área]' "
                "FORMATO: JSON válido. Incluye fuente URL real si conoces. No redactes, solo datos."
            ),
            "STRATEGIC_ROADMAP": (
                "Extrae SOLO acciones concretas a 90 días, 12 meses, 36 meses, y KPIs clave. "
                "Incluye responsables, fechas, y si el KPI es medible. No redactes, solo datos."
            ),
            "APPENDIX": (
                "Extrae SOLO glosario de términos, metodología y limitaciones. "
                "El glosario debe definir términos técnicos o de negocio usados en el informe. "
                "La metodología debe explicar brevemente el enfoque seguido. "
                "Las limitaciones deben ser honestas y profesionales. No redactes, solo datos."
            )
        }
        
        # ✅ CRITICAL FIX: Usar prompt específico si está disponible (para BENCHMARK_MATRIX)
        if section_id == "BENCHMARK_MATRIX" and specific_benchmark_prompt:
            # Usar el prompt específico generado con competidores
            instruction = specific_benchmark_prompt
            print(f"✅ [BENCHMARK] Usando prompt específico con competidores ({len(specific_benchmark_prompt)} chars)")
        else:
            # Usar instrucciones normales para otras secciones
            instruction = extraction_instructions.get(section_id, "Extrae SOLO datos estructurados según el esquema. No redactes.")
            if section_id == "BENCHMARK_MATRIX":
                print(f"⚠️ [BENCHMARK] Usando prompt genérico (no hay competidores específicos)")
        
        # Añadir contexto de patentes reales si está disponible
        full_instruction = instruction + real_patents_context
        
        # 🆕 NUEVO: PRE-FILTRO INTELIGENTE DE FUENTES ADICIONALES
        relevant_sources = ""
        extra_sources = shared_inputs.get('extra_sources', '')
        
        if section_id == "BENCHMARK_MATRIX":
            print(f"🔍🔍🔍 [INTEGRACIÓN] ===== BENCHMARK_MATRIX EXCLUIDO DEL FILTRO DE FUENTES =====")
            print(f"🔍🔍🔍 [INTEGRACIÓN] Razón: BENCHMARK_MATRIX se nutre completamente del COMPETITOR_MAPPING")
            print(f"🔍🔍🔍 [INTEGRACIÓN] Las fuentes ya influyeron en COMPETITOR_MAPPING → transferencia automática")
        elif extra_sources and extra_sources.strip():
            print(f"🔍🔍🔍 [INTEGRACIÓN] ===== INTEGRANDO FUENTES EN {section_id} =====")
            print(f"🔍🔍🔍 [INTEGRACIÓN] extra_sources desde shared_inputs: '{extra_sources}'")
            
            idea_brief = shared_inputs.get('idea_brief', '')
            print(f"🔍🔍🔍 [INTEGRACIÓN] idea_brief: '{idea_brief[:100]}...'")
            
            print(f"🔍🔍🔍 [INTEGRACIÓN] 🚀 LLAMANDO A get_relevant_sources_for_section...")
            relevant_sources = self.get_relevant_sources_for_section(section_id, extra_sources, idea_brief)
            
            print(f"🔍🔍🔍 [INTEGRACIÓN] 📥 RESULTADO PRE-FILTRO: '{relevant_sources}'")
            
            if relevant_sources:
                print(f"🔍🔍🔍 [INTEGRACIÓN] ✅ FUENTES RELEVANTES ENCONTRADAS - se usarán en prompt optimizado")
            else:
                print(f"🔍🔍🔍 [INTEGRACIÓN] ❌ NO HAY FUENTES RELEVANTES - continuando sin fuentes adicionales")
        else:
            print(f"🔍🔍🔍 [INTEGRACIÓN] ℹ️ NO HAY extra_sources en shared_inputs para {section_id}")
        
        # 🔥 FORZAR PROMPT ESPECÍFICO PARA BENCHMARK_MATRIX 🔥
        if section_id == "BENCHMARK_MATRIX" and specific_benchmark_prompt:
            print(f"🔥 [BENCHMARK-FORCE] USANDO PROMPT ESPECÍFICO COMPLETO EN LUGAR DEL GENÉRICO")
            prompt = specific_benchmark_prompt
            # Añadir esquema al final del prompt específico
            prompt += f"\n\n== ESQUEMA JSON OBLIGATORIO ==\n{schema}\n== FIN ESQUEMA ==\n\nRESPUESTA: JSON válido sin texto adicional."
        else:
            # 🆕 PROMPT OPTIMIZADO PARA FUENTES ADICIONALES
            if relevant_sources and section_id != "BENCHMARK_MATRIX":
                print(f"🔧 [PROMPT-OPTIMIZED] Usando prompt optimizado para fuentes adicionales en {section_id}")
                prompt = f"""ANÁLISIS COMPETITIVO - {section_id}

🚨 FUENTES PRE-APROBADAS POR FILTRO INTELIGENTE: {relevant_sources}

💡 IDEA: {shared_inputs.get('idea_brief', '')}
🎯 SECTOR: {', '.join(shared_inputs.get('sector_keywords', []))}

📋 TAREA: Analiza la sección {section_id} para la idea.

🔥 INSTRUCCIONES OBLIGATORIAS (EL FILTRO YA DETERMINÓ QUE SON RELEVANTES):
1. **DEBES CONSULTAR Y MENCIONAR** cada fuente de esta lista: {relevant_sources}
2. **PARA CADA FUENTE** incluye al menos una referencia específica usando:
   - "Según [NOMBRE_FUENTE]..."
   - "Datos de [NOMBRE_FUENTE] indican..."
   - "[NOMBRE_FUENTE] establece que..."
3. **SI UNA FUENTE** no aporta datos específicos directos, EXPLICA qué tipo de información se esperaría encontrar en ella para esta sección
4. **PROHIBIDO**: Ignorar las fuentes que ya fueron validadas como relevantes por el filtro inteligente

📚 SECCIÓN OBLIGATORIA AL FINAL: "📚 Referencias Consultadas:" con:
- Lista de fuentes mencionadas en el análisis
- URL oficial de cada fuente consultada (si la conoces)
- Breve descripción de qué información aportó cada una

⚠️ RECORDATORIO CRÍTICO: El sistema de filtrado inteligente ya validó que las fuentes {relevant_sources} son relevantes para {section_id}. Por lo tanto, DEBEN aparecer mencionadas en tu análisis de alguna forma.

== ESQUEMA JSON ==
{schema}
== FIN ESQUEMA ==

{full_instruction}

RESPUESTA: JSON válido con máximo detalle de fuentes consultadas."""
            else:
                # Prompt genérico para secciones sin fuentes adicionales
                prompt = f"""
ANALISTA TÉCNICO SENIOR - MISIÓN: MÁXIMO CONTENIDO ESPECÍFICO

IDEA: "{shared_inputs.get('idea_brief','')}"
KEYWORDS: {json.dumps(shared_inputs.get('sector_keywords', []), ensure_ascii=False)}
SCORE: "{shared_inputs.get('score','')}"

🚨 **PROHIBIDO TERMINANTEMENTE - DATOS INVENTADOS:** 🚨
❌ NUNCA inventes números de patentes (US10845123B2, EP3456789A1, etc.)
❌ NUNCA inventes URLs ficticias (https://patents.google.com/patent/...)
❌ NUNCA inventes DOIs o referencias que no existan
❌ NUNCA inventes datos específicos como fechas, autores, títulos exactos
❌ NUNCA inventes normativas (ISO 12345:2023, EN 98765, etc.)
❌ NUNCA inventes códigos de certificación o números de regulación ficticia

**TAMBIÉN PROHIBIDO - CONTENIDO GENÉRICO:**
❌ "área tecnológica específica" 
❌ "Se requiere búsqueda especializada"
❌ "bases de datos especializadas"
❌ "universidades del área"
❌ "investigadores por identificar"

**OBLIGATORIO - SOLO DATOS REALES:**
✅ Empresas REALES: Panasonic, Siemens, IBM, Google, Microsoft, Samsung
✅ Universidades REALES: MIT, Stanford, ETH Zurich, Delft University  
✅ Revistas REALES: Nature Materials, Science, IEEE Transactions
✅ Normativas REALES: ISO 9001, ISO 14001, REACH, RoHS, CE, UL, IEC 60601
✅ Organismos REALES: Comisión Europea, EPA, OSHA, FDA, BSI, TÜV, DNV
✅ Si NO conoces patentes reales, di: "Se requiere búsqueda específica en Google Patents para empresas [Panasonic/Siemens/etc.]"
✅ Si NO conoces normativas reales, di: "Se requiere consulta en [EPA/Comisión Europea/FDA] para regulación específica en [área]"

== ESQUEMA JSON A COMPLETAR ==
{schema}
== FIN ESQUEMA ==

{full_instruction}

RESPUESTA: JSON válido sin texto adicional. MÁXIMO detalle técnico específico.
"""
        
        # ✅ NUEVA ESTRATEGIA: Configuración específica para secciones críticas
        if section_id == "TECH_IP_LANDSCAPE":
            system_message = (
                "Eres un ANALISTA TÉCNICO SENIOR con amplio conocimiento en patentes y tecnología. "
                "MISIÓN: Buscar en tu conocimiento DATOS ESPECÍFICOS de patentes, publicaciones científicas, gaps y tendencias. "
                ""
                "INSTRUCCIONES CRÍTICAS: "
                "1. **USA CONOCIMIENTO REAL**: Si conoces patentes de IBM, Google, Microsoft, Samsung, Siemens - ÚSALAS con números reales "
                "2. **SI NO CONOCES**: Especifica EXACTAMENTE qué buscar - NO uses frases vagas como 'área tecnológica específica' "
                "3. **EJEMPLOS OBLIGATORIOS**: Para ultrasonido menciona Panasonic, Siemens; para electrificación menciona ABB, Schneider "
                "4. **UNIVERSIDADES REALES**: MIT, Stanford, ETH Zurich, Delft - NO 'universidades del área' "
                "5. **BASES DE DATOS**: Google Patents, USPTO.gov, EPO.org - NO 'bases especializadas' "
                "6. **REVISTAS REALES**: Nature Materials, IEEE Transactions, Science - NO 'revistas del área' "
                ""
                "FORMATO: JSON válido ESTRICTO sin texto adicional. "
                "OBJETIVO: Máximo contenido técnico específico conocido."
            )
            temp = 0.1  # Temperatura baja pero no extrema para permitir especificidad
            max_tok = 1500  # Tokens aumentados para permitir más detalle técnico
        elif section_id == "REGULATORY_ESG_RISK":
            system_message = (
                "Eres un ANALISTA REGULATORIO SENIOR con amplio conocimiento en normativas, certificaciones y ESG. "
                "MISIÓN: Buscar en tu conocimiento DATOS ESPECÍFICOS de normativas reales, certificaciones existentes, riesgos regulatorios y oportunidades ESG. "
                ""
                "INSTRUCCIONES CRÍTICAS: "
                "1. **USA NORMATIVAS REALES**: ISO 9001, ISO 14001, REACH, RoHS, CE, UL, IEC, FDA 21 CFR - NUNCA inventes códigos "
                "2. **ORGANISMOS REALES**: Comisión Europea, EPA, OSHA, FDA, BSI, TÜV, DNV, Lloyd's Register - NO 'autoridades competentes' "
                "3. **SI NO CONOCES**: Especifica 'Se requiere consulta en [EPA/Comisión Europea] para regulación específica en [área]' "
                "4. **CERTIFICACIONES REALES**: CE, UL, CSA, FCC, ATEX, SIL - NO inventes códigos de certificación "
                "5. **URLs REALES**: Solo si conoces la URL oficial real (europa.eu, epa.gov, iso.org) "
                "6. **TRANSPARENCIA TOTAL**: Si no conoces, ser específico sobre qué consultar y dónde "
                ""
                "FORMATO: JSON válido ESTRICTO sin texto adicional. "
                "OBJETIVO: Máximo contenido regulatorio real y específico conocido."
            )
            temp = 0.1  # Temperatura baja para máxima precisión regulatoria
            max_tok = 1500  # Tokens aumentados para permitir más detalle regulatorio
        else:
            system_message = "Eres un analista competitivo senior. NUNCA inventes números de patente o datos falsos. Sé transparente sobre limitaciones. Devuelve SOLO el JSON válido."
            temp = 0.15
            max_tok = 1400
        
        # 🔍 LOGGING CRÍTICO ANTES DE LLAMAR AL LLM
        if section_id == "BENCHMARK_MATRIX":
            print(f"🚨 [BENCHMARK-LLM] === ENVIANDO PROMPT AL LLM ===")
            print(f"🚨 [BENCHMARK-LLM] Prompt length: {len(prompt)} chars")
            print(f"🚨 [BENCHMARK-LLM] System message: {system_message[:100]}...")
            print(f"🚨 [BENCHMARK-LLM] First 500 chars of prompt: {prompt[:500]}...")
            if 'tabla_comparativa' in prompt:
                print(f"✅ [BENCHMARK-LLM] Prompt contiene 'tabla_comparativa'")
            # Buscar nombres de empresas específicas del mapping
            found_mapping_companies = []
            for word in ['Weber', 'Evoqua', 'Bluewater', 'Sonihull', 'AkzoNobel', 'Hempel', 'Trelleborg', 'ClearBlue', 'Marine Electrical']:
                if word in prompt:
                    found_mapping_companies.append(word)
            if found_mapping_companies:
                print(f"🎯 [BENCHMARK-LLM] EMPRESAS DEL MAPPING ENCONTRADAS: {found_mapping_companies}")
            else:
                print(f"⚠️ [BENCHMARK-LLM] NO SE ENCONTRARON EMPRESAS DEL MAPPING EN PROMPT")
            
            if any(word in prompt.lower() for word in ['competidor', 'empresa', 'siemens', 'abb']):
                print(f"✅ [BENCHMARK-LLM] Prompt contiene palabras clave de empresas")
            print(f"🚨 [BENCHMARK-LLM] === LLAMANDO A OPENAI ===")
        
        resp = self.openai_client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=temp,
            max_tokens=max_tok,
            response_format={"type": "json_object"}
        )
        
        # 🔍 LOGGING CRÍTICO DESPUÉS DE RECIBIR RESPUESTA
        if section_id == "BENCHMARK_MATRIX":
            raw_response = resp.choices[0].message.content
            print(f"🚨 [BENCHMARK-LLM] === RESPUESTA DEL LLM RECIBIDA ===")
            print(f"🚨 [BENCHMARK-LLM] Response length: {len(raw_response)} chars")
            print(f"🚨 [BENCHMARK-LLM] First 300 chars: {raw_response[:300]}...")
            if 'tabla_comparativa' in raw_response:
                print(f"✅ [BENCHMARK-LLM] Respuesta contiene 'tabla_comparativa'")
            if 'tabla' in raw_response and 'tabla_comparativa' not in raw_response:
                print(f"⚠️ [BENCHMARK-LLM] Respuesta contiene solo 'tabla' (formato antiguo)")
            
            # Buscar empresas del mapping en la respuesta
            mapping_companies_in_response = []
            for word in ['Weber', 'Evoqua', 'Bluewater', 'Sonihull', 'AkzoNobel', 'Hempel', 'Trelleborg', 'ClearBlue', 'Marine Electrical']:
                if word in raw_response:
                    mapping_companies_in_response.append(word)
            
            # Buscar empresas genéricas en la respuesta
            generic_companies = [name for name in ['Siemens', 'ABB', 'Schneider', 'GE', 'Rockwell', 'Bosch', 'Samsung', 'Panasonic'] if name in raw_response]
            
            if mapping_companies_in_response:
                print(f"🎯 [BENCHMARK-LLM] ¡ÉXITO! EMPRESAS DEL MAPPING EN RESPUESTA: {mapping_companies_in_response}")
            else:
                print(f"❌ [BENCHMARK-LLM] FALLÓ: No se encontraron empresas del mapping en respuesta")
            
            if generic_companies:
                print(f"⚠️ [BENCHMARK-LLM] EMPRESAS GENÉRICAS DETECTADAS: {generic_companies}")
            else:
                print(f"✅ [BENCHMARK-LLM] Sin empresas genéricas en respuesta")
            print(f"🚨 [BENCHMARK-LLM] === PROCESANDO JSON ===")
        
        # ✅ MEJORADO: Manejo robusto de JSON con múltiples estrategias de recuperación
        raw_content = resp.choices[0].message.content
        data = self._parse_json_with_fallback(raw_content, section_id)
        
        # ✅ APLICAR VALIDACIÓN Y FILTRADO AUTOMÁTICO PARA COMPETIDORES
        if section_id == "COMPETITOR_MAPPING":
            data = self._validate_and_filter_competitors(data)
            print(f"🔍 [CompetitorAnalysis] Competidores validados y filtrados para {section_id}")
        
        # ✅ NUEVA VALIDACIÓN PARA BENCHMARK_MATRIX - MÉTRICAS CUANTITATIVAS
        if section_id == "BENCHMARK_MATRIX":
            # 🔧 CONVERSIÓN CRÍTICA: Convertir formato antiguo a nuevo ANTES de validación
            if isinstance(data, dict) and 'tabla' in data and 'tabla_comparativa' not in data:
                print("🔄 [BENCHMARK] Convirtiendo formato antiguo 'tabla' a 'tabla_comparativa' ANTES de validación")
                data['tabla_comparativa'] = data.pop('tabla')
            
            # 🎯 NUEVA VALIDACIÓN ROBUSTA: Verificar coherencia con COMPETITOR_MAPPING
            data = self._validate_benchmark_competitor_coherence(data, report_dict)
            
            # Validar y normalizar métricas cuantitativas
            data = self._validate_benchmark_metrics(data)
            
            # Filtrar Sener y competidores inválidos (mantener compatibilidad con formato anterior)
            if isinstance(data, dict):
                # Nuevo formato: tabla_comparativa
                if 'tabla_comparativa' in data and isinstance(data['tabla_comparativa'], list):
                    tabla_filtrada = []
                    for competidor in data['tabla_comparativa']:
                        if isinstance(competidor, dict):
                            nombre = competidor.get('nombre', '')
                            if nombre and 'sener' not in nombre.lower():
                                tabla_filtrada.append(competidor)
                    data['tabla_comparativa'] = tabla_filtrada
                    print(f"🔍 [BENCHMARK] Tabla cuantitativa filtrada: {len(tabla_filtrada)} competidores (Sener excluido)")
                
                # Formato anterior para compatibilidad: tabla
                elif 'tabla' in data and isinstance(data['tabla'], list):
                    tabla_filtrada = []
                    for competidor in data['tabla']:
                        if isinstance(competidor, dict):
                            nombre = competidor.get('nombre', competidor.get('empresa', ''))
                            if nombre and 'sener' not in nombre.lower():
                                tabla_filtrada.append(competidor)
                    data['tabla'] = tabla_filtrada
                    print(f"🔍 [BENCHMARK] Tabla formato anterior filtrada: {len(tabla_filtrada)} competidores (Sener excluido)")
        
        # ✅ NUEVA VALIDACIÓN: Verificar patentes para TECH_IP_LANDSCAPE
        if section_id == "TECH_IP_LANDSCAPE":
            data = self._validate_patent_data(data)
            print(f"🔍 [CompetitorAnalysis] Datos de patentes validados para transparencia")
            
            # ✅ NUEVA VALIDACIÓN: Verificar publicaciones científicas
            data = self._validate_publication_data(data)
            print(f"🔍 [CompetitorAnalysis] Datos de publicaciones científicas validados para especificidad")
        
        # ✅ NUEVA VALIDACIÓN: Verificar datos regulatorios para REGULATORY_ESG_RISK
        if section_id == "REGULATORY_ESG_RISK":
            data = self._validate_regulatory_data(data)
            print(f"🔍 [CompetitorAnalysis] Datos regulatorios validados para transparencia")
        
        # ---------------------------------------------------------------
        # 🔥 NUEVO: fallback final -> si la tabla quedó vacía o solo contiene
        #            el placeholder genérico, crear una tabla mínima con los
        #            competidores del mapping y métricas 'N/D'.
        if section_id == "BENCHMARK_MATRIX":
            tabla_key = 'tabla_comparativa' if isinstance(data, dict) and 'tabla_comparativa' in data else 'tabla'
            placeholder_strings = [
                'análisis comparativo en desarrollo',
                'requiere estudio específico',
                'evaluación de modelos en proceso'
            ]
            def _fila_es_placeholder(fila: dict) -> bool:
                nombre = (fila.get('nombre') or '').lower()
                return any(ph in nombre for ph in placeholder_strings)
            tabla_actual = []
            if isinstance(data, dict) and tabla_key in data and isinstance(data[tabla_key], list):
                tabla_actual = [fila for fila in data[tabla_key] if isinstance(fila, dict) and not _fila_es_placeholder(fila)]
            # Si no quedan filas válidas, reconstruir con competidores del mapping
            if not tabla_actual:
                mapping_competitors = []
                if report_dict and 'COMPETITOR_MAPPING' in report_dict:
                    mapping_competitors = [c['nombre'] for c in self._extract_competitors_from_mapping(report_dict)[:7]]
                if mapping_competitors:
                    print("⚠️ [BENCHMARK] Tabla vacía o placeholder: generando versión mínima con competidores del mapping")
                    tabla_actual = []
                    for comp in mapping_competitors:
                        tabla_actual.append({
                            'nombre': comp,
                            'ingresos_anuales_millones_eur': 'N/D',
                            'empleados_total': 'N/D',
                            'años_en_mercado': 'N/D',
                            'paises_presencia': 'N/D',
                            'proyectos_anuales_estimados': 'N/D',
                            'precio_promedio_proyecto_millones': 'N/D',
                            'cuota_mercado_sector_porcentaje': 'N/D',
                            'gasto_id_porcentaje_ingresos': 'N/D',
                            'certificaciones_principales': 'N/D',
                            'patentes_activas_estimadas': 'N/D'
                        })
                    # Actualizar estructura
                    if isinstance(data, dict):
                        data[tabla_key] = tabla_actual
                    else:
                        data = {tabla_key: tabla_actual}
        # ---------------------------------------------------------------
        
        return data
    
    def _parse_json_with_fallback(self, raw_content, section_id):
        """
        ✅ NUEVA FUNCIÓN: Parsea JSON con múltiples estrategias de recuperación ante errores
        """
        import re
        
        # Estrategia 1: JSON directo (caso normal)
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as e:
            print(f"⚠️ [JSON] Estrategia 1 falló para {section_id}: {e}")
        
        # Estrategia 2: Limpiar comillas sin cerrar y caracteres problemáticos
        try:
            # Limpiar posibles problemas comunes de JSON
            cleaned = raw_content.strip()
            
            # Escapar comillas dobles no cerradas dentro de strings
            cleaned = self._fix_unescaped_quotes(cleaned)
            
            # Remover trailing commas
            cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
            
            # Intentar parsear JSON limpio
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"⚠️ [JSON] Estrategia 2 falló para {section_id}: {e}")
        
        # Estrategia 3: Extraer JSON desde el primer { hasta el último }
        try:
            start_idx = raw_content.find('{')
            end_idx = raw_content.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_part = raw_content[start_idx:end_idx+1]
                json_part = self._fix_unescaped_quotes(json_part)
                return json.loads(json_part)
        except json.JSONDecodeError as e:
            print(f"⚠️ [JSON] Estrategia 3 falló para {section_id}: {e}")
        
        # Estrategia 4: Intentar completar JSON incompleto
        try:
            completed_json = self._attempt_json_completion(raw_content)
            if completed_json:
                return json.loads(completed_json)
        except json.JSONDecodeError as e:
            print(f"⚠️ [JSON] Estrategia 4 falló para {section_id}: {e}")
        
        # Estrategia 5: Para TECH_IP_LANDSCAPE, intentar extraer partes del JSON malformado
        if section_id == "TECH_IP_LANDSCAPE":
            try:
                print(f"🔧 [JSON] Estrategia especial para TECH_IP_LANDSCAPE: extracción parcial")
                # Intentar extraer al menos las partes que se puedan usar
                partial_data = self._extract_partial_tech_landscape(raw_content)
                if partial_data and len(partial_data) > 1:  # Si tiene al menos algunos datos
                    return partial_data
            except Exception as e:
                print(f"⚠️ [JSON] Extracción parcial falló: {e}")
        
        # Estrategia 6: Fallback a estructura por defecto
        print(f"🔄 [JSON] Todas las estrategias fallaron para {section_id}, usando estructura por defecto")
        return self._generate_default_structure(section_id)
    
    def _fix_unescaped_quotes(self, json_str):
        """
        ✅ NUEVA FUNCIÓN: Repara comillas sin cerrar en JSON malformado
        """
        try:
            # Reparar strings sin cerrar al final de líneas
            lines = json_str.split('\n')
            fixed_lines = []
            
            for line in lines:
                # Si la línea tiene una comilla de apertura pero no de cierre
                if line.count('"') % 2 == 1 and ':' in line:
                    # Añadir comilla de cierre antes de la coma o fin de línea
                    if line.rstrip().endswith(','):
                        line = line.rstrip()[:-1] + '",'
                    elif not line.rstrip().endswith('"'):
                        line = line.rstrip() + '"'
                
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
        except Exception:
            return json_str
    
    def _attempt_json_completion(self, raw_content):
        """
        ✅ NUEVA FUNCIÓN: Intenta completar JSON incompleto
        """
        try:
            # Encontrar la estructura JSON principal
            start_idx = raw_content.find('{')
            if start_idx == -1:
                return None
            
            # Contar llaves para determinar si está completo
            open_braces = 0
            close_braces = 0
            last_valid_idx = start_idx
            
            for i, char in enumerate(raw_content[start_idx:], start_idx):
                if char == '{':
                    open_braces += 1
                elif char == '}':
                    close_braces += 1
                    last_valid_idx = i
                
                # Si las llaves están balanceadas, tenemos JSON completo
                if open_braces > 0 and open_braces == close_braces:
                    return raw_content[start_idx:i+1]
            
            # Si no están balanceadas, intentar completar
            if open_braces > close_braces:
                missing_braces = open_braces - close_braces
                completion = raw_content[start_idx:last_valid_idx+1] + ('}' * missing_braces)
                return completion
            
            return None
        except Exception:
            return None
    
    def _extract_partial_tech_landscape(self, raw_content):
        """
        ✅ NUEVA FUNCIÓN: Extrae datos parciales de TECH_IP_LANDSCAPE cuando JSON está malformado
        """
        try:
            import re
            
            # Estructura base
            result = {
                "patentes_destacadas": [],
                "publicaciones_clave": [],
                "gaps_tecnologicos": [],
                "tendencias_emergentes": []
            }
            
            # Buscar patentes con regex
            patent_pattern = r'"titulo":\s*"([^"]*)".*?"numero_patente":\s*"([^"]*)".*?"titular":\s*"([^"]*)"'
            patents = re.findall(patent_pattern, raw_content, re.DOTALL)
            
            for titulo, numero, titular in patents[:3]:  # Max 3 patentes
                if titulo and numero and titular:
                    result["patentes_destacadas"].append({
                        "titulo": titulo,
                        "numero_patente": numero,
                        "titular": titular,
                        "año": "N/D",
                        "pais": "N/D",
                        "descripcion": "Extraído de respuesta parcial",
                        "relevancia_competitiva": "Media",
                        "url": ""
                    })
            
            # Buscar publicaciones con regex
            pub_pattern = r'"titulo":\s*"([^"]*)".*?"autores":\s*"([^"]*)".*?"revista":\s*"([^"]*)"'
            publications = re.findall(pub_pattern, raw_content, re.DOTALL)
            
            for titulo, autores, revista in publications[:3]:  # Max 3 publicaciones
                if titulo and autores and revista:
                    result["publicaciones_clave"].append({
                        "titulo": titulo,
                        "autores": autores,
                        "revista": revista,
                        "año": "N/D",
                        "tipo": "Artículo",
                        "resumen": "Extraído de respuesta parcial",
                        "relevancia_tecnologica": "Media",
                        "url": ""
                    })
            
            return result if result["patentes_destacadas"] or result["publicaciones_clave"] else None
            
        except Exception:
            return None

    def _validate_patent_data(self, patent_data):
        """
        Valida y mejora la transparencia de los datos de patentes.
        ✅ FUNCIÓN MEJORADA: Detecta mejor datos inventados y los reemplaza con indicaciones de búsqueda
        """
        if not isinstance(patent_data, dict):
            return patent_data
        
        # Validar patentes destacadas
        if 'patentes_destacadas' in patent_data:
            validated_patents = []
            for patent in patent_data['patentes_destacadas']:
                if isinstance(patent, dict):
                    # Verificar números de patente inventados
                    numero = patent.get('numero_patente', '')
                    if numero and self._looks_like_fake_patent_number(numero):
                        # Reemplazar con búsqueda específica usando el formato de las instrucciones
                        titulo = patent.get('titulo', 'tecnología específica')
                        keywords = titulo.split()[:3]  # Primeras 3 palabras del título
                        keyword_str = '+'.join(keywords) if keywords else 'keywords+específicos'
                        patent['numero_patente'] = f'BÚSQUEDA REQUERIDA: Google Patents con keywords {keyword_str}'
                        
                        # También actualizar URL si existe
                        if patent.get('url', '').startswith('https://patents.google.com/patent/'):
                            patent['url'] = 'Disponible en Google Patents tras búsqueda específica con keywords técnicos'
                    
                    # Validar DOIs inventados (formato: 10.xxxx/...)
                    doi = patent.get('doi', '')
                    if doi and doi.startswith('10.') and len(doi) > 20:
                        # Si parece un DOI muy específico, probablemente inventado
                        patent['doi'] = 'DOI disponible tras búsqueda específica'
                    
                    validated_patents.append(patent)
            
            patent_data['patentes_destacadas'] = validated_patents
        
        return patent_data
    
    def _validate_regulatory_data(self, regulatory_data):
        """
        Valida y mejora la transparencia de los datos regulatorios.
        ✅ FUNCIÓN NUEVA: Detecta normativas inventadas y mejora transparencia
        """
        if not isinstance(regulatory_data, dict):
            return regulatory_data
        
        # Validar normativas clave
        if 'normativas_clave' in regulatory_data:
            validated_normativas = []
            for normativa in regulatory_data['normativas_clave']:
                if isinstance(normativa, dict):
                    # Verificar si parece una normativa inventada
                    nombre = normativa.get('nombre', '')
                    if nombre and self._looks_like_fake_regulation(nombre):
                        # Reemplazar con indicación transparente
                        normativa_transparente = {
                            **normativa,
                            'nombre': f"Se requiere consulta en Comisión Europea/EPA para regulación específica en {normativa.get('área', 'área aplicable')}",
                            'detalle': f"Verificación pendiente de regulaciones aplicables en {normativa.get('área', 'el sector')}"
                        }
                        validated_normativas.append(normativa_transparente)
                    else:
                        validated_normativas.append(normativa)
                elif isinstance(normativa, str):
                    if self._looks_like_fake_regulation(normativa):
                        validated_normativas.append(f"Se requiere consulta regulatoria específica para: {normativa}")
                    else:
                        validated_normativas.append(normativa)
            
            regulatory_data['normativas_clave'] = validated_normativas
        
        # Validar certificaciones
        if 'certificaciones' in regulatory_data:
            validated_certificaciones = []
            for cert in regulatory_data['certificaciones']:
                if isinstance(cert, dict):
                    nombre = cert.get('nombre', '')
                    if nombre and self._looks_like_fake_certification(nombre):
                        cert_transparente = {
                            **cert,
                            'nombre': f"Se requiere consulta en BSI/TÜV/DNV para certificación específica en {cert.get('área', 'área aplicable')}",
                            'detalle': f"Verificación pendiente de certificaciones requeridas en {cert.get('área', 'el sector')}"
                        }
                        validated_certificaciones.append(cert_transparente)
                    else:
                        validated_certificaciones.append(cert)
                elif isinstance(cert, str):
                    if self._looks_like_fake_certification(cert):
                        validated_certificaciones.append(f"Se requiere consulta para certificación: {cert}")
                    else:
                        validated_certificaciones.append(cert)
            
            regulatory_data['certificaciones'] = validated_certificaciones
        
        return regulatory_data
    
    def _validate_publication_data(self, publication_data):
        """
        Valida y mejora la transparencia de los datos de publicaciones científicas.
        ✅ FUNCIÓN NUEVA: Detecta publicaciones inventadas y mejora especificidad
        """
        if not isinstance(publication_data, dict):
            return publication_data
        
        # Validar publicaciones clave
        if 'publicaciones_clave' in publication_data:
            validated_publications = []
            for pub in publication_data['publicaciones_clave']:
                if isinstance(pub, dict):
                    # Verificar títulos genéricos o inventados
                    titulo = pub.get('titulo', '')
                    if titulo and self._looks_like_fake_publication_title(titulo):
                        # Reemplazar con búsqueda específica basada en el área
                        area_keyword = pub.get('resumen', '').split()[:3]  # Primeras palabras del resumen
                        area_keyword = ' '.join(area_keyword) if area_keyword else 'área tecnológica'
                        
                        pub['titulo'] = f"REVISIÓN LITERATURA REQUERIDA: Análisis bibliográfico especializado en {area_keyword}"
                    
                    # Verificar autores genéricos
                    autores = pub.get('autores', '')
                    if autores and self._looks_like_fake_authors(autores):
                        # Reemplazar con instituciones específicas de búsqueda
                        pub['autores'] = 'INVESTIGACIÓN NECESARIA: Equipos MIT, Stanford Engineering, ETH Zurich, Delft University, Cambridge'
                    
                    # Verificar revistas genéricas
                    revista = pub.get('revista', '')
                    if revista and self._looks_like_fake_journal(revista):
                        # Reemplazar con revistas específicas del área
                        pub['revista'] = 'BÚSQUEDA OBLIGATORIA: Nature Materials, Science Advances, IEEE Transactions específicas del área'
                    
                    # Verificar DOIs inventados
                    doi = pub.get('doi', '')
                    if doi and self._looks_like_fake_doi(doi):
                        pub['doi'] = 'DOI específico requerido tras búsqueda bibliográfica dirigida'
                    
                    # Verificar URLs inventadas
                    url = pub.get('url', '')
                    if url and self._looks_like_fake_publication_url(url):
                        pub['url'] = 'URL disponible tras identificación específica en bases bibliográficas'
                    
                    validated_publications.append(pub)
            
            publication_data['publicaciones_clave'] = validated_publications
        
        return publication_data
    
    def _looks_like_fake_publication_title(self, title):
        """
        Detecta títulos de publicaciones que parecen inventados o demasiado genéricos.
        """
        title_lower = title.lower()
        
        # Frases genéricas típicas de títulos inventados
        generic_phrases = [
            'análisis del estado del arte',
            'revisión de literatura',
            'estudio del área',
            'investigación en el campo',
            'advances in',
            'research in',
            'study of',
            'analysis of',
            'development of',
            'investigation into'
        ]
        
        # Detectar títulos muy genéricos
        for phrase in generic_phrases:
            if phrase in title_lower and len(title) < 100:  # Títulos cortos y genéricos
                return True
        
        # Detectar patrones de títulos inventados
        import re
        if re.search(r'^(study|analysis|research|investigation)\s+(of|on|in)\s+\w+$', title_lower):
            return True
        
        return False
    
    def _looks_like_fake_authors(self, authors):
        """
        Detecta listas de autores que parecen inventadas.
        """
        authors_lower = authors.lower()
        
        # Frases genéricas típicas de autores inventados
        generic_phrases = [
            'et al.',
            'y colaboradores',
            'equipo de investigación',
            'grupo de',
            'investigadores de',
            'equipo del',
            'por determinar',
            'autores varios'
        ]
        
        # Detectar frases genéricas de autores
        for phrase in generic_phrases:
            if phrase in authors_lower and len(authors) < 50:  # Autores cortos y genéricos
                return True
        
        return False
    
    def _looks_like_fake_journal(self, journal):
        """
        Detecta nombres de revistas que parecen inventados o demasiado genéricos.
        """
        journal_lower = journal.lower()
        
        # Frases genéricas de revistas inventadas
        generic_phrases = [
            'journal of',
            'revista de',
            'international journal',
            'revista internacional',
            'proceedings of',
            'revista especializada',
            'revista del área',
            'journal especializado'
        ]
        
        # Solo detectar si es MUY genérico (sin especificidad real)
        generic_count = sum(1 for phrase in generic_phrases if phrase in journal_lower)
        
        # Es genérico si tiene frases genéricas Y es muy corto (falta especificidad)
        if generic_count > 0 and len(journal) < 40:
            return True
        
        return False
    
    def _looks_like_fake_doi(self, doi):
        """
        Detecta DOIs que parecen inventados.
        """
        import re
        
        # Patrón básico de DOI real: 10.xxxx/yyyy
        if not re.match(r'^10\.\d{4}/.*', doi):
            return False  # No es un DOI válido, pero no necesariamente inventado
        
        # Detectar DOIs con patrones sospechosos (muy largos o muy simples)
        if len(doi) > 80:  # DOIs excesivamente largos
            return True
        
        # Detectar patrones de números secuenciales (10.1234/123456)
        if re.search(r'10\.\d{4}/\d{6,}$', doi):
            return True
        
        return False
    
    def _looks_like_fake_publication_url(self, url):
        """
        Detecta URLs de publicaciones que parecen inventadas.
        """
        url_lower = url.lower()
        
        # URLs claramente inventadas
        fake_patterns = [
            'example.com',
            'placeholder.org',
            'tempurl.com',
            'arxiv.org/fake',
            'doi.org/fake'
        ]
        
        for pattern in fake_patterns:
            if pattern in url_lower:
                return True
        
        return False
    
    def _looks_like_fake_regulation(self, regulation_name):
        """
        Detecta SOLO normativas que claramente parecen inventadas.
        ✅ FUNCIÓN NUEVA: Más selectiva, solo detecta patrones claramente falsos
        """
        import re
        
        # Patrones sospechosos de normativas inventadas
        fake_patterns = [
            r'ISO \d{5,}:\d{4}',  # ISO con números muy largos (ISO 12345:2023)
            r'EN \d{5,}',         # EN con números muy largos
            r'IEC \d{5,}',        # IEC con números muy largos
            r'ASTM [A-Z]\d{4,}',  # ASTM con números muy largos
            r'BS \d{5,}',         # BS con números muy largos
            r'DIN \d{5,}',        # DIN con números muy largos
        ]
        
        # También detectar frases genéricas
        generic_phrases = [
            'normativa específica del sector',
            'regulación aplicable',
            'estándar del área',
            'certificación requerida',
            'normativas por determinar'
        ]
        
        regulation_lower = regulation_name.lower()
        
        # Verificar patrones sospechosos
        for pattern in fake_patterns:
            if re.search(pattern, regulation_name):
                return True
        
        # Verificar frases genéricas
        for phrase in generic_phrases:
            if phrase in regulation_lower:
                return True
        
        return False
    
    def _looks_like_fake_certification(self, cert_name):
        """
        Detecta certificaciones que parecen inventadas.
        """
        import re
        
        # Patrones sospechosos de certificaciones inventadas
        fake_patterns = [
            r'[A-Z]{2,4}-\d{4,}',   # Códigos inventados tipo ABC-1234
            r'CERT\d{4,}',          # CERT1234
            r'[A-Z]{3,}\d{3,}',     # Códigos largos tipo XYZ123
        ]
        
        # Frases genéricas
        generic_phrases = [
            'certificación específica',
            'certificación aplicable',
            'certificación del sector',
            'certificación requerida',
            'por determinar'
        ]
        
        cert_lower = cert_name.lower()
        
        # Verificar patrones sospechosos
        for pattern in fake_patterns:
            if re.search(pattern, cert_name):
                return True
        
        # Verificar frases genéricas
        for phrase in generic_phrases:
            if phrase in cert_lower:
                return True
        
        return False
    
    def _looks_like_fake_patent_number(self, patent_number):
        """
        Detecta números de patente que parecen inventados.
        ✅ FUNCIÓN MEJORADA: Detecta patrones sospechosos MUCHO más agresiva
        """
        import re
        
        if not patent_number or not isinstance(patent_number, str):
            return False
        
        # 🚨 REGLA PRINCIPAL: Si el LLM genera CUALQUIER número de patente específico,
        # probablemente lo está inventando porque no tiene acceso a bases de datos reales
        
        # Lista ampliada de números de patente claramente inventados
        known_fake_patents = [
            'US10845123B2', 'EP3456789A1', 'US10234567B2', 'EP3456789A1', 
            'US10557234B2', 'CN123456789A', 'US10123456B2', 'EP1234567A1', 
            'JP2020123456A', 'US20190234567A1', 'US20200123456A1', 'EP3789456A1',
            'US10998877B2', 'US11123456B2', 'WO2020123456A1', 'CN111234567A'
        ]
        
        if patent_number in known_fake_patents:
            return True
        
        # 🚨 NUEVA ESTRATEGIA: RECHAZAR CASI TODOS LOS NÚMEROS ESPECÍFICOS
        # Patrones comunes de números inventados (muy amplio)
        common_fake_patterns = [
            r'^US\d{8}[AB]\d$',        # US + 8 dígitos + A/B + dígito
            r'^US\d{11}[AB]\d$',       # US + 11 dígitos + A/B + dígito  
            r'^EP\d{7}[AB]\d$',        # EP + 7 dígitos + A/B + dígito
            r'^CN\d{9}[AB]?$',         # CN + 9 dígitos + opcional A/B
            r'^WO\d{4}\d{6}[AB]\d$',   # WO + año + 6 dígitos + A/B + dígito
            r'^JP\d{4}\d{6}[AB]?$',    # JP + año + 6 dígitos + opcional A/B
            r'^US202[0-4]\d{6}A1$',    # US + año 2020-2024 + 6 dígitos + A1
            r'^US1[01]\d{6}B2$',       # US + 1 + otro dígito + 6 dígitos + B2
        ]
        
        # Si coincide con cualquier patrón común, analizarlo más
        for pattern in common_fake_patterns:
            if re.match(pattern, patent_number):
                
                # Extraer TODOS los dígitos para análisis
                all_digits = ''.join(re.findall(r'\d', patent_number))
                
                if len(all_digits) >= 6:
                    # Detectar patrones artificiales MÚLTIPLES
                    
                    # 1. Secuencias ascendentes/descendentes
                    consecutive_ascending = 0
                    consecutive_descending = 0
                    for i in range(len(all_digits) - 1):
                        if int(all_digits[i+1]) == int(all_digits[i]) + 1:
                            consecutive_ascending += 1
                        if int(all_digits[i+1]) == int(all_digits[i]) - 1:
                            consecutive_descending += 1
                    
                    # 2. Dígitos repetidos
                    unique_digits = len(set(all_digits))
                    digit_diversity = unique_digits / len(all_digits)
                    
                    # 3. Secuencias numéricas obvias
                    obvious_sequences = [
                        '123456', '234567', '345678', '456789', '567890',
                        '654321', '987654', '876543', '765432',
                        '111111', '222222', '333333', '444444', '555555',
                        '000000', '123123', '456456', '789789'
                    ]
                    has_obvious_sequence = any(seq in all_digits for seq in obvious_sequences)
                    
                    # 4. Años en el número que no tienen sentido
                    suspicious_years = ['2019', '2020', '2021', '2022', '2023', '2024']
                    has_recent_year = any(year in patent_number for year in suspicious_years)
                    
                    # 🚨 CRITERIOS MUY AGRESIVOS PARA DETECTAR INVENTOS:
                    # Si tiene 3+ dígitos consecutivos ascendentes/descendentes
                    if consecutive_ascending >= 3 or consecutive_descending >= 3:
                        return True
                    
                    # Si tiene muy poca diversidad de dígitos (menos de 50%)
                    if digit_diversity < 0.5:
                        return True
                    
                    # Si contiene secuencias obvias
                    if has_obvious_sequence:
                        return True
                    
                    # Si contiene años recientes en posiciones sospechosas
                    if has_recent_year and len(all_digits) >= 8:
                        return True
                    
                    # 🚨 NUEVA REGLA: Números "demasiado perfectos"
                    # Si los últimos 6 dígitos forman patrones
                    if len(all_digits) >= 6:
                        last_6 = all_digits[-6:]
                        # Números "redondos" o repetitivos
                        if last_6 in ['123456', '234567', '345678', '456789', '567890', 
                                     '111111', '222222', '333333', '444444', '555555', '666666',
                                     '777777', '888888', '999999', '000000', '123123', '456456']:
                            return True
        
        # 🚨 REGLA ADICIONAL: Si contiene ciertos indicadores de invención
        invention_indicators = [
            'example', 'sample', 'test', 'placeholder', 'temp', 'fake', 'demo'
        ]
        
        patent_lower = patent_number.lower()
        if any(indicator in patent_lower for indicator in invention_indicators):
            return True
            
        return False

    def _search_real_patents(self, sector_keywords, max_results=3):
        """
        Busca patentes reales relacionadas con las palabras clave del sector.
        ✅ NUEVA FUNCIÓN: Búsqueda real de patentes para evitar datos inventados
        """
        import requests
        import re
        from bs4 import BeautifulSoup
        import logging
        
        try:
            # Construir query de búsqueda para patentes
            if isinstance(sector_keywords, list):
                query_terms = " ".join(sector_keywords[:3])  # Usar máximo 3 keywords
            else:
                query_terms = str(sector_keywords)
            
            # Buscar en Google Patents usando requests
            search_url = "https://patents.google.com/xhr/query"
            params = {
                'url': f"q={query_terms}",
                'num': max_results,
                'sort': 'new'  # Patentes más nuevas primero
            }
            
            logging.info(f"[Patents] 🔍 Buscando patentes reales para: {query_terms}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    patents = []
                    
                    # Extraer información de patentes reales
                    if 'results' in data and 'cluster' in data['results']:
                        for cluster in data['results']['cluster']:
                            if 'result' in cluster:
                                for result in cluster['result']:
                                    patent_info = self._extract_patent_info(result)
                                    if patent_info:
                                        patents.append(patent_info)
                                        if len(patents) >= max_results:
                                            break
                            if len(patents) >= max_results:
                                break
                    
                    logging.info(f"[Patents] ✅ Encontradas {len(patents)} patentes reales")
                    return patents
                    
                except Exception as e:
                    logging.warning(f"[Patents] ⚠️ Error procesando respuesta de Google Patents: {e}")
                    return []
            else:
                logging.warning(f"[Patents] ⚠️ Error en búsqueda de patentes: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            logging.error(f"[Patents] ❌ Error en búsqueda real de patentes: {e}")
            return []

    def analyze_ideas_batch_competitor(self, ideas_list, context="", extra_sources="", max_workers=4):
        """
        Analiza una lista de ideas en paralelo usando ThreadPoolExecutor.
        Devuelve un dict con 'ideas' (análisis individuales sin EXEC_SUMMARY) y 'executive_summary' (resumen global).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        print(f"🟢 [CompetitorAnalysis] Iniciando análisis batch de {len(ideas_list)} ideas...")
        
        # 1. Analizar cada idea individualmente (SIN EXEC_SUMMARY)
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self._analyze_idea_without_exec_summary, idea, context, extra_sources): idx
                for idx, idea in enumerate(ideas_list)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"error": str(e)}
                results[idx] = result
        
        # Ordenar resultados
        ideas_analyzed = [results[i] for i in range(len(ideas_list))]
        
        # 2. Generar resumen ejecutivo GLOBAL
        print("🟢 [CompetitorAnalysis] Generando resumen ejecutivo global...")
        global_summary = self._generate_global_executive_summary(ideas_list, ideas_analyzed, context)
        
        return {
            'ideas': ideas_analyzed,
            'executive_summary': global_summary,
            'total_ideas': len(ideas_list),
            'context': context
        }

    def _analyze_idea_without_exec_summary(self, idea, context, extra_sources=""):
        """
        Analiza una idea individual SIN generar resumen ejecutivo (será global).
        """
        try:
            # Usar el análisis existente pero excluir EXEC_SUMMARY
            meta = {'score': idea.get('score', 0)} if isinstance(idea, dict) else {'score': 0}
            full_analysis = self.generate_ai_only_competition_report(idea, context, meta, extra_sources)
            
            # Remover EXEC_SUMMARY si existe
            if 'EXEC_SUMMARY' in full_analysis:
                del full_analysis['EXEC_SUMMARY']
            
            # Añadir título de la idea para referencia y datos originales
            idea_text = idea.get('idea') if isinstance(idea, dict) and 'idea' in idea else str(idea)
            title = idea.get('title', '') if isinstance(idea, dict) else ''
            if not title and idea_text:
                # 🔧 EXTRAER TÍTULO CON LIMPIEZA MEJORADA
                first_line = idea_text.split('\n')[0].strip()
                import re
                
                # Paso 1: Limpiar patrones duplicados como "Idea 1: Idea 1:"
                cleaned_line = re.sub(r'^(idea\s*\d*[\.:]\s*){2,}', '', first_line, flags=re.IGNORECASE)
                
                # Paso 2: Limpiar un prefijo simple "Idea X:" si queda
                cleaned_line = re.sub(r'^idea\s*\d*[\.:]\s*', '', cleaned_line, flags=re.IGNORECASE)
                
                # Paso 3: Limpiar espacios extra
                cleaned_line = cleaned_line.strip()
                
                if len(cleaned_line) > 10:
                    title = cleaned_line[:100] + ('...' if len(cleaned_line) > 100 else '')
                else:
                    # Si la primera línea es muy corta, tomar más palabras pero limpias
                    full_text_clean = re.sub(r'\b(idea\s*\d*[\.:]\s*){1,}', '', idea_text, flags=re.IGNORECASE)
                    words = full_text_clean.split()[:10]
                    title = ' '.join(words).strip()
                    if len(title) > 100:
                        title = title[:100] + '...'
            
            full_analysis['idea_title'] = title
            full_analysis['idea_text'] = idea_text
            full_analysis['original_idea_data'] = idea  # Preservar datos originales
            
            return full_analysis
            
        except Exception as e:
            print(f"❌ Error analizando idea individual: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def _generate_global_executive_summary(self, ideas_list, ideas_analyzed, context):
        """
        Genera un resumen ejecutivo global para todas las ideas analizadas.
        """
        try:
            # Preparar información de todas las ideas para el resumen global
            ideas_info = []
            
            for i, (idea_original, idea_analysis) in enumerate(zip(ideas_list, ideas_analyzed), 1):
                idea_text = idea_original.get('idea') if isinstance(idea_original, dict) and 'idea' in idea_original else str(idea_original)
                title = idea_original.get('title', '') if isinstance(idea_original, dict) else ''
                
                if not title and idea_text:
                    # 🔧 EXTRAER TÍTULO CON LIMPIEZA MEJORADA (para resumen ejecutivo)
                    first_line = idea_text.split('\n')[0].strip()
                    import re
                    
                    # Paso 1: Limpiar patrones duplicados como "Idea 1: Idea 1:"
                    cleaned_line = re.sub(r'^(idea\s*\d*[\.:]\s*){2,}', '', first_line, flags=re.IGNORECASE)
                    
                    # Paso 2: Limpiar un prefijo simple "Idea X:" si queda
                    cleaned_line = re.sub(r'^idea\s*\d*[\.:]\s*', '', cleaned_line, flags=re.IGNORECASE)
                    
                    # Paso 3: Limpiar espacios extra
                    cleaned_line = cleaned_line.strip()
                    
                    if len(cleaned_line) > 10:
                        title = cleaned_line[:80] + ('...' if len(cleaned_line) > 80 else '')
                    else:
                        # Si la primera línea es muy corta, tomar más palabras pero limpias
                        full_text_clean = re.sub(r'\b(idea\s*\d*[\.:]\s*){1,}', '', idea_text, flags=re.IGNORECASE)
                        words = full_text_clean.split()[:10]
                        title = ' '.join(words).strip()
                        if len(title) > 80:
                            title = title[:80] + '...'
                
                ideas_info.append({
                    'numero': i,
                    'titulo': title,
                    'idea': idea_text[:300] + ('...' if len(idea_text) > 300 else ''),
                    'analysis': idea_analysis
                })
            
            # Crear prompt para resumen ejecutivo global
            ideas_summary = "\n\n".join([
                f"IDEA {info['numero']}: {info['titulo']}\n{info['idea']}"
                for info in ideas_info
            ])
            
            user_context = (context or "").strip()
            if user_context:
                contexto_usuario = self.SENER_CONTEXT + "\n\n" + user_context
            else:
                contexto_usuario = self.SENER_CONTEXT
            
            prompt = f"""
            Genera un resumen ejecutivo CORTO Y DIRECTO para el análisis competitivo de {len(ideas_list)} ideas innovadoras.

            CONTEXTO DE SENER:
            {contexto_usuario}

            IDEAS ANALIZADAS:
            {ideas_summary}

            INSTRUCCIONES ESTRICTAS:
            - MÁXIMO 300 palabras total
            - Máximo 3 párrafos cortos y concisos
            - Ve DIRECTO al grano, sin relleno
            - Incluye SOLO los insights más importantes
            - NO repitas información de análisis individuales
            - Lenguaje ejecutivo: claro, decisivo, accionable

            ESTRUCTURA OBLIGATORIA:
            1. Párrafo 1 (100 palabras): Evaluación general del portafolio - ¿Qué representan estas ideas para Sener?
            2. Párrafo 2 (100 palabras): Oportunidades competitivas principales y posicionamiento estratégico
            3. Párrafo 3 (100 palabras): Recomendaciones ejecutivas inmediatas y próximos pasos críticos

            Enfócate en decisiones ejecutivas, no en análisis descriptivo.
            No empieces con "Resumen Ejecutivo: ..."
            """
            
            response = self.openai_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "Eres un consultor estratégico senior especializado en análisis competitivo y estrategia corporativa. Siempre eres conciso y directo."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            global_summary = response.choices[0].message.content.strip()
            
            print("✅ [CompetitorAnalysis] Resumen ejecutivo global generado correctamente")
            
            return {
                'texto': global_summary,
                'total_ideas': len(ideas_list),
                'fecha_generacion': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error generando resumen ejecutivo global: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'texto': "Error al generar resumen ejecutivo global. Se recomienda consultar los análisis individuales.",
                'error': str(e)
            }

    def generate_ai_only_competition_report(self, idea, context, meta, extra_sources=""):
        print("🟢 [CompetitorAnalysis] Iniciando generación de informe AI-only para competencia...")
        idea_raw = idea.get('idea') if isinstance(idea, dict) and 'idea' in idea else str(idea)
        analysis_full = idea.get('analysis') if isinstance(idea, dict) and 'analysis' in idea else ""
        idea_brief, sector_keywords = self._get_brief_and_keywords(idea_raw, analysis_full)
        user_context = (context or "").strip()
        if user_context:
            contexto_usuario = self.SENER_CONTEXT + "\n\n" + user_context
        else:
            contexto_usuario = self.SENER_CONTEXT
        shared_inputs = {
            'idea_brief': idea_brief,
            'sector_keywords': sector_keywords,
            'score': meta.get('score'),
            'unidad_negocio': meta.get('unidad_negocio'),
            'idioma': meta.get('idioma', 'es'),
            'contexto_usuario': contexto_usuario,
            'analysis_full': analysis_full or "",
            'extra_sources': extra_sources or ""
        }
        section_map = [
            'COMPETITOR_MAPPING',
            'BENCHMARK_MATRIX',
            'TECH_IP_LANDSCAPE',
            'MARKET_ANALYSIS',
            'SWOT_POSITIONING',
            'REGULATORY_ESG_RISK'
        ]
        report_dict = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # 🔧 CRITICAL FIX: Process COMPETITOR_MAPPING first, then BENCHMARK_MATRIX with extracted competitors
        # ✅ BENCHMARK_MATRIX EXCLUDED from first phase to avoid double processing
        section_map_first_phase = [
            'COMPETITOR_MAPPING',
            'TECH_IP_LANDSCAPE', 
            'MARKET_ANALYSIS',
            'SWOT_POSITIONING',
            'REGULATORY_ESG_RISK'
        ]
        print(f"🚨🚨🚨 [DEBUG-FASE1] Secciones FASE 1 (SIN BENCHMARK): {section_map_first_phase}")
        
        # PHASE 1: Extract all sections EXCEPT BENCHMARK_MATRIX
        def extract_structured(section_id):
            try:
                # Prompt reforzado: SOLO datos estructurados, sin texto ni tablas Markdown.
                datos = self._extract_section_data_llm(section_id, shared_inputs, report_dict)
                
                # ✅ VALIDACIÓN MEJORADA: Verificar calidad de datos extraídos
                if not datos:
                    print(f"⚠️ [CompetitorAnalysis] Datos vacíos para {section_id}, generando estructura básica")
                    datos = self._generate_default_structure(section_id)
                elif isinstance(datos, dict):
                    # Verificar si contiene datos útiles o solo mensajes de error
                    if 'aviso' in datos or 'error' in datos:
                        print(f"⚠️ [CompetitorAnalysis] Datos con aviso/error para {section_id}, intentando extracción básica")
                        datos = self._generate_default_structure(section_id)
                    elif not any(datos.values()):
                        print(f"⚠️ [CompetitorAnalysis] Datos estructurados vacíos para {section_id}, generando estructura básica")
                        datos = self._generate_default_structure(section_id)
                    else:
                        print(f"✅ [CompetitorAnalysis] Datos estructurados válidos extraídos para {section_id}")
                else:
                    print(f"⚠️ [CompetitorAnalysis] Formato de datos inesperado para {section_id}, generando estructura básica")
                    datos = self._generate_default_structure(section_id)
                    
            except Exception as e:
                print(f"❌ [CompetitorAnalysis] Error extrayendo datos para {section_id}: {e}")
                traceback.print_exc()
                # ✅ GENERAR ESTRUCTURA BÁSICA EN LUGAR DE MENSAJE DE ERROR
                datos = self._generate_default_structure(section_id)
                
            return section_id, datos

        # 1.1 Extract first phase sections in parallel
        print("🔄 [CompetitorAnalysis] FASE 1: Procesando secciones base...")
        with ThreadPoolExecutor(max_workers=min(5, self.max_workers)) as executor:
            futures = {executor.submit(extract_structured, section_id): section_id for section_id in section_map_first_phase}
            datos_dict = {}
            for future in as_completed(futures):
                section_id, datos = future.result()
                datos_dict[section_id] = datos
                # 🚨 CRITICAL: Add to report_dict immediately for BENCHMARK_MATRIX access
                report_dict[section_id] = {'datos': datos, 'texto': ''}

        # 1.2 Now extract BENCHMARK_MATRIX with COMPETITOR_MAPPING data available
        print("🔄 [CompetitorAnalysis] FASE 2: Procesando BENCHMARK_MATRIX con competidores específicos...")
        print(f"🚨🚨🚨 [DEBUG-FASE2] report_dict keys antes de BENCHMARK: {list(report_dict.keys())}")
        
        try:
            print(f"🚨🚨🚨 [DEBUG-FASE2] Llamando _extract_section_data_llm('BENCHMARK_MATRIX', shared_inputs, report_dict)")
            benchmark_datos = self._extract_section_data_llm('BENCHMARK_MATRIX', shared_inputs, report_dict)
            print(f"🚨🚨🚨 [DEBUG-FASE2] Resultado: {type(benchmark_datos)}, keys: {list(benchmark_datos.keys()) if isinstance(benchmark_datos, dict) else 'No es dict'}")
            
            if not benchmark_datos:
                print(f"⚠️ [CompetitorAnalysis] Datos vacíos para BENCHMARK_MATRIX, generando estructura básica")
                benchmark_datos = self._generate_default_structure('BENCHMARK_MATRIX')
            elif isinstance(benchmark_datos, dict):
                if 'aviso' in benchmark_datos or 'error' in benchmark_datos:
                    print(f"⚠️ [CompetitorAnalysis] Datos con aviso/error para BENCHMARK_MATRIX: {benchmark_datos}")
                    print(f"🚨🚨🚨 [DEBUG-FASE2] FORZANDO USO DE DEFAULT STRUCTURE")
                    benchmark_datos = self._generate_default_structure('BENCHMARK_MATRIX')
                elif not any(benchmark_datos.values()):
                    print(f"⚠️ [CompetitorAnalysis] Datos estructurados vacíos para BENCHMARK_MATRIX, generando estructura básica")
                    benchmark_datos = self._generate_default_structure('BENCHMARK_MATRIX')
                else:
                    print(f"✅ [CompetitorAnalysis] Datos estructurados válidos extraídos para BENCHMARK_MATRIX")
                    print(f"🚨🚨🚨 [DEBUG-FASE2] Datos válidos: primeros 200 chars = {str(benchmark_datos)[:200]}")
            else:
                print(f"⚠️ [CompetitorAnalysis] Formato de datos inesperado para BENCHMARK_MATRIX: {type(benchmark_datos)}")
                benchmark_datos = self._generate_default_structure('BENCHMARK_MATRIX')
        except Exception as e:
            print(f"❌ [CompetitorAnalysis] Error extrayendo datos para BENCHMARK_MATRIX: {e}")
            traceback.print_exc()
            benchmark_datos = self._generate_default_structure('BENCHMARK_MATRIX')
            
        datos_dict['BENCHMARK_MATRIX'] = benchmark_datos
        report_dict['BENCHMARK_MATRIX'] = {'datos': benchmark_datos, 'texto': ''}

        # 2. Redactar texto explicativo profesional en paralelo (sin recomendaciones ni conclusiones)
        print("🔄 [CompetitorAnalysis] FASE 3: Redactando textos explicativos...")
        section_map_complete = section_map_first_phase + ['BENCHMARK_MATRIX']
        
        def redactar_explicativo(section_id):
            datos = datos_dict[section_id]
            # Prompt reforzado: SOLO análisis profesional, sin tablas, sin referencias en bruto, sin títulos internos.
            custom_instruction = (
                "Redacta un texto explicativo profesional, extenso y consultor para la sección, usando SOLO los datos estructurados extraídos a continuación. "
                "NO incluyas recomendaciones ni conclusiones finales. NO repitas puntos ni mezcles información. NO inventes nada. "
                "NO incluyas tablas, títulos internos, ni referencias en bruto. NO incluyas ningún bloque de tabla ni referencias en el texto. "
                "El texto debe ser lo más extenso y profesional posible, con análisis profundo, contexto sectorial, implicaciones estratégicas, riesgos y oportunidades, pero SOLO sobre los datos extraídos."
            )
            try:
                texto = self._redact_section_llm(section_id, shared_inputs, datos, report_dict, custom_instruction=custom_instruction)
                if not texto or not texto.strip():
                    texto = "[No se pudo generar análisis profesional para esta sección. Consulte fuentes primarias.]"
                print(f"✅ [CompetitorAnalysis] Texto explicativo redactado para {section_id}")
            except Exception as e:
                print(f"❌ [CompetitorAnalysis] Error redactando texto para {section_id}: {e}")
                traceback.print_exc()
                texto = "[Error al redactar sección]"
            return section_id, texto
            
        with ThreadPoolExecutor(max_workers=min(6, self.max_workers)) as executor:
            futures = {executor.submit(redactar_explicativo, section_id): section_id for section_id in section_map_complete}
            textos_dict = {}
            for future in as_completed(futures):
                section_id, texto = future.result()
                textos_dict[section_id] = texto

        # 3. Montar el informe final
        for section_id in section_map_complete:
            report_dict[section_id] = {
                'datos': datos_dict.get(section_id, {}),
                'texto': textos_dict.get(section_id, "")
            }

        # --- EXEC_SUMMARY comentado - será generado globalmente ---
        # NOTA: El resumen ejecutivo se genera ahora a nivel global para todas las ideas
        print("ℹ️ [CompetitorAnalysis] Resumen ejecutivo será generado globalmente.")
        report_dict['metadatos'] = {
            "origen": "AI-only (scraping desactivado)",
            "fecha_generacion": datetime.now().isoformat(),
            "modelo": self.deployment_name if hasattr(self, 'deployment_name') else "openai",
            "secciones_generadas": list(report_dict.keys())
        }
        report_dict = fill_empty_sections(report_dict)
        # --- MEJORA: asegurar que todas las secciones sean homogéneas para PDF ---
        report_dict = _coerce_sections_for_pdf(report_dict)
        print("🎉 [CompetitorAnalysis] Informe AI-only generado correctamente.")
        return report_dict

    def _extract_text_from_pdf(self, url_or_path):
        """
        Extrae texto de un PDF desde una URL o path local usando pdf_processor_module.extract_text_from_pdf.
        """
        import tempfile
        import requests
        from pdf_processor_module import extract_text_from_pdf
        try:
            if url_or_path.startswith("http"):
                # Descargar PDF a un archivo temporal
                resp = requests.get(url_or_path, timeout=15)
                resp.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
                text = extract_text_from_pdf(tmp_path)
                return text or ""
            else:
                # Path local
                return extract_text_from_pdf(url_or_path) or ""
        except Exception as e:
            print(f"❌ Error extrayendo texto de PDF: {e}")
            return ""

    def generate_llm_draft(self, idea: Dict[str, Any], contexto_usuario: str = "") -> Dict[str, Any]:
        """
        Llama al LLM para generar el informe completo, sección por sección, con posibles scraping_requests.
        """
        meta = {"fecha": datetime.now().isoformat()}
        # Aquí puedes usar la lógica de generate_ai_only_competition_report, pero asegurando que cada sección puede devolver 'scraping_requests'.
        return self.generate_ai_only_competition_report(idea, contexto_usuario, meta)

    def analyze_idea(self, idea: Dict[str, Any], contexto_usuario: str = "") -> Dict[str, Any]:
        print("🟢 [CompetitorAnalysis] Iniciando análisis de idea...")
        import json
        from urllib.parse import urlparse
        def is_valid_url(url):
            try:
                parsed = urlparse(url)
                return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
            except Exception:
                return False
        # --- Paso 1: Generar borrador LLM completo (con textos profesionales) ---
        borrador = self.generate_llm_draft(idea, contexto_usuario)
        # Log borrador para depuración
        try:
            with open("output/last_llm_draft.json", "w", encoding="utf-8") as f:
                json.dump(borrador, f, indent=2, ensure_ascii=False)
            print("💾 [CompetitorAnalysis] Borrador LLM guardado en output/last_llm_draft.json")
        except Exception as e:
            print(f"[WARN] No se pudo guardar borrador LLM: {e}")
        scraping_requests = []
        # Paso 2: buscar scraping_requests en el borrador o en sus secciones
        if isinstance(borrador, dict):
            if 'scraping_requests' in borrador and isinstance(borrador['scraping_requests'], list):
                scraping_requests = borrador['scraping_requests']
            else:
                for v in borrador.values():
                    if isinstance(v, dict) and 'scraping_requests' in v and isinstance(v['scraping_requests'], list):
                        scraping_requests.extend(v['scraping_requests'])
        # --- NUEVO: detectar URLs en los datos extraídos y añadir scraping_requests automáticamente ---
        def find_urls(obj):
            urls = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.lower() in ("url", "fuente", "scrape_url") and isinstance(v, str) and is_valid_url(v):
                        urls.append(v)
                    else:
                        urls.extend(find_urls(v))
            elif isinstance(obj, list):
                for item in obj:
                    urls.extend(find_urls(item))
            return urls
        extra_urls = find_urls(borrador)
        for url in extra_urls:
            scraping_requests.append({'url': url, 'type': 'auto'})
        # Validar URLs antes de scrappear
        scraping_requests = [req for req in scraping_requests if isinstance(req, dict) and is_valid_url(req.get('url',''))]
        print(f"🔍 [CompetitorAnalysis] Scraping requests detectados: {len(scraping_requests)}")
        # Log scraping_requests
        try:
            with open("output/last_scraping_requests.json", "w", encoding="utf-8") as f:
                json.dump(scraping_requests, f, indent=2, ensure_ascii=False)
            print("💾 [CompetitorAnalysis] Scraping requests guardados en output/last_scraping_requests.json")
        except Exception as e:
            print(f"[WARN] No se pudo guardar scraping_requests: {e}")
        if scraping_requests:
            try:
                from targeted_scraper import scrape_targets
                from integrator import merge_llm_and_data
                print("🟠 [CompetitorAnalysis] Ejecutando scraping puntual...")
                datos_scrapeados = scrape_targets(scraping_requests)
                print("✅ [CompetitorAnalysis] Scraping completado.")
                # Log datos_scrapeados
                try:
                    with open("output/last_scraped_data.json", "w", encoding="utf-8") as f:
                        json.dump(datos_scrapeados, f, indent=2, ensure_ascii=False)
                    print("💾 [CompetitorAnalysis] Datos scrapeados guardados en output/last_scraped_data.json")
                except Exception as e:
                    print(f"[WARN] No se pudo guardar datos_scrapeados: {e}")
                try:
                    informe_final = merge_llm_and_data(borrador, datos_scrapeados)
                    print("✅ [CompetitorAnalysis] Integración de datos scrapeados completada.")
                    # Log informe_final
                    try:
                        with open("output/last_integrated_report.json", "w", encoding="utf-8") as f:
                            json.dump(informe_final, f, indent=2, ensure_ascii=False)
                        print("💾 [CompetitorAnalysis] Informe final guardado en output/last_integrated_report.json")
                    except Exception as e:
                        print(f"[WARN] No se pudo guardar informe_final: {e}")
                    return informe_final
                except Exception as e:
                    print(f"[WARN] Integración scraping+LLM falló: {e}")
                    traceback.print_exc()
                    print("🟢 [CompetitorAnalysis] Scraping fallido, devolviendo borrador LLM-only (con textos profesionales).")
                    return borrador
            except Exception as e:
                print(f"[WARN] Scraping falló: {e}")
                traceback.print_exc()
                print("🟢 [CompetitorAnalysis] Scraping fallido, devolviendo borrador LLM-only (con textos profesionales).")
                return borrador
        else:
            print("🟢 [CompetitorAnalysis] No se requieren scraping requests. Devolviendo borrador LLM-only (con textos profesionales).")
            return borrador

    def _generate_default_structure(self, section_id):
        """
        Genera estructuras de datos básicas pero válidas cuando el LLM falla en la extracción.
        ✅ NUEVA FUNCIÓN: Alternativa a mensajes de error genéricos
        """
        import json
        
        defaults = {
            'COMPETITOR_MAPPING': {
                "competidores_directos": [
                    {
                        "nombre": "Análisis específico pendiente",
                        "pais": "Global",
                        "sector": "Ingeniería y construcción",
                        "tamano": "Mediana",
                        "descripcion": "Requiere investigación específica del sector",
                        "website": "Pendiente de identificación"
                    }
                ],
                "competidores_indirectos": [
                    {
                        "nombre": "Evaluación de mercado pendiente",
                        "pais": "Global",
                        "sector": "Tecnología e infraestructura",
                        "tamano": "Grande",
                        "descripcion": "Requiere análisis detallado del ecosistema competitivo",
                        "website": "En proceso de identificación"
                    }
                ],
                "emergentes": [
                    {
                        "nombre": "Startups del sector pendientes de identificar",
                        "pais": "Múltiples regiones",
                        "sector": "Innovación tecnológica",
                        "tamano": "Pequeña",
                        "descripcion": "Monitoreo de empresas emergentes en desarrollo",
                        "website": "Búsqueda en bases de datos especializadas"
                    }
                ]
            },
            'BENCHMARK_MATRIX': {
                "tabla": [
                    {
                        "nombre": "Análisis comparativo en desarrollo",
                        "pais": "Global",
                        "sector": "Ingeniería",
                        "tamano": "Mediana",
                        "enfoque_estrategico": "Requiere estudio específico de estrategias competitivas",
                        "modelo_negocio": "Evaluación de modelos en proceso",
                        "diferenciador_clave": "Identificación de ventajas competitivas pendiente"
                    }
                ],
                "analisis_cualitativo": {
                    "gaps_identificados": [
                        "Análisis de brechas competitivas en desarrollo",
                        "Identificación de oportunidades de diferenciación pendiente"
                    ],
                    "oportunidades_sener": [
                        "Evaluación de posicionamiento estratégico en proceso",
                        "Análisis de capacidades diferenciadas de Sener en desarrollo"
                    ]
                }
            },
            'TECH_IP_LANDSCAPE': {
                "patentes_destacadas": [
                    {
                        "titulo": "Tecnologías del sector específico",
                        "numero_patente": "Disponible en bases de datos especializadas",
                        "titular": "Empresas líderes del sector",
                        "año": "2020-2024",
                        "pais": "Global",
                        "descripcion": "Análisis de patentes relevantes para el área tecnológica específica de la idea",
                        "relevancia_competitiva": "Evaluación de impacto tecnológico en desarrollo",
                        "url": "Disponible en Google Patents y bases de datos especializadas"
                    }
                ],
                "publicaciones_clave": [
                    {
                        "titulo": "Investigación académica del sector",
                        "autores": "Investigadores especializados en el área",
                        "revista": "Revistas científicas del sector específico",
                        "año": "2020-2024",
                        "tipo": "Artículo de investigación",
                        "resumen": "Estado del arte científico relacionado con la tecnología de la idea",
                        "relevancia_tecnologica": "Contribución al avance del conocimiento sectorial",
                        "url": "Disponible en bases de datos académicas especializadas"
                    }
                ],
                "gaps_tecnologicos": [
                    {
                        "area_tecnologica": "Área específica de la idea analizada",
                        "descripcion_gap": "Limitaciones tecnológicas identificadas en el mercado actual",
                        "impacto_competitivo": "Efecto en la competitividad del sector",
                        "oportunidad_sener": "Potencial para Sener de abordar estas limitaciones tecnológicas"
                    }
                ],
                "tendencias_emergentes": [
                    {
                        "tecnologia": "Tecnologías emergentes del sector específico",
                        "estado_madurez": "Desarrollo",
                        "potencial_disruptivo": "Medio",
                        "plazo_adopcion": "3-5 años"
                    }
                ]
            },
            'MARKET_ANALYSIS': {
                "TAM_2025": 0,  # Se requiere investigación específica
                "CAGR_2025_2030": 0,  # Pendiente de análisis sectorial
                "segmentos": [
                    "Segmentación de mercado pendiente de análisis específico"
                ],
                "geografias": [
                    "Análisis geográfico en desarrollo"
                ],
                "drivers": [
                    "Factores de crecimiento del sector en identificación"
                ],
                "restrictores": [
                    "Barreras del mercado en evaluación"
                ],
                "analisis_cualitativo": {
                    "gaps_identificados": [
                        "Vacíos de mercado en proceso de identificación específica",
                        "Análisis de necesidades no cubiertas en desarrollo"
                    ],
                    "oportunidades_sener": [
                        "Evaluación de oportunidades estratégicas para Sener en proceso",
                        "Identificación de ventajas competitivas aplicables en desarrollo"
                    ]
                }
            },
            'SWOT_POSITIONING': {
                "swot": {
                    "fortalezas": [
                        "Experiencia de Sener en ingeniería aplicable al sector específico",
                        "Capacidades técnicas y tecnológicas de la organización",
                        "Trayectoria en proyectos de alta complejidad técnica"
                    ],
                    "debilidades": [
                        "Evaluación de limitaciones específicas para esta idea en proceso",
                        "Análisis de gaps de capacidades sectoriales en desarrollo",
                        "Identificación de áreas de mejora competitiva pendiente"
                    ],
                    "oportunidades": [
                        "Tendencias del mercado favorables al desarrollo de la idea",
                        "Sinergias con capacidades existentes de Sener en el sector",
                        "Potencial de crecimiento del mercado específico"
                    ],
                    "amenazas": [
                        "Análisis de riesgos competitivos en evaluación",
                        "Identificación de barreras regulatorias en proceso",
                        "Evaluación de factores de riesgo del sector en desarrollo"
                    ]
                },
                "mapa_posicionamiento": {
                    "eje_x": "Especialización técnica vs Generalización",
                    "eje_y": "Tamaño de mercado vs Nicho especializado",
                    "comentario": "Posicionamiento estratégico de la idea en análisis"
                }
            },
            'REGULATORY_ESG_RISK': {
                "normativas_clave": [
                    "Análisis normativo del sector en desarrollo"
                ],
                "certificaciones": [
                    "Requisitos de certificación en evaluación"
                ],
                "riesgos": [
                    "Identificación de riesgos regulatorios en proceso"
                ],
                "oportunidades_ESG": [
                    "Evaluación de oportunidades de sostenibilidad en desarrollo"
                ]
            },
            'STRATEGIC_ROADMAP': {
                "acciones_90_dias": [
                    "Planificación estratégica inicial en desarrollo"
                ],
                "acciones_12_meses": [
                    "Roadmap de mediano plazo en elaboración"
                ],
                "acciones_36_meses": [
                    "Estrategia de largo plazo en definición"
                ],
                "KPIs_clave": [
                    "Definición de métricas de éxito en proceso"
                ]
            },
            'APPENDIX': {
                "glosario": {
                    "Análisis competitivo": "Evaluación sistemática del entorno competitivo",
                    "Vigilancia tecnológica": "Monitoreo de avances y tendencias tecnológicas"
                },
                "metodologia": "Análisis basado en información sectorial y capacidades de Sener",
                "limitaciones": "Análisis preliminar que requiere investigación específica adicional"
            }
        }
        
        default_structure = defaults.get(section_id, {})
        print(f"🔄 [CompetitorAnalysis] Generada estructura por defecto para {section_id}")
        return default_structure

    def _extract_patent_info(self, patent_result):
        """
        Extrae información estructurada de un resultado de patente real.
        """
        try:
            patent_info = {}
            
            # Extraer campos básicos
            patent_info['titulo'] = patent_result.get('title', '').strip()
            patent_info['numero_patente'] = patent_result.get('publication_number', '').strip()
            patent_info['titular'] = patent_result.get('assignee', '').strip()
            patent_info['año'] = patent_result.get('publication_date', '').split('-')[0] if patent_result.get('publication_date') else ''
            patent_info['pais'] = patent_result.get('publication_number', '')[:2] if patent_result.get('publication_number') else ''
            patent_info['descripcion'] = patent_result.get('snippet', '').strip()[:200]
            
            # Construir URL de Google Patents
            patent_id = patent_result.get('patent_id', '')
            if patent_id:
                patent_info['url'] = f"https://patents.google.com/{patent_id}"
            
            # Validar que tenemos información mínima
            if patent_info['titulo'] and patent_info['numero_patente']:
                return patent_info
            else:
                return None
                
        except Exception as e:
            import logging
            logging.warning(f"[Patents] ⚠️ Error extrayendo info de patente: {e}")
            return None

    def _redact_section_llm(self, section_id, shared_inputs, datos, report_dict=None, custom_instruction=""):
        """
        Usa el LLM para redactar texto explicativo profesional sobre una sección específica.
        ✅ MEJORADO: Instrucciones específicas por sección
        """
        idea_text = shared_inputs.get('idea_text', '').strip()
        analisis_full = shared_inputs.get('analysis_full', '').strip()
        context_usuario = shared_inputs.get('context_usuario', '').strip()
        
        # ✅ INSTRUCCIONES ESPECÍFICAS POR SECCIÓN
        if section_id == "COMPETITOR_MAPPING":
            prompt_instruction = (
                "Redacta un análisis DESCRIPTIVO del ecosistema competitivo (máximo 350 palabras) para la idea analizada. "
                
                "ENFOQUE DESCRIPTIVO (NO comparativo): "
                "- DESCRIBE qué hace cada competidor y su rol en el ecosistema "
                "- EXPLICA por qué cada empresa es relevante para el sector "
                "- IDENTIFICA las diferentes categorías de competencia (directos, indirectos, emergentes) "
                "- ANALIZA la estructura general del mercado competitivo "
                "- DESCRIBE tendencias y dinámicas del sector "
                
                "CONTENIDO OBLIGATORIO: "
                "- Menciona específicamente CADA empresa de los datos estructurados "
                "- Explica el rol y actividad principal de cada competidor "
                "- Describe la intensidad competitiva del segmento "
                "- Identifica patrones en el ecosistema competitivo "
                
                "FORMATO: Párrafos descriptivos fluidos, sin numeraciones ni comparaciones directas. "
                "ESTILO: Consultor que mapea y describe el panorama competitivo. "
                
                "PROHIBIDO: "
                "- NO hagas comparaciones directas entre empresas (eso va en Benchmarking) "
                "- NO uses '1) COMPETIDORES DIRECTOS', '2) INDIRECTOS' etc. "
                "- NO pongas subtítulos internos "
                "- NO menciones gaps de mercado ni oportunidades (van en Market Analysis) "
                
                "FORMATO: Análisis fluido y natural basado SOLO en los competidores identificados por el LLM. "
                "Menciona de forma natural todos los competidores de los datos estructurados sin ejemplos predefinidos."
            )
        elif section_id == "BENCHMARK_MATRIX":
            prompt_instruction = (
                "Redacta un análisis COMPARATIVO de benchmarking estratégico (máximo 350 palabras) entre los competidores clave. "
                
                "ENFOQUE COMPARATIVO (NO descriptivo): "
                "- COMPARA modelos de negocio entre competidores "
                "- CONTRASTA diferenciadores competitivos únicos "
                "- ANALIZA patrones de especialización vs generalización "
                "- EVALÚA ventajas competitivas relativas "
                "- IDENTIFICA factores críticos de éxito comunes y únicos "
                
                "CONTENIDO OBLIGATORIO: "
                "- Comparaciones directas entre enfoques estratégicos "
                "- Análisis de similitudes y diferencias en modelos de negocio "
                "- Evaluación de ventajas competitivas relativas "
                "- Identificación de patrones de éxito en el sector "
                
                "FORMATO: Párrafos comparativos fluidos, análisis 'versus' y contrastes. "
                "ESTILO: Consultor que compara y evalúa estrategias competitivas. "
                
                "PROHIBIDO TOTALMENTE: "
                "- Descripciones simples de qué hace cada empresa (eso va en Mapa) "
                "- Gaps de mercado u oportunidades para Sener (van en Market Analysis) "
                "- Cifras específicas, números de empleados, ingresos inventados "
                
                "ENFOQUE: Análisis puramente comparativo y estratégico de lo que hacen los competidores. "
                "FORMATO: Párrafos fluidos sin listas numeradas ni formato Markdown. "
                "RESPONDE SIEMPRE EN ESPAÑOL."
            )
        else:
            # Prompt genérico para otras secciones
            prompt_instruction = custom_instruction or (
                "Redacta un texto explicativo profesional, extenso y consultor para la sección, usando SOLO los datos estructurados extraídos a continuación. "
                "NO incluyas recomendaciones ni conclusiones finales. NO repitas puntos ni mezcles información. NO inventes nada. "
                "NO incluyas tablas, títulos internos, ni referencias en bruto. "
                "El texto debe ser lo más extenso y profesional posible, con análisis profundo, contexto sectorial, implicaciones estratégicas, riesgos y oportunidades, pero SOLO sobre los datos extraídos."
            )
        
        prompt = f"""
        INSTRUCCIÓN: {prompt_instruction}

        CONTEXTO DE LA IDEA:
        {idea_text[:800]}

        DATOS EXTRAÍDOS PARA LA SECCIÓN:
        {json.dumps(datos, indent=2, ensure_ascii=False) if isinstance(datos, (dict, list)) else str(datos)[:1000]}

        CONTEXTO ADICIONAL DEL USUARIO:
        {context_usuario[:400] if context_usuario else "No hay contexto adicional."}

        Redacta el análisis profesional solicitado:
        """
        
        try:
            response = self.openai_client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                    {"role": "system", "content": f"Eres un analista estratégico senior especializado en {section_id}. Redactas análisis profesionales concisos y accionables para empresas de ingeniería como Sener."},
                {"role": "user", "content": prompt}
            ],
                temperature=0.6,
                max_tokens=800 if section_id == "COMPETITOR_MAPPING" else 1200,
                timeout=45
                )
            
            texto = response.choices[0].message.content.strip()
            if not texto:
                return f"[No se pudo generar análisis para {section_id}]"
            return texto
            
        except Exception as e:
            print(f"❌ Error redactando sección {section_id}: {e}")
            return f"[Error al generar análisis para {section_id}]"

    def _get_brief_and_keywords(self, idea_raw, analysis_full=None):
        """
        Llama al LLM para obtener un brief y 5-8 palabras clave sectoriales, usando también el análisis completo si existe.
        """
        prompt = (
            "Devuelve SOLO un objeto JSON con dos campos: 'brief' (resumen de la idea en 2-3 frases) y 'keywords' (lista de 5-8 palabras clave sectoriales, en minúsculas, separadas por coma). Nada fuera del JSON.\n\nIDEA:\n" + idea_raw[:800]
        )
        if analysis_full:
            prompt += f"\n\nANALISIS_COMPLETO:\n{analysis_full[:1200]}"
        try:
            resp = self.openai_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "Eres un analista experto en síntesis de ideas y extracción de palabras clave."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.choices[0].message.content)
            brief = data.get('brief', '')
            keywords = data.get('keywords', '')
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]
            return brief, keywords
        except Exception as e:
            print(f"⚠️ Error extrayendo brief/keywords: {e}")
            return idea_raw[:200], []

    # 🆕 NUEVA FUNCIÓN: PRE-FILTRO INTELIGENTE DE FUENTES POR SECCIÓN
    def get_relevant_sources_for_section(self, section_id, extra_sources, idea_brief):
        """
        🧠 PRE-FILTRO INTELIGENTE: El LLM evalúa qué fuentes son relevantes para cada sección específica
        
        Args:
            section_id: ID de la sección (COMPETITOR_MAPPING, TECH_IP_LANDSCAPE, etc.)
            extra_sources: String con fuentes especificadas por el usuario (ej: "Crunchbase, LinkedIn, Patents")
            idea_brief: Resumen de la idea para contexto
            
        Returns:
            String con fuentes relevantes separadas por comas, o string vacío si ninguna es relevante
        """
        print(f"🔍🔍🔍 [PRE-FILTRO] ===== INICIANDO PRE-FILTRO PARA {section_id} =====")
        print(f"🔍🔍🔍 [PRE-FILTRO] extra_sources recibido: '{extra_sources}'")
        print(f"🔍🔍🔍 [PRE-FILTRO] idea_brief: '{idea_brief[:100]}...'")
        
        # 🚫 EXCLUIR BENCHMARK_MATRIX - se nutre del COMPETITOR_MAPPING
        if section_id == "BENCHMARK_MATRIX":
            print(f"🔍🔍🔍 [PRE-FILTRO] ❌ BENCHMARK_MATRIX EXCLUIDO - retornando vacío")
            return ""
        
        if not extra_sources or not extra_sources.strip():
            print(f"🔍🔍🔍 [PRE-FILTRO] ❌ NO HAY FUENTES - retornando vacío")
            return ""
        
        print(f"🔍🔍🔍 [PRE-FILTRO] ✅ FUENTES DETECTADAS - continuando con pre-filtro")
        
        try:
            # Prompt específico para el pre-filtro
            prompt = f"""
TAREA: Evaluar qué fuentes son relevantes para la sección {section_id}.

CONTEXTO DE LA IDEA: {idea_brief}

FUENTES DISPONIBLES: {extra_sources}

SECCIÓN A ANALIZAR: {section_id}

INSTRUCCIONES:
1. Evalúa SOLO si cada fuente aporta valor específico para la sección {section_id}
2. Si una fuente NO es relevante para esta sección específica, NO la incluyas
3. Responde ÚNICAMENTE con las fuentes relevantes separadas por comas
4. Si ninguna fuente es relevante, responde con "NINGUNA"

EJEMPLO DE RESPUESTA: "Crunchbase, LinkedIn" o "NINGUNA"

RESPUESTA:"""

            print(f"🔍🔍🔍 [PRE-FILTRO] 📝 PROMPT GENERADO:")
            print(f"🔍🔍🔍 [PRE-FILTRO] {prompt}")
            print(f"🔍🔍🔍 [PRE-FILTRO] 🚀 LLAMANDO AL LLM...")
            
            response = self.openai_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "Eres un experto en análisis competitivo. Evalúa únicamente la relevancia de fuentes para secciones específicas."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            if not response or not response.choices or not response.choices[0].message:
                print(f"🔍🔍🔍 [PRE-FILTRO] ❌ RESPUESTA LLM VACÍA")
                return ""
            
            raw_response = response.choices[0].message.content.strip()
            print(f"🔍🔍🔍 [PRE-FILTRO] 📥 RESPUESTA RAW LLM: '{raw_response}'")
            
            # 🔧 SOLUCIÓN COMILLAS: Limpiar comillas de la respuesta del LLM
            # Quitar comillas dobles que rodean toda la respuesta
            if raw_response.startswith('"') and raw_response.endswith('"'):
                raw_response = raw_response[1:-1]
                print(f"🔍🔍🔍 [PRE-FILTRO] 🔧 COMILLAS ELIMINADAS: '{raw_response}'")
            
            if raw_response.upper() == "NINGUNA" or not raw_response:
                print(f"🔍🔍🔍 [PRE-FILTRO] ❌ LLM DICE 'NINGUNA' - retornando vacío")
                return ""
            
            # Procesar la respuesta
            relevant_sources = [s.strip() for s in raw_response.split(',') if s.strip()]
            print(f"🔍🔍🔍 [PRE-FILTRO] 🔄 FUENTES PROCESADAS: {relevant_sources}")
            
            # Validar que las fuentes están en la lista original
            if relevant_sources:
                extra_sources_list = [s.strip() for s in extra_sources.split(',')]
                extra_sources_lower = [s.lower() for s in extra_sources_list]
                
                print(f"🔍🔍🔍 [PRE-FILTRO] 🔄 FUENTES ORIGINALES: {extra_sources_list}")
                print(f"🔍🔍🔍 [PRE-FILTRO] 🔄 FUENTES ORIGINALES LOWER: {extra_sources_lower}")
                
                filtered_sources = []
                for source in relevant_sources:
                    # Buscar coincidencias case-insensitive
                    for i, orig_lower in enumerate(extra_sources_lower):
                        if source.lower() == orig_lower:
                            filtered_sources.append(extra_sources_list[i])  # Usar original con mayúsculas
                            print(f"🔍🔍🔍 [PRE-FILTRO] ✅ FUENTE VALIDADA: '{source}' -> '{extra_sources_list[i]}'")
                            break
                    else:
                        print(f"🔍🔍🔍 [PRE-FILTRO] ⚠️ FUENTE NO ENCONTRADA EN ORIGINALES: '{source}'")
                
                result = ", ".join(filtered_sources)
                print(f"🔍🔍🔍 [PRE-FILTRO] 🎉 RESULTADO FINAL: '{result}'")
                return result
            
            print(f"🔍🔍🔍 [PRE-FILTRO] ❌ NO HAY FUENTES RELEVANTES DESPUÉS DE PROCESAR")
            return ""
            
        except Exception as e:
            print(f"🔍🔍🔍 [PRE-FILTRO] ❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""

def fill_empty_sections(report_data):
    """
    Rellena cualquier sección vacía o con 'No disponible' con textos profesionales y extensos por defecto.
    """
    default_texts = {
        'resumen_ejecutivo': "No se encontraron datos específicos, pero en el sector suelen observarse las siguientes tendencias y recomendaciones. Es recomendable realizar un análisis de mercado más profundo y consultar fuentes primarias para obtener información detallada. La digitalización, la sostenibilidad y la eficiencia suelen ser factores clave en la industria. Se recomienda identificar oportunidades de innovación y alianzas estratégicas, así como desarrollar un plan de acción basado en las mejores prácticas del sector.",
        'analisis_mercado': "No se encontraron datos específicos de mercado. Sin embargo, en el sector es habitual observar tendencias como la digitalización, la sostenibilidad y la búsqueda de eficiencia. Se recomienda analizar informes de mercado sectoriales y consultar fuentes especializadas para obtener datos cuantitativos y cualitativos relevantes.",
        'benchmarking': "No se encontraron datos de benchmarking específicos. Se recomienda analizar a los principales actores del sector y comparar tecnologías, modelos de negocio y precios. El benchmarking permite identificar oportunidades de mejora y diferenciarse de la competencia.",
        'vigilancia_tecnologica': "No se encontraron datos de vigilancia tecnológica específicos. Es recomendable consultar bases de datos de patentes y publicaciones científicas para identificar innovaciones relevantes. La vigilancia tecnológica es clave para anticipar tendencias y detectar oportunidades de innovación.",
        'dafo': "No se pudo realizar un análisis DAFO detallado. Sin embargo, en el sector suelen destacarse fortalezas como la innovación, oportunidades en mercados emergentes, debilidades relacionadas con la falta de datos y amenazas como la competencia global y los cambios regulatorios.",
        'recomendaciones': [
            "Se recomienda realizar un análisis de mercado más profundo y consultar fuentes primarias.",
            "Identificar oportunidades de innovación y alianzas estratégicas.",
            "Desarrollar un plan de acción basado en las mejores prácticas del sector.",
            "Implementar un sistema de vigilancia tecnológica continua para anticipar tendencias.",
            "Revisar periódicamente la estrategia competitiva y adaptarse a los cambios del mercado."
        ],
        'conclusion_final': "No se pudo extraer una conclusión final detallada. Se sugiere revisar periódicamente el entorno competitivo y ajustar la estrategia en función de los cambios del mercado. La adaptabilidad y la innovación continua son factores clave para el éxito a largo plazo."
    }
    for key, default in default_texts.items():
        if key not in report_data or not report_data[key] or (isinstance(report_data[key], str) and report_data[key].strip().lower() in ["no disponible.", "no disponible", ""]):
            report_data[key] = default
        elif isinstance(report_data[key], list) and not report_data[key]:
            report_data[key] = default if isinstance(default, list) else [default]
    return report_data

# --- Añadir función de homogeneización de secciones para PDF ---
def _coerce_sections_for_pdf(secciones: dict) -> dict:
    """
    Convierte listas o strings en dicts {'texto': …} para que el generador PDF no falle con .get('texto').
    Si el valor es un dict y ya contiene 'texto', lo deja tal cual.
    Si es una lista de dicts grande, la convierte en tabla (cabeceras + filas).
    Si la lista es muy grande (>10), la trunca y añade aviso.
    """
    import json
    coerced = {}
    for k, v in secciones.items():
        if k == 'metadatos':
            continue
        if isinstance(v, dict):
            if 'texto' in v:
                coerced[k] = v
            else:
                coerced[k] = v
        elif isinstance(v, list):
            # Detectar lista de dicts homogénea
            if v and all(isinstance(el, dict) for el in v):
                # Construir tabla: cabeceras = claves comunes
                headers = list({key for d in v for key in d.keys()})
                rows = []
                N = 10
                for el in v[:N]:
                    row = [str(el.get(h, '')) for h in headers]
                    rows.append(row)
                table_str = "\t".join(headers) + "\n" + "\n".join(["\t".join(row) for row in rows])
                if len(v) > N:
                    table_str += f"\n... (mostrando solo los primeros {N} elementos de {len(v)})"
                coerced[k] = {"texto": table_str}
            else:
                joined = "\n".join(
                    json.dumps(el, ensure_ascii=False, indent=2) if isinstance(el, (dict, list))
                    else str(el)
                    for el in v
                )
                coerced[k] = {"texto": joined}
        else:
            coerced[k] = {"texto": str(v)}
    return coerced

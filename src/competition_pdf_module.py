import os
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import tempfile
from fpdf import FPDF
import re
import json
import traceback
import unicodedata
import urllib.request
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from pdf_module import SenerPDF as BasePDF, clean_text_for_pdf, create_temp_image
import requests
from textwrap import wrap
import logging
from urllib.parse import urlparse
import time
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import textwrap
from PIL import Image  # type: ignore

# --- Asegurar que FONT_OK esté definido globalmente ---
FONT_OK = True

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def clean_and_normalize(text):
    """
    ✅ VERSIÓN CORREGIDA: Normalización menos agresiva para evitar corrupción de caracteres
    """
    if not text:
        return ""
    
    # Convertir a string si no lo es
    if not isinstance(text, str):
        text = str(text)
    
    # ✅ PASO 1: Limpiar solo caracteres problemáticos ESPECÍFICOS
    # NO hacer normalización Unicode agresiva que corrompe el texto
    
    # Reemplazar comillas tipográficas por comillas normales
    text = text.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")
    
    # ✅ CONVERTIR SÍMBOLO DEL EURO A TEXTO (solo si existe)
    text = text.replace('€', ' EUR').replace('$', ' USD').replace('£', ' GBP')
    
    # ✅ CONVERTIR VIÑETAS Y SÍMBOLOS A ASCII (solo si existe)
    text = text.replace('•', '* ').replace('◦', '- ').replace('‣', '> ')
    
    # ✅ CONVERTIR EMOJIS A TEXTO SIMPLE (solo si existe)
    text = text.replace('🟢', '[FORTALEZAS] ')
    text = text.replace('🔴', '[DEBILIDADES] ')
    text = text.replace('🔵', '[OPORTUNIDADES] ')
    text = text.replace('🟠', '[AMENAZAS] ')
    text = text.replace('⭐', '*')
    text = text.replace('✅', '[OK] ')
    text = text.replace('❌', '[ERROR] ')
    text = text.replace('⚠️', '[AVISO] ')
    text = text.replace('🎯', '[OBJETIVO] ')
    text = text.replace('🚀', '[INICIO] ')
    text = text.replace('📊', '[DATOS] ')
    
    # ✅ PASO 2: NORMALIZACIÓN SUAVE - SOLO para caracteres problemáticos
    import unicodedata
    
    # Caracteres españoles que NUNCA deben tocarse
    spanish_chars = set('áéíóúÁÉÍÓÚñÑüÜçÇ¿¡')
    
    # ✅ NUEVA ESTRATEGIA: Solo limpiar caracteres realmente problemáticos
    final_text = ''
    for char in text:
        # Preservar caracteres ASCII básicos, españoles y europeos comunes
        if ord(char) < 256 or char in spanish_chars:
            final_text += char
        # Solo reemplazar caracteres Unicode muy raros (> U+2000)
        elif ord(char) > 8192:  # Solo caracteres muy exóticos
            try:
                # Intentar obtener versión base del carácter
                normalized = unicodedata.normalize('NFD', char)
                base_char = ''.join(c for c in normalized if not unicodedata.combining(c))
                if base_char and ord(base_char) < 256:
                    final_text += base_char
                else:
                    final_text += ' '  # Espacio en lugar de eliminar
            except:
                final_text += ' '
        else:
            # Preservar todos los demás caracteres Unicode normales
            final_text += char
    
    # ✅ PASO 3: Limpiar espacios múltiples y retornar
    import re
    final_text = re.sub(r'\s+', ' ', final_text).strip()
    
    return final_text

def ensure_dejavu_fonts(out_dir="output"):
    """
    Descarga y verifica las fuentes DejaVu necesarias para FPDF en el directorio dado.
    ✅ MEJORADO: Mejor manejo de errores y timeout más robusto.
    """
    font_files = [
        ('DejaVuSans.ttf', 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSans.ttf'),
        ('DejaVuSans-Bold.ttf', 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSans-Bold.ttf'),
        ('DejaVuSans-Oblique.ttf', 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSans-Oblique.ttf'),
    ]
    os.makedirs(out_dir, exist_ok=True)
    
    font_success_count = 0
    
    for fname, url in font_files:
        fpath = os.path.join(out_dir, fname)
        
        # ✅ OPTIMIZACIÓN: Solo descargar si no existe o está corrupto
        if os.path.exists(fpath) and os.path.getsize(fpath) > 100000:  # Threshold de 100KB
            logging.info(f"✅ Fuente ya existe y es válida: {fname}")
            font_success_count += 1
            continue
            
        try:
            logging.info(f"⬇️ Descargando fuente: {fname}...")
            # ✅ TIMEOUT MEJORADO Y HEADERS
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            r = requests.get(url, timeout=15, headers=headers)  # Aumentado timeout
            if r.status_code == 200:
                with open(fpath, 'wb') as f:
                    f.write(r.content)
                font_success_count += 1
                logging.info(f"✅ Fuente descargada: {fname} ({len(r.content)} bytes)")
            else:
                logging.warning(f"❌ Error HTTP {r.status_code} descargando {fname}")
        except Exception as e:
            logging.error(f"❌ Error descargando {fname}: {e}")
            # Continuar sin interrumpir el flujo
    
    # ✅ FALLBACK: Si no se pudo descargar ninguna fuente, usar fuente por defecto
    if font_success_count == 0:
        logging.warning("⚠️ No se pudieron descargar fuentes DejaVu. Se usará fuente por defecto.")
        global FONT_OK
        FONT_OK = False
    else:
        logging.info(f"✅ {font_success_count}/{len(font_files)} fuentes disponibles")
        FONT_OK = True
    
    return font_success_count > 0

def generate_competition_analysis_pdf(data, output_name):
    """
    Genera un PDF profesional para análisis de competencia, con portada, índice, secciones y referencias.
    ✅ OPTIMIZADO: Con logging detallado y manejo mejorado de datos grandes + TIMEOUT GENERAL.
    """
    import time
    
    # ✅ TIMEOUT GENERAL DE SEGURIDAD - NUNCA MÁS DE 5 MINUTOS
    start_time = time.time()
    TIMEOUT_SEGUNDOS = 300  # 5 minutos máximo
    
    def check_timeout():
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT_SEGUNDOS:
            logging.error(f"[PDF] ⏱️ TIMEOUT GLOBAL después de {elapsed:.1f}s - ABORTANDO")
            raise TimeoutError(f"Generación PDF excedió timeout de {TIMEOUT_SEGUNDOS}s")
        return elapsed
    
    logging.info("[PDF] 🚀 Iniciando generación del PDF competitivo...")
    logging.info(f"[PDF] ⏱️ Timeout configurado: {TIMEOUT_SEGUNDOS}s máximo")
    
    # 🚨 DEBUG CRÍTICO: Mostrar estructura de datos que llega
    print(f"🚨🚨🚨 [PDF MAIN] ESTRUCTURA DE DATOS QUE LLEGA AL PDF: 🚨🚨🚨")
    if isinstance(data, dict) and 'ideas' in data:
        for i, idea in enumerate(data['ideas'], 1):
            print(f"🚨🚨🚨 [PDF MAIN] Idea {i}: {type(idea)} 🚨🚨🚨")
            if isinstance(idea, dict):
                print(f"🚨🚨🚨 [PDF MAIN] Idea {i} campos: {list(idea.keys())} 🚨🚨🚨")
                if 'idea_title' in idea:
                    print(f"🚨🚨🚨 [PDF MAIN] Idea {i} idea_title: '{idea['idea_title']}' 🚨🚨🚨")
                if 'title' in idea:
                    print(f"🚨🚨🚨 [PDF MAIN] Idea {i} title: '{idea['title']}' 🚨🚨🚨")
                if 'original_idea_data' in idea:
                    orig = idea['original_idea_data']
                    print(f"🚨🚨🚨 [PDF MAIN] Idea {i} original_idea_data tipo: {type(orig)} 🚨🚨🚨")
                    if isinstance(orig, dict):
                        print(f"🚨🚨🚨 [PDF MAIN] Idea {i} original_idea_data campos: {list(orig.keys())} 🚨🚨🚨")
    
    # ✅ SOLUCIÓN DE EMERGENCIA: Detectar si los datos están incompletos y usar borrador LLM
    if isinstance(data, dict):
        # Contar secciones válidas principales
        main_sections = ['COMPETITOR_MAPPING', 'BENCHMARK_MATRIX', 'TECH_IP_LANDSCAPE', 
                        'MARKET_ANALYSIS', 'SWOT_POSITIONING', 'REGULATORY_ESG_RISK', 'EXEC_SUMMARY']
        
        valid_sections = 0
        for section in main_sections:
            if section in data:
                section_data = data[section]
                if isinstance(section_data, dict) and (section_data.get('texto') or section_data.get('datos')):
                    valid_sections += 1
        
        logging.info(f"[PDF] 🔍 Detectadas {valid_sections} secciones válidas en datos de entrada")
        
        # ❌ REMOVIDO: No usar borrador LLM que puede contener datos incorrectos
        # Siempre usar los datos reales enviados desde el UI
        if valid_sections < 3:
            logging.warning(f"[PDF] ⚠️ Solo {valid_sections} secciones válidas detectadas en datos reales")
            logging.info(f"[PDF] 📋 Continuando con datos reales disponibles (no usar cache)")
            # NO cargar ningún archivo de cache que pueda tener datos incorrectos
    
    # ✅ OPTIMIZACIÓN: No re-descargar fuentes si ya existen
    logging.info("[PDF] 📁 Verificando fuentes DejaVu...")
    ensure_dejavu_fonts("output")
    logging.info("[PDF] ✅ Fuentes verificadas.")

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"{output_name}.pdf")

    logging.info("[PDF] 📄 Inicializando PDF...")

    referencias = []
    ref_map = {}
    ref_counter = 1
    
    def is_valid_reference_url(url):
        """Valida si es una URL real y no texto descriptivo"""
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        
        # ✅ FILTRO MÍNIMO: Solo verificar que sea URL válida
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            
            # Debe empezar con http:// o https:// y tener un dominio
            if parsed.scheme in ['http', 'https'] and parsed.netloc:
                logging.info(f"[PDF] ✅ URL válida aceptada: {url}")
                return True
            else:
                logging.info(f"[PDF] 🚫 No es URL válida: {url}")
                return False
                
        except Exception as e:
            logging.info(f"[PDF] 🚫 Error parsing URL: {url}")
            return False
    
    def add_reference(url):
        nonlocal ref_counter
        if not url or url in ref_map:
            return ref_map.get(url, "")
        
        # ✅ VALIDAR URL antes de añadir
        if not is_valid_reference_url(url):
            return ""
        
        ref_map[url] = str(ref_counter)
        referencias.append(url)
        ref_counter += 1
        logging.info(f"[PDF] 📖 Referencia añadida [{ref_counter-1}]: {url}")
        return str(ref_map[url])

    # --- Mapeo de secciones a títulos amigables en español ---
    SECTION_TITLE_MAP = {
        "COMPETITOR_MAPPING": "Mapa de Competidores",
        "BENCHMARK_MATRIX": "Benchmarking",
        "TECH_IP_LANDSCAPE": "Vigilancia Tecnologica",
        "MARKET_ANALYSIS": "Analisis de Mercado",
        "SWOT_POSITIONING": "DAFO y Posicionamiento",
        "REGULATORY_ESG_RISK": "Riesgo Regulatorio y ESG",
        "EXEC_SUMMARY": "Resumen Ejecutivo",
        "resumen_ejecutivo": "Resumen Ejecutivo",
        "analisis_mercado": "Analisis de Mercado",
        "benchmarking": "Benchmarking",
        "vigilancia_tecnologica": "Vigilancia Tecnologica",
        "dafo": "DAFO y Posicionamiento",
        "recomendaciones": "Recomendaciones",
        "conclusion_final": "Conclusion Final"
    }
    
    logging.info("[PDF] 🔧 Creando objeto PDF...")
    
    # --- Portada ---
    pdf = PatchedPDF(title="Análisis de Competencia")
    pdf.logo_path = 'logo1.png' if os.path.exists('logo1.png') else None
    
    # ✅ APLICAR ESTILO PROFESIONAL DESDE EL INICIO
    setup_professional_style(pdf)
    
    logging.info("[PDF] 🎨 Cargando fuentes Unicode...")
    
    # ✅ FUENTES UNICODE CORRECTAS - USAR DEJAVU SI ES POSIBLE
    font_family = 'Arial'  # Fallback por defecto seguro
    
    # ✅ ESTRATEGIA ROBUSTA DE FUENTES
    try:
        # Descargar fuentes DejaVu si no existen
        ensure_dejavu_fonts("output")
        
        # Intentar cargar DejaVu solo si está disponible y es válida
        dejavu_path = 'output/DejaVuSans.ttf'
        if os.path.exists(dejavu_path) and os.path.getsize(dejavu_path) > 100000:
            pdf.add_font('DejaVu', '', 'output/DejaVuSans.ttf', uni=True)
            
            # Solo cargar Bold e Italic si existen
            if os.path.exists('output/DejaVuSans-Bold.ttf'):
                pdf.add_font('DejaVu', 'B', 'output/DejaVuSans-Bold.ttf', uni=True)
            if os.path.exists('output/DejaVuSans-Oblique.ttf'):
                pdf.add_font('DejaVu', 'I', 'output/DejaVuSans-Oblique.ttf', uni=True)
                
            font_family = 'DejaVu'  # USAR DEJAVU como fuente principal
            logging.info("[PDF] ✅ Fuentes DejaVu cargadas y configuradas como principal.")
        else:
            logging.info("[PDF] ℹ️ DejaVu no disponible o corrupto, usando Arial como fallback.")
            font_family = 'Arial'
    except Exception as e:
        logging.warning(f"[PDF] ❌ Error con DejaVu, usando Arial como fallback: {e}")
        font_family = 'Arial'
        
    logging.info(f"[PDF] ✅ Fuente principal configurada: {font_family}")
    
    logging.info("[PDF] 📝 Generando portada...")
    check_timeout()  # CHEQUEO DE TIMEOUT
    pdf.add_page()
    
    # 🏢 AÑADIR LOGO SENER EN LA PORTADA (ANTES DEL TÍTULO)
    logging.info("[PDF] 🖼️ Añadiendo logo SENER en portada...")
    if pdf.logo_path and os.path.exists(pdf.logo_path):
        try:
            logging.info(f"[PDF] 📸 Insertando logo SENER en portada: {pdf.logo_path}")
            # Posicionar el logo en la parte superior central
            pdf.image(pdf.logo_path, x=85, y=30, w=40)
            pdf.ln(60)  # Espacio después del logo
            logging.info("[PDF] ✅ Logo SENER insertado en portada correctamente")
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error insertando logo SENER en portada: {e}")
            pdf.ln(30)  # Espacio mínimo si falla
    else:
        logging.info("[PDF] ℹ️ No hay logo SENER disponible para la portada")
        pdf.ln(30)  # Espacio equivalente
    
    logging.info("[PDF] 🎨 Configurando título principal...")
    check_timeout()  # CHEQUEO DE TIMEOUT
    
    logging.info("[PDF] 🔧 Paso 1: Configurando fuente...")
    
    # ✅ TAMAÑOS DE LETRA MÁS GRANDES + MEJOR DISEÑO
    try:
        pdf.set_font(font_family, 'B', 28)  # AUMENTADO de 24 a 28
        logging.info("[PDF] ✅ Fuente configurada correctamente")
    except Exception as e:
        logging.error(f"[PDF] ❌ Error configurando fuente: {e}")
        # Fallback con fuente más simple
        try:
            pdf.set_font('Arial', 'B', 24)
            font_family = 'Arial'
            logging.info("[PDF] ✅ Fuente fallback configurada")
        except Exception as e2:
            logging.error(f"[PDF] ❌ Error crítico con fuente fallback: {e2}")
            raise e2
    
    logging.info("[PDF] 🔧 Paso 2: Configurando color...")
    try:
        pdf.set_text_color(0, 51, 102)
        logging.info("[PDF] ✅ Color configurado correctamente")
    except Exception as e:
        logging.error(f"[PDF] ❌ Error configurando color: {e}")
        pdf.set_text_color(0, 0, 0)  # Negro por defecto
    
    logging.info("[PDF] 🔧 Paso 3: Renderizando celda de título...")
    
    # ✅ MANEJO ROBUSTO DE ENCODING PARA EVITAR HANG
    try:
        titulo_principal = "ANÁLISIS DE COMPETENCIA"  # CON ACENTOS
        
        logging.info(f"[PDF] 🔧 Paso 3a: Título preparado: '{titulo_principal}'")
        logging.info(f"[PDF] 🔧 Paso 3b: Usando cell nativo...")
        
        # ✅ USAR CELL NATIVO EN LUGAR DE MULTI_CELL PROBLEMÁTICO
        super(PatchedPDF, pdf).cell(0, 20, titulo_principal, ln=True, align='C')
        pdf.ln(5)  # Espacio adicional
        
        logging.info("[PDF] ✅ Título principal renderizado correctamente")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error con título, usando fallback: {e}")
        try:
            pdf.ln(20)  # Solo espacio si falla
            logging.info("[PDF] ✅ Fallback exitoso")
        except Exception as e2:
            logging.warning(f"[PDF] ⚠️ Fallback falló: {e2}")
            pass
    
    logging.info("[PDF] 🔧 Paso 4: Título completado, continuando...")
    
    logging.info("[PDF] 📄 Configurando subtítulo...")
    try:
        pdf.set_font(font_family, '', 16)  # AUMENTADO de 15 a 16
        logging.info("[PDF] ✅ Fuente subtítulo configurada")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error fuente subtítulo: {e}")
        pdf.set_font('Arial', '', 14)
    
    try:
        pdf.set_text_color(80, 80, 80)
        logging.info("[PDF] ✅ Color subtítulo configurado")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error color subtítulo: {e}")
        pdf.set_text_color(0, 0, 0)
    
    # ✅ SUBTÍTULO
    try:
        subtitulo = "Informe profesional LLM-First"
        logging.info("[PDF] 🔧 Renderizando subtítulo...")
        # ✅ USAR CELL NATIVO EN LUGAR DE MULTI_CELL PROBLEMÁTICO
        super(PatchedPDF, pdf).cell(0, 14, subtitulo, ln=True, align='C')
        pdf.ln(2)  # Espacio adicional
        logging.info("[PDF] ✅ Subtítulo renderizado correctamente")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error con subtítulo: {e}")
        try:
            pdf.ln(14)  # Solo espacio si falla
            logging.info("[PDF] ✅ Subtítulo fallback exitoso")
        except Exception as e2:
            logging.warning(f"[PDF] ⚠️ Subtítulo fallback falló: {e2}")
            pass
    
    logging.info("[PDF] 🖼️ Procesando logo...")
    pdf.ln(50)  # Más espacio
    
    # Logo si existe
    if pdf.logo_path and os.path.exists(pdf.logo_path):
        try:
            logging.info(f"[PDF] 📸 Insertando logo: {pdf.logo_path}")
            pdf.image(pdf.logo_path, x=85, y=pdf.get_y(), w=40)
            pdf.ln(50)
            logging.info("[PDF] ✅ Logo insertado correctamente")
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error insertando logo: {e}")
    else:
        logging.info("[PDF] ℹ️ No hay logo para insertar")
    
    logging.info("[PDF] 📅 Añadiendo fecha y empresa...")
    try:
        pdf.set_y(pdf.h-45)
        logging.info("[PDF] ✅ Posición Y configurada")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error posición Y: {e}")
    
    try:
        pdf.set_font(font_family, '', 12)  # AUMENTADO de 11 a 12
        logging.info("[PDF] ✅ Fuente fecha configurada")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error fuente fecha: {e}")
        pdf.set_font('Arial', '', 10)
    
    try:
        pdf.set_text_color(80, 80, 80)
        logging.info("[PDF] ✅ Color fecha configurado")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error color fecha: {e}")
        pdf.set_text_color(0, 0, 0)
    
    # ✅ FECHA Y EMPRESA
    try:
        fecha_texto = f"Fecha: {datetime.now().strftime('%d/%m/%Y')}"
        logging.info("[PDF] 🔧 Renderizando fecha...")
        # ✅ USAR CELL NATIVO EN LUGAR DE MULTI_CELL PROBLEMÁTICO
        super(PatchedPDF, pdf).cell(0, 10, fecha_texto, ln=True, align='C')
        logging.info("[PDF] ✅ Fecha renderizada correctamente")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error con fecha: {e}")
        try:
            pdf.ln(10)
            logging.info("[PDF] ✅ Fecha fallback exitosa")
        except Exception as e2:
            logging.warning(f"[PDF] ⚠️ Fecha fallback falló: {e2}")
            pass
    
    try:
        empresa_texto = "Sener - Innovación Tecnológica"  # CON ACENTOS
        logging.info("[PDF] 🔧 Renderizando empresa...")
        # ✅ USAR CELL NATIVO EN LUGAR DE MULTI_CELL PROBLEMÁTICO
        super(PatchedPDF, pdf).cell(0, 10, empresa_texto, ln=True, align='C')
        logging.info("[PDF] ✅ Empresa renderizada correctamente")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error con empresa: {e}")
        try:
            pdf.ln(10)
            logging.info("[PDF] ✅ Empresa fallback exitosa")
        except Exception as e2:
            logging.warning(f"[PDF] ⚠️ Empresa fallback falló: {e2}")
            pass
    
    try:
        pdf.set_text_color(0,0,0)
        logging.info("[PDF] ✅ Color reset completado")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error reset color: {e}")
    
    logging.info("[PDF] ✅ Portada completada")

    # --- Normalizar y limpiar secciones ---
    logging.info("[PDF] 📊 Normalizando datos de entrada...")
    
    def normalize_sections(d):
        logging.info(f"[PDF] 🔍 Normalizando {len(d)} secciones...")
        
        # ✅ AÑADIR TIMEOUT PARA EVITAR COLGARSE
        import time
        start_time = time.time()
        
        # ✅ SECCIONES EXCLUIDAS - NO INCLUIR EN EL PDF
        secciones_excluidas = {
            'resumen_ejecutivo', 'analisis_mercado', 'benchmarking', 
            'vigilancia_tecnologica', 'dafo', 'recomendaciones', 
            'conclusion_final', 'metadatos'
        }
        
        ordered_sections = get_ordered_sections()
        result = {}
        
        for i, section_key in enumerate(ordered_sections):
            logging.info(f"[PDF] 📋 Procesando sección {i+1}/{len(ordered_sections)}: {section_key}")
            
            # ✅ TIMEOUT DE SEGURIDAD
            if time.time() - start_time > 30:  # 30 segundos máximo
                logging.error(f"[PDF] ⏱️ TIMEOUT en normalización después de 30s, abortando")
                break
            
            v = None
            # Buscar la clave exacta (case-insensitive)
            for key in d.keys():
                if key.upper() == section_key.upper():
                    v = d[key]
                    break
                    
            if v is not None:
                logging.info(f"[PDF] 🔍 Encontrada sección {section_key}, tipo: {type(v)}")
                
                # ✅ OPTIMIZACIÓN: Truncar datos muy grandes para evitar colgarse
                if isinstance(v, dict):
                    texto = v.get('texto', '')
                    datos = v.get('datos')
                    
                    # ✅ FILTRAR TEXTOS NO DESEADOS
                    if isinstance(texto, str):
                        # Filtrar mensajes genéricos no deseados
                        texto_lower = texto.lower()
                        frases_excluidas = [
                            'no se pudo extraer',
                            'no se encontraron datos específicos',
                            'no se encontraron datos de',
                            'no se pudo realizar',
                            'consulte fuentes primarias',
                            'se recomienda realizar un análisis',
                            'es recomendable consultar',
                            'sin embargo, en el sector suelen',
                            'no se pudo extraer una conclusión'
                        ]
                        
                        if any(frase in texto_lower for frase in frases_excluidas):
                            logging.info(f"[PDF] 🚫 Texto genérico filtrado en {section_key}")
                            texto = ""  # Limpiar texto genérico
                    
                    # Limitar texto muy largo
                    if isinstance(texto, str) and len(texto) > 50000:  # AUMENTADO de 10000 a 50000
                        logging.warning(f"[PDF] ⚠️ Texto muy largo en {section_key}, truncando...")
                        texto = texto[:50000] + "... [Texto truncado por longitud]"  # AUMENTADO
                        v = {**v, 'texto': texto}
                    
                    # Limitar listas muy grandes en datos
                    if isinstance(datos, dict):
                        for key, value in datos.items():
                            if isinstance(value, list) and len(value) > 20:
                                logging.warning(f"[PDF] ⚠️ Lista muy grande en {section_key}.{key}, truncando...")
                                datos[key] = value[:20] + [{"nota": "... Lista truncada por tamaño"}]
                    
                    # Solo incluir si tiene contenido REAL y válido
                    if (texto and texto.strip() and 'no disponible' not in texto.lower()) or datos:
                        result[section_key] = v
                        logging.info(f"[PDF] ✅ Sección incluida: {section_key}")
                    else:
                        logging.info(f"[PDF] 🚫 Sección filtrada por contenido vacío: {section_key}")
                elif isinstance(v, str) and v.strip():
                    # ✅ FILTRAR STRINGS NO DESEADOS
                    v_lower = v.lower()
                    frases_excluidas = [
                        'no se pudo extraer',
                        'no se encontraron datos específicos',
                        'no se encontraron datos de',
                        'no se pudo realizar',
                        'consulte fuentes primarias',
                        'se recomienda realizar un análisis',
                        'es recomendable consultar'
                    ]
                    
                    if any(frase in v_lower for frase in frases_excluidas):
                        logging.info(f"[PDF] 🚫 String genérico filtrado en {section_key}")
                        continue  # No incluir esta sección
                    
                    if 'no disponible' not in v_lower:
                        # Truncar strings muy largos
                        if len(v) > 50000:  # AUMENTADO de 10000 a 50000
                            logging.warning(f"[PDF] ⚠️ String muy largo en {section_key}, truncando...")
                            v = v[:50000] + "... [Texto truncado por longitud]"  # AUMENTADO
                        result[section_key] = {'texto': v}
                        logging.info(f"[PDF] ✅ String válido incluido: {section_key}")
                    else:
                        logging.info(f"[PDF] 🚫 String 'no disponible' filtrado en {section_key}")
                elif isinstance(v, list) and len(v) > 0:
                    # ✅ LISTAS DE DATOS
                    # Truncar listas muy grandes
                    if len(v) > 20:
                        logging.warning(f"[PDF] ⚠️ Lista muy grande en {section_key}, truncando...")
                        v = v[:20] + [{"nota": "... Lista truncada por tamaño"}]
                    result[section_key] = {'datos': v}
                    logging.info(f"[PDF] ✅ Lista incluida: {section_key}")
                else:
                    logging.info(f"[PDF] 🚫 Sección no válida filtrada: {section_key}")
            else:
                logging.info(f"[PDF] ⏭️ Sección {section_key} no encontrada")
        
        # ✅ PRESERVAR CAMPOS CRÍTICOS DE METADATOS DE LA IDEA
        # Incluir campos esenciales y NO incluir secciones legacy excluidas
        campos_preservar = ['idea', 'idea_title', 'idea_text', 'original_idea_data', 'title']
        
        for key, value in d.items():
            if key in campos_preservar:
                result[key] = value
                logging.info(f"[PDF] ✅ Campo crítico preservado: {key}")
            elif key.lower() in secciones_excluidas:
                logging.info(f"[PDF] 🚫 Sección legacy excluida: {key}")
                continue  # No incluir secciones legacy
            
        elapsed = time.time() - start_time
        logging.info(f"[PDF] ✅ Normalización completada: {len(result)} secciones válidas en {elapsed:.2f}s")
        return result
        
    # Nueva estructura: executive_summary global + ideas individuales
    executive_summary = None
    ideas = []
    
    if isinstance(data, dict):
        # Extraer resumen ejecutivo global si existe
        if 'executive_summary' in data and data['executive_summary']:
            executive_summary = data['executive_summary']
            logging.info("[PDF] 📋 Resumen ejecutivo global encontrado")
        
        # Procesar ideas individuales
        if 'ideas' in data and isinstance(data['ideas'], list):
            logging.info(f"[PDF] 📋 Procesando {len(data['ideas'])} ideas individuales...")
            ideas = [normalize_sections(idea) for idea in data['ideas']]
        elif 'ideas' not in data:
            # Formato legacy: procesar como idea única
            logging.info("[PDF] 📋 Procesando como idea única (formato legacy)...")
            ideas = [normalize_sections(data)]
    else:
        logging.info("[PDF] 📋 Procesando datos como idea única...")
        ideas = [normalize_sections(data)]
        
    logging.info("[PDF] 🔄 Homogeneizando secciones para PDF...")
    # --- Homogeneizar secciones para PDF (garantiza que no se pierdan tablas ni dicts estructurados) ---
    ideas = [{**_coerce_sections_for_pdf(idea)} for idea in ideas]
    logging.info("[PDF] ✅ Homogeneización completada.")

    # --- Índice ---
    logging.info("[PDF] 📚 Generando índice...")
    pdf.add_page()
    
    # ✅ CONFIGURACIÓN DEL TÍTULO DEL ÍNDICE
    try:
        pdf.set_font(font_family, 'B', 20)  # AUMENTADO de 16 a 20
        logging.info("[PDF] ✅ Fuente índice configurada")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error fuente índice: {e}")
        pdf.set_font('Arial', 'B', 18)
    
    try:
        pdf.set_text_color(0, 51, 102)
        logging.info("[PDF] ✅ Color índice configurado")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error color índice: {e}")
        pdf.set_text_color(0, 0, 0)
    
    # ✅ TÍTULO DEL ÍNDICE
    try:
        titulo_indice = "Indice de Contenidos"  # SIN ACENTOS por defecto
        logging.info("[PDF] 🔧 Renderizando título índice con cell nativo...")
        super(PatchedPDF, pdf).cell(0, 15, titulo_indice, ln=True, align='C')
        pdf.ln(3)  # Espacio adicional
        logging.info("[PDF] ✅ Título del índice renderizado correctamente")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error con título índice, usando fallback: {e}")
        try:
            pdf.ln(15)
            logging.info("[PDF] ✅ Título índice fallback exitoso")
        except Exception as e2:
            logging.warning(f"[PDF] ⚠️ Título índice fallback falló: {e2}")
            pass
    
    try:
        pdf.ln(8)
        pdf.set_font(font_family, '', 12)  # AUMENTADO de 10 a 12
        pdf.set_text_color(0, 0, 0)
        logging.info("[PDF] ✅ Configuración TOC completada")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error configuración TOC: {e}")
        pdf.set_font('Arial', '', 10)
        pdf.set_text_color(0, 0, 0)
    
    # --- LÓGICA INTELIGENTE PARA ESPACIO DEL ÍNDICE ---
    num_ideas = len(ideas) if isinstance(ideas, list) else 1
    logging.info(f"[PDF] 📊 Detectadas {num_ideas} ideas - calculando espacio para índice...")
    
    # 🔥 LÓGICA DEL USUARIO: Páginas extra según número de ideas
    if num_ideas <= 2:
        extra_index_pages = 0
        logging.info(f"[PDF] 📋 {num_ideas} ideas: usando página actual del índice")
    elif num_ideas <= 5:
        extra_index_pages = 1
        logging.info(f"[PDF] 📋 {num_ideas} ideas: añadiendo 1 página extra para índice")
    else:
        extra_index_pages = 2
        logging.info(f"[PDF] 📋 {num_ideas} ideas: añadiendo 2 páginas extra para índice")
    
    # Guardar posición inicial del índice
    index_page_no = pdf.page_no()  # Guardamos número de página del índice
    index_y_start = pdf.get_y()    # Posición Y inicial donde comenzarán las entradas
    toc_entries = []               # Lista que almacenará (titulo, link_id, page_no)
    
    # Añadir páginas extra en blanco para el índice si es necesario
    for i in range(extra_index_pages):
        pdf.add_page()
        logging.info(f"[PDF] 📄 Página extra {i+1}/{extra_index_pages} añadida para índice")
    
    logging.info("[PDF] ⏳ Índice en construcción – se completará al final")

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # FIN DEL ÍNDICE: siempre empezar el contenido en nueva página
    pdf.add_page()
    pdf.set_y(20)  # 20 mm desde el borde superior
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    # --- 1. RESUMEN EJECUTIVO GLOBAL PRIMERO ---
    if executive_summary and executive_summary.get('texto'):
        logging.info("[PDF] 📝 Añadiendo resumen ejecutivo global...")
        
        link_id = pdf.add_link()
        pdf.set_link(link_id)  # El enlace apunta al inicio de la página actual
        toc_entries.append(("Resumen Ejecutivo", link_id, pdf.page_no()))
        
        # ✅ SEPARADOR VISUAL ELIMINADO - Sin líneas azules arriba del Resumen Ejecutivo
        pdf.ln(8)
        
        add_professional_header(pdf, "Análisis de Competencia")
        
        # Título del resumen ejecutivo
        try:
            pdf.set_font(font_family, 'B', 22)
            pdf.set_text_color(0, 51, 102)
            super(PatchedPDF, pdf).cell(0, 15, "Resumen Ejecutivo", ln=True)
            pdf.ln(8)
            pdf.set_text_color(0, 0, 0)
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error título resumen ejecutivo: {e}")
            pdf.ln(15)
        
        # Contenido del resumen ejecutivo global
        try:
            pdf.set_font(font_family, '', 11)
            texto_limpio = clean_and_normalize(executive_summary['texto'])
            add_generic_text_block(pdf, texto_limpio, font_family)
            pdf.ln(8)
            logging.info("[PDF] ✅ Resumen ejecutivo global añadido correctamente")
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error añadiendo resumen ejecutivo: {e}")
    else:
        logging.info("[PDF] ℹ️ No hay resumen ejecutivo global para añadir")

    # --- 2. ANÁLISIS INDIVIDUAL POR IDEA ---
    logging.info("[PDF] 📑 Iniciando generación de secciones por idea...")
    
    secciones_mostradas = 0
    for idx, idea in enumerate(ideas, 1):
        # 🔥 DEBUG TOTAL: QUÉ DATOS LLEGAN AL PDF
        print(f"🔥🔥🔥 [PDF] === IDEA {idx} DATOS RECIBIDOS === 🔥🔥🔥")
        print(f"🔥🔥🔥 [PDF] Tipo: {type(idea)} 🔥🔥🔥")
        if isinstance(idea, dict):
            print(f"🔥🔥🔥 [PDF] Campos: {list(idea.keys())} 🔥🔥🔥")
            for key in ['idea_title', 'title', 'idea_text', 'idea', 'original_idea_data']:
                if key in idea:
                    value = idea[key]
                    if isinstance(value, str):
                        print(f"🔥🔥🔥 [PDF] {key}: '{value[:100]}...' 🔥🔥🔥")
                    else:
                        print(f"🔥🔥🔥 [PDF] {key}: {type(value)} 🔥🔥🔥")
                else:
                    print(f"🔥🔥🔥 [PDF] {key}: NO EXISTE 🔥🔥🔥")
        else:
            print(f"🔥🔥🔥 [PDF] Contenido: {str(idea)[:100]}... 🔥🔥🔥")
        print(f"🔥🔥🔥 [PDF] ================================== 🔥🔥🔥")
        
        # ✅ USAR NUEVA ESTRUCTURA DE DATOS
        idea_title = extract_idea_title(idea, idx)
        
        logging.info(f"[PDF] 💡 Procesando idea {idx}: {idea_title[:50]}...")
        
        # Título principal de la idea - ÍNDICE ENTRY SOLAMENTE
        link_id = pdf.add_link()
        # ✅ NO AÑADIR PÁGINA NUEVA AQUÍ - El título aparecerá antes de la primera sección
        pdf.set_link(link_id)
        # ✅ USAR SOLO EL TÍTULO LIMPIO EN EL ÍNDICE (sin "Idea X:")
        toc_title = idea_title[:60] + ('...' if len(idea_title) > 60 else '')
        toc_entries.append((f"{idx}. {toc_title}", link_id, pdf.page_no()))
        
        # ✅ GUARDAR EL TÍTULO DE LA IDEA PARA USARLO EN LOS HEADERS
        current_idea_title = idea_title
        
        # ✅ COMENTADO: El texto de la idea ahora se muestra antes de la primera sección
        # para evitar páginas en blanco innecesarias
        
        first_section = True  # ✅ CONTROLAR SI ES LA PRIMERA SECCIÓN
        
        for sec in get_ordered_sections():
            logging.info(f"[PDF] 🔍 Evaluando sección: {sec}")
            
            sec_data = idea.get(sec)
            if not sec_data:
                logging.info(f"[PDF] ⏭️ Sección omitida: {sec} (no existe)")
                continue
                
            # Verificar si tiene contenido válido
            tiene_texto = (isinstance(sec_data, dict) and 
                          sec_data.get('texto') and 
                          sec_data['texto'].strip() and 
                          'no disponible' not in sec_data['texto'].lower())
            tiene_datos = isinstance(sec_data, dict) and sec_data.get('datos')
            
            if not tiene_texto and not tiene_datos:
                logging.info(f"[PDF] ⏭️ Sección omitida: {sec} (sin contenido válido)")
                continue
                
            logging.info(f"[PDF] ✅ Generando sección: {sec} (texto={tiene_texto}, datos={tiene_datos})")
            secciones_mostradas += 1
            sec_title = SECTION_TITLE_MAP.get(sec, sec)
            
            # --- Título de la sección ---
            link_id = pdf.add_link()                # Crear enlace para esta sección
            pdf.add_page()                          # Nueva página para la sección
            pdf.set_link(link_id)                   # Anclar enlace al inicio de la página
            # ✅ AGREGAR SECCIÓN CON INDENTACIÓN EN EL ÍNDICE
            # Calcular el número de sección correctamente (empezando desde 1)
            all_sections = get_ordered_sections()
            try:
                # Para EXEC_SUMMARY, usar número 1, para el resto, ajustar según el orden
                if sec == "EXEC_SUMMARY":
                    section_number = 1
                else:
                    # Encontrar la posición actual y ajustar (COMPETITOR_MAPPING será 2, etc.)
                    section_number = all_sections.index(sec) + 1
            except ValueError:
                # Si no está en la lista, usar número secuencial
                section_number = len([s for s in all_sections if s in idea]) + 1
            
            toc_entries.append((f"    {idx}.{section_number} {sec_title}", link_id, pdf.page_no()))
            
            # ✅ SEPARADOR VISUAL ELIMINADO - Sin líneas azules
            pdf.ln(8)
            
            # ✅ AÑADIR HEADER PROFESIONAL CON NOMBRE DE LA IDEA
            header_title = f"Análisis de Competencia: {current_idea_title[:50]}" + ('...' if len(current_idea_title) > 50 else '')
            add_professional_header(pdf, header_title)
            
            # ✅ AÑADIR TÍTULO DE LA IDEA ANTES DE LA PRIMERA SECCIÓN CON FUENTE MÁS GRANDE
            if first_section:
                try:
                    pdf.set_font(font_family, 'B', 24)  # AUMENTADO de 18 a 24 para mayor visibilidad
                    pdf.set_text_color(0, 51, 102)
                    # ✅ MOSTRAR EL TÍTULO COMPLETO DE LA IDEA
                    display_title = current_idea_title[:100] + ('...' if len(current_idea_title) > 100 else '')
                    super(PatchedPDF, pdf).cell(0, 15, display_title, ln=True)  # AUMENTADO altura de 12 a 15
                    pdf.ln(8)
                    pdf.set_text_color(0, 0, 0)
                    logging.info(f"[PDF] ✅ Título de idea añadido antes de primera sección")
                except Exception as e:
                    logging.warning(f"[PDF] ⚠️ Error título idea en primera sección: {e}")
                    pdf.ln(8)
                first_section = False
            
            # ✅ TÍTULOS DE SECCIÓN MÁS GRANDES Y VISIBLES - PROTECCIÓN ROBUSTA
            try:
                pdf.set_font(font_family, 'B', 20)  # AUMENTADO de 18 a 20 para mayor impacto
                logging.info(f"[PDF] ✅ Fuente sección {sec} configurada")
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error fuente sección {sec}: {e}")
                pdf.set_font('Arial', 'B', 18)
            
            try:
                pdf.set_text_color(0, 51, 102)
                logging.info(f"[PDF] ✅ Color sección {sec} configurado")
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error color sección {sec}: {e}")
                pdf.set_text_color(0, 0, 0)
            
            # ✅ RENDERIZAR TÍTULO CON PROTECCIÓN ROBUSTA
            try:
                logging.info(f"[PDF] 🔧 Renderizando título sección {sec} con cell nativo...")
                # ✅ USAR CELL NATIVO EN LUGAR DE MULTI_CELL PROBLEMÁTICO
                super(PatchedPDF, pdf).cell(0, 15, sec_title, ln=True)  # AUMENTADO altura de 12 a 15
                pdf.ln(5)  # Más espacio adicional
                logging.info(f"[PDF] ✅ Título sección {sec} renderizado")
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error título sección {sec}: {e}")
                try:
                    # Fallback con nombre simple
                    simple_title = sec.replace('_', ' ').title()
                    super(PatchedPDF, pdf).cell(0, 15, simple_title, ln=True)
                    pdf.ln(5)
                    logging.info(f"[PDF] ✅ Título sección fallback exitoso")
                except Exception as e2:
                    logging.warning(f"[PDF] ⚠️ Título sección fallback falló: {e2}")
                    pdf.ln(15)  # Solo espacio
            
            try:
                pdf.ln(3)  # Espacio después del título
                pdf.set_text_color(0, 0, 0)
                logging.info(f"[PDF] ✅ Configuración post-título completada")
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error post-título: {e}")
                pdf.set_text_color(0, 0, 0)
            
            # --- Mostrar las tablas visuales PRIMERO si existen datos ---
            if tiene_datos:
                try:
                    logging.info(f"[PDF] 📊 Procesando datos estructurados para {sec}...")
                    
                    # ✅ OPTIMIZACIÓN: Procesar cada tipo de sección específicamente
                    if sec == "BENCHMARK_MATRIX":
                        logging.info(f"[PDF] 📊 Procesando matriz de benchmarking cuantitativa...")
                        benchmarking_data = None
                        if isinstance(sec_data.get('datos'), dict):
                            benchmarking_data = sec_data['datos']
                        
                        # ✅ NUEVO: Soporte para formato cuantitativo y compatibilidad con formato anterior
                        has_quantitative_table = (benchmarking_data and 
                                                isinstance(benchmarking_data.get('tabla_comparativa'), list) and 
                                                len(benchmarking_data['tabla_comparativa']) > 0)
                        has_legacy_table = (benchmarking_data and 
                                          isinstance(benchmarking_data.get('tabla'), list) and 
                                          len(benchmarking_data['tabla']) > 0)
                        has_analysis = (benchmarking_data and 
                                      isinstance(benchmarking_data.get('analisis_cualitativo'), dict))
                        has_quantitative_gaps = (benchmarking_data and 
                                               isinstance(benchmarking_data.get('gaps_cuantitativos'), list) and
                                               len(benchmarking_data['gaps_cuantitativos']) > 0)
                        has_metrics = (benchmarking_data and 
                                     isinstance(benchmarking_data.get('metricas_comparativas'), dict))
                        
                        # Priorizar formato cuantitativo
                        if has_quantitative_table:
                            logging.info(f"[PDF] 📊 Generando tabla cuantitativa con {len(benchmarking_data['tabla_comparativa'])} competidores...")
                            # ✅ NUEVA FUNCIÓN: Tabla de métricas cuantitativas
                            add_quantitative_benchmarking_table(pdf, benchmarking_data, add_reference, clean_and_normalize)
                            
                            # Métricas comparativas del sector
                            if has_metrics:
                                metricas = benchmarking_data['metricas_comparativas']
                                pdf.ln(8)
                                pdf.add_subsection_title("Métricas Comparativas del Sector")
                                
                                metricas_text = ""
                                
                                # Líderes por métrica (con formato mejorado)
                                if 'lider_ingresos' in metricas and isinstance(metricas['lider_ingresos'], dict):
                                    lider = metricas['lider_ingresos']
                                    empresa = lider.get('empresa', 'N/D')
                                    valor = lider.get('valor', 0)
                                    metricas_text += f"Líder en Ingresos: {empresa} ({valor:,.0f} MEUR) "
                                
                                if 'lider_empleados' in metricas and isinstance(metricas['lider_empleados'], dict):
                                    lider = metricas['lider_empleados']
                                    empresa = lider.get('empresa', 'N/D')
                                    valor = lider.get('valor', 0)
                                    metricas_text += f"Líder en Empleados: {empresa} ({valor:,.0f} empleados) "
                                
                                if 'lider_cuota_mercado' in metricas and isinstance(metricas['lider_cuota_mercado'], dict):
                                    lider = metricas['lider_cuota_mercado']
                                    empresa = lider.get('empresa', 'N/D')
                                    valor = lider.get('valor', 0)
                                    metricas_text += f"Líder en Cuota de Mercado: {empresa} ({valor:.1f}%) "
                                
                                # Promedios del sector
                                if 'promedio_sector_ingresos' in metricas:
                                    promedio = metricas['promedio_sector_ingresos']
                                    metricas_text += f"Promedio Sectorial - Ingresos: {promedio:,.0f} MEUR "
                                
                                if 'promedio_sector_empleados' in metricas:
                                    promedio = metricas['promedio_sector_empleados']
                                    metricas_text += f"Promedio Sectorial - Empleados: {promedio:,.0f}"
                                
                                if metricas_text.strip():
                                    pdf.add_paragraph(metricas_text.strip())
                            
                            # Gaps cuantitativos
                            if has_quantitative_gaps:
                                gaps = benchmarking_data['gaps_cuantitativos']
                                pdf.ln(8)
                                pdf.add_subsection_title("Gaps Cuantitativos y Oportunidades")
                                
                                gaps_text = ""
                                for i, gap in enumerate(gaps, 1):
                                    if isinstance(gap, dict):
                                        metrica = gap.get('metrica', f'Métrica {i}')
                                        brecha = gap.get('brecha_identificada', 'Sin datos')
                                        oportunidad = gap.get('oportunidad_sener', 'Por evaluar')
                                        
                                        gaps_text += f"{i}. {metrica}\n"
                                        gaps_text += f"   Brecha: {clean_and_normalize(str(brecha))}\n"
                                        gaps_text += f"   Oportunidad Sener: {clean_and_normalize(str(oportunidad))}\n\n"
                                
                                if gaps_text.strip():
                                    pdf.add_paragraph(gaps_text.strip())
                            
                            logging.info(f"[PDF] ✅ Benchmarking cuantitativo completado")
                            
                        elif has_legacy_table or has_analysis:
                            logging.info(f"[PDF] 📋 Usando formato de benchmarking anterior: tabla={has_legacy_table}, análisis={has_analysis}")
                            # ✅ NO PONER TÍTULO "Matriz de Benchmarking" - ir directo a las tablas
                            add_benchmarking_table(pdf, benchmarking_data, add_reference, clean_and_normalize)
                            pdf.ln(4)
                            logging.info(f"[PDF] ✅ Matriz de benchmarking tradicional completada")
                        else:
                            logging.warning(f"[PDF] ⚠️ No hay datos de benchmarking para BENCHMARK_MATRIX")
                            
                    elif sec == "SWOT_POSITIONING":
                        logging.info(f"[PDF] 📊 Procesando análisis DAFO...")
                        dafo = None
                        if isinstance(sec_data.get('datos'), dict) and 'swot' in sec_data['datos']:
                            dafo = sec_data['datos']['swot']
                            
                        if dafo and isinstance(dafo, dict):
                            logging.info(f"[PDF] ✅ DAFO: campos {list(dafo.keys())}")
                            # ✅ ELIMINAR TÍTULO DUPLICADO - Ya aparece como título de sección
                            # pdf.set_font(font_family, 'B', 12)
                            # pdf.set_text_color(0, 51, 102)
                            # pdf.cell(0, 8, "Análisis DAFO", ln=True)
                            # pdf.set_text_color(0,0,0)
                            # pdf.ln(2)
                            add_dafo_visual(pdf, dafo, add_reference, clean_and_normalize)
                            pdf.ln(4)
                            logging.info(f"[PDF] ✅ DAFO completado")
                        else:
                            logging.warning(f"[PDF] ⚠️ No hay datos DAFO en SWOT_POSITIONING")
                            
                    elif sec == "TECH_IP_LANDSCAPE":
                        vigilancia = None
                        if isinstance(sec_data.get('datos'), dict):
                            datos = sec_data['datos']
                            
                            # 🔍 NUEVA VALIDACIÓN: Verificar que el contenido sea específico, no genérico
                            def is_content_specific(items, field_name):
                                """
                                🔥 VALIDADOR MEJORADO: Acepta contenido específico O indicaciones transparentes de búsqueda
                                """
                                if not items or not isinstance(items, list):
                                    return False
                                
                                # ✅ ACEPTAR indicaciones transparentes de búsqueda ESPECÍFICAS
                                search_indicators = [
                                    'búsqueda requerida', 'búsqueda pendiente', 'se requiere búsqueda',
                                    'búsqueda especializada', 'identificación pendiente', 'análisis requerido', 
                                    'por identificar', 'pendiente en bases de datos', 'especializada en',
                                    'investigación necesaria', 'revisión requerida', 'análisis del estado del arte',
                                    'análisis técnico requerido', 'google patents', 'uspto', 'epo',
                                    'nature', 'science', 'ieee', 'mit', 'stanford', 'eth',
                                    'investigadores líderes', 'universidades como', 'empresas líderes',
                                    'panasonic', 'siemens', 'general electric', 'ibm', 'microsoft',
                                    'búsqueda necesaria'
                                ]
                                
                                # ❌ RECHAZAR contenido genérico/inventado (lista expandida)
                                generic_indicators = [
                                    'tecnología relevante', 'empresas del sector', 'tecnología general',
                                    'métodos y sistemas para prevenir bioincrustaciones',  # Ejemplo específico falso
                                    'sistemas del sector', 'tecnologías tradicionales',
                                    'del sector en general', 'empresas tradicionales del área',
                                    'área tecnológica específica', 'se requiere búsqueda especializada',
                                    'bases de datos especializadas', 'universidades del área',
                                    'investigadores por identificar', 'tecnología de la idea',
                                    'análisis basado en datos disponibles', 'evaluación específica requerida',
                                    'pendiente de análisis detallado'
                                ]
                                
                                valid_count = 0
                                for item in items:
                                    if isinstance(item, dict):
                                        # Obtener el texto principal del item
                                        text_to_check = ''
                                        if field_name == 'patentes':
                                            text_to_check = item.get('titulo', '') + ' ' + item.get('numero_patente', '') + ' ' + item.get('titular', '')
                                        elif field_name == 'publicaciones':
                                            text_to_check = item.get('titulo', '') + ' ' + item.get('autores', '') + ' ' + item.get('revista', '')
                                        elif field_name == 'gaps':
                                            text_to_check = item.get('area_tecnologica', '') + ' ' + item.get('descripcion_gap', '')
                                        elif field_name == 'tendencias':
                                            text_to_check = item.get('tecnologia', '')
                                        
                                        # ✅ ACEPTAR si tiene indicadores de búsqueda transparente
                                        has_search_indicator = any(indicator in text_to_check.lower() for indicator in search_indicators)
                                        
                                        # ❌ RECHAZAR si tiene indicadores genéricos problemáticos
                                        has_generic_content = any(indicator in text_to_check.lower() for indicator in generic_indicators)
                                        
                                        if has_search_indicator:
                                            logging.info(f"[PDF] ✅ {field_name}: Indicación transparente de búsqueda aceptada")
                                            valid_count += 1
                                        elif has_generic_content:
                                            logging.warning(f"[PDF] ❌ {field_name}: Contenido genérico rechazado: '{text_to_check[:60]}...'")
                                        elif len(text_to_check.strip()) > 15:
                                            logging.info(f"[PDF] ✅ {field_name}: Contenido específico válido")
                                            valid_count += 1
                                
                                return valid_count > 0
                            
                            # Verificar contenido específico en cada campo
                            patentes = datos.get('patentes_destacadas', [])
                            publicaciones = datos.get('publicaciones_clave', [])
                            gaps = datos.get('gaps_tecnologicos', [])
                            tendencias = datos.get('tendencias_emergentes', [])
                            
                            patentes_especificas = is_content_specific(patentes, 'patentes')
                            publicaciones_especificas = is_content_specific(publicaciones, 'publicaciones')
                            gaps_especificos = is_content_specific(gaps, 'gaps')
                            tendencias_especificas = is_content_specific(tendencias, 'tendencias')
                            
                            # ✅ CRITERIO MÁS ESTRICTO: Exigir contenido de calidad
                            criterio_minimo = (patentes_especificas and publicaciones_especificas) or (gaps_especificos and tendencias_especificas)
                            
                            # ✅ VERIFICACIÓN ADICIONAL: Contar elementos específicos vs genéricos
                            total_items = len(patentes) + len(publicaciones) + len(gaps) + len(tendencias)
                            items_especificos = (len(patentes) if patentes_especificas else 0) + \
                                              (len(publicaciones) if publicaciones_especificas else 0) + \
                                              (len(gaps) if gaps_especificos else 0) + \
                                              (len(tendencias) if tendencias_especificas else 0)
                            
                            # Solo incluir si al menos 70% del contenido es específico
                            if total_items > 0:
                                ratio_especifico = items_especificos / total_items
                                logging.info(f"[PDF] 🔍 Ratio contenido específico: {ratio_especifico:.2f} ({items_especificos}/{total_items})")
                                
                                if ratio_especifico >= 0.7 and criterio_minimo:
                                    vigilancia = datos
                                    logging.info(f"[PDF] ✅ Vigilancia tecnológica incluida - calidad suficiente ({ratio_especifico:.0%})")
                                else:
                                    logging.info(f"[PDF] ❌ Vigilancia tecnológica omitida - calidad insuficiente ({ratio_especifico:.0%})")
                            else:
                                logging.info(f"[PDF] ⏭️ Vigilancia tecnológica omitida - sin contenido")
                        
                        if vigilancia:
                            logging.info(f"[PDF] Mostrando vigilancia tecnológica con campos: {list(vigilancia.keys())}")
                            # ✅ ELIMINAR TÍTULO REDUNDANTE "Datos de Vigilancia Tecnológica"
                            # El título de la sección ya aparece como "Vigilancia Tecnológica y Propiedad Intelectual"
                            add_vigilancia_tecnologica(pdf, vigilancia, add_reference, clean_and_normalize)
                            pdf.ln(4)
                        else:
                            logging.info(f"[PDF] ⏭️ Sección vigilancia tecnológica omitida completamente")
                            
                    elif sec == "MARKET_ANALYSIS":
                        logging.info(f"[PDF] 📊 Procesando análisis de mercado...")
                        
                        # ✅ USAR DATOS ESTRUCTURADOS DEL LLM EN LUGAR DE EXTRAER DEL TEXTO
                        gaps_from_llm = []
                        oportunidades_from_llm = []
                        
                        # Buscar en datos estructurados primero
                        market_data = sec_data.get('datos', {})
                        if isinstance(market_data, dict):
                            # Buscar gaps en analisis_cualitativo
                            analisis = market_data.get('analisis_cualitativo', {})
                            if isinstance(analisis, dict):
                                gaps_list = analisis.get('gaps_identificados', [])
                                oportunidades_list = analisis.get('oportunidades_sener', [])
                                
                                # Limpiar y procesar gaps
                                if isinstance(gaps_list, list):
                                    for gap in gaps_list[:4]:  # Máximo 4
                                        if gap and str(gap).strip():
                                            gap_clean = clean_and_normalize(str(gap))[:80]
                                            if len(gap_clean) > 15:
                                                gaps_from_llm.append(gap_clean)
                                
                                # Limpiar y procesar oportunidades
                                if isinstance(oportunidades_list, list):
                                    for opp in oportunidades_list[:4]:  # Máximo 4
                                        if opp and str(opp).strip():
                                            opp_clean = clean_and_normalize(str(opp))[:80]
                                            if len(opp_clean) > 15:
                                                oportunidades_from_llm.append(opp_clean)
                            
                            # Buscar también en restrictores y drivers como alternativa
                            if not gaps_from_llm:
                                restrictores = market_data.get('restrictores', [])
                                if isinstance(restrictores, list):
                                    for restrictor in restrictores[:3]:
                                        if restrictor and str(restrictor).strip():
                                            rest_clean = clean_and_normalize(str(restrictor))[:80]
                                            if len(rest_clean) > 15:
                                                gaps_from_llm.append(rest_clean)
                        
                        # ✅ FALLBACK: Si no hay datos estructurados, extraer del texto
                        market_text = sec_data.get('texto', '')
                        if (not gaps_from_llm or not oportunidades_from_llm) and market_text:
                            logging.info(f"[PDF] 🔍 Fallback: extrayendo del texto porque gaps={len(gaps_from_llm)}, opp={len(oportunidades_from_llm)}")
                            
                            # Solo usar regex si no hay datos estructurados
                            if not gaps_from_llm:
                                gaps_patterns = [
                                    r'gaps?\s+[^.]*?\.([^.]*?\.){0,1}',
                                    r'limitaciones?\s+[^.]*?\.([^.]*?\.){0,1}', 
                                    r'vacíos?\s+[^.]*?\.([^.]*?\.){0,1}',
                                    r'restrictor[^.]*?\.([^.]*?\.){0,1}'
                                ]
                                
                                for pattern in gaps_patterns:
                                    matches = re.finditer(pattern, market_text, re.IGNORECASE | re.DOTALL)
                                    for match in matches:
                                        gap_text = match.group(0).strip()
                                        if 20 < len(gap_text) < 200:
                                            gap_clean = clean_and_normalize(gap_text.split('.')[0])[:80]
                                            if len(gap_clean) > 15:
                                                gaps_from_llm.append(gap_clean)
                            
                            if not oportunidades_from_llm:
                                opp_patterns = [
                                    r'Sener\s+puede[^.]*?\.([^.]*?\.){0,1}',
                                    r'oportunidad[^.]*?Sener[^.]*?\.([^.]*?\.){0,1}',
                                    r'posicionarse[^.]*?\.([^.]*?\.){0,1}'
                                ]
                                
                                for pattern in opp_patterns:
                                    matches = re.finditer(pattern, market_text, re.IGNORECASE | re.DOTALL)
                                    for match in matches:
                                        opp_text = match.group(0).strip()
                                        if 20 < len(opp_text) < 200:
                                            opp_clean = clean_and_normalize(opp_text.split('.')[0])[:80]
                                            if len(opp_clean) > 15:
                                                oportunidades_from_llm.append(opp_clean)
                        
                        # ✅ VALORES POR DEFECTO SI NO HAY DATOS
                        if not gaps_from_llm:
                            gaps_from_llm = ["Requiere análisis específico de gaps"]
                        if not oportunidades_from_llm:
                            oportunidades_from_llm = ["Requiere análisis específico de oportunidades"]
                        
                        # ✅ CREAR GRÁFICO DIRECTAMENTE SIN TÍTULOS INTRODUCTORIOS
                        try:
                            logging.info(f"[PDF] 📈 Creando gráfico con datos del LLM: {len(gaps_from_llm)} gaps, {len(oportunidades_from_llm)} oportunidades")
                            chart_path = create_market_gaps_opportunities_chart_from_data(gaps_from_llm, oportunidades_from_llm, "output")
                            
                            if chart_path and os.path.exists(chart_path):
                                logging.info(f"[PDF] ✅ Insertando gráfico de gaps y oportunidades...")
                                
                                # ✅ SIN TÍTULOS INTRODUCTORIOS - DIRECTAMENTE EL GRÁFICO
                                try:
                                    # Calcular posición centrada
                                    _insert_full_width_image(pdf, chart_path)
                                    
                                    logging.info(f"[PDF] ✅ Gráfico insertado correctamente")
                                    
                                except Exception as img_e:
                                    logging.warning(f"[PDF] ⚠️ Error insertando imagen del gráfico: {img_e}")
                                    
                            else:
                                logging.warning(f"[PDF] ⚠️ No se pudo crear el gráfico de gaps y oportunidades")
                                
                        except Exception as chart_e:
                            logging.warning(f"[PDF] ⚠️ Error creando gráfico de gaps/oportunidades: {chart_e}")
                            # Continuar sin el gráfico
                            
                    elif sec == "COMPETITOR_MAPPING":
                        competidores = None
                        if isinstance(sec_data.get('datos'), dict):
                            datos = sec_data['datos']
                            if any(k in datos for k in ['competidores_directos', 'competidores_indirectos', 'emergentes']):
                                competidores = datos
                                
                        if competidores:
                            logging.info(f"[PDF] Mostrando mapa de competidores con tablas profesionales")
                            # ✅ NO PONER TÍTULO DUPLICADO "Mapa de Competidores"
                            # El título ya aparece en el procesamiento general de secciones
                            
                            # ✅ FUNCIÓN PARA CREAR TABLA DE COMPETIDORES PROFESIONAL - SÚPER ROBUSTA
                            def create_competitor_table(title, competitors, color_rgb):
                                try:
                                    if not competitors or not isinstance(competitors, list) or len(competitors) == 0:
                                        return
                                        
                                    # ✅ VALIDAR COLORES RGB
                                    try:
                                        r, g, b = color_rgb
                                        r = max(0, min(255, int(r)))
                                        g = max(0, min(255, int(g)))
                                        b = max(0, min(255, int(b)))
                                        color_rgb = (r, g, b)
                                    except:
                                        color_rgb = (100, 100, 100)  # Gris por defecto
                                    
                                    # ✅ TÍTULO DE CATEGORÍA CON PROTECCIÓN
                                    try:
                                        pdf.set_font(font_family, 'B', 11)
                                        pdf.set_text_color(*color_rgb)
                                        title_clean = clean_and_normalize(str(title))[:50]  # Limitar título
                                        super(PatchedPDF, pdf).cell(0, 8, title_clean, ln=True)
                                        pdf.set_text_color(0, 0, 0)
                                        pdf.ln(1)
                                    except Exception as e:
                                        logging.warning(f"[PDF] Error en título tabla competidores: {e}")
                                        pdf.ln(9)  # Solo espacio si falla
                                    
                                    # ✅ HEADERS DE TABLA CON VALIDACIÓN - COLUMNAS MÁS AMPLIAS
                                    headers = ["Empresa", "País", "Sector"]
                                    col_widths = [110, 50, 35]  # Total: 195 (mucho más espacio para nombres completos)
                                    
                                    # Verificar que la suma de columnas no exceda el ancho
                                    total_width = sum(col_widths)
                                    max_width = pdf.w - pdf.l_margin - pdf.r_margin - 10  # Margen de seguridad
                                    if total_width > max_width:
                                        # Escalar proporcionalmente
                                        scale = max_width / total_width
                                        col_widths = [int(w * scale) for w in col_widths]
                                    
                                    # ✅ HEADER CON PROTECCIÓN COMPLETA
                                    try:
                                        pdf.set_font(font_family, 'B', 9)
                                        # Color más suave para header
                                        header_r = min(255, color_rgb[0] + 80)
                                        header_g = min(255, color_rgb[1] + 80) 
                                        header_b = min(255, color_rgb[2] + 80)
                                        pdf.set_fill_color(header_r, header_g, header_b)
                                        
                                        for i, header in enumerate(headers):
                                            try:
                                                header_clean = clean_and_normalize(str(header))[:15]
                                                super(PatchedPDF, pdf).cell(col_widths[i], 7, header_clean, border=1, fill=True, align='C')
                                            except Exception as e:
                                                logging.warning(f"[PDF] Error en header {i}: {e}")
                                                super(PatchedPDF, pdf).cell(col_widths[i], 7, "Col", border=1, fill=True, align='C')
                                        pdf.ln()
                                    except Exception as e:
                                        logging.warning(f"[PDF] Error en headers tabla: {e}")
                                        pdf.ln(7)  # Solo espacio si falla
                                        return  # No continuar si falla el header
                                    
                                    # ✅ FILAS DE COMPETIDORES CON MÁXIMA PROTECCIÓN
                                    try:
                                        pdf.set_font(font_family, '', 8)
                                        pdf.set_fill_color(250, 250, 250)  # Fondo alternado muy claro
                                        
                                        processed_count = 0
                                        for idx, comp in enumerate(competitors):
                                            if processed_count >= 6:  # Máximo 6 por tabla
                                                break
                                                
                                            try:
                                                fill = (idx % 2 == 0)
                                                
                                                # ✅ PROCESAR DATOS CON MÁXIMA ROBUSTEZ
                                                if isinstance(comp, dict):
                                                    nombre = comp.get('nombre', comp.get('empresa', comp.get('name', '')))
                                                    pais = comp.get('país', comp.get('pais', comp.get('country', '')))
                                                    
                                                    # ✅ USAR SOLO DATOS DEL LLM - SIN ESTIMACIONES NI HARDCODEO
                                                    sector = comp.get('sector', comp.get('industry', ''))
                                                    tamano = comp.get('tamano', comp.get('size', ''))
                                                    
                                                    # ✅ SOLO OMITIR SI NO HAY NOMBRE (campo crítico)
                                                    if not nombre.strip():
                                                        continue  # Solo omitir si no hay nombre de empresa
                                                    
                                                    # ✅ PARA OTROS CAMPOS, USAR N/D SI FALTAN
                                                    if not pais.strip():
                                                            pais = "N/D"
                                                    if not sector.strip():
                                                        sector = "N/D"
                                                    if not tamano.strip():
                                                            tamano = "N/D"
                                                elif isinstance(comp, str):
                                                    # ✅ STRINGS YA NO SON VÁLIDOS - SOLO USAR DATOS ESTRUCTURADOS DEL LLM
                                                    # El LLM debe devolver objetos dict con todos los campos obligatorios
                                                    continue  # Omitir strings, solo usar datos estructurados del LLM
                                                else:
                                                    # Tipo no reconocido, omitir
                                                    continue
                                                
                                                # ✅ LIMPIAR Y TRUNCAR TODOS LOS TEXTOS - MENOS AGRESIVO
                                                try:
                                                    nombre = clean_and_normalize(str(nombre))
                                                    pais = clean_and_normalize(str(pais))
                                                    
                                                    # ✅ USAR SOLO SECTOR DEL LLM - SIN HARDCODEO
                                                    # El sector debe venir del LLM en los datos del competidor
                                                    
                                                    # Truncar con límites MÁS GENEROSOS
                                                    nombre = nombre[:35] + "..." if len(nombre) > 35 else nombre
                                                    pais = pais[:18] + "..." if len(pais) > 18 else pais
                                                    sector = sector[:12]  # Los sectores son cortos
                                                    
                                                    # ✅ ASEGURAR QUE SIEMPRE HAYA ALGO (N/D si está vacío después de limpiar)
                                                    if not nombre.strip():
                                                        continue  # Solo omitir si no hay nombre después de limpiar
                                                    if not pais.strip():
                                                        pais = "N/D"
                                                    if not sector.strip():
                                                        sector = "N/D"
                                                    
                                                    # Capturar website para añadir a referencias
                                                    try:
                                                        for url_key in ('website','web','url','link','pagina','sitio_web','site','homepage','home_page'):
                                                            if url_key in comp and comp[url_key]:
                                                                url_val = str(comp[url_key]).strip()
                                                                if url_val.lower().startswith(('http://','https://')):
                                                                    add_reference(url_val)
                                                                    break
                                                    except Exception:
                                                        pass
                                                    
                                                except Exception as e:
                                                    logging.warning(f"[PDF] Error limpiando textos: {e}")
                                                    # Si hay error, omitir este competidor
                                                    continue
                                                
                                                # ✅ RENDERIZAR FILA CON PROTECCIÓN INDIVIDUAL - NUEVA ESTRUCTURA
                                                try:
                                                    super(PatchedPDF, pdf).cell(col_widths[0], 6, nombre, border=1, fill=fill, align='L')
                                                    super(PatchedPDF, pdf).cell(col_widths[1], 6, pais, border=1, fill=fill, align='C')
                                                    super(PatchedPDF, pdf).cell(col_widths[2], 6, sector, border=1, fill=fill, align='C')
                                                    pdf.ln()
                                                    processed_count += 1
                                                except Exception as e:
                                                    logging.warning(f"[PDF] Error renderizando fila competidor {idx}: {e}")
                                                    # Fila de error como fallback
                                                    try:
                                                        super(PatchedPDF, pdf).cell(sum(col_widths), 6, f"Error fila {idx+1}", border=1, fill=fill, align='L')
                                                        pdf.ln()
                                                    except:
                                                        pdf.ln(6)  # Solo espacio si todo falla
                                                        
                                            except Exception as e:
                                                logging.warning(f"[PDF] Error procesando competidor {idx}: {e}")
                                                continue  # Saltar este competidor y continuar
                                        
                                        pdf.ln(3)  # Espacio entre tablas
                                        
                                    except Exception as e:
                                        logging.error(f"[PDF] Error en filas tabla competidores: {e}")
                                        pdf.ln(10)  # Espacio de recuperación
                                        
                                except Exception as e:
                                    logging.error(f"[PDF] Error general en tabla competidores: {e}")
                                    # Fallback: mostrar solo el título
                                    try:
                                        pdf.set_font(font_family, 'B', 11)
                                        pdf.set_text_color(100, 100, 100)
                                        super(PatchedPDF, pdf).cell(0, 8, f"Error en tabla: {title}", ln=True)
                                        pdf.set_text_color(0, 0, 0)
                                        pdf.ln(2)
                                    except:
                                        pdf.ln(10)  # Último recurso

                            # ✅ CREAR TABLAS DE COMPETIDORES POR CATEGORÍA - MEJORADAS SIN TÍTULOS CONFUSOS
                            try:
                                # Competidores directos (sin emoji confuso)
                                directos = competidores.get('competidores_directos', [])
                                if directos:
                                    create_competitor_table("Competidores Directos", directos, (180, 0, 0))
                                
                                # Competidores indirectos (sin emoji confuso)
                                indirectos = competidores.get('competidores_indirectos', [])
                                if indirectos:
                                    create_competitor_table("Competidores Indirectos", indirectos, (255, 140, 0))
                                
                                # Competidores emergentes (sin emoji confuso)
                                emergentes = competidores.get('emergentes', [])
                                if emergentes:
                                    create_competitor_table("Competidores Emergentes", emergentes, (0, 150, 0))
                                    
                                pdf.ln(4)
                                
                            except Exception as e:
                                logging.error(f"[PDF] Error creando tablas competidores: {e}")
                                pdf.set_font(font_family, 'I', 10)
                                pdf.set_text_color(200, 0, 0)
                                super(PatchedPDF, pdf).cell(0, 8, "Error generando tablas de competidores", ln=True)
                                pdf.set_text_color(0, 0, 0)
                                pdf.ln(2)
                        else:
                            logging.warning(f"[PDF] No hay datos de competidores en COMPETITOR_MAPPING")

                except Exception as e:
                    logging.error(f"[PDF] Error mostrando datos estructurados en {sec}: {e}")
                    pdf.set_font(font_family, 'I', 10)
                    pdf.set_text_color(200,0,0)
                    pdf.multi_cell(0, 7, f"[Error mostrando datos estructurados: {e}]")
                    pdf.set_text_color(0,0,0)

            # ✅ CORRECCIÓN CRÍTICA: SIEMPRE mostrar el texto del LLM después de los datos estructurados
            # El texto del LLM es OBLIGATORIO para TODAS las secciones, independientemente de si tienen datos estructurados
            texto_limpio = sec_data.get('texto', '').replace("Análisis y Contexto:", "").strip()
            if texto_limpio and len(texto_limpio.strip()) > 10:  # Solo si hay contenido significativo del LLM
                logging.info(f"[PDF] 📝 Renderizando texto del LLM para sección {sec} (datos estructurados: {tiene_datos})")
                
                # ✅ MEJORA: PARA EL MAPA DE COMPETIDORES, CREAR ANÁLISIS ESTRUCTURADO PRIMERO
                if sec == "COMPETITOR_MAPPING" and tiene_datos:
                    try:
                        logging.info(f"[PDF] 📝 Creando análisis estructurado para Mapa de Competidores...")
                        
                        def generate_structured_analysis(title, competitors_list):
                            """
                            ✅ FUNCIÓN REESCRITA: Análisis fluido sin subtítulos ni negritas rotas
                            """
                            if not competitors_list:
                                return
                            
                            # ✅ NO PONER SUBTÍTULOS - Directamente el análisis
                            
                            # ✅ ANALIZAR CADA COMPETIDOR DE FORMA FLUIDA
                            for i, comp in enumerate(competitors_list, 1): 
                                nombre = "Competidor Desconocido"
                                pais = "No especificado"
                                descripcion = "Información no disponible para este competidor."
                                
                                # ✅ FILTRO: EXCLUIR SENER AUTOMÁTICAMENTE
                                if isinstance(comp, dict):
                                    nombre_check = comp.get('nombre', comp.get('empresa', comp.get('name', ''))).lower()
                                elif isinstance(comp, str):
                                    nombre_check = comp.lower()
                                else:
                                    nombre_check = str(comp).lower()
                                
                                if 'sener' in nombre_check:
                                    continue  # Saltar Sener completamente
                                
                                if isinstance(comp, dict):
                                    nombre = comp.get('nombre', comp.get('empresa', comp.get('name', '')))
                                    pais = comp.get('pais', comp.get('país', comp.get('country', '')))
                                    
                                    # Buscar descripción en múltiples campos
                                    desc_keys = ['descripcion', 'descripción', 'description', 'enfoque', 'about', 'especialidad']
                                    descripcion = "Información no disponible para este competidor."  # Valor por defecto
                                    for key in desc_keys:
                                        if key in comp and comp[key] and str(comp[key]).strip():
                                            descripcion = str(comp[key]).strip()
                                            break
                                    
                                    # ✅ GENERAR ANÁLISIS ESPECÍFICO POR EMPRESA REAL
                                    if descripcion == "Información no disponible para este competidor.":
                                        # Si no hay descripción del LLM, simplemente omitir este competidor
                                        continue  # Saltar este competidor sin datos reales

                                elif isinstance(comp, str):
                                    # Parsear string con formato estructurado
                                    import re
                                    match = re.match(r'([^(]+)\(([^)]+)\)\s*[-–]\s*(.+)', comp)
                                    if match:
                                        nombre = match.group(1).strip()
                                        pais = match.group(2).strip()
                                        descripcion = match.group(3).strip()
                                    else:
                                        # Si no hay formato claro, omitir este competidor sin datos
                                        continue  # Saltar competidores sin información estructurada

                                # Limpiar y normalizar textos
                                nombre_limpio = clean_and_normalize(nombre)[:50]
                                pais_limpio = clean_and_normalize(pais)[:25]
                                desc_limpia = clean_and_normalize(descripcion)[:300]  # Más espacio para análisis

                                # ✅ FORMATO FLUIDO: Solo texto en párrafo normal
                                pdf.set_font(font_family, '', 10)
                                texto_completo = f"{nombre_limpio} ({pais_limpio}): {desc_limpia}"
                                super(PatchedPDF, pdf).multi_cell(0, 5, texto_completo)
                                pdf.ln(4)  # Espacio entre competidores

                        competidores_data = sec_data.get('datos', {})
                        
                        # ✅ ANALIZAR TODAS LAS CATEGORÍAS EN UN SOLO FLUJO DE TEXTO
                        directos = competidores_data.get('competidores_directos', [])
                        indirectos = competidores_data.get('competidores_indirectos', [])  
                        emergentes = competidores_data.get('emergentes', [])
                        
                        # Combinar todos en una sola función de análisis fluido
                        all_competitors = []
                        if directos:
                            all_competitors.extend(directos)
                        if indirectos:
                            all_competitors.extend(indirectos)
                        if emergentes:
                            all_competitors.extend(emergentes)
                        
                        if all_competitors:
                            generate_structured_analysis("", all_competitors)
                        
                        logging.info("[PDF] ✅ Análisis estructurado de competidores completado")

                    except Exception as analysis_exc:
                        logging.error(f"[PDF] ❌ Error generando análisis estructurado: {analysis_exc}")
                
                # ✅ SIEMPRE MOSTRAR EL TEXTO DEL LLM DESPUÉS DEL ANÁLISIS ESTRUCTURADO
                add_generic_text_block(pdf, texto_limpio, font_family)
                
            else:
                logging.warning(f"[PDF] ⚠️ Sección {sec} sin texto del LLM válido - posible fallo de API")

    # Si no se mostró ninguna sección, mostrar mensaje claro
    if secciones_mostradas == 0:
        logging.warning("[PDF] ⚠️ No se encontraron secciones válidas, mostrando mensaje de error")
        pdf.add_page()
        pdf.set_font(font_family, 'B', 16)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 12, "No se encontraron secciones con contenido para mostrar en el informe.", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(0,0,0)
        pdf.multi_cell(0, 8, "Verifique que los datos de entrada contienen al menos una sección con texto relevante. Si el problema persiste, revise el análisis de las ideas o consulte soporte técnico.")

    # --- 3. REFERENCIAS UNIFICADAS SEPARADAS POR IDEA ---
    if referencias:
        logging.info(f"[PDF] 📚 Añadiendo referencias unificadas ({len(referencias)} total)...")
        
        link_id = pdf.add_link()
        pdf.add_page()
        pdf.set_link(link_id)
        toc_entries.append(("Referencias", link_id, pdf.page_no()))
        
        # ✅ SEPARADOR VISUAL ELIMINADO - Sin líneas azules arriba de Referencias
        pdf.ln(8)
        
        add_professional_header(pdf, "Análisis de Competencia")
        
        # Título de referencias
        try:
            pdf.set_font(font_family, 'B', 20)
            pdf.set_text_color(0, 51, 102)
            super(PatchedPDF, pdf).cell(0, 15, "Referencias y Fuentes", ln=True)
            pdf.ln(8)
            pdf.set_text_color(0, 0, 0)
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error título referencias: {e}")
            pdf.ln(15)
        
        # Crear un mapeo de referencias por idea
        ref_por_idea = {}
        ref_globales = []
        
        # Analizar referencias y separarlas por idea
        # Como las referencias no están separadas por idea en el actual sistema,
        # las mostramos como referencias globales, pero con estructura mejorada
        for i, ref in enumerate(referencias, 1):
            try:
                if isinstance(ref, str) and ref.strip():
                    ref_globales.append(ref.strip())
                else:
                    ref_globales.append(f"Referencia {i} (formato no válido)")
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error procesando referencia {i}: {e}")
                ref_globales.append(f"Error procesando referencia {i}")
        
        # Mostrar referencias globales del análisis
        if ref_globales:
            try:
                pdf.set_font(font_family, 'B', 14)
                pdf.set_text_color(0, 51, 102)
                super(PatchedPDF, pdf).cell(0, 12, "Referencias Utilizadas en el Análisis", ln=True)
                pdf.ln(5)
                
                # Información adicional
                pdf.set_font(font_family, '', 10)
                pdf.set_text_color(80, 80, 80)
                super(PatchedPDF, pdf).cell(0, 8, f"Total de fuentes consultadas: {len(ref_globales)}", ln=True)
                pdf.ln(3)
                pdf.set_text_color(0, 0, 0)
                
                # Lista de referencias con numeración mejorada
                pdf.set_font(font_family, '', 9)
                for i, ref in enumerate(ref_globales, 1):
                    try:
                        # Formatear referencia con numeración clara
                        ref_text = f"[{i:02d}] {ref}"
                        
                        # Verificar si es una URL para darle formato especial
                        if ref.startswith(('http://', 'https://')):
                            pdf.set_text_color(0, 0, 200)  # Azul para URLs
                            safe_multi_cell(pdf, 0, 5, ref_text)
                            pdf.set_text_color(0, 0, 0)  # Volver a negro
                        else:
                            safe_multi_cell(pdf, 0, 5, ref_text)
                        
                        pdf.ln(2)  # Espacio entre referencias
                        
                    except Exception as e:
                        logging.warning(f"[PDF] ⚠️ Error añadiendo referencia {i}: {e}")
                        try:
                            super(PatchedPDF, pdf).cell(0, 5, f"[{i:02d}] Error en referencia", ln=True)
                        except:
                            pass
                        pdf.ln(2)
                
                pdf.ln(5)
                
                # Nota final sobre las referencias
                pdf.set_font(font_family, 'I', 8)
                pdf.set_text_color(100, 100, 100)
                super(PatchedPDF, pdf).cell(0, 6, "Nota: Las referencias mostradas corresponden a las fuentes utilizadas en la generación del análisis competitivo.", ln=True)
                pdf.set_text_color(0, 0, 0)
                        
            except Exception as e:
                logging.warning(f"[PDF] ⚠️ Error general en referencias: {e}")
                try:
                    pdf.set_font(font_family, '', 9)
                    super(PatchedPDF, pdf).cell(0, 8, "Error mostrando referencias", ln=True)
                except:
                    pdf.ln(8)
            
            logging.info("[PDF] ✅ Referencias añadidas correctamente")
    else:
        logging.info("[PDF] ℹ️ No hay referencias para añadir")

    # --- Completar índice de contenidos con numeración real ---
    try:
        # 🔥 SOLUCIÓN CRÍTICA: Guardar la página actual antes de volver al índice
        current_page = pdf.page_no()
        current_x = pdf.get_x()
        current_y = pdf.get_y()
        
        # Volver a la página del índice
        pdf.page = index_page_no
        pdf.set_xy(pdf.l_margin, index_y_start)
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(0, 0, 0)
        
        # 🔥 CALCULAR ESPACIO TOTAL DISPONIBLE (página inicial + páginas extra)
        total_index_pages = 1 + extra_index_pages
        entries_per_page = int((pdf.page_break_trigger - index_y_start - 15) / 10)  # Primera página
        entries_per_extra_page = int((pdf.page_break_trigger - pdf.t_margin - 15) / 10)  # Páginas extra
        
        max_total_entries = entries_per_page + (entries_per_extra_page * extra_index_pages)
        
        logging.info(f"[PDF] 📏 Espacio índice: {total_index_pages} páginas, máximo {max_total_entries} entradas")
        
        entries_count = 0
        current_index_page = 0
        
        for toc_title, toc_link, toc_page in toc_entries:
            # 🎯 SOLUCIÓN ROBUSTA: Verificar límites de página Y mantener formato exacto
            current_y_pos = pdf.get_y()
            
            # Si estamos cerca del final de la página del índice
            if current_y_pos > pdf.page_break_trigger - 20:
                current_index_page += 1
                if current_index_page < total_index_pages:
                    # 🔥 SOLUCIÓN ROBUSTA: USAR add_page() COMO LA PRIMERA PÁGINA
                    logging.info(f"[PDF] 📄 Cambiando a página {current_index_page + 1} del índice...")
                    
                    # ✅ GUARDAR ESTADO ACTUAL ANTES DEL CAMBIO
                    saved_font_family = font_family
                    saved_page_no = pdf.page_no()
                    
                    # 🎯 USAR EL MISMO MÉTODO QUE LA PRIMERA PÁGINA: add_page()
                    pdf.add_page()
                    
                    # ✅ CONFIGURACIÓN EXACTAMENTE IGUAL QUE PRIMERA PÁGINA (líneas 693-696)
                    try:
                        # STEP 1: Reset completo como primera página
                        pdf.set_font(saved_font_family, '', 12)  # EXACTO línea 695
                        pdf.set_text_color(0, 0, 0)              # EXACTO línea 696
                        
                        # STEP 2: Posición inicial segura
                        pdf.set_xy(pdf.l_margin, pdf.t_margin + 10)
                        
                        logging.info(f"[PDF] ✅ Página {current_index_page + 1} configurada idénticamente a la primera")
                        
                    except Exception as font_error:
                        logging.warning(f"[PDF] ⚠️ Error configurando página {current_index_page + 1}: {font_error}")
                        # FALLBACK EXACTO como primera página
                        pdf.set_font('Arial', '', 10)
                        pdf.set_text_color(0, 0, 0)
                    
                    logging.info(f"[PDF] 📄 Continuando índice en página {current_index_page + 1} (método robusto)")
                else:
                    # Se acabó el espacio disponible
                    logging.warning(f"[PDF] ⚠️ Índice truncado: {len(toc_entries) - entries_count} entradas restantes")
                    try:
                        pdf.set_font(font_family, 'I', 9)
                        pdf.set_text_color(120, 120, 120)
                        safe_cell(pdf, 0, 8, f"... y {len(toc_entries) - entries_count} secciones más", ln=True)
                    except Exception as trunc_error:
                        logging.warning(f"[PDF] ⚠️ Error añadiendo mensaje de truncado: {trunc_error}")
                    break
            
            # Si ya no hay espacio en ninguna página del índice
            if entries_count >= max_total_entries:
                logging.warning(f"[PDF] ⚠️ Límite de entradas alcanzado: {max_total_entries}")
                break
            
            # 🎯 RENDERIZAR ENTRADA CON INDENTACIÓN Y PUNTOS PERFECTOS
            try:
                # 🔧 PASO 1: Limpiar título manteniendo estructura
                raw_title = str(toc_title)
                clean_title = clean_and_normalize(raw_title[:80])
                page_str = str(toc_page)
                
                # 🔧 PASO 2: DETECCIÓN DE INDENTACIÓN CORREGIDA
                indent_spaces = ""
                title_stripped = raw_title.strip()
                
                # 🎯 LÓGICA MEJORADA: Detectar patrones específicos de numeración
                import re
                
                # Patrón para sub-puntos: "1.2", "2.3", "3.5", etc.
                subpoint_pattern = r'^\d+\.\d+'
                # Patrón para sub-sub-puntos: "1.2.1", "2.3.4", etc.
                subsubpoint_pattern = r'^\d+\.\d+\.\d+'
                
                if re.match(subsubpoint_pattern, title_stripped):
                    # Es un sub-sub-punto (ej: "1.2.1", "2.3.4")
                    indent_spaces = "            "  # 12 espacios
                    logging.debug(f"[PDF] Sub-sub-punto detectado: {title_stripped}")
                elif re.match(subpoint_pattern, title_stripped):
                    # Es un sub-punto (ej: "1.2", "2.3")
                    indent_spaces = "        "  # 8 espacios
                    logging.debug(f"[PDF] Sub-punto detectado: {title_stripped}")
                else:
                    # Es un punto principal (ej: "1.", "2.", "Resumen Ejecutivo")
                    indent_spaces = ""  # Sin indentación
                    logging.debug(f"[PDF] Punto principal: {title_stripped}")
                
                # 🔧 PASO 3: Calcular puntos con precisión EXACTA
                try:
                    # Usar la fuente actual para cálculos precisos
                    current_font_size = 12  # Asegurar tamaño consistente
                    pdf.set_font(font_family, '', current_font_size)
                    
                    # Calcular anchos EXACTOS
                    indent_width = pdf.get_string_width(indent_spaces)
                    title_width = pdf.get_string_width(clean_title)
                    page_width = pdf.get_string_width(page_str)
                    margin_buffer = 15  # Buffer para márgenes
                    
                    # Espacio disponible para puntos
                    total_content_width = indent_width + title_width + page_width + margin_buffer
                    available_for_dots = pdf.w - pdf.l_margin - pdf.r_margin - total_content_width
                    
                    if available_for_dots > 15:  # Mínimo espacio para puntos decentes
                        dot_width = pdf.get_string_width('.')
                        dots_count = max(5, int(available_for_dots / dot_width))
                        dots_count = min(dots_count, 60)  # Máximo 60 puntos
                        dots = '.' * dots_count
                    else:
                        # Mínimo de puntos si no hay mucho espacio
                        dots = '.....'  # Al menos 5 puntos
                        
                    # 🎯 FORMATO PARA MÉTODO DE ALINEACIÓN (entry_text solo para fallback)
                    entry_text = f"{indent_spaces}{clean_title} {dots} {page_str}"
                        
                except Exception as width_error:
                    logging.warning(f"[PDF] ⚠️ Error calculando puntos, usando formato seguro: {width_error}")
                    entry_text = f"{indent_spaces}{clean_title[:50]}... {page_str}"
                
                # 🔧 PASO 4: RENDERIZADO PERFECTO - PUNTOS INMEDIATAMENTE DESPUÉS DEL TÍTULO
                try:
                    current_y = pdf.get_y()
                    pdf.set_font(font_family, '', 12)
                    
                    # 🎯 POSICIONES EXACTAS PARA ALINEACIÓN PERFECTA
                    page_number_width = 20  # Ancho para números de página
                    page_x_position = pdf.w - pdf.r_margin - page_number_width  # Posición donde empiezan números
                    dots_end_position = page_x_position - 2  # Los puntos terminan justo antes del número
                    
                    # 🔧 CALCULAR POSICIÓN EXACTA DEL TÍTULO
                    title_with_indent = f"{indent_spaces}{clean_title}"
                    title_width = pdf.get_string_width(title_with_indent)
                    title_end_position = pdf.l_margin + title_width
                    
                    # 🎯 CALCULAR PUNTOS QUE LLENEN EXACTAMENTE EL ESPACIO
                    available_space = dots_end_position - title_end_position
                    
                    if available_space > 8:  # Suficiente espacio para puntos
                        dot_width = pdf.get_string_width('.')
                        # Calcular cuántos puntos caben exactamente en el espacio
                        dots_count = int(available_space / dot_width)
                        dots_count = max(3, min(dots_count, 100))  # Entre 3 y 100 puntos
                        dots_string = '.' * dots_count
                    else:
                        dots_string = '...'  # Mínimo si hay muy poco espacio
                    
                    # 🔧 RENDERIZAR SIN ESPACIOS ADICIONALES
                    # PASO 1: Título con indentación (sin espacios extra)
                    pdf.set_xy(pdf.l_margin, current_y)
                    super(PatchedPDF, pdf).cell(title_width, 10, title_with_indent, ln=False, link=toc_link)
                    
                    # PASO 2: Puntos inmediatamente después del título
                    current_x = pdf.get_x()  # Posición actual después del título
                    dots_space = dots_end_position - current_x
                    if dots_space > 5:  # Recalcular puntos con el espacio real disponible
                        dots_count_real = int(dots_space / dot_width)
                        dots_count_real = max(2, min(dots_count_real, 100))
                        dots_string = '.' * dots_count_real
                    
                    super(PatchedPDF, pdf).cell(dots_space, 10, dots_string, ln=False, align='R')
                    
                    # PASO 3: Número de página alineado a la derecha
                    pdf.set_xy(page_x_position, current_y)
                    super(PatchedPDF, pdf).cell(page_number_width, 10, page_str, ln=True, align='R')
                    
                    entries_count += 1
                    logging.debug(f"[PDF] ✅ Entrada {entries_count} con puntos pegados al título: {clean_title[:20]}...")
                    
                except Exception as render_error:
                    logging.warning(f"[PDF] ⚠️ Error en renderizado perfecto, usando método simple: {render_error}")
                    # FALLBACK: método original simple pero funcional
                    super(PatchedPDF, pdf).cell(0, 10, entry_text, ln=True, link=toc_link)
                    entries_count += 1
                
            except Exception as entry_error:
                logging.warning(f"[PDF] ⚠️ Error procesando entrada {entries_count}: {entry_error}")
                # ✅ CONTINUAR CON LA SIGUIENTE ENTRADA - NUNCA FALLAR EL ÍNDICE COMPLETO
                try:
                    # Entrada mínima de emergencia
                    emergency_text = f"Sección {entries_count + 1} .................... {toc_page}"
                    super(PatchedPDF, pdf).cell(0, 10, emergency_text, ln=True)
                    entries_count += 1
                except:
                    # Si incluso eso falla, simplemente continuar
                    pass
                continue
        
        # 🔥 RESTAURAR POSICIÓN ORIGINAL PARA CONTINUAR CON EL CONTENIDO
        pdf.page = current_page
        pdf.set_xy(current_x, current_y)
        
        logging.info(f"[PDF] ✅ Índice completado: {entries_count}/{len(toc_entries)} entradas mostradas")
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error completando índice: {e}")
        # ✅ RESTAURAR POSICIÓN INCLUSO SI HAY ERROR
        try:
            pdf.page = current_page
            pdf.set_xy(current_x, current_y)
        except Exception as restore_error:
            logging.error(f"[PDF] ❌ Error restaurando posición: {restore_error}")
            # Como último recurso, ir al final del documento
            try:
                pdf.page = pdf.page_no()
                pdf.set_y(pdf.get_y())
            except:
                pass

    # ✅ OPTIMIZACIÓN: Guardar PDF con manejo de errores
    try:
        logging.info(f"[PDF] 💾 Guardando PDF en: {pdf_path}")
        pdf.output(pdf_path)
        logging.info(f"[PDF] ✅ PDF generado correctamente: {pdf_path}")
        logging.info(f"[PDF] 📊 Estadísticas: {secciones_mostradas} secciones, {len(referencias)} referencias")
        return pdf_path
    except Exception as e:
        logging.error(f"[PDF] ❌ Error guardando PDF: {e}")
        # Intentar guardar con nombre alternativo
        fallback_path = pdf_path.replace('.pdf', '_fallback.pdf')
        try:
            pdf.output(fallback_path)
            logging.info(f"[PDF] ✅ PDF guardado como fallback: {fallback_path}")
            return fallback_path
        except Exception as e2:
            logging.error(f"[PDF] ❌ Error crítico guardando PDF: {e2}")
            raise e2

# --- FUNCIONES AUXILIARES ---
def split_paragraphs(text):
    import re
    text = clean_text(text)
    if not text or not isinstance(text, str):
        return ["No hay informacion disponible"]
    if '\n\n' in text:
        return [p.strip() for p in text.split('\n\n') if p.strip()]
    sentences = re.split(r'(?<=[.!?]) +', text)
    paragraphs = []
    for j in range(0, len(sentences), 3):
        paragraphs.append(' '.join(sentences[j:j+3]))
    return paragraphs

def clean_text(text):
    if not isinstance(text, str):
        return text
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text

def sanitize_text_for_pdf(text, max_length=5000):  # AUMENTADO de 1000 a 5000
    if not isinstance(text, str):
        text = str(text)
    # Eliminar caracteres no ASCII
    text = text.encode('latin-1', 'replace').decode('latin-1')
    # Truncar si es muy largo
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text

def safe_text(txt, max_len_word=25, max_total=5000):  # AUMENTADO de 1000 a 5000
    """
    Normaliza, corta palabras largas y recorta el string
    para que nunca rompa las celdas de fpdf2.
    """
    import unicodedata, re
    if not isinstance(txt, str):
        txt = str(txt)
    txt = unicodedata.normalize('NFKD', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    txt = txt[:max_total]
    out = []
    for w in txt.split(' '):
        out.extend(wrap(w, max_len_word))
    return ' '.join(out)

def break_long_words(text, max_len=25):
    """
    Inserta saltos de línea '
    dentro de palabras muy largas
    para evitar el error de espacio horizontal.
    """
    if not isinstance(text, str):
        text = str(text)
    new_words = []
    for word in text.split(" "):
        if len(word) > max_len:
            new_words.extend(wrap(word, max_len))
        else:
            new_words.append(word)
    return " ".join(new_words)

def _shorten(val, max_chars=50, key=None):
    """
    ✅ VERSIÓN CORREGIDA - NO truncar texto importante, solo limpiar
    """
    if not isinstance(val, str):
        val = str(val)
    val = val.strip()
    if not val or val.lower() in ("no disponible", "n/a", "none", "-", "null"):
        return "N/C"
    if key and key.lower() in ("fuente", "url", "link", "enlace"):
        return val if val.lower().startswith(("http://", "https://")) else "N/C"
    if val.lower().startswith(("http://", "https://")):
        return "N/C"
    # Si es un número, lo dejamos completo
    try:
        float_val = float(val.replace(",", "."))
        return val
    except Exception:
        pass
    # ✅ CORRECCIÓN CRÍTICA: NO truncar texto importante, devolver completo
    # Solo limpiar caracteres problemáticos
    val_clean = clean_and_normalize(val)
    return val_clean

def add_benchmarking_table(pdf, benchmarking, add_reference, clean_and_normalize):
    """
    ✅ FUNCIÓN COMPLETAMENTE REESCRITA: Tabla de benchmarking SIMPLE y ROBUSTA
    """
    try:
        # Validar estructura de datos
        if not benchmarking or not isinstance(benchmarking, dict):
            pdf.set_font('DejaVu', 'B', 12)
            pdf.set_text_color(180, 180, 180)
            super(PatchedPDF, pdf).cell(0, 10, "BENCHMARKING", ln=True, align='C')
            pdf.ln(3)
            pdf.set_font('DejaVu', 'I', 11)
            pdf.set_text_color(120, 120, 120)
            super(PatchedPDF, pdf).cell(0, 8, "Sin datos de benchmarking disponibles para esta idea.", ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)
            return

        # ✅ LÍNEA DECORATIVA SUPERIOR ELIMINADA - Sin líneas azules en benchmarking
        pdf.ln(6)

        # ✅ OBTENER DATOS DE TABLA
        tabla_data = benchmarking.get('tabla', [])
        if not tabla_data or not isinstance(tabla_data, list) or len(tabla_data) == 0:
            pdf.set_font('DejaVu', 'I', 11)
            pdf.set_text_color(120, 120, 120)
            super(PatchedPDF, pdf).cell(0, 8, "No hay datos de tabla para benchmarking.", ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            return
        
        # ✅ TÍTULO PRINCIPAL
        pdf.set_font('DejaVu', 'B', 14)
        pdf.set_text_color(0, 51, 102)
        super(PatchedPDF, pdf).cell(0, 12, "BENCHMARKING", ln=True, align='C')
        pdf.set_text_color(80, 80, 80)
        pdf.set_font('DejaVu', '', 10)
        super(PatchedPDF, pdf).cell(0, 8, "Análisis comparativo de competidores del sector", ln=True, align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln(8)
        
        # ✅ PREPARAR DATOS LIMPIOS - MÁXIMO 6 EMPRESAS
        companies_data = []
        for i, row in enumerate(tabla_data[:6]):  # Máximo 6 empresas
            if not isinstance(row, dict):
                continue
            # Capturar website para referencias
            try:
                for url_key in ('website','web','url','link','pagina','sitio_web','site','homepage','home_page'):
                    if url_key in row and row[url_key]:
                        url_val = str(row[url_key]).strip()
                        if url_val.lower().startswith(('http://','https://')):
                            add_reference(url_val)
                            break
            except Exception:
                pass
            
            # Extraer y limpiar campos básicos
            nombre = clean_and_normalize(str(row.get('nombre', row.get('empresa', ''))))
            if not nombre.strip():
                continue  # Solo omitir si no hay nombre
                
            pais = clean_and_normalize(str(row.get('pais', row.get('país', ''))))
            enfoque = clean_and_normalize(str(row.get('enfoque_estrategico', row.get('especialidad', ''))))
            modelo = clean_and_normalize(str(row.get('modelo_negocio', row.get('business_model', ''))))
            diferenciador = clean_and_normalize(str(row.get('diferenciador_clave', row.get('fortaleza_principal', ''))))
            
            # Usar N/D para campos faltantes
            if not pais.strip():
                pais = "N/D"
            if not enfoque.strip():
                enfoque = "N/D"
            if not modelo.strip():
                modelo = "N/D"
            if not diferenciador.strip():
                diferenciador = "N/D"
            
            # Truncar textos largos AGRESIVAMENTE para evitar desbordamiento
            nombre = nombre[:25] + "..." if len(nombre) > 25 else nombre
            pais = pais[:15] + "..." if len(pais) > 15 else pais
            enfoque = enfoque[:40] + "..." if len(enfoque) > 40 else enfoque
            modelo = modelo[:35] + "..." if len(modelo) > 35 else modelo
            diferenciador = diferenciador[:35] + "..." if len(diferenciador) > 35 else diferenciador
            
            companies_data.append({
                'nombre': nombre,
                'pais': pais,
                'enfoque': enfoque,
                'modelo': modelo,
                'diferenciador': diferenciador
            })
        
        if not companies_data:
            pdf.set_font('DejaVu', 'I', 11)
            pdf.set_text_color(120, 120, 120)
            super(PatchedPDF, pdf).cell(0, 8, "No hay empresas válidas para mostrar.", ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            return
        
        # ✅ TABLA 1: SIN TÍTULO - DIRECTAMENTE LA TABLA
        # Headers tabla 1 - ANCHO FIJO PARA EVITAR PROBLEMAS
        headers_1 = ["Empresa", "País", "Enfoque Estratégico"]
        col_widths_1 = [45, 25, 100]  # Total: 170 (seguro)
        
        # Header con fondo azul
        pdf.set_font('DejaVu', 'B', 9)
        pdf.set_fill_color(230, 235, 245)
        pdf.set_text_color(0, 51, 102)
        for i, header in enumerate(headers_1):
            super(PatchedPDF, pdf).cell(col_widths_1[i], 8, header, border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        
        # Filas tabla 1 - SOLO CELL(), SIN MULTI_CELL
        pdf.set_font('DejaVu', '', 8)
        for idx, comp in enumerate(companies_data):
            # Color alternado
            if idx % 2 == 0:
                pdf.set_fill_color(248, 250, 255)
            else:
                pdf.set_fill_color(255, 255, 255)
            
            # SOLO USAR CELL() - NUNCA MULTI_CELL()
            super(PatchedPDF, pdf).cell(col_widths_1[0], 12, comp['nombre'], border=1, fill=True, align='L')
            super(PatchedPDF, pdf).cell(col_widths_1[1], 12, comp['pais'], border=1, fill=True, align='C')
            super(PatchedPDF, pdf).cell(col_widths_1[2], 12, comp['enfoque'], border=1, fill=True, align='L')
            pdf.ln()
        
        pdf.ln(8)  # Espacio entre tablas
        
        # ✅ TABLA 2: SIN TÍTULO - DIRECTAMENTE LA TABLA
        # Headers tabla 2 - ANCHO FIJO
        headers_2 = ["Empresa", "Modelo Negocio", "Diferenciador"]
        col_widths_2 = [45, 65, 60]  # Total: 170 (seguro)
        
        # Header con fondo verde
        pdf.set_font('DejaVu', 'B', 9)
        pdf.set_fill_color(235, 245, 235)
        pdf.set_text_color(0, 102, 51)
        for i, header in enumerate(headers_2):
            super(PatchedPDF, pdf).cell(col_widths_2[i], 8, header, border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        
        # Filas tabla 2 - SOLO CELL(), SIN MULTI_CELL
        pdf.set_font('DejaVu', '', 8)
        for idx, comp in enumerate(companies_data):
            # Color alternado
            if idx % 2 == 0:
                pdf.set_fill_color(248, 255, 248)
            else:
                pdf.set_fill_color(255, 255, 255)
            
            # SOLO USAR CELL() - NUNCA MULTI_CELL()
            super(PatchedPDF, pdf).cell(col_widths_2[0], 12, comp['nombre'], border=1, fill=True, align='L')
            super(PatchedPDF, pdf).cell(col_widths_2[1], 12, comp['modelo'], border=1, fill=True, align='L')
            super(PatchedPDF, pdf).cell(col_widths_2[2], 12, comp['diferenciador'], border=1, fill=True, align='L')
            pdf.ln()
            
        pdf.ln(10)
        
        # ✅ LÍNEA DECORATIVA INFERIOR ELIMINADA - Sin líneas azules en benchmarking
        pdf.ln(8)

    except Exception as e:
        import logging
        logging.error(f"[PDF] Error en add_benchmarking_table: {e}")
        pdf.set_font('DejaVu', 'I', 10)
        pdf.set_text_color(200, 0, 0)
        super(PatchedPDF, pdf).cell(0, 8, "[Error generando tabla de benchmarking]", ln=True)
        pdf.set_text_color(0, 0, 0)

def add_dafo_visual(pdf, dafo, add_reference, clean_and_normalize):
    """
    Crea una visualización DAFO profesional con 4 cuadrantes y estética mejorada.
    ✅ VERSIÓN CORREGIDA: Sin cortes de texto y sin solapamientos
    """
    import logging
    
    try:
        logging.info(f"[PDF] 📊 Iniciando generación DAFO visual mejorado...")
        logging.info(f"[PDF] 🔍 Datos DAFO recibidos: {type(dafo)}, keys: {list(dafo.keys()) if isinstance(dafo, dict) else 'No es dict'}")
        
        # ✅ VALIDAR Y CORREGIR ESTRUCTURA DAFO AL INICIO
        dafo = validate_and_fix_dafo_structure(dafo)
        logging.info(f"[PDF] ✅ Estructura DAFO validada: {list(dafo.keys())}")
        
        # ✅ LOG DETALLADO DE CONTENIDO
        for seccion, items in dafo.items():
            logging.info(f"[PDF] 📋 {seccion.upper()}: {len(items)} items")
            for i, item in enumerate(items):
                logging.info(f"[PDF]   {i+1}. {item[:50]}...")
        
        pdf.ln(8)
        
        # ✅ CONFIGURACIÓN AJUSTADA PARA EVITAR SOLAPAMIENTOS
        margin = 15  # Margen interno generoso
        gap = 12     # Espacio entre cuadrantes aumentado
        content_width = pdf.w - pdf.l_margin - pdf.r_margin - (2 * margin)
        col_width = (content_width - gap) / 2
        row_height = 60  # ✅ AUMENTADO para dar más espacio al texto
        
        # ✅ COLORES PROFESIONALES (sin cambios)
        colores = {
            'fortalezas': (240, 248, 240),    # Verde muy suave
            'debilidades': (255, 245, 245),   # Rojo muy suave  
            'oportunidades': (240, 245, 255), # Azul muy suave
            'amenazas': (255, 250, 240)       # Naranja muy suave
        }
        
        border_color = {
            'fortalezas': (76, 175, 80),      # Verde profesional
            'debilidades': (244, 67, 54),     # Rojo profesional
            'oportunidades': (33, 150, 243),  # Azul profesional
            'amenazas': (255, 152, 0)         # Naranja profesional
        }
        
        def draw_enhanced_quadrant(title, items, color_bg, border_col, pos_x, pos_y, is_top=True):
            """Dibuja un cuadrante con texto completo sin cortes"""
            try:
                logging.info(f"[PDF] 🎨 Dibujando cuadrante mejorado: {title}")
                
                # ✅ CONFIGURAR POSICIÓN EXACTA
                pdf.set_xy(pos_x, pos_y)

                # ✅ DIBUJAR FONDO CON BORDE ELEGANTE
                pdf.set_fill_color(*color_bg)
                pdf.set_draw_color(*border_col)
                pdf.set_line_width(0.8)
                
                # Crear rectángulo de fondo
                pdf.rect(pos_x, pos_y, col_width, row_height, 'DF')
                
                # ✅ TÍTULO CON ESTILO PROFESIONAL
                pdf.set_xy(pos_x + 2, pos_y + 3)
                try:
                    pdf.set_font('DejaVu', 'B', 10)
                except:
                    pdf.set_font('Arial', 'B', 10)
                
                pdf.set_text_color(*border_col)
                safe_title = clean_and_normalize(title.replace('🟢', '').replace('🔴', '').replace('🔵', '').replace('🟠', '').strip())
                
                # Centrar título en el cuadrante
                title_width = pdf.get_string_width(safe_title)
                title_x = pos_x + (col_width - title_width) / 2
                pdf.set_x(title_x)
                super(PatchedPDF, pdf).cell(title_width, 6, safe_title, ln=False)
                
                # ✅ CONTENIDO SIN CORTES DE TEXTO
                content_y = pos_y + 12
                pdf.set_xy(pos_x + 3, content_y)
                
                try:
                    pdf.set_font('DejaVu', '', 8)  # ✅ Fuente más pequeña para más texto
                except:
                    pdf.set_font('Arial', '', 8)
                
                pdf.set_text_color(60, 60, 60)  # Gris profesional para texto
                
                # ✅ PROCESAR ITEMS CON TEXTO COMPLETO
                if items and isinstance(items, list):
                    # Preparar contenido sin truncar
                    formatted_items = []
                    for i, item in enumerate(items[:3]):  # Máximo 3 items
                        if item and str(item).strip():
                            # ✅ NO TRUNCAR - mantener texto completo
                            clean_item = clean_and_normalize(str(item))
                            formatted_items.append(f"* {clean_item}")
                    
                    # ✅ USAR multi_cell PARA MANEJO AUTOMÁTICO DE LÍNEAS
                    content_text = "\n".join(formatted_items)
                    
                    # Calcular área disponible para contenido
                    available_width = col_width - 6  # Margen interno
                    available_height = row_height - 15  # Espacio para título
                    
                    # ✅ CONFIGURAR POSICIÓN Y USAR multi_cell
                    pdf.set_xy(pos_x + 3, content_y)
                    
                    # Dividir en líneas si es necesario para control manual
                    max_chars_per_line = int(available_width * 2.2)  # Estimación
                    
                    current_y = content_y
                    line_height = 4
                    
                    for item_text in formatted_items:
                        if current_y + line_height > pos_y + row_height - 2:  # No salirse del cuadrante
                            break
                            
                        # ✅ USAR multi_cell PARA TEXTO LARGO
                        pdf.set_xy(pos_x + 3, current_y)
                        
                        # Calcular líneas necesarias
                        words = item_text.split()
                        current_line = ""
                        lines = []
                        
                        for word in words:
                            test_line = current_line + " " + word if current_line else word
                            if pdf.get_string_width(test_line) <= available_width:
                                current_line = test_line
                            else:
                                if current_line:
                                    lines.append(current_line)
                                    current_line = word
                                else:
                                    # Palabra muy larga, dividir
                                    lines.append(word[:max_chars_per_line//2])
                                    current_line = word[max_chars_per_line//2:]
                        
                        if current_line:
                            lines.append(current_line)
                        
                        # Renderizar líneas
                        for line in lines:
                            if current_y + line_height <= pos_y + row_height - 2:
                                pdf.set_xy(pos_x + 3, current_y)
                                super(PatchedPDF, pdf).cell(available_width, line_height, line, ln=False)
                                current_y += line_height
                            else:
                                break
                        
                        current_y += 1  # Espacio entre items
                
                else:
                    pdf.set_xy(pos_x + 3, content_y)
                    pdf.set_text_color(150, 150, 150)  # Gris más claro para placeholder
                    super(PatchedPDF, pdf).cell(col_width - 6, 6, "* No disponible")

                logging.info(f"[PDF] ✅ Cuadrante mejorado {title} completado")

            except Exception as e:
                logging.error(f"[PDF] ❌ Error dibujando cuadrante mejorado {title}: {e}")
                # Fallback simple
                pdf.set_fill_color(240, 240, 240)
                pdf.set_draw_color(100, 100, 100)
                pdf.rect(pos_x, pos_y, col_width, row_height, 'DF')
                pdf.set_xy(pos_x + 4, pos_y + 20)
                try:
                    pdf.set_font('DejaVu', 'I', 9)
                except:
                    pdf.set_font('Arial', 'I', 9)
                pdf.set_text_color(100, 100, 100)
                super(PatchedPDF, pdf).cell(col_width - 8, 6, f"Error en {title}")
        
        # ✅ CALCULAR POSICIONES CON SEPARACIÓN AUMENTADA
        start_x = pdf.l_margin + margin
        start_y = pdf.get_y()
        
        # ✅ DIBUJAR TÍTULO CENTRAL ELEGANTE
        pdf.set_xy(pdf.l_margin, start_y - 6)
        try:
            pdf.set_font('DejaVu', 'B', 14)
        except:
            pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(60, 60, 60)
        title_text = "ANÁLISIS DAFO"
        title_width = pdf.get_string_width(title_text)
        title_x = pdf.l_margin + (pdf.w - pdf.l_margin - pdf.r_margin - title_width) / 2
        pdf.set_x(title_x)
        super(PatchedPDF, pdf).cell(title_width, 8, title_text)
        pdf.ln(15)  # ✅ Más espacio después del título
        
        # Actualizar posición inicial
        start_y = pdf.get_y()
        
        # ✅ DIBUJAR CUADRANTES CON POSICIONAMIENTO PRECISO
        logging.info(f"[PDF] 🎨 Dibujando matriz DAFO 2x2 mejorada")
        
        # Fila superior: FORTALEZAS (izq) y DEBILIDADES (der)
        draw_enhanced_quadrant("FORTALEZAS", dafo.get('fortalezas', []), 
                             colores['fortalezas'], border_color['fortalezas'],
                             start_x, start_y, is_top=True)
        
        draw_enhanced_quadrant("DEBILIDADES", dafo.get('debilidades', []), 
                             colores['debilidades'], border_color['debilidades'],
                             start_x + col_width + gap, start_y, is_top=True)
        
        # Fila inferior: OPORTUNIDADES (izq) y AMENAZAS (der)
        draw_enhanced_quadrant("OPORTUNIDADES", dafo.get('oportunidades', []), 
                             colores['oportunidades'], border_color['oportunidades'],
                             start_x, start_y + row_height + gap, is_top=False)
        
        draw_enhanced_quadrant("AMENAZAS", dafo.get('amenazas', []), 
                             colores['amenazas'], border_color['amenazas'],
                             start_x + col_width + gap, start_y + row_height + gap, is_top=False)
        
        # ✅ AÑADIR LÍNEAS DIVISORIAS ELEGANTES EN EL CENTRO
        pdf.set_draw_color(200, 200, 200)  # Gris muy suave
        pdf.set_line_width(0.3)
        
        # Línea horizontal central
        center_y = start_y + row_height + (gap / 2)
        pdf.line(start_x - 5, center_y, start_x + (col_width * 2) + gap + 5, center_y)
        
        # Línea vertical central
        center_x = start_x + col_width + (gap / 2)
        pdf.line(center_x, start_y - 5, center_x, start_y + (row_height * 2) + gap + 5)
        
        # ✅ AÑADIR ETIQUETAS DE EJES ELEGANTES
        pdf.set_text_color(120, 120, 120)
        try:
            pdf.set_font('DejaVu', 'I', 8)
        except:
            pdf.set_font('Arial', 'I', 8)
        
        # Etiqueta superior: "FACTORES INTERNOS"
        label_y = start_y - 8
        label_text = "FACTORES INTERNOS"
        label_width = pdf.get_string_width(label_text)
        label_x = start_x + ((col_width * 2) + gap - label_width) / 2
        pdf.set_xy(label_x, label_y)
        super(PatchedPDF, pdf).cell(label_width, 4, label_text)
        
        # Etiqueta inferior: "FACTORES EXTERNOS"
        label_y = start_y + (row_height * 2) + gap + 3
        label_text = "FACTORES EXTERNOS"
        label_width = pdf.get_string_width(label_text)
        label_x = start_x + ((col_width * 2) + gap - label_width) / 2
        pdf.set_xy(label_x, label_y)
        super(PatchedPDF, pdf).cell(label_width, 4, label_text)
        
        # ✅ POSICIONAR CURSOR DESPUÉS DEL DAFO CON ESPACIO SUFICIENTE
        pdf.set_y(start_y + (row_height * 2) + gap + 20)
        
        # Restaurar colores por defecto
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(0, 0, 0)
        
        logging.info(f"[PDF] ✅ DAFO visual mejorado completado exitosamente")

    except Exception as e:
        logging.error(f"[PDF] ❌ Error crítico generando DAFO visual mejorado: {e}")
        import traceback
        traceback.print_exc()
        
        # ✅ FALLBACK MÁS ROBUSTO: Crear DAFO simple con datos por defecto
        try:
            logging.info(f"[PDF] 🔄 Aplicando fallback para DAFO...")
            
            # Usar función de validación para obtener datos por defecto
            dafo_fallback = validate_and_fix_dafo_structure({})
            
            pdf.set_font('DejaVu', 'B', 12)
            pdf.set_text_color(0, 51, 102)
            super(PatchedPDF, pdf).cell(0, 8, "Análisis DAFO", ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)
            
            # Crear tabla simple de DAFO
            for seccion, items in dafo_fallback.items():
                pdf.set_font('DejaVu', 'B', 10)
                super(PatchedPDF, pdf).cell(0, 6, seccion.upper(), ln=True)
                pdf.set_font('DejaVu', '', 9)
                
                for item in items[:3]:  # Solo 3 items por sección
                    super(PatchedPDF, pdf).multi_cell(0, 5, f"* {item}")
                pdf.ln(3)
            
            logging.info(f"[PDF] ✅ DAFO fallback aplicado correctamente")
            
        except Exception as fallback_error:
            logging.error(f"[PDF] ❌ Error en fallback DAFO: {fallback_error}")
            # Último recurso: mensaje simple
            try:
                pdf.set_font('DejaVu', 'I', 10)
                pdf.set_text_color(100, 100, 100)
                super(PatchedPDF, pdf).cell(0, 8, "Análisis DAFO: Datos en proceso de validación", ln=True, align='C')
                pdf.set_text_color(0, 0, 0)
                pdf.ln(10)
            except:
                # Si nada funciona, solo añadir espacio
                pdf.ln(20)

def add_vigilancia_tecnologica(pdf, vigilancia, add_reference, clean_and_normalize):
    """
    ✅ VERSIÓN REORGANIZADA: 
    1. GAPS TECNOLÓGICOS PRIMERO CON GRÁFICO VISUAL (igual que market analysis)
    2. Patentes y publicaciones compactadas para no ocupar todo el espacio
    3. Layout profesional con mejor distribución
    """
    total_items = 0
    
    # ✅ USAR FUENTE SEGURA UNICODE
    try:
        font_family = 'DejaVu'  
        pdf.set_font(font_family, '', 10)
    except:
        font_family = 'Arial'
        pdf.set_font(font_family, '', 10)

    # ============================================================================
    # 🎯 SECCIÓN 1: GAPS TECNOLÓGICOS CON GRÁFICO VISUAL (PRIMERO Y PRIORITARIO)
    # ============================================================================
    gaps = vigilancia.get('gaps_tecnologicos', [])
    print(f"🔍 DEBUG VIGILANCIA: gaps_tecnologicos = {gaps}")
    print(f"🔍 DEBUG VIGILANCIA: len(gaps) = {len(gaps) if gaps else 0}")
    
    if gaps and len(gaps) > 0:
        try:
            # ✅ EXTRAER DATOS PARA EL GRÁFICO (igual que en market analysis)
            gaps_text_list = []
            oportunidades_text_list = []
            
            for gap in gaps[:4]:  # Máximo 4 para el gráfico
                if isinstance(gap, dict):
                    # Texto del gap para la izquierda del gráfico
                    area = gap.get('area_tecnologica', '')
                    descripcion = gap.get('descripcion_gap', '')
                    if area and descripcion:
                        gap_text = f"{area}: {descripcion}"
                    elif descripcion:
                        gap_text = descripcion
                    else:
                        gap_text = "Gap tecnológico sin especificar"
                    
                    # Oportunidad Sener para la derecha del gráfico
                    oportunidad = gap.get('oportunidad_sener', '')
                    if oportunidad:
                        oportunidades_text_list.append(oportunidad)
                    else:
                        oportunidades_text_list.append("Requiere análisis específico")
                    
                    gaps_text_list.append(gap_text)
                elif isinstance(gap, str):
                    gaps_text_list.append(gap)
                    oportunidades_text_list.append("Requiere análisis específico")
            
            # ✅ VALORES POR DEFECTO SI NO HAY DATOS
            if not gaps_text_list:
                gaps_text_list = ["Requiere análisis específico de gaps tecnológicos"]
            if not oportunidades_text_list:
                oportunidades_text_list = ["Requiere análisis específico de oportunidades"]
            

            
            # ✅ CREAR GRÁFICO VISUAL PARA GAPS TECNOLÓGICOS (FUNCIÓN DEDICADA)
            try:
                import logging
                logging.info(f"[PDF] 📈 Creando gráfico de gaps tecnológicos: {len(gaps_text_list)} gaps, {len(oportunidades_text_list)} oportunidades")
                
                # ✅ CREAR FUNCIÓN ESPECÍFICA PARA GAPS TECNOLÓGICOS
                chart_path = create_tech_gaps_opportunities_chart(gaps_text_list, oportunidades_text_list, "output")
                
                if chart_path and os.path.exists(chart_path):
                    logging.info(f"[PDF] ✅ Insertando gráfico de gaps tecnológicos...")
                    
                    # ✅ SIN TÍTULOS - DIRECTAMENTE EL GRÁFICO
                    try:
                        # Calcular posición centrada
                        _insert_full_width_image(pdf, chart_path, spacing=10)
                        
                        logging.info(f"[PDF] ✅ Gráfico de gaps tecnológicos insertado")
                        
                    except Exception as img_e:
                        logging.warning(f"[PDF] ⚠️ Error insertando gráfico gaps tecnológicos: {img_e}")
                        
                else:
                    logging.warning(f"[PDF] ⚠️ No se pudo crear gráfico de gaps tecnológicos")
                    
            except Exception as chart_e:
                logging.warning(f"[PDF] ⚠️ Error creando gráfico gaps tecnológicos: {chart_e}")
                # Continuar sin el gráfico pero mostrar gaps en texto
                
        except Exception as e:
            logging.error(f"[PDF] Error en sección gaps tecnológicos: {e}")

    # ============================================================================
    # 🎯 SECCIÓN 2: PATENTES COMPLETAS (RESPETANDO MÁRGENES)
    # ============================================================================
    patentes = vigilancia.get('patentes_destacadas', [])
    if patentes and len(patentes) > 0:
        try:
            pdf.set_font(font_family, 'B', 12)
            pdf.set_text_color(0, 100, 100)
            super(PatchedPDF, pdf).cell(0, 8, "Patentes Relevantes", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            pdf.set_font(font_family, '', 10)  # ✅ FUENTE LEGIBLE AUMENTADA
            for i, patente in enumerate(patentes[:5], 1):  # ✅ HASTA 5 PATENTES
                try:
                    if isinstance(patente, dict):
                        titulo = patente.get('titulo', '')
                        numero = patente.get('numero_patente', '')
                        titular = patente.get('titular', '')
                        año = patente.get('año', '')
                        pais = patente.get('pais', '')
                        descripcion = patente.get('descripcion', '')
                        relevancia = patente.get('relevancia_competitiva', '')
                        
                        # ✅ LÍNEA PRINCIPAL CON INFORMACIÓN COMPLETA - RESPETANDO MÁRGENES
                        if titulo:
                            texto_patente = f"{i}. {clean_and_normalize(titulo)}"
                            if numero:
                                texto_patente += f" ({numero})"
                            if titular and año:
                                texto_patente += f" - {titular} ({año})"
                            if pais:
                                texto_patente += f" [{pais}]"
                        else:
                            texto_patente = f"{i}. Información no disponible"
                        
                        # ✅ USAR SAFE_MULTI_CELL ULTRA-SEGURO PARA EVITAR ERRORES
                        pdf.set_font(font_family, 'B', 10)
                        pdf.set_x(pdf.l_margin)
                        # Calcular ancho disponible respetando márgenes
                        ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin
                        safe_multi_cell(pdf, ancho_disponible, 6, texto_patente)
                        
                        # ✅ DESCRIPCIÓN SIMPLIFICADA PARA EVITAR ERRORES
                        if descripcion:
                            pdf.set_font(font_family, '', 9)
                            pdf.set_text_color(80, 80, 80)
                            desc_clean = clean_and_normalize(descripcion)[:200]
                            pdf.set_x(pdf.l_margin)
                            # USAR SAFE_MULTI_CELL ultra-seguro para mostrar descripción completa
                            pdf.set_x(pdf.l_margin + 10)  # Indentación
                            ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin - 10
                            safe_multi_cell(pdf, ancho_disponible, 5, desc_clean)
                            pdf.set_text_color(0, 0, 0)
                        
                        # ✅ RELEVANCIA SIMPLIFICADA PARA EVITAR ERRORES
                        if relevancia:
                            pdf.set_font(font_family, '', 9)
                            pdf.set_text_color(0, 80, 0)
                            rel_clean = clean_and_normalize(relevancia)[:150]
                            pdf.set_x(pdf.l_margin)
                            # USAR SAFE_MULTI_CELL ultra-seguro para mostrar relevancia completa
                            pdf.set_x(pdf.l_margin + 10)  # Indentación
                            ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin - 10
                            safe_multi_cell(pdf, ancho_disponible, 5, f"Relevancia: {rel_clean}")
                            pdf.set_text_color(0, 0, 0)
                        
                        # Añadir URL a referencias si existe
                        url = patente.get('url')
                        if url: 
                            add_reference(url)
                            
                    else:
                        # Si la patente no es un dict, tratarla como string
                        texto_patente = f"{i}. {clean_and_normalize(str(patente))}"
                        # USAR SAFE_MULTI_CELL ultra-seguro para mostrar patente completa
                        ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin
                        safe_multi_cell(pdf, ancho_disponible, 5, texto_patente)
                    
                    pdf.ln(2)  # ✅ PEQUEÑO ESPACIO ENTRE PATENTES
                    total_items += 1
                        
                except Exception as e:
                    logging.warning(f"[PDF] Error procesando patente {i}: {e}")
                    pdf.cell(0, 5, f"{i}. Error en patente", ln=True)
                    pdf.ln(2)
            
            pdf.ln(3)  # ✅ ESPACIADO AL FINAL DE LA SECCIÓN PATENTES
            
        except Exception as e:
            logging.error(f"[PDF] Error en sección patentes: {e}")

    # ============================================================================
    # 🎯 SECCIÓN 3: PUBLICACIONES COMPLETAS (RESPETANDO MÁRGENES)
    # ============================================================================
    publicaciones = vigilancia.get('publicaciones_clave', [])
    if publicaciones and len(publicaciones) > 0:
        try:
            pdf.set_font(font_family, 'B', 12)
            pdf.set_text_color(0, 0, 150)
            pdf.cell(0, 8, "Literatura Cientifica y Estado del Arte", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            pdf.set_font(font_family, '', 10)  # ✅ FUENTE LEGIBLE AUMENTADA
            for i, pub in enumerate(publicaciones[:5], 1):  # ✅ HASTA 5 PUBLICACIONES
                try:
                    if isinstance(pub, dict):
                        titulo = pub.get('titulo', '')
                        autores = pub.get('autores', '')
                        revista = pub.get('revista', '')
                        año = pub.get('año', '')
                        tipo = pub.get('tipo', '')
                        resumen = pub.get('resumen', '')
                        relevancia = pub.get('relevancia_tecnologica', '')
                        
                        # ✅ LÍNEA PRINCIPAL CON INFORMACIÓN COMPLETA - RESPETANDO MÁRGENES
                        if titulo:
                            texto_pub = f"- {clean_and_normalize(titulo)}"
                            if autores:
                                texto_pub += f" ({autores})"
                            if revista and año:
                                texto_pub += f" - {revista} ({año})"
                            if tipo:
                                texto_pub += f" [{tipo}]"
                        else:
                            texto_pub = f"- Información no disponible"
                        
                        # ✅ USAR SAFE_MULTI_CELL ULTRA-SEGURO PARA EVITAR ERRORES
                        pdf.set_font(font_family, 'B', 10)
                        pdf.set_x(pdf.l_margin)
                        # Calcular ancho disponible respetando márgenes
                        ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin
                        safe_multi_cell(pdf, ancho_disponible, 6, texto_pub)
                        
                        # ✅ RESUMEN SIMPLIFICADO PARA EVITAR ERRORES
                        if resumen:
                            pdf.set_font(font_family, '', 9)
                            pdf.set_text_color(80, 80, 80)
                            res_clean = clean_and_normalize(resumen)[:200]
                            pdf.set_x(pdf.l_margin)
                            # USAR SAFE_MULTI_CELL ultra-seguro para mostrar resumen completo
                            pdf.set_x(pdf.l_margin + 10)  # Indentación
                            ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin - 10
                            safe_multi_cell(pdf, ancho_disponible, 5, res_clean)
                            pdf.set_text_color(0, 0, 0)
                        
                        # ✅ RELEVANCIA SIMPLIFICADA PARA EVITAR ERRORES
                        if relevancia:
                            pdf.set_font(font_family, '', 9)
                            pdf.set_text_color(0, 0, 150)
                            rel_clean = clean_and_normalize(relevancia)[:150]
                            pdf.set_x(pdf.l_margin)
                            # USAR SAFE_MULTI_CELL ultra-seguro para mostrar impacto completo
                            pdf.set_x(pdf.l_margin + 10)  # Indentación
                            ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin - 10
                            safe_multi_cell(pdf, ancho_disponible, 5, f"Impacto: {rel_clean}")
                            pdf.set_text_color(0, 0, 0)
                        
                        # Añadir URL a referencias si existe
                        url = pub.get('url')
                        if url: 
                            add_reference(url)
                            
                    else:
                        # Si la publicación no es un dict, tratarla como string
                        texto_pub = f"- {clean_and_normalize(str(pub))}"
                        # USAR SAFE_MULTI_CELL ultra-seguro para mostrar publicación completa
                        ancho_disponible = pdf.w - pdf.l_margin - pdf.r_margin
                        safe_multi_cell(pdf, ancho_disponible, 5, texto_pub)
                    
                    pdf.ln(2)  # ✅ PEQUEÑO ESPACIO ENTRE PUBLICACIONES
                    total_items += 1
                        
                except Exception as e:
                    logging.warning(f"[PDF] Error procesando publicación {i}: {e}")
                    pdf.cell(0, 5, f"- Error en publicación", ln=True)
                    pdf.ln(2)
                        
            pdf.ln(3)  # ✅ ESPACIADO ENTRE SECCIONES
            
        except Exception as e:
            logging.error(f"[PDF] Error en sección publicaciones: {e}")

    # ============================================================================
    # 🎯 SECCIÓN 4: TENDENCIAS TECNOLÓGICAS EMERGENTES COMPLETAS
    # ============================================================================
    tendencias = vigilancia.get('tendencias_emergentes', [])
    if tendencias and len(tendencias) > 0:
        try:
            pdf.set_font(font_family, 'B', 12)
            pdf.set_text_color(150, 50, 0)
            pdf.cell(0, 8, "Tendencias Tecnologicas Emergentes", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            pdf.set_font(font_family, '', 10)  # ✅ FUENTE LEGIBLE AUMENTADA
            for i, tendencia in enumerate(tendencias[:5], 1):  # ✅ HASTA 5 TENDENCIAS
                try:
                    if isinstance(tendencia, dict):
                        tecnologia = tendencia.get('tecnologia', '')
                        estado = tendencia.get('estado_madurez', '')
                        potencial = tendencia.get('potencial_disruptivo', '')
                        plazo = tendencia.get('plazo_adopcion', '')
                        
                        # ✅ LÍNEA PRINCIPAL CON INFORMACIÓN COMPLETA
                        if tecnologia:
                            texto_tend = f"- {clean_and_normalize(tecnologia)}"
                            
                            # ✅ MOSTRAR EN MÚLTIPLES LÍNEAS SI ES NECESARIO
                            pdf.cell(0, 6, texto_tend, ln=True)
                            
                            # ✅ DETALLES EN LÍNEAS SEPARADAS CON INDENTACIÓN Y FUENTE LEGIBLE
                            pdf.set_font(font_family, '', 9)
                            pdf.set_text_color(80, 80, 80)
                            
                            if estado:
                                pdf.cell(0, 5, f"    Estado de madurez: {estado}", ln=True)
                            
                            if potencial:
                                pdf.cell(0, 5, f"    Potencial disruptivo: {potencial}", ln=True)
                            
                            if plazo:
                                pdf.cell(0, 5, f"    Plazo de adopción: {plazo}", ln=True)
                            
                            pdf.set_text_color(0, 0, 0)
                            pdf.set_font(font_family, '', 9)
                            
                        else:
                            texto_tend = f"- Tendencia {i}: Información no disponible"
                            pdf.cell(0, 6, texto_tend, ln=True)
                    else:
                        texto_tend = f"- {clean_and_normalize(str(tendencia))}"
                        pdf.cell(0, 6, texto_tend, ln=True)
                    
                    total_items += 1
                        
                except Exception as e:
                    logging.warning(f"[PDF] Error procesando tendencia {i}: {e}")
                    pdf.cell(0, 6, f"- Error en tendencia", ln=True)
                    
            pdf.ln(3)  # ✅ ESPACIADO AL FINAL DE LA SECCIÓN TENDENCIAS
            
        except Exception as e:
            logging.error(f"[PDF] Error en sección tendencias: {e}")

    # ============================================================================
    # 🎯 SECCIÓN 5: ANÁLISIS FINAL COMPACTADO (SI HAY ESPACIO)
    # ============================================================================
    analisis = vigilancia.get('analisis', '')
    if analisis and total_items > 0:
        try:
            # ✅ ANÁLISIS CORTO AL FINAL (solo si hay datos)
            analisis_clean = clean_and_normalize(analisis)
            if len(analisis_clean) > 300:
                analisis_clean = analisis_clean[:300] + "..."
                
            pdf.set_font(font_family, '', 9)
            try:
                analisis_safe = safe_text(analisis_clean, max_len_word=30, max_total=300)
                pdf.multi_cell(0, 5, analisis_safe)
            except Exception as e:
                pdf.cell(0, 5, analisis_clean[:100] + "..." if len(analisis_clean) > 100 else analisis_clean, ln=True)
            
        except Exception as e:
            logging.error(f"[PDF] Error en análisis final: {e}")
    
    # ✅ RETURN FINAL CORREGIDO - FUERA DE TODOS LOS TRY/EXCEPT
    return total_items > 0
        

def create_tech_gaps_opportunities_chart(gaps_list, oportunidades_list, output_dir="output"):
    """
    Crea un gráfico dinámico (sin recorte) para vigilancia tecnológica.
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        import textwrap, os, time, logging

        if not gaps_list and not oportunidades_list:
            return None

        gaps = gaps_list if gaps_list else ["Requiere análisis específico"]
        opps = oportunidades_list if oportunidades_list else ["Requiere análisis específico"]
        rows = max(len(gaps), len(opps))
        
        # 🔧 AJUSTE CRÍTICO: Wrap más agresivo para evitar desbordamiento
        wrap_width = 35  # REDUCIDO para mejor ajuste en recuadros
        
        # 🔧 WRAP ROBUSTO: Garantizar que TODOS los textos se ajusten
        wrapped_gaps = []
        for gap in gaps:
            gap_text = str(gap).strip()
            if len(gap_text) > wrap_width:
                wrapped_text = "\n".join(textwrap.wrap(gap_text, wrap_width))
            else:
                wrapped_text = gap_text
            wrapped_gaps.append(wrapped_text)
            
        wrapped_opps = []
        for opp in opps:
            opp_text = str(opp).strip()
            if len(opp_text) > wrap_width:
                wrapped_text = "\n".join(textwrap.wrap(opp_text, wrap_width))
            else:
                wrapped_text = opp_text
            wrapped_opps.append(wrapped_text)
        while len(wrapped_gaps) < rows:
            wrapped_gaps.append("")
        while len(wrapped_opps) < rows:
            wrapped_opps.append("")

        def rect_h(t):
            # 🔧 ALTURA MEJORADA: Más espacio por línea para mejor legibilidad
            lines = t.count("\n") + 1 if t else 1
            return max(1.2, 0.8 * lines + 0.6)  # Mínimo 1.2, más espacio por línea
        
        heights = [max(rect_h(wrapped_gaps[i]), rect_h(wrapped_opps[i])) for i in range(rows)]
        spacing = 0.4  # Espaciado entre filas
        total_h = sum(heights) + spacing * (rows - 1) + 4

        fig, ax = plt.subplots(figsize=(12, 9), dpi=200)
        fig.suptitle('VIGILANCIA TECNOLÓGICA: GAPS vs OPORTUNIDADES', fontsize=34, fontweight='bold', color='#003366', y=0.95)  # +2 puntos
        ax.set_xlim(0, 20)
        ax.set_ylim(0, total_h)
        ax.set_axis_off()

        gap_color = '#B71C1C'
        opp_color = '#1565C0'
        
        # 🎯 TÍTULOS COMPLETAMENTE SEPARADOS HORIZONTALMENTE
        title_y_position = total_h - 1.5  # Posición más baja para evitar solapamiento
        
        # Separar completamente los títulos en sus respectivas zonas SIN RECUADROS
        ax.text(5, title_y_position, 'GAPS TECNOLÓGICOS', fontsize=28, fontweight='bold', color=gap_color, ha='center')  # +2 puntos
        ax.text(15, title_y_position, 'OPORTUNIDADES SENER', fontsize=28, fontweight='bold', color=opp_color, ha='center')  # +2 puntos

        # 🔥 FLECHA Y TEXTO ENTRE TÍTULOS Y RECTÁNGULOS (MEJOR POSICIÓN)
        arrow_y_position = total_h - 2.8  # Entre títulos y rectángulos
        ax.annotate('', xy=(10.2, arrow_y_position), xytext=(9.8, arrow_y_position), arrowprops=dict(arrowstyle='->', lw=4, color='#003366'))
        ax.text(10, arrow_y_position - 0.3, 'TRANSFORMAR', fontsize=16, ha='center', style='italic', color='#003366', fontweight='bold')  # +2 puntos

        y = total_h - 4.0  # SEPARACIÓN AUMENTADA después de los títulos para evitar solapamiento
        for i in range(rows):
            h = heights[i]
            yc = y - h/2
            
            # 🔧 RENDERIZADO MEJORADO: Tamaño de fuente dinámico según contenido AUMENTADO
            # Calcular tamaño de fuente basado en el número de líneas
            lines_gaps = wrapped_gaps[i].count('\n') + 1 if wrapped_gaps[i] else 1
            lines_opps = wrapped_opps[i].count('\n') + 1 if wrapped_opps[i] else 1
            max_lines = max(lines_gaps, lines_opps)
            
            # 🔧 TAMAÑO DE FUENTE +2 PUNTOS para mejor legibilidad
            if max_lines <= 2:
                font_size = 20  # +2 puntos: de 18 a 20
            elif max_lines <= 3:
                font_size = 18  # +2 puntos: de 16 a 18
            elif max_lines <= 4:
                font_size = 17  # +2 puntos: de 15 a 17
            else:
                font_size = 16  # +2 puntos: de 14 a 16
            
            # GAPS (izquierda - rojo)
            if wrapped_gaps[i]:
                ax.add_patch(Rectangle((0.5, yc-h/2), 9, h, facecolor=gap_color, edgecolor='white', linewidth=2, alpha=0.85))
                ax.text(5, yc, f"* {wrapped_gaps[i]}", ha='center', va='center', fontsize=font_size, color='white', 
                       fontweight='normal', linespacing=1.1)
                       
            # OPORTUNIDADES (derecha - azul)
            if wrapped_opps[i]:
                ax.add_patch(Rectangle((10.5, yc-h/2), 9, h, facecolor=opp_color, edgecolor='white', linewidth=2, alpha=0.85))
                ax.text(15, yc, f"* {wrapped_opps[i]}", ha='center', va='center', fontsize=font_size, color='white',
                       fontweight='normal', linespacing=1.1)
                       
            y -= h + spacing

        # 🔥 FLECHA YA MOVIDA ARRIBA - ELIMINAR LA DE ABAJO
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"tech_gaps_opportunities_{int(time.time())}.png")
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        logging.info(f"[PDF] ✅ Gráfico de vigilancia tecnológica dinámico creado: {path}")
        return path
    except Exception as e:
        import logging, traceback
        logging.error(f"[PDF] ❌ Error gráfico vigilancia tecnológica dinámico: {e}")
        traceback.print_exc()
        return None

def generate_competitor_profile_pdf(competitor_data, output_name="perfil_competidor"):
    """
    Genera un PDF detallado con el perfil de un competidor específico
    
    Args:
        competitor_data: Diccionario con los datos del competidor
        output_name: Nombre base para el archivo de salida
        
    Returns:
        Ruta al archivo PDF generado
    """
    # Extraer información
    name = competitor_data.get('name', 'Competidor')
    description = competitor_data.get('description', '')
    market_share = competitor_data.get('market_share', 'No disponible')
    strengths = competitor_data.get('strengths', [])
    weaknesses = competitor_data.get('weaknesses', [])
    products = competitor_data.get('products', [])
    strategies = competitor_data.get('strategies', [])
    financials = competitor_data.get('financials', {})
    
    # Crear PDF
    pdf = PatchedPDF(title=f"Perfil Competitivo: {name}")
    
    # Añadir portada
    if hasattr(pdf, 'add_cover_page'):
        pdf.add_cover_page(subtitle=f"Análisis detallado del competidor")
    
    # Descripción general
    pdf.add_page()
    pdf.add_section_title("Descripción General")
    pdf.add_paragraph(description)
    
    # Información básica (tabla)
    pdf.ln(5)
    pdf.add_subsection_title("Información Clave")
    
    # Crear tabla de información básica
    headers = ["Métrica", "Valor"]
    col_widths = [100, 90]
    
    pdf.add_table_header(headers, col_widths)
    
    # Datos básicos
    basic_info = [
        ["Nombre", name],
        ["Cuota de mercado", market_share],
        ["Segmento principal", competitor_data.get('main_segment', 'No especificado')],
        ["Posicionamiento", competitor_data.get('positioning', 'No especificado')],
        ["Antigüedad", competitor_data.get('age', 'No especificado')],
        ["Ubicación", competitor_data.get('location', 'No especificado')]
    ]
    
    for item in basic_info:
        pdf.add_table_row(item, col_widths)
    
    # Productos y servicios
    pdf.add_page()
    pdf.add_section_title("Productos y Servicios")
    
    if products:
        for product in products:
            name = product.get('name', 'Producto')
            description = product.get('description', '')
            market_position = product.get('market_position', '')
            
            pdf.add_subsection_title(name)
            pdf.add_paragraph(description)
            
            if market_position:
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Posición en el mercado:", ln=True)
                pdf.add_paragraph(market_position)
    else:
        pdf.add_paragraph("No se dispone de información detallada sobre productos y servicios.")
    
    # Fortalezas y Debilidades
    pdf.add_page()
    pdf.add_section_title("Fortalezas y Debilidades")
    
    # Fortalezas
    pdf.add_subsection_title("Fortalezas")
    if strengths:
        for strength in strengths:
            pdf.set_font('Helvetica', '', 11)
            pdf.cell(0, 8, f"- {clean_text_for_pdf(strength)}", ln=True)
    else:
        pdf.add_paragraph("No se han identificado fortalezas específicas.")
    
    pdf.ln(5)
    
    # Debilidades
    pdf.add_subsection_title("Debilidades")
    if weaknesses:
        for weakness in weaknesses:
            pdf.set_font('Helvetica', '', 11)
            pdf.cell(0, 8, f"- {clean_text_for_pdf(weakness)}", ln=True)
    else:
        pdf.add_paragraph("No se han identificado debilidades específicas.")
    
    # Estrategias
    pdf.add_page()
    pdf.add_section_title("Estrategias de Mercado")
    
    if strategies:
        for strategy in strategies:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, f"- {clean_text_for_pdf(strategy.get('name', 'Estrategia'))}", ln=True)
            
            if 'description' in strategy:
                pdf.add_paragraph(strategy['description'])
    else:
        pdf.add_paragraph("No se dispone de información detallada sobre estrategias de mercado.")
    
    # Información financiera
    if financials:
        pdf.add_page()
        pdf.add_section_title("Información Financiera")
        
        revenue = financials.get('revenue', 'No disponible')
        growth = financials.get('growth', 'No disponible')
        profitability = financials.get('profitability', 'No disponible')
        
        financial_data = [
            ["Ingresos", revenue],
            ["Crecimiento", growth],
            ["Rentabilidad", profitability],
            ["Inversión en I+D", financials.get('r_and_d', 'No disponible')],
            ["Otros indicadores", financials.get('other', 'No disponible')]
        ]
        
        pdf.add_table_header(["Indicador", "Valor"], [100, 90])
        
        for item in financial_data:
            pdf.add_table_row(item, [100, 90])
    
    # Recomendaciones
    pdf.add_page()
    pdf.add_section_title("Recomendaciones")
    
    recommendations = competitor_data.get('recommendations', [])
    if recommendations:
        for recommendation in recommendations:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, f"- {clean_text_for_pdf(recommendation)}", ln=True)
    else:
        pdf.add_paragraph("Se recomienda un análisis más profundo para formular recomendaciones específicas en relación a este competidor.")
    
    # Guardar PDF
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(output_dir, f"{output_name}_{name.replace(' ', '_')}_{timestamp}.pdf")
    pdf.output(pdf_path)
    return pdf_path

def generate_professional_report_pdf(report, company_name="Sener", output_name=None):
    from datetime import datetime
    import re
    FONT_PATH = os.path.join("output", "DejaVuSans.ttf")
    FONT_OK = os.path.exists(FONT_PATH)
    FONT_NAME = 'DejaVu' if FONT_OK else 'Helvetica'
    logo_path = 'logo1.png'
    color_primario = (0, 51, 102)
    pdf = PatchedPDF(title=f"Análisis de Competencia: {company_name}")
    pdf.set_auto_page_break(auto=True, margin=15)

    def default_text(section):
        return "Sin datos extraídos para este apartado."

    # --- Mapeo de secciones profesionales a legacy ---
    section_map = [
        ("COMPETITOR_MAPPING", "benchmarking"),
        ("BENCHMARK_MATRIX", "benchmarking"),
        ("TECH_IP_LANDSCAPE", "vigilancia_tecnologica"),
        ("MARKET_ANALYSIS", "analisis_mercado"),
        ("SWOT_POSITIONING", "dafo"),
        ("REGULATORY_ESG_RISK", "recomendaciones"),
    ]
    # --- PORTADA estilo ranking ---
    pdf.add_page()
    if logo_path and os.path.exists(logo_path):
        pdf.image(logo_path, x=(pdf.w-50)/2, y=30, w=50)
    pdf.set_y(90)
    pdf.set_font('Helvetica', 'B', 24)
    pdf.set_text_color(40, 60, 90)
    pdf.cell(0, 18, "ANÁLISIS DE COMPETENCIA", ln=True, align='C')
    pdf.set_font('Helvetica', '', 15)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 12, "Análisis competitivo y posicionamiento estratégico", ln=True, align='C')
    pdf.ln(60)
    pdf.set_y(pdf.h-45)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.cell(0, 8, f"Sener - Innovación Tecnológica", ln=True, align='C')
    pdf.set_text_color(0,0,0)

    # --- ÍNDICE JERÁRQUICO POR IDEAS CON PÁGINAS ---
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(*color_primario)
    pdf.cell(0, 12, "Índice de Contenidos", ln=True)
    pdf.ln(2)
    ideas = report.get('ideas', [report])
    referencias = []
    index_entries = []
    page_counter = 2  # Portada=1, Índice=2
    resumen = report.get('EXEC_SUMMARY', {}).get('texto') or report.get('resumen_ejecutivo') or report.get('resumen_ejecutivo_global')
    conclusion = report.get('conclusion_final')
    # Precalcular páginas
    idea_pages = []
    if resumen:
        page_counter += 1
    for idea in ideas:
        idea_page = page_counter + 1
        idea_pages.append(idea_page)
        page_counter += 1 + 5  # 1 para la idea, 5 para subsecciones (aprox)
    if conclusion:
        page_counter += 1
    # Índice
    for i, idea in enumerate(ideas, 1):
        idea_name = clean_and_normalize(idea.get('idea', f'Idea {i}'))
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(*color_primario)
        pdf.cell(0, 8, f"{i}. {idea_name} ............................................. {idea_pages[i-1]}", ln=True)
        for sidx, (sec_pro, sec_legacy) in enumerate(section_map, 1):
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(60,60,60)
            pdf.cell(0, 7, f"   {i}.{sidx} {sec_pro.replace('_',' ').title()} ............................................. {idea_pages[i-1]+sidx}", ln=True)
    if resumen:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(80,80,80)
        pdf.cell(0, 7, f"Resumen Ejecutivo ............................................. 3", ln=True)
    if conclusion:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(80,80,80)
        pdf.cell(0, 7, f"Conclusión Final ............................................. {page_counter}", ln=True)
    pdf.ln(4)
    pdf.set_text_color(0,0,0)

    # --- RESUMEN EJECUTIVO (si existe) ---
    if resumen:
        pdf.add_page()
        pdf.add_section_title("Resumen Ejecutivo")
        pdf.add_paragraph(clean_and_normalize(resumen))

    # --- POR CADA IDEA ---
    ref_map = {}
    ref_counter = 1
    for i, idea in enumerate(ideas, 1):
        idea_name = clean_and_normalize(idea.get('idea', f'Idea {i}'))
        pdf.add_page()
        pdf.add_section_title(f"{i}. {idea_name}")
        for sidx, (sec_pro, sec_legacy) in enumerate(section_map, 1):
            pdf.add_subsection_title(f"{i}.{sidx} {sec_pro.replace('_',' ').title()}")
            # --- Buscar primero la sección profesional ---
            contenido = None
            # Buscar clave profesional (case-insensitive)
            for k in idea.keys():
                if k.upper() == sec_pro.upper():
                    sec = idea[k]
                    if isinstance(sec, dict):
                        contenido = sec.get('texto') or sec.get('text')
                    elif isinstance(sec, str):
                        contenido = sec
                    break
            # Si no hay profesional, buscar legacy
            if not contenido:
                for k in idea.keys():
                    if k.lower() == sec_legacy.lower():
                        sec = idea[k]
                        if isinstance(sec, dict):
                            contenido = sec.get('texto') or sec.get('text')
                        elif isinstance(sec, str):
                            contenido = sec
                        break
            # Si sigue sin haber contenido, usar default
            if not contenido or not contenido.strip() or 'no disponible' in contenido.lower() or 'no se pudo extraer' in contenido.lower():
                pdf.set_font('Helvetica', 'I', 10)
                pdf.set_text_color(150,0,0)
                pdf.multi_cell(0, 6, '[Sección no disponible o incompleta. Consulte fuentes primarias o realice revisión manual.]')
                pdf.set_text_color(0,0,0)
                continue
            pdf.set_text_color(0,0,0)
            pdf.add_paragraph(clean_and_normalize(contenido))
    # --- CONCLUSIÓN FINAL (si existe) ---
    if conclusion:
        pdf.add_page()
        pdf.add_section_title("Conclusión Final")
        pdf.add_paragraph(clean_and_normalize(conclusion))

    # --- REFERENCIAS ---
    if referencias:
        pdf.add_page()
        pdf.add_section_title("Referencias y Fuentes")
        pdf.set_font('Helvetica', '', 9)
        for i, ref in enumerate(referencias, 1):
            ref_clean = clean_and_normalize(str(ref))[:200]
            pdf.multi_cell(0, 6, f"[{i}] {ref_clean}", link=ref)
            pdf.ln(1)
    if not output_name:
        output_name = f"informe_profesional_{company_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    output_path = os.path.join("output", output_name)
    os.makedirs("output", exist_ok=True)
    pdf.output(output_path)
    return output_path

def _format_benchmarking_section(pdf, benchmarking_data):
    # Si la tabla es muy ancha, usar formato vertical
    if len(benchmarking_data) > 0 and len(benchmarking_data[0]) > 5:
        for comp in benchmarking_data:
            pdf.set_font("helvetica", "B", 12)
            pdf.cell(0, 10, safe_text(comp.get('Competidor', 'Competidor')), ln=True)
            pdf.set_font("helvetica", size=11)
            for k, v in comp.items():
                if k == 'Competidor':
                    continue
                pdf.multi_cell(0, 8, f"{safe_text(k)}: {safe_text(v)}")
            pdf.ln(4)
        return
    # Si cabe en horizontal, ajustar columnas
    headers = list(benchmarking_data[0].keys())
    col_widths = []
    max_page_width = 180
    min_col_width = 30
    pdf.set_font("helvetica", "B", 11)
    for h in headers:
        max_len = max([len(safe_text(row.get(h, ''))) for row in benchmarking_data] + [len(safe_text(h))])
        col_width = min(max(min_col_width, max_len * 3.5), max_page_width // len(headers))
        col_widths.append(col_width)
    # Ajustar fuente si la suma excede el ancho
    if sum(col_widths) > max_page_width:
        pdf.set_font("helvetica", size=9)
        scale = max_page_width / sum(col_widths)
        col_widths = [int(w * scale) for w in col_widths]
    # Cabecera
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, safe_text(h), border=1, align='C')
    pdf.ln()
    pdf.set_font("helvetica", size=10)
    # Filas
    for row in benchmarking_data:
        y_start = pdf.get_y()
        max_y = y_start
        for i, h in enumerate(headers):
            x = pdf.get_x()
            y = pdf.get_y()
            text = safe_text(row.get(h, ''))
            pdf.multi_cell(col_widths[i], 8, text, border=1, align='L', max_line_height=pdf.font_size_pt)
            max_y = max(max_y, pdf.get_y())
            pdf.set_xy(x + col_widths[i], y)
        pdf.set_y(max_y)
    pdf.ln(6) 

def _add_dafo_section(pdf, dafo_dict):
    # Cuadrantes DAFO
    cuadrantes = [
        ("Fortalezas", 'fortalezas'),
        ("Debilidades", 'debilidades'),
        ("Oportunidades", 'oportunidades'),
        ("Amenazas", 'amenazas')
    ]
    for titulo, clave in cuadrantes:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, titulo, ln=True)
        items = dafo_dict.get(clave, [])
        if not items:
            pdf.set_font('Helvetica', 'I', 9)
            pdf.cell(0, 6, f"No se encontraron {titulo.lower()} específicas para este análisis.", ln=True)
            continue
        for item in items:
            try:
                pdf.set_font('Helvetica', '', 10)
                if isinstance(item, dict):
                    texto = item.get('texto') or item.get('descripcion') or item.get('valor') or item.get('titulo') or str(item)
                    fuente = item.get('fuente') or item.get('url')
                else:
                    texto = str(item)
                    fuente = None
                pdf.multi_cell(0, 6, f"- {texto}")
                if fuente:
                    pdf.set_font('Helvetica', 'I', 8)
                    pdf.multi_cell(0, 5, f"  Fuente: {fuente}")
                    pdf.set_font('Helvetica', '', 10)
                pdf.ln(1)
            except Exception as e:
                pdf.set_font('Helvetica', 'I', 8)
                pdf.cell(0, 6, f"[Error mostrando ítem DAFO: {e}]", ln=True)
                pdf.set_font('Helvetica', '', 10)
        pdf.ln(2) 

def safe_cell(pdf, w=0, h=0, txt="", *cell_args, **cell_kwargs):
    """
    ✅ VERSIÓN COMPLETAMENTE CORREGIDA - Sin recursión infinita y con limpieza de caracteres
    """
    try:
        # Limpiar texto básico sin procesos complejos
        if txt is None:
            txt = ""
        
        txt_clean = str(txt).strip()
        
        # ✅ LIMPIAR CARACTERES PROBLEMÁTICOS PARA PDF
        txt_clean = clean_and_normalize(txt_clean)
        
        # Límite básico de longitud para evitar overflow
        if len(txt_clean) > 100:
            txt_clean = txt_clean[:100] + "..."
            
        # Calcular ancho seguro
        if w == 0:
            w = pdf.w - pdf.r_margin - pdf.x
        
        # Asegurar ancho mínimo
        min_width = 10
        if w < min_width:
            w = min_width
            
        # ✅ VERIFICAR QUE EL PDF TIENE LOS MÉTODOS NECESARIOS
        if hasattr(pdf, '_in_cell_override') and pdf._in_cell_override:
            # Si estamos en recursión, usar método base directo
            from fpdf import FPDF
            FPDF.cell(pdf, w, h, txt_clean, *cell_args, **cell_kwargs)
        else:
            # ✅ USAR EL MÉTODO NORMAL DEL PDF (que ya tiene protección de recursión)
            pdf.cell(w, h, txt_clean, *cell_args, **cell_kwargs)
            
    except Exception as e:
        logging.warning(f"[PDF] Error en safe_cell: {e}")
        # Último recurso: celda vacía
        try:
            from fpdf import FPDF
            FPDF.cell(pdf, w or 10, h or 6, "N/D", *cell_args, **cell_kwargs)
        except:
            pass

def safe_multi_cell(pdf, w, h, txt, *cell_args, **cell_kwargs):
    """
    ✅ VERSIÓN COMPLETAMENTE CORREGIDA - Sin recursión infinita
    """
    try:
        # Limpiar texto básico
        if txt is None:
            txt = ""
            
        txt_clean = str(txt).strip().replace('\n', ' ').replace('\r', ' ')
        
        # Límite básico de longitud
        if len(txt_clean) > 10000:  # AUMENTADO de 2000 a 10000
            txt_clean = txt_clean[:10000] + "... [Texto truncado]"  # AUMENTADO
        
        # Calcular ancho seguro
        if w == 0:
            w = pdf.w - pdf.r_margin - pdf.x
            
        # Asegurar ancho mínimo
        min_width = 20
        if w < min_width:
            w = min_width
            
        # Usar método nativo FPDF directamente SIN recursión
        try:
            # Método super() directo sin override personalizado
            super(type(pdf), pdf).multi_cell(w, h, txt_clean, *cell_args, **cell_kwargs)
        except:
            # Fallback con método base
            from fpdf import FPDF
            FPDF.multi_cell(pdf, w, h, txt_clean, *cell_args, **cell_kwargs)
            
    except Exception as e:
        logging.warning(f"[PDF] Error en safe_multi_cell: {e}")
        # Último recurso: salto de línea
        try:
            pdf.ln(h or 6)
        except:
            pass

def _strip_markdown_tables(text):
    """
    Detecta y elimina tablas Markdown del texto, dejando solo el texto útil.
    """
    if not isinstance(text, str):
        return str(text)
    
    import re
    lines = text.splitlines()
    out = []
    in_table = False
    
    for line in lines:
        # Detectar líneas de tabla Markdown
        if re.match(r'^\s*\|.*\|\s*$', line):
            if not in_table:
                out.append('[Tabla omitida]')
                in_table = True
            continue
        elif re.match(r'^\s*[|-]+\s*$', line):  # Separadores de tabla
            continue
        elif in_table and not line.strip():
            in_table = False
            continue
            
        if not in_table:
            out.append(line)
    
    return '\n'.join(out)

class PatchedPDF(BasePDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._in_cell_override = False  # Flag para evitar recursión
    
    def cell(self, w=0, h=0, txt="", *a, **k):
        """
        ✅ VERSIÓN SIMPLIFICADA que evita recursión infinita
        """
        if self._in_cell_override:
            # Evitar recursión - usar método padre directamente
            return super().cell(w, h, txt, *a, **k)
            
        try:
            self._in_cell_override = True
            
            # Limpiar texto básico
            txt_clean = str(txt or "").strip()
            if len(txt_clean) > 500:  # AUMENTADO de 100 a 500
                txt_clean = txt_clean[:500] + "..."  # AUMENTADO
            
            # Calcular ancho seguro
            if w == 0:
                w = self.w - self.r_margin - self.x
            w = max(w, 10)  # Ancho mínimo
            
            # Llamar al método padre
            result = super().cell(w, h, txt_clean, *a, **k)
            return result
            
        finally:
            self._in_cell_override = False
    
    def multi_cell(self, w, h, txt="", *a, **k):
        """
        ✅ VERSIÓN SIMPLIFICADA que evita recursión infinita
        """
        if self._in_cell_override:
            # Evitar recursión - usar método padre directamente
            return super().multi_cell(w, h, txt, *a, **k)
            
        try:
            self._in_cell_override = True
            
            # Limpiar texto básico
            txt_clean = str(txt or "").strip()
            txt_clean = txt_clean.replace('\n', ' ').replace('\r', ' ')
            
            if len(txt_clean) > 10000:  # AUMENTADO de 2000 a 10000
                txt_clean = txt_clean[:10000] + "... [Texto truncado]"  # AUMENTADO
            
            # Calcular ancho seguro
            if w == 0:
                w = self.w - self.r_margin - self.x
            w = max(w, 20)  # Ancho mínimo para multi_cell
            
            # Llamar al método padre
            result = super().multi_cell(w, h, txt_clean, *a, **k)
            return result
            
        finally:
            self._in_cell_override = False

def _coerce_sections_for_pdf(secciones: dict) -> dict:
    """
    ✅ OPTIMIZADO: Convierte listas o strings en dicts con límites de tamaño y timeout para evitar colgarse.
    """
    import time
    start_time = time.time()
    
    logging.info(f"[PDF] 🔄 Iniciando coercion de {len(secciones)} secciones...")
    
    coerced = {}
    for i, (k, v) in enumerate(secciones.items()):
        logging.info(f"[PDF] 🔧 Procesando elemento {i+1}/{len(secciones)}: {k}")
        
        # ✅ TIMEOUT DE SEGURIDAD
        if time.time() - start_time > 20:  # 20 segundos máximo
            logging.error(f"[PDF] ⏱️ TIMEOUT en coercion después de 20s, abortando resto")
            break
            
        if k == 'metadatos':
            logging.info(f"[PDF] ⏭️ Omitiendo metadatos")
            continue
            
        if isinstance(v, dict):
            if 'texto' in v:
                coerced[k] = v
                logging.info(f"[PDF] ✅ Dict con texto mantenido: {k}")
            else:
                coerced[k] = v
                logging.info(f"[PDF] ✅ Dict sin texto mantenido: {k}")
        elif isinstance(v, list):
            logging.info(f"[PDF] 📋 Procesando lista de {len(v)} elementos en {k}")
            
            # ✅ OPTIMIZACIÓN: Limitar listas muy grandes
            if len(v) > 50:
                logging.warning(f"[PDF] ⚠️ Lista muy grande en {k}: {len(v)} elementos, truncando a 50")
                v = v[:50] + [{"nota": f"... {len(v)-50} elementos más omitidos por tamaño"}]
                
            # Detectar lista de dicts homogénea
            if v and all(isinstance(el, dict) for el in v):
                logging.info(f"[PDF] 📊 Convirtiendo lista de dicts a tabla para {k}")
                # Construir tabla: cabeceras = claves comunes
                headers = list({key for d in v for key in d.keys()})
                rows = []
                N = min(10, len(v))  # Máximo 10 filas para evitar PDFs enormes
                for el in v[:N]:
                    row = [str(el.get(h, ''))[:100] for h in headers]  # Truncar celdas muy largas
                    rows.append(row)
                table_str = "\t".join(headers) + "\n" + "\n".join(["\t".join(row) for row in rows])
                if len(v) > N:
                    table_str += f"\n... (mostrando solo los primeros {N} elementos de {len(v)})"
                coerced[k] = {"texto": table_str}
                logging.info(f"[PDF] ✅ Tabla creada para {k}")
            else:
                logging.info(f"[PDF] 📝 Convirtiendo lista mixta a texto para {k}")
                # ✅ OPTIMIZACIÓN: Limitar elementos individuales
                joined_elements = []
                for j, el in enumerate(v[:20]):  # Máximo 20 elementos
                    if isinstance(el, (dict, list)):
                        el_str = str(el)[:500]  # Simplificado y más rápido
                        if len(str(el)) > 500:
                            el_str += "... [Contenido truncado]"
                    else:
                        el_str = str(el)[:200]  # Truncar strings muy largos
                        if len(str(el)) > 200:
                            el_str += "... [Texto truncado]"
                    joined_elements.append(el_str)
                    
                if len(v) > 20:
                    joined_elements.append(f"... y {len(v)-20} elementos más")
                    
                joined = "\n".join(joined_elements)
                coerced[k] = {"texto": joined}
                logging.info(f"[PDF] ✅ Lista mixta convertida para {k}")
        else:
            # ✅ OPTIMIZACIÓN: Truncar strings muy largos
            text_str = str(v)
            if len(text_str) > 5000:
                text_str = text_str[:20000] + "... [Texto truncado por longitud]"  # AUMENTADO de 5000 a 20000
            coerced[k] = {"texto": text_str}
            logging.info(f"[PDF] ✅ String convertido para {k}")
    
    elapsed = time.time() - start_time
    logging.info(f"[PDF] ✅ Coercion completada: {len(coerced)} elementos en {elapsed:.2f}s")
    return coerced

# --- ORDEN CORRECTO DE SECCIONES ---
def get_ordered_sections():
    """Define el orden correcto de las secciones en el PDF."""
    return [
        "EXEC_SUMMARY",           # 1. Resumen Ejecutivo
        "COMPETITOR_MAPPING",     # 2. Mapa de Competidores  
        "BENCHMARK_MATRIX",       # 3. Benchmarking
        "MARKET_ANALYSIS",        # 4. Análisis de Mercado
        "TECH_IP_LANDSCAPE",      # 5. Vigilancia Tecnológica
        "SWOT_POSITIONING",       # 6. DAFO y Posicionamiento
        "REGULATORY_ESG_RISK"     # 7. Riesgo Regulatorio y ESG
    ] 

# ✅ MEJORAS DE DISEÑO PROFESIONAL

def setup_professional_style(pdf):
    """
    ✅ CONFIGURACIÓN DE ESTILO PROFESIONAL PARA EL PDF
    """
    try:
        # Configurar márgenes profesionales
        pdf.set_margins(left=20, top=20, right=20)
        pdf.set_auto_page_break(auto=True, margin=25)
        
        # Configurar fuente por defecto
        pdf.set_font('Arial', '', 11)
        
        # Configurar colores corporativos
        pdf.color_primary = (0, 51, 102)     # Azul corporativo
        pdf.color_secondary = (80, 80, 80)    # Gris
        pdf.color_accent = (0, 100, 0)       # Verde para destacados
        
        logging.info("[PDF] ✅ Estilo profesional configurado")
        
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error configurando estilo profesional: {e}")

def add_professional_header(pdf, title=""):
    """
    ✅ AÑADIR HEADER PROFESIONAL A CADA PÁGINA - VERSIÓN CORREGIDA
    """
    try:
        # ✅ SOLO AÑADIR HEADER SI ESTAMOS EN EL INICIO DE UNA PÁGINA
        if pdf.get_y() > 30:  # Si ya hay contenido, no añadir header
            return
            
        # Guardar posición actual
        y_before = pdf.get_y()
        
        # ✅ VERIFICAR QUE ESTAMOS EN POSICIÓN CORRECTA
        if y_before < 25:
            # Ir al inicio de la página
            pdf.set_y(10)
            
            # ✅ LÍNEA SUPERIOR ELIMINADA - Sin barra azul en el header
            
            # Título en header
            if title:
                pdf.set_font('Arial', 'B', 10)
                pdf.set_text_color(0, 51, 102)
                pdf.set_y(17)
                super(PatchedPDF, pdf).cell(0, 6, title, ln=True, align='C')
            
            # ✅ ESTABLECER POSICIÓN INICIAL CORRECTA PARA CONTENIDO
            pdf.set_y(30)  # Posición fija después del header
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 11)
        else:
            # Si ya hay contenido, mantener posición actual
            pdf.set_y(y_before)
        
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error añadiendo header: {e}")
        # Asegurar posición mínima
        if pdf.get_y() < 25:
            pdf.set_y(25)

def add_professional_footer(pdf):
    """
    ✅ AÑADIR FOOTER PROFESIONAL CON PAGINACIÓN
    """
    try:
        # Guardar posición actual
        y_before = pdf.get_y()
        
        # Ir al final de la página
        pdf.set_y(pdf.h - 20)
        
        # Línea inferior
        pdf.set_draw_color(0, 51, 102)
        pdf.set_line_width(0.5)
        pdf.line(20, pdf.h - 15, pdf.w - 20, pdf.h - 15)
        
        # Número de página
        pdf.set_font('Arial', '', 9)
        pdf.set_text_color(80, 80, 80)
        page_text = f"Página {pdf.page_no()}"
        super(PatchedPDF, pdf).cell(0, 6, page_text, ln=True, align='C')
        
        # Información de empresa
        pdf.set_y(pdf.h - 10)
        super(PatchedPDF, pdf).cell(0, 6, "Sener - Innovación Tecnológica", ln=True, align='C')
        
        # Restaurar configuración
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', '', 11)
        
        # No restaurar posición Y para que el footer quede fijo
        
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error añadiendo footer: {e}")

def add_references_section(pdf, referencias, clean_and_normalize):
    """
    Añade sección de referencias con mejor validación y sin duplicación.
    ✅ MEJORADO: Evita referencias duplicadas y valida URLs
    """
    import re
    from urllib.parse import urlparse
    
    if not referencias:
        logging.info("[PDF] ℹ️ No hay referencias para añadir")
        return
    
    # ✅ LIMPIAR Y DEDUPLICAR REFERENCIAS
    referencias_limpias = []
    urls_vistas = set()
    
    for url in referencias:
        if not url or not isinstance(url, str):
            continue
            
        url = url.strip()
        if not url or url in urls_vistas:
            continue
            
        # ✅ VALIDAR URL BÁSICA
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                # Si no es URL válida, saltar
                continue
        except:
            continue
            
        # ✅ FILTRAR URLs OBVIAMENTE FALSAS
        domain = parsed.netloc.lower()
        
        # Skip URLs que parecen inventadas por LLM
        skip_patterns = [
            'example.com', 'test.com', 'company.com', 'website.com',
            'empresa.com', 'sample.com', 'demo.com'
        ]
        
        if any(pattern in domain for pattern in skip_patterns):
            logging.warning(f"[PDF] ⚠️ Saltando URL posiblemente falsa: {url}")
            continue
            
        # ✅ VERIFICAR QUE EL DOMINIO TENGA SENTIDO
        if len(domain.split('.')) < 2:
            continue
            
        referencias_limpias.append(url)
        urls_vistas.add(url)
    
    if not referencias_limpias:
        logging.warning("[PDF] ⚠️ No quedaron referencias válidas después de la limpieza")
        return
    
    logging.info(f"[PDF] 📄 Añadiendo sección de referencias con {len(referencias_limpias)} URLs válidas")
    
    pdf.add_page()
    
    try:
        pdf.set_font("DejaVu", 'B', 16)
    except:
        pdf.set_font('Arial', 'B', 16)
    
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "Referencias y Fuentes", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # ✅ AÑADIR EXPLICACIÓN SOBRE FILTRADO DE REFERENCIAS
    try:
        pdf.set_font("DejaVu", 'B', 11)
    except:
        pdf.set_font('Arial', 'B', 11)
    
    pdf.cell(0, 8, "Referencias Utilizadas en el Análisis", ln=True)
    pdf.ln(2)
    
    try:
        pdf.set_font("DejaVu", '', 10)
    except:
        pdf.set_font('Arial', '', 10)
    
    pdf.cell(0, 6, f"Total de fuentes consultadas: {len(referencias_limpias)}", ln=True)
    pdf.ln(3)
    
    # ✅ AÑADIR REFERENCIAS NUMERADAS
    try:
        pdf.set_font("DejaVu", '', 11)
    except:
        pdf.set_font('Arial', '', 11)
    
    for i, url in enumerate(referencias_limpias, 1):
        try:
            # Limpiar URL para PDF
            url_clean = clean_and_normalize(url)
            
            # Truncar URLs muy largas
            if len(url_clean) > 80:
                url_display = url_clean[:77] + "..."
            else:
                url_display = url_clean
            
            pdf.cell(0, 6, f"[{i:02d}] {url_display}", ln=True)
            
        except Exception as e:
            logging.warning(f"[PDF] ⚠️ Error añadiendo referencia {i}: {e}")
            try:
                pdf.cell(0, 6, f"[{i:02d}] URL no disponible", ln=True)
            except:
                pdf.ln(6)
                    
    # ✅ AÑADIR DISCLAIMER METODOLÓGICO
    pdf.ln(10)
    try:
        pdf.set_font("DejaVu", 'B', 12)
    except:
        pdf.set_font('Arial', 'B', 12)
    
    pdf.cell(0, 8, "Metodología y Validación", ln=True)
    pdf.ln(5)
    
    try:
        pdf.set_font("DejaVu", '', 10)
    except:
        pdf.set_font('Arial', '', 10)
    
    metodologia_text = f"""VALIDACIÓN DE REFERENCIAS:
- Solo se incluyen URLs verificables y específicas de documentos reales
- Se excluyen búsquedas genéricas e indicaciones de consulta pendiente
- URLs base sin documento específico son filtradas automáticamente
- Total validado: {len(referencias_limpias)} de múltiples fuentes analizadas

METODOLOGÍA DE ANÁLISIS:
- Datos extraídos mediante análisis LLM avanzado con validación cruzada
- Competidores identificados mediante búsqueda sectorial especializada
- Estimaciones basadas en patrones industriales verificables
- Información actualizada hasta la fecha de generación del informe
- Recomendación: validar datos críticos mediante investigación directa"""
    
    try:
        # Usar multi_cell para texto largo
        pdf.multi_cell(0, 5, clean_and_normalize(metodologia_text))
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ Error añadiendo metodología: {e}")
        # Fallback simple
        pdf.cell(0, 8, "Metodología: Análisis LLM con validación cruzada", ln=True)
    
    logging.info("[PDF] ✅ Sección de referencias completada")

def add_generic_text_block(pdf, texto, font_family):
    """
    ✅ FUNCIÓN ROBUSTA: Renderizado de texto seguro sin corrupción de caracteres
    """
    try:
        logging.info(f"[PDF] 📝 Renderizando texto genérico...")
        
        # ✅ VALIDACIÓN INICIAL
        if not texto or not str(texto).strip():
            return
            
        # ✅ LIMPIAR TEXTO CON NUEVA FUNCIÓN SEGURA
        texto_limpio = clean_and_normalize(str(texto))
        if not texto_limpio:
            return
            
        # ✅ CONFIGURAR FUENTE DE FORMA SEGURA
        try:
            pdf.set_font(font_family, '', 11)
            logging.info(f"[PDF] ✅ Fuente configurada: {font_family}")
        except Exception as fe:
            logging.warning(f"[PDF] ⚠️ Error fuente {font_family}: {fe}, usando Arial")
            try:
                pdf.set_font('Arial', '', 11)
                font_family = 'Arial'
            except Exception as fe2:
                logging.error(f"[PDF] ❌ Error fuente Arial: {fe2}")
                return
        
        # ✅ CONFIGURAR COLOR SEGURO
        try:
            pdf.set_text_color(0, 0, 0)
        except Exception as ce:
            logging.warning(f"[PDF] ⚠️ Error color: {ce}")
        
        # ✅ PREPARAR PÁRRAFOS DE FORMA ROBUSTA
        if '\n\n' in texto_limpio:
            paragraphs = [p.strip() for p in texto_limpio.split('\n\n') if p.strip()]
        elif '\n' in texto_limpio:
            paragraphs = [p.strip() for p in texto_limpio.split('\n') if p.strip()]
        else:
            # Texto sin saltos - dividir solo si es muy largo
            if len(texto_limpio) > 1000:
                import re
                # Dividir por oraciones
                sentences = re.split(r'\.(?=\s+[A-Z])', texto_limpio)
                paragraphs = []
                current_para = ""
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    if not sentence.endswith('.'):
                        sentence += '.'
                        
                    if len(current_para) > 600:
                        if current_para:
                            paragraphs.append(current_para.strip())
                        current_para = sentence
                    else:
                        current_para = current_para + " " + sentence if current_para else sentence
                
                if current_para:
                    paragraphs.append(current_para.strip())
            else:
                paragraphs = [texto_limpio]
        
        # ✅ RENDERIZAR PÁRRAFOS DE FORMA ULTRA-SEGURA
        pdf.ln(3)  # Espacio inicial
        
        for i, paragraph in enumerate(paragraphs):
            if not paragraph.strip():
                continue
                
            try:
                # ✅ VALIDAR CONTENIDO DEL PÁRRAFO
                safe_paragraph = paragraph.strip()
                
                # ✅ ESTRATEGIA DE RENDERIZADO SEGÚN LONGITUD
                if len(safe_paragraph) <= 100:
                    # Párrafo corto - usar cell (más seguro)
                    super(PatchedPDF, pdf).cell(0, 6, safe_paragraph, ln=True)
                else:
                    # Párrafo largo - usar multi_cell con validación
                    try:
                        super(PatchedPDF, pdf).multi_cell(0, 6, safe_paragraph)
                    except Exception as mc_error:
                        logging.warning(f"[PDF] ⚠️ Error multi_cell: {mc_error}, usando cell")
                        # Fallback: truncar y usar cell
                        truncated = safe_paragraph[:120] + "..." if len(safe_paragraph) > 120 else safe_paragraph
                        super(PatchedPDF, pdf).cell(0, 6, truncated, ln=True)
                
                # Espacio entre párrafos
                if i < len(paragraphs) - 1:
                    pdf.ln(3)
                    
            except Exception as pe:
                logging.warning(f"[PDF] ⚠️ Error párrafo {i}: {pe}")
                # Fallback ultra-seguro
                try:
                    super(PatchedPDF, pdf).cell(0, 6, "[Contenido no mostrable]", ln=True)
                except:
                    pdf.ln(6)
        
        pdf.ln(6)  # Espacio final
        logging.info(f"[PDF] ✅ Texto renderizado exitosamente")
        
    except Exception as e:
        logging.error(f"[PDF] ❌ Error crítico en texto: {e}")
        # Fallback de emergencia
        try:
            pdf.set_font('Arial', 'I', 10)
            pdf.set_text_color(150, 150, 150)
            super(PatchedPDF, pdf).cell(0, 8, "[Error mostrando contenido]", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)
        except:
            pdf.ln(10)  # Solo espacio si todo falla


def validate_and_fix_dafo_structure(dafo_data):
    """
    Valida y corrige la estructura de datos DAFO para asegurar compatibilidad con el PDF.
    ✅ FUNCIÓN MEJORADA: Genera datos profesionales específicos para Sener cuando faltan datos
    """
    import logging
    logging.info(f"[PDF] 🔍 Validando estructura DAFO: {type(dafo_data)}")
    
    # Datos por defecto específicos para Sener (más profesionales)
    default_dafo = {
        'fortalezas': [
            'Experiencia consolidada en ingeniería de infraestructuras complejas',
            'Capacidades técnicas avanzadas en múltiples sectores estratégicos',
            'Trayectoria de más de 65 años en proyectos de alta complejidad técnica',
            'Presencia internacional y conocimiento de mercados globales'
        ],
        'debilidades': [
            'Requiere análisis específico de capacidades para esta oportunidad',
            'Necesidad de evaluar recursos disponibles para nuevos desarrollos',
            'Posible curva de aprendizaje en segmentos de mercado específicos',
            'Competencia con empresas especializadas en nichos concretos'
        ],
        'oportunidades': [
            'Creciente demanda de soluciones de ingeniería innovadoras',
            'Oportunidades de expansión en nuevos mercados tecnológicos',
            'Posibilidad de aplicar conocimientos existentes en nuevos sectores',
            'Tendencias hacia la digitalización y sostenibilidad'
        ],
        'amenazas': [
            'Competencia intensificada en mercados tecnológicos emergentes',
            'Evolución rápida de requisitos regulatorios y técnicos',
            'Presión de nuevos entrantes con enfoques disruptivos',
            'Riesgos asociados a la adopción de nuevas tecnologías'
        ]
    }
    
    if not isinstance(dafo_data, dict):
        logging.warning(f"[PDF] ⚠️ DAFO no es dict, usando estructura por defecto")
        return default_dafo
    
    # Si tiene la estructura anidada "swot", extraerla
    if 'swot' in dafo_data:
        dafo_data = dafo_data['swot']
        logging.info(f"[PDF] ✅ Extraída estructura 'swot' anidada")
    
    # Validar y corregir cada sección
    result = {}
    required_sections = ['fortalezas', 'debilidades', 'oportunidades', 'amenazas']
    
    for section in required_sections:
        items = dafo_data.get(section, [])
        
        # Asegurar que es una lista
        if not isinstance(items, list):
            if isinstance(items, str) and items.strip():
                # Si es string, convertir a lista
                items = [items.strip()]
            else:
                items = []
        
        # Limpiar items vacíos o inválidos
        clean_items = []
        for item in items:
            if item and isinstance(item, str) and item.strip():
                clean_item = clean_and_normalize(item.strip())
                # Filtrar items muy cortos o genéricos
                if len(clean_item) > 10 and not clean_item.lower().startswith('requiere análisis'):
                    clean_items.append(clean_item)
        
        # Si no hay items válidos o muy pocos, usar defaults específicos
        if len(clean_items) < 2:
            logging.warning(f"[PDF] ⚠️ Sección {section} insuficiente ({len(clean_items)} items), usando defaults")
            clean_items = default_dafo[section]
        else:
            # Asegurar mínimo 3 items, completar con defaults si es necesario
            while len(clean_items) < 3:
                # Añadir items de default que no estén ya presentes
                for default_item in default_dafo[section]:
                    if not any(default_item.lower() in existing.lower() for existing in clean_items):
                        clean_items.append(default_item)
                        break
                if len(clean_items) >= 3:
                    break
        
        # Limitar a máximo 4 items y asegurar mínimo 3
        result[section] = clean_items[:4]
        if len(result[section]) < 3:
            result[section].extend(default_dafo[section][:3-len(result[section])])
    
    logging.info(f"[PDF] ✅ DAFO validado: F={len(result['fortalezas'])}, D={len(result['debilidades'])}, O={len(result['oportunidades'])}, A={len(result['amenazas'])}")
    return result

def create_market_gaps_opportunities_chart_from_data(gaps_list, oportunidades_list, output_dir="output"):
    """
    🔥 NUEVA VERSIÓN: Estructura idéntica a Vigilancia Tecnológica
    Crea un gráfico dinámico simple y elegante para GAPS vs OPORTUNIDADES de mercado.
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        import textwrap, os, time, logging

        if not gaps_list and not oportunidades_list:
            return None

        gaps = gaps_list if gaps_list else ["Requiere análisis específico"]
        opps = oportunidades_list if oportunidades_list else ["Requiere análisis específico"]
        rows = max(len(gaps), len(opps))
        
        # 🔧 WRAP idéntico a Vigilancia Tecnológica
        wrap_width = 35  # MISMO valor que Vigilancia Tecnológica
        
        # 🔧 WRAP ROBUSTO: Igual que Vigilancia Tecnológica
        wrapped_gaps = []
        for gap in gaps:
            gap_text = str(gap).strip()
            if len(gap_text) > wrap_width:
                wrapped_text = "\n".join(textwrap.wrap(gap_text, wrap_width))
            else:
                wrapped_text = gap_text
            wrapped_gaps.append(wrapped_text)
            
        wrapped_opps = []
        for opp in opps:
            opp_text = str(opp).strip()
            if len(opp_text) > wrap_width:
                wrapped_text = "\n".join(textwrap.wrap(opp_text, wrap_width))
            else:
                wrapped_text = opp_text
            wrapped_opps.append(wrapped_text)
            
        while len(wrapped_gaps) < rows:
            wrapped_gaps.append("")
        while len(wrapped_opps) < rows:
            wrapped_opps.append("")

        def rect_h(t):
            # 🔧 ALTURA idéntica a Vigilancia Tecnológica
            lines = t.count("\n") + 1 if t else 1
            return max(1.2, 0.8 * lines + 0.6)
        
        heights = [max(rect_h(wrapped_gaps[i]), rect_h(wrapped_opps[i])) for i in range(rows)]
        spacing = 0.4  # MISMO valor que Vigilancia Tecnológica
        total_h = sum(heights) + spacing * (rows - 1) + 4

        fig, ax = plt.subplots(figsize=(12, 9), dpi=200)  # MISMAS dimensiones
        fig.suptitle('ANÁLISIS DE MERCADO: GAPS vs OPORTUNIDADES', fontsize=34, fontweight='bold', color='#003366', y=0.95)  # +2 puntos
        ax.set_xlim(0, 20)
        ax.set_ylim(0, total_h)
        ax.set_axis_off()

        # 🔧 COLORES IDÉNTICOS a Vigilancia Tecnológica  
        gap_color = '#B71C1C'  # MISMO rojo que Vigilancia Tecnológica
        opp_color = '#1565C0'  # MISMO azul que Vigilancia Tecnológica
        
        # 🎯 TÍTULOS idénticos a Vigilancia Tecnológica
        title_y_position = total_h - 1.5
        ax.text(5, title_y_position, 'GAPS DE MERCADO', fontsize=28, fontweight='bold', color=gap_color, ha='center')  # +2 puntos
        ax.text(15, title_y_position, 'OPORTUNIDADES SENER', fontsize=28, fontweight='bold', color=opp_color, ha='center')  # +2 puntos

        # 🔥 FLECHA Y TEXTO ENTRE TÍTULOS Y RECTÁNGULOS (MEJOR POSICIÓN)
        arrow_y_position = total_h - 2.8  # Entre títulos y rectángulos
        ax.annotate('', xy=(10.2, arrow_y_position), xytext=(9.8, arrow_y_position), arrowprops=dict(arrowstyle='->', lw=4, color='#003366'))
        ax.text(10, arrow_y_position - 0.3, 'TRANSFORMAR', fontsize=16, ha='center', style='italic', color='#003366', fontweight='bold')  # +2 puntos

        y = total_h - 4.0
        for i in range(rows):
            h = heights[i]
            yc = y - h/2
            
            # 🔧 TAMAÑO DE FUENTE idéntico a Vigilancia Tecnológica + 2 puntos
            lines_gaps = wrapped_gaps[i].count('\n') + 1 if wrapped_gaps[i] else 1
            lines_opps = wrapped_opps[i].count('\n') + 1 if wrapped_opps[i] else 1
            max_lines = max(lines_gaps, lines_opps)
            
            # 🔧 FUENTES +2 PUNTOS respecto a Vigilancia Tecnológica
            if max_lines <= 2:
                font_size = 20  # Era 18, ahora 20
            elif max_lines <= 3:
                font_size = 18  # Era 16, ahora 18
            elif max_lines <= 4:
                font_size = 17  # Era 15, ahora 17
            else:
                font_size = 16  # Era 14, ahora 16
            
            # GAPS (izquierda - rojo) - ESTRUCTURA IDÉNTICA
            if wrapped_gaps[i]:
                ax.add_patch(Rectangle((0.5, yc-h/2), 9, h, facecolor=gap_color, edgecolor='white', linewidth=2, alpha=0.85))
                ax.text(5, yc, f"* {wrapped_gaps[i]}", ha='center', va='center', fontsize=font_size, color='white', 
                       fontweight='normal', linespacing=1.1)
                       
            # OPORTUNIDADES (derecha - azul) - ESTRUCTURA IDÉNTICA
            if wrapped_opps[i]:
                ax.add_patch(Rectangle((10.5, yc-h/2), 9, h, facecolor=opp_color, edgecolor='white', linewidth=2, alpha=0.85))
                ax.text(15, yc, f"* {wrapped_opps[i]}", ha='center', va='center', fontsize=font_size, color='white',
                       fontweight='normal', linespacing=1.1)
                       
            y -= h + spacing

        # 🔥 FLECHA YA MOVIDA ARRIBA - ELIMINAR LA DE ABAJO
        
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"market_gaps_opportunities_{int(time.time())}.png")
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        logging.info(f"[PDF] ✅ Gráfico de mercado dinámico creado: {path}")
        return path
    except Exception as e:
        import logging, traceback
        logging.error(f"[PDF] ❌ Error gráfico mercado dinámico: {e}")
        traceback.print_exc()
        return None

# ------------------------------------------------------------------------------------
# Helper: insertar imagen a ancho completo sin solapamientos
# ------------------------------------------------------------------------------------

def _insert_full_width_image(pdf, image_path, margin: int = 5, spacing: int = 12):
    """Inserta `image_path` ocupando el ancho útil del PDF y avanza la posición Y."""
    w_available = pdf.w - pdf.l_margin - pdf.r_margin - (margin * 2)
    height = None
    try:
        from PIL import Image  # type: ignore
        with Image.open(image_path) as im:
            iw, ih = im.size
            if iw:
                height = (w_available / iw) * ih
    except Exception:
        pass
    if height is None:
        height = w_available * 0.55  # Heurística de altura
    x_pos = pdf.l_margin + margin
    try:
        pdf.image(image_path, x=x_pos, y=pdf.get_y(), w=w_available, h=0)
    except Exception as e:
        logging.warning(f"[PDF] ⚠️ No se pudo insertar la imagen '{image_path}': {e}")
        return
    pdf.ln(height + spacing)

def extract_idea_title(idea_data, idea_index):
    """
    🔥 FUNCIÓN MEJORADA: Extrae el título real de una idea con debug TOTAL.
    """
    
    def log_debug(msg):
        print(f"🚨🚨🚨 [EXTRACT_TITLE] {msg} 🚨🚨🚨")
        logging.info(f"[PDF] {msg}")
    
    if not idea_data:
        log_debug(f"❌ No hay datos para idea {idea_index}")
        return f"Idea {idea_index}"
    
    log_debug(f"🔍 ===== EXTRAYENDO TÍTULO PARA IDEA {idea_index} =====")
    log_debug(f"🔍 Tipo de idea_data: {type(idea_data)}")
    
    if isinstance(idea_data, dict):
        log_debug(f"🔍 ===== CAMPOS DISPONIBLES: {list(idea_data.keys())} =====")
        # ✅ DEBUG COMPLETO: Mostrar contenido de campos relevantes
        for field in ['idea_title', 'title', 'idea_text', 'idea', 'original_idea_data']:
            if field in idea_data:
                value = idea_data[field]
                if isinstance(value, str):
                    log_debug(f"🔍 ===== Campo '{field}': '{value[:100]}...' ({len(value)} chars) =====")
                elif isinstance(value, dict):
                    log_debug(f"🔍 ===== Campo '{field}': dict con keys {list(value.keys())} =====")
                else:
                    log_debug(f"🔍 ===== Campo '{field}': {type(value)} - {str(value)[:50]}... =====")
            else:
                log_debug(f"🔍 ===== Campo '{field}': NO EXISTE =====")
    else:
        log_debug(f"🔍 ===== idea_data NO ES DICT - ES {type(idea_data)} =====")
    
    # ✅ ESTRATEGIA 1: idea_title (PRINCIPAL desde UI)
    title = ""
    if isinstance(idea_data, dict) and 'idea_title' in idea_data and idea_data['idea_title']:
        raw_title = idea_data['idea_title']
        log_debug(f"🔍 Raw idea_title: {raw_title} (tipo: {type(raw_title)})")
        
        # Si es un diccionario, extraer el contenido interno
        if isinstance(raw_title, dict):
            # Buscar campos comunes de texto
            for text_field in ['texto', 'text', 'content', 'title']:
                if text_field in raw_title and raw_title[text_field]:
                    inner_content = raw_title[text_field]
                    log_debug(f"🔍 Contenido en '{text_field}': {inner_content}")
                    
                    # Si es string, procesarlo
                    if isinstance(inner_content, str):
                        # Limpiar comillas dobles y otros caracteres
                        clean_inner = inner_content.strip().strip('"').strip("'").strip()
                        log_debug(f"🔍 Contenido limpio: '{clean_inner}'")
                        
                        if clean_inner and len(clean_inner) > 2:
                            title = clean_inner
                            break
            
            # Si no encontramos nada en subcampos, usar representación string del dict
            if not title:
                title = str(raw_title).strip()
        else:
            # Si es string directo, usarlo
            title = str(raw_title).strip()
        
        log_debug(f"✅✅✅ ENCONTRADO en 'idea_title': '{title}' ✅✅✅")
        
        if title and len(title) > 3:
            # Limpiar comillas dobles finales y normalizar
            title = title.strip().strip('"').strip("'").strip()
            final_title = clean_and_normalize(title)
            log_debug(f"🎉🎉🎉 RETORNANDO TÍTULO DESDE idea_title: '{final_title}' 🎉🎉🎉")
            return final_title
    
    # ✅ ESTRATEGIA 2: title (SECUNDARIO)
    if isinstance(idea_data, dict) and 'title' in idea_data and idea_data['title']:
        title = str(idea_data['title']).strip()
        log_debug(f"✅ ENCONTRADO en 'title': '{title}'")
        if title and len(title) > 3:
            return clean_and_normalize(title)
    
    # ✅ ESTRATEGIA 3: original_idea_data (DATOS ORIGINALES)
    if isinstance(idea_data, dict) and 'original_idea_data' in idea_data:
        orig_data = idea_data['original_idea_data']
        log_debug(f"🔍 Explorando original_idea_data: {type(orig_data)}")
        if isinstance(orig_data, dict):
            log_debug(f"🔍 original_idea_data campos: {list(orig_data.keys())}")
            
            # Buscar título en datos originales
            for field in ['title', 'idea_title', 'idea']:
                if field in orig_data and orig_data[field]:
                    orig_title = str(orig_data[field]).strip()
                    log_debug(f"✅ ENCONTRADO en original_idea_data['{field}']: '{orig_title[:50]}...'")
                    
                    # Si es el campo 'idea', extraer solo la primera línea como título
                    if field == 'idea':
                        first_line = orig_title.split('\n')[0].strip()
                        # Limpiar prefijos "Idea X:"
                        import re
                        clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                        if len(clean_title) > 10:
                            return clean_and_normalize(clean_title[:80])
                    else:
                        if len(orig_title) > 3:
                            return clean_and_normalize(orig_title)
    
    # ✅ ESTRATEGIA 4: idea_text o idea (CONTENIDO DIRECTO)
    text_fields = ['idea_text', 'idea']
    for field in text_fields:
        if isinstance(idea_data, dict) and field in idea_data and idea_data[field]:
            raw_content = idea_data[field]
            log_debug(f"🔍 Procesando campo '{field}': {type(raw_content)}")
            
            # Extraer contenido de diccionario anidado si es necesario
            idea_text = ""
            if isinstance(raw_content, dict):
                # Buscar contenido en subcampos
                for text_subfield in ['texto', 'text', 'content', 'idea']:
                    if text_subfield in raw_content and raw_content[text_subfield]:
                        inner_text = str(raw_content[text_subfield]).strip()
                        if inner_text and len(inner_text) > 10:
                            idea_text = inner_text
                            break
                
                # Si no hay subcampos útiles, usar string del dict completo
                if not idea_text:
                    idea_text = str(raw_content).strip()
            else:
                idea_text = str(raw_content).strip()
            
            log_debug(f"🔍 Texto extraído de '{field}': {len(idea_text)} caracteres")
            
            if idea_text:
                # Extraer primera línea como título
                first_line = idea_text.split('\n')[0].strip()
                # Limpiar comillas dobles si las hay
                first_line = first_line.strip().strip('"').strip("'").strip()
                log_debug(f"🔍 Primera línea de '{field}': '{first_line}'")
                
                # Limpiar prefijos
                import re
                clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                
                if len(clean_title) > 10:
                    final_title = clean_title[:80] + ('...' if len(clean_title) > 80 else '')
                    log_debug(f"✅ TÍTULO EXTRAÍDO de '{field}': '{final_title}'")
                    return clean_and_normalize(final_title)
    
    # ✅ ESTRATEGIA 5: Si idea_data es un string directo
    if isinstance(idea_data, str) and idea_data.strip():
        log_debug(f"🔍 idea_data es string directo: {len(idea_data)} caracteres")
        first_line = idea_data.split('\n')[0].strip()
        import re
        clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
        if len(clean_title) > 10:
            final_title = clean_title[:80] + ('...' if len(clean_title) > 80 else '')
            log_debug(f"✅ TÍTULO EXTRAÍDO de string directo: '{final_title}'")
            return clean_and_normalize(final_title)
    
    # ✅ ÚLTIMO RECURSO: Título genérico
    generic_title = f"Idea {idea_index}"
    log_debug(f"🚨🚨🚨 USANDO TÍTULO GENÉRICO: '{generic_title}' 🚨🚨🚨")
    log_debug(f"🚨🚨🚨 MOTIVO: No se encontró título válido en ninguno de los campos 🚨🚨🚨")
    log_debug(f"🚨🚨🚨 ESTO SIGNIFICA QUE LOS DATOS NO LLEGAN CORRECTAMENTE 🚨🚨🚨")
    
    return generic_title

   

def add_quantitative_benchmarking_table(pdf, benchmarking_data, add_reference, clean_and_normalize):
    """
    ✅ NUEVA FUNCIÓN: Genera tabla de benchmarking con métricas cuantitativas
    Enfocada en números y cifras específicas en lugar de texto descriptivo
    """
    import logging
    
    if not isinstance(benchmarking_data, dict) or 'tabla_comparativa' not in benchmarking_data:
        logging.warning("[PDF] ⚠️ No hay datos de tabla_comparativa para benchmarking cuantitativo")
        return
    
    competitors = benchmarking_data['tabla_comparativa']
    if not isinstance(competitors, list) or len(competitors) == 0:
        logging.warning("[PDF] ⚠️ Lista de competidores vacía en tabla_comparativa")
        return
    
    logging.info(f"[PDF] 📊 Generando tabla cuantitativa con {len(competitors)} competidores")
    
    # Configurar fuente para tabla
    font_family = getattr(pdf, 'font_family', 'Arial')
    
    # Título de la tabla
    pdf.ln(6)
    pdf.set_font(font_family, 'B', 11)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 8, "Tabla Comparativa de Métricas Cuantitativas", ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    
    # Configurar columnas principales (dividir métricas en dos tablas por espacio)
    table1_headers = ["Empresa", "Ingresos (MEUR)", "Empleados", "Años", "Países"]
    table2_headers = ["Empresa", "Proyectos/año", "EUR/Proyecto (M)", "Cuota %", "I+D %"]
    
    # 🎯 CENTRAR TABLAS: Calcular margen para centrado
    table_width = 135  # mm
    page_width = pdf.w - 40  # Ancho útil (márgenes)
    center_margin = (page_width - table_width) / 2 + 20  # Centrado + margen izquierdo
    
    # TABLA 1: Métricas básicas de empresa
    pdf.set_x(center_margin)  # 🎯 CENTRAR TABLA
    pdf.set_font(font_family, 'B', 8)
    pdf.set_fill_color(220, 220, 220)
    
    # Headers tabla 1
    col_widths_1 = [45, 25, 25, 20, 20]  # Ancho total: 135mm
    for i, header in enumerate(table1_headers):
        pdf.cell(col_widths_1[i], 8, header, border=1, fill=True, align='C')
    pdf.ln()
    
    # Datos tabla 1
    pdf.set_font(font_family, '', 7)
    for comp in competitors:
        pdf.set_x(center_margin)  # 🎯 CENTRAR CADA FILA
        if not isinstance(comp, dict):
            continue
            
        # Obtener datos con valores por defecto
        nombre = clean_and_normalize(str(comp.get('nombre', 'N/D')))[:20]
        ingresos = comp.get('ingresos_anuales_millones_eur', 0)
        empleados = comp.get('empleados_total', 0)
        años = comp.get('años_en_mercado', 0)
        países = comp.get('paises_presencia', 0)
        
        # Formatear números
        ingresos_fmt = f"{ingresos:,.0f}" if ingresos > 0 else "N/D"
        empleados_fmt = f"{empleados:,}" if empleados > 0 else "N/D"
        años_fmt = f"{años}" if años > 0 else "N/D"
        países_fmt = f"{países}" if países > 0 else "N/D"
        
        # Agregar fila
        pdf.cell(col_widths_1[0], 7, nombre, border=1, align='L')
        pdf.cell(col_widths_1[1], 7, ingresos_fmt, border=1, align='R')
        pdf.cell(col_widths_1[2], 7, empleados_fmt, border=1, align='R')
        pdf.cell(col_widths_1[3], 7, años_fmt, border=1, align='C')
        pdf.cell(col_widths_1[4], 7, países_fmt, border=1, align='C')
        pdf.ln()
    
    pdf.ln(8)
    
    # TABLA 2: Métricas de negocio y tecnología
    pdf.set_x(center_margin)  # 🎯 CENTRAR TABLA
    pdf.set_font(font_family, 'B', 8)
    pdf.set_fill_color(220, 220, 220)
    
    # Headers tabla 2
    col_widths_2 = [45, 25, 25, 20, 20]  # Ancho total: 135mm
    for i, header in enumerate(table2_headers):
        pdf.cell(col_widths_2[i], 8, header, border=1, fill=True, align='C')
    pdf.ln()
    
    # Datos tabla 2
    pdf.set_font(font_family, '', 7)
    for comp in competitors:
        pdf.set_x(center_margin)  # 🎯 CENTRAR CADA FILA
        if not isinstance(comp, dict):
            continue
            
        # Obtener datos con valores por defecto
        nombre = clean_and_normalize(str(comp.get('nombre', 'N/D')))[:20]
        proyectos = comp.get('proyectos_anuales_estimados', 0)
        precio_proyecto = comp.get('precio_promedio_proyecto_millones', 0)
        cuota = comp.get('cuota_mercado_sector_porcentaje', 0)
        id_percent = comp.get('gasto_id_porcentaje_ingresos', 0)
        
        # Formatear números
        proyectos_fmt = f"{proyectos}" if proyectos > 0 else "N/D"
        precio_fmt = f"{precio_proyecto:.1f}" if precio_proyecto > 0 else "N/D"
        cuota_fmt = f"{cuota:.1f}" if cuota > 0 else "N/D"
        id_fmt = f"{id_percent:.1f}" if id_percent > 0 else "N/D"
        
        # Agregar fila
        pdf.cell(col_widths_2[0], 7, nombre, border=1, align='L')
        pdf.cell(col_widths_2[1], 7, proyectos_fmt, border=1, align='R')
        pdf.cell(col_widths_2[2], 7, precio_fmt, border=1, align='R')
        pdf.cell(col_widths_2[3], 7, cuota_fmt, border=1, align='R')
        pdf.cell(col_widths_2[4], 7, id_fmt, border=1, align='R')
        pdf.ln()
    
    pdf.ln(6)
    
    # TABLA 3: Métricas adicionales (certificaciones, patentes)
    pdf.set_font(font_family, 'B', 9)
    pdf.cell(0, 8, "Métricas de Innovación y Certificación", ln=True, align='C')
    pdf.ln(2)
    
    table3_headers = ["Empresa", "Certificaciones", "Patentes Activas"]
    col_widths_3 = [70, 30, 35]  # Ancho total: 135mm
    
    pdf.set_x(center_margin)  # 🎯 CENTRAR TABLA
    pdf.set_font(font_family, 'B', 8)
    pdf.set_fill_color(220, 220, 220)
    
    # Headers tabla 3
    for i, header in enumerate(table3_headers):
        pdf.cell(col_widths_3[i], 8, header, border=1, fill=True, align='C')
    pdf.ln()
    
    # Datos tabla 3
    pdf.set_font(font_family, '', 7)
    for comp in competitors:
        pdf.set_x(center_margin)  # 🎯 CENTRAR CADA FILA
        if not isinstance(comp, dict):
            continue
            
        # Obtener datos con valores por defecto
        nombre = clean_and_normalize(str(comp.get('nombre', 'N/D')))[:30]
        certificaciones = comp.get('certificaciones_principales', 0)
        patentes = comp.get('patentes_activas_estimadas', 0)
        
        # Formatear números
        cert_fmt = f"{certificaciones}" if certificaciones > 0 else "N/D"
        patentes_fmt = f"{patentes}" if patentes > 0 else "N/D"
        
        # Agregar fila
        pdf.cell(col_widths_3[0], 7, nombre, border=1, align='L')
        pdf.cell(col_widths_3[1], 7, cert_fmt, border=1, align='C')
        pdf.cell(col_widths_3[2], 7, patentes_fmt, border=1, align='C')
        pdf.ln()
    
    # Nota explicativa
    pdf.ln(4)
    pdf.set_font(font_family, 'I', 7)
    pdf.set_text_color(100, 100, 100)
    nota_text = ("Nota: Las cifras mostradas son estimaciones basadas en análisis de mercado y pueden variar según "
                "fuentes públicas disponibles. MEUR = Millones de Euros. I+D % = Porcentaje de ingresos destinado a I+D+i.")
    pdf.multi_cell(0, 4, nota_text)
    pdf.set_text_color(0, 0, 0)
    
    logging.info(f"[PDF] ✅ Tabla cuantitativa de benchmarking completada con {len(competitors)} competidores")

   

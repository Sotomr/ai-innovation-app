# analysis_module2.py
import warnings
warnings.filterwarnings('ignore')  # Silenciar TODOS los warnings

from fpdf.fpdf import FPDF, FPDFException  # Importación específica para evitar conflictos
import openai
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import tempfile
import json
import os
import requests
import traceback
import concurrent.futures
import re
import time
from openai_config import get_openai_client, get_deployment_name
import shutil  # Agregar esta importación al principio del archivo junto con las demás importaciones
import textwrap
import logging
from contextlib import contextmanager
import unicodedata

# Configuración de logging profesional
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

@contextmanager
def timed(label):
    start = time.time()
    # logging.info(f"⏱️ {label} - INICIO")  # SUPRIMIDO POR PETICIÓN DEL USUARIO
    try:
        yield
    finally:
        elapsed = time.time() - start
        # logging.info(f"⏱️ {label} - FIN ({elapsed:.2f}s)")  # SUPRIMIDO POR PETICIÓN DEL USUARIO

SEVERITY = {5:(255,80,80),4:(255,150,80),3:(255,220,80),2:(200,255,200),1:(230,230,230)}

def fila(pdf, texto, sev, font_family):
    r,g,b = SEVERITY.get(sev,(240,240,240))
    pdf.set_fill_color(r,g,b)
    pdf.set_font(font_family, '', 11)
    pdf.multi_cell(0,6,f"{texto} — Severidad: {sev}",0,'L',True)
    pdf.ln(1)

# Obtener el cliente de OpenAI
client = get_openai_client()
DEPLOYMENT_NAME = get_deployment_name()

# Variables globales
analyzed_ideas_global = []
_last_analyzed_ideas = []
DEFAULT_ANALYSIS_TEMPLATE = """
Analiza la siguiente idea considerando los siguientes aspectos:

1. Viabilidad Técnica: Evaluación de la factibilidad tecnológica y recursos necesarios
2. Potencial de Mercado: Análisis del tamaño de mercado, demanda y posibles clientes
3. Ventaja Competitiva: Diferenciadores frente a soluciones existentes
4. Modelo de Negocio: Posibles vías de monetización y estructura de costes
5. Riesgos y Mitigaciones: Principales obstáculos y estrategias para superarlos

Idea a analizar:
{idea}
"""

def get_analysis_template():
    """Obtiene el template de análisis actual"""
    return DEFAULT_ANALYSIS_TEMPLATE

def update_analysis_template(new_template):
    """Actualiza el template de análisis global"""
    global DEFAULT_ANALYSIS_TEMPLATE
    DEFAULT_ANALYSIS_TEMPLATE = new_template
    return True

def analyze_idea_detailed(idea, prompt_template):
    """
    Analiza una idea individual usando un formato estructurado con secciones claramente identificables
    """
    try:
        # Asegurar que la idea es un string
        if isinstance(idea, dict):
            idea_text = str(idea.get('idea', ''))
        else:
            idea_text = str(idea)
            
        if not idea_text.strip():
            return None, "Idea vacía"
            
        # Formatear el prompt con la idea y pedir secciones CLARAMENTE MARCADAS
        prompt = f"""
        Realiza un análisis exhaustivo y detallado de la siguiente idea, siguiendo EXACTAMENTE la estructura especificada.
        
        Idea a analizar:
        {idea_text}
        
        IMPORTANTE: Marca CLARAMENTE el inicio de cada sección con el formato "**NOMBRE DE SECCIÓN**".
        
        Estructura requerida del análisis:
        
        **RESUMEN EJECUTIVO**
        Proporciona una visión general de la idea, sus puntos clave, valor diferencial e impacto potencial.
        
        **ANÁLISIS TÉCNICO**
        Analiza la viabilidad técnica, requisitos tecnológicos, complejidad de implementación y riesgos técnicos.
        
        **POTENCIAL DE INNOVACIÓN**
        Evalúa el grado de innovación, diferenciación competitiva, oportunidades de patentes y alineación con tendencias.
        
        **ALINEACIÓN ESTRATÉGICA CON SENER**
        Determina cómo encaja con la estrategia de Sener, sinergias con proyectos existentes e impacto en la cartera.
        
        **VIABILIDAD COMERCIAL**
        Analiza el tamaño del mercado, modelo de negocio, costes, proyecciones financieras y barreras de entrada.
        
        **VALORACIÓN GLOBAL**
        Resume fortalezas, debilidades, oportunidades, amenazas y proporciona recomendaciones finales.
        
        INSTRUCCIONES ADICIONALES:
        - Cada sección debe ser detallada (mínimo 250 palabras por sección)
        - Usa lenguaje profesional y técnico
        - Incluye datos cuantitativos cuando sea posible
        - Mantén la estructura exactamente como se solicita con los títulos de sección marcados como **TÍTULO**
        - Evita crear subsecciones adicionales no solicitadas
        """
        
        # Llamar a la API de OpenAI
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
        messages=[
                {"role": "system", "content": "Eres un consultor estratégico senior especializado en innovación industrial con amplia experiencia en empresas de ingeniería como Sener. Ofreces análisis críticos e incisivos, no generalidades. Tus clientes pagan miles de euros por tu experiencia, opiniones claras y recomendaciones accionables basadas en datos."},
            {"role": "user", "content": prompt}
        ],
            temperature=0.7,
            max_tokens=4000
        )
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content.strip()
        
        # Validar que el análisis tiene contenido
        if not analysis or len(analysis) < 100:
            return None, "Análisis demasiado corto o vacío"
            
        # Crear el objeto de idea analizada
        analyzed_idea = {
            'idea': idea_text,
            'analysis': analysis,
            'metrics': {}
        }
        
        return analyzed_idea, None
        
    except Exception as e:
        return None, f"Error en el análisis: {str(e)}"

def extract_analysis_points(prompt):
    """
    Extrae los puntos de análisis específicos del prompt
    para asegurar que se respetan exactamente
    """
    points = []
    
    # Buscar líneas que comiencen con números o viñetas
    pattern = r'(?:^|\n)(?:\d+\.|\-|\*)\s*(.+?)(?=\n|$)'
    matches = re.findall(pattern, prompt)
    
    if matches:
        points = [match.strip() for match in matches]
    
    # Si no se encontraron puntos con el patrón anterior, intentar dividir por líneas
    if not points:
        lines = [line.strip() for line in prompt.split('\n') if line.strip()]
        # Filtrar líneas que parezcan puntos de análisis (evitando títulos o instrucciones)
        points = [line for line in lines if ':' in line or 
                 any(keyword in line.lower() for keyword in ['análisis', 'evaluación', 'potencial', 'viabilidad'])]
    
    return points

def validate_analysis_structure(analysis, expected_points=None):
    """
    Valida que el análisis contenga todos los puntos esperados o tenga una estructura básica válida
    """
    # Basic validation for empty or non-string analysis
    if not analysis or not isinstance(analysis, str):
        return False
    
    # Si no hay puntos específicos, verificar que tenga una estructura mínima coherente
    if expected_points is None or not expected_points:
        # Increase minimum length requirement for validity
        min_length = 250
        min_paragraphs = 3
        
        # Comprobar longitud mínima
        if len(analysis) < min_length:
            return False
        
        # Check for minimum paragraphs - try both newline patterns
        paragraphs = [p for p in analysis.split('\n\n') if p.strip()]
        lines = [l for l in analysis.split('\n') if l.strip()]
        
        if len(paragraphs) < min_paragraphs and len(lines) < min_paragraphs:
            return False
        
        # Check for bullet points or numbered items which should be present in any good analysis
        bullet_pattern = r'(?:\n|\A)(?:[\d\.\-\*\•]+\s+|\d+\.\s+|[\-\*\•]\s+)([^\n]+)'
        bullet_points = re.findall(bullet_pattern, analysis)
        
        if not bullet_points and len(analysis) < 500:
            # If no bullet points and analysis is relatively short, look for key phrases
            # that indicate a structured analysis
            analysis_indicators = [
                'análisis', 'evaluación', 'viabilidad', 'fortalezas', 'debilidades',
                'potencial', 'mercado', 'conclusión', 'recomendación'
            ]
            lower_analysis = analysis.lower()
            indicator_count = sum(1 for indicator in analysis_indicators if indicator in lower_analysis)
            
            # If we don't find at least 3 indicators and no bullet points, it's suspicious
            if indicator_count < 3:
                return False
        
        # Verificar que no contiene solo errores
        error_indicators = [
            'error', 'exception', 'failed', 'could not', 'unable to', 
            'no puedo', 'no es posible', 'lo siento'
        ]
        lower_analysis = analysis.lower()
        if any(indicator in lower_analysis for indicator in error_indicators) and len(analysis) < 400:
            # If error indicators are found, ensure there's enough substantial content
            return False
            
        return True
    
    # Validación específica basada en puntos esperados
    points_found = 0
    for point in expected_points:
        # Skip empty points
        if not point or len(point) < 3:
            continue
            
        # Extraer el título del punto (sin los números o símbolos iniciales)
        point_title = re.sub(r'^[\d\.\-\*\•]+\s*', '', point).strip()
        
        # Ignorar títulos muy cortos (< 3 caracteres) que podrían dar falsos positivos
        if len(point_title) < 3:
            continue
            
        # Try different matching strategies:
        # 1. Direct match
        if re.search(re.escape(point_title), analysis, re.IGNORECASE):
            points_found += 1
            continue
            
        # 2. Check for semantic similarity - look for key phrases
        # Extract the first few words which typically contain the main concept
        key_words = ' '.join(point_title.split()[:3])
        if len(key_words) >= 3 and re.search(re.escape(key_words), analysis, re.IGNORECASE):
            points_found += 1
            continue
    
    # Consider it valid if at least 75% of expected points are found
    min_valid_ratio = 0.75
    if expected_points and len(expected_points) > 0:
        valid_expected_points = [p for p in expected_points if p and len(p.strip()) >= 3]
        if len(valid_expected_points) == 0:
            return True  # No valid points to check against
        
        return points_found / len(valid_expected_points) >= min_valid_ratio
    
    return True

def analyze_ideas_batch(ideas_list, title="", context="", template=None):
    """
    Analiza un lote de ideas en paralelo y genera un PDF con formato profesional.
    Optimizado para máxima eficiencia y compatibilidad con fuentes estándar.
    """
    try:
        if not ideas_list or not isinstance(ideas_list, list):
            print("❌ Error: Se requiere una lista válida de ideas")
            return None, None
            
        # Validar y normalizar las ideas
        validated_ideas = []
        print("\n📋 Iniciando validación de ideas...")
        
        for idx, idea in enumerate(ideas_list):
            if isinstance(idea, dict) and 'idea' in idea:
                validated_ideas.append({
                    'idea': idea['idea'],
                    'index': idx
                })
                print(f"✅ Idea {idx + 1} validada (formato diccionario)")
            elif isinstance(idea, str):
                validated_ideas.append({
                    'idea': idea,
                    'index': idx
                })
                print(f"✅ Idea {idx + 1} validada (formato texto)")
                
        if not validated_ideas:
            print("❌ Error: No hay ideas válidas para analizar")
            return None, None
            
        print(f"\n🚀 Iniciando análisis paralelo de {len(validated_ideas)} ideas...")
        
        # Definir la función de análisis para cada idea
        def analyze_idea(idea_obj):
            try:
                idea_text = idea_obj['idea']
                index = idea_obj['index']
                start_time = time.time()
                
                print(f"\n📝 Procesando idea {index + 1}/{len(validated_ideas)}")
                print(f"⏱️ Inicio de análisis: {datetime.now().strftime('%H:%M:%S')}")
                
                # Contexto optimizado
                sener_context = """
                Sener es una empresa líder en ingeniería y tecnología con especialización en sectores
                aeroespacial, infraestructuras, energía, naval y digitalización. Fundada en 1956, 
                se centra en la excelencia técnica, innovación y desarrollo de soluciones avanzadas.
                """
                
                # 🔧 PROMPT MEJORADO CON ORDEN Y FORMATO ESPECÍFICOS
                prompt = f"""
                Analiza exhaustivamente esta idea para Sener:
                "{idea_text}"
                
                Debes estructurar tu análisis EXACTAMENTE en las siguientes secciones, EN ESTE ORDEN:
                
                RESUMEN EJECUTIVO
                ANÁLISIS TÉCNICO
                POTENCIAL DE INNOVACIÓN
                ALINEACIÓN ESTRATÉGICA CON SENER
                VIABILIDAD COMERCIAL
                VALORACIÓN GLOBAL
                
                INSTRUCCIONES CRÍTICAS DE FORMATO:
                - Usa EXACTAMENTE los nombres de sección arriba, en MAYÚSCULAS
                - NO agregues números ni viñetas a los títulos de sección
                - Cada sección debe tener mínimo 250-300 palabras
                - NO uses comillas tipográficas, guiones largos, ni caracteres especiales
                - Usa solo caracteres ASCII estándar (comillas normales "", guiones simples -)
                
                INSTRUCCIONES DE CONSULTORÍA:
                - Actúa como un consultor de innovación senior con 15+ años de experiencia
                - Proporciona análisis detallados con ejemplos concretos y casos comparables
                - Identifica claramente oportunidades, riesgos y barreras de mercado
                - Incluye métricas relevantes cuando sea aplicable (ROI esperado, tiempo de desarrollo, etc.)
                - Ofrece recomendaciones específicas y accionables, no generalidades
                - Proporciona análisis técnicos rigurosos con base en tendencias reales de mercado
                - NO intentes ser neutral o equilibrado; ofrece opiniones claras y justificadas
                - Haz recomendaciones decisivas sobre si Sener debería o no seguir con la idea
                
                ESTRUCTURA REQUERIDA PARA CADA SECCIÓN:
                - Introducción clara del aspecto a analizar
                - 3-4 puntos clave bien desarrollados
                - Conclusión específica con recomendación
                - Usa párrafos bien estructurados
                """
                
                print(f"🤖 Enviando solicitud a la API para idea {index + 1}...")
                
                # Realizar llamada a la API
                response = client.chat.completions.create(
                    model=DEPLOYMENT_NAME,
                    messages=[
                        {"role": "system", "content": "Eres un consultor estratégico senior especializado en innovación industrial con amplia experiencia en empresas de ingeniería como Sener. Ofreces análisis críticos e incisivos, no generalidades. Tus clientes pagan miles de euros por tu experiencia, opiniones claras y recomendaciones accionables basadas en datos. Usas solo caracteres ASCII básicos en tus informes."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.6
                )
                
                # Procesar la respuesta
                if response and response.choices and response.choices[0].message:
                    # Obtener el título de la idea (primera línea o primeras palabras)
                    idea_title = idea_text.split('\n')[0].strip()
                    if len(idea_title) > 60:
                        idea_title = idea_title[:57] + "..."
                    
                    # Normalizar el texto para eliminar caracteres problemáticos
                    analysis_content = response.choices[0].message.content.strip()
                    
                    # DEBUG: Imprimir los primeros 100 caracteres del análisis
                    if analysis_content:
                        print(f"🔍 Análisis recibido. Primeros 100 caracteres: {analysis_content[:100]}...")
                    else:
                        print("⚠️ Análisis recibido está vacío")
                    
                    end_time = time.time()
                    processing_time = end_time - start_time
                    
                    print(f"✅ Análisis completado para idea {index + 1}")
                    print(f"⏱️ Tiempo de procesamiento: {processing_time:.2f} segundos")
                    print(f"📊 Longitud del análisis: {len(analysis_content)} caracteres")
                        
                    return {
                        'idea': idea_text,
                        'idea_title': idea_title,
                        'analysis': analysis_content,
                        'original_index': index,
                        'processing_time': processing_time
                    }
                else:
                    print(f"❌ Error: No se recibió respuesta válida para idea {index + 1}")
                    return None
                    
            except Exception as e:
                print(f"❌ Error analizando idea #{idea_obj['index']}: {str(e)}")
                print(f"📋 Detalles del error: {traceback.format_exc()}")
                return None
        
        # Ejecutar análisis en paralelo
        max_workers = min(10, len(validated_ideas))
        print(f"\n⚙️ Configurando procesamiento paralelo con {max_workers} workers...")
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            print("🔄 Iniciando workers...")
            futures = [executor.submit(analyze_idea, idea) for idea in validated_ideas]
            
            # Monitorear el progreso
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                print(f"\n📊 Progreso: {completed}/{len(validated_ideas)} ideas procesadas")
                if future.exception():
                    print(f"❌ Error en worker: {future.exception()}")
        
        # Filtrar resultados válidos
        results = [future.result() for future in futures if future.result() is not None]
        valid_results = [result for result in results if result is not None]
        
        if not valid_results:
            print("❌ Error: No se pudo analizar ninguna idea")
            return None, None
            
        # Ordenar resultados por índice original
        valid_results.sort(key=lambda x: x['original_index'])

        # ------------------------------------------------------------------
        # SINCRONIZACIÓN GLOBAL  (añadir justo después de ordenar valid_results)
        global_save_analyzed_ideas(valid_results)      # ← ① deja la lista completa
        global _last_analyzed_ideas
        _last_analyzed_ideas = valid_results           # ← ② backup para get_analyzed_ideas()
        # ------------------------------------------------------------------
        
        total_time = time.time() - start_time
        print(f"\n✅ Análisis completado en {total_time:.2f} segundos")
        print(f"📊 Estadísticas:")
        print(f"   - Ideas procesadas: {len(valid_results)}/{len(validated_ideas)}")
        print(f"   - Tiempo promedio por idea: {total_time/len(valid_results):.2f} segundos")
        
        print("\n📄 Generando PDF con los resultados...")
        
        # PRIMERO: Intentar usar la función unificada
        try:
            # Generar PDF con la función unificada (más robusta)
            pdf_ok = generate_unified_pdf(valid_results, pdf_type="professional")
            if pdf_ok:
                print("✅ PDF generado correctamente con función unificada")
                pdf_path = pdf_ok
            else:
                raise Exception("La función unificada de generación de PDF falló")
        except Exception as e1:
            print(f"⚠️ Error con método profesional: {str(e1)}")
            try:
                # ALTERNATIVA: Usar función unificada como fallback seguro
                print("🔄 Intentando generar PDF con función unificada...")
                pdf_path = generate_unified_pdf(valid_results, pdf_type="basic")
                if pdf_path:
                    print(f"✅ PDF generado con función unificada: {pdf_path}")
                else:
                    raise Exception("La función unificada también falló")
            except Exception as e2:
                print(f"❌ Error con método básico: {str(e2)}")
                pdf_path = None
        
        # Texto combinado para mostrar en la interfaz
        combined_text = "\n\n".join([
            f"## Idea {i+1}: {result['idea_title']}\n\n{result['analysis']}"
            for i, result in enumerate(valid_results)
        ])
        
        return combined_text, pdf_path
        
    except Exception as e:
        print(f"❌ Error en proceso de análisis: {str(e)}")
        print(f"📋 Detalles del error: {traceback.format_exc()}")
        return None, None

def generate_unified_pdf(results, output_dir="output", pdf_type="analysis"):
    """
    🔥 FUNCIÓN UNIFICADA para generar PDFs robustos con manejo de errores mejorado.
    
    Args:
        results: Lista de ideas analizadas
        output_dir: Directorio de salida
        pdf_type: Tipo de PDF ('analysis', 'ranking', 'basic')
    """
    try:
        # Validar entrada
        if not results or not isinstance(results, list):
            print("❌ Error: No hay resultados para mostrar en el PDF")
            return None
        
        # Validar que todas las ideas tienen la estructura correcta
        validated_results = []
        for i, result in enumerate(results):
            if isinstance(result, dict):
                validated_results.append(result)
            else:
                print(f"⚠️ Resultado {i+1} no es un diccionario válido, omitiendo...")
                
        if not validated_results:
            print("❌ Error: No hay resultados válidos para el PDF")
            return None
            
        # Preparar directorio de salida
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"analisis_ideas_{timestamp}.pdf")
        
        # Crear PDF robusto
        pdf = CustomPDF(orientation='P', unit='mm', format='A4')
        pdf.set_margins(left=15, top=15, right=15)
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # PORTADA PROFESIONAL MEJORADA
        pdf.skip_header_footer = True
        pdf.add_page()
        
        # Logo más grande usando función unificada (80mm como en ranking)
        load_logo_unified(pdf, y=40, logo_type="standard")
        
        # Título principal más grande (24pt como en ranking)
        pdf.set_font('Arial', 'B', 24)
        pdf.set_text_color(0, 51, 102)  # Azul corporativo
        pdf.ln(130)  # Espacio después del logo
        pdf.cell(0, 20, 'ANÁLISIS DE IDEAS DE INNOVACIÓN', ln=True, align='C')
        
        # Subtítulo profesional
        pdf.set_font('Arial', '', 16)
        pdf.cell(0, 10, 'Informe Técnico de Evaluación', ln=True, align='C')
        
        # Estadísticas y fecha con estilo profesional
        pdf.ln(20)
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(100, 100, 100)  # Gris elegante
        pdf.cell(0, 10, f'Fecha: {datetime.now().strftime("%d/%m/%Y")}', ln=True, align='C')
        pdf.cell(0, 10, f'Total de ideas analizadas: {len(validated_results)}', ln=True, align='C')
        pdf.cell(0, 10, '6 dimensiones de evaluación', ln=True, align='C')
        
        # ÍNDICE PROFESIONAL (ESTILO COMPETENCIA)
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, "Índice de Ideas", ln=True, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)
        
        # 🔧 ELIMINAR TEXTO REDUNDANTE - ir directo al índice
        pdf.ln(10)  # Solo espacio antes del índice

        # ÍNDICE INTERACTIVO PREPARACIÓN (como en competencia)
        toc_entries = []  # Lista para almacenar (titulo, link_id, page_no)
        
        print(f"📋 Preparando entradas de índice para {len(validated_results)} ideas...")

        # Activar header/footer para las páginas de contenido
        pdf.skip_header_footer = False
        
        # CONTENIDO CON LINKS INTERACTIVOS
        seen_titles = set()
        idea_index = 0
        
        for i, result in enumerate(validated_results, 1):
            idea_title = result.get('idea_title', f"Idea {i}").strip()
            norm_title = idea_title.lower()
            
            # Saltar duplicados
            if norm_title in seen_titles:
                print(f"⚠️ Idea duplicada omitida: {idea_title}")
                continue
            seen_titles.add(norm_title)
            
            display_num = len(seen_titles)
            
            # 🔧 CREAR LINK PARA EL ÍNDICE
            link_id = pdf.add_link()
            
            # 🔧 CADA IDEA EN PÁGINA NUEVA - SIN ESPACIOS EN BLANCO
            pdf.add_page()  # Siempre nueva página para cada idea
            # 🔧 ESTABLECER EL LINK EN LA PÁGINA ACTUAL
            pdf.set_link(link_id)
            
            # Crear entrada del índice con título limpio
            clean_index_title = clean_text_for_pdf(idea_title)
            entry_title = f"{display_num}. {clean_index_title}"
            toc_entries.append((entry_title, link_id, pdf.page_no()))
            
            # Título de la idea MÁS GRANDE (17pt) y en azul corporativo
            
            # NO establecer contexto para headers (eliminar header contextual)
            # if hasattr(pdf, 'set_idea_context'):
            #     pdf.set_idea_context(idea_title)
            
            pdf.set_font('Arial', 'B', 17)  # Título aún más grande (17pt)
            pdf.set_text_color(0, 51, 102)  # Azul corporativo
            clean_title = clean_text_for_pdf(idea_title)
            safe_multicell(pdf, f"IDEA {display_num}: {clean_title}", w=0, h=15)
            pdf.set_text_color(0, 0, 0)  # Restaurar color negro para el contenido
            pdf.ln(8)  # 🔧 ESPACIADO UNIFORME: 8mm después del título principal
            
            idea_index += 1
            
            # Análisis
            analysis_text = result.get('analysis', '')
            if not analysis_text or not analysis_text.strip():
                analysis_text = f"[No hay análisis disponible para la idea {i}]"
                
            # Información de debug
            print(f"📝 Idea {i}: Longitud del análisis: {len(analysis_text)} caracteres")
            if len(analysis_text) > 100:
                print(f"Primeros 100 caracteres: '{analysis_text[:100]}...'")
                    
            # 🔧 APLICAR MISMO FORMATO ESTRUCTURADO CON ACENTOS CORREGIDOS
            section_titles = [
                "RESUMEN EJECUTIVO",
                "ANÁLISIS TÉCNICO", 
                "POTENCIAL DE INNOVACIÓN",
                "ALINEACIÓN ESTRATÉGICA CON SENER",
                "VIABILIDAD COMERCIAL",
                "VALORACIÓN GLOBAL"
            ]
            
            import re
            # 🔧 LIMPIAR ANALYSIS_TEXT ANTES DE PROCESARLO
            clean_text = clean_text_for_pdf(analysis_text)
            clean_text = clean_text.replace('**', '').replace('###', '').replace('__', '')
            
            # 🔧 EXTRAER CONTENIDO USANDO process_analysis_text_improved
            # que maneja correctamente los acentos y variaciones
            print(f"🔍 DEBUG: Enviando texto a process_analysis_text_improved")
            print(f"📝 Primeros 200 caracteres del texto limpio: '{clean_text[:200]}...'")
            
            sections_detected = process_analysis_text_improved(clean_text)
            
            print(f"🔍 DEBUG: Secciones detectadas por process_analysis_text_improved:")
            for section_key, section_content in sections_detected.items():
                print(f"   - '{section_key}': {len(section_content)} caracteres")
                if section_content:
                    print(f"     Primeros 100 caracteres: '{section_content[:100]}...'")
            
            blocks = []
            for section_title in section_titles:  # ← ORDEN FIJO
                # Buscar en las secciones detectadas por la función mejorada
                content_found = ""
                
                print(f"🔍 DEBUG: Buscando sección '{section_title}'...")
                
                # Buscar coincidencia exacta primero
                if section_title in sections_detected:
                    content_found = sections_detected[section_title]
                    print(f"   ✅ Encontrada por coincidencia exacta: {len(content_found)} caracteres")
                else:
                    # Buscar por clave normalizada (manejo de acentos)
                    section_normalized = normalize_text(section_title)
                    print(f"   🔍 Buscando por clave normalizada: '{section_normalized}'")
                    
                    for detected_section, detected_content in sections_detected.items():
                        detected_normalized = normalize_text(detected_section)
                        print(f"     Comparando con: '{detected_normalized}'")
                        
                        if detected_normalized == section_normalized:
                            content_found = detected_content
                            print(f"   ✅ Encontrada por normalización: {len(content_found)} caracteres")
                            break
                    
                    # Si aún no se encuentra, buscar parcialmente
                    if not content_found:
                        print(f"   🔍 Buscando por coincidencia parcial...")
                        for detected_section, detected_content in sections_detected.items():
                            detected_normalized = normalize_text(detected_section)
                            # Búsqueda flexible - contiene palabras clave
                            if (any(word in detected_normalized for word in section_normalized.split() if len(word) > 3) or
                                any(word in section_normalized for word in detected_normalized.split() if len(word) > 3)):
                                content_found = detected_content
                                print(f"   ✅ Encontrada por coincidencia parcial: '{detected_section}' → {section_title}: {len(content_found)} caracteres")
                                break
                
                # Si no se encuentra contenido, usar mensaje por defecto
                if not content_found or not content_found.strip():
                    content_found = f"[Sección {section_title} no encontrada en el análisis]"
                    print(f"   ❌ NO ENCONTRADA: usando mensaje por defecto")
                
                blocks.append((section_title, content_found))
            
            # 🔧 RENDERIZAR SECCIONES EN ORDEN FIJO CON FORMATO PROFESIONAL
            for title, content in blocks:
                # Subtítulo con formato mejorado y color corporativo
                pdf.set_font('Arial', 'B', 14)  # Título de sección más grande
                pdf.set_text_color(0, 51, 102)  # Azul corporativo para títulos
                pdf.ln(8)  # 🔧 ESPACIADO UNIFORME: 8mm antes de cada sección
                clean_section_title = clean_text_for_pdf(title)
                pdf.cell(0, 10, clean_section_title, ln=True)
                pdf.set_text_color(0, 0, 0)  # Restaurar color negro para contenido
                pdf.ln(4)  # 🔧 ESPACIADO UNIFORME: 4mm después del título
                
                # Contenido
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(0, 0, 0)
                
                if content and content.strip() and not content.startswith("[Sección"):
                    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
                    for paragraph in paragraphs:
                        if paragraph:
                            safe_multicell(pdf, paragraph, w=0, h=6)
                            pdf.ln(3)  # 🔧 ESPACIADO UNIFORME: 3mm entre párrafos
                else:
                    # Si no hay contenido estructurado, mostrar texto sin formato
                    pdf.set_font('Arial', 'I', 10)
                    pdf.set_text_color(150, 150, 150)
                    pdf.cell(0, 6, "[Contenido no disponible]", ln=True)
                    pdf.set_text_color(0, 0, 0)
                
                pdf.ln(7)  # 🔧 ESPACIADO UNIFORME: 7mm después de cada sección
            
            # Pie de página automático (manejado por CustomPDF.footer())
            # No añadir pie manual para evitar duplicación
        
        # 🔧 GENERAR ÍNDICE INTERACTIVO AL FINAL (página 2)
        if toc_entries:
            print(f"📋 Generando índice interactivo con {len(toc_entries)} entradas...")
            
            # Ir a la página 2 para el índice
            pdf.page = 2
            pdf.set_xy(pdf.l_margin, pdf.t_margin + 30)  # 🔧 MENOS ESPACIO - Posición más cerca del título
            
            # Configurar fuente para el índice (letra pequeña, sin negrita)
            pdf.set_font('Arial', '', 10)  # Letra pequeña como antes
            pdf.set_text_color(0, 0, 0)
            
            # Renderizar cada entrada del índice
            for toc_title, toc_link, toc_page in toc_entries:
                try:
                    # 🔧 NÚMEROS FIJOS EN MARGEN DERECHO - SIN IDENTADO
                    
                    current_y = pdf.get_y()
                    page_text = str(toc_page)
                    
                    # 1. Título con link
                    pdf.set_xy(pdf.l_margin, current_y)
                    title_width = pdf.get_string_width(toc_title)
                    pdf.cell(title_width, 6, toc_title, ln=False, link=toc_link)
                    
                    # 2. NÚMERO FIJO EN MARGEN DERECHO (posición absoluta)
                    page_x_position = pdf.w - pdf.r_margin - 10  # 10mm desde margen derecho
                    pdf.set_xy(page_x_position, current_y)
                    pdf.cell(10, 6, page_text, ln=False, align='R')
                    
                    # 3. Puntos que llenan EXACTAMENTE el espacio hasta los números
                    dots_start_x = pdf.l_margin + title_width + 1  # Solo 1mm de separación
                    dots_end_x = page_x_position - 1               # Solo 1mm antes del número
                    dots_width = dots_end_x - dots_start_x
                    
                    if dots_width > 3:
                        dot_width = pdf.get_string_width('.')
                        dots_count = int(dots_width / dot_width)
                        dots_count = max(5, dots_count)  # Mínimo 5 puntos, sin máximo
                        dots = '.' * dots_count
                        
                        pdf.set_xy(dots_start_x, current_y)
                        pdf.cell(dots_width, 6, dots, ln=False, align='C')  # Centrados para llenar mejor
                    
                    # Siguiente línea
                    pdf.set_xy(pdf.l_margin, current_y + 6)
                    
                    # Verificar si necesitamos nueva página
                    if pdf.get_y() > (pdf.h - pdf.b_margin - 20):
                        pdf.add_page()
                        pdf.set_xy(pdf.l_margin, pdf.t_margin)
                        
                except Exception as entry_error:
                    print(f"⚠️ Error renderizando entrada de índice '{toc_title}': {entry_error}")
                    # Fallback simple con posicionamiento fijo
                    try:
                        current_y = pdf.get_y()
                        # Título truncado
                        short_title = toc_title[:50] + "..." if len(toc_title) > 50 else toc_title
                        pdf.set_xy(pdf.l_margin, current_y)
                        pdf.cell(120, 8, short_title, ln=False, link=toc_link)
                        # Número fijo en margen derecho
                        pdf.set_xy(pdf.w - pdf.r_margin - 15, current_y)
                        pdf.cell(15, 8, str(toc_page), ln=True, align='R')
                        pdf.ln(1)
                    except:
                        print(f"⚠️ Error grave con entrada de índice, saltando...")
                        continue
                        
            print(f"✅ Índice interactivo generado con {len(toc_entries)} entradas en página 2")
        else:
            print("⚠️ No hay entradas para el índice")
            
        # Guardar PDF
        try:
            pdf.output(pdf_path)
            print(f"✅ PDF básico generado correctamente: {pdf_path}")
            return pdf_path
        except Exception as e:
            print(f"❌ Error al guardar PDF: {str(e)}")
            traceback.print_exc()
            return None
            
    except Exception as e:
        print(f"❌ Error general al generar PDF: {str(e)}")
        traceback.print_exc()
        return None

def normalize_text_for_pdf(text):
    """
    Normaliza el texto para su presentación en el PDF, mejorando la legibilidad
    y el formato.
    """
    if not text:
        return ""
        
    # Convertir a string si no lo es
    text = str(text)
    
    # Eliminar caracteres especiales de markdown
    text = re.sub(r'#{1,6}\s+', '', text)  # Eliminar encabezados
    text = re.sub(r'\*\*|\*|__|\^', '', text)  # Eliminar énfasis
    text = re.sub(r'---+', '', text)  # Eliminar líneas horizontales
    
    # Eliminar espacios múltiples
    text = re.sub(r'\s+', ' ', text)
                
    # Eliminar espacios al inicio y final
    text = text.strip()
    
    # Normalizar saltos de línea
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Máximo dos saltos de línea consecutivos
    
    # Normalizar puntos y comas
    text = re.sub(r'\s*([.,;:])\s*', r'\1 ', text)  # Espacio después de puntuación
    text = re.sub(r'\s+([.,;:])', r'\1', text)  # Eliminar espacio antes de puntuación
    
    # Normalizar paréntesis
    text = re.sub(r'\(\s+', '(', text)  # Eliminar espacio después de paréntesis abierto
    text = re.sub(r'\s+\)', ')', text)  # Eliminar espacio antes de paréntesis cerrado
    
    # Normalizar comillas
    text = re.sub(r'"\s+', '"', text)  # Eliminar espacio después de comilla abierta
    text = re.sub(r'\s+"', '"', text)  # Eliminar espacio antes de comilla cerrada
    
    # Normalizar guiones
    text = re.sub(r'\s*-\s*', '-', text)  # Eliminar espacios alrededor de guiones
    
    # Normalizar números y unidades
    text = re.sub(r'(\d)\s+([a-zA-Z])', r'\1\2', text)  # Eliminar espacio entre número y unidad
    
    # Normalizar acrónimos
    text = re.sub(r'([A-Z])\.\s+([A-Z])\.', r'\1.\2.', text)  # Eliminar espacio entre letras de acrónimo
    
    # Normalizar listas
    text = re.sub(r'^\s*[-•*]\s+', '• ', text, flags=re.MULTILINE)  # Normalizar viñetas
    
    # Normalizar números de lista
    text = re.sub(r'^\s*(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)  # Normalizar números de lista
    
    # Normalizar espacios en párrafos
    paragraphs = text.split('\n\n')
    processed_paragraphs = []
    
    for paragraph in paragraphs:
        # Eliminar espacios al inicio y final de cada línea
        lines = [line.strip() for line in paragraph.split('\n')]
        # Unir líneas con un espacio
        processed_paragraph = ' '.join(lines)
        # Eliminar espacios múltiples
        processed_paragraph = re.sub(r'\s+', ' ', processed_paragraph)
        if processed_paragraph.strip():  # Solo añadir párrafos no vacíos
            processed_paragraphs.append(processed_paragraph)
    
    # Unir párrafos con doble salto de línea
    text = '\n\n'.join(processed_paragraphs)
    
    # Si después de toda la normalización el texto está vacío, devolver el texto original
    if not text.strip():
        return str(text)
    
    return text

def emergency_clean_text(text):
    """
    Función de limpieza de emergencia que garantiza que el texto solo contiene caracteres ASCII.
    Se usa como último recurso cuando clean_text_for_pdf falla.
    """
    if not text:
        return ""
    
    # Asegurar que solo caracteres ASCII básicos estén presentes
    result = ""
    for char in text:
        if ord(char) < 128:  # Solo caracteres ASCII estándar
            result += char
        else:
            # Reemplazar cualquier otro caracter con espacio
            result += ' '
    
    # Normalizar espacios múltiples
    result = re.sub(r' +', ' ', result)
    return result.strip()

def normalize_text(text):
    """Normaliza texto removiendo acentos y convirtiendo a minúsculas"""
    import unicodedata
    # Remover acentos
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    # Convertir a minúsculas y limpiar espacios extra
    return text.lower().strip()

def process_analysis_text_improved(text):
    """
    Procesa el texto del análisis para identificar y estructurar las secciones.
    Retorna un diccionario con las secciones identificadas y su contenido.
    """
    if not text or not isinstance(text, str):
        return {"GENERAL": "No hay análisis disponible."}
    
    # print(f"🔍 Procesando texto de {len(text)} caracteres")
        
    # Definir las secciones principales y sus variantes (SIN ACENTOS Y CON VARIACIONES)
    main_sections = {
        "RESUMEN EJECUTIVO": [
            "RESUMEN EJECUTIVO", "resumen ejecutivo", "RESUMEN", "resumen", "RESUMEN:", "resumen:",
            "**RESUMEN EJECUTIVO**", "**resumen ejecutivo**", "**RESUMEN**"
        ],
        "ANÁLISIS TÉCNICO": [
            "ANÁLISIS TÉCNICO", "ANALISIS TECNICO", "analisis tecnico", "análisis técnico",
            "ANÁLISIS TÉCNICO:", "ANALISIS TECNICO:", "analisis tecnico:", "análisis técnico:",
            "**ANÁLISIS TÉCNICO**", "**ANALISIS TECNICO**", "**analisis tecnico**", "**análisis técnico**"
        ],
        "POTENCIAL DE INNOVACIÓN": [
            "POTENCIAL DE INNOVACIÓN", "POTENCIAL DE INNOVACION", "potencial de innovacion", "potencial de innovación",
            "INNOVACIÓN", "INNOVACION", "innovacion", "innovación",
            "POTENCIAL DE INNOVACIÓN:", "POTENCIAL DE INNOVACION:", "potencial de innovacion:", "potencial de innovación:",
            "**POTENCIAL DE INNOVACIÓN**", "**POTENCIAL DE INNOVACION**", "**potencial de innovacion**"
        ],
        "ALINEACIÓN ESTRATÉGICA CON SENER": [
            "ALINEACIÓN ESTRATÉGICA CON SENER", "ALINEACION ESTRATEGICA CON SENER", "alineacion estrategica con sener",
            "ALINEACIÓN ESTRATÉGICA", "ALINEACION ESTRATEGICA", "alineacion estrategica", "alineación estratégica",
            "ALINEACIÓN CON SENER", "ALINEACION CON SENER", "alineacion con sener", "alineación con sener",
            "ALINEACIÓN ESTRATÉGICA:", "ALINEACION ESTRATEGICA:", "alineacion estrategica:", "alineación estratégica:",
            "**ALINEACIÓN ESTRATÉGICA CON SENER**", "**ALINEACION ESTRATEGICA CON SENER**", "**alineacion estrategica con sener**",
            "**ALINEACIÓN ESTRATÉGICA**", "**ALINEACION ESTRATEGICA**", "**alineacion estrategica**"
        ],
        "VIABILIDAD COMERCIAL": [
            "VIABILIDAD COMERCIAL", "viabilidad comercial", "VIABILIDAD", "viabilidad",
            "VIABILIDAD COMERCIAL:", "viabilidad comercial:", "VIABILIDAD:", "viabilidad:",
            "**VIABILIDAD COMERCIAL**", "**viabilidad comercial**", "**VIABILIDAD**"
        ],
        "VALORACIÓN GLOBAL": [
            "VALORACIÓN GLOBAL", "VALORACION GLOBAL", "valoracion global", "valoración global",
            "CONCLUSIÓN", "CONCLUSION", "conclusion", "conclusión",
            "VALORACIÓN GLOBAL:", "VALORACION GLOBAL:", "valoracion global:", "valoración global:",
            "**VALORACIÓN GLOBAL**", "**VALORACION GLOBAL**", "**valoracion global**", "**valoración global**"
        ]
    }
    
    # Inicializar el diccionario de secciones
    sections = {}
    current_section = None
    current_content = []
    
    # Procesar el texto línea por línea
    lines = text.split('\n')
    
    for line_num, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Verificar si es un título de sección
        is_section = False
        line_normalized = normalize_text(line)
        
        # PRIMERA VERIFICACIÓN: Debe ser una línea corta para ser un título
        if len(line.strip()) > 100:  # Si la línea es muy larga, probablemente no es un título
            pass  # No es título, continúa como contenido
        else:
            for section, variants in main_sections.items():
                # Normalizar cada variante y compararla
                for variant in variants:
                    variant_normalized = normalize_text(variant)
                    # BÚSQUEDA EXACTA PARA TÍTULOS - no buscar en contenido
                    if (line_normalized == variant_normalized or 
                        line_normalized.startswith(variant_normalized) or
                        variant_normalized in line_normalized):
                        
                        # SEGUNDA VERIFICACIÓN: El título debe estar al inicio de línea o ser la línea completa
                        # No debe ser parte de una oración larga
                        words_after = line_normalized.replace(variant_normalized, '').strip()
                        if len(words_after) < 50:  # Máximo 50 caracteres después del título
                            
                            # Guardar sección anterior si existe
                            if current_section:
                                sections[current_section] = '\n'.join(current_content)
                                # print(f"✅ Guardada sección '{current_section}' con {len(current_content)} líneas")
                            
                            current_section = section
                            current_content = []
                            is_section = True
                            # print(f"✅ Sección detectada: '{line}' → {section}")
                            break
                
                if is_section:
                    break
        
        if not is_section:
            if current_section:
                # Procesar el contenido de la sección
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                    # Es un punto numerado
                    current_content.append(line)
                elif line.startswith(('- ', '• ', '* ')):
                    # Es un punto de lista
                    current_content.append(line)
                else:
                    # Es texto normal
                    if current_content and not current_content[-1].endswith('\n'):
                        current_content[-1] += ' ' + line
                    else:
                        current_content.append(line)
            else:
                # Si no hay sección actual, crear una sección GENERAL
                current_section = "GENERAL"
                current_content.append(line)
    
    # Guardar la última sección
    if current_section:
        sections[current_section] = '\n'.join(current_content)
        # print(f"✅ Guardada última sección '{current_section}' con {len(current_content)} líneas")
    
    # Si no se encontraron secciones, usar el texto completo como sección GENERAL
    if not sections:
        print("⚠️ No se encontraron secciones, usando texto completo como GENERAL")
        sections["GENERAL"] = text
    
    # print(f"✅ Secciones procesadas: {list(sections.keys())}")
    # for section_key, section_content in sections.items():
    #     print(f"   - '{section_key}': {len(section_content)} caracteres")
    
    # Procesar el contenido de cada sección para mejorar su presentación
    processed_sections = {}
    for section, content in sections.items():
        # Dividir en párrafos
        paragraphs = content.split('\n\n')
        processed_paragraphs = []
        
        for paragraph in paragraphs:
            # Si el párrafo es muy largo, dividirlo en oraciones
            if len(paragraph) > 200:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                processed_paragraphs.extend(sentences)
            else:
                processed_paragraphs.append(paragraph)
        
        # Unir los párrafos procesados
        processed_sections[section] = '\n\n'.join(processed_paragraphs)
    
    # Asegurarse de que el contenido no esté vacío
    if not any(content.strip() for content in processed_sections.values()):
        print("⚠️ Todas las secciones procesadas están vacías, usando texto original")
        processed_sections["GENERAL"] = text
    
    return processed_sections

def perform_analysis_module(ideas, context, additional_info, template=None):
    """
    Realiza el análisis de las ideas de manera optimizada, procesando cada punto por separado.
    """
    try:
        # Validar entrada
        if not ideas:
            print("Error: No hay ideas para analizar")
            return None, None, "Error: No hay ideas para analizar"
            
        # Validar y normalizar las ideas
        validated_ideas = []
        
        # Si es una cadena, intentar dividirla en ideas
        if isinstance(ideas, str):
            # Dividir por líneas y filtrar las vacías
            ideas_list = [line.strip() for line in ideas.split('\n') if line.strip()]
            for idea in ideas_list:
                if len(idea) > 10:  # Solo ideas con contenido significativo
                    validated_ideas.append({
                        'idea': idea,
                        'analysis': [],
                        'original_order': len(validated_ideas),
                        'title': idea.split('\n')[0].strip() if '\n' in idea else idea.strip()  # Guardar el título original
                    })
        # Si es una lista, procesar cada elemento
        elif isinstance(ideas, list):
            for idea in ideas:
                if isinstance(idea, str) and len(idea.strip()) > 10:
                    validated_ideas.append({
                        'idea': idea.strip(),
                        'analysis': [],
                        'original_order': len(validated_ideas),
                        'title': idea.strip().split('\n')[0] if '\n' in idea.strip() else idea.strip()  # Guardar el título original
                    })
                elif isinstance(idea, dict) and 'idea' in idea and len(str(idea['idea']).strip()) > 10:
                    idea_text = str(idea['idea']).strip()
                    validated_ideas.append({
                        'idea': idea_text,
                        'analysis': idea.get('analysis', []),
                        'original_order': idea.get('original_order', len(validated_ideas)),
                        'title': idea_text.split('\n')[0] if '\n' in idea_text else idea_text  # Guardar el título original
                    })
        
        if not validated_ideas:
            print("Error: No hay ideas válidas para analizar")
            return None, None, "Error: No hay ideas válidas para analizar"
        
        print(f"✅ Verificación completa: {len(validated_ideas)} ideas únicas confirmadas")
        
        # Ordenar por orden original
        validated_ideas.sort(key=lambda x: x['original_order'])
        
        # Extraer puntos de análisis del template
        analysis_points = []
        if template:
            # Extraer puntos numerados del template
            points = re.findall(r'\d+\.\s*(.*?)(?=\n\d+\.|\Z)', template, re.DOTALL)
            analysis_points = [point.strip() for point in points if point.strip()]
        
        if not analysis_points:
            analysis_points = [
                "Viabilidad Técnica",
                "Potencial de Mercado",
                "Ventaja Competitiva",
                "Riesgos y Desafíos",
                "Recomendaciones"
            ]
        
        # Procesar todas las ideas juntas para cada punto de análisis
        for point in analysis_points:
            print(f"\nAnalizando {point} para {len(validated_ideas)} ideas...")
            
            # Crear el prompt para el análisis del punto actual
            prompt = f"""
            Analiza el siguiente punto para cada una de las ideas proporcionadas:
            
            Punto: {point}
            
            Ideas a analizar:
            {chr(10).join(f"{j+1}. {idea['idea']}" for j, idea in enumerate(validated_ideas))}
            
            Para cada idea, proporciona un análisis profesional y estructurado del punto {point}.
            El análisis debe:
            1. Ser conciso y específico
            2. Incluir datos cuantificables cuando sea posible
            3. Seguir un formato profesional de consultoría
            4. Evitar lenguaje informal o coloquial
            5. Incluir conclusiones claras y recomendaciones cuando sea apropiado
            
            Formato de respuesta:
            Para cada idea, proporciona el análisis en el siguiente formato:
            [Número de idea]. [Título del punto]:
            [Análisis profesional y estructurado]
            """
            
            try:
                # Obtener el análisis para todas las ideas de una vez
                response = client.chat.completions.create(
                    model=DEPLOYMENT_NAME,
                    messages=[
                        {"role": "system", "content": "Eres un consultor experto en análisis de innovación y desarrollo de ideas."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000  # Aumentar tokens para manejar más ideas
                )
                
                # Procesar la respuesta y asignar el análisis a cada idea
                analysis_text = response.choices[0].message.content
                analyses = re.split(r'\d+\.\s*', analysis_text)[1:]  # Dividir por números
                
                for j, analysis in enumerate(analyses):
                    if j < len(validated_ideas):
                        # Limpiar y formatear el análisis
                        clean_analysis = analysis.strip()
                        clean_analysis = re.sub(r'\n+', '\n', clean_analysis)  # Eliminar líneas vacías extra
                        validated_ideas[j]['analysis'].append(f"{len(validated_ideas[j]['analysis']) + 1}. {point}:\n{clean_analysis}")
                
            except Exception as e:
                print(f"Error al analizar {point}: {str(e)}")
                continue
        
        # Guardar las ideas analizadas globalmente
        try:
            global_save_analyzed_ideas(validated_ideas)
            print(f"✅ Ideas analizadas guardadas globalmente: {len(validated_ideas)} ideas")
        except Exception as e:
            print(f"Advertencia: Error al guardar ideas globalmente: {str(e)}")
        
        # Generar el PDF
        try:
            pdf_path = generate_improved_pdf(validated_ideas)
            if pdf_path:
                print(f"✅ PDF generado correctamente: {pdf_path}")
                return validated_ideas, pdf_path, f"Análisis completado: {len(validated_ideas)} ideas analizadas"
            else:
                print("Error al generar el PDF")
                return validated_ideas, None, f"Análisis completado pero error al generar PDF: {len(validated_ideas)} ideas analizadas"
        except Exception as e:
            print(f"Error al generar el PDF: {str(e)}")
            return validated_ideas, None, f"Análisis completado pero error al generar PDF: {str(e)}"
            
    except Exception as e:
        print(f"Error general en el análisis: {str(e)}")
        return None, None, f"Error en el análisis: {str(e)}"

def global_save_analyzed_ideas(ideas_to_save):
    """
    🔧 MEJORADO: Guarda las ideas analizadas con validación y limpieza de memoria.
    """
    global analyzed_ideas_global, _last_analyzed_ideas
    
    # Validar entrada
    if not ideas_to_save:
        analyzed_ideas_global = []
        _last_analyzed_ideas = []
        print("✅ Variables globales limpiadas (lista vacía)")
        return True
    
    # Validar estructura y limpiar ideas malformadas
    validated_ideas = []
    for i, idea in enumerate(ideas_to_save):
        if isinstance(idea, dict) and 'idea' in idea:
            # Asegurar estructura mínima requerida
            validated_idea = {
                'idea': str(idea['idea']),
                'analysis': str(idea.get('analysis', '')),
                'metrics': idea.get('metrics', {}),
                'title': idea.get('title', f'Idea {i+1}')
            }
            validated_ideas.append(validated_idea)
        else:
            print(f"⚠️ Idea {i+1} no válida, omitiendo...")
    
    # Limpiar memoria anterior y guardar nuevas ideas
    analyzed_ideas_global = validated_ideas
    _last_analyzed_ideas = validated_ideas
    
    print(f"✅ Ideas analizadas guardadas: {len(validated_ideas)} ideas válidas")
    return True

def get_global_analyzed_ideas():
    """
    Devuelve la lista más robusta posible de ideas analizadas, comprobando todas las variables globales y el archivo temporal.
    """
    global analyzed_ideas_global
    try:
        # 1. Si la variable global principal está bien, úsala
        if isinstance(analyzed_ideas_global, list) and analyzed_ideas_global and all(isinstance(idea, dict) and 'analysis' in idea and idea['analysis'] for idea in analyzed_ideas_global):
            return analyzed_ideas_global
        # 2. Probar variables alternativas
        global _analyzed_ideas_global
        if '_analyzed_ideas_global' in globals() and isinstance(_analyzed_ideas_global, list) and _analyzed_ideas_global and all(isinstance(idea, dict) and 'analysis' in idea and idea['analysis'] for idea in _analyzed_ideas_global):
            return _analyzed_ideas_global
        global _last_analyzed_ideas
        if '_last_analyzed_ideas' in globals() and isinstance(_last_analyzed_ideas, list) and _last_analyzed_ideas and all(isinstance(idea, dict) and 'analysis' in idea and idea['analysis'] for idea in _last_analyzed_ideas):
            return _last_analyzed_ideas
        # 3. Intentar cargar desde archivo temporal
        import tempfile, os, json
        temp_dir = tempfile.gettempdir()
        results_path = os.path.join(temp_dir, "last_analysis_results.json")
        if os.path.exists(results_path):
            with open(results_path, 'r', encoding='utf-8') as f:
                ideas_data = json.load(f)
            if ideas_data and all(isinstance(idea, dict) and 'analysis' in idea and idea['analysis'] for idea in ideas_data):
                return ideas_data
        # 4. Si no hay nada válido, devolver lista vacía
        print("⚠️ No se encontraron ideas analizadas completas en memoria global ni en disco.")
        return []
    except Exception as e:
        print(f"❌ Error en get_global_analyzed_ideas: {str(e)}")
        return []

# Variable global para almacenar el último conjunto de ideas analizadas
_last_analyzed_ideas = []

def clear_all_global_memory():
    """
    🔧 NUEVA: Limpia completamente toda la memoria global del módulo.
    """
    global analyzed_ideas_global, _last_analyzed_ideas
    
    # Limpiar todas las variables globales
    analyzed_ideas_global = []
    _last_analyzed_ideas = []
    
    # Limpiar archivo temporal si existe
    try:
        import tempfile, os
        temp_dir = tempfile.gettempdir()
        results_path = os.path.join(temp_dir, "last_analysis_results.json")
        if os.path.exists(results_path):
            os.remove(results_path)
            print("🗑️ Archivo temporal de resultados eliminado")
    except Exception as e:
        print(f"⚠️ Error limpiando archivo temporal: {str(e)}")
    
    print("🧹 Memoria global completamente limpiada")
    return True

# 🔧 ALIAS PARA COMPATIBILIDAD: Las funciones antiguas ahora usan la función unificada
def generate_basic_pdf(results, output_dir="output"):
    """DEPRECIADO: Usa generate_unified_pdf en su lugar"""
    print("⚠️ generate_basic_pdf está depreciado, usando generate_unified_pdf")
    return generate_unified_pdf(results, output_dir, pdf_type="basic")

def generate_improved_pdf(analyses, output_dir="output"):
    """DEPRECIADO: Usa generate_unified_pdf en su lugar"""
    print("⚠️ generate_improved_pdf está depreciado, usando generate_unified_pdf")
    return generate_unified_pdf(analyses, output_dir, pdf_type="improved")

def get_analyzed_ideas():
    """
    Obtiene las ideas analizadas más recientemente
    """
    global _last_analyzed_ideas
    
    # Si hay ideas en memoria, devolverlas
    if _last_analyzed_ideas and len(_last_analyzed_ideas) > 0:
        return _last_analyzed_ideas
    
    # Si no hay en memoria, intentar cargar desde archivo
    try:
        temp_dir = tempfile.gettempdir()
        results_path = os.path.join(temp_dir, "last_analysis_results.json")
        
        if os.path.exists(results_path):
            with open(results_path, 'r', encoding='utf-8') as f:
                ideas_data = json.load(f)
            
            if ideas_data and len(ideas_data) > 0:
                print(f"✅ Se cargaron {len(ideas_data)} ideas analizadas del archivo")
                _last_analyzed_ideas = ideas_data
                return ideas_data
    except Exception as e:
        print(f"❌ Error cargando resultados: {str(e)}")
    
    # Si no se pudieron cargar ideas, devolver lista vacía
    return []

def analyze_idea_exhaustive(idea_text):
    """
    Realiza un análisis exhaustivo de una idea innovadora para el departamento de innovación de Sener.
    """
    try:
        # Validar entrada
        if not idea_text or not isinstance(idea_text, str):
            print("❌ Error: La idea debe ser un texto no vacío")
            return None
            
        # Limpiar y normalizar el texto
        idea_text = idea_text.strip()
        if len(idea_text) < 10:
            print("❌ Error: La idea es demasiado corta")
            return None
            
        # Contexto optimizado de Sener
        sener_context = """
        Sener: Ingeniería, tecnología e innovación con visión global

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
        
        """
        
        # Crear un prompt único que analice todos los aspectos a la vez
        prompt = f"""
        Contexto de Sener:
        {sener_context}

        Idea a analizar:
        {idea_text}

        Realiza un análisis exhaustivo de la idea considerando los siguientes aspectos:

        1. Resumen Ejecutivo:
        - Valor para Sener
        - Impacto potencial
        - Oportunidad de mercado

        2. Análisis Técnico:
        - Viabilidad técnica
        - Recursos necesarios
        - Nivel de madurez tecnológica

        3. Potencial de Innovación:
        - Grado de novedad
        - Carácter disruptivo
        - Ventajas competitivas

        4. Alineación Estratégica:
        - Conexión con áreas estratégicas
        - Objetivos corporativos
        - Sinergias potenciales

        5. Viabilidad Comercial:
        - Potencial comercial
        - Modelo de negocio
        - Retorno de inversión

        IMPORTANTE:
        - Proporciona un análisis profesional y detallado
        - Usa lenguaje técnico específico
        - Incluye ejemplos y justificaciones
        - Mantén un enfoque práctico y orientado a la acción
        - Evita caracteres especiales que puedan causar problemas
        """
        
        # 🔧 AÑADIR TIMEOUT: Realizar llamada a la API con timeout de 60 segundos
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("La llamada a OpenAI excedió el tiempo límite de 60 segundos")
        
        try:
            # Configurar timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(60)  # 60 segundos de timeout
            
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Eres un experto en análisis de innovación para Sener. Usa solo caracteres ASCII básicos en tus respuestas."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.7
            )
            
            # Desactivar timeout
            signal.alarm(0)
            
        except TimeoutError as e:
            print(f"❌ Timeout en análisis: {str(e)}")
            return None
        except Exception as e:
            signal.alarm(0)  # Asegurar que se desactiva el timeout
            print(f"❌ Error en llamada OpenAI: {str(e)}")
            return None
        
        if response and response.choices and response.choices[0].message:
            analysis_text = response.choices[0].message.content.strip()
            
            # Eliminar duplicaciones de títulos
            standard_sections = ["RESUMEN EJECUTIVO", "ANÁLISIS TÉCNICO", "POTENCIAL DE INNOVACIÓN", 
                                "ALINEACIÓN ESTRATÉGICA", "VIABILIDAD COMERCIAL", "VALORACIÓN GLOBAL"]
            
            for section in standard_sections:
                # Eliminar duplicación de títulos
                pattern = f"({section})[\\s\\n]*({section})"
                analysis_text = re.sub(pattern, r"\1", analysis_text, flags=re.IGNORECASE)
            
            # Normalizar el texto del análisis para evitar caracteres problemáticos
            normalized_analysis = normalize_text_for_pdf(analysis_text)
            
            # Generar PDF usando solo fuentes estándar
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            
            # Portada
            pdf.add_page()
            
            # Cargar logo usando función unificada
            load_logo_unified(pdf, y=40, logo_type="standard")
            
            pdf.set_font('Arial', 'B', 24)
            pdf.ln(80)  # Espacio para dejar sitio al logo
            pdf.cell(0, 40, "Informe de Analisis de Innovacion", ln=True, align='C')
            pdf.ln(20)
            
            pdf.set_font('Arial', '', 16)
            pdf.cell(0, 10, "Generado por: AI Agent Innovacion Sener", ln=True, align='C')
            pdf.cell(0, 10, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='C')
            
            # Índice
            index_page = pdf.page_no()
            pdf.add_page()
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 20, "Indice", ln=True)
            pdf.ln(10)
            
            # Preparar el texto para el índice y almacenar posiciones
            toc_entries = []
            pdf.set_font('Arial', '', 12)
            
            # Dividir el análisis en secciones para el índice
            sections = normalized_analysis.split('\n\n')
            section_pages = {}
            
            for i, section in enumerate(sections, 1):
                if section.strip():
                    title = section.split('\n')[0].strip()
                    if len(title) > 50:
                        title = title[:47] + "..."
                    y_pos = pdf.get_y()
                    pdf.cell(0, 10, f"{i}. {title}", ln=True)
                    toc_entries.append({'num': i, 'title': title, 'y_pos': y_pos})
            
            # Guardar la página final del índice
            last_index_page = pdf.page_no()
            
            # Contenido - con registro de páginas
            for i, section in enumerate(sections, 1):
                if section.strip():
                    # Registrar la página de esta sección
                    section_pages[i] = pdf.page_no() + 1  # +1 porque vamos a añadir página
                    
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 16)
                    title = section.split('\n')[0].strip()
                    pdf.cell(0, 20, title, ln=True)
                    pdf.ln(10)
                    
                    pdf.set_font('Arial', '', 12)
                    content = '\n'.join(section.split('\n')[1:]).strip()
                    try:
                        # Si es un título de sección principal, aplicar formato especial pero SIN duplicar
                        if title.upper() in ["RESUMEN EJECUTIVO", "ANÁLISIS TÉCNICO", "ANALISIS TECNICO", 
                                              "POTENCIAL DE INNOVACIÓN", "ALINEACIÓN ESTRATÉGICA", 
                                              "VIABILIDAD COMERCIAL", "VALORACIÓN GLOBAL"]:
                            # Evitar duplicar el título - solo usar formato normal
                            pdf.set_font('Arial', '', 12)  # Normal, sin negrita
                        
                        # Dividir en párrafos para mejor presentación
                        paragraphs = section.split('\n\n')
                        for paragraph in paragraphs:
                            if paragraph.strip():
                                pdf.multi_cell(0, 6, normalize_text_for_pdf(paragraph.strip()))
                                pdf.ln(4)
                    except Exception as e:
                        print(f"⚠️ Error al procesar contenido: {str(e)}")
                        # Intento de recuperación con limpieza adicional
                        pdf.multi_cell(0, 6, emergency_clean_text(content))
            
            # Pie de página
            pdf.set_y(-15)
            pdf.set_font('Arial', 'I', 8)
            pdf.set_text_color(150, 150, 150)  # Gris claro
            pdf.cell(0, 10, f"Página {pdf.page_no()}", align='R')
        
        # Volver al índice para completar números de página
        current_page = pdf.page_no()
        
        # Recorrer las páginas del índice
        for page in range(index_page, last_index_page + 1):
            # Cambiar a la página del índice
            pdf.page = page
            
            # Para cada entrada del índice en esta página
            for entry in toc_entries:
                # Asegurarnos de que la entrada sea válida y tenga un número en idea_pages
                if isinstance(entry, dict) and 'num' in entry and 'y_pos' in entry and entry['num'] in section_pages:
                    # Colocar el cursor en la posición Y de la entrada
                    pdf.set_y(entry['y_pos'])
                    
                    # Colocar el cursor en la posición X para el número de página (alineado a la derecha)
                    pdf.set_x(180)
                    
                    # Añadir el número de página con formato
                    pdf.cell(15, 10, str(section_pages[entry['num']]), align='R')
        
        # Guardar PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"analisis_detallado_{timestamp}.pdf")
        
        try:
            pdf.output(pdf_path)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF generado correctamente: {pdf_path}")
                return normalized_analysis, pdf_path
            else:
                print("❌ Error: El archivo PDF no se generó correctamente")
                return normalized_analysis, None
        except Exception as e:
            print(f"❌ Error guardando PDF: {str(e)}")
            return normalized_analysis, None
                
    except Exception as e:
        print(f"❌ Error en análisis exhaustivo: {str(e)}")
        traceback.print_exc()
        return None, None

def process_text_response(text):
    """
    Procesa una respuesta de texto en un formato estructurado.
    """
    sections = {
        "Resumen Ejecutivo": {"Puntuación": 0, "Justificación": ""},
        "Análisis Técnico": {"Puntuación": 0, "Justificación": ""},
        "Potencial de Innovación": {"Puntuación": 0, "Justificación": ""},
        "Alineación Estratégica": {"Puntuación": 0, "Justificación": ""},
        "Próximos Pasos": {"Puntuación": 0, "Justificación": ""},
        "Indicadores Inferidos": {
            "Riesgo Técnico": {"Puntuación": 0, "Justificación": ""},
            "Tiempo de Desarrollo": {"Puntuación": 0, "Justificación": ""},
            "% Costes sobre Ingresos": {"Puntuación": 0, "Justificación": ""},
            "Ingresos Previstos": {"Puntuación": 0, "Justificación": ""},
            "Riesgo de Mercado": {"Puntuación": 0, "Justificación": ""}
        },
        "Evaluación Global Cualitativa (S)": {"Puntuación": 0, "Justificación": ""},
        "Resumen del Análisis": ""
    }
    
    # Procesar el texto para extraer información
    lines = text.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Buscar secciones principales
        for section in sections:
            if section in line:
                current_section = section
                break
                
        if current_section:
            if "Puntuación" in line:
                try:
                    score = int(line.split(':')[1].strip())
                    sections[current_section]["Puntuación"] = score
                except:
                    pass
            elif "Justificación" in line:
                sections[current_section]["Justificación"] = line.split(':')[1].strip()
            else:
                sections[current_section]["Justificación"] += " " + line
    
    return sections

def create_text_logo(pdf, text="SENER", x=None, y=40, width=80, height=30):
    """
    Crea un logo de texto personalizado cuando no se puede cargar la imagen.
    
    Args:
        pdf: Objeto FPDF
        text: Texto a mostrar como logo
        x, y: Posición
        width, height: Dimensiones
    """
    # Calcular posición centrada si no se proporciona
    if x is None:
        x = (210 - width) / 2  # Centrado horizontalmente (A4 = 210mm ancho)
    
    # Guardar estados actuales de la fuente
    font_family = pdf.font_family
    font_style = pdf.font_style
    font_size = pdf.font_size_pt
    
    # Crear un rectángulo de fondo azul
    pdf.set_fill_color(0, 51, 153)  # Azul corporativo
    pdf.rect(x, y, width, height, style='F')
    
    # Agregar el texto en el centro del rectángulo
    pdf.set_font('Arial', 'B', 24)
    pdf.set_text_color(255, 255, 255)  # Texto blanco
    
    # Calcular posición y para centrar el texto verticalmente
    text_y = y + (height / 2) - 5
    
    # Dibujar el texto centrado
    pdf.set_xy(x, text_y)
    pdf.cell(width, 10, text, align='C')
    
    # Restaurar estados de la fuente
    pdf.set_font(font_family, font_style, font_size)
    pdf.set_text_color(0, 0, 0)  # Volver a texto negro
    
    print("✅ Logo de texto creado como alternativa")
    return True

def load_image_to_pdf(pdf, image_path, x, y, w, h):
    """
    Función alternativa para cargar una imagen en el PDF usando múltiples métodos
    para mayor compatibilidad.
    
    Args:
        pdf: Objeto FPDF
        image_path: Ruta al archivo de imagen
        x, y: Posición
        w, h: Ancho y alto
    
    Returns:
        bool: True si la carga fue exitosa, False si falló
    """
    try:
        # Método 1: Carga estándar
        pdf.image(image_path, x=x, y=y, w=w, h=h)
        return True
    except Exception as e:
        print(f"Método 1 falló: {str(e)}")
        
        try:
            # Método 2: Cargar usando pillow si está disponible
            try:
                from PIL import Image
                img = Image.open(image_path)
                
                # Crear un archivo temporal para una versión convertida
                temp_path = os.path.join(tempfile.gettempdir(), "temp_logo.png")
                img.save(temp_path)
                
                # Intentar cargar desde el archivo temporal
                pdf.image(temp_path, x=x, y=y, w=w, h=h)
                
                print(f"✅ Imagen cargada usando método alternativo 2 (PIL)")
                return True
            except ImportError:
                print("PIL no está disponible para método 2")
        except Exception as e2:
            print(f"Método 2 falló: {str(e2)}")
            
            try:
                # Método 3: Usar un método más básico si está disponible
                if hasattr(pdf, 'add_image'):
                    pdf.add_image(image_path, x=x, y=y, w=w, h=h)
                    print(f"✅ Imagen cargada usando método alternativo 3 (add_image)")
                    return True
            except Exception as e3:
                print(f"Método 3 falló: {str(e3)}")
                
                # Método 4: Crear un logo de texto como último recurso
                try:
                    return create_text_logo(pdf, "SENER", x, y, w, h)
                except Exception as e4:
                    print(f"Método 4 falló: {str(e4)}")
        
        return False

def clean_text_for_pdf(text):
    """
    Limpia el texto para PDF: convierte caracteres Unicode problemáticos a ASCII seguro.
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Mapa de caracteres Unicode problemáticos → ASCII seguro
    unicode_replacements = {
        # Comillas tipográficas
        '"': '"',    # Comilla izquierda
        '"': '"',    # Comilla derecha  
        "'": "'",    # Comilla simple izquierda
        "'": "'",    # Comilla simple derecha
        # Guiones
        '–': '-',    # En dash
        '—': '-',    # Em dash
        '−': '-',    # Minus sign
        # Espacios especiales
        ' ': ' ',    # Non-breaking space
        ' ': ' ',    # Thin space
        ' ': ' ',    # Figure space
        # Puntos suspensivos
        '…': '...',  # Ellipsis
        # Otros caracteres especiales
        '«': '"',    # Left guillemet
        '»': '"',    # Right guillemet
        '‚': ',',    # Single low-9 quotation mark
        '„': '"',    # Double low-9 quotation mark
        '‹': '<',    # Single left-pointing angle quotation mark
        '›': '>',    # Single right-pointing angle quotation mark
        '°': 'o',    # Degree symbol
        '™': '(TM)', # Trademark
        '®': '(R)',  # Registered trademark
        '©': '(C)',  # Copyright
        '€': 'EUR',  # Euro symbol
        '£': 'GBP',  # Pound symbol
        '¥': 'JPY',  # Yen symbol
        # Acentos y diacríticos (mantener legibilidad)
        'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a', 'ã': 'a', 'å': 'a',
        'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e',
        'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i',
        'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u',
        'ñ': 'n', 'ç': 'c',
        'Á': 'A', 'À': 'A', 'Ä': 'A', 'Â': 'A', 'Ã': 'A', 'Å': 'A',
        'É': 'E', 'È': 'E', 'Ë': 'E', 'Ê': 'E',
        'Í': 'I', 'Ì': 'I', 'Ï': 'I', 'Î': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ö': 'O', 'Ô': 'O', 'Õ': 'O',
        'Ú': 'U', 'Ù': 'U', 'Ü': 'U', 'Û': 'U',
        'Ñ': 'N', 'Ç': 'C'
    }
    
    # Aplicar reemplazos
    for unicode_char, ascii_replacement in unicode_replacements.items():
        text = text.replace(unicode_char, ascii_replacement)
    
    # Eliminar caracteres Unicode invisibles
    text = re.sub(r'[\u200b\u200c\u200d\u2028\u2029]', '', text)
    
    # Normalizar espacios y saltos de línea
    text = text.replace('\t', ' ')
    text = re.sub(r' +', ' ', text)
    
    # Como último recurso, filtrar cualquier caracter no-ASCII restante
    clean_text = ""
    for char in text:
        if ord(char) < 128:  # Solo caracteres ASCII
            clean_text += char
        else:
            # Si aún hay caracteres problemáticos, reemplazar por ?
            clean_text += '?'
    
    return clean_text.strip()

def safe_multicell(pdf: FPDF, txt: str, w=0, h=5, align="L"):
    """
    Imprime texto en el PDF de forma robusta, limpiando caracteres Unicode y evitando errores.
    """
    # Aplicar limpieza robusta SIEMPRE
    txt = clean_text_for_pdf(txt)
    
    # Trocea palabras largas (sin espacios) de más de 20 caracteres
    txt = re.sub(r'([^\s]{20})', r'\1 ', txt)
    try:
        pdf.multi_cell(w, h, txt, align=align)
    except Exception as e:
        print(f"⚠️ safe_multicell: Error '{e}' con texto: {txt[:100]}...")
        # Trocea la línea en fragmentos de 20 caracteres
        for chunk in textwrap.wrap(txt, 20, break_long_words=True, break_on_hyphens=True):
            try:
                # Aplicar limpieza adicional al chunk
                clean_chunk = clean_text_for_pdf(chunk)
                pdf.multi_cell(w, h, clean_chunk, align=align)
            except Exception as e2:
                print(f"❌ safe_multicell: Chunk imposible: {chunk[:20]}... Error: {e2}")
                # Como último recurso, usar emergency_clean_text
                emergency_chunk = emergency_clean_text(chunk)
                try:
                    pdf.multi_cell(w, h, emergency_chunk, align=align)
                except:
                    # Si aún falla, skipear este chunk
                    print(f"❌ Chunk completamente ignorado: {chunk[:10]}...")

def emergency_clean_text(text):
    """
    Función de limpieza de emergencia que garantiza que el texto solo contiene caracteres ASCII.
    Se usa como último recurso cuando clean_text_for_pdf falla.
    """
    if not text:
        return ""
    
    # Asegurar que solo caracteres ASCII básicos estén presentes
    result = ""
    for char in text:
        if ord(char) < 128:  # Solo caracteres ASCII estándar
            result += char
        else:
            # Reemplazar cualquier otro caracter con espacio
            result += ' '
    
    # Normalizar espacios múltiples
    result = re.sub(r' +', ' ', result)
    return result.strip()

# Agregar esta definición de clase antes de la función generate_professional_pdf
class CustomPDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.skip_header_footer = True  # Para portada e índice
        self.current_idea_title = ""  # Para headers contextuales
    
    def header(self):
        # No mostrar cabecera en portada ni índice
        if self.skip_header_footer or self.page_no() <= 2:
            return
        
        try:
            # Solo añadir header si estamos en el inicio de una página
            if self.get_y() > 30:
                return
                
            # Verificar que estamos en posición correcta
            if self.get_y() < 25:
                # Ir al inicio de la página
                self.set_y(10)
                
                # Título en header SIN contexto específico
                header_title = "Análisis de Ideas de Innovación"
                
                self.set_font('Arial', 'B', 10)
                self.set_text_color(0, 51, 102)  # Azul corporativo
                self.set_y(17)
                self.cell(0, 6, header_title, ln=True, align='C')
                
                # Establecer posición inicial correcta para contenido
                self.set_y(30)
                self.set_text_color(0, 0, 0)
                self.set_font('Arial', '', 11)
            
        except Exception as e:
            print(f"⚠️ Error añadiendo header: {e}")
            # Asegurar posición mínima
            if self.get_y() < 25:
                self.set_y(25)

    def footer(self):
        # No mostrar pie en portada ni índice
        if self.skip_header_footer or self.page_no() <= 2:
            return
        
        try:
            # Posicionar en el pie de página (más limpio y simple)
            self.set_y(self.h - 15)
            
            # Solo número de página, centrado y discreto
            self.set_font('Arial', '', 9)
            self.set_text_color(120, 120, 120)  # Gris más discreto
            page_text = f"Página {self.page_no()}"
            self.cell(0, 6, page_text, ln=True, align='C')
            
            # Restaurar configuración
            self.set_text_color(0, 0, 0)
            self.set_font('Arial', '', 11)
            
        except Exception as e:
            print(f"⚠️ Error añadiendo footer: {e}")
    
    def set_idea_context(self, idea_title):
        """Establecer el título de la idea actual para headers contextuales"""
        self.current_idea_title = idea_title

def generate_professional_pdf(results, output_dir="output"):
    """
    Genera un PDF profesional con formato visual de alta calidad, similar al de ranking.
    Incluye portada, índice y contenido bien estructurado con secciones claramente identificadas.
    """
    try:
        if not results or not isinstance(results, list):
            print("❌ Error: No hay resultados para mostrar en el PDF")
            return None
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"analisis_ideas_{timestamp}.pdf")
        pdf = CustomPDF(orientation='P', unit='mm', format='A4')
        pdf.set_margins(left=15, top=15, right=15)
        pdf.set_auto_page_break(auto=True, margin=15)
        # PORTADA
        pdf.skip_header_footer = True
        pdf.add_page()
        try:
            if os.path.exists("logo.png"):
                pdf.image("logo.png", x=(210-60)/2, y=40, w=60)
            elif os.path.exists("logo1.png"):
                pdf.image("logo1.png", x=(210-60)/2, y=40, w=60)
        except Exception as e:
            print(f"⚠️ Error al cargar el logo: {str(e)}")
        pdf.set_font('Arial', 'B', 20)
        pdf.ln(100)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 12, "ANÁLISIS DE IDEAS", align='C', ln=True)
        pdf.ln(10)
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 8, "INFORME DE INNOVACIÓN", align='C', ln=True)
        pdf.ln(15)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', '', 11)
        pdf.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", align='C', ln=True)
        pdf.cell(0, 8, f"Total ideas analizadas: {len(results)}", align='C', ln=True)
        # ÍNDICE EN PÁGINA SEPARADA CON NÚMEROS DE PÁGINA CORRECTOS
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, "Índice de Ideas", ln=True)
        pdf.ln(5)

        # Primero, calcular los números de página simulando la escritura del contenido
        temp_page_numbers = {}
        seen_titles_temp = set()
        current_page_sim = 3  # Página 1: portada, Página 2: índice, Página 3: primera idea
        
        for idx, result in enumerate(results):
            idea_title = result.get('idea_title', 'Idea').strip()
            norm_title = idea_title.lower()
            
            # Saltar duplicados
            if norm_title in seen_titles_temp:
                continue
            seen_titles_temp.add(norm_title)
            
            # Asignar número de página
            temp_page_numbers[norm_title] = current_page_sim
            
            # Simular espacio requerido para la idea (estimación conservadora)
            # Asumimos que cada idea requiere al menos 1 página nueva
            if idx > 0:  # A partir de la segunda idea
                current_page_sim += 1  # Nueva página por idea
        
        # Ahora crear el índice con los números de página calculados
        seen_titles = set()
        display_num = 0
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(0, 0, 0)
        
        for result in results:
            idea_title = result.get('idea_title', 'Idea').strip()
            norm_title = idea_title.lower()
            
            # Saltar duplicados
            if norm_title in seen_titles:
                print(f"⚠️  Duplicado omitido en índice: {idea_title}")
                continue
            seen_titles.add(norm_title)
            display_num += 1
            
            # Obtener número de página calculado
            page_num = temp_page_numbers.get(norm_title, display_num + 2)
            
            # Limpiar título para el índice
            clean_index_title = clean_text_for_pdf(idea_title)
            
            # Escribir entrada completa del índice
            pdf.cell(170, 7, f"{display_num}. {clean_index_title}", 0, 0, 'L')
            pdf.cell(0, 7, str(page_num), 0, 1, 'R')
            pdf.ln(2)
            
            print(f"📄 Índice creado: '{clean_index_title}' → página {page_num}")

        # --- GENERAR EL CONTENIDO DE LAS IDEAS ---
        pdf.skip_header_footer = False
        for idx, result in enumerate(results):
            idea_title = result.get('idea_title', 'Idea').strip()
            norm_title = idea_title.lower()
            
            # 🔧 SOLO AÑADIR PÁGINA SI ES LA PRIMERA IDEA O SI NO HAY ESPACIO SUFICIENTE
            if idx == 0:
                # Primera idea: siempre empezar en nueva página
                pdf.add_page()
            else:
                # Ideas siguientes: verificar si hay espacio suficiente (al menos 50mm)
                space_remaining = pdf.h - pdf.get_y() - pdf.b_margin
                if space_remaining < 50:  # Si queda menos de 50mm, nueva página
                    pdf.add_page()
                else:
                    # Si hay espacio, separar ideas con línea divisoria y espacio
                    pdf.ln(8)  # Espacio antes de la línea
                    pdf.set_draw_color(200, 200, 200)  # Color gris claro
                    pdf.line(15, pdf.get_y(), 195, pdf.get_y())  # Línea horizontal
                    pdf.ln(8)  # Espacio después de la línea
            
            # --- Escribir el contenido de la idea ---
            pdf.set_font('Arial', 'B', 14)
            pdf.set_text_color(0, 51, 102)
            # 🔧 LIMPIAR TÍTULO ANTES DE USARLO
            clean_title = clean_text_for_pdf(idea_title)
            pdf.cell(0, 10, f"IDEA: {clean_title}", ln=True)
            pdf.ln(5)
            analysis_text = result.get('analysis', '')
            if not analysis_text or not analysis_text.strip():
                pdf.set_font('Arial', 'I', 11)
                pdf.set_text_color(150, 0, 0)
                pdf.cell(0, 8, "[No hay análisis disponible]", ln=True)
                continue
                
            # 🔧 ORDEN FIJO Y CORRECTO DE SECCIONES
            section_titles = [
                "RESUMEN EJECUTIVO",
                "ANÁLISIS TÉCNICO", 
                "POTENCIAL DE INNOVACIÓN",
                "ALINEACIÓN ESTRATÉGICA CON SENER",
                "VIABILIDAD COMERCIAL",
                "VALORACIÓN GLOBAL"
            ]
            
            import re
            # 🔧 LIMPIAR ANALYSIS_TEXT ANTES DE PROCESARLO
            clean_text = clean_text_for_pdf(analysis_text)
            clean_text = clean_text.replace('**', '').replace('###', '').replace('__', '')
            
            # 🔧 EXTRAER CONTENIDO USANDO process_analysis_text_improved
            # que maneja correctamente los acentos y variaciones
            print(f"🔍 DEBUG: Enviando texto a process_analysis_text_improved")
            print(f"📝 Primeros 200 caracteres del texto limpio: '{clean_text[:200]}...'")
            
            sections_detected = process_analysis_text_improved(clean_text)
            
            print(f"🔍 DEBUG: Secciones detectadas por process_analysis_text_improved:")
            for section_key, section_content in sections_detected.items():
                print(f"   - '{section_key}': {len(section_content)} caracteres")
                if section_content:
                    print(f"     Primeros 100 caracteres: '{section_content[:100]}...'")
            
            blocks = []
            for section_title in section_titles:  # ← ORDEN FIJO
                # Buscar en las secciones detectadas por la función mejorada
                content_found = ""
                
                print(f"🔍 DEBUG: Buscando sección '{section_title}'...")
                
                # Buscar coincidencia exacta primero
                if section_title in sections_detected:
                    content_found = sections_detected[section_title]
                    print(f"   ✅ Encontrada por coincidencia exacta: {len(content_found)} caracteres")
                else:
                    # Buscar por clave normalizada (manejo de acentos)
                    section_normalized = normalize_text(section_title)
                    print(f"   🔍 Buscando por clave normalizada: '{section_normalized}'")
                    
                    for detected_section, detected_content in sections_detected.items():
                        detected_normalized = normalize_text(detected_section)
                        print(f"     Comparando con: '{detected_normalized}'")
                        
                        if detected_normalized == section_normalized:
                            content_found = detected_content
                            print(f"   ✅ Encontrada por normalización: {len(content_found)} caracteres")
                            break
                    
                    # Si aún no se encuentra, buscar parcialmente
                    if not content_found:
                        print(f"   🔍 Buscando por coincidencia parcial...")
                        for detected_section, detected_content in sections_detected.items():
                            detected_normalized = normalize_text(detected_section)
                            # Búsqueda flexible - contiene palabras clave
                            if (any(word in detected_normalized for word in section_normalized.split() if len(word) > 3) or
                                any(word in section_normalized for word in detected_normalized.split() if len(word) > 3)):
                                content_found = detected_content
                                print(f"   ✅ Encontrada por coincidencia parcial: '{detected_section}' → {section_title}: {len(content_found)} caracteres")
                                break
                
                # Si no se encuentra contenido, usar mensaje por defecto
                if not content_found or not content_found.strip():
                    content_found = f"[Sección {section_title} no encontrada en el análisis]"
                    print(f"   ❌ NO ENCONTRADA: usando mensaje por defecto")
                
                blocks.append((section_title, content_found))
            
            # 🔧 RENDERIZAR SECCIONES EN ORDEN FIJO CON FORMATO PROFESIONAL
            for title, content in blocks:
                # 🔧 FORMATO MEJORADO PARA SUBTÍTULOS
                pdf.set_font('Arial', 'B', 13)  # ← Aumentar tamaño de fuente
                pdf.set_text_color(0, 51, 102)  # ← Color azul corporativo
                
                # 🔧 LIMPIAR TÍTULO DE SECCIÓN
                clean_section_title = clean_text_for_pdf(title)
                
                # 🔧 AÑADIR ESPACIO ANTES DEL SUBTÍTULO
                pdf.ln(4)
                
                # 🔧 SUBTÍTULO CON MEJOR FORMATO
                pdf.cell(0, 10, clean_section_title, ln=True)
                
                # 🔧 ESPACIO DESPUÉS DEL SUBTÍTULO
                pdf.ln(3)
                
                # 🔧 CONTENIDO CON FORMATO MEJORADO
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(0, 0, 0)  # ← Negro para contenido
                
                # 🔧 PROCESAR PÁRRAFOS CON MEJOR ESPACIADO
                if content and content.strip():
                    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
                    for paragraph in paragraphs:
                        if paragraph:  # Solo párrafos no vacíos
                            # 🔧 USAR safe_multicell CON ALTURA AJUSTADA
                            safe_multicell(pdf, paragraph, w=0, h=6)
                            pdf.ln(2)  # ← Espacio entre párrafos
                else:
                    # Si no hay contenido, mostrar mensaje
                    pdf.set_font('Arial', 'I', 10)
                    pdf.set_text_color(150, 150, 150)
                    pdf.cell(0, 6, "[Contenido no disponible]", ln=True)
                    pdf.set_text_color(0, 0, 0)
                
                # 🔧 ESPACIO MAYOR ENTRE SECCIONES
                pdf.ln(5)
            
            # Pie de página
            pdf.set_y(-15)
            pdf.set_font('Arial', 'I', 8)
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 10, f"Página {pdf.page_no()}", align='R')
        
        # GUARDAR PDF
        try:
            pdf.output(pdf_path)
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF profesional generado correctamente: {pdf_path}")
                return pdf_path
            else:
                print("❌ Error: El archivo PDF no se generó correctamente")
                return None
        except Exception as e:
            print(f"❌ Error al guardar PDF: {str(e)}")
            return None
    except Exception as e:
        print(f"❌ Error general al generar PDF: {str(e)}")
        return None

# --- NUEVO BLOQUE: GENERACIÓN DE PDF DE SOLUCIÓN A RETOS ---
def generate_challenges_and_solutions_pdf(analyzed_ideas, context="", output_dir="output"):
    import os
    from datetime import datetime
    from fpdf import FPDF
    import re
    import concurrent.futures
    import time

    if not analyzed_ideas or not isinstance(analyzed_ideas, list):
        print("❌ No hay ideas analizadas para generar el PDF de retos y soluciones")
        return None

    os.makedirs(output_dir, exist_ok=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Cargar fuente DejaVu Unicode - solución robusta para Docker y desarrollo
    try:
        pdf = RetosPDF()
        font_family = 'DejaVu'
        
        # Determinar el directorio base de la aplicación
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        app_root = current_script_dir  # Por defecto, asumir que estamos en la raíz
        
        # Si estamos en un subdirectorio (como .gradio), subir al directorio padre
        if current_script_dir.endswith('.gradio') or current_script_dir.endswith('\\.gradio'):
            app_root = os.path.dirname(current_script_dir)
        
        # Lista de posibles ubicaciones (CORREGIDA: priorizar directorio de trabajo)
        working_dir = os.getcwd()  # Directorio desde donde se ejecuta la app
        
        font_paths = [
            # PRIORIDAD 1: Directorio de trabajo actual (donde está la app principal)
            os.path.join(working_dir, 'output'),
            working_dir,
            
            # PRIORIDAD 2: Rutas relativas al directorio de trabajo
            'output',
            './output',
            '.',
            
            # PRIORIDAD 3: Rutas relativas al script
            os.path.join(current_script_dir, 'output'),
            os.path.join(app_root, 'output'),
            current_script_dir,
            app_root,
            
            # PRIORIDAD 4: Rutas Docker estándar
            '/app/output',
            '/app/.gradio/output',
            '/app/data/output',
            '/app/',
            
            # PRIORIDAD 5: Fallbacks de desarrollo
            '../output',
            '../../output',
            '../',
            
            # ÚLTIMO RECURSO: Directorio temporal
            tempfile.gettempdir(),
        ]
        
        print(f"📁 Directorio del script: {current_script_dir}")
        print(f"📁 Directorio raíz detectado: {app_root}")
        print(f"📁 Directorio de trabajo actual: {os.getcwd()}")
        
        font_loaded = False
        for font_base_path in font_paths:
            try:
                font_regular = os.path.join(font_base_path, 'DejaVuSans.ttf')
                font_bold = os.path.join(font_base_path, 'DejaVuSans-Bold.ttf')
                font_italic = os.path.join(font_base_path, 'DejaVuSans-Oblique.ttf')
                
                # Verificar que los archivos existen
                if all(os.path.exists(f) for f in [font_regular, font_bold, font_italic]):
                    pdf.add_font('DejaVu', '', font_regular, uni=True)
                    pdf.add_font('DejaVu', 'B', font_bold, uni=True)
                    pdf.add_font('DejaVu', 'I', font_italic, uni=True)
                    print(f"✅ Fuentes DejaVu Unicode cargadas desde: {font_base_path}")
                    font_loaded = True
                    break
                else:
                    # Solo mostrar rutas que realmente existen para debugging
                    if os.path.exists(font_base_path):
                        existing_fonts = [f for f in [font_regular, font_bold, font_italic] if os.path.exists(f)]
                        if existing_fonts:
                            print(f"⚠️ Directorio {font_base_path} existe pero faltan fuentes: {len(existing_fonts)}/3 encontradas")
            except Exception as e:
                # Solo mostrar errores significativos, no de rutas que no existen
                if 'No such file or directory' not in str(e) and 'cannot find' not in str(e).lower():
                    print(f"⚠️ Error intentando cargar desde {font_base_path}: {e}")
                continue
        
        if not font_loaded:
            print("⚠️ No se encontraron fuentes DejaVu en ninguna ubicación")
            print("🔄 Intentando descargar fuentes automáticamente...")
            
            # Intentar descargar las fuentes si no existen
            font_download_success = download_fonts_if_needed(output_dir)
            if font_download_success:
                # Intentar cargar de nuevo desde output_dir
                try:
                    font_regular = os.path.join(output_dir, 'DejaVuSans.ttf')
                    font_bold = os.path.join(output_dir, 'DejaVuSans-Bold.ttf')
                    font_italic = os.path.join(output_dir, 'DejaVuSans-Oblique.ttf')
                    
                    if all(os.path.exists(f) for f in [font_regular, font_bold, font_italic]):
                        pdf.add_font('DejaVu', '', font_regular, uni=True)
                        pdf.add_font('DejaVu', 'B', font_bold, uni=True)
                        pdf.add_font('DejaVu', 'I', font_italic, uni=True)
                        print(f"✅ Fuentes DejaVu descargadas y cargadas desde: {output_dir}")
                        font_loaded = True
                except Exception as e:
                    print(f"❌ Error cargando fuentes descargadas: {e}")
            
            if not font_loaded:
                print("⚠️ Usando Arial como fuente de respaldo")
                font_family = 'Arial'
            
    except Exception as e:
        print(f"❌ Error general cargando fuentes: {e}")
        font_family = 'Arial'
        print("⚠️ Usando Arial como fuente de emergencia")

    # PORTADA
    pdf.skip_footer = True
    pdf.add_page()
    # Logo usando función unificada
    load_logo_unified(pdf, y=40, logo_type="compact")
    pdf.set_font(font_family, 'B', 20)
    pdf.ln(100)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, "SOLUCIÓN A RETOS", align='C', ln=True)
    pdf.ln(10)
    pdf.set_font(font_family, 'B', 14)
    pdf.cell(0, 8, "INFORME DE RETOS Y SOLUCIONES", align='C', ln=True)
    pdf.ln(15)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, '', 11)
    pdf.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", align='C', ln=True)
    pdf.cell(0, 8, f"Total ideas analizadas: {len(analyzed_ideas)}", align='C', ln=True)

    # ÍNDICE
    pdf.add_page()
    indice_page = pdf.page_no()
    pdf.set_font(font_family, 'B', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "Índice de Ideas", ln=True)
    pdf.ln(5)

    index_entries = []

    for i, idea in enumerate(analyzed_ideas, 1):
        idea_title = idea.get('idea_title', f"Idea {i}")
        entry_text = f"{i}. {idea_title}"

        y_start = pdf.get_y()
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(170, 7, entry_text)
        y_end = pdf.get_y()
        y_middle = (y_start + y_end) / 2

        index_entries.append({'num': i, 'title': idea_title, 'y_pos': y_middle, 'page': 0})

        pdf.ln(2)

    # --- PROCESAMIENTO EN PARALELO DE RETOS Y SOLUCIONES ---
    def retos_worker(idea, idx):
        analysis = idea.get('analysis', '')
        if not analysis:
            return "[No hay análisis disponible]"
        print(f"⏳ Extrayendo retos para idea {idx+1}...")
        t0 = time.time()
        try:
            retos = get_challenges_for_idea(analysis, context)
            print(f"✅ Retos extraídos para idea {idx+1} ({time.time()-t0:.1f}s)")
            return retos
        except Exception as e:
            print(f"❌ Error extrayendo retos para idea {idx+1}: {e}")
            return f"[Error extrayendo retos: {e}]"

    def soluciones_worker(retos_block, idx):
        if not retos_block or '[No hay análisis disponible]' in retos_block:
            return "[No hay retos extraídos]"
        print(f"⏳ Proponiendo soluciones para idea {idx+1}...")
        t0 = time.time()
        try:
            soluciones = get_solutions_for_challenges(retos_block, context)
            print(f"✅ Soluciones propuestas para idea {idx+1} ({time.time()-t0:.1f}s)")
            return soluciones
        except Exception as e:
            print(f"❌ Error proponiendo soluciones para idea {idx+1}: {e}")
            return f"[Error extrayendo soluciones: {e}]"

    # 1. Extraer retos en paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(analyzed_ideas))) as executor:
        retos_futures = [executor.submit(retos_worker, idea, idx) for idx, idea in enumerate(analyzed_ideas)]
        retos_blocks = [f.result() for f in concurrent.futures.as_completed(retos_futures)]
    retos_blocks_ordered = [None]*len(analyzed_ideas)
    for idx, f in enumerate(retos_futures):
        try:
            retos_blocks_ordered[idx] = f.result()
        except Exception as e:
            retos_blocks_ordered[idx] = f"[Error extrayendo retos: {e}]"

    # 2. Extraer soluciones en paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(analyzed_ideas))) as executor:
        soluciones_futures = [executor.submit(soluciones_worker, retos_blocks_ordered[idx], idx) for idx in range(len(analyzed_ideas))]
        soluciones_blocks = [f.result() for f in concurrent.futures.as_completed(soluciones_futures)]
    soluciones_blocks_ordered = [None]*len(analyzed_ideas)
    for idx, f in enumerate(soluciones_futures):
        try:
            soluciones_blocks_ordered[idx] = f.result()
        except Exception as e:
            soluciones_blocks_ordered[idx] = f"[Error extrayendo soluciones: {e}]"

    # --- Emparejar retos y soluciones por orden ---
    def parse_retros(text):
        retos = []
        if not text or '[No hay análisis disponible]' in text:
            return retos
        text = re.sub(r'#.*', '', text)
        text = re.sub(r'RETOS TÉCNICOS.*?\n', '', text, flags=re.IGNORECASE|re.DOTALL)
        text = re.sub(r'RETOS DE MERCADO.*?\n', '', text, flags=re.IGNORECASE|re.DOTALL)
        # Eliminar bloques de NOTA FINAL, CONCLUSIÓN, etc.
        text = re.sub(r'(NOTA FINAL|CONCLUSI[ÓO]N( REFORZADA)?)(.*?)(Página|$)', '', text, flags=re.IGNORECASE|re.DOTALL)
        patron = r'(\d+)\.\s*([^\n]+?)(?:\s+Severidad:\s*(\d))?\s*\n\s*([^\n]+)'
        for m in re.finditer(patron, text):
            num, nombre, severidad, justif = m.groups()
            # Filtrar si el nombre o justificación es NOTA FINAL, CONCLUSIÓN, etc.
            if re.search(r'(NOTA FINAL|CONCLUSI[ÓO]N)', nombre, re.IGNORECASE) or re.search(r'(NOTA FINAL|CONCLUSI[ÓO]N)', justif, re.IGNORECASE):
                continue
            retos.append({
                'nombre': nombre.strip(),
                'severidad': severidad.strip() if severidad else '',
                'justificacion': justif.strip()
            })
        return retos

    def parse_soluciones(text):
        soluciones = []
        if not text or '[No hay retos extraídos]' in text:
            return soluciones
        text = re.sub(r'#.*', '', text)
        text = re.sub(r'SOLUCIONES PROPUESTAS.*?\n', '', text, flags=re.IGNORECASE|re.DOTALL)
        # Eliminar bloques de NOTA FINAL, CONCLUSIÓN, etc.
        text = re.sub(r'(NOTA FINAL|CONCLUSI[ÓO]N( REFORZADA)?)(.*?)(Página|$)', '', text, flags=re.IGNORECASE|re.DOTALL)
        patron = r'\d+\.\s*Reto:\s*([^\n]+)\s*\n\s*Soluci[oó]n propuesta:\s*([^\n]+(?:\n\s+[^\d\n][^\n]*)*)'
        for m in re.finditer(patron, text):
            reto, solucion = m.groups()
            # Filtrar si el reto o solución es NOTA FINAL, CONCLUSIÓN, etc.
            if re.search(r'(NOTA FINAL|CONCLUSI[ÓO]N)', reto, re.IGNORECASE) or re.search(r'(NOTA FINAL|CONCLUSI[ÓO]N)', solucion, re.IGNORECASE):
                continue
            soluciones.append({
                'reto': reto.strip(),
                'solucion': solucion.strip()})
        return soluciones

    # CONTENIDO POR IDEA
    any_content = False
    first_idea = True
    
    for i, idea in enumerate(analyzed_ideas, 1):
        # Solo añadir página nueva si es la primera idea o si no hay espacio suficiente
        if first_idea:
            pdf.add_page()
            first_idea = False
        else:
            # Verificar si hay espacio suficiente para el título y al menos 3 líneas de contenido
            remaining_space = pdf.h - pdf.get_y() - pdf.b_margin
            needed_space = 30  # Espacio mínimo necesario para título + algo de contenido
            
            if remaining_space < needed_space:
                # No hay espacio suficiente, añadir nueva página
                pdf.add_page()
            else:
                # Hay espacio suficiente, usar separador visual
                pdf.ln(8)
                pdf.set_draw_color(0, 51, 102)
                pdf.set_line_width(0.8)
                pdf.line(15, pdf.get_y(), 195, pdf.get_y())
                pdf.ln(8)
        
        # Actualizar número de página en el índice
        index_entries[i-1]['page'] = pdf.page_no()
        
        # Título de la idea
        pdf.set_font(font_family, 'B', 14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, f"IDEA {i}: {idea.get('idea_title', f'Idea {i}')}", ln=True)
        pdf.ln(5)
        analysis = idea.get('analysis', '')
        if not analysis:
            pdf.set_font(font_family, 'I', 11)
            pdf.set_text_color(150, 0, 0)
            pdf.cell(0, 8, "[No hay análisis disponible]", ln=True)
            continue
        retos_block = retos_blocks_ordered[i-1]
        soluciones_block = soluciones_blocks_ordered[i-1]
        retos = parse_retros(retos_block)
        soluciones = parse_soluciones(soluciones_block)
        # Emparejar por orden (si hay igual número)
        if retos and soluciones and len(retos) == len(soluciones):
            for idx, reto in enumerate(retos):
                # Verificar si hay espacio suficiente para este reto y su solución
                estimated_height = 35  # Altura estimada para reto + solución
                remaining_space = pdf.h - pdf.get_y() - pdf.b_margin
                
                if remaining_space < estimated_height and idx > 0:
                    # No hay espacio suficiente, añadir nueva página
                    pdf.add_page()
                
                pdf.set_font(font_family, 'B', 12)
                pdf.set_text_color(0, 51, 102)
                pdf.cell(0, 8, f"Reto {idx+1}: {reto['nombre']}", ln=True)
                pdf.set_font(font_family, '', 11)
                pdf.set_text_color(80, 80, 80)
                # Mostrar severidad como N/5
                if reto['severidad']:
                    escala = 5  # Por defecto
                    try:
                        val = int(reto['severidad'])
                        if val > 5:
                            escala = val  # Si alguna vez hay escala mayor
                    except:
                        pass
                    pdf.cell(0, 7, f"Severidad: {reto['severidad']}/{escala}", ln=True)
                pdf.multi_cell(0, 7, reto['justificacion'])
                pdf.ln(1)
                pdf.set_font(font_family, 'B', 11)
                pdf.set_text_color(0, 102, 0)
                pdf.cell(0, 7, "Solución propuesta:", ln=True)
                pdf.set_font(font_family, '', 11)
                pdf.set_text_color(0, 0, 0)
                pdf.multi_cell(0, 7, soluciones[idx]['solucion'])
                
                # Espaciado más compacto entre retos
                if idx < len(retos) - 1:  # No añadir espacio después del último reto
                    pdf.ln(3)  # Reducido de 4 a 3
                else:
                    pdf.ln(2)  # Espacio mínimo después del último reto
        else:
            pdf.set_font(font_family, 'B', 12)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 8, "RETOS TÉCNICOS Y DE MERCADO", ln=True)
            pdf.ln(2)
            pdf.set_font(font_family, '', 11)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 7, re.sub(r'#.*', '', retos_block or ''))
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 12)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 8, "SOLUCIONES PROPUESTAS", ln=True)
            pdf.ln(2)
            pdf.set_font(font_family, '', 11)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 7, re.sub(r'#.*', '', soluciones_block or ''))
        any_content = True
        pdf.set_y(-15)
        pdf.set_font(font_family, 'I', 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 10, f"Página {pdf.page_no()}", align='R')

    pdf.page = indice_page
    for entry in index_entries:
        pdf.set_y(entry['y_pos'])
        pdf.set_x(180)
        pdf.set_font(font_family, '', 12)
        pdf.cell(15, 7, str(entry['page']), align='R')

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"solucion_retos_{timestamp}.pdf")
        pdf.output(pdf_path)
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            print(f"✅ PDF de retos y soluciones generado correctamente: {pdf_path}")
            return pdf_path
        else:
            print("❌ El archivo PDF no se generó correctamente")
            return None
    except Exception as e:
        import traceback
        print(f"❌ Error al guardar PDF de retos/soluciones: {e}")
        traceback.print_exc()
        return None

def extraer_bloque(texto, bloque):
    """
    Extrae todas las líneas relevantes de un bloque entre un título y el siguiente bloque o fin.
    Devuelve el bloque completo, incluyendo todos los ítems numerados y justificaciones.
    """
    if not texto or not bloque:
        return ""
    # Buscar el bloque con o sin asteriscos
    patron = rf"(?:\*\*{bloque}\*\*|{bloque})(.*?)(?:\n\*\*|\Z)"
    matches = re.findall(patron, texto, re.DOTALL | re.IGNORECASE)
    if matches:
        # Unir todos los matches y limpiar
        bloque_completo = "\n".join([m.strip() for m in matches if m.strip()])
        return bloque_completo
    return ""

# --- FUNCIONES PROFESIONALES PARA RETOS Y SOLUCIONES ---
def get_challenges_for_idea(analysis, context=""):
    prompt = f"""
Eres un consultor senior de innovación industrial. A partir del siguiente análisis profesional de una idea, extrae los principales RETOS TÉCNICOS y RETOS DE MERCADO que dificultan su implantación o éxito comercial.

- Sé concreto y profesional, sin repetir el análisis original.
- Para cada reto, indica una breve justificación y una severidad del 1 al 5 (5 = crítico).
- Separa claramente los bloques:
  RETOS TÉCNICOS
  1. Nombre del reto -- Severidad: X
     Justificación breve.
  ...
  RETOS DE MERCADO
  1. Nombre del reto -- Severidad: X
     Justificación breve.
  ...
- No inventes retos si no hay base en el análisis.
- Usa siempre formato profesional y claro.

ANÁLISIS DE PARTIDA:
{analysis}
"""
    with timed("↗️  Extracción de retos LLM"):
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un consultor estratégico senior especializado en innovación industrial. Sé concreto, profesional y crítico."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1200
        )
    text = response.choices[0].message.content.strip() if response and response.choices and response.choices[0].message else ""
    return clean_llm_text(text)

def get_solutions_for_challenges(challenges_block, context=""):
    prompt = f"""
Eres un consultor senior de innovación industrial. A partir de la siguiente lista de retos técnicos y de mercado, propone SOLUCIONES PROFESIONALES para cada uno.

- Para cada reto, sugiere una solución concreta, viable y alineada con buenas prácticas de ingeniería y negocio.
- Usa formato:
  1. Reto: [nombre del reto]
     Solución propuesta: [explicación profesional, breve y clara]
  ...
- No repitas los retos, solo soluciones claras y accionables.
- Si algún reto no tiene solución realista, indícalo.

RETOS EXTRAÍDOS:
{challenges_block}
"""
    with timed("↗️  Propuesta de soluciones LLM"):
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un consultor estratégico senior especializado en innovación industrial. Sé concreto, profesional y crítico."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1200
        )
    text = response.choices[0].message.content.strip() if response and response.choices and response.choices[0].message else ""
    return clean_llm_text(text)

def clean_llm_text(text):
    import re
    # Elimina markdown, '**', '*', '__', '###', etc.
    text = re.sub(r'\*\*|\*|__|###|--+', '', text)
    # Elimina espacios múltiples
    text = re.sub(r' +', ' ', text)
    # Normaliza saltos de línea
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def load_logo_unified(pdf, x=None, y=40, width=80, logo_type="standard"):
    """
    Función UNIFICADA para cargar logos en todos los módulos.
    
    Args:
        pdf: Objeto FPDF
        x: Posición X (None = centrado automáticamente)
        y: Posición Y (default: 40)
        width: Ancho del logo (default: 80mm)
        logo_type: "standard" (80mm) o "compact" (60mm)
    
    Returns:
        bool: True si se cargó exitosamente, False si no
    """
    try:
        # Ajustar tamaño según tipo
        if logo_type == "compact":
            width = 60
        else:
            width = 80
            
        # Calcular posición centrada si no se especifica X
        if x is None:
            x = (210 - width) / 2  # A4 = 210mm de ancho
        
        # Determinar directorio base (para compatibilidad Docker)
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        app_root = current_script_dir
        
        if current_script_dir.endswith('.gradio') or current_script_dir.endswith('\\.gradio'):
            app_root = os.path.dirname(current_script_dir)
        
        # ORDEN DE PRIORIDAD ESTANDARIZADO: logo1.png PRIMERO (como en UI)
        logo_names = ["logo1.png", "logo.png"]
        
        # RUTAS DE BÚSQUEDA CORREGIDAS (priorizar directorio de trabajo actual)
        working_dir = os.getcwd()  # Directorio desde donde se ejecuta la app
        
        search_paths = [
            # PRIORIDAD 1: Directorio de trabajo actual (donde está la app principal)
            working_dir,
            os.path.join(working_dir, "output"),
            os.path.join(working_dir, "static"),
            
            # PRIORIDAD 2: Rutas relativas al directorio de trabajo
            ".",
            "./",
            "output/",
            "static/",
            "assets/",
            
            # PRIORIDAD 3: Rutas relativas al script
            current_script_dir,
            app_root,
            os.path.join(current_script_dir, "output"),
            os.path.join(current_script_dir, "static"),
            os.path.join(app_root, "output"),
            os.path.join(app_root, "static"),
            
            # PRIORIDAD 4: Rutas Docker estándar
            "/app/",
            "/app/output/",
            "/app/static/",
            "/app/.gradio/",
            "/app/.gradio/output/",
            
            # PRIORIDAD 5: Fallbacks
            "../",
            "../output/",
            "../static/",
        ]
        
        print(f"🔍 DEBUG LOGO - Directorio de trabajo: {working_dir}")
        print(f"🔍 DEBUG LOGO - Directorio del script: {current_script_dir}")
        
        # Buscar logo en todas las combinaciones
        for logo_name in logo_names:
            for search_path in search_paths:
                logo_path = os.path.join(search_path, logo_name)
                
                # Normalizar ruta para evitar problemas
                logo_path = os.path.normpath(logo_path)
                
                if os.path.exists(logo_path):
                    try:
                        pdf.image(logo_path, x=x, y=y, w=width)
                        print(f"✅ Logo cargado: {logo_name} desde {search_path}")
                        return True
                    except Exception as e:
                        print(f"⚠️ Error cargando {logo_path}: {e}")
                        continue
        
        # Si no se encontró ningún logo, usar fallback de texto
        print("⚠️ No se encontraron archivos de logo, usando logo de texto")
        try:
            create_text_logo(pdf, "SENER", x=x, y=y, width=width)
            return True
        except Exception as e:
            print(f"❌ Error creando logo de texto: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error general cargando logo: {e}")
        return False

def download_fonts_if_needed(target_dir):
    """
    Descarga las fuentes DejaVu si no existen en el directorio objetivo.
    Diseñado para funcionar tanto en desarrollo como en Docker.
    """
    try:
        import requests
        
        # Asegurar que el directorio objetivo existe
        os.makedirs(target_dir, exist_ok=True)
        
        # URLs de las fuentes DejaVu desde GitHub (fuente confiable)
        fonts_to_download = {
            'DejaVuSans.ttf': 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf',
            'DejaVuSans-Bold.ttf': 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf',
            'DejaVuSans-Oblique.ttf': 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Oblique.ttf'
        }
        
        all_downloaded = True
        for font_name, font_url in fonts_to_download.items():
            font_path = os.path.join(target_dir, font_name)
            
            # Si la fuente ya existe y tiene un tamaño razonable, saltarla
            if os.path.exists(font_path) and os.path.getsize(font_path) > 50000:  # > 50KB
                print(f"✅ Fuente {font_name} ya existe")
                continue
                
            print(f"🔄 Descargando {font_name}...")
            try:
                response = requests.get(font_url, timeout=30)
                response.raise_for_status()
                
                with open(font_path, 'wb') as f:
                    f.write(response.content)
                
                # Verificar que se descargó correctamente
                if os.path.exists(font_path) and os.path.getsize(font_path) > 50000:
                    print(f"✅ {font_name} descargada correctamente ({os.path.getsize(font_path)} bytes)")
                else:
                    print(f"❌ {font_name} descargada pero parece corrupta")
                    all_downloaded = False
                    
            except requests.RequestException as e:
                print(f"❌ Error descargando {font_name}: {e}")
                all_downloaded = False
            except Exception as e:
                print(f"❌ Error guardando {font_name}: {e}")
                all_downloaded = False
        
        return all_downloaded
        
    except ImportError:
        print("❌ Módulo 'requests' no disponible para descargar fuentes")
        return False
    except Exception as e:
        print(f"❌ Error general descargando fuentes: {e}")
        return False

# En generate_challenges_and_solutions_pdf, mostrar el texto tal cual, sin intentar parsear JSON
# En los bloques de retos y soluciones, usar pdf.multi_cell(0, 7, texto) para mostrar el resultado limpio

class RetosPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skip_footer = True  # Portada e índice
    def footer(self):
        # No mostrar pie en portada ni índice
        if self.skip_footer or self.page_no() <= 2:
            return
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Página {self.page_no()}", align='R')

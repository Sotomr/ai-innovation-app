import PyPDF2
import re
import tempfile
import os
from datetime import datetime
from fpdf import FPDF
import openai
import asyncio
import requests
import concurrent.futures
import gc
import json
import traceback

# Importar configuración centralizada de OpenAI
from openai_config import get_openai_client, get_deployment_name

# Obtener el cliente y configuración de OpenAI desde el módulo centralizado
client = get_openai_client()
DEPLOYMENT_NAME = get_deployment_name()

def extract_text_from_pdf(pdf_path):
    """
    Extrae el texto de un archivo PDF
    """
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        print(f"Error extrayendo texto del PDF: {str(e)}")
        return None

def detect_ideas_basic(text):
    """
    Detecta ideas en el texto CAPTURANDO TODA LA INFORMACIÓN descriptiva
    disponible en el documento original, y evitando generar ideas falsas.
    """
    ideas = []
    
    # PRIMER PASO: Extraer ideas claramente marcadas por número o formato común
    print("Paso 1: Buscando ideas claramente numeradas o marcadas...")
    
    # Buscar secciones de "Idea X:" o "X. [texto]" primero (más confiable)
    # Patrón mejorado para capturar el texto hasta la siguiente idea o fin del documento
    # Capturar prefijo (grupo 1) y todo el contenido restante (grupo 2)
    idea_pattern = r'(?:^|\n)(?:Idea|IDEA)\s*\d+[\.:]\s*([^\n]+)([\s\S]*?)(?=(?:^|\n)(?:Idea|IDEA)\s*\d+[\.:]|$)'
    idea_matches = re.findall(idea_pattern, text)
    
    # Patrón para ideas numeradas: capturar número (grupo 1), título (grupo 2) y contenido (grupo 3)
    numbered_pattern = r'(?:^|\n)\s*(\d+)[\.:](?:\s+)([^\n]+)([\s\S]*?)(?=(?:^|\n)\s*\d+[\.:]\s+|$)'
    numbered_matches = re.findall(numbered_pattern, text)
    
    # Si encontramos ideas claramente numeradas, usarlas primero
    if idea_matches:
        print(f"✅ Se encontraron {len(idea_matches)} ideas marcadas con formato 'Idea X:'")
        for i, (title, content) in enumerate(idea_matches, 1):
            title = title.strip()
            content = content.strip()
            
            # Verificar que hay título y contenido válidos
            if title and len(title) > 3 and content and len(content) > 10:
                # IMPORTANTE: Usar SOLO el título real extraído (lo que viene después de "Idea X:")
                # y añadir el contenido completo
                full_text = f"{title}\n\n{content}"
                ideas.append({
                    'idea': full_text,
                    'analysis': '',
                    'metrics': {}
                })
                print(f"  Idea {i}: Título: '{title[:50]}...' + {len(content)} caracteres de contenido")
    elif numbered_matches:
        print(f"✅ Se encontraron {len(numbered_matches)} ideas con formato 'X. [texto]'")
        for i, (num, title, content) in enumerate(numbered_matches, 1):
            title = title.strip()
            content = content.strip()
            
            # Verificar que hay título y contenido válidos
            if title and len(title) > 3 and content and len(content) > 10:
                # IMPORTANTE: Usar SOLO el título real extraído (lo que viene después de "X.")
                # y añadir el contenido completo
                full_text = f"{title}\n\n{content}"
                ideas.append({
                    'idea': full_text,
                    'analysis': '',
                    'metrics': {}
                })
                print(f"  Idea {num}: Título: '{title[:50]}...' + {len(content)} caracteres de contenido")
    
    # Si no encontramos ideas con formatos claros, intentar con párrafos
    if not ideas:
        print("Paso 2: Buscando párrafos que podrían ser ideas...")
        # Mejorar la división de párrafos para mantener la estructura de cada idea
        paragraphs = re.split(r'\n\s*\n\s*\n', text)  # Buscar dobles saltos de línea al menos
        
        # Filtrar párrafos cortos o irrelevantes pero mantener la estructura interna
        valid_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para and len(para) > 50 and len(para.split()) > 15:
                valid_paragraphs.append(para)
        
        if valid_paragraphs:
            print(f"✅ Se identificaron {len(valid_paragraphs)} párrafos como posibles ideas")
            for i, para in enumerate(valid_paragraphs, 1):
                # Intentar extraer título y contenido del párrafo
                lines = para.split('\n', 1)
                if len(lines) > 1:
                    title = lines[0].strip()
                    content = lines[1].strip()
                    
                    # Si el título parece ser un número o tiene formato "Idea X:", extraer solo el título real
                    title_match = re.match(r'^(?:Idea|IDEA)?\s*\d+[\.:]\s*([^\n]+)', title)
                    if title_match:
                        title = title_match.group(1).strip()
                    
                    full_text = f"{title}\n\n{content}"
                else:
                    # Si no se puede dividir, usar todo como contenido con título genérico
                    title = f"Concepto {i}"
                    content = para
                    full_text = f"{title}\n\n{content}"
                
                # Preservar la estructura interna del párrafo (posibles secciones)
                ideas.append({
                    'idea': full_text,
                    'analysis': '',
                    'metrics': {}
                })
                print(f"  Idea {i}: Título: '{title[:50]}...' + {len(content)} caracteres")
    
    # Verificar que todas las ideas tienen contenido suficiente
    verified_ideas = []
    for idx, idea in enumerate(ideas, 1):
        idea_text = str(idea.get('idea', '')).strip()
        if idea_text:
            # IMPORTANTE: NO normalizar espacios, ya que perderíamos estructura
            # Solo eliminar espacios extra al inicio y final
            idea_text = idea_text.strip()
            
            # Verificar que hay contenido descriptivo después del título
            if "\n\n" in idea_text:
                parts = idea_text.split("\n\n", 1)
                title = parts[0].strip()
                content = parts[1].strip()
                
                if content and len(content) > 20:  # Asegurar que hay contenido descriptivo
                    print(f"  ✓ Idea {idx} verificada: título + {len(content)} caracteres de contenido")
                    verified_ideas.append({
                        'idea': idea_text,
                        'analysis': str(idea.get('analysis', '')).strip(),
                        'metrics': idea.get('metrics', {})
                    })
                else:
                    print(f"  ⚠️ Idea {idx} descartada: no tiene contenido descriptivo suficiente")
            else:
                # Si no tiene formato de título pero hay suficiente texto, la aceptamos como idea
                if len(idea_text) > 100:
                    # Intentar separar título y contenido
                    if "\n" in idea_text:
                        parts = idea_text.split("\n", 1)
                        title = parts[0].strip()
                        content = parts[1].strip()
                        
                        # Reformatear para tener doble salto entre título y contenido
                        idea_text = f"{title}\n\n{content}"
                    
                    verified_ideas.append({
                        'idea': idea_text,
                        'analysis': str(idea.get('analysis', '')).strip(),
                        'metrics': idea.get('metrics', {})
                    })
                    print(f"  ✓ Idea {idx} verificada: {len(idea_text)} caracteres")
    
    print(f"✅ Total de ideas verificadas: {len(verified_ideas)}")
    
    # Ordenar ideas por longitud para priorizar las más detalladas
    verified_ideas.sort(key=lambda x: len(str(x.get('idea', ''))), reverse=True)
    
    return verified_ideas

async def enhance_idea_with_ai(idea, context):
    """
    Mejora una idea individual usando OpenAI de manera asíncrona
    """
    try:
        prompt = f"""
        Analiza la siguiente idea y mejórala con el contexto proporcionado:
        
        Idea original: {idea['idea']}
        
        Contexto adicional: {context}
        
        Por favor, proporciona:
        1. Una versión mejorada y estructurada de la idea
        2. Un breve análisis de su potencial
        3. Puntos clave a considerar
        
        Formato de respuesta:
        Idea mejorada: [texto]
        Análisis: [texto]
        Puntos clave: [lista]
        """
        
        response = await client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis y mejora de ideas innovadoras."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        enhanced_text = response.choices[0].message.content
        
        # Extraer las partes de la respuesta
        idea_match = re.search(r'Idea mejorada:\s*(.*?)(?=Análisis:|$)', enhanced_text, re.DOTALL)
        analysis_match = re.search(r'Análisis:\s*(.*?)(?=Puntos clave:|$)', enhanced_text, re.DOTALL)
        
        # Asegurar que todos los valores son strings
        return {
            'idea': str(idea_match.group(1).strip() if idea_match else idea['idea']),
            'analysis': str(analysis_match.group(1).strip() if analysis_match else ''),
            'metrics': {}
        }
    except Exception as e:
        print(f"Error mejorando idea con AI: {str(e)}")
        return {
            'idea': str(idea['idea']),
            'analysis': '',
            'metrics': {}
        }

async def process_and_structure_idea(idea):
    """
    Procesa y estructura una idea usando AI para tener un formato consistente
    """
    try:
        # Asegurar que la idea es un string válido
        idea_text = str(idea.get('idea', '')).strip()
        if not idea_text or len(idea_text) < 3 or idea_text.isdigit():
            return idea

        # Limpiar cualquier bullet point u otros caracteres problemáticos
        clean_text = idea_text.replace("•", "-").replace("·", "-").replace("…", "...").replace("\u2022", "-")

        prompt = f"""
        Reformatea la siguiente idea técnica en un solo párrafo claro y profesional:

        {clean_text}

        Por favor, proporciona la respuesta en el siguiente formato exacto:
        TÍTULO: [título conciso de la idea]
        TEXTO: [un párrafo único que combine toda la información sin bullet points ni listas]
        """

        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un experto en redacción técnica. Reformatea ideas manteniendo su esencia técnica pero presentándolas en un formato simple de título y párrafo único."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        structured_text = response.choices[0].message.content
        
        # Extraer las partes de la respuesta
        title = ""
        paragraph = ""
        
        # Buscar título
        title_match = re.search(r'TÍTULO:\s*(.*?)(?=TEXTO:|$)', structured_text, re.DOTALL | re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
        
        # Buscar texto
        text_match = re.search(r'TEXTO:\s*(.*?)$', structured_text, re.DOTALL | re.IGNORECASE)
        if text_match:
            paragraph = text_match.group(1).strip()
        
        # Construir el texto formateado (más simple, sin bullets)
        formatted_text = ""
        if title:
            formatted_text += f"{title}\n\n"
        if paragraph:
            formatted_text += f"{paragraph}"
        
        return {
            'idea': formatted_text.strip(),
            'analysis': str(idea.get('analysis', '')).strip(),
            'metrics': {}
        }
    except Exception as e:
        print(f"Error procesando idea con AI: {str(e)}")
        # Si hay error, devolver la idea original pero limpiando caracteres problemáticos
        clean_idea = str(idea.get('idea', '')).strip()
        clean_idea = clean_idea.replace("•", "-").replace("·", "-").replace("…", "...").replace("\u2022", "-")
        return {
            'idea': clean_idea,
            'analysis': str(idea.get('analysis', '')).strip(),
            'metrics': {}
        }

def clean_text_for_pdf(text):
    """
    Limpia el texto para hacerlo compatible con las fuentes estándar de PDF.
    Reemplaza caracteres Unicode problemáticos por equivalentes ASCII seguros.
    """
    if not text:
        return ""
    
    # Tabla de reemplazo para caracteres problemáticos
    replacements = {
        "•": "-",   # Bullet points
        "·": "-",   # Middle dot
        "…": "...", # Ellipsis
        "\u2022": "-", # Bullet
        "\u2023": "-", # Triangular bullet
        "\u2043": "-", # Hyphen bullet
        "\u204C": "-", # Black leftwards bullet
        "\u204D": "-", # Black rightwards bullet
        "\u2219": "-", # Bullet operator
        "–": "-",   # En dash
        "—": "--",  # Em dash
        """: "\"",  # Comillas dobles
        """: "\"",  # Comillas dobles
        "'": "'",   # Comillas simples
        "'": "'",   # Comillas simples
        "«": "\"",  # Comillas angulares
        "»": "\"",  # Comillas angulares
        "„": "\"",  # Comillas bajas
        "‟": "\"",  # Comillas bajas
        "❝": "\"",  # Comillas ornamentadas
        "❞": "\"",  # Comillas ornamentadas
    }
    
    # Aplicar reemplazos
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    # Filtro adicional para caracteres muy problemáticos (fuera del rango ASCII extendido)
    # Solo si encontramos errores después de los reemplazos específicos
    cleaned_text = ""
    for char in text:
        # Mantener ASCII y caracteres extendidos comunes, reemplazar otros
        if ord(char) < 128 or (ord(char) >= 160 and ord(char) <= 255):
            cleaned_text += char
        else:
            # Intentar encontrar una aproximación razonable para caracteres especiales
            if char in 'áàäâãå':
                cleaned_text += 'a'
            elif char in 'éèëê':
                cleaned_text += 'e'
            elif char in 'íìïî':
                cleaned_text += 'i'
            elif char in 'óòöôõ':
                cleaned_text += 'o'
            elif char in 'úùüû':
                cleaned_text += 'u'
            elif char in 'ñ':
                cleaned_text += 'n'
            elif char in 'ç':
                cleaned_text += 'c'
            else:
                cleaned_text += '?'
    
    return cleaned_text

def process_idea_sync(idea, context=None):
    """
    Procesa una idea extrayendo SOLO el título original (breve) y usando el CONTENIDO descriptivo
    del PDF original como base para generar un texto fluido y coherente con OpenAI.
    """
    try:
        # Verificar que tenemos contenido para procesar
        idea_text = str(idea.get('idea', '')).strip()
        if not idea_text or len(idea_text) < 10:
            return idea

        # Primera etapa: Extracción simple y directa del título
        # Buscar el título en formato "Idea X: [título]" o similar
        title_pattern = r'^(Idea\s*\d+[\.:]\s*|\d+[\.:]\s*)([^-\n]+)'
        title_match = re.search(title_pattern, idea_text, re.IGNORECASE)
        
        if title_match:
            # IMPORTANTE: Extraer SOLO el título real (lo que viene después de "Idea X:")
            # y NO incluir "Idea X:" en el título
            prefix = title_match.group(1).strip()  # "Idea X:" o "X."
            real_title = title_match.group(2).strip()  # El título real
            
            # Extraer el contenido (todo lo que viene después del título completo)
            title_end = title_match.end()
            content = idea_text[title_end:].strip()
            
            # Para debugging
            print(f"Prefijo: '{prefix}', Título real: '{real_title}'")
        else:
            # Si no tiene el formato estándar, tomar la primera línea como título
            if "\n" in idea_text:
                parts = idea_text.split("\n", 1)
                real_title = parts[0].strip()
                content = parts[1].strip()
            else:
                # Si no hay separación, usar todo como título y no hay contenido
                real_title = idea_text
                content = ""

        # IMPORTANTE: Si no hay contenido suficiente, NO generar uno a partir del título
        # En lugar de esto, usar el título como está y dejarlo sin descripción adicional
        if not content or len(content) < 5:
            print(f"⚠️ No hay contenido descriptivo suficiente después del título: '{real_title[:50]}...'")
            # Devolver idea con solo el título real, sin inventar una descripción
            return {
                'idea': real_title,
                'analysis': str(idea.get('analysis', '')).strip(),
                'metrics': idea.get('metrics', {})
            }

        # Segunda etapa: Pre-procesamiento directo del contenido original para eliminar marcadores
        # Eliminar "- Descripción general:" y otros marcadores similares
        content = re.sub(r'-\s*Descripción\s+general\s*:\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'-\s*Mecanismo\s+de\s+acción\s*:\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'-\s*Aplicación[^:]*:\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'-\s*Ventajas\s*:\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'-\s*Desafíos\s*:\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'-\s*\w+(?:\s+\w+){0,3}\s*:\s*', '', content, flags=re.IGNORECASE)  # Patrón general para otros marcadores
        
        # Eliminar guiones al inicio de líneas y normalizar espacios
        content = re.sub(r'(?:^|\n)\s*-\s*', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()

        # Verificación de seguridad: asegurarnos de que hay contenido real para procesar
        if not content or len(content) < 10:
            print(f"⚠️ Después de limpiar marcadores, no queda contenido descriptivo para: '{real_title[:50]}...'")
            # Devolver solo el título real en este caso
            return {
                'idea': real_title,
                'analysis': str(idea.get('analysis', '')).strip(),
                'metrics': idea.get('metrics', {})
            }
        
        print(f"✓ Contenido descriptivo encontrado ({len(content)} caracteres) para título: '{real_title[:40]}...'")
        print(f"   Primeros 80 caracteres del contenido: '{content[:80]}...'")

        # Tercera etapa: usar OpenAI para mejorar el CONTENIDO extraído del PDF
        clean_content = clean_text_for_pdf(content)
        
        # Usar OpenAI para reformatear el contenido en un párrafo cohesivo
        prompt = f"""
        Reescribe el siguiente contenido técnico en un párrafo único y cohesivo,
        manteniendo todos los detalles técnicos importantes:
        
        {clean_content}
        
        Instrucciones:
        1. NO introduzcas ni menciones etiquetas como "Descripción general", "Mecanismo de acción", etc.
        2. El resultado debe ser UN SOLO PÁRRAFO cohesivo sin subdivisiones
        3. Mantén TODOS los detalles técnicos y valores numéricos exactos del texto original
        4. Usa lenguaje sencillo y profesional
        5. NO agregues información extra que no esté explícitamente en el texto original
        """
        
        if context and isinstance(context, str) and len(context.strip()) > 0:
            prompt += f"\n\nContexto adicional (APLICA ESTE CONTEXTO ESPECÍFICAMENTE A LA IDEA '{real_title}'): {context.strip()}\n\n- Asegúrate de explicar cómo esta idea específica se relaciona con el contexto proporcionado.\n- IMPORTANTE: Integra conceptos del contexto de manera relevante y específica para esta idea en particular."

        # Usar la API de OpenAI con una temperatura muy baja para mayor fidelidad al texto original
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "system", 
                    "content": "Tu tarea es convertir un texto técnico fragmentado en un párrafo cohesivo y bien estructurado, sin usar marcadores ni etiquetas. No debes añadir información nueva pero DEBES integrar el contexto proporcionado de manera específica para esta idea en particular. Mantén TODOS los detalles técnicos, cifras y valores específicos del texto original y relaciona la idea con el contexto de manera relevante."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Temperatura muy baja = seguir instrucciones estrictamente
            max_tokens=1000
        )
        
        # Extraer el contenido reescrito
        if response and response.choices and response.choices[0].message:
            rewritten_content = response.choices[0].message.content.strip()
            
            # Limpieza final para evitar problemas de codificación
            clean_rewritten_content = clean_text_for_pdf(rewritten_content)
            
            # Verificar que el contenido reescrito no esté vacío
            if not clean_rewritten_content:
                clean_rewritten_content = "No se pudo procesar el contenido descriptivo para esta idea."
            
            # Devolver la idea formateada: título real + contenido reescrito
            # Asegurar que hay exactamente un doble salto de línea entre título y contenido
            formatted_text = f"{real_title.strip()}\n\n{clean_rewritten_content.strip()}"
            
            # Log de debugging
            print(f"✅ Idea procesada: Título real: '{real_title[:30]}...' + Contenido reescrito: '{clean_rewritten_content[:30]}...'")
            
            return {
                'idea': formatted_text,
                'analysis': str(idea.get('analysis', '')).strip(),
                'metrics': idea.get('metrics', {})
            }
        else:
            # Si la API falla, devolver el título y el contenido pre-procesado
            formatted_text = f"{real_title.strip()}\n\n{clean_content.strip()}"
            print(f"⚠️ Usando contenido pre-procesado (sin AI) debido a fallo de API: '{real_title[:30]}...'")
            
            return {
                'idea': formatted_text,
                'analysis': str(idea.get('analysis', '')).strip(),
                'metrics': idea.get('metrics', {})
            }
    except Exception as e:
        print(f"❌ Error procesando idea: {str(e)}")
        traceback.print_exc()
        
        # En caso de error, intentar devolver al menos el título
        try:
            idea_text = str(idea.get('idea', '')).strip()
            
            # Intentar extraer título y contenido de forma básica
            if "\n" in idea_text:
                title, content = idea_text.split("\n", 1)
                title = title.strip()
                content = content.strip()
                
                # Si hay contenido, formatearlo correctamente
                if content:
                    formatted_text = f"{title}\n\n{content}"
                else:
                    formatted_text = title
            else:
                # Si no hay salto de línea, usar todo como título
                formatted_text = idea_text
            
            # Limpiar para evitar problemas de codificación
            formatted_text = clean_text_for_pdf(formatted_text)
            
            return {
                'idea': formatted_text,
                'analysis': str(idea.get('analysis', '')).strip(),
                'metrics': idea.get('metrics', {})
            }
        except:
            # Si todo falla, devolver la idea original sin cambios
            return idea

def batch_process_ideas(ideas, batch_size=12, progress_callback=None, context=None):
    """
    Procesa un lote de ideas en paralelo para optimizar tiempo,
    manteniendo los títulos originales y mejorando solo el contenido.
    
    Args:
        ideas (list): Lista de ideas a procesar
        batch_size (int): Número de ideas a procesar simultáneamente
        progress_callback (function): Función para reportar progreso
        context (str): Contexto opcional proporcionado por el usuario
        
    Returns:
        list: Lista de ideas procesadas
    """
    if not ideas:
        return []
        
    # Verificación del contexto para debugging
    if context and isinstance(context, str) and len(context.strip()) > 0:
        print(f"\n====== CONTEXTO EN BATCH_PROCESS_IDEAS ======")
        print(f"Contexto disponible: {len(context)} caracteres")
        print(f"Primeros 100 caracteres: '{context[:100]}...'")
        print(f"==============================================\n")
    else:
        print("\n⚠️ No hay contexto disponible para batch_process_ideas\n")
        
    # Si hay pocas ideas, procesarlas una por una
    if len(ideas) <= 3:
        print(f"Procesando {len(ideas)} ideas de forma secuencial...")
        processed_ideas = []
        for i, idea in enumerate(ideas, 1):
            # Extraer el título de la idea para el log
            idea_text = str(idea.get('idea', '')).strip()
            title = idea_text.split('\n')[0][:30] if '\n' in idea_text else idea_text[:30]
            
            print(f"Processing idea {i}/{len(ideas)}: '{title}...' with context of {len(context) if context else 0} characters")
            
            if progress_callback:
                progress_callback(i, len(ideas))
                
            processed = process_idea_sync(idea, context)
            if processed and processed.get('idea'):
                processed_ideas.append(processed)
                
        return processed_ideas
    
    # Para más ideas, procesar en lotes más grandes
    print(f"Procesando {len(ideas)} ideas en lotes de {batch_size}...")
    all_processed = []
    total_processed = 0
    
    # Crear un pool de workers para procesar en paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
        # Dividir las ideas en lotes
        batches = [ideas[i:i + batch_size] for i in range(0, len(ideas), batch_size)]
        
        for batch_idx, batch in enumerate(batches, 1):
            print(f"Procesando lote {batch_idx}/{len(batches)} ({len(batch)} ideas)...")
            
            # Procesar el lote en paralelo - asegurar que context se pasa correctamente a cada llamada
            futures = []
            for idea_idx, idea in enumerate(batch):
                # Extraer el título de la idea para el log
                idea_text = str(idea.get('idea', '')).strip()
                title = idea_text.split('\n')[0][:30] if '\n' in idea_text else idea_text[:30]
                
                print(f"  Enviando idea {total_processed + idea_idx + 1}: '{title}...' con contexto de {len(context) if context else 0} caracteres")
                futures.append(executor.submit(process_idea_sync, idea, context))
                
            batch_results = []
            
            # Esperar a que todas las ideas del lote se procesen
            for future_idx, future in enumerate(concurrent.futures.as_completed(futures)):
                try:
                    result = future.result(timeout=20)  # Reducido a 20 segundos por idea
                    if result and isinstance(result, dict) and result.get('idea'):
                        # Obtener título del resultado para log
                        result_text = str(result.get('idea', '')).strip()
                        result_title = result_text.split('\n')[0][:30] if '\n' in result_text else result_text[:30]
                        
                        print(f"  ✅ Completada idea: '{result_title}...'")
                        batch_results.append(result)
                        total_processed += 1
                        if progress_callback:
                            progress_callback(total_processed, len(ideas))
                    else:
                        print(f"  ⚠️ Idea procesada sin resultado válido")
                except Exception as e:
                    print(f"  ❌ Error procesando idea: {str(e)}")
            
            all_processed.extend(batch_results)
            print(f"Progreso: {total_processed}/{len(ideas)} ideas procesadas")
            
            # Liberar memoria después de cada lote
            gc.collect()
    
    return all_processed

def process_pdf_file(pdf_path, context=None):
    """
    Procesa un archivo PDF para extraer y estructurar ideas.
    
    Args:
        pdf_path: Ruta al archivo PDF
        context: Contexto opcional para mejorar las ideas
        
    Returns:
        Tupla de (lista_de_ideas, mensaje_de_estado)
    """
    try:
        print(f"Procesando PDF: {pdf_path}")
        
        # Registrar información sobre el contexto recibido
        if context:
            print(f"\n==== CONTEXTO RECIBIDO EN PDF PROCESSOR ====")
            print(f"Tipo: {type(context)}")
            print(f"Longitud: {len(context)} caracteres")
            print(f"Contenido: {context[:200]}...")
            print(f"=========================================\n")
        else:
            print(f"\n⚠️ NO SE RECIBIÓ CONTEXTO en process_pdf_file\n")
        
        # Extraer texto del PDF
        text = extract_text_from_pdf(pdf_path)
        if not text:
            print("❌ No se pudo extraer texto del PDF")
            return None, "No se pudo extraer texto del PDF"
            
        print(f"✅ Texto extraído: {len(text)} caracteres")
        
        # Verificar si podemos usar el nuevo método optimizado
        try:
            # Importar el módulo de análisis competitivo
            from competitor_analysis_module import CompetitorAnalysis
            
            # Inicializar el analizador
            analyzer = CompetitorAnalysis()
            
            # Usar el nuevo método para procesar ideas del PDF
            print("Utilizando método optimizado para procesamiento de ideas...")
            
            # IMPORTANTE: Asegurarse de que el contexto nunca sea None para evitar problemas
            # con las comprobaciones de contexto en los métodos siguientes
            context_text = ""
            if context is not None:
                context_text = str(context)  # Convertir a string para garantizar compatibilidad
                
            print(f"\n==== PASANDO CONTEXTO AL MÉTODO OPTIMIZADO ====")
            print(f"Longitud del contexto pasado: {len(context_text)} caracteres")
            print(f"Primeros 100 caracteres: {context_text[:100]}")
            print(f"==============================================\n")
            
            processed_ideas = analyzer.process_pdf_ideas(text, context_text)
            
            if processed_ideas:
                print(f"✅ Se procesaron {len(processed_ideas)} ideas con el método optimizado")
                
                # Transformar al formato esperado por la interfaz
                formatted_ideas = []
                for idea_dict in processed_ideas:
                    title = idea_dict.get("idea", "")
                    description = idea_dict.get("descripcion", "")
                    tags = idea_dict.get("tags", [])
                    
                    # Crear la estructura esperada
                    # El formato de idea es: título en la primera línea, 
                    # seguido por doble salto de línea y luego la descripción completa
                    formatted_idea = {
                        'idea': f"{title}\n\n{description}",
                        'analysis': f"Tags identificados: {', '.join(tags)}",
                        'metrics': {}
                    }
                    formatted_ideas.append(formatted_idea)
                    
                return formatted_ideas, f"✅ Se procesaron {len(formatted_ideas)} ideas con el método optimizado"
            else:
                print("⚠️ El método optimizado no encontró ideas, usando método tradicional...")
        except Exception as opt_error:
            print(f"⚠️ No se pudo usar el método optimizado: {str(opt_error)}")
            traceback.print_exc()
            print("Utilizando método tradicional...")
        
        # Si llegamos aquí, usamos el método tradicional
        ideas = detect_ideas_basic(text)
        print(f"✅ Se detectaron {len(ideas)} ideas")
        
        if context:
            print("Mejorando ideas con contexto adicional...")
            # Procesar ideas con contexto si está disponible
            processed_ideas = batch_process_ideas(ideas, context=context)
            print(f"✅ Se procesaron {len(processed_ideas)} ideas")
            return processed_ideas, f"✅ Se procesaron {len(processed_ideas)} ideas con el método tradicional"
        else:
            # Si no hay contexto, devolver las ideas tal cual
            return ideas, f"✅ Se detectaron {len(ideas)} ideas con el método tradicional"
            
    except Exception as e:
        print(f"❌ Error procesando PDF: {str(e)}")
        traceback.print_exc()
        return None, f"Error procesando PDF: {str(e)}"

def generate_robust_pdf(items, title="Ideas Procesadas", template="default"):
    """
    Función robusta para generar PDFs usando reportlab.
    
    Args:
        items (list): Lista de elementos a incluir en el PDF
        title (str): Título del documento
        template (str): Tipo de template a usar ('default', 'analysis', 'ranking', 'competitor')
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        
        # Crear directorio de salida
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Generar nombre de archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"{title.lower().replace(' ', '_')}_{timestamp}.pdf")
        
        # Configurar el documento
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Estilos
        styles = getSampleStyleSheet()
        
        # Estilo para título principal
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1  # Centrado
        )
        
        # Estilo para subtítulos
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10
        )
        
        # Estilo para texto normal
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceBefore=6,
            spaceAfter=6
        )
        
        # Lista de elementos para el PDF
        elements = []
        
        # Título principal
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.5*inch))
        
        # Procesar cada elemento según el template
        for idx, item in enumerate(items, 1):
            try:
                if not isinstance(item, dict):
                    continue
                    
                # Agregar número de elemento
                elements.append(Paragraph(f"#{idx}", heading_style))
                
                if template == "analysis":
                    # Template para análisis detallado
                    if 'idea' in item:
                        elements.append(Paragraph(str(item['idea']).strip(), heading_style))
                    if 'analysis' in item:
                        elements.append(Paragraph("Análisis:", heading_style))
                        analysis_text = str(item['analysis']).strip()
                        paragraphs = analysis_text.split('\n')
                        for p in paragraphs:
                            if p.strip():
                                elements.append(Paragraph(p.strip(), normal_style))
                                
                elif template == "ranking":
                    # Template para ranking
                    if 'score' in item:
                        elements.append(Paragraph(f"Puntuación: {item['score']}", heading_style))
                    if 'idea' in item:
                        elements.append(Paragraph(str(item['idea']).strip(), normal_style))
                    if 'justification' in item:
                        elements.append(Paragraph("Justificación:", heading_style))
                        elements.append(Paragraph(str(item['justification']).strip(), normal_style))
                        
                elif template == "competitor":
                    # Template para análisis de competidores
                    if 'idea' in item:
                        elements.append(Paragraph(str(item['idea']).strip(), heading_style))
                    if 'competitors' in item:
                        elements.append(Paragraph("Competidores:", heading_style))
                        for comp in item['competitors']:
                            elements.append(Paragraph(f"- {comp}", normal_style))
                    if 'analysis' in item:
                        elements.append(Paragraph("Análisis Competitivo:", heading_style))
                        elements.append(Paragraph(str(item['analysis']).strip(), normal_style))
                        
                else:
                    # Template por defecto
                    for key, value in item.items():
                        if isinstance(value, str) and value.strip():
                            elements.append(Paragraph(f"{key.title()}:", heading_style))
                            elements.append(Paragraph(value.strip(), normal_style))
                
                # Espaciador entre elementos
                elements.append(Spacer(1, 0.3*inch))
                
            except Exception as e:
                print(f"Error procesando elemento {idx}: {str(e)}")
                continue
        
        # Generar el PDF
        try:
            doc.build(elements)
            print(f"✅ PDF generado exitosamente: {pdf_path}")
            return pdf_path
        except Exception as e:
            print(f"Error generando PDF: {str(e)}")
            return None
            
    except Exception as e:
        print(f"Error general: {str(e)}")
        return None

def generate_pdf_from_ideas(ideas, title="Listado de Ideas Procesadas"):
    """
    Genera un PDF a partir de una lista de ideas formateadas.
    Asegura que el título y el contenido descriptivo se muestren claramente separados
    en el PDF, sin páginas en blanco entre ideas.
    """
    try:
        if not ideas or not isinstance(ideas, list):
            print("❌ Error: No hay ideas para generar el PDF")
            return None
            
        # Crear PDF con formato mejorado
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Colores corporativos
        primary_color = (41, 128, 185)  # Azul
        secondary_color = (44, 62, 80)  # Gris oscuro
        accent_color = (39, 174, 96)    # Verde
        
        # Primera página - Portada
        pdf.add_page()
        
        # Intentar añadir el logo
        try:
            logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
            logo_found = False
            
            for logo_path in logo_paths:
                if os.path.exists(logo_path):
                    # Calcular posición centrada para el logo
                    pdf.image(logo_path, x=(210-80)/2, y=40, w=80)
                    logo_found = True
                    print(f"✅ Logo encontrado en: {logo_path}")
                    break
                    
            if not logo_found:
                print("⚠️ Archivo logo.png no encontrado. Se generará la portada sin logo.")
        except Exception as e:
            print(f"⚠️ Error al cargar el logo: {str(e)}")
        
        # Título principal con formato mejorado
        pdf.set_y(130)  # Espacio para dejar sitio al logo
        pdf.set_font('Arial', 'B', 24)
        pdf.set_text_color(*secondary_color)
        pdf.cell(0, 20, "INFORME DE IDEAS", ln=True, align='C')
        pdf.cell(0, 20, "INNOVADORAS", ln=True, align='C')
        
        # Fecha y contador de ideas
        pdf.set_y(180)
        pdf.set_font('Arial', '', 14)
        pdf.cell(0, 10, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.cell(0, 10, f"Total de ideas: {len(ideas)}", ln=True, align='C')
        
        # Contenido principal - Ideas continuas sin páginas en blanco
        pdf.add_page()
        
        # SUMARIO: Recuento de ideas con y sin descripción
        ideas_con_descripcion = 0
        ideas_solo_titulo = 0
        
        # Debug: mostrar la estructura de las ideas antes de procesarlas
        print("\n---- Estructura de ideas para el PDF ----")
        for i, idea in enumerate(ideas, 1):
            if isinstance(idea, dict):
                idea_text = str(idea.get('idea', '')).strip()
                has_description = "\n\n" in idea_text
                if has_description:
                    ideas_con_descripcion += 1
                else:
                    ideas_solo_titulo += 1
                    
                print(f"Idea {i}: {idea_text[:100]}... {'(TIENE DESCRIPCIÓN)' if has_description else '(SOLO TÍTULO)'}")
        
        print(f"\n📊 RESUMEN: {ideas_con_descripcion} ideas tienen descripción, {ideas_solo_titulo} ideas solo tienen título")
        
        for i, idea in enumerate(ideas, 1):
            if not isinstance(idea, dict):
                print(f"⚠️ Idea {i} no es un diccionario, es {type(idea)}. Saltando...")
                continue
                
            # Extraer texto completo de la idea
            idea_text = str(idea.get('idea', '')).strip()
            if not idea_text:
                print(f"⚠️ Idea {i} no tiene texto. Saltando...")
                continue
                
            print(f"\nProcesando idea {i} para PDF: {idea_text[:50]}...")
            
            # Limpiar texto para evitar problemas con caracteres especiales
            idea_text = clean_text_for_pdf(idea_text)
            
            # Separar título y contenido descriptivo
            # Buscamos un doble salto de línea que separe título de contenido
            if "\n\n" in idea_text:
                parts = idea_text.split("\n\n", 1)
                title = parts[0].strip()
                description = parts[1].strip()
                print(f"  ✓ Título original: '{title[:50]}...'")
                print(f"  ✓ Descripción encontrada: '{description[:50]}...'")
            else:
                # Si no hay doble salto, podría ser que solo tengamos título
                if "\n" in idea_text:
                    parts = idea_text.split("\n", 1)
                    title = parts[0].strip()
                    description = parts[1].strip()
                    print(f"  ✓ Título original (primera línea): '{title[:50]}...'")
                    print(f"  ✓ Descripción (resto): '{description[:50]}...'")
                else:
                    # Si no hay ningún salto, todo es título sin descripción
                    title = idea_text
                    description = ""
                    print(f"  ⚠️ Solo título, sin descripción: '{title[:50]}...'")
            
            # Asegurarse de que el título no contenga marcadores
            # Limpiar posibles restos de "Descripción general" en el título
            title = re.sub(r'\s*-\s*Descripción\s+general.*$', '', title, flags=re.IGNORECASE)
            
            # Si no es la primera idea, agregar un separador
            if i > 1:
                pdf.ln(10)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(10)
            
            # TÍTULO: Mostrar con formato destacado y NUMERADO
            pdf.set_font('Arial', 'B', 16)
            pdf.set_text_color(*secondary_color)
            
            # IMPORTANTE: Numerar las ideas secuencialmente como "Idea 1", "Idea 2", etc.
            numbered_title = f"Idea {i}: {title}"
            
            # Usar multi_cell para manejar títulos largos
            pdf.multi_cell(0, 8, numbered_title, align='L')
            pdf.ln(5)
            
            # CONTENIDO DESCRIPTIVO: Mostrar con formato normal (si existe)
            if description:
                pdf.set_font('Arial', '', 12)
                pdf.set_text_color(60, 60, 60)
                pdf.multi_cell(0, 8, description)
                print(f"  ✓ Agregada descripción al PDF: '{description[:50]}...'")
            else:
                pdf.set_font('Arial', 'I', 11)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(0, 8, "(No hay descripción detallada disponible para esta idea)")
                print(f"  ⚠️ Idea {i} no tiene descripción - se ha añadido un mensaje informativo")
            
            # Análisis (si existe)
            analysis_text = idea.get('analysis')
            if analysis_text and str(analysis_text).strip():
                # Limpiar texto del análisis
                analysis_text = clean_text_for_pdf(str(analysis_text))
                
                pdf.ln(5)
                pdf.set_font('Arial', 'B', 14)
                pdf.set_text_color(*accent_color)
                pdf.cell(0, 10, "ANÁLISIS:", ln=True)
                
                pdf.set_font('Arial', '', 12)
                pdf.set_text_color(60, 60, 60)
                pdf.multi_cell(0, 8, analysis_text)
                print(f"  ✓ Agregado análisis al PDF")
            
            # Pie de página en cada página
            pdf.set_y(-15)
            pdf.set_font('Arial', 'I', 8)
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 10, f"Página {pdf.page_no()}", align='R')
        
        # Guardar PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"ideas_{timestamp}.pdf")
        
        try:
            pdf.output(pdf_path)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF generado correctamente: {pdf_path}")
                return pdf_path
            else:
                print("❌ Error: El archivo PDF no se generó correctamente")
                return None
        except Exception as e:
            print(f"❌ Error guardando PDF: {str(e)}")
            traceback.print_exc()
            
            # Intento de recuperación: crear PDF más simple con solo ASCII
            try:
                print("⚠️ Intentando generar PDF más simple...")
                pdf_simple = FPDF()
                pdf_simple.add_page()
                pdf_simple.set_auto_page_break(auto=True, margin=15)
                pdf_simple.set_font('Arial', 'B', 16)
                pdf_simple.cell(0, 10, "IDEAS PROCESADAS (VERSION SIMPLE)", ln=True, align='C')
                pdf_simple.ln(10)
                
                # Añadir ideas en formato simplificado
                for i, idea in enumerate(ideas, 1):
                    if not isinstance(idea, dict):
                        continue
                    
                    # Extraer y limpiar el texto
                    idea_text = str(idea.get('idea', '')).strip()
                    # Limpiar más agresivamente
                    idea_text = ''.join(c for c in idea_text if ord(c) < 128)
                    
                    # Dividir título y contenido si es posible
                    if "\n\n" in idea_text:
                        parts = idea_text.split("\n\n", 1)
                        title = parts[0].strip()
                        description = parts[1].strip()
                        # Añadir idea con formato simple, numerada
                        pdf_simple.ln(5)
                        pdf_simple.set_font('Arial', 'B', 12)
                        pdf_simple.multi_cell(0, 8, f"Idea {i}: {title}")
                        pdf_simple.ln(3)
                        pdf_simple.set_font('Arial', '', 10)
                        pdf_simple.multi_cell(0, 8, description)
                    elif "\n" in idea_text:
                        parts = idea_text.split("\n", 1)
                        title = parts[0].strip()
                        description = parts[1].strip()
                        # Añadir idea con formato simple, numerada
                        pdf_simple.ln(5)
                        pdf_simple.set_font('Arial', 'B', 12)
                        pdf_simple.multi_cell(0, 8, f"Idea {i}: {title}")
                        pdf_simple.ln(3)
                        pdf_simple.set_font('Arial', '', 10)
                        pdf_simple.multi_cell(0, 8, description)
                    else:
                        title = idea_text[:50] + "..." if len(idea_text) > 50 else idea_text
                        # Añadir idea con formato simple, numerada
                        pdf_simple.ln(5)
                        pdf_simple.set_font('Arial', 'B', 12)
                        pdf_simple.multi_cell(0, 8, f"Idea {i}: {title}")
                
                # Guardar versión simple
                simple_pdf_path = os.path.join(output_dir, f"ideas_simple_{timestamp}.pdf")
                pdf_simple.output(simple_pdf_path)
                print(f"✅ PDF simple generado como alternativa: {simple_pdf_path}")
                return simple_pdf_path
            except Exception as e2:
                print(f"❌ Error generando PDF simple: {str(e2)}")
                return None
            
    except Exception as e:
        print(f"❌ Error generando PDF: {str(e)}")
        traceback.print_exc()
        return None

def analyze_ideas(ideas, analysis_points=None):
    """
    Analiza un conjunto de ideas usando OpenAI para generar insights detallados.
    El análisis se personaliza según los puntos seleccionados por el usuario.
    
    Args:
        ideas (list): Lista de ideas a analizar
        analysis_points (list): Lista de puntos de análisis seleccionados por el usuario
                              Ejemplo: ["tendencias", "oportunidades", "riesgos", "recomendaciones"]
    
    Returns:
        tuple: (texto_analisis, error) o (None, mensaje_error)
    """
    if not ideas:
        return None, "No hay ideas para analizar"
        
    # Puntos de análisis por defecto si no se especifican
    if not analysis_points:
        analysis_points = [
            "resumen_ejecutivo",
            "temas_principales",
            "tendencias",
            "oportunidades",
            "riesgos",
            "recomendaciones"
        ]
    
    try:
        # Construir el prompt dinámicamente basado en los puntos seleccionados
        prompt_sections = []
        
        # Sección de análisis general
        if "resumen_ejecutivo" in analysis_points or "temas_principales" in analysis_points:
            prompt_sections.append("ANÁLISIS GENERAL:")
            if "resumen_ejecutivo" in analysis_points:
                prompt_sections.append("- Resumen ejecutivo (máximo 3 líneas)")
            if "temas_principales" in analysis_points:
                prompt_sections.append("- Temas principales identificados")
        
        # Sección de análisis detallado
        if any(point in analysis_points for point in ["tendencias", "oportunidades", "riesgos"]):
            prompt_sections.append("\nANÁLISIS DETALLADO:")
            if "tendencias" in analysis_points:
                prompt_sections.append("- Tendencias y patrones observados")
            if "oportunidades" in analysis_points:
                prompt_sections.append("- Oportunidades identificadas")
            if "riesgos" in analysis_points:
                prompt_sections.append("- Riesgos y desafíos potenciales")
        
        # Sección de recomendaciones
        if "recomendaciones" in analysis_points:
            prompt_sections.append("\nRECOMENDACIONES:")
            prompt_sections.append("- Acciones prioritarias")
            prompt_sections.append("- Siguientes pasos")
            prompt_sections.append("- Áreas de investigación")
        
        # Construir el prompt final
        prompt = f"""
        Analiza en detalle el siguiente conjunto de ideas. Sigue estrictamente este formato:

        {chr(10).join(prompt_sections)}

        INSTRUCCIONES:
        - Máximo 1000 palabras en total
        - Formato estructurado y claro
        - Sin información adicional no solicitada
        - Enfócate solo en los puntos solicitados

        Ideas a analizar:
        {json.dumps(ideas, ensure_ascii=False, indent=2)}
        """
        
        # Configuración de la llamada a OpenAI
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "system", 
                    "content": "Eres un analista experto en innovación y gestión de ideas. Analiza el contenido de forma estructurada y profesional, enfocándote solo en los puntos solicitados."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
            top_p=0.95,
            frequency_penalty=0.5,
            presence_penalty=0.5
        )
        
        # Validar y procesar la respuesta
        if not response or not response.choices:
            return None, "Error en la respuesta de OpenAI"
            
        analysis_text = response.choices[0].message.content.strip()
        
        # Validar que se incluyeron todas las secciones solicitadas
        for section in prompt_sections:
            if section.endswith(":"):  # Solo verificar secciones principales
                if section not in analysis_text:
                    return None, f"Error: Falta la sección {section} en el análisis"
        
        return analysis_text, None
        
    except Exception as e:
        print(f"❌ Error en el análisis: {str(e)}")
        return None, f"Error en el análisis: {str(e)}"

def generate_ai_only_competition_pdf(report_dict, output_name="informe_competencia_ai_only.pdf"):
    """
    Genera un PDF profesional a partir del informe AI-only, usando la estética del ranking (logo, colores, fuentes, portada, disclaimers).
    """
    import os
    from datetime import datetime
    from fpdf import FPDF
    # --- Clase PDF con header/footer ---
    class PDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                try:
                    logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
                    for logo_path in logo_paths:
                        if os.path.exists(logo_path):
                            self.image(logo_path, 10, 8, 33)
                            break
                except:
                    pass
                self.set_font('Helvetica', 'B', 12)
                self.cell(0, 10, 'Informe de Competencia y Vigilancia Tecnológica', 0, 1, 'C')
                self.ln(5)
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Página {self.page_no()}  |  Fuente: IA generativa OpenAI • confidencial', 0, 0, 'C')
    # --- Inicializar PDF ---
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    # --- Fuente principal ---
    try:
        pdf.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
        pdf.add_font('DejaVu', 'B', 'DejaVuSansCondensed-Bold.ttf', uni=True)
        font_family = 'DejaVu'
    except:
        font_family = 'Helvetica'
    # --- Portada ---
    try:
        logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                logo_width = 80
                logo_x = (210 - logo_width) / 2
                pdf.image(logo_path, x=logo_x, y=40, w=logo_width)
                break
    except Exception as e:
        pass
    pdf.set_font(font_family, 'B', 24)
    pdf.set_text_color(44, 62, 80)
    pdf.ln(130)
    pdf.cell(0, 20, 'INFORME DE COMPETENCIA Y VIGILANCIA TECNOLÓGICA', ln=True, align='C')
    pdf.set_font(font_family, '', 16)
    pdf.cell(0, 10, 'Generado por IA (sin scraping web)', ln=True, align='C')
    pdf.ln(20)
    pdf.set_font(font_family, '', 12)
    pdf.set_text_color(100, 100, 100)
    fecha = report_dict.get('metadatos', {}).get('fecha_generacion', datetime.now().strftime("%d/%m/%Y"))
    pdf.cell(0, 10, f'Fecha: {fecha}', ln=True, align='C')
    pdf.cell(0, 10, f'Modelo: {report_dict.get("metadatos", {}).get("modelo", "openai")}', ln=True, align='C')
    pdf.ln(10)
    pdf.set_font(font_family, '', 11)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 8, 'Este informe ha sido generado íntegramente por IA, sin fuentes externas ni scraping web. Para uso interno y confidencial.')
    # --- Tabla de contenidos ---
    pdf.add_page()
    pdf.set_font(font_family, 'B', 16)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, 'Tabla de Contenidos', ln=True)
    pdf.ln(5)
    pdf.set_font(font_family, '', 12)
    pdf.set_text_color(0, 0, 0)
    secciones = [
        ('EXEC_SUMMARY', 'Resumen Ejecutivo'),
        ('COMPETITOR_MAPPING', 'Mapeo Competitivo'),
        ('BENCHMARK_MATRIX', 'Benchmarking'),
        ('TECH_IP_LANDSCAPE', 'Tecnología & Patentes'),
        ('MARKET_ANALYSIS', 'Tamaño y Tendencias'),
        ('SWOT_POSITIONING', 'SWOT y Posicionamiento'),
        ('REGULATORY_ESG_RISK', 'Marco Regulatorio y ESG'),
        ('STRATEGIC_ROADMAP', 'Roadmap Estratégico'),
        ('APPENDIX', 'Glosario y Metodología')
    ]
    toc_pages = {}
    for sec_id, sec_title in secciones:
        toc_pages[sec_id] = pdf.page_no() + 1  # Estimación, se actualizará después si se quiere
        pdf.cell(0, 8, f'{sec_title}', ln=True)
    # --- Una página por sección ---
    for sec_id, sec_title in secciones:
        pdf.add_page()
        pdf.set_font(font_family, 'B', 16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, sec_title, ln=True)
        pdf.ln(5)
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(0, 0, 0)
        sec_data = report_dict.get(sec_id, {})
        # Mostrar el contenido de la sección de forma estructurada
        if isinstance(sec_data, dict):
            for k, v in sec_data.items():
                if isinstance(v, (str, int, float)):
                    pdf.set_font(font_family, 'B', 12)
                    pdf.cell(0, 8, f'{k.capitalize()}:', ln=True)
                    pdf.set_font(font_family, '', 12)
                    pdf.multi_cell(0, 7, str(v))
                    pdf.ln(2)
                elif isinstance(v, list):
                    pdf.set_font(font_family, 'B', 12)
                    pdf.cell(0, 8, f'{k.capitalize()}:', ln=True)
                    pdf.set_font(font_family, '', 12)
                    for item in v:
                        if isinstance(item, dict):
                            for subk, subv in item.items():
                                pdf.set_font(font_family, 'I', 11)
                                pdf.cell(0, 6, f'  - {subk.capitalize()}: {subv}', ln=True)
                            pdf.ln(1)
                        else:
                            pdf.cell(0, 6, f'  - {item}', ln=True)
                    pdf.ln(2)
                elif isinstance(v, dict):
                    pdf.set_font(font_family, 'B', 12)
                    pdf.cell(0, 8, f'{k.capitalize()}:', ln=True)
                    pdf.set_font(font_family, '', 12)
                    for subk, subv in v.items():
                        pdf.cell(0, 6, f'  - {subk.capitalize()}: {subv}', ln=True)
                    pdf.ln(2)
        elif isinstance(sec_data, str):
            pdf.multi_cell(0, 7, sec_data)
        else:
            pdf.cell(0, 7, 'Sin datos.', ln=True)
        pdf.ln(5)
    # --- Guardar PDF ---
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, output_name)
    try:
        pdf.output(pdf_path)
    except Exception as e:
        # Fallback a Helvetica si hay error de fuente
        try:
            pdf.set_font('Helvetica', '', 12)
            pdf.output(pdf_path)
        except Exception as e2:
            print(f"❌ Error generando PDF: {e2}")
            return None
    return pdf_path 
import openai
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
from fpdf import FPDF
import tempfile
import os
from datetime import datetime
import numpy as np
import json
import base64
# IMPORTACIÓN REMOVIDA: from pdf_processor_module import generate_robust_pdf
# Se usará función interna para evitar dependencias circulares
import traceback
import random
import time
import concurrent.futures
from tqdm import tqdm
import hashlib
from typing import List, Dict, Any
from pathlib import Path

# Asegurarnos de que matplotlib use un backend que no requiera pantalla
import matplotlib
matplotlib.use('Agg')

# Importar configuración de OpenAI
try:
    from openai_config import get_openai_client, get_deployment_name
    client = get_openai_client()
    DEPLOYMENT_NAME = get_deployment_name()
    USING_NEW_CLIENT = True
    print("✅ Usando OpenAI Client desde openai_config")
except ImportError:
    try:
        from openai import OpenAI
        client = OpenAI()
        USING_NEW_CLIENT = True
        DEPLOYMENT_NAME = "gpt-4-turbo-preview"
        print("✅ Usando OpenAI Client moderno directamente")
    except:
        USING_NEW_CLIENT = False
        DEPLOYMENT_NAME = "gpt-4-turbo-preview"
        print("⚠️ Usando OpenAI legacy client")

def obtener_respuesta(messages, deployment_name, max_tokens=800, temperature=0.2):
    try:
        if USING_NEW_CLIENT and client:
            response = client.chat.completions.create(
                model=deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=60
            )
            return response.choices[0].message.content.strip()
        else:
            response = openai.ChatCompletion.create(
                engine=deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ Error en obtener_respuesta: {str(e)}")
        traceback.print_exc()
        return f"Error al obtener respuesta: {str(e)}"

def obtener_parametros_tecnicos(idea, analisis_previo, context_sener, deployment_name):
    try:
        messages_payload = [
            {
                "role": "system",
                "content": (
                    "Eres un consultor experto en tecnología e innovación en SENER. "
                    "Analiza la idea y el análisis previo y estima profesionalmente los parámetros técnicos. "
                    "Incluye la línea EXACTA: \"Ubicación en la Payoff Matrix: (X, Y)\"."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Contexto de SENER:\n{context_sener}\n\n"
                    f"Idea:\n{idea}\n\n"
                    f"Análisis Previo:\n{analisis_previo}\n\n"
                    "Finaliza tu respuesta con la línea EXACTA:\n"
                    "\"Ubicación en la Payoff Matrix: (X, Y)\""
                )
            }
        ]
        response = obtener_respuesta(messages_payload, deployment_name, max_tokens=800)
        return response
    except Exception as e:
        return f"Error obteniendo parámetros: {str(e)}"

def ranking_priorizacion(lista_ideas, context_sener, deployment_name):
    try:
        ideas_info = ""
        for i, idea_dict in enumerate(lista_ideas, start=1):
            ideas_info += (
                f"Idea #{i}: {idea_dict['nombre']}\n"
                f"Parametros:\n{idea_dict['parametros']}\n"
                f"Análisis previo:\n{idea_dict['analisis_previo']}\n\n"
            )

        messages_payload = [
            {
                "role": "system",
                "content": (
                    "Eres un consultor estratégico en SENER. "
                    "Genera un ranking priorizando los proyectos según los parámetros y análisis."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Contexto de SENER:\n{context_sener}\n\n"
                    "Lista de ideas:\n"
                    f"{ideas_info}\n\n"
                    "Genera el ranking final."
                )
            }
        ]
        response = obtener_respuesta(messages_payload, deployment_name, max_tokens=1200)
        return response
    except Exception as e:
        return f"Error generando ranking: {str(e)}"

def graficar_payoff_matrix(lista_ideas):
    data = []
    for idea in lista_ideas:
        # Usar directamente los valores de effort y benefit calculados por calculate_payoff_matrix_values
        if 'effort' in idea and 'benefit' in idea:
            # Convertir la escala 0-100 a 0-10 para mantener compatibilidad con código existente
            x = round(idea['effort'] / 10)
            y = round(idea['benefit'] / 10)
            # Asegurar que los valores están en el rango 0-10
            x = min(10, max(0, x))
            y = min(10, max(0, y))
            
            title = idea.get('title', idea.get('nombre', ''))
            data.append({"Proyecto": title, "X": x, "Y": y})
        else:
            # Fallback a búsqueda en parametros si no hay valores calculados
            parametros = idea.get("parametros", "")
            match = re.search(r'Ubicación en la Payoff Matrix:\s*\((\d+),\s*(\d+)\)', parametros, re.IGNORECASE)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                data.append({"Proyecto": idea.get("nombre", ""), "X": x, "Y": y})
    
    if not data:
        return None, None
    df = pd.DataFrame(data)
    sns.set_style("whitegrid")
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    rect_q1 = plt.Rectangle((0, 5), 5, 5, color='#b3ffb3', alpha=0.3)
    rect_q2 = plt.Rectangle((5, 5), 5, 5, color='#ffcccc', alpha=0.3)
    rect_q3 = plt.Rectangle((0, 0), 5, 5, color='#cce0ff', alpha=0.3)
    rect_q4 = plt.Rectangle((5, 0), 5, 5, color='#ffffcc', alpha=0.3)
    ax.add_patch(rect_q1)
    ax.add_patch(rect_q2)
    ax.add_patch(rect_q3)
    ax.add_patch(rect_q4)
    ax.axvline(5, color='black', linestyle='--', linewidth=1)
    ax.axhline(5, color='black', linestyle='--', linewidth=1)
    ax.text(2.5, 7.5, "Quick Win!", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(7.5, 7.5, "Do we have\ntime & money?", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(2.5, 2.5, "Improvements", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(7.5, 2.5, "Kill it!", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.set_xlabel("Effort (Low → High)", fontsize=12)
    ax.set_ylabel("Benefit (Low → High)", fontsize=12)
    ax.set_title("Payoff Matrix de Proyectos", fontsize=16, fontweight='bold', pad=20)
    for _, row in df.iterrows():
        label = row["Proyecto"]
        ax.scatter(row["X"], row["Y"], color='blue', s=60, edgecolors='black', linewidth=0.5)
        ax.annotate(label, (row["X"], row["Y"]), textcoords="offset points", xytext=(5, 5),
                    ha='left', fontsize=10, color='blue')
    return fig, df

def generar_pdf_payoff(fig, ranking_text, lista_ideas):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Ranking Final y Payoff Matrix", ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 5, ranking_text)
        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Leyenda de Ideas:", ln=True)
        pdf.set_font("Arial", size=12)
        for idea in lista_ideas:
            pdf.cell(0, 5, f"{idea['nombre']}: {idea['idea'][:60]}...", ln=True)
        pdf.ln(5)
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(img_buffer.getbuffer())
            tmp_filename = tmp_file.name
        pdf.image(tmp_filename, x=10, y=pdf.get_y()+5, w=pdf.w - 20)
        pdf_output = pdf.output(dest="S").encode("latin1")
        pdf_buffer = BytesIO(pdf_output)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        return f"Error generando PDF: {str(e)}"

def analyze_idea_for_ranking(idea):
    """
    Analiza una idea individual para el ranking basándose en criterios de consultor experto
    """
    prompt = f"""
    Como consultor experto en innovación tecnológica, analiza la siguiente idea para SENER:
    
    Idea: {idea}
    
    Analiza la idea considerando:
    1. Potencial de implementación inmediata (0-40 puntos)
    2. Alineación con partners tecnológicos estratégicos (0-30 puntos)
    3. Potencial de impacto a largo plazo (0-30 puntos)
    
    Proporciona:
    - Puntuación total (0-100)
    - Análisis detallado de cada criterio
    - Partners tecnológicos recomendados
    - Recomendaciones de implementación
    """
    
    try:
        response = openai.ChatCompletion.create(
            engine=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un consultor experto en innovación tecnológica para SENER."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error en el análisis: {str(e)}"

def extract_metrics_from_analysis(analysis_text, idea_text="", ranking_context=""):
    """
    Extrae métricas cuantitativas y cualitativas del análisis de una idea.
    
    Esta función analiza el texto de análisis para encontrar métricas específicas mencionadas
    y extrae sus valores basándose en evidencia textual, no en valores aleatorios o inventados.
    
    Las métricas están divididas en tres dimensiones de igual peso (33,3% cada una):
    - Dimensión Técnica: riesgo_técnico, tiempo_desarrollo, progreso_TRL
    - Dimensión Económica: ratio_costes_ingresos, ingresos_previstos, payback_ROI
    - Dimensión de Mercado: tamaño_mercado, riesgo_mercado, alineacion_estrategica
    """
    # Métricas por defecto - valores neutros para casos donde no se pueda extraer información
    default_metrics = {
        # Dimensión Técnica
        'riesgo_tecnico': 3,
        'tiempo_desarrollo': 3,
        'trl_inicial': 3,
        'trl_final': 6,
        
        # Dimensión Económica
        'ratio_costes_ingresos': 3,
        'ingresos_previstos': 3,
        'payback_roi': 3,
        
        # Dimensión de Mercado
        'tamano_mercado': 3,
        'riesgo_mercado': 3,
        'alineacion_estrategica': 3,
        
        # Evaluación cualitativa (se mantiene para compatibilidad)
        'evaluacion_cualitativa': 3
    }
    
    # Verificar si tenemos un análisis válido
    if not analysis_text:
        print(f"⚠️ No se proporcionó texto de análisis")
        return default_metrics
        
    if not isinstance(analysis_text, str):
        try:
            # Intentar convertir a string si es posible
            analysis_text = str(analysis_text)
        except:
            print(f"⚠️ El análisis no es un texto válido")
            return default_metrics
    
    if len(analysis_text.strip()) < 100:
        print(f"⚠️ Análisis demasiado corto ({len(analysis_text.strip())} caracteres)")
        return default_metrics
    
    # Sanitizar el texto del análisis para evitar problemas de formato
    safe_analysis_text = analysis_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
    
    # Extraer un resumen del texto de la idea para incluirlo en el prompt
    idea_summary = ""
    if idea_text:
        if isinstance(idea_text, str):
            # Sanitizar el texto de la idea
            safe_idea_text = idea_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            idea_summary = safe_idea_text[:300]
        else:
            try:
                idea_summary = str(idea_text)[:300]
            except:
                idea_summary = ""
    
    # Resumen del contexto de priorización
    context_summary = ""
    if ranking_context:
        if isinstance(ranking_context, str):
            # Sanitizar el contexto
            safe_context = ranking_context.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            context_summary = safe_context[:300]
        else:
            try:
                context_summary = str(ranking_context)[:300]
            except:
                context_summary = ""
    
    # Limpiar el texto para el procesamiento
    clean_analysis = safe_analysis_text.replace('\r', ' ').replace('\n\n', '\n').strip()
    
    # ID único para esta evaluación
    evaluation_id = f"metrics_extract_{int(time.time())}_{random.randint(1000, 9999)}"
    
    prompt = f"""
    EVALUACIÓN ID: {evaluation_id}
    
    Como analista especializado en evaluación de proyectos de innovación, tu tarea es extraer métricas cuantitativas de la siguiente idea y su análisis detallado.
    Debes basarte ÚNICAMENTE en lo que está explícitamente mencionado o puede inferirse razonablemente del texto.
    
    CONTEXTO DE SENER:
    {context_summary}
    
    IDEA A EVALUAR:
    {idea_summary}
    
    ANÁLISIS DETALLADO:
    {clean_analysis}
    
    INSTRUCCIONES CRÍTICAS:
    - EXTRAE los valores de las métricas basándote EXCLUSIVAMENTE en la evidencia textual del análisis.
    - Antes de valorar cada métrica, INCLUYE SIEMPRE el contexto completo de SENER, los objetivos estratégicos y el análisis detallado de la idea.
    - NO INVENTES ni generes valores aleatorios. Si falta información, asigna un valor neutral (3).
    - Para cada métrica, proporciona un breve fragmento de texto del análisis que respalde tu valoración.
    - Sé OBJETIVO y PRECISO, manteniendo una temperatura baja en tu evaluación.
    - IMPORTANTE: Todas las métricas en escala 1-5 pueden usar valores decimales (por ejemplo: 3.75, 4.2, 2.8) para una evaluación más precisa.
    
    MÉTRICAS A EXTRAER (todas en escala 1-5 con decimales permitidos, excepto TRL que es 1-9 entero):
    
    DIMENSIÓN TÉCNICA (33,3% del componente cuantitativo):
    1. riesgo_tecnico (1.0 = viabilidad dudosa, 5.0 = tecnología probada)
       - Evalúa el riesgo tecnológico según la viabilidad y madurez
       - Permite valores decimales para reflejar matices en la evaluación
       
    2. tiempo_desarrollo (1.0 = >3 años, 5.0 = <6 meses)
       - Evalúa el tiempo necesario para completar el desarrollo
       - Permite valores decimales para reflejar estimaciones más precisas
       
    3. trl_inicial (1-9, Nivel actual de Preparación Tecnológica)
       - Nivel actual de madurez tecnológica (TRL)
       - Solo valores enteros
       
    4. trl_final (1-9, Nivel de Preparación Tecnológica esperado)
       - Nivel de madurez tecnológica esperado tras el desarrollo
       - Solo valores enteros
       
    DIMENSIÓN ECONÓMICA (33,3% del componente cuantitativo):
    5. ratio_costes_ingresos (1.0 = >75%, 5.0 = <10%)
       - Proporción entre costes operativos e ingresos
       - Permite valores decimales para reflejar proporciones específicas
       
    6. ingresos_previstos (1.0 = <0,5 M€, 5.0 = >20 M€)
       - Volumen de ingresos esperados
       - Permite valores decimales para ajustes más precisos
       
    7. payback_roi (1.0 = retorno >5 años, 5.0 = retorno <1 año)
       - Período de recuperación de la inversión
       - Permite valores decimales para períodos intermedios
       
    DIMENSIÓN DE MERCADO (33,3% del componente cuantitativo):
    8. tamano_mercado (1.0 = TAM <0,5 B€, 5.0 = TAM >10 B€)
       - Tamaño total del mercado direccionable
       - Permite valores decimales para mercados intermedios
       
    9. riesgo_mercado (1.0 = riesgo ALTO, 5.0 = riesgo BAJO)
       - Nivel de riesgo en la entrada al mercado
       - 1.0-2.0: Riesgo ALTO - Barreras significativas, adopción lenta
       - 2.1-3.9: Riesgo MEDIO - Barreras moderadas, adopción media
       - 4.0-5.0: Riesgo BAJO - Barreras mínimas, adopción rápida
       - Permite valores decimales para una evaluación más granular
       
    10. alineacion_estrategica (1.0 = baja sinergia SENER, 5.0 = encaje perfecto)
        - Grado de alineación con la estrategia de SENER
        - Permite valores decimales para reflejar niveles intermedios de alineación
    
    11. evaluacion_cualitativa (5.0 = excelente, 1.0 = pobre)
        - Evaluación general basada en todos los aspectos analizados
        - Permite valores decimales para una evaluación más matizada
    
    FORMATO DE RESPUESTA:
    Responde ÚNICAMENTE con un objeto JSON que contenga:
    1. Las métricas con sus valores numéricos (usando decimales cuando sea apropiado)
    2. Una breve justificación para cada métrica basada en el texto (max 1-2 oraciones)
    
    Por ejemplo:
    {{
        "riesgo_tecnico": 3.75,
        "tiempo_desarrollo": 2.8,
        ...
        "justificacion": {{
            "riesgo_tecnico": "Tecnología probada pero con desafíos de integración específicos.",
            ...
        }}
    }}
    """
    
    try:
        # Usar el cliente de OpenAI importado
        try:
            # Usar client.chat.completions
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Eres un consultor especializado en extraer métricas objetivas de análisis técnicos y de negocio. Tu trabajo es identificar valores basados ÚNICAMENTE en el texto proporcionado, sin inventar información. Mantienes una temperatura baja para asegurar evaluaciones objetivas y precisas."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Temperatura muy baja para mayor consistencia y precisión
                max_tokens=1500,
                response_format={"type": "json_object"},
                timeout=60
            )
            
            if response and response.choices and response.choices[0].message:
                metrics_text = response.choices[0].message.content.strip()
            else:
                print("⚠️ Respuesta vacía de la API")
                return default_metrics
        except Exception as api_error:
            print(f"❌ Error en la llamada a la API: {str(api_error)}")
            traceback.print_exc()
            return default_metrics
        
        # Limpiar la respuesta para asegurar que sea un JSON válido
        metrics_text = metrics_text.replace('```json', '').replace('```', '').strip()
        
        try:
            metrics_data = json.loads(metrics_text)
            
            # CAMBIO CLAVE: Sanitizar las justificaciones antes de usar
            if 'justificacion' in metrics_data and isinstance(metrics_data['justificacion'], dict):
                for key, value in metrics_data['justificacion'].items():
                    if isinstance(value, str):
                        # Sanitizar cada justificación para prevenir errores de formato
                        metrics_data['justificacion'][key] = value.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
            # Extraer solo las métricas numéricas (sin las justificaciones)
            extracted_metrics = {}
            for key in default_metrics.keys():
                if key in metrics_data:
                    # Convertir a número y validar el rango
                    try:
                        value = float(metrics_data[key])
                        # Validar rangos
                        if key.startswith('trl_'):
                            extracted_metrics[key] = max(1, min(9, value))  # TRL: 1-9
                        else:
                            extracted_metrics[key] = max(1, min(5, value))  # Otras métricas: 1-5
                    except (ValueError, TypeError):
                        extracted_metrics[key] = default_metrics[key]
                else:
                    extracted_metrics[key] = default_metrics[key]
            
            # Para retrocompatibilidad (si se usa el nombre antiguo de la métrica)
            if 'costes_ingresos' in metrics_data and 'ratio_costes_ingresos' not in metrics_data:
                extracted_metrics['ratio_costes_ingresos'] = extracted_metrics.get('costes_ingresos', 3)
            
            # IMPORTANTE: Guardar las justificaciones sanitizadas en las métricas extraídas
            if 'justificacion' in metrics_data and isinstance(metrics_data['justificacion'], dict):
                extracted_metrics['justificacion'] = metrics_data['justificacion']
            
            # Registrar para depuración
            print(f"✅ Métricas extraídas del análisis:")
            for key, value in extracted_metrics.items():
                if key != 'justificacion':
                    justification = "No disponible"
                    if 'justificacion' in extracted_metrics and key in extracted_metrics['justificacion']:
                        justification = extracted_metrics['justificacion'][key]
                print(f"  - {key}: {value} → {justification}")
            
            return extracted_metrics
            
        except json.JSONDecodeError:
            print(f"❌ Error decodificando JSON: {metrics_text}")
            # Intentar extraer métricas mediante regex como fallback
            extracted_metrics = default_metrics.copy()
            
            try:
                # Buscar pares clave-valor en el texto
                pattern = r'"([^"]+)":\s*(\d+\.?\d*)'
                matches = re.findall(pattern, metrics_text)
                
                for key, value_str in matches:
                    if key in default_metrics:
                        value = float(value_str)
                        # Validar rangos
                        if key.startswith('trl_'):
                            extracted_metrics[key] = max(1, min(9, value))
                        else:
                            extracted_metrics[key] = max(1, min(5, value))
                
                return extracted_metrics
            except:
                print("❌ Falló la extracción de respaldo mediante regex")
                return default_metrics
                
    except Exception as e:
        print(f"❌ Error general extrayendo métricas: {str(e)}")
        traceback.print_exc()
        return default_metrics

def calculate_final_score(metrics):
    """
    Calcula la puntuación final basada en las métricas extraídas divididas en tres dimensiones.
    
    50% de la puntuación proviene del análisis cuantitativo (métricas)
    50% proviene de una evaluación cualitativa directa realizada por OpenAI.
    
    El componente cuantitativo se divide en tres dimensiones con igual peso (33,3% cada una):
    - Dimensión Técnica
    - Dimensión Económica 
    - Dimensión de Mercado
    
    Nota: Las métricas en escala 1-5 pueden contener valores decimales para una evaluación más precisa.
    Solo los valores TRL son enteros.
    """
    if not metrics:
        return {'score': 50}  # Puntuación neutra por defecto
    
    try:
        # Calcular el progreso TRL normalizado a escala 1-5
        trl_delta = int(metrics['trl_final']) - int(metrics['trl_inicial'])
        
        # Mapear Δ TRL a escala 1-5 según la tabla de correspondencia
        # Permitimos valores decimales intermedios para casos especiales
        if trl_delta >= 6:
            progreso_trl = 5.0
        elif trl_delta >= 4 and trl_delta <= 5:
            progreso_trl = 4.0 + (trl_delta - 4) * 0.5  # 4.0 - 4.5
        elif trl_delta >= 2 and trl_delta <= 3:
            progreso_trl = 3.0 + (trl_delta - 2) * 0.5  # 3.0 - 3.5
        elif trl_delta == 1:
            progreso_trl = 2.0
        else:  # trl_delta <= 0
            progreso_trl = 1.0
        
        # Dimensión Técnica (media de 3 métricas)
        dimension_tecnica = np.mean([
            float(metrics['riesgo_tecnico']),
            float(metrics['tiempo_desarrollo']),
            float(progreso_trl)
        ])
        
        # Dimensión Económica (media de 3 métricas)
        dimension_economica = np.mean([
            float(metrics.get('ratio_costes_ingresos', metrics.get('costes_ingresos', 3.0))),
            float(metrics['ingresos_previstos']),
            float(metrics.get('payback_roi', 3.0))
        ])
        
        # Dimensión de Mercado (media de 3 métricas)
        dimension_mercado = np.mean([
            float(metrics.get('tamano_mercado', 3.0)),
            float(metrics['riesgo_mercado']),
            float(metrics.get('alineacion_estrategica', 3.0))
        ])
        
        # Normalizar cada dimensión de escala 1-5 a 0-100
        # Usamos valores decimales para mayor precisión
        tech_score_norm = ((dimension_tecnica - 1.0) / 4.0) * 100
        econ_score_norm = ((dimension_economica - 1.0) / 4.0) * 100
        market_score_norm = ((dimension_mercado - 1.0) / 4.0) * 100
        
        # Calcular el score cuantitativo (media de las tres dimensiones)
        score_quantitative = np.mean([tech_score_norm, econ_score_norm, market_score_norm])
        
        # Obtener el score cualitativo (ya normalizado a 0-100)
        score_qualitative = float(metrics.get('evaluacion_cualitativa', 3.0)) * 20  # Convertir de 1-5 a 0-100
        
        # Calcular el score final (50% cuantitativo, 50% cualitativo)
        final_score = (score_quantitative + score_qualitative) / 2
        
        return {
            'score': round(final_score, 1),  # Score final redondeado a 1 decimal
            'score_quantitative': round(score_quantitative, 1),
            'score_qualitative': round(score_qualitative, 1),
            'dimension_tecnica': round(tech_score_norm, 1),
            'dimension_economica': round(econ_score_norm, 1),
            'dimension_mercado': round(market_score_norm, 1)
        }
        
    except Exception as e:
        print(f"Error calculando score: {str(e)}")
        return {'score': 50}  # Valor por defecto en caso de error

def generate_ranking_pdf(ideas, ranking_context):
    """
    🔧 MEJORADO: Genera un PDF con el ranking de ideas sin dependencias externas
    """
    try:
        if not ideas or not isinstance(ideas, list):
            print("❌ No hay ideas para generar ranking PDF")
            return None
            
        # 🔧 USAR FUNCIÓN MEJORADA INTERNA EN LUGAR DE DEPENDENCIA EXTERNA
        return generate_ranking_pdf_improved(ideas, ranking_context)
            
    except Exception as e:
        print(f"❌ Error general: {str(e)}")
        traceback.print_exc()
        return None

def generate_simplified_analysis(idea_text):
    """
    Genera un análisis simplificado de una idea cuando no hay análisis previo
    """
    try:
        # Validar y acortar la idea si es necesario
        if not idea_text or not isinstance(idea_text, str) or len(idea_text.strip()) < 10:
            print("⚠️ Texto de idea no válido para análisis simplificado")
            return "No se pudo generar un análisis para la idea (texto inválido)"
            
        # Acortar la idea si es muy larga para reducir tokens
        shortened_idea = idea_text[:800] + "..." if len(idea_text) > 800 else idea_text
            
        # Generar un ID único para esta evaluación
        eval_id = f"analysis_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Crear una clave única para caché
        cache_key = f"simplified_analysis_{hashlib.md5(shortened_idea.encode()).hexdigest()}"
        
        # Verificar si ya tenemos este resultado en caché
        if cache_key in _api_cache:
            print(f"🔄 Usando análisis en caché")
            return _api_cache[cache_key]
        
        prompt = f"""
        EVALUACIÓN ID: {eval_id}
        
        Como consultor experto en análisis de innovación tecnológica, realiza un análisis conciso pero completo de la siguiente idea:
        
        IDEA: {shortened_idea}
        
        Analiza los siguientes aspectos con profundidad y especificidad:
        
        1. RESUMEN EJECUTIVO: Visión general, impacto potencial, desafíos y oportunidades principales.
        
        2. ANÁLISIS TÉCNICO: Viabilidad técnica, recursos necesarios, complejidades técnicas.
        
        3. POTENCIAL DE INNOVACIÓN: Novedad en el mercado, ventajas competitivas, propiedad intelectual.
        
        4. ALINEACIÓN ESTRATÉGICA: Compatibilidad con mercado de ingeniería, integración con sistemas existentes.
        
        5. VIABILIDAD COMERCIAL: Potencial de mercado, modelo de negocio, ROI estimado.
        
        6. VALORACIÓN GLOBAL: Evaluación ponderada, factores favorables/desfavorables, recomendación.
        
        IMPORTANTE:
        - Estilo profesional y ejecutivo
        - Análisis específico, no genérico
        - Incluir datos cuantitativos cuando sea posible
        - Usar títulos en MAYÚSCULAS para cada sección
        - Ser conciso pero completo
        """
        
        try:
            # Usar client.chat.completions.create en lugar de openai.ChatCompletion
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Eres un consultor analítico sénior especializado en evaluación de ideas innovadoras para empresas tecnológicas e ingenierías avanzadas."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,  # Reducido para optimizar velocidad
                timeout=60
            )
            
            if response and response.choices and response.choices[0].message:
                analysis = response.choices[0].message.content.strip()
                # Guardar en caché
                _api_cache[cache_key] = analysis
                return analysis
            else:
                print("⚠️ Respuesta vacía de la API")
                return f"Error: No se pudo generar el análisis debido a una respuesta vacía"
        except Exception as api_error:
            print(f"❌ Error en la llamada a la API: {str(api_error)}")
            traceback.print_exc()
            return f"Error en la llamada a la API: {str(api_error)}"
            
    except Exception as e:
        print(f"❌ Error generando análisis simplificado: {str(e)}")
        traceback.print_exc()
        return f"Error al generar análisis: {str(e)}"

def generate_qualitative_evaluation(idea_text, analysis_text="", context=""):
    """
    Genera una evaluación cualitativa de una idea que representará el 50% de la puntuación final.
    Esta evaluación se basa en la lectura y comprensión del contexto de la idea.
    
    Retorna una puntuación de 0 a 100 y una justificación de la evaluación.
    Los valores de esfuerzo y beneficio ya no se calculan aquí, sino en una función separada.
    """
    try:
        # Validar la entrada
        if not idea_text or not isinstance(idea_text, str) or len(idea_text.strip()) < 10:
            print("⚠️ Texto de idea no válido para evaluación cualitativa")
            return {
                "score": 50, 
                "justification": "No se pudo evaluar (texto inválido)"
            }
        
        # Crear una clave única para caché
        cache_key = f"qual_eval_{hashlib.md5((idea_text[:300] + (analysis_text[:300] if analysis_text else '') + (context[:100] if context else '')).encode()).hexdigest()}"
        
        # Verificar si ya tenemos este resultado en caché
        if cache_key in _api_cache:
            print(f"🔄 Usando evaluación cualitativa en caché")
            return _api_cache[cache_key]
            
        # Acortar textos si son demasiado largos para reducir tokens
        shortened_idea = idea_text[:500] + "..." if len(idea_text) > 500 else idea_text
        shortened_analysis = ""
        
        if analysis_text and isinstance(analysis_text, str) and len(analysis_text.strip()) > 100:
            # Extraer solo las partes más relevantes del análisis
            sections = ["RESUMEN EJECUTIVO", "VALORACIÓN GLOBAL", "VIABILIDAD COMERCIAL"]
            extracted = []
            
            for section in sections:
                pattern = f"{section}.*?(?=\n\n|$)"
                matches = re.findall(pattern, analysis_text, re.DOTALL | re.IGNORECASE)
                if matches:
                    extracted.append(matches[0][:200])
            
            if extracted:
                shortened_analysis = "\n\n".join(extracted)
            else:
                shortened_analysis = analysis_text[:500] + "..." if len(analysis_text) > 500 else analysis_text
        
        # Incluir contexto si existe, acortado
        context_text = f"\nCONTEXTO DE PRIORIZACIÓN:\n{context[:300]}\n\n" if context and len(context.strip()) > 5 else ""
        
        # ID único para esta evaluación
        eval_id = f"qual_eval_{int(time.time())}_{random.randint(1000, 9999)}"
        
        prompt = f"""
        EVALUACIÓN ID: {eval_id}
        
        Como consultor experto en evaluación de ideas innovadoras, realiza una evaluación cualitativa 
        de la siguiente idea, que representará el 50% de su puntuación final de ranking.
        
        IDEA:
        {shortened_idea}
        {context_text}
        {shortened_analysis if shortened_analysis else ""}
        
        INSTRUCCIONES:
        1. Evalúa la calidad, innovación, viabilidad y potencial de la idea.
        2. Asigna una puntuación de 0 a 100, donde:
           - 0-20: Idea muy pobre o inviable
           - 21-40: Idea con problemas significativos
           - 41-60: Idea de calidad media
           - 61-80: Idea buena con potencial
           - 81-100: Idea excepcional de alto potencial
        3. Proporciona una justificación breve pero fundamentada de tu evaluación.
        
        FORMATO DE RESPUESTA:
        Responde en formato JSON con la siguiente estructura exacta:
        {{
          "score": [puntuación de 0 a 100],
          "justification": "[justificación detallada]"
        }}
        """
        
        try:
            # Usar el cliente de OpenAI importado
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Eres un consultor experto en evaluación de ideas innovadoras con amplia experiencia en priorización de proyectos de tecnología, ingeniería y ciencia."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,  # Reducimos la temperatura para mayor consistencia
                max_tokens=800,  # Reducido para optimizar
                response_format={"type": "json_object"},  # Forzar formato JSON
                timeout=60
            )
            
            if response and response.choices and response.choices[0].message:
                result_text = response.choices[0].message.content.strip()
                
                try:
                    # Limpiar texto y convertir a JSON
                    result_text = result_text.replace('```json', '').replace('```', '').strip()
                    result = json.loads(result_text)
                    
                    # Validar los campos requeridos
                    if "score" not in result or "justification" not in result:
                        print("⚠️ Respuesta de la API no contiene todos los campos necesarios")
                        return {
                            "score": 50, 
                            "justification": "Error: Respuesta incompleta"
                        }
                    
                    # Validar rango de la puntuación
                    score = float(result["score"])
                    if score < 0 or score > 100:
                        print(f"⚠️ Puntuación fuera de rango: {score}, ajustando")
                        score = max(0, min(100, score))
                    
                    final_result = {
                        "score": score,
                        "justification": result["justification"]
                    }
                    
                    # Guardar en caché
                    _api_cache[cache_key] = final_result
                    
                    return final_result
                except json.JSONDecodeError:
                    print(f"❌ Error decodificando JSON: {result_text}")
                    # Intentar extraer valores mediante regex
                    score_match = re.search(r'"score":\s*(\d+\.?\d*)', result_text)
                    if score_match:
                        score = float(score_match.group(1))
                        # Extraer justificación con regex
                        justification_match = re.search(r'"justification":\s*"([^"]*)"', result_text)
                        justification = justification_match.group(1) if justification_match else "Error al extraer justificación"
                        
                        # Intentar extraer esfuerzo y beneficio
                        effort_match = re.search(r'"effort":\s*(\d+\.?\d*)', result_text)
                        effort = float(effort_match.group(1)) if effort_match else 50
                        
                        benefit_match = re.search(r'"benefit":\s*(\d+\.?\d*)', result_text)
                        benefit = float(benefit_match.group(1)) if benefit_match else 50
                        
                        return {
                            "score": score, 
                            "justification": justification,
                            "effort": effort,
                            "benefit": benefit
                        }
                    else:
                        return {
                            "score": 50, 
                            "justification": "Error al procesar respuesta",
                            "effort": 50,
                            "benefit": 50
                        }
            else:
                print("⚠️ Respuesta vacía de la API")
                return {
                    "score": 50, 
                    "justification": "Error: Respuesta vacía de la API",
                    "effort": 50,
                    "benefit": 50
                }
        except Exception as api_error:
            print(f"❌ Error en la llamada a la API: {str(api_error)}")
            traceback.print_exc()
            return {
                "score": 50, 
                "justification": f"Error en evaluación: {str(api_error)}",
                "effort": 50,
                "benefit": 50
            }
    except Exception as e:
        print(f"❌ Error general en evaluación cualitativa: {str(e)}")
        traceback.print_exc()
        return {
            "score": 50, 
            "justification": f"Error general: {str(e)}",
            "effort": 50,
            "benefit": 50
        }

def clean_text_for_pdf(text):
    """
    Limpia el texto para garantizar compatibilidad con PDF
    
    Esta función reemplaza caracteres especiales que puedan causar problemas
    con las fuentes básicas de PDF como helvetica, que no soportan Unicode completo.
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Diccionario de reemplazos para caracteres específicos
    replacements = {
        # Subíndices
        '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
        '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
        
        # Superíndices
        '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
        '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
        
        # Comillas y apóstrofes
        '"': '"', '"': '"', ''': "'", ''': "'",
        
        # Guiones
        '—': '-', '–': '-', '‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-',
        
        # Símbolos matemáticos y científicos
        '×': 'x', '÷': '/', '±': '+/-', '≈': '~=', '≤': '<=', '≥': '>=',
        '∞': 'infinito', '∑': 'suma', '∏': 'producto', '√': 'raiz',
        'π': 'pi', 'Ω': 'Omega', 'µ': 'micro', '∆': 'Delta',
        
        # Otros caracteres
        '…': '...', '•': '*', '′': "'", '″': '"', '€': 'EUR', '£': 'GBP',
        '©': '(c)', '®': '(R)', '™': '(TM)', '°': ' grados',
        
        # Caracteres latinos extendidos
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U'
    }
    
    # Aplicar reemplazos
    for special_char, replacement in replacements.items():
        text = text.replace(special_char, replacement)
    
    # Lista de intervalos Unicode a eliminar o reemplazar
    # Podemos expandir esto según sea necesario
    problematic_ranges = [
        (0x2000, 0x206F),  # Puntuación general
        (0x2100, 0x214F),  # Letras y símbolos
        (0x2150, 0x218F),  # Formas numéricas
        (0x2190, 0x21FF),  # Flechas
        (0x2200, 0x22FF),  # Operadores matemáticos
        (0x25A0, 0x25FF),  # Formas geométricas
        (0x2700, 0x27BF),  # Dingbats
        (0x1F300, 0x1F5FF),  # Emojis y símbolos varios
    ]
    
    # Construir una lista de caracteres a eliminar
    chars_to_remove = []
    for start, end in problematic_ranges:
        for code_point in range(start, end + 1):
            try:
                # Intentar convertir el punto de código a carácter
                char = chr(code_point)
                if char in text:
                    chars_to_remove.append(char)
            except:
                pass
    
    # Eliminar caracteres problemáticos
    for char in chars_to_remove:
        text = text.replace(char, '')
    
    return text

def generate_justification_v2(idea_text, analysis_text, score_data, ranking_context):
    """
    Genera una justificación detallada para la puntuación asignada a una idea.
    
    La justificación incluye análisis de las tres dimensiones (técnica, económica y de mercado),
    así como una valoración general.
    """
    try:
        if not idea_text or not score_data:
            return "No se pudo generar una justificación para esta idea debido a datos incompletos."
        
        # Sanitizar todos los textos de entrada para prevenir errores de formato
        safe_idea_text = ""
        if idea_text:
            if isinstance(idea_text, str):
                safe_idea_text = idea_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            else:
                try:
                    safe_idea_text = str(idea_text).replace('%', '%%').replace('{', '{{').replace('}', '}}')
                except:
                    safe_idea_text = "Error al procesar texto de idea"
        
        safe_analysis_text = ""
        if analysis_text:
            if isinstance(analysis_text, str):
                safe_analysis_text = analysis_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            else:
                try:
                    safe_analysis_text = str(analysis_text).replace('%', '%%').replace('{', '{{').replace('}', '}}')
                except:
                    safe_analysis_text = "Error al procesar texto de análisis"
        
        safe_ranking_context = ""
        if ranking_context:
            if isinstance(ranking_context, str):
                safe_ranking_context = ranking_context.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            else:
                try:
                    safe_ranking_context = str(ranking_context).replace('%', '%%').replace('{', '{{').replace('}', '}}')
                except:
                    safe_ranking_context = ""
        
        # ID para esta evaluación
        eval_id = f"justification_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Obtener los componentes de la puntuación
        score = score_data.get('score', 0)
        score_quantitative = score_data.get('score_quantitative', 0)
        score_qualitative = score_data.get('score_qualitative', 0)
        
        # Obtener información sobre las dimensiones
        dim_tecnica = score_data.get('dimension_tecnica', 0)
        dim_economica = score_data.get('dimension_economica', 0)
        dim_mercado = score_data.get('dimension_mercado', 0)
        
        # Formatear el contexto de ranking si está disponible
        ranking_context_text = ""
        if safe_ranking_context and len(safe_ranking_context.strip()) > 0:
            ranking_context_text = f"CONTEXTO DE PRIORIZACIÓN:\n{safe_ranking_context}\n\n"
        
        # CAMBIO IMPORTANTE: No usar las justificaciones individuales de las métricas
        # En su lugar, formatear directamente los valores numéricos de las métricas
        metrics_info = ""
        if 'metrics' in score_data and isinstance(score_data['metrics'], dict):
            metrics = score_data['metrics']
            
            # Asegurar que todos los valores de métricas son seguros para f-strings
            safe_metrics = {}
            for key, value in metrics.items():
                if isinstance(value, str):
                    safe_metrics[key] = value.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                else:
                    safe_metrics[key] = value
            
            # Calcular el progreso TRL para mostrar
            trl_inicial = safe_metrics.get('trl_inicial', 3)
            trl_final = safe_metrics.get('trl_final', 6)
            
            # Validar que sean números
            try:
                trl_inicial = int(trl_inicial)
                trl_final = int(trl_final)
            except:
                trl_inicial = 3
                trl_final = 6
                
            trl_delta = trl_final - trl_inicial
            
            # Determinar el valor normalizado del progreso TRL
            if trl_delta >= 6:
                progreso_trl_valor = 5
            elif trl_delta >= 4:
                progreso_trl_valor = 4
            elif trl_delta >= 2:
                progreso_trl_valor = 3
            elif trl_delta == 1:
                progreso_trl_valor = 2
            else:
                progreso_trl_valor = 1
            
            # Evitar el uso de justificaciones y solo incluir valores numéricos
            metrics_info = "\n".join([
                f"MÉTRICAS CLAVE:",
                f"Dimensión Técnica:",
                f"- Riesgo Técnico: {safe_metrics.get('riesgo_tecnico', 3)}/5",
                f"- Tiempo de Desarrollo: {safe_metrics.get('tiempo_desarrollo', 3)}/5",
                f"- TRL Inicial/Final: {trl_inicial}/{trl_final} (Progreso: {progreso_trl_valor}/5)",
                f"",
                f"Dimensión Económica:",
                f"- Ratio Costes/Ingresos: {safe_metrics.get('ratio_costes_ingresos', safe_metrics.get('costes_ingresos', 3))}/5",
                f"- Ingresos Previstos: {safe_metrics.get('ingresos_previstos', 3)}/5",
                f"- Payback/ROI: {safe_metrics.get('payback_roi', 3)}/5",
                f"",
                f"Dimensión de Mercado:",
                f"- Tamaño de Mercado: {safe_metrics.get('tamano_mercado', 3)}/5",
                f"- Riesgo de Mercado: {safe_metrics.get('riesgo_mercado', 3)}/5", 
                f"- Alineación Estratégica: {safe_metrics.get('alineacion_estrategica', 3)}/5"
            ])
        
        # Crear prompt para generar la justificación
        prompt = f"""
        ID EVALUACIÓN: {eval_id}
        
        Como consultor estratégico senior de Sener, genera un análisis detallado y completo para la siguiente idea:
        
        IDEA: {safe_idea_text}
        
        PUNTUACIÓN FINAL: {score}/100
        - Componente Cuantitativo (50%): {score_quantitative}/100
        - Componente Cualitativo (50%): {score_qualitative}/100
        
        DESGLOSE POR DIMENSIONES:
        - Dimensión Técnica (33,3% del 50% cuantitativo): {dim_tecnica}/100
        - Dimensión Económica (33,3% del 50% cuantitativo): {dim_economica}/100
        - Dimensión de Mercado (33,3% del 50% cuantitativo): {dim_mercado}/100
        
        {metrics_info}
        {ranking_context_text}
        ANÁLISIS PREVIO: {safe_analysis_text}
        
        Genera un análisis extenso y profundo (400-600 palabras) que incluya:
        
        1. VALORACIÓN GENERAL: Explicación clara de la puntuación asignada, destacando tanto el componente cuantitativo como cualitativo, y contextualizando la idea en el panorama tecnológico actual.
        
        2. ANÁLISIS DE DIMENSIONES:
           - Dimensión Técnica: Interpretación detallada del riesgo técnico, tiempo de desarrollo y progreso TRL
           - Dimensión Económica: Análisis de ratio costes/ingresos, ingresos previstos y ROI
           - Dimensión de Mercado: Evaluación del tamaño de mercado, riesgo y alineación estratégica
        
        3. ALINEACIÓN ESTRATÉGICA: Análisis sobre cómo se alinea con el contexto de priorización (si existe) y con la estrategia de la organización.
        
        4. FORTALEZAS Y DEBILIDADES: Examen exhaustivo de los puntos fuertes y áreas de mejora, con ejemplos concretos.
        
        5. RECOMENDACIONES Y SIGUIENTES PASOS: Plan de acción detallado, con recomendaciones claras sobre si priorizar la idea, y qué acciones específicas tomar.
        
        El análisis debe ser específico para esta idea, evitando generalidades. Usa párrafos bien estructurados, lenguaje profesional, y enfoque analítico. No uses secciones con encabezados, sino un texto fluido que cubra todos los aspectos de manera natural.
        
        IMPORTANTE: Evita usar caracteres especiales como subíndices, superíndices, símbolos matemáticos o cualquier símbolo Unicode avanzado, ya que causarán problemas en el documento final. Usa solo caracteres ASCII básicos.
        """
        
        try:
            # Usar nuevo cliente de OpenAI si está disponible
            if USING_NEW_CLIENT:
                response = client.chat.completions.create(
                    model=DEPLOYMENT_NAME,
                    messages=[
                        {"role": "system", "content": "Eres un consultor estratégico experto en análisis tecnológico para SENER, enfocado en proporcionar evaluaciones fundamentadas y acciones claras. Tus análisis son detallados, objetivos y accionables."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=1500,
                    timeout=60
                )
                
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    justification = response.choices[0].message.content.strip()
                else:
                    print("⚠️ Respuesta vacía al generar justificación")
                    return "No se pudo generar una justificación detallada. Por favor, revise las métricas y el análisis manualmente."
                    
            else:
                # Fallback al cliente legacy
                response = openai.ChatCompletion.create(
                    engine=DEPLOYMENT_NAME,
                    messages=[
                        {"role": "system", "content": "Eres un consultor estratégico experto en análisis tecnológico para SENER, enfocado en proporcionar evaluaciones fundamentadas y acciones claras."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=1500
                )
                
                if 'choices' in response and len(response['choices']) > 0:
                    justification = response['choices'][0]['message']['content'].strip()
                else:
                    print("⚠️ Respuesta vacía al generar justificación (legacy)")
                    return "No se pudo generar una justificación detallada. Por favor, revise las métricas y el análisis manualmente."
            
            # Limpiar texto para evitar problemas con PDF y sanitizar
            justification = clean_text_for_pdf(justification)
            justification = justification.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
            return justification
            
        except Exception as api_err:
            error_msg = str(api_err)
            # Sanitizar mensaje de error
            error_msg = error_msg.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
            print(f"❌ Error llamando a la API para justificación: {error_msg}")
            traceback.print_exc()
            return f"Error generando justificación: {error_msg}"
        
    except Exception as e:
        error_msg = str(e)
        # Sanitizar mensaje de error
        error_msg = error_msg.replace('%', '%%').replace('{', '{{').replace('}', '}}')
        
        print(f"❌ Error general en generate_justification_v2: {error_msg}")
        traceback.print_exc()
        return f"Error general: {error_msg}"

def generate_ranking_pdf_improved(ideas, ranking_context):
    """
    Genera un PDF profesional con el ranking de ideas incluyendo portada,
    tabla de calificaciones, análisis detallado, y matriz de payoff.
    
    Args:
        ideas: Lista de ideas rankeadas
        ranking_context: Contexto utilizado para la priorización
        
    Returns:
        Ruta del archivo PDF generado
    """
    try:
        # Verificar que tenemos ideas
        if not ideas or not isinstance(ideas, list) or len(ideas) == 0:
            print("❌ No hay ideas para generar el PDF de ranking")
            return None
            
        # Obtener resumen ejecutivo
        ranking_summary = generate_ranking_summary(ideas, ranking_context)
        
        # Crear PDF
        from fpdf import FPDF
        
        class PDF(FPDF):
            def header(self):
                # Logo (solo a partir de la página 2)
                if self.page_no() > 1:
                    try:
                        logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
                        for logo_path in logo_paths:
                            if os.path.exists(logo_path):
                                self.image(logo_path, 10, 8, 33)
                                break
                    except:
                        pass
                    
                    # Título del documento en cada página (excepto portada)
                    self.set_font('Helvetica', 'B', 12)
                    self.cell(0, 10, 'Ranking de Ideas - Análisis de Priorización', 0, 1, 'C')
                    self.ln(5)
                
            def footer(self):
                # Posicionar a 1.5 cm del final
                self.set_y(-15)
                # Fuente y color de texto del pie
                self.set_font('Helvetica', 'I', 8)
                self.set_text_color(128, 128, 128)
                # Número de página centrado
                self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
        
        # Inicializar PDF con fuente Unicode
        pdf = PDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Intentar usar fuentes que soporten Unicode
        try:
            pdf.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
            pdf.add_font('DejaVu', 'B', 'DejaVuSansCondensed-Bold.ttf', uni=True)
            font_family = 'DejaVu'
            print("✅ Usando fuente DejaVu con soporte Unicode")
        except:
            # Fallback a Arial/Helvetica
            font_family = 'Helvetica'
            print("⚠️ Usando fuente Helvetica (limitado soporte Unicode)")
        
        # Portada con logo grande y centrado
        try:
            logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
            for logo_path in logo_paths:
                if os.path.exists(logo_path):
                    # Cálculo para posicionar el logo en el centro
                    logo_width = 80  # Ancho del logo más grande
                    logo_x = (210 - logo_width) / 2  # Centrado (A4 = 210mm)
                    pdf.image(logo_path, x=logo_x, y=40, w=logo_width)
                    break
        except Exception as e:
            print(f"⚠️ No se pudo añadir el logo en la portada: {str(e)}")
        
        pdf.set_font(font_family, 'B', 24)
        pdf.set_text_color(44, 62, 80)  # Azul oscuro
        pdf.ln(130)  # Espacio después del logo
        pdf.cell(0, 20, 'RANKING DE IDEAS', ln=True, align='C')
        pdf.set_font(font_family, '', 16)
        pdf.cell(0, 10, 'Informe de Priorización', ln=True, align='C')
        
        # Fecha y número de ideas
        pdf.ln(20)
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, f'Fecha: {datetime.now().strftime("%d/%m/%Y")}', ln=True, align='C')
        pdf.cell(0, 10, f'Total de ideas analizadas: {len(ideas)}', ln=True, align='C')
        
        # Contexto si existe
        if ranking_context and isinstance(ranking_context, str) and len(ranking_context.strip()) > 5:
            # Eliminamos esta sección según la solicitud del usuario
            # pdf.add_page()
            # pdf.set_font(font_family, 'B', 16)
            # pdf.set_text_color(44, 62, 80)
            # pdf.cell(0, 10, 'Contexto de Priorización', ln=True)
            # pdf.ln(5)
            # pdf.set_font(font_family, '', 12)
            # pdf.set_text_color(0, 0, 0)
            # clean_context = clean_text_for_pdf(ranking_context)
            # pdf.multi_cell(0, 6, clean_context)
            pass
        
        # Resumen ejecutivo
        pdf.add_page()
        pdf.set_font(font_family, 'B', 16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, 'Resumen Ejecutivo', ln=True)
        pdf.ln(5)
        pdf.set_font(font_family, '', 12)
        pdf.set_text_color(0, 0, 0)
        clean_summary = clean_text_for_pdf(ranking_summary)
        pdf.multi_cell(0, 6, clean_summary)
        
        # Tabla de ideas rankeadas
        pdf.add_page()
        pdf.set_font(font_family, 'B', 16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, 'Ranking de Ideas', ln=True)
        pdf.ln(5)
        
        # Encabezados de tabla simplificada (solo posición, idea, nota total y página)
        pdf.set_font(font_family, 'B', 12)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(15, 10, 'Pos.', 1, 0, 'C', True)
        pdf.cell(130, 10, 'Idea', 1, 0, 'C', True)
        pdf.cell(25, 10, 'Total', 1, 0, 'C', True)
        pdf.cell(20, 10, 'Página', 1, 1, 'C', True)
        
        # Variables para seguimiento de páginas
        idea_pages = {}
        current_page = pdf.page_no()
        
        # Datos de la tabla
        pdf.set_font(font_family, '', 10)
        for i, idea in enumerate(ideas, 1):
            if not isinstance(idea, dict):
                continue
                
            # Extraer título
            title = idea.get('title', '')
            if not title and 'idea' in idea:
                idea_text = str(idea['idea'])
                title = idea_text.split('\n')[0][:50] if '\n' in idea_text else idea_text[:50]
                if len(title) >= 50:
                    title += "..."
            
            # Si aún no hay título, usar uno genérico
            if not title:
                title = f"Idea {i}"
            
            # Limpiar título para PDF
            title = clean_text_for_pdf(title)
            
            # Color de fondo alternante
            fill = i % 2 == 0
            bg_color = (245, 245, 245) if fill else (255, 255, 255)
            pdf.set_fill_color(*bg_color)
            
            # Puntuación
            score = idea.get('score', 0)
            
            # Página estimada (se actualizará después)
            idea_pages[i] = "TBD"
            
            # Añadir fila
            pdf.cell(15, 10, str(i), 1, 0, 'C', fill)
            
            # Título con altura variable
            current_x = pdf.get_x()
            current_y = pdf.get_y()
            pdf.multi_cell(130, 10, title, 1, 'L', fill)
            pdf.set_xy(current_x + 130, current_y)
            
            # Puntuación total y página (temporal)
            pdf.cell(25, 10, f"{score:.1f}", 1, 0, 'C', fill)
            pdf.cell(20, 10, "TBD", 1, 1, 'C', fill)
            
            # Si el título era largo y causó un salto de línea, ajustar
            if pdf.get_y() > current_y + 10:
                pdf.set_y(pdf.get_y())
        
        # Añadir matriz de payoff al PDF
        from payoff_matrix_generator import add_payoff_matrix_to_pdf
        try:
            print("🔄 Generando matriz de payoff para el PDF...")
            pdf.add_page()
            add_payoff_matrix_to_pdf(pdf, ideas)
        except Exception as e:
            print(f"⚠️ Error al generar matriz de payoff: {str(e)}")
            traceback.print_exc()
            # Continuar sin la matriz de payoff
        
        # Detalles de cada idea
        for i, idea in enumerate(ideas, 1):
            if not isinstance(idea, dict):
                continue
                
            # Nueva página para cada idea
            pdf.add_page()
            
            # Guardar página actual para la tabla de contenidos
            idea_pages[i] = pdf.page_no()
            
            # Título con número de ranking
            pdf.set_font(font_family, 'B', 14)
            pdf.set_text_color(44, 62, 80)
            
            # Extraer título
            title = idea.get('title', '')
            if not title and 'idea' in idea:
                idea_text = str(idea['idea'])
                title = idea_text.split('\n')[0][:70] if '\n' in idea_text else idea_text[:70]
                if len(title) >= 70:
                    title += "..."
            
            # Si aún no hay título, usar uno genérico
            if not title:
                title = f"Idea {i}"
                
            # Limpiar para PDF
            title = clean_text_for_pdf(title)
            
            # Mostrar título con número de ranking
            pdf.cell(0, 10, f"{i}. {title}", ln=True)
            
            # Insertar resumen ejecutivo de la idea justo después del título
            pdf.ln(3)
            pdf.set_font(font_family, '', 10)
            pdf.set_text_color(60, 60, 60)  # Gris oscuro para diferenciarlo
            
            # Generar resumen inteligente en lugar del texto completo
            if 'idea' in idea:
                idea_summary = generate_idea_summary(str(idea['idea']), max_chars=300)
                pdf.multi_cell(0, 5, idea_summary)
                pdf.ln(3)
            
            # Opcional: Agregar indicador de que hay más texto si se truncó
            original_text = str(idea.get('idea', ''))
            if len(original_text) > 300:
                pdf.set_font(font_family, 'I', 8)
                pdf.set_text_color(120, 120, 120)
                pdf.cell(0, 4, "(Resumen ejecutivo - ver texto completo al final del documento)", ln=True)
                pdf.ln(2)
            
            # Restablecer color y fuente para la siguiente sección
            pdf.set_font(font_family, '', 11)
            pdf.set_text_color(0, 0, 0)
            
            # Crear visualización de puntuación
            try:
                score = idea.get('score', 0)
                score_img = generate_score_wheel(score)
                
                if score_img:
                    # Posicionar la rueda a la derecha
                    current_y = pdf.get_y()
                    img_width = 40  # Ancho en mm
                    pdf.image(score_img, x=pdf.w - img_width - 10, y=current_y, w=img_width)
                    
                    # Texto explicativo a la izquierda
                    pdf.set_xy(10, current_y)
                    pdf.set_font(font_family, 'B', 12)
                    pdf.cell(pdf.w - img_width - 20, 10, f"Puntuación: {score:.1f}/100", ln=True)
                    
                    # Restaurar posición vertical después de la imagen
                    pdf.set_y(current_y + img_width + 5)
                else:
                    # Si no se pudo generar la rueda, mostrar solo texto
                    pdf.set_font(font_family, 'B', 12)
                    pdf.cell(0, 10, f"Puntuación: {score:.1f}/100", ln=True)
            except Exception as e:
                print(f"⚠️ Error al generar rueda de puntuación: {str(e)}")
                pdf.set_font(font_family, 'B', 12)
                pdf.cell(0, 10, f"Puntuación: {score:.1f}/100", ln=True)
            
            # Resumen de puntuaciones
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 12)
            pdf.cell(0, 10, 'Resumen de Puntuaciones:', ln=True)
            
            # Tabla de puntuaciones
            pdf.set_font(font_family, '', 10)
            pdf.set_fill_color(240, 240, 240)
            
            # Puntuaciones
            score = idea.get('score', 0)
            score_quant = idea.get('score_quantitative', 0)
            score_qual = idea.get('score_qualitative', 0)
            
            # Obtener las métricas originales en su escala (1-5 o 1-9)
            if 'metrics' in idea and isinstance(idea['metrics'], dict):
                metrics = idea['metrics']
                # Valores originales (escala 1-5, excepto TRL que es 1-9)
                riesgo_tecnico = metrics.get('riesgo_tecnico', 3)
                tiempo_desarrollo = metrics.get('tiempo_desarrollo', 3)
                trl_inicial = metrics.get('trl_inicial', 3)
                trl_final = metrics.get('trl_final', 6)
                costes_ingresos = metrics.get('ratio_costes_ingresos', metrics.get('costes_ingresos', 3))
                ingresos_previstos = metrics.get('ingresos_previstos', 3)
                payback_roi = metrics.get('payback_roi', 3)
                tamano_mercado = metrics.get('tamano_mercado', 3)
                riesgo_mercado = metrics.get('riesgo_mercado', 3)
                alineacion_estrategica = metrics.get('alineacion_estrategica', 3)
                evaluacion_cualitativa = metrics.get('evaluacion_cualitativa', 3)
                # Calcular dimensiones en escala 0-100 (igual que en calculate_final_score)
                # Dimensión Técnica
                trl_delta = trl_final - trl_inicial
                if trl_delta >= 6:
                    progreso_trl = 5.0
                elif trl_delta >= 4 and trl_delta <= 5:
                    progreso_trl = 4.0 + (trl_delta - 4) * 0.5
                elif trl_delta >= 2 and trl_delta <= 3:
                    progreso_trl = 3.0 + (trl_delta - 2) * 0.5
                elif trl_delta == 1:
                    progreso_trl = 2.0
                else:
                    progreso_trl = 1.0
                dim_tecnica = ((float(riesgo_tecnico) + float(tiempo_desarrollo) + float(progreso_trl)) / 3 - 1.0) / 4.0 * 100
                dim_economica = ((float(costes_ingresos) + float(ingresos_previstos) + float(payback_roi)) / 3 - 1.0) / 4.0 * 100
                dim_mercado = ((float(tamano_mercado) + float(riesgo_mercado) + float(alineacion_estrategica)) / 3 - 1.0) / 4.0 * 100
            else:
                # Convertir valores de 0-100 a escala 0-100 (ya están normalizados)
                dim_tecnica = idea.get('dimension_tecnica', 60)
                dim_economica = idea.get('dimension_economica', 60)
                dim_mercado = idea.get('dimension_mercado', 60)
            
            # Primera fila de tabla
            pdf.set_font(font_family, 'B', 10)
            pdf.cell(90, 8, "Categoría", 1, 0, 'C', True)
            pdf.cell(45, 8, "Puntuación", 1, 0, 'C', True)
            pdf.cell(45, 8, "Peso", 1, 1, 'C', True)

            # Componente Cuantitativo (negrita)
            pdf.set_font(font_family, 'B', 10)
            pdf.cell(90, 8, "Componente Cuantitativo", 1, 0, 'L')
            pdf.cell(45, 8, f"{score_quant:.1f}/100", 1, 0, 'C')
            pdf.cell(45, 8, "50%", 1, 1, 'C')

            # Dimensiones (guion y texto normal)
            pdf.set_font(font_family, '', 10)
            pdf.cell(90, 8, "- Dimensión Técnica", 1, 0, 'L')
            pdf.cell(45, 8, f"{dim_tecnica:.1f}/100", 1, 0, 'C')
            pdf.cell(45, 8, "16.7%", 1, 1, 'C')

            pdf.cell(90, 8, "- Dimensión Económica", 1, 0, 'L')
            pdf.cell(45, 8, f"{dim_economica:.1f}/100", 1, 0, 'C')
            pdf.cell(45, 8, "16.7%", 1, 1, 'C')

            pdf.cell(90, 8, "- Dimensión de Mercado", 1, 0, 'L')
            pdf.cell(45, 8, f"{dim_mercado:.1f}/100", 1, 0, 'C')
            pdf.cell(45, 8, "16.7%", 1, 1, 'C')

            # Evaluación Cualitativa (negrita)
            pdf.set_font(font_family, 'B', 10)
            pdf.cell(90, 8, "Evaluación Cualitativa", 1, 0, 'L')
            pdf.cell(45, 8, f"{score_qual:.1f}/100", 1, 0, 'C')
            pdf.cell(45, 8, "50%", 1, 1, 'C')

            # Puntuación total (ya estaba en negrita)
            pdf.set_font(font_family, 'B', 10)
            pdf.cell(90, 8, "PUNTUACIÓN TOTAL", 1, 0, 'L', True)
            pdf.cell(45, 8, f"{score:.1f}/100", 1, 0, 'C', True)
            pdf.cell(45, 8, "100%", 1, 1, 'C', True)
            
            # Extraer y añadir métricas si están disponibles
            pdf.ln(5)
            if 'metrics' in idea and isinstance(idea['metrics'], dict):
                pdf.set_font(font_family, 'B', 12)
                pdf.cell(0, 10, 'Métricas Clave:', ln=True)
                
                pdf.set_font(font_family, '', 10)
                metrics = idea['metrics']
                
                # Tabla de métricas - Encabezado
                pdf.cell(120, 8, "Dimensión y Métrica", 1, 0, 'C', True)
                pdf.cell(60, 8, "Valor", 1, 1, 'C', True)
                
                # Calcular progreso TRL para mostrar
                trl_inicial = metrics.get('trl_inicial', 3)
                trl_final = metrics.get('trl_final', 6)
                trl_delta = trl_final - trl_inicial
                if trl_delta >= 6:
                    progreso_trl = 5
                elif trl_delta >= 4 and trl_delta <= 5:
                    progreso_trl = 4
                elif trl_delta >= 2 and trl_delta <= 3:
                    progreso_trl = 3
                elif trl_delta == 1:
                    progreso_trl = 2
                else:  # trl_delta <= 0
                    progreso_trl = 1
                # Dimensión Técnica (mostrar en 1-5 para submétricas)
                media_tecnica = (float(riesgo_tecnico) + float(tiempo_desarrollo) + float(progreso_trl)) / 3
                pdf.set_font(font_family, 'B', 10)
                pdf.cell(120, 8, "Dimensión Técnica (media)", 1, 0, 'L')
                pdf.cell(60, 8, f"{media_tecnica:.2f}/5", 1, 1, 'C')
                pdf.set_font(font_family, '', 10)
                pdf.cell(120, 8, "   - Riesgo Técnico", 1, 0, 'L')
                pdf.cell(60, 8, f"{riesgo_tecnico:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Tiempo de Desarrollo", 1, 0, 'L')
                pdf.cell(60, 8, f"{tiempo_desarrollo:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Progreso TRL", 1, 0, 'L')
                pdf.cell(60, 8, f"{progreso_trl}/5 (delta={trl_delta})", 1, 1, 'C')
                pdf.cell(120, 8, "   - TRL Inicial / Final", 1, 0, 'L')
                pdf.cell(60, 8, f"{trl_inicial}/9 -> {trl_final}/9", 1, 1, 'C')
                # Dimensión Económica
                media_economica = (float(costes_ingresos) + float(ingresos_previstos) + float(payback_roi)) / 3
                pdf.set_font(font_family, 'B', 10)
                pdf.cell(120, 8, "Dimensión Económica (media)", 1, 0, 'L')
                pdf.cell(60, 8, f"{media_economica:.2f}/5", 1, 1, 'C')
                pdf.set_font(font_family, '', 10)
                pdf.cell(120, 8, "   - Ratio Costes/Ingresos", 1, 0, 'L')
                pdf.cell(60, 8, f"{costes_ingresos:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Ingresos Previstos", 1, 0, 'L')
                pdf.cell(60, 8, f"{ingresos_previstos:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Payback/ROI", 1, 0, 'L')
                pdf.cell(60, 8, f"{payback_roi:.2f}/5", 1, 1, 'C')
                # Dimensión de Mercado
                media_mercado = (float(tamano_mercado) + float(riesgo_mercado) + float(alineacion_estrategica)) / 3
                pdf.set_font(font_family, 'B', 10)
                pdf.cell(120, 8, "Dimensión de Mercado (media)", 1, 0, 'L')
                pdf.cell(60, 8, f"{media_mercado:.2f}/5", 1, 1, 'C')
                pdf.set_font(font_family, '', 10)
                pdf.cell(120, 8, "   - Tamaño de Mercado", 1, 0, 'L')
                pdf.cell(60, 8, f"{tamano_mercado:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Riesgo de Mercado", 1, 0, 'L')
                pdf.cell(60, 8, f"{riesgo_mercado:.2f}/5", 1, 1, 'C')
                pdf.cell(120, 8, "   - Alineación Estratégica", 1, 0, 'L')
                pdf.cell(60, 8, f"{alineacion_estrategica:.2f}/5", 1, 1, 'C')
                # Evaluación cualitativa (componente separado)
                pdf.set_font(font_family, 'B', 10)
                pdf.cell(120, 8, "Evaluación Cualitativa", 1, 0, 'L')
                pdf.cell(60, 8, f"{evaluacion_cualitativa:.2f}/5", 1, 1, 'C')
            
            # Añadir la sección de justificación
            pdf.ln(10)
            pdf.set_font(font_family, 'B', 14)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 10, 'Justificación:', ln=True)
            pdf.ln(2)
            
            # Extraer y añadir la justificación
            if 'justification' in idea and idea['justification']:
                justification_text = clean_text_for_pdf(str(idea['justification']))
                pdf.set_font(font_family, '', 11)
                pdf.set_text_color(0, 0, 0)
                pdf.multi_cell(0, 6, justification_text)
            else:
                pdf.set_font(font_family, '', 11)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(0, 6, "No se ha proporcionado una justificación detallada para esta idea.")
        
        # Volver a la página de tabla de ranking para actualizar los números de página
        # La siguiente línea puede causar errores:
        # pdf.page = current_page
        
        # En lugar de intentar volver a una página anterior, vamos a crear
        # páginas de referencias por separado al final
        
        # Guardar la página actual antes de añadir la página de referencias
        current_page_final = pdf.page_no()
        
        # Añadir una página para referencias
        pdf.add_page()
        pdf.set_font(font_family, 'B', 16)
        pdf.set_text_color(44, 62, 80)  # Azul oscuro
        pdf.cell(0, 10, "Referencias de Ideas", 0, 1, 'C')
        pdf.ln(5)
        
        # Tabla de referencias
        pdf.set_font(font_family, 'B', 12)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(15, 10, 'Pos.', 1, 0, 'C', True)
        pdf.cell(130, 10, 'Idea', 1, 0, 'C', True)
        pdf.cell(45, 10, 'Página', 1, 1, 'C', True)
        
        # Datos de la tabla
        pdf.set_font(font_family, '', 10)
        for i, idea in enumerate(ideas, 1):
            if not isinstance(idea, dict):
                continue
                
            # Extraer título
            title = idea.get('title', '')
            if not title and 'idea' in idea:
                idea_text = str(idea['idea'])
                title = idea_text.split('\n')[0][:50] if '\n' in idea_text else idea_text[:50]
                if len(title) >= 50:
                    title += "..."
            
            # Si aún no hay título, usar uno genérico
            if not title:
                title = f"Idea {i}"
                
            # Limpiar título para PDF
            title = clean_text_for_pdf(title)
            
            # Color de fondo alternante
            fill = i % 2 == 0
            bg_color = (245, 245, 245) if fill else (255, 255, 255)
            pdf.set_fill_color(*bg_color)
            
            # Página
            page_num = idea_pages[i]
            
            # Añadir fila
            pdf.cell(15, 10, str(i), 1, 0, 'C', fill)
            
            # Título con altura variable
            current_x = pdf.get_x()
            current_y = pdf.get_y()
            pdf.multi_cell(130, 10, title, 1, 'L', fill)
            pdf.set_xy(current_x + 130, current_y)
            
            # Página
            pdf.cell(45, 10, str(page_num), 1, 1, 'C', fill)
        
        # Añadir sección de textos completos al final (solo para ideas que fueron resumidas)
        long_ideas = [idea for idea in ideas if len(str(idea.get('idea', ''))) > 300]
        if long_ideas:
            pdf.add_page()
            pdf.set_font(font_family, 'B', 16)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 10, 'Anexo: Textos Completos de Ideas', ln=True)
            pdf.ln(5)
            
            pdf.set_font(font_family, '', 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, 'Esta sección contiene el texto completo de las ideas que fueron resumidas en las páginas anteriores.', ln=True)
            pdf.ln(8)
            
            for idea in long_ideas:
                # Buscar el número de ranking
                idea_index = next((i+1 for i, ranked_idea in enumerate(ideas) if ranked_idea == idea), 0)
                
                # Título
                pdf.set_font(font_family, 'B', 12)
                pdf.set_text_color(44, 62, 80)
                title = idea.get('title', '')
                if not title and 'idea' in idea:
                    idea_text = str(idea['idea'])
                    title = idea_text.split('\n')[0][:70] if '\n' in idea_text else idea_text[:70]
                    if len(title) >= 70:
                        title += "..."
                if not title:
                    title = f"Idea {idea_index}"
                
                pdf.cell(0, 8, f"{idea_index}. {clean_text_for_pdf(title)}", ln=True)
                pdf.ln(3)
                
                # Texto completo
                pdf.set_font(font_family, '', 9)
                pdf.set_text_color(0, 0, 0)
                full_text = clean_text_for_pdf(str(idea.get('idea', '')))
                pdf.multi_cell(0, 5, full_text)
                pdf.ln(8)
        
        # Guardar PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"ranking_{timestamp}.pdf")
        pdf.output(pdf_path)
        
        print(f"✅ PDF de ranking generado exitosamente: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        print(f"❌ Error al generar PDF de ranking: {str(e)}")
        traceback.print_exc()
        return None

def generate_ranking_summary(ranked_ideas, ranking_context=""):
    """
    Genera un resumen ejecutivo del ranking global de ideas, explicando patrones, 
    criterios de priorización y razones por las que algunas ideas destacan sobre otras.
    
    Args:
        ranked_ideas: Lista de ideas ya ordenadas por puntuación
        ranking_context: Contexto de priorización proporcionado por el usuario
        
    Returns:
        Un texto con el resumen ejecutivo del ranking
    """
    if not ranked_ideas or len(ranked_ideas) == 0:
        return "No hay ideas suficientes para generar un resumen del ranking."
    
    # Extraer información clave de las ideas rankeadas
    num_ideas = len(ranked_ideas)
    max_score = ranked_ideas[0].get('score', 0) if num_ideas > 0 else 0
    min_score = ranked_ideas[-1].get('score', 0) if num_ideas > 0 else 0
    avg_score = sum(idea.get('score', 0) for idea in ranked_ideas) / num_ideas if num_ideas > 0 else 0
    
    # Extraer títulos de las ideas mejor rankeadas (top 3 o menos)
    top_ideas = ranked_ideas[:min(3, num_ideas)]
    top_ideas_info = "\n".join([f"- {i+1}. {idea.get('title', 'Idea sin título')} ({idea.get('score', 0):.1f}/100)" 
                               for i, idea in enumerate(top_ideas)])
    
    # Obtener las categorías/métricas donde las ideas mejor rankeadas destacan
    top_strengths = []
    if num_ideas > 0 and 'metrics' in ranked_ideas[0]:
        metrics = ranked_ideas[0]['metrics']
        # Identificar las métricas más altas
        if metrics.get('riesgo_tecnico', 0) >= 4:
            top_strengths.append("bajo riesgo técnico")
        if metrics.get('tiempo_desarrollo', 0) >= 4:
            top_strengths.append("corto tiempo de desarrollo")
        if metrics.get('costes_ingresos', 0) >= 4:
            top_strengths.append("excelente relación costes-ingresos")
        if metrics.get('ingresos_previstos', 0) >= 4:
            top_strengths.append("alto potencial de ingresos")
        if metrics.get('riesgo_mercado', 0) >= 4:
            top_strengths.append("bajo riesgo de mercado")
    
    strengths_text = ", ".join(top_strengths) if top_strengths else "múltiples áreas"
    
    # Crear un ID único para esta solicitud
    eval_id = f"ranking_summary_{int(time.time())}_{random.randint(1000, 9999)}"
    
    # Crear clave de caché
    cache_key = f"ranking_summary_{hashlib.md5((str(max_score) + str(min_score) + str(num_ideas) + (ranking_context[:100] if ranking_context else '')).encode()).hexdigest()}"
    
    # Verificar si ya tenemos este resultado en caché
    if cache_key in _api_cache:
        print(f"🔄 Usando resumen de ranking en caché")
        return _api_cache[cache_key]
    
    # Crear el prompt para generar el resumen ejecutivo
    prompt = f"""
    ID EVALUACIÓN: {eval_id}
    
    Como consultor estratégico senior de Sener, genera un RESUMEN EJECUTIVO GLOBAL del ranking de ideas innovadoras.
    
    DATOS DEL RANKING:
    - Número total de ideas evaluadas: {num_ideas}
    - Puntuación más alta: {max_score:.1f}/100
    - Puntuación más baja: {min_score:.1f}/100
    - Puntuación media: {avg_score:.1f}/100
    - Ideas mejor rankeadas:
    {top_ideas_info}
    
    CONTEXTO DE PRIORIZACIÓN:
    {ranking_context if ranking_context else "No se ha especificado un contexto particular de priorización."}
    
    INSTRUCCIONES:
    Genera un análisis global del ranking (350-450 palabras) que:
    
    1. Explique las tendencias generales observadas en el ranking y por qué ciertas ideas destacan sobre otras.
    2. Analice los patrones comunes entre las ideas mejor puntuadas (p.ej., destacan en {strengths_text}).
    3. Interprete cómo el contexto de priorización (si existe) ha influido en la evaluación.
    4. Proporcione recomendaciones globales sobre cómo proceder con las ideas rankeadas.
    5. Destaque diferencias clave entre las ideas de alta y baja puntuación.
    
    El resumen debe ser profesional, estratégico y útil para la toma de decisiones ejecutivas.
    Evita caracteres especiales o símbolos Unicode avanzados, usa solo ASCII básico.
    No uses subtítulos o secciones numeradas, sino un texto fluido y bien estructurado.
    """
    
    try:
        # Usar client.chat.completions.create para llamar a la API
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un consultor estratégico senior especializado en evaluación y priorización de ideas innovadoras para grandes empresas tecnológicas y de ingeniería."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            timeout=60
        )
        
        if response and response.choices and response.choices[0].message:
            summary = response.choices[0].message.content.strip()
            # Limpiar el resumen para eliminar caracteres problemáticos
            clean_summary = clean_text_for_pdf(summary)
            # Guardar en caché
            _api_cache[cache_key] = clean_summary
            return clean_summary
        else:
            return "No se pudo generar un resumen ejecutivo del ranking. Por favor, revise los detalles individuales de cada idea."
            
    except Exception as api_error:
        print(f"❌ Error generando resumen del ranking: {str(api_error)}")
        return f"Error al generar el resumen ejecutivo: {str(api_error)}"

def generate_ranking(ideas_list, ranking_context="", max_workers=10, batch_size=None):
    """
    Genera un ranking basado en el análisis de las ideas, extrayendo métricas y calculando scores.
    Utiliza procesamiento en paralelo para reducir significativamente el tiempo de cálculo.
    
    Parámetros:
    - ideas_list: Lista de ideas a procesar
    - ranking_context: Contexto opcional para la priorización
    - max_workers: Número máximo de workers para procesamiento en paralelo (default: 10)
    - batch_size: Tamaño de lote para procesar ideas (default: None = procesar todas a la vez)
    """
    try:
        print(f"🔄 Iniciando generación de ranking en paralelo con {max_workers} workers...")
        
        # Verificar que tenemos un array de ideas no vacío
        if not ideas_list or not isinstance(ideas_list, list) or len(ideas_list) == 0:
            print("❌ No hay ideas para generar ranking")
            return []
            
        # Preparar información para el rankeo
        ranked_ideas = []
        
        # Función para procesar una idea individual (para paralelización)
        def process_single_idea(idea_data):
            idea_index, idea = idea_data
            try:
                # Convertir a formato estándar si es necesario
                if isinstance(idea, str):
                    idea_text = idea
                    analysis_text = ""
                    idea_obj = {"idea": idea_text}
                elif isinstance(idea, dict):
                    idea_text = str(idea.get('idea', ''))
                    # Intentar obtener el análisis existente
                    analysis_text = str(idea.get('analysis', ''))
                    idea_obj = idea
                else:
                    return {
                        "error": True,
                        "message": f"Formato de idea {idea_index} no reconocido",
                        "index": idea_index
                    }
                
                # Verificar que tengamos una idea con contenido
                if not idea_text or len(idea_text.strip()) < 10:
                    return {
                        "error": True,
                        "message": f"Idea {idea_index} está vacía o es demasiado corta",
                        "index": idea_index
                    }
                    
                # Sanitizar el texto de análisis para evitar problemas de formato
                if analysis_text:
                    # Reemplazar caracteres que podrían causar problemas en strings formateados
                    analysis_text = analysis_text.replace('%', '%%')
                    analysis_text = analysis_text.replace('{', '{{').replace('}', '}}')
                
                # Si no hay análisis, generar un análisis simplificado
                if not analysis_text or len(analysis_text.strip()) < 100:
                    analysis_text = generate_simplified_analysis(idea_text)
                    if analysis_text:
                        # Sanitizar el análisis generado
                        analysis_text = analysis_text.replace('%', '%%')
                        analysis_text = analysis_text.replace('{', '{{').replace('}', '}}')
                    
                    if not analysis_text or "Error" in analysis_text:
                        # Incluir la idea con un score bajo por defecto
                        return {
                            "idea": idea_text,
                            "title": idea_text[:50] + "..." if len(idea_text) > 50 else idea_text,
                            "score": 25, # Score bajo por defecto cuando no hay análisis
                            "justification": "No se pudo generar un análisis para esta idea",
                            "index": idea_index
                        }
                
                # CAMBIO RADICAL: Creamos un análisis simplificado para las métricas y evitamos usar justificaciones
                try:
                    # Extraer métricas del análisis con cache para evitar llamadas duplicadas
                        # Pero modificamos cómo manejamos las métricas para evitar el problema de formato
                    metrics = extract_metrics_from_analysis(analysis_text, idea_text, ranking_context)
                        
                        # IMPORTANTE: Eliminar completamente la justificación para evitar problemas
                    if 'justificacion' in metrics:
                            del metrics['justificacion']
                    
                    # Generar evaluación cualitativa (50% de la puntuación)
                    print(f"ℹ️ Generando evaluación cualitativa para idea {idea_index}...")
                    qualitative_eval = generate_qualitative_evaluation(idea_text, analysis_text, ranking_context)
                    
                        # Sanitizar la justificación cualitativa
                    if qualitative_eval and 'justification' in qualitative_eval:
                            qualitative_eval['justification'] = str(qualitative_eval.get('justification', '')).replace('%', '%%').replace('{', '{{').replace('}', '}}')
                        
                    # Incorporar la evaluación cualitativa en las métricas
                    if qualitative_eval and 'score' in qualitative_eval:
                        # Convertir la puntuación de 0-100 a 1-5 para integrarla con las métricas
                        metrics['evaluacion_cualitativa'] = (qualitative_eval['score'] / 100) * 4 + 1
                    
                    # Calcular score basado en las métricas (50% cuantitativo, 50% cualitativo)
                    score_data = calculate_final_score(metrics)
                    
                    # Actualizar score_data con información de la evaluación cualitativa
                    if qualitative_eval and 'justification' in qualitative_eval:
                        score_data['qualitative_justification'] = qualitative_eval['justification']
                    
                        # Asegurar que las métricas en score_data están sanitizadas
                        if 'metrics' in score_data:
                            # Eliminar justificaciones problemáticas
                            if isinstance(score_data['metrics'], dict) and 'justificacion' in score_data['metrics']:
                                del score_data['metrics']['justificacion']
                        
                        # CAMBIO: Pasamos métricas sanitizadas a generate_justification_v2
                        score_data['metrics'] = metrics  # Métricas ya sanitizadas
                        
                    # Generar justificación personalizada
                    justification = generate_justification_v2(idea_text, analysis_text, score_data, ranking_context)
                    
                        # Sanitizar la justificación final
                    if justification:
                            justification = str(justification).replace('%', '%%').replace('{', '{{').replace('}', '}}')
                        
                    # CAMBIO: Calcular valores de effort y benefit después de tener todos los análisis
                    effort_value, benefit_value = calculate_payoff_matrix_values(
                        idea_text, 
                        analysis_text, 
                        metrics, 
                        score_data
                    )
                    
                    # Generar visualización de la puntuación
                    wheel_img = generate_score_wheel(score_data['score'])
                    
                    # 🔥 CREAR TÍTULO PRESERVANDO EL TÍTULO REAL DE LA IDEA
                    # Priorizar el título existente en la idea original
                    title = idea_obj.get('title', '') if isinstance(idea_obj, dict) else ''
                    
                    # Solo extraer de la primera línea si NO hay título real
                    if not title or title.strip() == "":
                        first_line = idea_text.split('\n')[0] if idea_text else ""
                        # Limpiar prefijos "Idea X:" de la primera línea
                        import re
                        clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                        title = clean_title[:80] if clean_title else f"Idea {idea_index}"
                        
                    # Asegurar que no sea demasiado largo
                    if len(title) > 100:
                        title = title[:100] + "..."
                        
                    # Sanitizar título
                    title = title.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                    
                    # 🔥 DEBUG: Mostrar qué título se está usando
                    print(f"🔥 [RANKING] Idea {idea_index}: título final='{title}' (original: '{idea_obj.get('title', 'NO_TITLE') if isinstance(idea_obj, dict) else 'NO_DICT'}')")
                        
                    return {
                        "idea": idea_text,
                        "analysis": analysis_text,
                        "title": title,
                        "score": score_data['score'],
                        "score_quantitative": score_data.get('score_quantitative', 0),
                        "score_qualitative": score_data.get('score_qualitative', 0),
                        "dimension_tecnica": score_data.get('dimension_tecnica', 0),
                        "dimension_economica": score_data.get('dimension_economica', 0), 
                        "dimension_mercado": score_data.get('dimension_mercado', 0),
                        "evaluacion_cualitativa": score_data.get('evaluacion_cualitativa', 0),
                        "metrics": metrics,
                        "justification": justification,
                        "wheel_img": wheel_img,
                        "index": idea_index,
                            "effort": effort_value,
                            "benefit": benefit_value
                        }
                except Exception as inner_e:
                        # Capturar errores específicos del proceso de métricas y justificación
                        print(f"⚠️ Error en el proceso de métricas para idea {idea_index}: {str(inner_e)}")
                        traceback.print_exc()
                        
                        # PLAN B: Si fallan las métricas, crear un resultado básico sin usar justificaciones problemáticas
                        return {
                            "idea": idea_text,
                            "analysis": analysis_text,
                            "title": idea_text[:50] + "..." if len(idea_text) > 50 else idea_text,
                            "score": 50,  # Puntuación neutral
                            "score_quantitative": 50,
                            "score_qualitative": 50,
                            "dimension_tecnica": 50,
                            "dimension_economica": 50, 
                            "dimension_mercado": 50,
                            "justification": f"No se pudo generar una justificación detallada debido a un error interno. El análisis está disponible, pero se requiere evaluación manual.",
                            "index": idea_index,
                            "effort": 50,
                            "benefit": 50
                    }
                
            except Exception as e:
                # Capturar errores a nivel de idea individual
                error_msg = str(e)
                
                # Sanitizar mensaje de error para evitar problemas de formato
                error_msg = error_msg.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                
                print(f"⚠️ Error al procesar idea {idea_index}: {error_msg}")
                traceback.print_exc()
                
                return {
                    "error": True,
                    "message": f"Error al procesar idea {idea_index}: {error_msg}",
                    "index": idea_index,
                    "exception": error_msg
                }
        
        # Si hay un tamaño de lote, procesar las ideas en lotes
        if batch_size and batch_size > 0 and batch_size < len(ideas_list):
            batches = [ideas_list[i:i+batch_size] for i in range(0, len(ideas_list), batch_size)]
            print(f"🔄 Procesando ideas en {len(batches)} lotes de {batch_size} ideas...")
            
            for batch_num, batch in enumerate(batches, 1):
                print(f"🔄 Procesando lote {batch_num}/{len(batches)} ({len(batch)} ideas)...")
                
                # Crear lista de tuplas (índice, idea) para este lote
                indexed_batch = [(i + (batch_num-1)*batch_size, idea) for i, idea in enumerate(batch, 1)]
                
                # Procesar el lote actual en paralelo
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(batch))) as executor:
                    batch_results = list(tqdm(
                        executor.map(process_single_idea, indexed_batch),
                        total=len(batch),
                        desc=f"Lote {batch_num}"
                    ))
                
                # Filtrar resultados válidos y manejar errores
                for result in batch_results:
                    if result and isinstance(result, dict):
                        if result.get("error"):
                            print(f"⚠️ {result.get('message', 'Error desconocido')}")
                        else:
                            ranked_ideas.append(result)
                
                print(f"✅ Lote {batch_num} completado: {len(batch_results)} ideas procesadas")
        
        else:
            # Procesar todas las ideas en paralelo de una vez
            # Crear lista de tuplas (índice, idea)
            indexed_ideas = [(i, idea) for i, idea in enumerate(ideas_list, 1)]
            
            # Usar ThreadPoolExecutor para paralelizar el procesamiento
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(ideas_list))) as executor:
                # Usar tqdm para mostrar progreso
                results = list(tqdm(
                    executor.map(process_single_idea, indexed_ideas),
                    total=len(ideas_list),
                    desc="Procesando ideas"
                ))
            
            # Filtrar resultados válidos
            for result in results:
                if result and isinstance(result, dict):
                    if result.get("error"):
                        print(f"⚠️ {result.get('message', 'Error desconocido')}")
                    else:
                        ranked_ideas.append(result)
        
        # Ordenar ideas por puntuación
        ranked_ideas.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        print(f"✅ Ranking completado: {len(ranked_ideas)} ideas procesadas")
        return ranked_ideas
        
    except Exception as e:
        print(f"❌ Error general generando ranking: {str(e)}")
        traceback.print_exc()
        return []

# Función optimizada para el procesamiento en lotes de LLM
def process_ideas_batch_optimized(ideas_batch, system_prompt, user_prompt_template, temperature=0.7, max_tokens=2000):
    """
    Procesa un lote de ideas con una sola llamada a la API, reduciendo el número total de llamadas.
    
    Parámetros:
    - ideas_batch: Lista de ideas a procesar juntas
    - system_prompt: Prompt del sistema para la llamada API
    - user_prompt_template: Plantilla para el prompt de usuario (debe contener '{ideas}')
    - temperature: Temperatura para la llamada API
    - max_tokens: Tokens máximos para la respuesta
    
    Retorna:
    - Texto con los resultados combinados del procesamiento
    """
    try:
        # Validar entradas
        if not ideas_batch or not isinstance(ideas_batch, list):
            return "Error: No hay ideas para procesar en lote"
            
        if not user_prompt_template or "{ideas}" not in user_prompt_template:
            return "Error: La plantilla debe contener '{ideas}'"
            
        # Construir el contenido de las ideas
        ideas_content = "\n\n".join([
            f"IDEA #{i}:\n{idea}" 
            for i, idea in enumerate(ideas_batch, 1)
        ])
        
        # Construir el prompt completo
        user_prompt = user_prompt_template.format(ideas=ideas_content)
        
        # Realizar una única llamada a la API para todo el lote
        try:
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120  # Aumentar timeout para lotes grandes
            )
            
            if response and response.choices and response.choices[0].message:
                return response.choices[0].message.content.strip()
            else:
                return "Error: Respuesta vacía de la API"
        except Exception as api_error:
            print(f"❌ Error en llamada a API para lote: {str(api_error)}")
            traceback.print_exc()
            return f"Error en procesamiento de lote: {str(api_error)}"
            
    except Exception as e:
        print(f"❌ Error general en procesamiento por lotes: {str(e)}")
        traceback.print_exc()
        return f"Error en procesamiento: {str(e)}"

# Optimización del cliente de OpenAI para reducir sobrecarga de conexión
def optimize_openai_client():
    """
    Optimiza la configuración del cliente de OpenAI para reducir latencia y mejorar rendimiento.
    """
    try:
        from openai import OpenAI
        import httpx
        
        # Crear un cliente HTTPX optimizado con connection pooling y keepalive
        http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            http2=True
        )
        
        # Crear un cliente OpenAI con el cliente HTTP optimizado
        optimized_client = OpenAI(http_client=http_client)
        
        print("✅ Cliente OpenAI optimizado configurado")
        return optimized_client
    except Exception as e:
        print(f"⚠️ No se pudo optimizar cliente OpenAI: {str(e)}")
        return None

# Cache para almacenar llamadas a la API y evitar repeticiones
_api_cache = {}

def cached_api_call(prompt_key, call_function, *args, **kwargs):
    """
    Realiza una llamada a la API con caché para evitar llamadas repetidas.
    
    Parámetros:
    - prompt_key: Clave única para esta llamada (normalmente el prompt)
    - call_function: Función que realiza la llamada a la API
    - args, kwargs: Argumentos para la función
    
    Retorna:
    - Resultado de la función, ya sea desde caché o de una nueva llamada
    """
    global _api_cache
    
    # Generar un hash de la clave del prompt
    key_hash = hashlib.md5(prompt_key.encode()).hexdigest()
    
    # Verificar si ya tenemos este resultado en caché
    if key_hash in _api_cache:
        print(f"🔄 Usando resultado en caché para llamada a API")
        return _api_cache[key_hash]
    
    # Si no está en caché, realizar la llamada
    result = call_function(*args, **kwargs)
    
    # Almacenar en caché
    _api_cache[key_hash] = result
    
    return result

def generate_score_wheel(score):
    """
    Genera una visualización en forma de rueda polar para una puntuación
    con gradientes de color según rangos de puntuación
    """
    try:
        # Crear figura con fondo transparente
        fig = plt.figure(figsize=(6, 6), facecolor='none')
        ax = fig.add_subplot(111, polar=True)
        
        # Definir rangos de puntuación y sus colores correspondientes
        # Usamos una escala de colores personalizada
        if score < 30:
            color = '#FF5252'  # Rojo para puntuaciones bajas
        elif score < 50:
            color = '#FFA726'  # Naranja para puntuaciones medias-bajas
        elif score < 70:
            color = '#FFEB3B'  # Amarillo para puntuaciones medias
        elif score < 85:
            color = '#66BB6A'  # Verde claro para puntuaciones buenas
        else:
            color = '#00C853'  # Verde intenso para puntuaciones excelentes
        
        # Normalizar puntuación a radianes (0-100 a 0-2π)
        score_radians = (score / 100) * 2 * np.pi
        
        # Crear un gradiente para la rueda
        cmap = plt.cm.get_cmap('RdYlGn')
        colors = [cmap(i) for i in np.linspace(0, 1, 100)]
        
        # Dibujar la rueda con colores degradados
        bars = ax.bar(
            x=np.linspace(0, 2*np.pi, 100),
            height=np.ones(100),
            width=2*np.pi/100,
            color=colors,
            alpha=0.6
        )
        
        # Añadir la puntuación actual (barra de puntuación)
        positions = np.linspace(0, score_radians, 50)
        heights = np.ones(50) * 0.9
        ax.bar(positions, heights, width=score_radians/50, color=color, alpha=0.9)
        
        # Personalizar la gráfica
        ax.set_xticks([0, np.pi/2, np.pi, 3*np.pi/2])
        ax.set_xticklabels(['100', '75', '50', '25'])
        ax.set_yticks([])
        
        # Ajustar límites
        ax.set_ylim(0, 1.2)
        
        # Añadir puntuación en el centro
        ax.text(0, 0, f"{score:.1f}", fontsize=22, fontweight='bold', ha='center', va='center')
        
        # Remover fondo y spines 
        ax.set_facecolor('none')
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # Guardar la imagen en un objeto BytesIO para permitir su uso en PDF
        img_stream = BytesIO()
        plt.savefig(img_stream, format='png', bbox_inches='tight', transparent=True, dpi=100)
        img_stream.seek(0)
        plt.close()
        
        return img_stream
    except Exception as e:
        print(f"❌ Error generando visualización de puntuación: {str(e)}")
        traceback.print_exc()
        return None

class RankingModule:
    def __init__(self):
        self.ideas = []
        self.ideas_file = "ranked_ideas.json"
        self._load_ideas()
        
    def _load_ideas(self):
        """
        Carga las ideas desde el archivo JSON
        """
        try:
            if os.path.exists(self.ideas_file):
                try:
                    with open(self.ideas_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if not content:
                            self.ideas = []
                            return
                        
                        loaded_ideas = json.loads(content)
                        if not isinstance(loaded_ideas, list):
                            self.ideas = []
                            self._save_ideas()
                            return
                        
                        # Validar y limpiar ideas cargadas
                        self.ideas = [self._clean_idea(idea) for idea in loaded_ideas if isinstance(idea, dict)]
                except json.JSONDecodeError:
                    self.ideas = []
                    self._save_ideas()
                except Exception as e:
                    self.ideas = []
            else:
                self.ideas = []
                self._save_ideas()
        except Exception as e:
            self.ideas = []

    def _clean_idea(self, idea: dict) -> dict:
        """
        Limpia una idea para asegurar que es serializable
        """
        clean = {}
        try:
            # Solo mantener campos esenciales
            if "idea" in idea:
                clean["idea"] = str(idea["idea"])
            if "score" in idea:
                clean["score"] = float(idea["score"])
            if "title" in idea:
                clean["title"] = str(idea["title"])
                
            # Excluir explícitamente campos problemáticos
            exclude = ["wheel_img", "bytes_io", "image"]
            for key, value in idea.items():
                if key not in exclude and key not in clean:
                    try:
                        # Intentar serializar para verificar si es válido
                        json.dumps({key: value})
                        clean[key] = value
                    except:
                        # Si no es serializable, convertir a string
                        clean[key] = str(value)
                        
            return clean
        except Exception as e:
            print(f"Error limpiando idea: {str(e)}")
            return {"idea": str(idea.get("idea", "")), "score": float(idea.get("score", 0))}
            
    def _save_ideas(self):
        """
        Guarda las ideas en formato JSON
        """
        try:
            # Limpiar ideas antes de guardar
            clean_ideas = [self._clean_idea(idea) for idea in self.ideas]
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(self.ideas_file) if os.path.dirname(self.ideas_file) else '.', exist_ok=True)
            
            with open(self.ideas_file, 'w', encoding='utf-8') as f:
                json.dump(clean_ideas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Error guardando ideas: {str(e)}")
            traceback.print_exc()

    def update_rankings(self, new_ideas: List[Dict[str, Any]]):
        """
        Actualiza la lista de ideas con nuevos rankings
        """
        try:
            if not new_ideas:
                return False
                
            # Limpiar nuevas ideas
            self.ideas = [self._clean_idea(idea) for idea in new_ideas if isinstance(idea, dict)]
            
            # Guardar cambios
            self._save_ideas()
            
            print(f"✅ Rankings actualizados: {len(self.ideas)} ideas disponibles para análisis")
            return True
        except Exception as e:
            print(f"❌ Error actualizando rankings: {str(e)}")
            traceback.print_exc()
            return False

    def get_ranked_ideas(self) -> List[Dict[str, Any]]:
        """
        Retorna la lista de ideas rankeadas ordenadas por puntuación
        """
        try:
            # Recargar ideas del archivo para asegurar datos actualizados
            self._load_ideas()
            
            # Ordenar ideas por puntuación de mayor a menor
            return sorted(
                self.ideas,
                key=lambda x: float(x.get('score', 0)),
                reverse=True
            )
        except Exception as e:
            print(f"❌ Error obteniendo ideas rankeadas: {str(e)}")
            traceback.print_exc()
            return []

    def add_idea(self, idea: Dict[str, Any]):
        """
        Añade una nueva idea al ranking
        """
        try:
            if not isinstance(idea, dict) or 'idea' not in idea or 'score' not in idea:
                print("Formato de idea inválido")
                return False
            
            # Limpiar la idea antes de agregarla
            cleaned_idea = {
                'idea': str(idea['idea']),
                'score': float(idea['score'])
            }
            # Agregar otros campos si son serializables
            for key, value in idea.items():
                if key not in ['idea', 'score']:
                    try:
                        json.dumps(value)
                        cleaned_idea[key] = value
                    except (TypeError, OverflowError):
                        cleaned_idea[key] = str(value)
            
            self.ideas.append(cleaned_idea)
            self._save_ideas()
            print(f"Idea añadida correctamente: {cleaned_idea['idea'][:50]}...")
            return True
        except Exception as e:
            print(f"Error añadiendo idea: {str(e)}")
            return False

    def clear_rankings(self):
        """
        Limpia todas las ideas rankeadas
        """
        try:
            self.ideas = []
            self._save_ideas()
            print("Rankings limpiados correctamente")
            return True
        except Exception as e:
            print(f"Error limpiando rankings: {str(e)}")
            return False

# Nueva función para calcular effort y benefit después de análisis completo
def calculate_payoff_matrix_values(idea_text, analysis_text, metrics, score_data):
    """
    Calcula los valores de effort y benefit para la payoff matrix después de tener
    el análisis completo, evitando ambigüedades y con criterios determinantes.
    
    Parámetros:
    - idea_text: Texto de la idea
    - analysis_text: Análisis completo generado para la idea
    - metrics: Métricas extraídas del análisis
    - score_data: Datos de puntuación calculados
    
    Retorna:
    - effort: Valor de esfuerzo (0-100)
    - benefit: Valor de beneficio (0-100)
    """
    try:
        # Validar la entrada
        if not idea_text or not analysis_text:
            return 50, 50  # Valores neutrales por defecto
            
        # Sanitizar textos para evitar problemas de formato
        safe_idea_text = idea_text
        if isinstance(idea_text, str):
            safe_idea_text = idea_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
        safe_analysis_text = analysis_text
        if isinstance(analysis_text, str):
            safe_analysis_text = analysis_text.replace('%', '%%').replace('{', '{{').replace('}', '}}')
        
        # Crear una clave única para caché
        cache_key = f"payoff_matrix_{hashlib.md5((idea_text[:300] + analysis_text[:300]).encode()).hexdigest()}"
        
        # Verificar si ya tenemos este resultado en caché
        if cache_key in _api_cache:
            print(f"🔄 Usando valores de payoff matrix en caché")
            return _api_cache[cache_key]["effort"], _api_cache[cache_key]["benefit"]
        
        # Preparar información relevante de las métricas y puntuaciones para el prompt
        metric_info = ""
        if metrics:
            # Sanitizar métricas para formato seguro
            safe_metrics = {}
            for key, value in metrics.items():
                if isinstance(value, str):
                    safe_metrics[key] = value.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                else:
                    safe_metrics[key] = value
            
            metric_info += "MÉTRICAS TÉCNICAS:\n"
            metric_info += f"- Riesgo técnico: {safe_metrics.get('riesgo_tecnico', 'N/A')}/5\n"
            metric_info += f"- Tiempo de desarrollo: {safe_metrics.get('tiempo_desarrollo', 'N/A')}/5\n"
            metric_info += f"- TRL inicial: {safe_metrics.get('trl_inicial', 'N/A')}/9\n"
            metric_info += f"- TRL final: {safe_metrics.get('trl_final', 'N/A')}/9\n"
            
            metric_info += "\nMÉTRICAS ECONÓMICAS Y DE MERCADO:\n"
            metric_info += f"- Ratio costes/ingresos: {safe_metrics.get('ratio_costes_ingresos', 'N/A')}/5\n"
            metric_info += f"- Ingresos previstos: {safe_metrics.get('ingresos_previstos', 'N/A')}/5\n"
            metric_info += f"- Retorno de inversión: {safe_metrics.get('payback_roi', 'N/A')}/5\n"
            metric_info += f"- Tamaño de mercado: {safe_metrics.get('tamano_mercado', 'N/A')}/5\n"
            metric_info += f"- Riesgo de mercado: {safe_metrics.get('riesgo_mercado', 'N/A')}/5\n"
            metric_info += f"- Alineación estratégica: {safe_metrics.get('alineacion_estrategica', 'N/A')}/5\n"
        
        score_info = ""
        if score_data:
            # Sanitizar score_data para formato seguro
            safe_score_data = {}
            for key, value in score_data.items():
                if isinstance(value, str):
                    safe_score_data[key] = value.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                else:
                    safe_score_data[key] = value
                    
            score_info += "\nPUNTUACIONES CALCULADAS:\n"
            score_info += f"- Puntuación global: {safe_score_data.get('score', 'N/A')}/100\n"
            score_info += f"- Dimensión técnica: {safe_score_data.get('dimension_tecnica', 'N/A')}/100\n"
            score_info += f"- Dimensión económica: {safe_score_data.get('dimension_economica', 'N/A')}/100\n"
            score_info += f"- Dimensión de mercado: {safe_score_data.get('dimension_mercado', 'N/A')}/100\n"
            score_info += f"- Evaluación cualitativa: {safe_score_data.get('score_qualitative', 'N/A')}/100\n"
        
        # Acortar análisis si es muy largo
        shortened_analysis = safe_analysis_text[:800] + "..." if len(safe_analysis_text) > 800 else safe_analysis_text
        
        # ID único para esta evaluación
        eval_id = f"payoff_matrix_{int(time.time())}_{random.randint(1000, 9999)}"
        
        prompt = f"""
        EVALUACIÓN ID: {eval_id}
        
        Como consultor especializado en evaluación estratégica de ideas innovadoras, necesito calcular los valores
        para una matriz de payoff para la siguiente idea, utilizando todos los análisis y métricas disponibles.
        
        IDEA:
        {safe_idea_text[:300]}...
        
        ANÁLISIS REALIZADO:
        {shortened_analysis}
        
        {metric_info}
        {score_info}
        
        INSTRUCCIONES PRECISAS:
        
        1. Evalúa el esfuerzo y beneficio para ubicar esta idea en el cuadrante apropiado de la matriz de payoff.
        
        2. VALORES DE "EFFORT" (ESFUERZO):
           - Evalúa recursos, tiempo, complejidad técnica, inversión, riesgos de implementación.
           - 0-25: Esfuerzo mínimo (implementación rápida, bajo coste, tecnología disponible)
           - 25-50: Esfuerzo moderado bajo
           - 50-75: Esfuerzo moderado alto
           - 75-100: Esfuerzo máximo (gran inversión, complejidad técnica extrema, años de desarrollo)
        
        3. VALORES DE "BENEFIT" (BENEFICIO):
           - Evalúa retorno financiero, impacto estratégico, ventaja competitiva, potencial de mercado.
           - 0-25: Beneficio mínimo (impacto marginal, ROI bajo, sin ventaja competitiva clara)
           - 25-50: Beneficio moderado bajo
           - 50-75: Beneficio moderado alto
           - 75-100: Beneficio máximo (transformador, ROI excepcional, ventaja competitiva disruptiva)
        
        CRITERIOS ESENCIALES:
        
        No dudes nunca: evalúa con determinación la innovación, la afinidad estratégica y los riesgos intangibles (p. ej. dependencia tecnológica, barreras regulatorias).
        
        No repitas valores: evita respuestas planas alrededor de 50 salvo que el caso esté irrefutablemente equilibrado. 
        
        Asignación precisa: utiliza valores específico. tienes +-1 , puedes ser lo preciso que quieras en las puntuaciones
        
        Clasificación definitiva: Se contundente y no abuses de la ambigudedas, como consultor experto tienes que polarizar mas las puntuaciones para que quede claro cual son las mejores y evita que las puntuaciones simopre esten el mismo cuadrante. Obviamnete si lo ves necesario si, pero solo si lo ves evidente
        
        Actua como profesional y puntua de forma justa clara 

        FORMATO DE RESPUESTA:
        Responde en formato JSON con la siguiente estructura exacta e incluye una justificación para cada valor:
        {{
          "effort": [valor de 0 a 100,],
          "benefit": [valor de 0 a 100,],
          "effort_justification": "[justificación detallada de effort]",
          "benefit_justification": "[justificación detallada de benefit]",
        }}
        """
        
        try:
            # Usar el cliente de OpenAI importado
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "Eres un consultor estratégico especializado en evaluación de innovación para grandes empresas tecnológicas y de ingeniería. Tomas decisiones firmes y evitas la ambigüedad."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # Temperatura baja para decisiones más determinantes
                max_tokens=1200,
                response_format={"type": "json_object"},
                timeout=60
            )
            
            if response and response.choices and response.choices[0].message:
                result_text = response.choices[0].message.content.strip()
                
                try:
                    # Limpiar texto y convertir a JSON
                    result_text = result_text.replace('```json', '').replace('```', '').strip()
                    result = json.loads(result_text)
                    
                    # Validar los campos requeridos
                    if "effort" not in result or "benefit" not in result:
                        print("⚠️ Respuesta de la API no contiene todos los campos necesarios")
                        return 50, 50
                    
                    # Validar rango de valores
                    effort = float(result["effort"])
                    if effort < 0 or effort > 100:
                        print(f"⚠️ Esfuerzo fuera de rango: {effort}, ajustando")
                        effort = max(0, min(100, effort))
                        
                    benefit = float(result["benefit"])
                    if benefit < 0 or benefit > 100:
                        print(f"⚠️ Beneficio fuera de rango: {benefit}, ajustando")
                        benefit = max(0, min(100, benefit))
                    
                    # Limitar al rango 0-100
                    effort = min(99, max(1, effort))  
                    benefit = min(99, max(1, benefit))
                    
                    # Sanitizar justificaciones para prevenir problemas de formato
                    effort_justification = result.get("effort_justification", "")
                    benefit_justification = result.get("benefit_justification", "")
                    
                    if isinstance(effort_justification, str):
                        effort_justification = effort_justification.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                        
                    if isinstance(benefit_justification, str):
                        benefit_justification = benefit_justification.replace('%', '%%').replace('{', '{{').replace('}', '}}')
                    
                    # Guardar en caché
                    _api_cache[cache_key] = {
                        "effort": effort,
                        "benefit": benefit,
                        "effort_justification": effort_justification,
                        "benefit_justification": benefit_justification,
                    }
                    
                    print(f"✅ Calculated payoff matrix values - Effort: {effort}, Benefit: {benefit}")
                    
                    return effort, benefit
                except json.JSONDecodeError as json_err:
                    print(f"❌ Error decodificando JSON: {str(json_err)}")
                    print(f"Respuesta: {result_text}")
                    return 50, 50
                    
            else:
                print("⚠️ Respuesta vacía de la API")
                return 50, 50
                
        except Exception as api_error:
            error_msg = str(api_error)
            # Sanitizar mensaje de error
            error_msg = error_msg.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
            print(f"❌ Error en la llamada a la API: {error_msg}")
            traceback.print_exc()
            return 50, 50
            
    except Exception as e:
        error_msg = str(e)
        # Sanitizar mensaje de error
        error_msg = error_msg.replace('%', '%%').replace('{', '{{').replace('}', '}}')
            
        print(f"❌ Error calculando valores de payoff matrix: {error_msg}")
        traceback.print_exc()
        return 50, 50

def generate_idea_summary(idea_text, max_chars=350):
    """
    Genera un resumen inteligente de una idea larga para el PDF de ranking.
    
    Args:
        idea_text (str): Texto completo de la idea
        max_chars (int): Máximo número de caracteres para el resumen
    
    Returns:
        str: Resumen optimizado para PDF
    """
    if not idea_text or len(idea_text) <= max_chars:
        return clean_text_for_pdf(idea_text)
    
    try:
        # Limpiar el texto primero
        clean_text = clean_text_for_pdf(idea_text)
        
        # Si aún es corto después de limpiar, devolverlo
        if len(clean_text) <= max_chars:
            return clean_text
        
        # Extraer el título/primera línea como base
        lines = clean_text.split('\n')
        title = lines[0].strip() if lines else ""
        
        # Buscar puntos clave usando IA para generar resumen
        from openai_config import get_openai_client, get_deployment_name
        client = get_openai_client()
        deployment_name = get_deployment_name()
        
        prompt = f"""
        Genera un resumen ejecutivo conciso de la siguiente idea en máximo 300 caracteres.
        
        REQUISITOS:
        - Máximo 300 caracteres (incluidos espacios)
        - Mantén la esencia y conceptos clave
        - Lenguaje técnico pero claro
        - Sin saltos de línea innecesarios
        - Elimina redundancias y detalles excesivos
        
        IDEA ORIGINAL:
        {clean_text[:1000]}
        
        RESUMEN EJECUTIVO (máximo 300 caracteres):
        """
        
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "Eres un experto en síntesis de ideas técnicas. Generas resúmenes precisos y concisos."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
            timeout=15
        )
        
        if response and response.choices and response.choices[0].message:
            summary = response.choices[0].message.content.strip()
            # Limpiar el resumen
            summary = clean_text_for_pdf(summary)
            
            # Verificar longitud y truncar si es necesario
            if len(summary) > max_chars:
                # Truncar en la última oración completa que quepa
                truncated = summary[:max_chars-3]
                last_period = truncated.rfind('.')
                last_comma = truncated.rfind(',')
                cut_point = max(last_period, last_comma)
                
                if cut_point > max_chars * 0.7:  # Al menos 70% del texto
                    summary = truncated[:cut_point + 1]
                else:
                    summary = truncated + "..."
            
            return summary
        
    except Exception as e:
        print(f"⚠️ Error generando resumen IA: {str(e)}")
    
    # Fallback: resumen manual si falla la IA
    clean_text = clean_text_for_pdf(idea_text)
    
    # Truncar en punto o coma más cercano
    if len(clean_text) > max_chars:
        truncated = clean_text[:max_chars-3]
        last_period = truncated.rfind('.')
        last_comma = truncated.rfind(',')
        cut_point = max(last_period, last_comma)
        
        if cut_point > max_chars * 0.6:  # Al menos 60% del texto
            return truncated[:cut_point + 1]
        else:
            return truncated + "..."
    
    return clean_text

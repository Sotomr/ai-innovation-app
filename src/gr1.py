# Silenciar todos los warnings
import warnings
warnings.filterwarnings('ignore')

import gradio as gr
import pandas as pd
import openai
import asyncio
import os
from excel_module import process_excel_file, generate_ideas_pdf
from pdf_processor_module import process_pdf_file, generate_pdf_from_ideas
from analysis_module2 import (
    get_analysis_template, 
    update_analysis_template, 
    analyze_ideas_batch as analyze_batch, 
    generate_improved_pdf,
    perform_analysis_module,
    get_analyzed_ideas,
    global_save_analyzed_ideas,
    analyze_idea_exhaustive,
    generate_challenges_and_solutions_pdf,
    get_global_analyzed_ideas
)
from ranking_module import generate_ranking, generate_ranking_pdf
from competitor_analysis_module import CompetitorAnalysis
import tempfile
from datetime import datetime
import json
import requests
from pathlib import Path
import sys
from fpdf import FPDF
import traceback
import re
from openai_config import get_openai_client, get_deployment_name
import spacy
from sklearn.metrics.pairwise import cosine_similarity
from pdf_generator import generate_analysis_pdf
from analysis_module import analysis_manager
from competitor_analysis_ui import CompetitorAnalysisUI
from competition_pdf_module import generate_competition_analysis_pdf

# Obtener el cliente de OpenAI
client = get_openai_client()
DEPLOYMENT_NAME = get_deployment_name()

# Crear una instancia del analizador de competencia
competitor_analyzer = CompetitorAnalysis()

# Global variables
ideas_list = []
idea_counter = 0
analyzed_ideas_global_ui = []  # Variable global para almacenar ideas analizadas
analysis_points_validated = None

# Variables globales para registro
terminal_log = []
log_limit = 50  # Limitar el número de líneas para evitar problemas de memoria

def set_ideas_list_safe(ideas):
    """
    Asigna la variable global ideas_list SOLO si es una lista de diccionarios válidos.
    Si recibe basura, la ignora y deja la variable vacía.
    """
    global ideas_list
    if isinstance(ideas, list):
        valid_ideas = [idea for idea in ideas if isinstance(idea, dict) and 'idea' in idea]
        if valid_ideas:
            ideas_list = valid_ideas
            print(f"✅ ideas_list actualizado: {len(valid_ideas)} ideas válidas")
        else:
            ideas_list = []
            print("⚠️ ideas_list no se actualizó: la lista recibida no contenía ideas válidas.")
    else:
        ideas_list = []
        print("⚠️ ideas_list no se actualizó: el objeto recibido no era una lista.")

def set_analyzed_ideas_global(ideas):
    """
    Establece la variable global de ideas analizadas.
    Esta función es utilizada por analysis_module2.py.
    Solo acepta listas de diccionarios válidos (con clave 'idea').
    Si recibe basura, la ignora y deja la variable global vacía.
    """
    global analyzed_ideas_global_ui
    # Filtrar solo dicts válidos
    if isinstance(ideas, list):
        valid_ideas = [idea for idea in ideas if isinstance(idea, dict) and 'idea' in idea]
        analyzed_ideas_global_ui = valid_ideas
        set_ideas_list_safe(valid_ideas)
        if valid_ideas:
            print(f"✅ Ideas analizadas guardadas globalmente: {len(valid_ideas)} ideas")
        else:
            analyzed_ideas_global_ui = []
            print("⚠️ No se guardaron ideas: la lista recibida no contenía ideas válidas.")
    else:
        analyzed_ideas_global_ui = []
        set_ideas_list_safe([])
        print("⚠️ No se guardaron ideas: el objeto recibido no era una lista.")
    return True

def get_analyzed_ideas_global():
    """
    Recupera las ideas analizadas de la variable global.
    Esta función es utilizada por analysis_module2.py.
    Siempre devuelve una lista de diccionarios válidos.
    Si detecta basura, la ignora y lo notifica por log.
    """
    global analyzed_ideas_global_ui
    # Si hay ideas analizadas y es una lista de dicts válidos, devolverlas
    if analyzed_ideas_global_ui and isinstance(analyzed_ideas_global_ui, list):
        valid_ideas = [idea for idea in analyzed_ideas_global_ui if isinstance(idea, dict) and 'idea' in idea and 'analysis' in idea]
        if len(valid_ideas) != len(analyzed_ideas_global_ui):
            print("⚠️ Se detectaron objetos no válidos en analyzed_ideas_global_ui. Fueron ignorados.")
        if valid_ideas:
            return valid_ideas
    # Si no hay ideas analizadas globales pero sí ideas en la lista principal, devolverlas si son válidas
    global ideas_list
    if ideas_list and isinstance(ideas_list, list):
        valid_ideas = [idea for idea in ideas_list if isinstance(idea, dict) and 'idea' in idea and 'analysis' in idea]
        if len(valid_ideas) != len(ideas_list):
            print("⚠️ Se detectaron objetos no válidos en ideas_list. Fueron ignorados.")
        if valid_ideas:
            return valid_ideas
    # Si no hay nada válido, devolver lista vacía
    print("⚠️ No se encontraron ideas válidas en memoria global.")
    return []

def update_idea_counter(count):
    """Update the global idea counter."""
    global idea_counter
    try:
        idea_counter = int(count)
    except ValueError:
        print("Error: El contador debe ser un número")
        return False
    return True

def clean_global_memory():
    """
    🔥 NUEVA FUNCIÓN: Limpia la memoria global de ideas para forzar regeneración
    """
    global ideas_list, analyzed_ideas_global_ui, idea_counter
    ideas_list = []
    analyzed_ideas_global_ui = []
    idea_counter = 0
    print("🧹 Memoria global de ideas limpiada - se forzará regeneración completa")
    return True

def validate_idea_format(idea):
    """
    Valida que una idea tenga el formato correcto
    """
    if isinstance(idea, str):
        return {'idea': idea, 'analysis': '', 'metrics': {}}
    elif isinstance(idea, dict) and 'idea' in idea:
        return {
            'idea': str(idea['idea']),
            'analysis': str(idea.get('analysis', '')),
            'metrics': idea.get('metrics', {})
        }
    return None

def validate_ideas_list(ideas):
    """
    Valida y limpia la lista de ideas
    """
    if not ideas or not isinstance(ideas, list):
        return []
    
    validated_ideas = []
    for idea in ideas:
        valid_idea = validate_idea_format(idea)
        if valid_idea:
            validated_ideas.append(valid_idea)
    
    return validated_ideas

def process_excel_direct(excel_file, context=None):
    """Process Excel file and return status message."""
    if not excel_file:
        return "❌ Error: No se ha seleccionado ningún archivo Excel", "0"
    
    try:
        # Validar archivo Excel
        if hasattr(excel_file, 'name'):
            excel_path = excel_file.name
        else:
            excel_path = str(excel_file)
            
        if not os.path.exists(excel_path):
            return "❌ Error: El archivo Excel no existe", "0"
        
        # Procesar Excel y extraer ideas
        ideas = process_excel_file(excel_path)
        if not ideas:
            return "❌ Error: No se encontraron ideas en el Excel", "0"
        
        # Validar y estructurar ideas
        validated_ideas = []
        for idea in ideas:
            if isinstance(idea, str):
                validated_ideas.append({
                    'idea': idea,
                    'analysis': '',
                    'metrics': {}
                })
            elif isinstance(idea, dict) and 'idea' in idea:
                validated_ideas.append({
                    'idea': str(idea['idea']),
                    'analysis': str(idea.get('analysis', '')),
                    'metrics': idea.get('metrics', {})
                })
        
        if not validated_ideas:
            return "❌ Error: No se encontraron ideas válidas", "0"
            # Actualizar ideas globales
        set_ideas_list_safe(validated_ideas)
        update_idea_counter(len(validated_ideas))
        
        # Generar PDF estructurado
        try:
            pdf_path = generate_ideas_pdf(validated_ideas)
            if not pdf_path or not os.path.exists(str(pdf_path)):
                return "❌ Error: No se pudo generar el PDF estructurado", str(len(validated_ideas))
        except Exception as e:
            print(f"Error generando PDF: {str(e)}")
            return "❌ Error: No se pudo generar el PDF estructurado", str(len(validated_ideas))
        
        return f"✅ Se procesaron {len(validated_ideas)} ideas del Excel correctamente", str(len(validated_ideas))
        
    except Exception as e:
        print(f"Error procesando Excel: {str(e)}")
        return f"❌ Error procesando Excel: {str(e)}", "0"

async def process_pdf_direct(pdf_file, context):
    """
    Procesa un PDF directamente y reestructura cada idea usando OpenAI
    """
    if pdf_file is None:
        return "Por favor, sube un archivo PDF.", "0"
    try:
        if context and context.strip():
            print(f"\n==== CONTEXTO RECIBIDO EN PROCESS_PDF_DIRECT ====")
            print(f"Contenido: {context}")
            print(f"Longitud: {len(context)} caracteres")
            print(f"=========================================\n")
        else:
            print("\n⚠️ No se proporcionó contexto en process_pdf_direct\n")
        ideas, status = process_pdf_file(pdf_file.name, context)
        if not ideas:
            return f"❌ {status}", "0"
        validated_ideas = []
        for idea in ideas:
            if isinstance(idea, dict):
                idea_text = str(idea.get('idea', ''))
                if '\n\n' in idea_text:
                    title, _ = idea_text.split('\n\n', 1)
                elif '\n' in idea_text:
                    title, _ = idea_text.split('\n', 1)
                else:
                    title = idea_text
                title = title.strip()
                
                # 🔥 LIMPIAR PREFIJOS DUPLICADOS EN EL ORIGEN
                import re
                # Eliminar patrones como "Idea 1: Idea 1:" o "IDEA X: IDEA X:"
                title = re.sub(r'^(idea\s*\d*[\.:]\s*){2,}', '', title, flags=re.IGNORECASE)
                # Eliminar un prefijo simple "Idea X:" que pueda quedar
                title = re.sub(r'^idea\s*\d*[\.:]\s*', '', title, flags=re.IGNORECASE)
                title = title.strip()
                if (len(title) < 4 or not re.search(r'[a-zA-Z]', title) or re.match(r'^[\d\W_]+$', title)):
                    print(f"⚠️ Idea descartada por título inválido: '{title}'")
                    continue
                if idea_text.strip():
                    validated_ideas.append({
                        'idea': idea_text,
                        'title': title,  # 🔥 GUARDAR TÍTULO LIMPIO
                        'analysis': '',
                        'original_order': idea.get('original_order', len(validated_ideas))
                    })
            elif isinstance(idea, str) and idea.strip():
                idea_text = idea.strip()
                if '\n\n' in idea_text:
                    title, _ = idea_text.split('\n\n', 1)
                elif '\n' in idea_text:
                    title, _ = idea_text.split('\n', 1)
                else:
                    title = idea_text
                title = title.strip()
                
                # 🔥 LIMPIAR PREFIJOS DUPLICADOS EN EL ORIGEN
                import re
                # Eliminar patrones como "Idea 1: Idea 1:" o "IDEA X: IDEA X:"
                title = re.sub(r'^(idea\s*\d*[\.:]\s*){2,}', '', title, flags=re.IGNORECASE)
                # Eliminar un prefijo simple "Idea X:" que pueda quedar
                title = re.sub(r'^idea\s*\d*[\.:]\s*', '', title, flags=re.IGNORECASE)
                title = title.strip()
                if (len(title) < 4 or not re.search(r'[a-zA-Z]', title) or re.match(r'^[\d\W_]+$', title)):
                    print(f"⚠️ Idea descartada por título inválido: '{title}'")
                    continue
                validated_ideas.append({
                    'idea': idea_text,
                    'title': title,  # 🔥 GUARDAR TÍTULO LIMPIO
                    'analysis': '',
                    'original_order': len(validated_ideas)
                })
        if not validated_ideas:
            return "❌ No se encontraron ideas válidas", "0"
        validated_ideas.sort(key=lambda x: x['original_order'])
        set_ideas_list_safe(validated_ideas)
        update_idea_counter(len(validated_ideas))
        return f"✅ Se procesaron y ordenaron {len(validated_ideas)} ideas correctamente", str(len(validated_ideas))
    except Exception as e:
        print(f"Error procesando PDF: {str(e)}")
        traceback.print_exc()
        return f"❌ Error al procesar el PDF: {str(e)}", "0"

def generate_combined_pdf():
    """NO hace nada, solo retorna error para evitar PDF de competencia en carga de documentos."""
    return None, "❌ Generación de PDF deshabilitada en carga de documentos."

def process_excel_with_context(excel_file, context):
    """
    Procesa un archivo Excel con contexto adicional
    """
    if excel_file is None:
        return "Por favor, sube un archivo Excel.", "0"
    
    try:
        # Procesar Excel y generar ideas
        ideas = process_excel_file(excel_file.name, context)
        
        if not ideas:
            return "❌ No se encontraron ideas en el Excel.", "0"
        
        # Actualizar ideas globales
        set_ideas_list_safe(ideas)
        update_idea_counter(len(ideas))
        
        return f"✅ Se han procesado {len(ideas)} ideas del Excel.", str(len(ideas))
    except Exception as e:
        return f"❌ Error al procesar el Excel: {str(e)}", "0"

def update_global_ideas(new_ideas_count):
    """Actualiza el contador global de ideas."""
    try:
        count = int(new_ideas_count) if new_ideas_count else 0
        return str(count)
    except ValueError:
        return "0"

def run_batch_analysis():
    """Ejecuta el análisis de las ideas cargadas."""
    terminal_output = []
    output_html = ""
    try:
        global ideas_list
        if not ideas_list:
            output_html = "❌ **Error:** No hay ideas cargadas para analizar."
            return output_html, None
        output_html = f"🔄 **Iniciando análisis de {len(ideas_list)} ideas...**"
        terminal_output.append(f"Iniciando análisis de {len(ideas_list)} ideas...")
        output_html += f"\n\n⏳ **Procesando ideas en lote...**"
        terminal_output.append("Procesando ideas en lote...")
        pdf_path = lote_analyze(ideas_list)
        print(f"[DEBUG UI] Path recibido de lote_analyze: {pdf_path} ({type(pdf_path)})")
        import os
        if pdf_path and isinstance(pdf_path, str) and os.path.exists(pdf_path):
            output_html = f"✅ **Análisis completado exitosamente.**\n\n{len(ideas_list)} ideas han sido analizadas.\n\nPuedes descargar el informe PDF usando el botón de abajo."
            terminal_output.append(f"✅ Análisis completado. Se han analizado {len(ideas_list)} ideas.")
            return output_html, pdf_path
        output_html += f"\n\n❌ **Error:** No se pudo generar el PDF o el archivo no existe."
        terminal_output.append("❌ Error: No se pudo generar el PDF o el archivo no existe.")
        return output_html, None
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error general: {error_msg}")
        import traceback
        traceback.print_exc()
        output_html = f"❌ **Error en el análisis:** {error_msg}\n\nRevisa los mensajes de error e intenta nuevamente."
        terminal_output.append(f"❌ Error en el análisis: {error_msg}")
        return output_html, None

def create_ranking_tab():
    """
    Crea la pestaña de ranking con visualización del top 5
    """
    with gr.Tab("🏆 Ranking de Ideas"):
        # Header profesional para la pestaña de ranking
        gr.HTML("""
        <div style="text-align: center; margin-bottom: 35px; padding: 30px; background: var(--tech-gradient-1); border-radius: 18px; border: 1px solid var(--tech-border-1); box-shadow: 0 20px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-glow-accent), inset 0 2px 0 rgba(255,255,255,0.08);">
            <div style="font-size: 4.5rem; margin-bottom: 20px;">🏆</div>
            <h2 style="color: var(--tech-warning); margin: 0; font-weight: 700; font-size: 2.2rem; text-shadow: 0 0 15px var(--tech-glow-primary);">Sistema de Ranking Inteligente</h2>
            <p style="color: var(--tech-text-secondary); font-size: 1.2rem; margin: 15px 0; font-weight: 500;">Priorización estratégica con matriz de payoff visual</p>
            <div style="height: 4px; width: 150px; background: var(--tech-gradient-3); margin: 20px auto; border-radius: 4px; box-shadow: 0 0 10px var(--tech-glow-accent);"></div>
            <p style="color: var(--tech-text-tertiary); font-size: 1rem; margin: 0;">📊 Scoring multidimensional • 🎯 Matriz esfuerzo vs beneficio • 📈 Visualización profesional</p>
        </div>
        """)
        
        # Incluir script JavaScript y estilos mejorados
        gr.HTML("""
        <script src="file=static/ranking_ui.js"></script>
        <style>
            .payoff-matrix-container {
                margin-top: 25px;
                background: var(--tech-gradient-1) !important;
                border-radius: 18px !important;
                padding: 25px !important;
                box-shadow: 0 15px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-border-1), inset 0 2px 0 rgba(255,255,255,0.08) !important;
                border: 1px solid var(--tech-border-1) !important;
                backdrop-filter: blur(15px) !important;
            }
            .payoff-matrix-title {
                font-weight: 700 !important;
                margin-bottom: 20px !important;
                font-size: 1.4em !important;
                color: var(--tech-warning) !important;
                text-align: center !important;
            }
            .payoff-matrix-explanation {
                margin: 20px 0 !important;
                padding: 20px !important;
                background: var(--tech-surface-2) !important;
                border-left: 2px solid var(--tech-warning) !important;
                border-radius: 12px !important;
                font-size: 0.95rem !important;
                line-height: 1.6 !important;
                box-shadow: 0 4px 15px var(--tech-shadow-1) !important;
                border: 1px solid var(--tech-border-1) !important;
            }
            .quadrant-explanation {
                margin-top: 12px !important;
                padding: 8px 0 !important;
                font-weight: 500 !important;
                color: var(--tech-text-secondary) !important;
            }
        </style>
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                # Descripción estilo análisis competitivo
                gr.HTML("""
                <div style="background: var(--tech-gradient-1); border-radius: 16px; padding: 25px; margin-bottom: 25px; box-shadow: 0 15px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-border-1), inset 0 2px 0 rgba(255,255,255,0.08); border: 1px solid var(--tech-border-1);">
                    <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
                        <div style="font-size: 2.5rem;">🏆</div>
                        <h3 style="color: var(--tech-warning); margin: 0; font-weight: 700; font-size: 1.6rem;">Proceso de Ranking Inteligente</h3>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px;">
                        <div style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--tech-surface-2); border-radius: 8px; border: 1px solid var(--tech-border-1);">
                            <div style="font-size: 1.2rem;">🟢</div>
                            <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.8rem;">Paso 1: Cargar Ideas</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--tech-surface-2); border-radius: 8px; border: 1px solid var(--tech-border-1);">
                            <div style="font-size: 1.2rem;">🎯</div>
                            <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.8rem;">Paso 2: Contexto</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--tech-surface-2); border-radius: 8px; border: 1px solid var(--tech-border-1);">
                            <div style="font-size: 1.2rem;">📊</div>
                            <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.8rem;">Paso 3: Generar</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--tech-surface-2); border-radius: 8px; border: 1px solid var(--tech-border-1);">
                            <div style="font-size: 1.2rem;">📈</div>
                            <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.8rem;">Paso 4: Visualizar</div>
                        </div>
                    </div>
                    <div style="padding: 15px; background: var(--tech-surface-3); border-radius: 12px; border-left: 2px solid var(--tech-warning); box-shadow: 0 4px 15px var(--tech-shadow-1);">
                        <p style="margin: 0; color: var(--tech-text-secondary); font-weight: 500; font-size: 0.95rem;">
                            🎯 <strong style="color: var(--tech-warning);">Resultado:</strong> Ranking multidimensional, matriz de payoff esfuerzo vs beneficio, clasificación en cuadrantes estratégicos y PDF ejecutivo
                        </p>
                    </div>
                </div>
                """)
                
                ranking_context = gr.TextArea(
                    label="Contexto de Priorización",
                    placeholder="Ejemplo: Quiero priorizar proyectos con impacto a corto plazo y que requieran inversión moderada...",
                    lines=3
                )
                
                generate_ranking_btn = gr.Button("🔄 Generar Ranking", variant="primary", elem_classes=["ranking-btn"])
                ranking_status = gr.Textbox(label="Estado", interactive=False)
                ranking_pdf = gr.File(label="PDF de Ranking", interactive=False)
            
            with gr.Column(scale=3):
                gr.Markdown("### Ideas Rankeadas")
                ranking_table = gr.Dataframe(
                    headers=["Posición", "Idea", "Puntuación"],
                    datatype=["number", "str", "number"],
                    col_count=(3, "fixed"),
                    interactive=False
                )
                
                # Añadir sección para la matriz de payoff
                with gr.Group(elem_classes=["payoff-matrix-container"]):
                    gr.Markdown("### Matriz de Payoff (Esfuerzo vs Beneficio)", elem_classes=["payoff-matrix-title"])
                    
                    # Explicación sobre la matriz de payoff mejorada
                    gr.HTML("""
                    <div class="payoff-matrix-explanation">
                        <strong style="color: var(--tech-text-primary);">Cómo interpretar la matriz:</strong>
                        <p style="color: var(--tech-text-secondary); margin: 10px 0;">Esta matriz muestra la relación entre el esfuerzo requerido y el beneficio potencial de cada idea, clasificándolas en 4 cuadrantes:</p>
                        <div class="quadrant-explanation" style="color: var(--tech-success);">🟢 <strong>Quick Win (Superior Izquierdo):</strong> Alto beneficio con bajo esfuerzo - Ideas a implementar inmediatamente</div>
                        <div class="quadrant-explanation" style="color: var(--tech-error);">🔴 <strong>Estratégico (Superior Derecho):</strong> Alto beneficio pero alto esfuerzo - Evaluar recursos disponibles</div>
                        <div class="quadrant-explanation" style="color: var(--tech-accent);">🔵 <strong>Mejoras (Inferior Izquierdo):</strong> Bajo beneficio con bajo esfuerzo - Implementar si hay tiempo</div>
                        <div class="quadrant-explanation" style="color: var(--tech-warning);">🟡 <strong>Descartar (Inferior Derecho):</strong> Bajo beneficio con alto esfuerzo - No seguir adelante</div>
                        <p style="color: var(--tech-text-secondary); margin: 10px 0;">Los números en la matriz corresponden a la posición de cada idea en el ranking.</p>
                    </div>
                    """)
                    
                    payoff_matrix_img = gr.Image(
                        label="Matriz de Payoff",
                        show_label=False,
                        visible=False,
                        elem_id="payoff-matrix-display"
                    )
                    
                    payoff_matrix_download = gr.File(
                        label="Descargar Matriz de Payoff",
                        visible=False,
                        elem_id="payoff-matrix-download"
                    )
        
        # Estilo personalizado para el botón y mensajes
        gr.HTML("""
        <style>
            .generate-ranking-btn {
                font-weight: bold !important;
                transition: all 0.3s ease !important;
            }
            .generate-ranking-btn:disabled {
                opacity: 0.7 !important;
                cursor: not-allowed !important;
            }
        </style>
        """)
        
        generate_ranking_btn.click(
            fn=generate_ranking_ui,
            inputs=[ranking_context],
            outputs=[ranking_status, ranking_pdf, ranking_table, payoff_matrix_img, payoff_matrix_download]
        )

def generate_ranking_ui(ranking_context):
    """
    Genera un ranking de ideas utilizando el módulo de ranking y actualiza la UI con los resultados
    """
    try:
        # Obtener ideas analizadas desde las funciones existentes
        analyzed_ideas = get_analyzed_ideas_global()
        
        # Si no hay ideas analizadas, intentar obtenerlas de la lista global de ideas
        if not analyzed_ideas or not isinstance(analyzed_ideas, list) or len(analyzed_ideas) == 0:
            # Intentar obtener ideas de la lista general
            global ideas_list
            if 'ideas_list' in globals() and ideas_list:
                print(f"📝 Usando lista de ideas sin analizar: {len(ideas_list)} ideas")
                
                # Verificar si alguna idea tiene análisis previo
                has_analysis = any(isinstance(idea, dict) and 'analysis' in idea and idea['analysis'] 
                                 for idea in ideas_list)
                
                if has_analysis:
                    print("✅ Se encontraron análisis previos en algunas ideas")
                else:
                    print("⚠️ Las ideas no tienen análisis previo, se generarán análisis simplificados")
                
                analyzed_ideas = ideas_list
            else:
                # Intentar obtener las ideas desde la función de obtención general
                try:
                    analyzed_ideas = get_analyzed_ideas()
                    print(f"📝 Obtenidas {len(analyzed_ideas) if analyzed_ideas else 0} ideas del almacén general")
                except:
                    analyzed_ideas = []
            
        if not analyzed_ideas or not isinstance(analyzed_ideas, list) or len(analyzed_ideas) == 0:
            print("🚫 No se encontraron ideas para rankear")
            return (
                "⚠️ No se encontraron ideas para rankear. Primero debes cargar y procesar ideas desde la pestaña 'Carga de Documentos'.",
                None,
                [],
                None,
                None
            )
            
        print(f"📊 Generando ranking con {len(analyzed_ideas)} ideas")
        
        # Asegurarse de que cada idea tenga el formato correcto
        ideas_with_analysis = []
        for i, idea in enumerate(analyzed_ideas):
            if isinstance(idea, str):
                # Convertir strings a diccionarios con formato correcto
                # 🔥 EXTRAER TÍTULO DESDE STRING
                first_line = idea.split('\n')[0] if idea else ""
                import re
                clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                title = clean_title[:80] if clean_title else f"Idea {i+1}"
                
                ideas_with_analysis.append({
                    "idea": idea,
                    "title": title,  # 🔥 TÍTULO EXTRAÍDO DE STRING
                    "analysis": "",  # Sin análisis previo
                    "original_index": i
                })
            elif isinstance(idea, dict) and 'idea' in idea:
                # 🔥 PRESERVAR TÍTULO Y ANÁLISIS EXISTENTES
                analysis = idea.get('analysis', '')
                title = idea.get('title', '')
                ideas_with_analysis.append({
                    "idea": idea['idea'],
                    "title": title,  # 🔥 PRESERVAR TÍTULO ORIGINAL
                    "analysis": str(analysis) if analysis else "",
                    "original_index": i
                })
            else:
                print(f"⚠️ Idea en posición {i} tiene formato no válido, omitiendo")
                
        if not ideas_with_analysis:
            return (
                "⚠️ No se encontraron ideas válidas para rankear.",
                None,
                [],
                None,
                None
            )
        
        # Generar el ranking usando el módulo
        try:
            from ranking_module import generate_ranking, RankingModule
            print(f"🔍 Llamando a generate_ranking con {len(ideas_with_analysis)} ideas")
            
            # Pasar las ideas con su análisis (si existe) para que extract_metrics_from_analysis pueda utilizarlo
            ranked_ideas = generate_ranking(ideas_with_analysis, ranking_context)
            
            # Verificar que tenemos ideas rankeadas
            if not ranked_ideas or not isinstance(ranked_ideas, list) or len(ranked_ideas) == 0:
                print("⚠️ No se generaron ideas rankeadas")
                return (
                    "⚠️ No se pudieron generar rankings para las ideas. Por favor, intenta de nuevo.",
                    None,
                    [],
                    None,
                    None
                )
            
            # Guardar las ideas rankeadas usando RankingModule
            ranking_module = RankingModule()
            ranking_module.update_rankings(ranked_ideas)
            print("✅ Ideas rankeadas guardadas correctamente")
                
            # Ordenar por puntuación (por si acaso no están ordenadas)
            ranked_ideas = sorted(ranked_ideas, key=lambda x: x.get('score', 0) if isinstance(x, dict) else 0, reverse=True)
            
            # Crear tabla para mostrar
            table_data = []
            for i, idea in enumerate(ranked_ideas, 1):
                if isinstance(idea, dict):
                    # Extraer el título de la idea
                    title = idea.get('title', '')
                    if not title and 'idea' in idea:
                        # Extraer título de la idea si no está definido explícitamente
                        idea_text = str(idea['idea'])
                        title = idea_text.split('\n')[0][:50] if '\n' in idea_text else idea_text[:50]
                        if len(title) >= 50:
                            title += "..."
                    
                    # Si aún no hay título, usar un título genérico
                    if not title:
                        title = f"Idea {i}"
                            
                    score = idea.get('score', 0)
                    table_data.append([i, title[:100] + "..." if len(title) > 100 else title, score])
            
            if not table_data:
                print("⚠️ No se pudo crear la tabla de datos")
                return ("⚠️ No se generaron rankings. Intenta de nuevo.", None, [], None, None)
            
            # Generar matriz de payoff
            from payoff_matrix_generator import generate_payoff_matrix, save_payoff_matrix_to_file
            try:
                print("🔄 Generando matriz de payoff para mostrar en UI...")
                # Guardar matriz como archivo para mostrar en la UI
                payoff_matrix_path = save_payoff_matrix_to_file(ranked_ideas)
                print(f"✅ Matriz de payoff generada en: {payoff_matrix_path}")
                
                # Asegurarnos de que la matriz será visible en la UI
                payoff_matrix_visible = gr.update(visible=True, value=payoff_matrix_path)
                payoff_matrix_download_visible = gr.update(visible=True, value=payoff_matrix_path)
            except Exception as e:
                print(f"⚠️ Error al generar matriz de payoff para UI: {str(e)}")
                payoff_matrix_path = None
                payoff_matrix_visible = gr.update(visible=False, value=None)
                payoff_matrix_download_visible = gr.update(visible=False, value=None)
            
            # Generar PDF de ranking
            from ranking_module import generate_ranking_pdf_improved
            pdf_path = generate_ranking_pdf_improved(ranked_ideas, ranking_context)
            
            # Verificar si se generó el PDF
            if pdf_path and os.path.exists(pdf_path):
                pdf_file = pdf_path
                success_message = f"✅ Ranking generado con éxito para {len(ranked_ideas)} ideas. Se ha creado un PDF con los resultados detallados y la matriz de payoff."
            else:
                pdf_file = None
                success_message = f"✅ Ranking generado con éxito para {len(ranked_ideas)} ideas, pero no se pudo crear el PDF."
            
            print(f"✅ Ranking completado exitosamente con {len(ranked_ideas)} ideas")
            
            # Actualizar ideas_list con las métricas y scores para usos posteriores
            for ranked_idea in ranked_ideas:
                # Buscar la idea original por su contenido
                original_idea_text = ranked_idea.get('idea', '')
                if not original_idea_text:
                    continue
                    
                for idea in ideas_list:
                    idea_text = idea['idea'] if isinstance(idea, dict) and 'idea' in idea else str(idea)
                    if idea_text == original_idea_text:
                        # Actualizar con los datos del ranking
                        if isinstance(idea, dict):
                            idea['score'] = ranked_idea.get('score', 0)
                            idea['metrics'] = ranked_idea.get('metrics', {})
                            # Preservar o actualizar el análisis
                            if 'analysis' in ranked_idea and ranked_idea['analysis'] and not idea.get('analysis'):
                                idea['analysis'] = ranked_idea['analysis']
                        break
            
            # Guardar ranked_ideas para uso futuro si es necesario
            global ranked_ideas_global
            ranked_ideas_global = ranked_ideas
            
            set_analyzed_ideas_global(ranked_ideas)
            
            return (success_message, pdf_file, table_data, payoff_matrix_visible, payoff_matrix_download_visible)
                
        except Exception as e:
            print(f"❌ Error al generar ranking: {str(e)}")
            import traceback
            traceback.print_exc()
            return (f"⚠️ Error: No se pudo generar el ranking. {str(e)}", None, [], gr.update(visible=False), gr.update(visible=False))
    
    except Exception as e:
        print(f"❌ Error general en UI de ranking: {str(e)}")
        import traceback
        traceback.print_exc()
        return (f"⚠️ Error en la interfaz: {str(e)}", None, [], gr.update(visible=False), gr.update(visible=False))

def create_competitor_tab():
    """
    Crea la pestaña de análisis de competencia
    """
    competitor_ui = CompetitorAnalysisUI()
    return competitor_ui.create_competitor_tab()

def get_analyzed_ideas():
    """
    Obtiene las ideas analizadas del estado global
    """
    global ideas_list
    return ideas_list

def process_pdf(pdf_file):
    """
    Procesa un archivo PDF y extrae las ideas
    """
    try:
        if pdf_file is None:
            return None, "No se ha seleccionado ningún archivo PDF"
        
        # Procesar el PDF
        ideas, message = process_pdf_file(pdf_file.name)
        if not ideas:
            return None, message
        
        # Generar PDF combinado
        pdf_path, status = generate_combined_pdf()
        if not pdf_path:
            return None, status
        
        return pdf_path, status
        
    except Exception as e:
        return None, f"Error al procesar el PDF: {str(e)}"

def create_document_upload_tab():
    """Crea la pestaña de carga de documentos con opciones para Excel y PDF."""
    with gr.Tab("📄 Carga de Documentos"):
        with gr.Column():
            # Header profesional para documentos
            gr.HTML("""
            <div style="text-align: center; margin-bottom: 35px; padding: 30px; background: var(--tech-gradient-1); border-radius: 18px; border: 1px solid var(--tech-border-1); box-shadow: 0 20px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-glow-accent), inset 0 2px 0 rgba(255,255,255,0.08);">
                <div style="font-size: 4.5rem; margin-bottom: 20px;">📄</div>
                <h2 style="color: var(--tech-text-primary); margin: 0; font-weight: 700; font-size: 2.2rem; text-shadow: 0 0 15px var(--tech-glow-primary);">Procesamiento de Documentos</h2>
                <p style="color: var(--tech-text-secondary); font-size: 1.2rem; margin: 15px 0; font-weight: 500;">Carga y analiza archivos PDF y Excel con tecnología de inteligencia artificial</p>
                <div style="height: 4px; width: 150px; background: var(--tech-gradient-3); margin: 20px auto; border-radius: 4px; box-shadow: 0 0 10px var(--tech-glow-accent);"></div>
                <p style="color: var(--tech-text-tertiary); font-size: 1rem; margin: 0;">📊 Detección automática • 🤖 Análisis con IA • 📈 Informes profesionales</p>
            </div>
            """)
            
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 📑 PDF", elem_classes="reduced-subheading")
                    pdf_file = gr.File(
                        label="Archivo PDF",
                        file_types=[".pdf"],
                        elem_classes="file-input"
                    )
                    pdf_context = gr.Textbox(
                        label="Contexto (Opcional)",
                        placeholder="Describe el contexto para procesar el PDF...",
                        lines=3
                    )
                    pdf_button = gr.Button(
                        "📥 Procesar PDF", 
                        variant="primary",
                        size="lg",
                        elem_classes="process-btn"
                    )
                    pdf_status = gr.Textbox(
                        label="Estado",
                        interactive=False,
                        elem_classes="status-box"
                    )
            
            with gr.Row(equal_height=True):
                ideas_counter = gr.Number(
                    label="💡 Ideas Procesadas",
                    value=0,
                    interactive=False,
                    elem_classes="counter-box"
                )
        
        # Estilos CSS personalizados
        gr.Markdown("""
        <style>
        .file-input {
            border: 2px dashed #2980b9;
            border-radius: 8px;
            padding: 20px;
            margin: 10px 0;
        }
        .status-box {
            background-color: #f8f9fa;
            border-radius: 6px;
            padding: 10px;
            margin: 5px 0;
        }

        .reduced-heading h2 {
            font-size: 1.5rem !important;
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }
        .reduced-subheading h3 {
            font-size: 1.2rem !important;
            margin-top: 0.3rem !important;
            margin-bottom: 0.3rem !important;
        }
        </style>
        """)
        
        # Eventos
        pdf_button.click(
            fn=process_pdf_direct,
            inputs=[pdf_file, pdf_context],
            outputs=[pdf_status, ideas_counter]
        )

def create_analysis_tab():
    """Crea la pestaña de análisis para procesar las ideas cargadas."""
    with gr.Tab("📊 Análisis de Ideas"):
        # Header profesional para análisis
        gr.HTML("""
        <div style="text-align: center; margin-bottom: 35px; padding: 30px; background: var(--tech-gradient-1); border-radius: 18px; border: 1px solid var(--tech-border-1); box-shadow: 0 20px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-glow-accent), inset 0 2px 0 rgba(255,255,255,0.08);">
            <div style="font-size: 4.5rem; margin-bottom: 20px;">📊</div>
            <h2 style="color: var(--tech-text-primary); margin: 0; font-weight: 700; font-size: 2.2rem; text-shadow: 0 0 15px var(--tech-glow-primary);">Motor de Análisis</h2>
            <p style="color: var(--tech-text-secondary); font-size: 1.2rem; margin: 15px 0; font-weight: 500;">Evaluación profunda en 6 dimensiones estratégicas</p>
            <div style="height: 4px; width: 150px; background: var(--tech-gradient-3); margin: 20px auto; border-radius: 4px; box-shadow: 0 0 10px var(--tech-glow-accent);"></div>
            <p style="color: var(--tech-text-tertiary); font-size: 1rem; margin: 0;">🎯 Análisis multidimensional • 🔬 IA avanzada • 📋 Informes detallados</p>
        </div>
        """)
        
        # Descripción horizontal tipo análisis competitivo
        gr.HTML("""
        <div style="background: var(--tech-gradient-1); border-radius: 16px; padding: 25px; margin-bottom: 25px; box-shadow: 0 15px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-border-1), inset 0 2px 0 rgba(255,255,255,0.08); border: 1px solid var(--tech-border-1);">
            <h3 style="color: var(--tech-text-primary); margin-bottom: 20px; font-weight: 600; font-size: 1.2rem;">📋 Dimensiones de Análisis</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-primary); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">📄</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Resumen Ejecutivo</div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-accent); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">🔧</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Análisis Técnico</div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-warning); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">💡</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Potencial Innovador</div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-error); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">🎯</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Alineación Estratégica</div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-success); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">💰</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Viabilidad Comercial</div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: var(--tech-surface-2); border-radius: 10px; border-left: 3px solid var(--tech-primary); border: 1px solid var(--tech-border-1);">
                    <div style="font-size: 1.3rem;">⭐</div>
                    <div style="color: var(--tech-text-secondary); font-weight: 600; font-size: 0.85rem;">Valoración Global</div>
                </div>
            </div>
            <div style="padding: 15px; background: var(--tech-surface-3); border-radius: 12px; border-left: 4px solid var(--tech-primary); box-shadow: 0 4px 15px var(--tech-shadow-1);">
                <p style="margin: 0; color: var(--tech-text-secondary); font-weight: 500; font-size: 0.95rem;">
                    📊 <strong style="color: var(--tech-primary);">Informe completo:</strong> El PDF generado incluye análisis detallado en todas estas dimensiones para cada idea procesada
                </p>
            </div>
        </div>
        """)
        
        with gr.Row():
            with gr.Column():
                analyze_btn = gr.Button(
                    "🚀 Ejecutar Análisis",
                    variant="primary",
                    size="lg",
                    elem_classes="analysis-btn"
                )
                
                analysis_status = gr.Markdown(
                    "Esperando inicio del análisis...",
                    elem_id="analysis_status"
                )
        
        with gr.Row():
            download_pdf = gr.File(
                label="Descargar Informe",
                interactive=False
            )
        
        # --- NUEVO BLOQUE: Botón para generar y descargar PDF de retos y soluciones ---
        with gr.Row():
            with gr.Column():
                btn_generate_challenges = gr.Button(
                    "🛠️ Generar Solución a Retos",
                    variant="primary",
                    size="lg",
                    elem_classes="analysis-btn"
                )
                status_challenges = gr.Markdown(
                    "Esperando generación de retos y soluciones...",
                    elem_id="challenges_status"
                )
            with gr.Column():
                download_challenges_pdf = gr.File(
                    label="Descargar Solución a Retos",
                    interactive=False
                )
        
        # Eventos
        analyze_btn.click(
            fn=run_batch_analysis,
            outputs=[analysis_status, download_pdf]
        )
        
        # Al iniciar el análisis, limpiar el log aunque no mostremos el progreso
        def initialize_analysis():
            global terminal_log
            terminal_log = []
            log_message("Iniciando análisis...")
            return get_terminal_log()
        
        analyze_btn.click(
            fn=initialize_analysis,
            outputs=[] # No actualizamos ningún componente visible
        )
        
        # --- NUEVO: Evento para generar el PDF de retos y soluciones ---
        btn_generate_challenges.click(
            fn=handler_generate_challenges_pdf,
            inputs=[],
            outputs=[download_challenges_pdf, status_challenges]
        )

def individual_analyze(ideas_list):
    """Analiza ideas individualmente utilizando analyze_idea_exhaustive"""
    try:
        from analysis_module2 import analyze_idea_exhaustive, generate_improved_pdf, global_save_analyzed_ideas
        import analysis_module2
        validated_ideas = []
        
        log_message(f"🔄 Iniciando análisis individual de {len(ideas_list)} ideas...")
        
        for i, idea in enumerate(ideas_list, 1):
            try:
                if isinstance(idea, dict):
                    idea_text = idea.get('idea', '')
                else:
                    idea_text = str(idea)
                if not idea_text or not idea_text.strip():
                    log_message(f"⚠️ Idea {i} está vacía, saltando...")
                    # --- MEJORA: incluir bloque en el informe aunque esté vacía ---
                    validated_ideas.append({
                        'idea': f'Idea {i}',
                        'analysis': 'No se pudo analizar esta idea. Requiere revisión manual.'
                    })
                    continue
                preview = idea_text[:50] + "..." if len(idea_text) > 50 else idea_text
                log_message(f"🔍 Analizando idea {i}/{len(ideas_list)}: {preview}")
                result = analyze_idea_exhaustive(idea_text)
                if result and isinstance(result, tuple) and result[0]:
                    log_message(f"✅ Idea {i} analizada correctamente")
                    validated_ideas.append({
                        'idea': idea_text,
                        'analysis': result[0]
                    })
                else:
                    log_message(f"⚠️ No se pudo analizar la idea {i}")
                    # --- MEJORA: incluir bloque en el informe aunque falle ---
                    validated_ideas.append({
                        'idea': idea_text,
                        'analysis': 'No se pudo analizar esta idea. Requiere revisión manual.'
                    })
            except Exception as ex:
                error_msg = str(ex)
                log_message(f"❌ Error analizando idea {i}: {error_msg}")
                import traceback
                error_trace = traceback.format_exc()
                log_message(f"Detalles del error: {error_trace[:500]}...")
                # --- MEJORA: incluir bloque en el informe aunque haya excepción ---
                validated_ideas.append({
                    'idea': f'Idea {i}',
                    'analysis': 'No se pudo analizar esta idea. Requiere revisión manual.'
                })
        
        if validated_ideas:
            log_message(f"📊 Se analizaron {len(validated_ideas)} ideas de {len(ideas_list)}")
            log_message("🔄 Generando PDF con los resultados...")
            pdf_path = generate_improved_pdf(validated_ideas)
            if pdf_path:
                log_message(f"✅ PDF generado exitosamente: {pdf_path}")
                set_analyzed_ideas_global(validated_ideas)
                analysis_module2.analyzed_ideas_global = validated_ideas  # <--- SINCRONIZACIÓN CRÍTICA
                return pdf_path
            else:
                log_message("❌ Error: No se pudo generar el PDF")
                # --- MEJORA: mensaje claro en la UI si el PDF no se genera ---
                return None
        else:
            log_message("❌ Error: No se pudo analizar ninguna idea")
            # --- MEJORA: mensaje claro en la UI si no hay ideas válidas ---
            return None
    except Exception as e:
        error_msg = str(e)
        log_message(f"❌ Error general en análisis individual: {error_msg}")
        # Registrar la traza del error para depuración
        import traceback
        error_trace = traceback.format_exc()
        log_message(f"Detalles del error: {error_trace}")
        return None

def download_fonts():
    """
    Descarga y registra las fuentes DejaVu para FPDF
    """
    try:
        print("🔄 Verificando fuentes...")
        # Crear directorio temporal para las fuentes
        temp_dir = tempfile.gettempdir()
        fonts_dir = os.path.join(temp_dir, "fonts")
        
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
        
        # Fuentes a descargar
        fonts = {
            'DejaVuSansCondensed.ttf': 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSansCondensed.ttf',
            'DejaVuSansCondensed-Bold.ttf': 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSansCondensed-Bold.ttf',
            'DejaVuSansCondensed-Oblique.ttf': 'https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/trunk/ttf/DejaVuSansCondensed-Oblique.ttf'
        }
        
        # Verificar y descargar cada fuente
        all_fonts_present = True
        for font_file, font_url in fonts.items():
            font_path = os.path.join(fonts_dir, font_file)
            
            # Si la fuente ya existe y tiene contenido, pasar a la siguiente
            if os.path.exists(font_path) and os.path.getsize(font_path) > 1000:
                print(f"✅ Fuente ya disponible: {font_file}")
                continue
                
            # Descargar fuente
            print(f"🔄 Descargando fuente: {font_file}...")
            try:
                response = requests.get(font_url, timeout=10)
                if response.status_code == 200:
                    with open(font_path, 'wb') as f:
                        f.write(response.content)
                    print(f"✅ Fuente descargada correctamente: {font_file}")
                else:
                    print(f"❌ Error descargando fuente {font_file}: {response.status_code}")
                    all_fonts_present = False
            except Exception as e:
                print(f"❌ Error descargando fuente {font_file}: {str(e)}")
                all_fonts_present = False
        
        # Verificación final
        if all_fonts_present:
            print("✅ Todas las fuentes están disponibles")
            return True
        else:
            print("⚠️ No se pudieron descargar todas las fuentes, se usarán fuentes predeterminadas")
            return False
            
    except Exception as e:
        print(f"❌ Error en download_fonts: {str(e)}")
        return False

async def enhance_idea_with_ai(idea, context):
    """
    Mejora una idea usando la API de OpenAI con el contexto proporcionado
    """
    try:
        # Asegurar que la idea es un string
        if isinstance(idea, dict):
            idea_text = str(idea.get('idea', ''))
        else:
            idea_text = str(idea)
            
        if not idea_text.strip():
            return idea
            
        # Preparar el prompt con el contexto
        prompt = f"""
        Contexto: {context}
        
        Idea a mejorar: {idea_text}
        
        Por favor, mejora esta idea considerando el contexto proporcionado.
        Mantén la esencia de la idea original pero añade detalles relevantes
        basados en el contexto.
        """
        
        # Llamar a la API de OpenAI usando el cliente de Azure
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Eres un experto en innovación y desarrollo de ideas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            timeout=30  # Añadir timeout para evitar bloqueos
        )
        
        # Extraer la idea mejorada
        if not response or not response.choices or not response.choices[0].message:
            return idea
            
        enhanced_idea = response.choices[0].message.content.strip()
        
        # Crear el objeto de idea mejorada
        if isinstance(idea, dict):
            idea['idea'] = enhanced_idea
            return idea
        else:
            return enhanced_idea
            
    except Exception as e:
        print(f"Error mejorando idea: {str(e)}")
        traceback.print_exc()  # Añadir traza completa del error
        return idea

def detect_ideas_basic(text):
    try:
        global ideas_list
        if ideas_list and len(ideas_list) > 0:
            print(f"✅ Usando {len(ideas_list)} ideas del documento cargado")
            return [idea['idea'] if isinstance(idea, dict) else idea for idea in ideas_list]

        print("⚠️ No hay ideas cargadas, intentando detectar del texto...")

        # --- Detección robusta por bullets tipo '• IDEA X:' (soporta saltos de línea y bullets pegados al margen) ---
        bullet_pattern = r'(?:^|\n)\s*•\s*IDEA\s*\d+:.*?(?=(?:\n\s*•\s*IDEA\s*\d+:|\Z))'
        matches = re.findall(bullet_pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            final_ideas = []
            seen = set()
            for idea in matches:
                idea = idea.strip()
                idea = re.sub(r'\s+', ' ', idea)
                if len(idea) > 10 and idea not in seen:
                    final_ideas.append(idea)
                    seen.add(idea)
            print(f"✅ Ideas detectadas por bullet: {len(final_ideas)}")
            set_ideas_list_safe([{"idea": idea} for idea in final_ideas])
            return final_ideas

        # --- Si no hay bullets, seguir con los métodos previos ---
        lines = text.split('\n')
        validated_ideas = []
        current_idea = ""
        in_idea = False
        pattern1 = re.compile(r'^•\s*.*?:|idea\s+\d+:|^\d+\.\s+', re.IGNORECASE)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if pattern1.match(line):
                if in_idea and current_idea:
                    validated_ideas.append(current_idea.strip())
                cleaned_line = re.sub(r'^•\s*.*?:\s*|^idea\s+\d+:\s*|^\d+\.\s*', '', line, flags=re.IGNORECASE)
                current_idea = cleaned_line
                in_idea = True
            elif in_idea:
                current_idea += " " + line
        if in_idea and current_idea:
            validated_ideas.append(current_idea.strip())
        if not validated_ideas:
            print("⚠️ No se encontraron ideas con formato estándar, aplicando detección secundaria...")
            paragraphs = re.split(r'\n\s*\n', text)
            for para in paragraphs:
                para = para.strip()
                if len(para) > 50 and para.count('\n') < 5:
                    validated_ideas.append(para)
            if not validated_ideas:
                for line in lines:
                    line = line.strip()
                    if len(line) > 60:
                        validated_ideas.append(line)
        final_ideas = []
        seen = set()
        for idea in validated_ideas:
            idea = idea.strip()
            idea = re.sub(r'\s+', ' ', idea)
            if len(idea) > 10 and idea not in seen:
                final_ideas.append(idea)
                seen.add(idea)
        final_ideas = final_ideas[:20]
        print(f"✅ Ideas detectadas del texto: {len(final_ideas)}")
        set_ideas_list_safe([{"idea": idea} for idea in final_ideas])
        return final_ideas
    except Exception as e:
        print(f"❌ Error en detect_ideas_basic: {str(e)}")
        traceback.print_exc()  # Añadir trazas completas para depuración
        return []

def generate_analysis_pdf(analyzed_ideas):
    """
    Genera un PDF con el análisis de las ideas usando una fuente por defecto
    """
    try:
        # Crear PDF con fuente por defecto
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Configurar fuente por defecto
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        
        # Título
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "Análisis de Ideas", ln=True, align="C")
        pdf.ln(10)
        
        # Contenido
        pdf.set_font("helvetica", size=12)
        for idea in analyzed_ideas:
            # Idea
            pdf.set_font("helvetica", "B", 12)
            pdf.multi_cell(0, 10, f"Idea: {idea['text']}")
            pdf.ln(5)
            
            # Análisis
            pdf.set_font("helvetica", size=12)
            for title, analysis in idea['analysis'].items():
                pdf.set_font("helvetica", "B", 12)
                pdf.cell(0, 10, f"{title}:", ln=True)
                pdf.set_font("helvetica", size=12)
                pdf.multi_cell(0, 10, analysis)
                pdf.ln(5)
            
            pdf.ln(10)
        
        # Guardar PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"analisis_{timestamp}.pdf")
        pdf.output(pdf_path)
        
        return pdf_path
        
    except Exception as e:
        print(f"Error al generar PDF: {str(e)}")
        return None

def lote_analyze(ideas_list):
    """Analiza un lote de ideas utilizando la función analyze_ideas_batch"""
    try:
        from analysis_module2 import analyze_ideas_batch, get_analyzed_ideas
        import analysis_module2
        log_message(f"🔄 Procesando {len(ideas_list)} ideas en lote...")
        total_ideas = len(ideas_list)
        for i, idea in enumerate(ideas_list[:3], 1):
            idea_text = idea['idea'] if isinstance(idea, dict) and 'idea' in idea else str(idea)
            preview = idea_text[:60] + "..." if len(idea_text) > 60 else idea_text
            log_message(f"📋 Idea {i}/{total_ideas}: {preview}")
        if total_ideas > 3:
            log_message(f"... y {total_ideas - 3} ideas más")
        log_message("🧠 Iniciando análisis con IA...")
        result = analyze_ideas_batch(
            ideas_list,
            title="Análisis de Ideas Innovadoras",
            context="",
            template=None
        )
        if isinstance(result, tuple) and len(result) == 2:
            analysis_text, pdf_path = result
            print(f"DEBUG PDF path: {pdf_path} ({type(pdf_path)})")
            import os
            if pdf_path and isinstance(pdf_path, str) and os.path.exists(pdf_path):
                analyzed_ideas = get_analyzed_ideas()
                if analyzed_ideas and all(isinstance(idea, dict) and idea.get('analysis') for idea in analyzed_ideas):
                    set_analyzed_ideas_global(analyzed_ideas)
                    analysis_module2.analyzed_ideas_global = analyzed_ideas  # <--- SINCRONIZACIÓN CRÍTICA
                else:
                    set_analyzed_ideas_global(ideas_list)
                    analysis_module2.analyzed_ideas_global = ideas_list  # <--- SINCRONIZACIÓN CRÍTICA
                log_message(f"✅ PDF generado exitosamente: {pdf_path}")
                return pdf_path
            log_message("❌ Error: No se pudo generar el PDF o el archivo no existe")
            return None
        else:
            log_message("❌ Error: Formato de respuesta incorrecto del análisis")
        return None
    except Exception as e:
        log_message(f"❌ Error en análisis por lotes: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        log_message(f"Detalles del error: {error_trace}")
        return None

def log_message(msg):
    """Registra un mensaje en el log del terminal"""
    global terminal_log
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    
    # Añadir al principio para tener los mensajes más recientes primero
    terminal_log.insert(0, log_entry)
    
    # Limitar el tamaño del log
    if len(terminal_log) > log_limit:
        terminal_log = terminal_log[:log_limit]
    
    # Usar original_print en lugar de print para evitar recursión infinita
    # print(log_entry)  # Esta línea causa recursión infinita
    original_print(log_entry)
    return log_entry

def get_terminal_log():
    """Obtiene el registro del terminal para la UI"""
    global terminal_log
    return "\n".join(terminal_log)

# Sobreescribir print para capturar todos los mensajes
original_print = print
def custom_print(*args, **kwargs):
    message = " ".join(str(arg) for arg in args)
    # Añadir el mensaje al log sin usar log_message
    global terminal_log
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    # Añadir al principio para tener los mensajes más recientes primero
    terminal_log.insert(0, log_entry)
    
    # Limitar el tamaño del log
    if len(terminal_log) > log_limit:
        terminal_log = terminal_log[:log_limit]
        
    # Llamar a la función original print
    original_print(*args, **kwargs)

# Reemplazar print con nuestra versión personalizada
print = custom_print

# --- NUEVO: Handler para generar el PDF de retos y soluciones ---
def handler_generate_challenges_pdf(context=None):
    from analysis_module2 import generate_challenges_and_solutions_pdf, get_global_analyzed_ideas
    analyzed_ideas = get_global_analyzed_ideas()
    print("DEBUG: analyzed_ideas para retos/soluciones:", analyzed_ideas)
    # Solo procesar si todas las ideas son dicts válidos con 'idea' y 'analysis'
    if not analyzed_ideas or not all(isinstance(idea, dict) and idea.get('analysis') for idea in analyzed_ideas):
        return None, "❌ No hay análisis completo para las ideas. Ejecuta primero el análisis y asegúrate de que cada idea tiene su análisis generado."
    try:
        pdf_path = generate_challenges_and_solutions_pdf(analyzed_ideas, context or "")
        if pdf_path and os.path.exists(pdf_path):
            return pdf_path, f"✅ PDF de retos y soluciones generado correctamente."
        else:
            return None, "❌ Error al generar el PDF de retos y soluciones."
    except Exception as e:
        print(f"❌ Error interno al generar PDF de retos: {str(e)}")
        return None, "❌ Error inesperado al generar el PDF de retos y soluciones. Por favor, revisa que las ideas estén correctamente analizadas."

# Crear la interfaz de Gradio con la nueva API para el terminal
with gr.Blocks(theme=gr.themes.Soft(), title="AI Innovation para la Fase de Ideación") as demo:
    # Añadir CSS global mejorado
    gr.HTML("""
    <style>
    /* ============= PALETA PROFESIONAL TECNOLÓGICA ============= */
    :root {
        /* Colores base */
        --tech-primary: #0ea5e9;
        --tech-secondary: #3b82f6;
        --tech-accent: #06b6d4;
        
        /* Superficies progresivas - del más oscuro al más claro */
        --tech-bg-primary: #0f172a;
        --tech-bg-secondary: #1e293b;
        --tech-bg-tertiary: #334155;
        --tech-bg-quaternary: #475569;
        
        /* Superficies de contenido */
        --tech-surface-1: #1e293b;
        --tech-surface-2: #334155;
        --tech-surface-3: #475569;
        --tech-surface-4: #64748b;
        
        /* Bordes progresivos */
        --tech-border-1: #334155;
        --tech-border-2: #475569;
        --tech-border-3: #64748b;
        
        /* Textos jerarquizados */
        --tech-text-primary: #f8fafc;
        --tech-text-secondary: #e2e8f0;
        --tech-text-tertiary: #cbd5e1;
        --tech-text-muted: #94a3b8;
        
        /* Estados */
        --tech-success: #22c55e;
        --tech-warning: #f59e0b;
        --tech-error: #ef4444;
        --tech-info: #3b82f6;
        
        /* Efectos */
        --tech-glow-primary: rgba(14, 165, 233, 0.3);
        --tech-glow-accent: rgba(6, 182, 212, 0.2);
        --tech-shadow-1: rgba(0, 0, 0, 0.1);
        --tech-shadow-2: rgba(0, 0, 0, 0.2);
        --tech-shadow-3: rgba(0, 0, 0, 0.3);
        
        /* Gradientes */
        --tech-gradient-1: linear-gradient(135deg, var(--tech-surface-1), var(--tech-surface-2));
        --tech-gradient-2: linear-gradient(135deg, var(--tech-surface-2), var(--tech-surface-3));
        --tech-gradient-3: linear-gradient(135deg, var(--tech-primary), var(--tech-accent));
    }
    
    /* ============= FONDO PRINCIPAL PROFESIONAL ============= */
    .gradio-container {
        background: var(--tech-bg-primary) !important;
        font-family: 'Inter', 'SF Pro Display', 'Segoe UI', sans-serif !important;
        color: var(--tech-text-secondary) !important;
        min-height: 100vh !important;
        line-height: 1.6 !important;
        font-weight: 400 !important;
    }
    
    /* Mejorar legibilidad global */
    body, * {
        font-optical-sizing: auto !important;
        text-rendering: optimizeLegibility !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
    }
    
        /* ============= HEADER PROFESIONAL ELEGANTE ============= */
    .header-container {
        background: var(--tech-gradient-1) !important;
        border: 1px solid var(--tech-border-1) !important;
        border-radius: 20px !important;
        padding: 40px 30px !important;
        margin-bottom: 35px !important;
        box-shadow: 
            0 25px 50px var(--tech-shadow-3),
            0 0 0 1px var(--tech-glow-accent),
            inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .header-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: -200%;
        width: 400%;
        height: 100%;
        background: linear-gradient(90deg, transparent 0%, var(--tech-glow-primary) 50%, transparent 100%);
        animation: shimmer 12s ease-in-out infinite;
        pointer-events: none;
        opacity: 0.6;
    }
    
    .header-container::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: radial-gradient(circle at 50% 0%, var(--tech-glow-accent), transparent 70%);
        pointer-events: none;
        opacity: 0.1;
    }
    
    @keyframes shimmer {
        0% { left: -200%; }
        100% { left: 200%; }
    }
    
    .header-container h1 {
        color: var(--tech-text-primary) !important;
        text-shadow: 0 0 30px var(--tech-glow-primary) !important;
        font-weight: 700 !important;
        margin: 0 !important;
        font-size: 2.8rem !important;
        letter-spacing: -0.02em !important;
        text-align: center !important;
        position: relative !important;
        z-index: 2 !important;
    }
    
    /* ============= LOGO PROFESIONAL ELEGANTE ============= */
    .fixed-logo {
        pointer-events: none !important;
        user-select: none !important;
        -webkit-user-drag: none !important;
        -webkit-user-select: none !important;
        filter: drop-shadow(0 0 20px var(--tech-glow-primary)) !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    .fixed-logo-container {
        background: var(--tech-gradient-2) !important;
        border-radius: 16px !important;
        padding: 25px !important;
        border: 1px solid var(--tech-border-2) !important;
        box-shadow: 
            0 20px 40px var(--tech-shadow-2),
            0 0 0 1px var(--tech-glow-accent),
            inset 0 2px 0 rgba(255, 255, 255, 0.1) !important;
        text-align: center !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .fixed-logo-container::before {
        content: '';
        position: absolute;
        top: -3px;
        left: -3px;
        right: -3px;
        bottom: -3px;
        background: var(--tech-gradient-3);
        border-radius: 18px;
        z-index: -1;
        opacity: 0;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .fixed-logo-container::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: radial-gradient(circle, var(--tech-glow-primary), transparent 70%);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        opacity: 0;
        z-index: 1;
        pointer-events: none;
    }
    
    .fixed-logo-container:hover {
        transform: translateY(-4px) scale(1.05) !important;
        box-shadow: 
            0 30px 60px var(--tech-shadow-3),
            0 0 40px var(--tech-glow-primary) !important;
    }
    
    .fixed-logo-container:hover::before {
        opacity: 0.8;
    }
    
    .fixed-logo-container:hover::after {
        width: 100px;
        height: 100px;
        opacity: 0.15;
    }
    
    /* ============= PESTAÑAS PROFESIONALES ELEGANTES ============= */
    .tab-nav {
        background: transparent !important;
        padding: 0 !important;
        gap: 2px !important;
        width: 100% !important;
        display: flex !important;
        margin-bottom: 25px !important;
    }
    
    .tab-nav button {
        background: var(--tech-surface-2) !important;
        border: 2px solid var(--tech-border-1) !important;
        border-radius: 0 !important;
        padding: 22px 35px !important;
        margin: 0 !important;
        flex: 1 !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        color: var(--tech-text-tertiary) !important;
        position: relative !important;
        overflow: hidden !important;
        letter-spacing: 0.025em !important;
        text-transform: none !important;
    }
    
    .tab-nav button:first-child {
        border-radius: 14px 0 0 14px !important;
        border-right: 1px solid var(--tech-border-1) !important;
    }
    
    .tab-nav button:last-child {
        border-radius: 0 14px 14px 0 !important;
        border-left: 1px solid var(--tech-border-1) !important;
    }
    
    .tab-nav button:not(:first-child):not(:last-child) {
        border-left: 1px solid var(--tech-border-1) !important;
        border-right: 1px solid var(--tech-border-1) !important;
    }
    
    .tab-nav button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, var(--tech-glow-primary), transparent);
        transition: left 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        z-index: 0;
        opacity: 0.8;
    }
    
    .tab-nav button::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 50%;
        width: 0;
        height: 3px;
        background: var(--tech-gradient-3);
        transform: translateX(-50%);
        transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        border-radius: 3px 3px 0 0;
    }
    
    .tab-nav button:hover {
        border-color: var(--tech-border-2) !important;
        color: var(--tech-text-secondary) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 12px 30px var(--tech-shadow-2) !important;
        background: var(--tech-surface-3) !important;
    }
    
    .tab-nav button:hover::before {
        left: 0;
    }
    
    .tab-nav button:hover::after {
        width: 60%;
    }
    
    .tab-nav button[aria-selected="true"] {
        border-color: var(--tech-border-3) !important;
        color: var(--tech-text-primary) !important;
        background: var(--tech-surface-4) !important;
        transform: translateY(-3px) !important;
        box-shadow: 
            0 15px 35px var(--tech-shadow-2),
            0 0 0 1px var(--tech-glow-accent),
            inset 0 2px 0 rgba(255, 255, 255, 0.1) !important;
    }
    
    .tab-nav button[aria-selected="true"]::before {
        left: 0;
        background: linear-gradient(90deg, var(--tech-primary), var(--tech-accent), var(--tech-primary));
        opacity: 0.2;
    }
    
    .tab-nav button[aria-selected="true"]::after {
        width: 90%;
        height: 4px;
        background: var(--tech-gradient-3);
        box-shadow: 0 0 15px var(--tech-glow-primary);
    }
    
    /* ============= BOTONES PROFESIONALES ELEGANTES ============= */
    .btn button, button {
        background: var(--tech-gradient-1) !important;
        border: 1px solid var(--tech-border-2) !important;
        border-radius: 12px !important;
        padding: 16px 32px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        text-transform: none !important;
        letter-spacing: 0.025em !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 
            0 8px 25px var(--tech-shadow-1),
            inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
        color: var(--tech-text-secondary) !important;
        cursor: pointer !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .btn button::before, button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, var(--tech-glow-primary), transparent);
        transition: left 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        z-index: 0;
        opacity: 0.6;
    }
    
    .btn button::after, button::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: radial-gradient(circle, var(--tech-glow-accent), transparent 70%);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        opacity: 0;
        z-index: 1;
        pointer-events: none;
    }
    
    .btn button:hover, button:hover {
        border-color: var(--tech-border-3) !important;
        transform: translateY(-3px) scale(1.02) !important;
        box-shadow: 
            0 15px 40px var(--tech-shadow-2),
            0 0 0 1px var(--tech-glow-accent),
            inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
        color: var(--tech-text-primary) !important;
        background: var(--tech-gradient-2) !important;
    }
    
    .btn button:hover::before, button:hover::before {
        left: 0;
    }
    
    .btn button:hover::after, button:hover::after {
        width: 200px;
        height: 200px;
        opacity: 0.1;
    }
    
    .btn button:active, button:active {
        transform: translateY(-1px) scale(0.98) !important;
        box-shadow: 
            0 8px 20px var(--tech-shadow-1),
            inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
    }
    
    /* Botones primarios */
    .btn button[variant="primary"], button[variant="primary"] {
        background: var(--tech-gradient-3) !important;
        border-color: var(--tech-primary) !important;
        color: var(--tech-text-primary) !important;
        box-shadow: 
            0 10px 30px var(--tech-glow-primary),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
    }
    
    .btn button[variant="primary"]:hover, button[variant="primary"]:hover {
        box-shadow: 
            0 20px 50px var(--tech-glow-primary),
            0 0 0 1px var(--tech-accent),
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }
    
    /* Botones de análisis */
    .analysis-btn {
        background: linear-gradient(135deg, var(--tech-success), #059669) !important;
        border-color: var(--tech-success) !important;
        color: var(--tech-text-primary) !important;
        box-shadow: 
            0 10px 30px rgba(34, 197, 94, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
    }
    
    .analysis-btn:hover {
        box-shadow: 
            0 20px 50px rgba(34, 197, 94, 0.4),
            0 0 0 1px #10b981,
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }
    
    /* Botones de ranking */
    .ranking-btn {
        background: linear-gradient(135deg, var(--tech-warning), #d97706) !important;
        border-color: var(--tech-warning) !important;
        color: var(--tech-text-primary) !important;
        box-shadow: 
            0 10px 30px rgba(245, 158, 11, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
    }
    
    .ranking-btn:hover {
        box-shadow: 
            0 20px 50px rgba(245, 158, 11, 0.4),
            0 0 0 1px #f59e0b,
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }
    
    /* Botones de procesamiento */
    .process-btn {
        background: linear-gradient(135deg, var(--tech-accent), var(--tech-secondary)) !important;
        border-color: var(--tech-accent) !important;
        color: var(--tech-text-primary) !important;
        box-shadow: 
            0 10px 30px var(--tech-glow-accent),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
    }
    
    .process-btn:hover {
        box-shadow: 
            0 20px 50px var(--tech-glow-accent),
            0 0 0 1px var(--tech-accent),
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }
    
    /* ============= CARDS Y GRUPOS PROFESIONALES ============= */
    .gradio-group {
        background: var(--tech-gradient-1) !important;
        border-radius: 18px !important;
        padding: 30px !important;
        box-shadow: 
            0 15px 40px var(--tech-shadow-2),
            0 0 0 1px var(--tech-border-1),
            inset 0 2px 0 rgba(255, 255, 255, 0.08) !important;
        border: 1px solid var(--tech-border-1) !important;
        margin: 20px 0 !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .gradio-group::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: var(--tech-gradient-3);
        opacity: 0;
        transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        border-radius: 18px 18px 0 0;
    }
    
    .gradio-group::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: radial-gradient(circle, var(--tech-glow-accent), transparent 70%);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        opacity: 0;
        z-index: 0;
        pointer-events: none;
    }
    
    .gradio-group:hover {
        transform: translateY(-4px) scale(1.01) !important;
        box-shadow: 
            0 25px 60px var(--tech-shadow-3),
            0 0 0 1px var(--tech-border-2),
            0 0 30px var(--tech-glow-accent),
            inset 0 2px 0 rgba(255, 255, 255, 0.12) !important;
        border-color: var(--tech-border-2) !important;
        background: var(--tech-gradient-2) !important;
    }
    
    .gradio-group:hover::before {
        opacity: 1;
    }
    
    .gradio-group:hover::after {
        width: 300px;
        height: 300px;
        opacity: 0.05;
    }
    
    /* ============= INPUTS Y ELEMENTOS PROFESIONALES ============= */
    .gradio-textbox textarea, .gradio-textbox input, .gradio-number input {
        border-radius: 14px !important;
        border: 1px solid var(--tech-border-1) !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        background: var(--tech-surface-2) !important;
        padding: 18px !important;
        font-size: 15px !important;
        color: var(--tech-text-secondary) !important;
        box-shadow: 
            0 4px 15px var(--tech-shadow-1),
            inset 0 2px 0 rgba(255, 255, 255, 0.05) !important;
        font-weight: 400 !important;
        line-height: 1.5 !important;
    }
    
    .gradio-textbox textarea::placeholder, .gradio-textbox input::placeholder, .gradio-number input::placeholder {
        color: var(--tech-text-muted) !important;
        opacity: 0.8 !important;
    }
    
    .gradio-textbox textarea:focus, .gradio-textbox input:focus, .gradio-number input:focus {
        border-color: var(--tech-border-2) !important;
        box-shadow: 
            0 8px 25px var(--tech-shadow-2),
            0 0 0 2px var(--tech-glow-accent),
            inset 0 2px 0 rgba(255, 255, 255, 0.08) !important;
        transform: translateY(-2px) !important;
        background: var(--tech-surface-3) !important;
        outline: none !important;
        color: var(--tech-text-primary) !important;
    }
    
    .gradio-file {
        border-radius: 18px !important;
        border: 2px dashed var(--tech-border-1) !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        background: var(--tech-surface-1) !important;
        padding: 35px 25px !important;
        box-shadow: 
            0 10px 30px var(--tech-shadow-1),
            inset 0 2px 0 rgba(255, 255, 255, 0.05) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .gradio-file::before {
        content: '';
        position: absolute;
        top: 0;
        left: -200%;
        width: 400%;
        height: 100%;
        background: linear-gradient(90deg, transparent, var(--tech-glow-primary), transparent);
        transition: left 1s cubic-bezier(0.4, 0, 0.2, 1);
        z-index: 0;
        opacity: 0.4;
        pointer-events: none;
    }
    
    .gradio-file::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: radial-gradient(circle, var(--tech-glow-accent), transparent 70%);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        opacity: 0;
        z-index: 1;
        pointer-events: none;
    }
    
    .gradio-file:hover {
        border-color: var(--tech-border-2) !important;
        border-style: solid !important;
        transform: translateY(-4px) scale(1.01) !important;
        box-shadow: 
            0 20px 50px var(--tech-shadow-2),
            0 0 0 1px var(--tech-glow-accent),
            inset 0 2px 0 rgba(255, 255, 255, 0.08) !important;
        background: var(--tech-surface-2) !important;
    }
    
    .gradio-file:hover::before {
        left: 0;
    }
    
    .gradio-file:hover::after {
        width: 200px;
        height: 200px;
        opacity: 0.08;
    }
    
    /* Labels mejorados */
    .gradio-textbox label, .gradio-file label, .gradio-number label {
        color: var(--tech-text-secondary) !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        margin-bottom: 8px !important;
        letter-spacing: 0.025em !important;
    }
    

    
    /* ============= TABLAS Y DATAFRAMES PROFESIONALES ============= */
    .gradio-dataframe, .gradio-dataframe table {
        border-radius: 16px !important;
        overflow: hidden !important;
        box-shadow: 
            0 15px 40px var(--tech-shadow-2),
            0 0 0 1px var(--tech-border-1) !important;
        background: var(--tech-surface-1) !important;
        border: none !important;
    }
    
    .gradio-dataframe thead th {
        background: var(--tech-gradient-2) !important;
        color: var(--tech-text-primary) !important;
        padding: 20px 18px !important;
        font-weight: 700 !important;
        text-transform: none !important;
        letter-spacing: 0.025em !important;
        font-size: 14px !important;
        border: none !important;
        border-bottom: 2px solid var(--tech-border-2) !important;
        position: relative !important;
    }
    
    .gradio-dataframe thead th::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: var(--tech-gradient-3);
        opacity: 0.6;
    }
    
    .gradio-dataframe tbody td {
        background: var(--tech-surface-2) !important;
        color: var(--tech-text-secondary) !important;
        padding: 16px 18px !important;
        border: none !important;
        border-bottom: 1px solid var(--tech-border-1) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    
    .gradio-dataframe tbody tr:hover td {
        background: var(--tech-surface-3) !important;
        color: var(--tech-text-primary) !important;
        transform: scale(1.005) !important;
        box-shadow: 0 4px 15px var(--tech-shadow-1) !important;
    }
    
    .gradio-dataframe tbody tr:last-child td {
        border-bottom: none !important;
    }
    
    /* Estilos para elementos de conteo */
    .counter-box {
        font-size: 32px !important;
        font-weight: 900 !important;
        text-align: center !important;
        color: var(--tech-text-primary) !important;
        padding: 25px !important;
        background: var(--tech-gradient-1) !important;
        border-radius: 16px !important;
        margin: 25px 0 !important;
        box-shadow: 
            0 8px 32px var(--tech-shadow-2),
            inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
        border: 1px solid var(--tech-border-1) !important;
        transition: all 0.3s ease !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .counter-box::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, var(--tech-glow-primary), transparent);
        transition: left 0.8s ease;
        pointer-events: none;
    }
    
    .counter-box:hover {
        transform: translateY(-3px) scale(1.02) !important;
        box-shadow: 
            0 12px 40px var(--tech-shadow-3),
            0 0 20px var(--tech-glow-primary),
            inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
        border-color: var(--tech-border-2) !important;
    }
    
    .counter-box:hover::before {
        left: 0;
    }
    
    .counter-box input {
        background: transparent !important;
        border: none !important;
        color: var(--tech-text-primary) !important;
        font-weight: 900 !important;
        font-size: 32px !important;
        text-align: center !important;
    }
    
    /* ============= ANIMACIONES GLOBALES ============= */
    @keyframes slideInUp {
        from {
            opacity: 0;
            transform: translateY(40px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    
    .gradio-group, .gradio-textbox, .gradio-file {
        animation: slideInUp 0.8s ease-out !important;
    }
    
    /* ============= MENSAJES DE ESTADO MEJORADOS ============= */
    .gradio-textbox[label*="Estado"] {
        border-radius: 15px !important;
        background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(248,249,250,0.95)) !important;
        border: 2px solid rgba(0,51,153,0.1) !important;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1) !important;
        padding: 20px !important;
        font-weight: 500 !important;
    }
    
    /* ============= LOADING STATES ============= */
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }
    
    .loading {
        animation: pulse 1.5s infinite ease-in-out !important;
    }
    
    /* ============= ELEMENTOS DE ESTADO Y MARKDOWN ============= */
    .gradio-textbox[label*="Estado"], 
    .gradio-markdown,
    .gradio-markdown p,
    .gradio-markdown div,
    .gradio-html,
    .gradio-html p,
    .gradio-html div {
        color: var(--tech-text-secondary) !important;
        background: var(--tech-surface-2) !important;
        border-radius: 14px !important;
        padding: 16px 20px !important;
        font-weight: 500 !important;
        line-height: 1.6 !important;
        border: 1px solid var(--tech-border-1) !important;
        margin: 10px 0 !important;
        box-shadow: 
            0 4px 15px var(--tech-shadow-1),
            inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    
    /* Títulos y encabezados mejorados */
    .gradio-markdown h1, .gradio-markdown h2, .gradio-markdown h3,
    .gradio-html h1, .gradio-html h2, .gradio-html h3 {
        color: var(--tech-text-primary) !important;
        font-weight: 700 !important;
        margin: 20px 0 15px 0 !important;
        text-shadow: 0 0 10px var(--tech-glow-primary) !important;
    }
    
    /* Enlaces y elementos interactivos */
    .gradio-markdown a, .gradio-html a {
        color: var(--tech-accent) !important;
        text-decoration: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    
    .gradio-markdown a:hover, .gradio-html a:hover {
        color: var(--tech-primary) !important;
        text-shadow: 0 0 8px var(--tech-glow-accent) !important;
    }
    
    /* Elementos de ayuda e instrucciones */
    small, .help-text, [class*="helper"], [class*="instruction"],
    .gr-form-helper, .gr-form-instructions {
        color: var(--tech-text-tertiary) !important;
        background: var(--tech-surface-1) !important;
        border-radius: 10px !important;
        padding: 10px 14px !important;
        font-weight: 400 !important;
        line-height: 1.5 !important;
        font-size: 13px !important;
        border: 1px solid var(--tech-border-1) !important;
        margin: 8px 0 !important;
    }
    
    /* Eliminación de fondos blancos restantes */
    .gr-form, .gr-panel, .gr-box, 
    .gradio-container > div,
    .gradio-container > div > div {
        background: transparent !important;
    }
    
    /* Mejoras específicas para elementos problemáticos */
    .gr-button-primary {
        background: var(--tech-gradient-3) !important;
        color: var(--tech-text-primary) !important;
        border: 1px solid var(--tech-primary) !important;
    }
    
    .gr-button-secondary {
        background: var(--tech-gradient-1) !important;
        color: var(--tech-text-secondary) !important;
        border: 1px solid var(--tech-border-2) !important;
    }
    
    /* Scrollbar personalizada mejorada */
    * {
        scrollbar-width: thin;
        scrollbar-color: var(--tech-border-2) var(--tech-surface-1);
    }
    
    *::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    *::-webkit-scrollbar-track {
        background: var(--tech-surface-1);
        border-radius: 8px;
    }
    
    *::-webkit-scrollbar-thumb {
        background: var(--tech-gradient-2);
        border-radius: 8px;
        border: 2px solid var(--tech-surface-1);
        transition: all 0.3s ease;
    }
    
    *::-webkit-scrollbar-thumb:hover {
        background: var(--tech-gradient-3);
        box-shadow: 0 0 10px var(--tech-glow-accent);
    }
    
    /* Elementos específicos de estado */
    .gr-textbox[data-testid*="status"], 
    .gr-textbox[data-testid*="state"],
    [id*="status"], [id*="state"] {
        background: var(--tech-surface-2) !important;
        color: var(--tech-text-secondary) !important;
        border: 1px solid var(--tech-border-1) !important;
        font-weight: 500 !important;
    }
    
    /* ============= MEJORAS ADICIONALES PROFESIONALES ============= */
    
    /* Animaciones suaves mejoradas */
    @keyframes pulse-glow {
        0%, 100% { 
            box-shadow: 0 0 20px var(--tech-glow-primary); 
            opacity: 1; 
        }
        50% { 
            box-shadow: 0 0 40px var(--tech-glow-accent); 
            opacity: 0.8; 
        }
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-5px); }
    }
    
    /* Efectos hover avanzados para elementos clave */
    .gradio-group:hover, .gradio-textbox:hover, .gradio-file:hover {
        animation: float 3s ease-in-out infinite;
    }
    
    /* Transiciones suaves globales */
    * {
        transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease !important;
    }
    
    /* Mejoras tipográficas */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', 'SF Pro Display', 'Segoe UI', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
    }
    
    /* Focus mejorado para accesibilidad */
    button:focus-visible, input:focus-visible, textarea:focus-visible {
        outline: 2px solid var(--tech-accent) !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 0 4px var(--tech-glow-accent) !important;
    }
    
    /* Estados de carga */
    .loading, [data-loading="true"] {
        position: relative !important;
        overflow: hidden !important;
    }
    
    .loading::before, [data-loading="true"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, var(--tech-glow-primary), transparent);
        animation: shimmer 2s infinite;
        z-index: 10;
    }
    
    /* ============= RESPONSIVE DESIGN MEJORADO ============= */
    @media (max-width: 1200px) {
        .header-container h1 {
            font-size: 2.4rem !important;
        }
        
        .tab-nav button {
            padding: 18px 25px !important;
            font-size: 14px !important;
        }
    }
    
    @media (max-width: 768px) {
    .header-container {
            flex-direction: column !important;
            gap: 20px !important;
            padding: 25px 20px !important;
        }
        
        .header-container h1 {
            font-size: 2rem !important;
        }
        
        .fixed-logo-container {
            width: 100px !important;
            height: 100px !important;
        }
        
        .tab-nav {
            flex-direction: column !important;
            gap: 8px !important;
        }
        
        .tab-nav button {
            border-radius: 12px !important;
            padding: 16px 20px !important;
            font-size: 14px !important;
        }
        
        .btn button, button {
            padding: 14px 24px !important;
            font-size: 14px !important;
        }
        
        .counter-box {
            font-size: 28px !important;
            padding: 20px !important;
        }
        
        .gradio-group {
            padding: 20px !important;
            margin: 15px 0 !important;
        }
    }
    
    @media (max-width: 480px) {
        .header-container h1 {
            font-size: 1.8rem !important;
        }
        
        .gradio-group {
            padding: 15px !important;
        }
        
        .btn button, button {
            padding: 12px 20px !important;
            font-size: 13px !important;
        }
    }
    
    /* ============= MICRO-INTERACCIONES ============= */
    
    /* Efecto ripple para botones */
    .btn button:active::after, button:active::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: rgba(255, 255, 255, 0.5);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        animation: ripple 0.6s ease-out;
    }
    
    @keyframes ripple {
        to {
            width: 200px;
            height: 200px;
            opacity: 0;
        }
    }
    
    /* Indicadores de progreso mejorados */
    .progress-indicator {
        background: var(--tech-gradient-1) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        position: relative !important;
    }
    
    .progress-indicator::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        height: 100%;
        background: var(--tech-gradient-3);
        border-radius: 10px;
        transition: width 0.3s ease;
    }
    

    </style>
    """)
    
    # Crear una fila con estructura flexible que acerque el logo y el título
    with gr.Row(elem_classes=["header-container"]):
        # Logo y título centrado
        with gr.Column():
            # Cargar logo corporativo con diseño profesional PRIORIZADO
            logo_base64 = None
            
            try:
                # PRIORIZAR LOGO CORPORATIVO logo.png CON MÚLTIPLES RUTAS
                logo_paths = [
                    "assets/logo.png",             # Directorio assets (PRINCIPAL)
                    "./assets/logo.png",           # Assets explícito
                    "logo.png",                    # Directorio actual
                    "./logo.png",                  # Directorio actual explícito
                    "static/logo.png",             # Subdirectorio static
                    "./static/logo.png",           # Static explícito
                    "../logo.png",                 # Directorio padre
                    "output/logo.png",             # Directorio output (donde hay otros archivos)
                    "assets/logo1.png",            # Assets fallback
                    "logo1.png",                   # Fallback logo1
                    "static/logo1.png"             # Fallback static
                ]
                logo_path = None
                
                print("🔍 Buscando logos corporativos...")
                print(f"   📁 Directorio actual: {os.getcwd()}")
                print(f"   📂 Archivos en directorio actual:")
                try:
                    files = [f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
                    for f in files[:10]:  # Mostrar máximo 10 archivos de imagen
                        print(f"      - {f}")
                    if len(files) > 10:
                        print(f"      ... y {len(files)-10} más")
                except Exception as e:
                    print(f"      Error listando archivos: {e}")
                
                # Verificar específicamente la carpeta assets
                print(f"   🎨 Verificando carpeta assets:")
                if os.path.exists('assets'):
                    print(f"      ✅ Carpeta assets existe")
                    try:
                        assets_files = [f for f in os.listdir('assets') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
                        print(f"      📁 Archivos en assets:")
                        for f in assets_files:
                            print(f"         - {f}")
                    except Exception as e:
                        print(f"      ❌ Error listando assets: {e}")
                else:
                    print(f"      ⚠️ Carpeta assets NO existe")
                
                for path in logo_paths:
                    abs_path = os.path.abspath(path)
                    print(f"   Verificando: {path} -> {abs_path} -> Existe: {os.path.exists(path)}")
                    if os.path.exists(path):
                        logo_path = path
                        print(f"   ✅ Logo encontrado: {path}")
                        break
                
                if logo_path:
                    print(f"🔄 Intentando cargar logo desde: {logo_path}")
                    import base64
                    try:
                       with open(logo_path, "rb") as img_file:
                            img_data = img_file.read()
                            print(f"   📁 Archivo leído: {len(img_data)} bytes")
                            logo_base64 = base64.b64encode(img_data).decode('utf-8')
                            print(f"   🔢 Base64 generado: {len(logo_base64)} caracteres")
                    except Exception as img_error:
                        print(f"   ❌ Error leyendo imagen: {str(img_error)}")
                        raise img_error
                    
                    # DISEÑO PROFESIONAL CON LOGO CORPORATIVO
                    logo_title_html = f"""
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 25px;">
                        <div class="corporate-logo-container" style="
                            background: linear-gradient(135deg, 
                                rgba(255, 255, 255, 0.95) 0%,
                                rgba(248, 250, 252, 0.98) 50%,
                                rgba(241, 245, 249, 0.95) 100%
                            );
                            backdrop-filter: blur(20px);
                            -webkit-backdrop-filter: blur(20px);
                            border: 2px solid rgba(255, 255, 255, 0.3);
                            border-radius: 20px;
                            padding: 25px;
                            box-shadow: 
                                0 25px 50px rgba(0, 0, 0, 0.15),
                                0 15px 35px rgba(59, 130, 246, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.8),
                                0 0 0 1px rgba(59, 130, 246, 0.1);
                            position: relative;
                            overflow: hidden;
                            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                        ">
                            <div style="
                                position: absolute;
                                top: -50%;
                                left: -50%;
                                width: 200%;
                                height: 200%;
                                background: radial-gradient(circle, rgba(59, 130, 246, 0.03) 0%, transparent 70%);
                                animation: rotate 20s linear infinite;
                                pointer-events: none;
                            "></div>
                            <img src="data:image/png;base64,{logo_base64}" 
                                class="corporate-logo" 
                                style="
                                    width: 120px; 
                                    height: auto; 
                                    max-height: 120px; 
                                    object-fit: contain;
                                    filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.1));
                                    transition: all 0.3s ease;
                                    position: relative;
                                    z-index: 2;
                                " 
                                alt="Logo SENER">
                            <div style="
                                position: absolute;
                                bottom: 0;
                                left: 0;
                                right: 0;
                                height: 3px;
                                background: linear-gradient(90deg, 
                                    transparent 0%, 
                                    rgba(59, 130, 246, 0.6) 25%, 
                                    rgba(6, 182, 212, 0.6) 75%, 
                                    transparent 100%
                                );
                                border-radius: 0 0 18px 18px;
                            "></div>
                    </div>
                        <div style="text-align: center;">
                            <h1 style="
                                margin: 0; 
                                font-size: 2.4rem; 
                                font-weight: 700; 
                                color: var(--tech-text-primary); 
                                text-shadow: 0 0 20px var(--tech-glow-primary); 
                                letter-spacing: -0.5px;
                                background: linear-gradient(135deg, var(--tech-text-primary), var(--tech-accent));
                                -webkit-background-clip: text;
                                -webkit-text-fill-color: transparent;
                                background-clip: text;
                            ">
                                AI Innovation Agent
                            </h1>
                            <p style="
                                margin: 15px 0 0 0; 
                                font-size: 1.1rem; 
                                color: var(--tech-text-secondary); 
                                font-weight: 500;
                                letter-spacing: 0.5px;
                            ">
                                Sistema Avanzado de Análisis de Ideas para SENER
                            </p>
                            <div style="
                                height: 3px; 
                                width: 120px; 
                                background: linear-gradient(135deg, var(--tech-primary), var(--tech-accent)); 
                                margin: 20px auto; 
                                border-radius: 3px;
                                box-shadow: 0 0 15px var(--tech-glow-accent);
                            "></div>
                        </div>
                    </div>
                    
                    <style>
                    @keyframes rotate {{
                        from {{ transform: rotate(0deg); }}
                        to {{ transform: rotate(360deg); }}
                    }}
                    
                    .corporate-logo-container:hover {{
                        transform: translateY(-5px) scale(1.02);
                        box-shadow: 
                            0 35px 70px rgba(0, 0, 0, 0.2),
                            0 20px 50px rgba(59, 130, 246, 0.15),
                            inset 0 1px 0 rgba(255, 255, 255, 0.9),
                            0 0 0 1px rgba(59, 130, 246, 0.2);
                    }}
                    
                    .corporate-logo:hover {{
                        transform: scale(1.05);
                        filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.15));
                    }}
                    </style>
                    """
                    print(f"✅ Logo corporativo SENER cargado desde {logo_path} con diseño profesional")
                else:
                    print("⚠️ Ningún logo corporativo encontrado en las rutas especificadas")
                    print("   Rutas verificadas:", logo_paths)
                    # Fallback corporativo profesional
                    logo_title_html = """
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 25px;">
                        <div class="corporate-logo-container" style="
                            background: linear-gradient(135deg, 
                                rgba(255, 255, 255, 0.95) 0%,
                                rgba(248, 250, 252, 0.98) 50%,
                                rgba(241, 245, 249, 0.95) 100%
                            );
                            backdrop-filter: blur(20px);
                            border: 2px solid rgba(255, 255, 255, 0.3);
                            border-radius: 20px;
                            padding: 25px;
                            box-shadow: 
                                0 25px 50px rgba(0, 0, 0, 0.15),
                                0 15px 35px rgba(59, 130, 246, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.8);
                            width: 140px;
                            height: 140px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        ">
                            <div style="text-align: center; color: #1e293b;">
                                <div style="font-weight: 800; font-size: 24px; line-height: 1.2; letter-spacing: 3px; color: #0ea5e9;">SENER</div>
                                <div style="font-size: 10px; font-weight: 600; margin-top: 8px; letter-spacing: 1.5px; color: #64748b;">ENGINEERING & TECHNOLOGY</div>
                            </div>
                        </div>
                        <div style="text-align: center;">
                            <h1 style="
                                margin: 0; 
                                font-size: 2.4rem; 
                                font-weight: 700; 
                                color: var(--tech-text-primary); 
                                text-shadow: 0 0 20px var(--tech-glow-primary); 
                                letter-spacing: -0.5px;
                            ">
                                AI Innovation Agent
                            </h1>
                            <p style="
                                margin: 15px 0 0 0; 
                                font-size: 1.1rem; 
                                color: var(--tech-text-secondary); 
                                font-weight: 500;
                            ">
                                Sistema Avanzado de Análisis de Ideas para SENER
                            </p>
                            <div style="
                                height: 3px; 
                                width: 120px; 
                                background: linear-gradient(135deg, var(--tech-primary), var(--tech-accent)); 
                                margin: 20px auto; 
                                border-radius: 3px;
                            "></div>
                        </div>
                    </div>
                    """
                    print("⚠️ Logo corporativo no encontrado - usando diseño profesional de emergencia")
            except Exception as e:
                print(f"❌ Error crítico cargando logo corporativo: {str(e)}")
                import traceback
                print("   Traceback completo:")
                traceback.print_exc()
                # Diseño corporativo de emergencia
                logo_title_html = """
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 25px;">
                    <div style="
                        background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.98));
                        border: 2px solid rgba(255, 255, 255, 0.3);
                        border-radius: 20px;
                        padding: 25px;
                        box-shadow: 0 25px 50px rgba(0, 0, 0, 0.15);
                        width: 140px;
                        height: 140px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    ">
                        <div style="text-align: center; color: #1e293b;">
                            <div style="font-weight: 800; font-size: 24px; line-height: 1.2; letter-spacing: 3px; color: #0ea5e9;">SENER</div>
                            <div style="font-size: 10px; font-weight: 600; margin-top: 8px; letter-spacing: 1.5px; color: #64748b;">ENGINEERING & TECHNOLOGY</div>
                        </div>
                    </div>
                    <div style="text-align: center;">
                        <h1 style="margin: 0; font-size: 2.4rem; font-weight: 700; color: var(--tech-text-primary); text-shadow: 0 0 20px var(--tech-glow-primary);">
                            AI Innovation Agent
                        </h1>
                        <p style="margin: 15px 0 0 0; font-size: 1.1rem; color: var(--tech-text-secondary); font-weight: 500;">
                            Sistema Avanzado de Análisis de Ideas para SENER
                        </p>
                        <div style="height: 3px; width: 120px; background: linear-gradient(135deg, var(--tech-primary), var(--tech-accent)); margin: 20px auto; border-radius: 3px;"></div>
                    </div>
                </div>
                """
                print(f"❌ Error cargando logo corporativo: {str(e)}")
            
            # Mostrar el HTML del logo y título centrado
            gr.HTML(logo_title_html)

    # --- AÑADIR LOS 4 TABS INTERACTIVOS ---
    with gr.Tabs():
        create_document_upload_tab()
        create_analysis_tab()
        create_ranking_tab()
        create_competitor_tab()
    
    # JavaScript para efectos interactivos finales
    gr.HTML("""
    <script>
    // Efectos de animación y UX mejorados
    document.addEventListener('DOMContentLoaded', function() {
        console.log('🎨 AI Innovation Agent - Interfaz estética mejorada cargada');
        
        // Efecto de aparición progresiva para elementos
        setTimeout(() => {
            const elements = document.querySelectorAll('.gradio-group, .gradio-textbox, .gradio-file');
            elements.forEach((el, index) => {
                if (el && !el.hasAttribute('data-animated')) {
                    el.setAttribute('data-animated', 'true');
                    el.style.opacity = '0';
                    el.style.transform = 'translateY(20px)';
                    setTimeout(() => {
                        el.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
                        el.style.opacity = '1';
                        el.style.transform = 'translateY(0)';
                    }, index * 100);
                }
            });
        }, 500);
        
        // Efectos de hover para botones
        function addButtonEffects() {
            const buttons = document.querySelectorAll('button:not([data-enhanced])');
            buttons.forEach(btn => {
                btn.setAttribute('data-enhanced', 'true');
                btn.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
                
                btn.addEventListener('mouseenter', function() {
                    if (!this.disabled) {
                        this.style.transform = 'translateY(-2px) scale(1.02)';
                        this.style.filter = 'brightness(1.1)';
                    }
                });
                
                btn.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0) scale(1)';
                    this.style.filter = 'brightness(1)';
                });
                
                btn.addEventListener('mousedown', function() {
                    if (!this.disabled) {
                        this.style.transform = 'translateY(0) scale(0.98)';
                    }
                });
                
                btn.addEventListener('mouseup', function() {
                    if (!this.disabled) {
                        this.style.transform = 'translateY(-2px) scale(1.02)';
                    }
                });
            });
        }
        
        // Aplicar efectos inicialmente y cada vez que se agreguen nuevos elementos
        addButtonEffects();
        setInterval(addButtonEffects, 2000);
        
        // Efecto de focus mejorado para inputs
        function addInputEffects() {
            const inputs = document.querySelectorAll('input:not([data-enhanced]), textarea:not([data-enhanced])');
            inputs.forEach(input => {
                input.setAttribute('data-enhanced', 'true');
                
                input.addEventListener('focus', function() {
                    this.style.transform = 'translateY(-1px)';
                    this.style.boxShadow = '0 8px 25px rgba(0,170,255,0.2)';
                });
                
                input.addEventListener('blur', function() {
                    this.style.transform = 'translateY(0)';
                    this.style.boxShadow = '';
                });
            });
        }
        
        addInputEffects();
        setInterval(addInputEffects, 2000);
        
        // Animación para contadores
        function animateCounter(element, endValue) {
            if (!element) return;
            
            const startValue = parseInt(element.textContent) || 0;
            const duration = 1000;
            const startTime = performance.now();
            
            function updateCounter(currentTime) {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                const currentValue = Math.floor(startValue + (endValue - startValue) * progress);
                element.textContent = currentValue;
                
                if (progress < 1) {
                    requestAnimationFrame(updateCounter);
                } else {
                    element.style.transform = 'scale(1.1)';
                    setTimeout(() => {
                        element.style.transform = 'scale(1)';
                    }, 200);
                }
            }
            
            requestAnimationFrame(updateCounter);
        }
        
        // Observador para detectar cambios en contadores
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                    const target = mutation.target;
                    if (target.id && target.id.includes('count')) {
                        const newValue = parseInt(target.textContent);
                        if (!isNaN(newValue) && newValue > 0) {
                            animateCounter(target, newValue);
                        }
                    }
                }
            });
        });
        
        // Observar cambios en elementos con IDs que contengan 'count'
        document.querySelectorAll('[id*="count"]').forEach(el => {
            observer.observe(el, { childList: true, characterData: true, subtree: true });
        });
    });
    </script>
    """)

import socket

if __name__ == "__main__":
    # Obtener IP local
    ip = socket.gethostbyname(socket.gethostname())

    # Mostrar URL útil
    print(f"\n🌐 Accede desde tu navegador usando:")
    print(f"🔸 En esta máquina: http://localhost:7860")
    print(f"🔸 Desde otra máquina en tu red: http://{ip}:7860\n")



    # Lanzar servidor accesible
    demo.launch(server_name="0.0.0.0", server_port=7860)
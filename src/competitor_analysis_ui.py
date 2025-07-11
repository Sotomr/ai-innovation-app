import gradio as gr
from competitor_analysis_module import CompetitorAnalysis
from ranking_module import RankingModule
import pandas as pd
import json
import os
from typing import List, Dict, Any
import time
import traceback
from analysis_module2 import analyze_ideas_batch
from competition_pdf_module import generate_competition_analysis_pdf

class CompetitorAnalysisUI:
    def __init__(self):
        self.analyzer = CompetitorAnalysis()
        self.ranking = RankingModule()
        self.max_ideas = 6
        self.selected_ideas = {}  # Diccionario de ideas seleccionadas {id: idea_data}

    def create_competitor_tab(self) -> gr.Tab:
        """
        Crea la pestaña de análisis de competidores
        """
        with gr.Tab("🕵️ Análisis de Competidores") as tab:
            # Header elegante para la pestaña de competidores
            gr.HTML("""
            <div style="text-align: center; margin-bottom: 35px; padding: 25px; background: linear-gradient(135deg, rgba(155,89,182,0.08), rgba(142,68,173,0.08)); border-radius: 20px; border: 2px solid rgba(155,89,182,0.1);">
                <div style="font-size: 4.5rem; margin-bottom: 20px;">🕵️</div>
                <h2 style="color: #9b59b6; margin: 0; font-weight: 700; font-size: 2.2rem;">Análisis Competitivo Inteligente</h2>
                <p style="color: #666; font-size: 1.2rem; margin: 15px 0; font-weight: 500;">Sistema híbrido LLM + Web Scraping para insights estratégicos</p>
                <div style="height: 4px; width: 150px; background: linear-gradient(135deg, #9b59b6, #8e44ad); margin: 20px auto; border-radius: 4px;"></div>
                <p style="color: #888; font-size: 1rem; margin: 0;">🔍 8 secciones estratégicas • 📊 Benchmarking cuantitativo • 🌐 Búsqueda web avanzada</p>
            </div>
            """)
            
            # Instrucciones con diseño elegante
            gr.HTML("""
            <div style="background: var(--tech-gradient-1); border-radius: 18px; padding: 25px; margin-bottom: 25px; box-shadow: 0 15px 40px var(--tech-shadow-2), 0 0 0 1px var(--tech-border-1), inset 0 2px 0 rgba(255,255,255,0.08); border: 1px solid var(--tech-border-1);">
                <h3 style="color: var(--tech-accent); margin-bottom: 25px; font-weight: 600; font-size: 1.4rem;">📋 Proceso de Análisis Competitivo</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">
                    <div style="padding: 18px; background: var(--tech-surface-2); border-radius: 12px; border-left: 4px solid var(--tech-success); border: 1px solid var(--tech-border-1);">
                        <div style="font-size: 2rem; margin-bottom: 10px;">🟢</div>
                        <strong style="color: var(--tech-success); font-size: 1.1rem;">Paso 1: Cargar Ideas</strong><br>
                        <span style="color: var(--tech-text-secondary);">Haga clic en <strong>'Cargar Ideas Rankeadas'</strong> para obtener las ideas del módulo de ranking</span>
                    </div>
                    <div style="padding: 18px; background: var(--tech-surface-2); border-radius: 12px; border-left: 4px solid var(--tech-primary); border: 1px solid var(--tech-border-1);">
                        <div style="font-size: 2rem; margin-bottom: 10px;">☑️</div>
                        <strong style="color: var(--tech-primary); font-size: 1.1rem;">Paso 2: Seleccionar</strong><br>
                        <span style="color: var(--tech-text-secondary);">Seleccione las ideas que desee analizar utilizando los checkboxes (máximo 6)</span>
                    </div>
                    <div style="padding: 18px; background: var(--tech-surface-2); border-radius: 12px; border-left: 4px solid var(--tech-warning); border: 1px solid var(--tech-border-1);">
                        <div style="font-size: 2rem; margin-bottom: 10px;">🔄</div>
                        <strong style="color: var(--tech-warning); font-size: 1.1rem;">Paso 3: Confirmar</strong><br>
                        <span style="color: var(--tech-text-secondary);">Haga clic en <strong>'Actualizar Selección'</strong> para confirmar su selección</span>
                    </div>
                    <div style="padding: 18px; background: var(--tech-surface-2); border-radius: 12px; border-left: 4px solid var(--tech-accent); border: 1px solid var(--tech-border-1);">
                        <div style="font-size: 2rem; margin-bottom: 10px;">📝</div>
                        <strong style="color: var(--tech-accent); font-size: 1.1rem;">Paso 4: Contexto</strong><br>
                        <span style="color: var(--tech-text-secondary);">(Opcional) Añada contexto adicional y fuentes específicas</span>
                    </div>
                    <div style="padding: 18px; background: var(--tech-surface-2); border-radius: 12px; border-left: 4px solid var(--tech-error); border: 1px solid var(--tech-border-1); grid-column: span 1;">
                        <div style="font-size: 2rem; margin-bottom: 10px;">📑</div>
                        <strong style="color: var(--tech-error); font-size: 1.1rem;">Paso 5: Analizar</strong><br>
                        <span style="color: var(--tech-text-secondary);">Haga clic en <strong>'Realizar Análisis'</strong> para generar el reporte PDF profesional</span>
                    </div>
                </div>
                <div style="margin-top: 25px; padding: 18px; background: var(--tech-surface-3); border-radius: 12px; border-left: 4px solid var(--tech-warning); border: 1px solid var(--tech-border-1); text-align: center; box-shadow: 0 4px 15px var(--tech-shadow-1);">
                    <p style="margin: 0; color: var(--tech-text-primary); font-weight: 600; font-size: 1.1rem;">
                        🎯 El análisis incluye: Mapeo competitivo, Benchmarking, Landscape tecnológico, Análisis de mercado, DAFO, Regulaciones ESG, Roadmap estratégico y Resumen ejecutivo
                    </p>
                </div>
            </div>
            """)
            
            # Mostrar ideas y selecciones
            ideas_display = gr.HTML("<p>Haga clic en 'Cargar Ideas Rankeadas' para comenzar</p>")
            selection_status = gr.HTML(f"<p>Ideas seleccionadas: 0/{self.max_ideas}</p>")
            
            # CSS personalizado para botones lila
            gr.HTML("""
            <style>
            .competitor-btn-primary {
                background: linear-gradient(135deg, #9b59b6, #8e44ad) !important;
                border: 1px solid #9b59b6 !important;
                color: white !important;
                border-radius: 12px !important;
                padding: 12px 24px !important;
                font-weight: 600 !important;
                transition: all 0.3s ease !important;
                box-shadow: 0 4px 15px rgba(155, 89, 182, 0.3) !important;
            }
            .competitor-btn-primary:hover {
                background: linear-gradient(135deg, #8e44ad, #7d3c98) !important;
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 25px rgba(155, 89, 182, 0.4) !important;
            }
            .competitor-btn-secondary {
                background: linear-gradient(135deg, rgba(155, 89, 182, 0.1), rgba(142, 68, 173, 0.1)) !important;
                border: 1px solid #9b59b6 !important;
                color: #9b59b6 !important;
                border-radius: 12px !important;
                padding: 12px 24px !important;
                font-weight: 600 !important;
                transition: all 0.3s ease !important;
            }
            .competitor-btn-secondary:hover {
                background: linear-gradient(135deg, rgba(155, 89, 182, 0.2), rgba(142, 68, 173, 0.2)) !important;
                transform: translateY(-2px) !important;
                color: white !important;
            }
            </style>
            """)
            
            # Botones principales
            with gr.Row():
                load_btn = gr.Button("Cargar Ideas Rankeadas", variant="primary", elem_classes=["competitor-btn-primary"])
                update_selection_btn = gr.Button("Actualizar Selección", variant="secondary", elem_classes=["competitor-btn-secondary"])
            
            # Usar CheckboxGroup para mostrar todas las ideas
            idea_checkboxes = gr.CheckboxGroup(
                label="Seleccione las ideas a analizar (máximo 6)",
                choices=[],
                value=[],
                visible=False
            )
            
            # Contexto opcional
            context = gr.Textbox(
                label="Contexto Adicional (Opcional)",
                placeholder="Ingrese información adicional para el análisis...",
                lines=3
            )
            
            # 🆕 NUEVO: Fuentes adicionales - SOLO UI, sin lógica aún
            extra_sources = gr.Textbox(
                label="🔍 Fuentes Adicionales (Opcional)",
                placeholder="Especifique plataformas donde buscar información adicional (ej: Crunchbase, LinkedIn, etc.)",
                lines=2,
                info="Estas fuentes complementarán la búsqueda estándar del análisis"
            )
            
            # Botón de análisis y estado
            analyze_btn = gr.Button("Realizar Análisis", variant="primary", size="lg", elem_classes=["competitor-btn-primary"])
            status = gr.Textbox(label="Estado", interactive=False)
            
            # Elemento para descargar el PDF
            pdf_download = gr.File(label="Informe PDF de Análisis", interactive=False, visible=False)
            
            # --- NUEVO: Área de log de queries ---
            query_log = gr.Markdown("""<div style='font-size:0.95em; color:#8ecae6;'><b>Log de queries y progreso:</b><br>Esperando análisis...</div>""", visible=True)
            
            # Estado para datos de ideas y mapeo
            all_ideas_data = gr.State([])
            idea_id_map = gr.State({})  # Mapear opciones a IDs de ideas
            
            # Función para cargar ideas
            def load_ranked_ideas():
                try:
                    ranked_ideas = self.ranking.get_ranked_ideas()
                    if not ranked_ideas:
                        return "<p>No hay ideas rankeadas disponibles</p>", [], {}, [], gr.update(visible=False)
                    
                    # Preparar datos de ideas - Mostrar todas las ideas disponibles
                    ideas_list = []
                    for i, idea in enumerate(ranked_ideas):
                        idea_text = idea.get("idea", "")
                        
                        # 🔥 EXTRACCIÓN CORRECTA DE TÍTULO - PRIORIZAR TÍTULO REAL
                        title = idea.get("title", "")
                        
                        # 🔥 SOLO si NO hay título, extraer de la primera línea LIMPIANDO prefijos
                        if not title or title.strip() == "":
                            first_line = idea_text.split('\n')[0] if idea_text else ""
                            # Limpiar prefijos "Idea X:" de la primera línea
                            import re
                            clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                            title = clean_title[:80] if clean_title else f"Idea {i+1}"
                        
                        score = idea.get("score", 0)
                        
                        # 🔥 DEBUG: Mostrar título extraído
                        print(f"🔥 [UI] Idea {i+1}: título='{title}' (original: '{idea.get('title', 'NO_TITLE')}')")
                        
                        ideas_list.append({
                            "id": i,
                            "title": title,
                            "idea": idea_text,
                            "score": score
                        })
                    
                    # Generar HTML con tabla de ideas
                    html = """
                    <style>
                    .ideas-table {
                        width: 100%;
                        border-collapse: collapse;
                        margin-bottom: 20px;
                        background: var(--tech-surface-1) !important;
                        border-radius: 12px !important;
                        overflow: hidden !important;
                        box-shadow: 0 4px 15px var(--tech-shadow-1) !important;
                    }
                    .ideas-table th {
                        background: var(--tech-gradient-2) !important;
                        color: var(--tech-text-primary) !important;
                        text-align: left;
                        padding: 15px 12px;
                        border-bottom: 2px solid var(--tech-border-2) !important;
                        font-weight: 700 !important;
                        font-size: 14px !important;
                    }
                    .ideas-table td {
                        padding: 12px;
                        border-bottom: 1px solid var(--tech-border-1) !important;
                        background: var(--tech-surface-2) !important;
                        color: var(--tech-text-secondary) !important;
                        transition: all 0.3s ease !important;
                    }
                    .ideas-table tr:hover td {
                        background: var(--tech-surface-3) !important;
                        color: var(--tech-text-primary) !important;
                        transform: scale(1.005) !important;
                    }
                    .idea-score {
                        text-align: right;
                        font-weight: bold;
                        color: var(--tech-warning) !important;
                    }
                    </style>
                    
                    <table class="ideas-table">
                        <tr>
                            <th>N°</th>
                            <th>Idea</th>
                            <th>Score</th>
                        </tr>
                    """
                    
                    # Crear filas de tabla para todas las ideas
                    for i, idea in enumerate(ideas_list):
                        html += f"""
                        <tr>
                            <td><strong>{i+1}</strong></td>
                            <td><strong>{idea['title']}</strong></td>
                            <td class="idea-score">{idea['score']:.1f}</td>
                        </tr>
                        """
                    
                    total_ideas = len(ideas_list)
                    html += f"""
                    </table>
                    <p>Se han cargado {total_ideas} ideas. Seleccione las ideas que desee analizar usando los checkboxes a continuación. 
                    Recuerde que puede seleccionar como máximo {self.max_ideas} ideas para el análisis.</p>
                    """
                    
                    # Reiniciar selecciones
                    self.selected_ideas = {}
                    
                    # Crear opciones para CheckboxGroup
                    checkbox_options = []
                    id_map = {}
                    
                    for i, idea in enumerate(ideas_list):
                        option_text = f"Idea {i+1}: {idea['title']}"
                        checkbox_options.append(option_text)
                        id_map[option_text] = i
                        # Preseleccionar las primeras 6 ideas o menos
                        if i < min(6, total_ideas):
                            self.selected_ideas[i] = ideas_list[i]
                    
                    # Seleccionar las primeras 6 ideas o todas si hay menos
                    default_selection = checkbox_options[:min(6, total_ideas)]
                    
                    # Actualizar conteo inicial de selecciones
                    selection_html = f"<p>Ideas seleccionadas: {len(self.selected_ideas)}/{self.max_ideas}</p>"
                    if self.selected_ideas:
                        selection_html += "<ul>"
                        for idea_id, idea_data in self.selected_ideas.items():
                            selection_html += f"<li><strong>Idea {idea_id+1}:</strong> {idea_data['title']}</li>"
                        selection_html += "</ul>"
                    
                    return html, ideas_list, id_map, default_selection, gr.update(
                        choices=checkbox_options,
                        value=default_selection,
                        visible=True
                    )
                
                except Exception as e:
                    print(f"Error cargando ideas: {str(e)}")
                    traceback.print_exc()
                    return f"<p>Error cargando ideas: {str(e)}</p>", [], {}, [], gr.update(visible=False)
            
            # Función para actualizar estado de selección
            def update_selection(selected_options, ideas_list, id_map):
                try:
                    # Reiniciar selecciones
                    self.selected_ideas = {}
                    
                    # Actualizar selecciones basado en opciones seleccionadas
                    for option in selected_options:
                        if option in id_map:
                            idea_id = id_map[option]
                            if idea_id < len(ideas_list):
                                self.selected_ideas[idea_id] = ideas_list[idea_id]
                    
                    # Contar total de selecciones
                    selected_count = len(self.selected_ideas)
                    
                    # Verificar límites de selección
                    warning_message = ""
                    if selected_count > self.max_ideas:
                        warning_message = f"<p style='color: red; font-weight: bold;'>⚠️ ¡ADVERTENCIA! Ha seleccionado {selected_count} ideas. El máximo permitido es {self.max_ideas}. Por favor, desmarque algunas ideas.</p>"
                    elif selected_count == 0:
                        warning_message = "<p style='color: red; font-weight: bold;'>⚠️ Debe seleccionar al menos 1 idea.</p>"
                    
                    # Mostrar número de ideas seleccionadas
                    html = f"<p>Ideas seleccionadas: {selected_count}/{self.max_ideas}</p>"
                    
                    # Añadir mensaje de advertencia si es necesario
                    if warning_message:
                        html = warning_message + html
                    
                    # Mostrar lista de ideas seleccionadas
                    if selected_count > 0:
                        html += "<ul>"
                        for idea_id, idea_data in self.selected_ideas.items():
                            html += f"<li><strong>Idea {idea_id+1}:</strong> {idea_data['title']}</li>"
                        html += "</ul>"
                    
                    return html
                    
                except Exception as e:
                    print(f"Error actualizando selección: {str(e)}")
                    traceback.print_exc()
                    return "<p>Error actualizando selección</p>"
            
            # --- NUEVO: Función de análisis con log ---
            def perform_analysis_with_log(context, extra_sources, ideas_list):
                try:
                    log_msgs = []
                    def log(msg):
                        log_msgs.append(msg)
                    if not self.selected_ideas:
                        log_msgs.append("❌ <b>No hay ideas seleccionadas.</b> Por favor, seleccione al menos una idea y haga clic en 'Actualizar Selección'.")
                        return "⚠️ No hay ideas seleccionadas. Por favor, seleccione al menos una idea y haga clic en 'Actualizar Selección'.", gr.update(visible=False), '<br>'.join(log_msgs)
                    selected_count = len(self.selected_ideas)
                    if selected_count > self.max_ideas:
                        log_msgs.append(f"❌ <b>Demasiadas ideas seleccionadas:</b> {selected_count} (máximo {self.max_ideas})")
                        return f"⚠️ Ha seleccionado {selected_count} ideas. El máximo permitido es {self.max_ideas}. Por favor, desmarque algunas ideas y haga clic en 'Actualizar Selección'.", gr.update(visible=False), '<br>'.join(log_msgs)
                    elif selected_count == 0:
                        log_msgs.append("❌ <b>No hay ideas seleccionadas.</b>")
                        return "⚠️ Debe seleccionar al menos 1 idea. Por favor, seleccione ideas y haga clic en 'Actualizar Selección'.", gr.update(visible=False), '<br>'.join(log_msgs)
                    ideas_to_analyze = []
                    for idea_id, idea_data in self.selected_ideas.items():
                        ideas_to_analyze.append(idea_data)
                    log(f"🟢 <b>Iniciando análisis competitivo LLM-first en paralelo...</b>")
                    log(f"📋 <b>Total de ideas a analizar:</b> {len(ideas_to_analyze)}")
                    
                    # 🆕 LOG de fuentes adicionales (IMPLEMENTADO - CON PRE-FILTRO INTELIGENTE)
                    if extra_sources and extra_sources.strip():
                        log(f"🔍 <b>Fuentes adicionales especificadas:</b> {extra_sources}")
                        log("🧠 <b>Pre-filtro inteligente:</b> El LLM evaluará qué fuentes son relevantes para cada sección")
                    
                    # Lanzar análisis en paralelo con nueva estructura (CON extra_sources)
                    batch_result = self.analyzer.analyze_ideas_batch_competitor(ideas_to_analyze, context, extra_sources)
                    
                    # Extraer datos de la nueva estructura
                    analyses = batch_result.get('ideas', [])
                    executive_summary = batch_result.get('executive_summary', {})
                    
                    secciones = {}
                    for i, (idea_dict, analysis) in enumerate(zip(ideas_to_analyze, analyses), 1):
                        idea_title = idea_dict.get('title') or idea_dict.get('idea', f'Idea {i}')
                        if 'error' in analysis:
                            log(f"❌ <b>Error al analizar Idea {i}:</b> {analysis['error']}")
                        else:
                            log(f"✅ <b>Idea {i} analizada correctamente.</b>")
                        secciones[f"Idea {i}"] = analysis
                    
                    # Añadir resumen ejecutivo global
                    if executive_summary and executive_summary.get('texto'):
                        log("✅ <b>Resumen ejecutivo global generado correctamente.</b>")
                        secciones['GLOBAL_EXECUTIVE_SUMMARY'] = executive_summary
                    else:
                        log("⚠️ <b>No se pudo generar resumen ejecutivo global.</b>")
                    output_name = f"analisis_competencia_{int(time.time())}"
                    log("📝 <b>Generando informe PDF profesional...</b>")
                    # --- Nueva estructura para PDF con resumen ejecutivo global ---
                    # Separar resumen ejecutivo global de las ideas individuales
                    global_exec_summary = secciones.pop('GLOBAL_EXECUTIVE_SUMMARY', None)
                    ideas_for_pdf = []
                    
                    # Combinar datos de idea original con análisis
                    idea_index = 0
                    for key, analysis_data in secciones.items():
                        if key.startswith('Idea ') and idea_index < len(ideas_to_analyze):
                            original_idea = ideas_to_analyze[idea_index]
                            
                            # Crear estructura completa para PDF
                            idea_for_pdf = dict(analysis_data)  # Copiar análisis
                            
                            # 🔥 EXTRACCIÓN CRÍTICA DE TÍTULO - PRIORIZAR TÍTULO REAL
                            idea_title = original_idea.get('title', '') or original_idea.get('idea_title', '')
                            idea_text = str(original_idea.get('idea', ''))
                            
                            # 🔥 SOLO si NO hay título, extraer de texto LIMPIANDO prefijos
                            if not idea_title or idea_title.strip() == "":
                                first_line = idea_text.split('\n')[0] if idea_text else ""
                                import re
                                clean_title = re.sub(r'^idea\s*\d*[\.:]\s*', '', first_line, flags=re.IGNORECASE).strip()
                                idea_title = clean_title[:80] if clean_title else f"Idea {idea_index + 1}"
                            
                            idea_for_pdf.update({
                                'idea_title': idea_title,
                                'idea_text': idea_text,
                                'original_idea_data': original_idea
                            })
                            
                            # ✅ DEBUG: Mostrar qué se está enviando al PDF
                            print(f"🔥🔥🔥 [DEBUG UI] Idea {idea_index + 1}: 🔥🔥🔥")
                            print(f"🔥🔥🔥   - Título extraído: '{idea_title}' 🔥🔥🔥")
                            print(f"🔥🔥🔥   - Texto: '{idea_text[:100]}...' 🔥🔥🔥")
                            print(f"🔥🔥🔥   - Campos originales: {list(original_idea.keys())} 🔥🔥🔥")
                            print(f"🔥🔥🔥   - idea_for_pdf tendrá idea_title: '{idea_title}' 🔥🔥🔥")
                            
                            ideas_for_pdf.append(idea_for_pdf)
                            idea_index += 1
                    
                    # Estructura para el PDF: resumen global + ideas individuales
                    pdf_input = {
                        'executive_summary': global_exec_summary,
                        'ideas': ideas_for_pdf,
                        'total_ideas': len(ideas_for_pdf),
                        'original_ideas': ideas_to_analyze  # Para referencia
                    }
                    print("[DEBUG] Estructura enviada al PDF:")
                    print(json.dumps(pdf_input, indent=2, ensure_ascii=False))
                    pdf_path = generate_competition_analysis_pdf(pdf_input, output_name)
                    if pdf_path and os.path.exists(pdf_path):
                        log(f"✅ <b>Informe PDF generado exitosamente:</b> {pdf_path}")
                        log("🎉 <b>Análisis competitivo finalizado.</b>")
                        return (
                            f"✅ Análisis competitivo completado. Se analizaron {len(ideas_to_analyze)} ideas. Puede descargar el informe PDF a continuación.",
                            gr.update(value=pdf_path, visible=True),
                            '<br>'.join(log_msgs)
                        )
                    log("❌ <b>Error al generar el informe PDF.</b>")
                    return (
                        "❌ Error al generar el análisis competitivo. Por favor, intente nuevamente.",
                        gr.update(visible=False),
                        '<br>'.join(log_msgs)
                    )
                except Exception as e:
                    return f"❌ Error durante el análisis competitivo: {str(e)}", gr.update(visible=False), f"<div style='color:red;'>Error: {str(e)}</div>"
            
            # Configurar eventos
            load_btn.click(
                fn=load_ranked_ideas,
                outputs=[ideas_display, all_ideas_data, idea_id_map, selection_status, idea_checkboxes]
            )
            
            update_selection_btn.click(
                fn=update_selection,
                inputs=[idea_checkboxes, all_ideas_data, idea_id_map],
                outputs=[selection_status]
            )
            
            analyze_btn.click(
                fn=perform_analysis_with_log,
                inputs=[context, extra_sources, all_ideas_data],  # 🆕 Añadido extra_sources
                outputs=[status, pdf_download, query_log]
            )
            
            return tab

    def perform_analysis(self, ideas_to_analyze, context: str = ""):
        """
        Realiza el análisis de las ideas seleccionadas
        """
        try:
            if not ideas_to_analyze:
                return False
            # Realizar análisis
            result = analyze_ideas_batch(ideas_to_analyze, context)
            # --- NUEVO: Si hay error, mostrarlo en la UI ---
            if isinstance(result, dict) and "error" in result:
                return f"❌ {result['error']}"
            return result
        except Exception as e:
            print(f"❌ Error en análisis: {str(e)}")
            traceback.print_exc()
            return False 
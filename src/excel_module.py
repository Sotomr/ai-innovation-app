import pandas as pd
import re
from fpdf import FPDF
import tempfile
from concurrent.futures import ThreadPoolExecutor
import openai
from docx import Document
import os
from datetime import datetime
import numpy as np

# Configuración de OpenAI
AZURE_OPENAI_ENDPOINT = "https://azureaiservices-ailab-dev-003.openai.azure.com/"
AZURE_OPENAI_API_KEY = "67788dc5a5a6425c9551d774c938b162"
DEPLOYMENT_NAME = "gpt-4o"
API_VERSION = "2024-05-01-preview"

openai.api_type = "azure"
openai.api_base = AZURE_OPENAI_ENDPOINT
openai.api_version = API_VERSION
openai.api_key = AZURE_OPENAI_API_KEY

def generar_descripcion_breve(texto, contexto, deployment_name, max_tokens=50, temperature=0.3):
    """
    Llama a la API de OpenAI para generar una descripción muy breve (menos de 20 palabras)
    basada en el texto (propuesta) y el contexto dado.
    """
    prompt = (
        f"Contexto: {contexto}\n"
        "Dada la siguiente idea, resume en una frase muy breve y concisa lo que es:\n\n"
        f"Idea: {texto}\n\n"
        "La respuesta debe ser muy breve (menos de 20 palabras)."
    )
    try:
        response = openai.ChatCompletion.create(
            engine=deployment_name,
            messages=[
                {"role": "system", "content": "Eres un experto en innovación y análisis estratégico."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        resumen = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        resumen = f"Error: {e}"
    return resumen

def procesar_excel_clusters(excel_file, contexto, deployment_name):
    """
    Procesa el Excel para extraer ideas agrupadas en clusters.
    
    Se busca la fila de encabezado (aquella que contiene "descripción" en alguna de sus celdas)
    y se procesan solo las filas debajo de ese encabezado.
    
    Se asume:
      - Columna A (índice 0): contiene el nombre del cluster (celdas fusionadas, se propagan hacia abajo).
      - Columna B (índice 1): si es convertible a número, la fila es una idea; si no, se ignora.
      - Columna C (índice 2): contiene el texto de la propuesta.
    
    Para cada fila con número en la columna B se genera una breve descripción mediante OpenAI.
    Luego se agrupan las ideas por cluster y se genera un PDF con la siguiente estructura:
    
         Cluster X:
             Idea 1 - [breve descripción]
             Idea 2 - [breve descripción]
             ...
    
    Retorna:
      - clusters: diccionario con la información organizada.
      - pdf_filepath: ruta del archivo PDF generado.
      - mensaje: resumen del procesamiento.
    """
    # Leer el Excel sin header para poder buscar la fila de encabezado
    df = pd.read_excel(excel_file, header=None)
    
    # Buscar la fila donde aparece "descripción" (ignorando mayúsculas)
    header_idx = None
    for i, row in df.iterrows():
        if row.astype(str).str.lower().str.contains("descripción").any():
            header_idx = i
            break
    if header_idx is None:
        return {}, "", "No se encontró la fila de encabezados con 'descripción'."
    
    # Procesar solo las filas debajo del header
    df_data = df.iloc[header_idx+1:].copy()
    
    # Propagar el valor de la columna A (Cluster) hacia abajo.
    df_data[0] = df_data[0].ffill()
    
    clusters = {}
    for idx, row in df_data.iterrows():
        cluster = str(row[0]).strip()
        if not cluster or cluster.lower() == "nan":
            continue
        if cluster not in clusters:
            clusters[cluster] = []
        
        indicator = row[1]
        # Descarta filas donde el indicador sea NaN o "nan"
        if pd.isna(indicator) or str(indicator).strip().lower() == "nan":
            continue
        try:
            _ = float(indicator)
        except (ValueError, TypeError):
            continue
        
        texto = row[2]
        if pd.isna(texto) or str(texto).strip() == "":
            continue
        texto = str(texto).strip()
        brief_desc = generar_descripcion_breve(texto, contexto, deployment_name)
        idea_entry = {"numero": str(indicator).strip(), "descripcion": brief_desc, "propuesta": texto}
        clusters.setdefault(cluster, []).append(idea_entry)
    
    # Ordenar las ideas dentro de cada cluster por el valor numérico original (opcional)
    for cluster_name, ideas_list in clusters.items():
        ideas_list.sort(key=lambda x: float(x["numero"]))
    
    # Generar el PDF organizado con numeración secuencial "Idea 1, Idea 2, ..."
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Listado de Ideas por Cluster", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    
    for cluster_name, ideas_list in clusters.items():
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Cluster {cluster_name}:", ln=True)
        pdf.ln(2)
        pdf.set_font("Arial", size=12)
        counter = 1  # Numeración secuencial para cada idea en el cluster
        for idea in ideas_list:
            pdf.cell(0, 10, f"  Idea {counter} - {idea['descripcion']}", ln=True)
            counter += 1
        pdf.ln(5)
    
    pdf_string = pdf.output(dest="S").encode("latin1")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_string)
        pdf_filepath = tmp.name
    
    total_ideas = sum(len(ideas) for ideas in clusters.values())
    mensaje = f"Se han procesado {total_ideas} ideas en {len(clusters)} clusters."
    return clusters, pdf_filepath, mensaje

def process_excel_file(file_path, context=None):
    """
    Procesa el archivo Excel y extrae las ideas válidas de forma eficiente
    """
    try:
        # Leer el Excel
        df = pd.read_excel(file_path, header=None)
        
        # Configuración de procesamiento
        config = {
            'start_row': 26,  # Índice de la fila donde empiezan los datos
            'cluster_col': 0,  # Columna del cluster
            'number_col': 1,   # Columna del número
            'text_col': 2      # Columna del texto
        }
        
        # Filtrar solo las filas relevantes
        df = df.iloc[config['start_row']:]
        
        # Limpiar datos
        df = df.replace('', np.nan)
        df = df.replace('nan', np.nan)
        
        # Propagar valores de cluster (columna A) hacia abajo
        df[config['cluster_col']] = df[config['cluster_col']].ffill()
        
        # Filtrar filas válidas
        valid_rows = df[
            (df[config['number_col']].notna()) &  # Columna B no vacía
            (df[config['text_col']].notna()) &    # Columna C no vacía
            (df[config['text_col']].str.strip().astype(bool))  # Columna C no solo espacios
        ]
        
        # Procesar ideas en paralelo con un máximo de 10 workers
        enriched_ideas = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _, row in valid_rows.iterrows():
                cluster = str(row[config['cluster_col']]).strip()
                idea_text = str(row[config['text_col']]).strip()
                futures.append(
                    executor.submit(enrich_idea_with_context, idea_text, cluster, context)
                )
            
            # Recolectar resultados
            for future in futures:
                try:
                    result = future.result()
                    if result:
                        enriched_ideas.append(result)
                except Exception as e:
                    print(f"Error procesando idea: {str(e)}")
        
        return enriched_ideas
    except Exception as e:
        print(f"Error procesando Excel: {str(e)}")
        return []

def generate_ideas_pdf(ideas, context=None):
    """
    Genera un PDF con las ideas enriquecidas usando fuentes estándar Arial
    """
    try:
        # Crear PDF
        pdf = FPDF()
        # Configurar para UTF-8
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Configurar fuentes Arial
        pdf.set_font('Arial', 'B', 16)
        # Usar encode/decode para manejar caracteres especiales
        pdf.cell(0, 10, "Análisis de Ideas de Innovación - SENER", ln=True, align="C")
        pdf.ln(5)
        
        # Agregar fecha
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
        pdf.ln(5)
        
        # Organizar ideas por cluster
        clusters = {}
        for idea in ideas:
            if isinstance(idea, dict) and 'cluster' in idea:
                cluster = str(idea['cluster'])
                if not cluster in clusters:
                    clusters[cluster] = []
                clusters[cluster].append(idea)
        
        # Generar contenido por cluster
        for cluster, cluster_ideas in clusters.items():
            try:
                # Título del cluster
                pdf.set_font('Arial', 'B', 14)
                safe_cluster = str(cluster).encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(0, 10, f"Campo: {safe_cluster}", ln=True)
                pdf.ln(2)
                
                # Ideas del cluster
                for i, idea in enumerate(cluster_ideas, 1):
                    if not isinstance(idea, dict):
                        continue
                        
                    try:
                        pdf.set_font('Arial', 'B', 12)
                        pdf.cell(0, 10, f"Idea {i}:", ln=True)
                        
                        pdf.set_font('Arial', '', 12)
                        # Texto original de la idea (con codificación segura)
                        idea_text = str(idea.get('idea', 'No hay texto disponible'))
                        safe_idea = idea_text.encode('latin-1', 'replace').decode('latin-1')
                        pdf.multi_cell(0, 10, f"Propuesta: {safe_idea}")
                        
                        # Análisis de la idea (con codificación segura)
                        analysis_text = str(idea.get('analysis', 'No hay análisis disponible'))
                        safe_analysis = analysis_text.encode('latin-1', 'replace').decode('latin-1')
                        pdf.multi_cell(0, 10, f"Análisis: {safe_analysis}")
                        pdf.ln(5)
                    except Exception as e:
                        print(f"❌ Error procesando idea {i} del cluster {cluster}: {str(e)}")
                        continue
                
                pdf.ln(5)
            except Exception as e:
                print(f"❌ Error procesando cluster {cluster}: {str(e)}")
                continue
        
        # Guardar PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"ideas_analizadas_{timestamp}.pdf")
        
        try:
            pdf.output(output_path)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"✅ PDF generado correctamente: {output_path}")
                return output_path
            else:
                print("❌ Error: El archivo PDF no se generó correctamente")
                return None
        except Exception as e:
            print(f"❌ Error guardando PDF: {str(e)}")
            # Intentar guardar en ubicación alternativa
            backup_path = os.path.join(tempfile.gettempdir(), f"ideas_{timestamp}.pdf")
            try:
                pdf.output(backup_path)
                if os.path.exists(backup_path):
                    print(f"✅ PDF guardado en ubicación alternativa: {backup_path}")
                    return backup_path
            except:
                pass
            return None
            
    except Exception as e:
        print(f"❌ Error generando PDF: {str(e)}")
        return None

def enrich_idea_with_context(idea_text, cluster, context):
    """
    Enriquece una idea con su contexto y cluster usando OpenAI
    """
    try:
        # Configuración de OpenAI
        openai_config = {
            'temperature': 0.4,  # Reducido para mayor consistencia
            'max_tokens': 150,   # Ajustado para respuestas más concisas
            'engine': DEPLOYMENT_NAME
        }
        
        prompt = f"""
        Como experto tecnológico, explica brevemente la siguiente idea del campo {cluster}:

        Idea: {idea_text}
        Contexto: {context}

        Proporciona una explicación clara y concisa (2-3 líneas) que:
        - Desarrolle el concepto principal
        - Destaque los aspectos tecnológicos relevantes
        - Explique cómo funcionaría en la práctica

        La explicación debe ser técnica pero comprensible, evitando generalidades.
        NO menciones evaluaciones de viabilidad ni impactos en la empresa.

        Formato de respuesta:
        ANÁLISIS: [tu explicación aquí]
        """
        
        response = openai.ChatCompletion.create(
            engine=openai_config['engine'],
            messages=[
                {"role": "system", "content": "Eres un experto en tecnología que explica conceptos de forma clara y precisa."},
                {"role": "user", "content": prompt}
            ],
            temperature=openai_config['temperature'],
            max_tokens=openai_config['max_tokens']
        )
        
        try:
            analysis = response.choices[0].message.content.split("ANÁLISIS:")[1].strip()
        except (IndexError, AttributeError):
            print(f"❌ Error: Respuesta de OpenAI en formato incorrecto para idea: {idea_text[:50]}...")
            analysis = "No se pudo generar el análisis."
        
        return {
            'cluster': cluster,
            'idea': idea_text,
            'analysis': analysis
        }
    except Exception as e:
        print(f"❌ Error enriqueciendo idea: {str(e)}")
        return None

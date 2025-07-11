from fpdf import FPDF
import os
from datetime import datetime
import re
import unicodedata

def normalize_text(text):
    """
    Normaliza el texto para asegurar compatibilidad con la fuente.
    """
    if not text:
        return ""
        
    # Diccionario de reemplazos para caracteres especiales
    replacements = {
        # Comillas y guiones
        '"': '"',  # Comillas dobles
        "'": "'",  # Comillas simples
        "—": "-",  # Guión largo
        "–": "-",  # Guión medio
        "…": "...",  # Puntos suspensivos
        # Caracteres especiales
        "¿": "?",
        "¡": "!",
        "«": '"',
        "»": '"',
        "‹": "'",
        "›": "'",
        # Símbolos matemáticos
        "×": "x",
        "÷": "/",
        "±": "+/-",
        "≠": "!=",
        "≤": "<=",
        "≥": ">=",
        # Símbolos de moneda
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "¢": "c",
        # Caracteres con acentos
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "ñ": "n",
        "Ñ": "N",
        "ü": "u",
        "Ü": "U"
    }
    
    # Aplicar reemplazos
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Eliminar cualquier otro carácter especial
    text = ''.join(c for c in text if ord(c) < 128)
    
    return text

def extract_title(text):
    """
    Extrae el título de la idea del texto completo.
    """
    lines = text.split('\n')
    for line in lines:
        if line.strip().startswith('Titulo:'):
            return line.replace('Titulo:', '').strip()
    return text.split('\n')[0].strip()

def clean_analysis_text(text):
    """
    Limpia el texto del análisis para presentación en PDF.
    """
    if not text:
        return ""
        
    # Dividir el texto en líneas
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Si la línea comienza con un número y dos puntos, es un título
        if re.match(r'^\d+\.', line):
            # Extraer el número y el texto
            match = re.match(r'^(\d+)\.\s*(.*)', line)
            if match:
                number, content = match.groups()
                # Formatear como título
                cleaned_lines.append(f"{number}. {content.strip()}")
        else:
            # Si es texto normal, mantenerlo
            cleaned_lines.append(line)
    
    # Unir las líneas con saltos de línea dobles
    return '\n\n'.join(cleaned_lines)

def generate_analysis_pdf(ideas):
    """
    Genera un PDF profesional con el análisis de las ideas.
    """
    try:
        # Validar entrada
        if not ideas:
            print("Error: No hay ideas para generar el PDF")
            return None
            
        # Crear el PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Configurar la fuente
        pdf.add_font('Arial', '', 'arial.ttf', uni=True)
        pdf.add_font('Arial', 'B', 'arialbd.ttf', uni=True)
        pdf.set_font('Arial', '', 12)
        
        # Primera página (portada)
        pdf.add_page()
        pdf.set_font('Arial', 'B', 24)
        pdf.cell(0, 40, "Informe de Análisis de Innovación", ln=True, align='C')
        pdf.ln(20)
        
        pdf.set_font('Arial', '', 16)
        pdf.cell(0, 10, "Generado por: AI Agent Innovacion Sener", ln=True, align='C')
        pdf.cell(0, 10, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='C')
        
        # Página de índice
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, "Índice", ln=True)
        pdf.ln(10)
        
        pdf.set_font('Arial', '', 12)
        for i, idea in enumerate(ideas, 1):
            pdf.cell(0, 10, f"{i}. {normalize_text(idea['idea'])}", ln=True)
        
        # Páginas de análisis
        for i, idea in enumerate(ideas, 1):
            pdf.add_page()
            
            # Título de la idea
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, f"Idea {i}: {normalize_text(idea['idea'])}", ln=True)
            pdf.ln(10)
            
            # Análisis
            pdf.set_font('Arial', '', 12)
            for analysis in idea.get('analysis', []):
                # Dividir el análisis en líneas
                lines = analysis.split('\n')
                for line in lines:
                    pdf.multi_cell(0, 10, normalize_text(line))
                pdf.ln(5)
        
        # Guardar el PDF
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"analisis_innovacion_{timestamp}.pdf")
        pdf.output(pdf_path)
        
        return pdf_path
        
    except Exception as e:
        print(f"Error al generar el PDF: {str(e)}")
        return None
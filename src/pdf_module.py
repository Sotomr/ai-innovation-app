from fpdf import FPDF
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
import tempfile
import re
import unicodedata

def clean_text_for_pdf(text):
    """
    Limpia el texto para que sea compatible con FPDF
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        '—': '-', '–': '-', '…': '...', '"': '"', '≤': '<=', '≥': '>=', '×': 'x', '÷': '/', '≠': '!=', '≈': '~=',
        '°': ' grados', '©': '(c)', '®': '(R)', '™': '(TM)', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '§': 'Seccion',
        '•': '-', '·': '-', '►': '->', '◄': '<-', '▼': 'v', '▲': '^', '■': '[*]', '□': '[ ]', '★': '*', '☆': '*',
        '✓': 'v', '✔': 'v', '✗': 'x', '✘': 'x',
        '\u2022': '-', '\u2023': '-', '\u2043': '-', '\u204C': '-', '\u204D': '-', '\u2219': '-',
        '\u25CF': '*', '\u25CB': 'o', '\u25D8': '*', '\u25E6': 'o',
        '\u2780': '(1)', '\u2781': '(2)', '\u2782': '(3)', '\u2783': '(4)', '\u2784': '(5)'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    normalized_text = unicodedata.normalize('NFKD', text)
    final_text = ""
    for char in normalized_text:
        if ord(char) < 128:
            final_text += char
        elif char in 'áéíóúÁÉÍÓÚñÑüÜ':
            final_text += char
        else:
            final_text += ' '
    return final_text

def create_temp_image(fig):
    """
    Guarda una figura de matplotlib como archivo temporal y devuelve la ruta
    """
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        temp_path = tmp.name
    fig.savefig(temp_path, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    return temp_path

class SenerPDF(FPDF):
    """
    Clase base para todos los documentos PDF de Sener con diseño consistente
    """
    def __init__(self, title="Informe Sener", orientation='P', unit='mm', format='A4'):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.title = title
        # Configurar opciones generales
        self.set_auto_page_break(auto=True, margin=15)
        # Añadir fuentes
        self.set_font("Helvetica", "", 12)
        # Definir colores corporativos
        self.primary_color = (44, 62, 80)  # Azul oscuro
        self.secondary_color = (52, 152, 219)  # Azul claro
        self.accent_color = (211, 84, 0)  # Naranja
        self.light_bg = (245, 245, 245)  # Gris claro para fondos

    def header(self):
        # Logo (solo a partir de la página 2)
        if self.page_no() > 1:
            try:
                logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
                for logo_path in logo_paths:
                    if os.path.exists(logo_path):
                        self.image(logo_path, 10, 8, 33)
                        break
            except Exception:
                pass
                
            # Título del documento en cada página (excepto portada)
            self.set_font('Helvetica', 'B', 12)
            self.set_text_color(*self.primary_color)
            self.cell(0, 10, self.title, 0, 1, 'C')
            self.ln(5)
    
    def footer(self):
        # Posicionar a 1.5 cm del final
        self.set_y(-15)
        # Fuente y color de texto del pie
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        # Fecha a la izquierda
        self.cell(50, 10, datetime.now().strftime("%d/%m/%Y"), 0, 0, 'L')
        # Número de página centrado
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
        
    def add_cover_page(self, subtitle=None, image_path=None):
        """
        Añade una página de portada al documento
        """
        self.add_page()
        
        # Añadir imagen de fondo si se proporciona
        if image_path and os.path.exists(image_path):
            self.image(image_path, 0, 0, 210, 297)
        
        # Franja superior de color
        self.set_fill_color(*self.primary_color)
        self.rect(0, 0, 210, 40, style="F")
        
        # Logo en la parte superior
        try:
            logo_paths = ["logo.png", "static/logo.png", "assets/logo.png", "../static/logo.png"]
            for logo_path in logo_paths:
                if os.path.exists(logo_path):
                    self.image(logo_path, 10, 10, 40)
                    break
        except Exception:
            pass
        
        # Título principal
        self.ln(60)
        self.set_font('Helvetica', 'B', 24)
        self.set_text_color(*self.primary_color)
        self.cell(0, 20, self.title, ln=True, align='C')
        
        # Subtítulo si se proporciona
        if subtitle:
            self.ln(10)
            self.set_font('Helvetica', '', 16)
            self.set_text_color(*self.secondary_color)
            self.cell(0, 10, subtitle, ln=True, align='C')
        
        # Fecha en la parte inferior
        self.set_y(-50)
        self.set_font('Helvetica', '', 14)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Generado el {datetime.now().strftime('%d de %B de %Y')}", ln=True, align='C')
        self.cell(0, 10, "Sener - Innovación Tecnológica", ln=True, align='C')
    
    def add_section_title(self, title, with_line=True):
        """
        Añade un título de sección con formato consistente
        """
        self.ln(5)
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(*self.primary_color)
        self.cell(0, 10, title, ln=True)
        
        if with_line:
            # Línea horizontal bajo el título
            current_x, current_y = self.get_x(), self.get_y()
            self.set_draw_color(*self.secondary_color)
            self.set_line_width(0.5)
            self.line(current_x, current_y-2, current_x+180, current_y-2)
            self.ln(5)
    
    def add_subsection_title(self, title):
        """
        Añade un subtítulo con formato consistente
        """
        self.ln(3)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(*self.secondary_color)
        self.cell(0, 8, title, ln=True)
    
    def add_paragraph(self, text, font_size=11):
        """
        Añade un párrafo de texto con formato consistente
        """
        self.set_font('Helvetica', '', font_size)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, clean_text_for_pdf(text))
        self.ln(3)
    
    def add_table_header(self, headers, col_widths=None):
        """
        Añade una fila de encabezado a una tabla
        """
        if col_widths is None:
            col_widths = [self.w / len(headers)] * len(headers)
        self.set_font('Helvetica', 'B', 11)
        self.set_fill_color(*self.primary_color)
        self.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 8, header, 1, 0, 'C', True)
        self.ln()
    
    def add_table_row(self, data, col_widths=None, highlight=False):
        """
        Añade una fila a una tabla
        """
        if col_widths is None:
            col_widths = [self.w / len(data)] * len(data)
        if highlight:
            self.set_fill_color(*self.light_bg)
            fill = True
        else:
            fill = False
        self.set_font('Helvetica', '', 10)
        self.set_text_color(0, 0, 0)
        for i, value in enumerate(data):
            align = 'C' if i == len(data) - 1 else 'L'
            self.cell(col_widths[i], 7, str(value), 1, 0, align, fill)
        self.ln()

def generate_payoff_matrix_chart(data, title="Matriz de Payoff"):
    """
    Genera un gráfico de matriz de payoff con los datos proporcionados
    
    Args:
        data: Lista de diccionarios con keys 'Proyecto', 'X' e 'Y'
        title: Título del gráfico
        
    Returns:
        Objeto figure de matplotlib
    """
    # Configurar estilo
    sns.set_style("whitegrid")
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    
    # Configurar límites
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    
    # Añadir cuadrantes coloreados
    rect_q1 = plt.Rectangle((0, 5), 5, 5, color='#b3ffb3', alpha=0.3)  # Verde claro
    rect_q2 = plt.Rectangle((5, 5), 5, 5, color='#ffcccc', alpha=0.3)  # Rojo claro
    rect_q3 = plt.Rectangle((0, 0), 5, 5, color='#cce0ff', alpha=0.3)  # Azul claro
    rect_q4 = plt.Rectangle((5, 0), 5, 5, color='#ffffcc', alpha=0.3)  # Amarillo claro
    
    # Añadir los rectángulos
    for rect in [rect_q1, rect_q2, rect_q3, rect_q4]:
        ax.add_patch(rect)
    
    # Líneas divisorias
    ax.axvline(5, color='black', linestyle='--', linewidth=1)
    ax.axhline(5, color='black', linestyle='--', linewidth=1)
    
    # Etiquetas de cuadrantes
    ax.text(2.5, 7.5, "Quick Win!", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(7.5, 7.5, "Do we have\ntime & money?", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(2.5, 2.5, "Improvements", ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(7.5, 2.5, "Kill it!", ha='center', va='center', fontsize=14, fontweight='bold')
    
    # Etiquetas de ejes
    ax.set_xlabel("Effort (Low → High)", fontsize=12)
    ax.set_ylabel("Benefit (Low → High)", fontsize=12)
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    
    # Plotear puntos y etiquetas
    for item in data:
        x = item.get('X', 0)
        y = item.get('Y', 0)
        label = item.get('Proyecto', '')
        
        # Dibujar punto
        ax.scatter(x, y, color='blue', s=60, edgecolors='black', linewidth=0.5)
        
        # Añadir etiqueta
        ax.annotate(label, (x, y), textcoords="offset points", xytext=(5, 5),
                   ha='left', fontsize=10, color='blue')
    
    # Ajustar diseño
    plt.tight_layout()
    
    return fig

def generate_analysis_pdf(title, content, subtitle=None, output_name="analisis"):
    """
    Genera un PDF con diseño profesional para informes de análisis
    
    Args:
        title: Título principal del documento
        content: Contenido principal del análisis como texto
        subtitle: Subtítulo opcional
        output_name: Nombre base para el archivo de salida
        
    Returns:
        Ruta al archivo PDF generado
    """
    # Crear documento PDF
    pdf = SenerPDF(title=title)
    
    # Añadir portada
    pdf.add_cover_page(subtitle=subtitle)
    
    # Añadir contenido principal
    pdf.add_page()
    pdf.add_section_title("Análisis detallado")
    pdf.add_paragraph(content)
    
    # Guardar PDF
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(output_dir, f"{output_name}_{timestamp}.pdf")
    pdf.output(pdf_path)
    
    return pdf_path 
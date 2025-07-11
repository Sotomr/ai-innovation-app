"""
Módulo para generar la matriz de payoff (esfuerzo vs beneficio) de ideas rankeadas.
Este módulo crea visualizaciones atractivas y profesionales para ayudar en la toma de decisiones.
"""

import os
import io
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib as mpl
import numpy as np
from PIL import Image
import base64

# Colores para la matriz
COLORS = {
    'quick_win': '#b3ffb3',     # Verde claro
    'strategic': '#ffcccc',     # Rojo claro
    'improvements': '#cce0ff',  # Azul claro
    'kill': '#ffffcc',          # Amarillo claro
    'background': '#f5f5f5',    # Gris muy claro
    'border': '#444444',        # Gris oscuro
    'line': '#555555',          # Gris para líneas
    'title': '#333333',         # Casi negro para títulos
    'number': '#1f77b4',        # Azul para números de ideas
    'dot': '#3366cc',           # Azul para puntos
    'dot_border': '#000000'     # Negro para borde de puntos
}

def generate_payoff_matrix(ranked_ideas, width=10, height=10, dpi=300):
    """
    Genera una matriz de payoff visual para las ideas rankeadas.
    
    Args:
        ranked_ideas: Lista de ideas rankeadas con valores de esfuerzo y beneficio
        width: Ancho de la figura en pulgadas
        height: Alto de la figura en pulgadas
        dpi: Resolución de la imagen
        
    Returns:
        Base64 string de la imagen generada
    """
    # Configurar matplotlib para mejor calidad
    mpl.rcParams['figure.dpi'] = dpi
    mpl.rcParams['font.family'] = 'sans-serif'
    mpl.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'sans-serif']
    mpl.rcParams['axes.labelsize'] = 14
    mpl.rcParams['axes.titlesize'] = 16
    mpl.rcParams['axes.titleweight'] = 'bold'
    mpl.rcParams['xtick.labelsize'] = 12
    mpl.rcParams['ytick.labelsize'] = 12
    
    # Crear figura
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    # Configurar límites de ejes (invertir eje X para que 0 esté a la derecha)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    
    # Dibujar cuadrantes
    # Cuadrante 1: Alto beneficio, bajo esfuerzo = Quick Win
    rect_q1 = patches.Rectangle((0, 50), 50, 50, facecolor=COLORS['quick_win'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    # Cuadrante 2: Alto beneficio, alto esfuerzo = Strategic
    rect_q2 = patches.Rectangle((50, 50), 50, 50, facecolor=COLORS['strategic'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    # Cuadrante 3: Bajo beneficio, bajo esfuerzo = Improvements
    rect_q3 = patches.Rectangle((0, 0), 50, 50, facecolor=COLORS['improvements'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    # Cuadrante 4: Bajo beneficio, alto esfuerzo = Kill it
    rect_q4 = patches.Rectangle((50, 0), 50, 50, facecolor=COLORS['kill'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    
    # Añadir cuadrantes al gráfico
    ax.add_patch(rect_q1)
    ax.add_patch(rect_q2)
    ax.add_patch(rect_q3)
    ax.add_patch(rect_q4)
    
    # Añadir líneas divisorias
    ax.axvline(50, color=COLORS['line'], linestyle='--', linewidth=1.5)
    ax.axhline(50, color=COLORS['line'], linestyle='--', linewidth=1.5)
    
    # Añadir etiquetas de cuadrantes
    ax.text(25, 75, "Quick Win!", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    ax.text(75, 75, "Do we have the\ntime and money?", ha='center', va='center', 
            fontsize=16, fontweight='bold', color=COLORS['title'])
    ax.text(25, 25, "Improvements", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    ax.text(75, 25, "Kill it!", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    
    # Etiquetas de ejes
    ax.set_xlabel("Effort (Resources: Time, Money, People)", fontsize=14, fontweight='bold')
    ax.set_ylabel("Benefit (Increased revenue, decreased costs)", fontsize=14, fontweight='bold')
    
    # Título
    ax.set_title("Payoff Matrix", fontsize=18, fontweight='bold', pad=20)
    
    # Añadir puntos para cada idea
    for i, idea in enumerate(ranked_ideas, 1):
        if not isinstance(idea, dict):
            continue
            
        # Extraer valores de esfuerzo y beneficio, normalizados a 0-100
        effort = min(100, max(0, idea.get('effort', 50)))
        benefit = min(100, max(0, idea.get('benefit', 50)))
        
        # Dibujar punto
        ax.scatter(effort, benefit, s=120, color=COLORS['dot'], 
                  edgecolors=COLORS['dot_border'], linewidth=1, zorder=10)
        
        # Añadir número de la idea
        ax.text(effort, benefit, str(i), ha='center', va='center', 
                color='white', fontweight='bold', fontsize=10, zorder=11)
    
    # Leyenda
    ax.text(5, 95, "Low Effort", fontsize=12, ha='left', va='center')
    ax.text(95, 95, "High Effort", fontsize=12, ha='right', va='center')
    ax.text(5, 5, "Low Benefit", fontsize=12, ha='left', va='center')
    ax.text(5, 95, "High Benefit", fontsize=12, ha='left', va='center')
    
    # Mejorar la presentación general
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['left'].set_linewidth(1.5)
    
    # Establecer ticks en los ejes
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(['0', '25', '50', '75', '100'])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(['0', '25', '50', '75', '100'])
    
    # Añadir cuadrícula
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.5)
    
    # Ajustar espaciado
    plt.tight_layout()
    
    # Convertir figura a base64 para mostrar en interfaz web
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=dpi)
    buffer.seek(0)
    
    # Crear una imagen base64
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # Cerrar figura para liberar memoria
    plt.close(fig)
    
    return img_str

def save_payoff_matrix_to_file(ranked_ideas, output_path=None, width=10, height=10, dpi=300):
    """
    Genera y guarda la matriz de payoff en un archivo.
    
    Args:
        ranked_ideas: Lista de ideas rankeadas
        output_path: Ruta donde guardar la imagen (optional)
        width, height, dpi: Parámetros para la imagen
        
    Returns:
        Ruta del archivo guardado
    """
    # Crear directorio output si no existe
    if not output_path:
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_path = os.path.join(output_dir, "payoff_matrix.png")
    
    # Configurar matplotlib
    mpl.rcParams['figure.dpi'] = dpi
    mpl.rcParams['font.family'] = 'sans-serif'
    mpl.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'sans-serif']
    
    # Crear figura
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    # Configurar límites de ejes
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    
    # Dibujar cuadrantes
    rect_q1 = patches.Rectangle((0, 50), 50, 50, facecolor=COLORS['quick_win'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    rect_q2 = patches.Rectangle((50, 50), 50, 50, facecolor=COLORS['strategic'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    rect_q3 = patches.Rectangle((0, 0), 50, 50, facecolor=COLORS['improvements'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    rect_q4 = patches.Rectangle((50, 0), 50, 50, facecolor=COLORS['kill'], 
                               alpha=0.6, edgecolor=COLORS['border'], linewidth=0.5)
    
    ax.add_patch(rect_q1)
    ax.add_patch(rect_q2)
    ax.add_patch(rect_q3)
    ax.add_patch(rect_q4)
    
    # Añadir líneas divisorias
    ax.axvline(50, color=COLORS['line'], linestyle='--', linewidth=1.5)
    ax.axhline(50, color=COLORS['line'], linestyle='--', linewidth=1.5)
    
    # Añadir etiquetas de cuadrantes
    ax.text(25, 75, "Quick Win!", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    ax.text(75, 75, "Do we have the\ntime and money?", ha='center', va='center', 
            fontsize=16, fontweight='bold', color=COLORS['title'])
    ax.text(25, 25, "Improvements", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    ax.text(75, 25, "Kill it!", ha='center', va='center', fontsize=16, 
            fontweight='bold', color=COLORS['title'])
    
    # Etiquetas de ejes
    ax.set_xlabel("Effort (Resources: Time, Money, People)", fontsize=14, fontweight='bold')
    ax.set_ylabel("Benefit (Increased revenue, decreased costs)", fontsize=14, fontweight='bold')
    
    # Título
    ax.set_title("Payoff Matrix", fontsize=18, fontweight='bold', pad=20)
    
    # Añadir puntos para cada idea
    for i, idea in enumerate(ranked_ideas, 1):
        if not isinstance(idea, dict):
            continue
            
        effort = min(100, max(0, idea.get('effort', 50)))
        benefit = min(100, max(0, idea.get('benefit', 50)))
        
        # Dibujar punto
        ax.scatter(effort, benefit, s=120, color=COLORS['dot'], 
                  edgecolors=COLORS['dot_border'], linewidth=1, zorder=10)
        ax.text(effort, benefit, str(i), ha='center', va='center', 
                color='white', fontweight='bold', fontsize=10, zorder=11)
    
    # Mejorar apariencia
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['left'].set_linewidth(1.5)
    
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(['0', '25', '50', '75', '100'])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(['0', '25', '50', '75', '100'])
    
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.5)
    
    plt.tight_layout()
    
    # Guardar imagen
    plt.savefig(output_path, format='png', bbox_inches='tight', dpi=dpi)
    plt.close(fig)
    
    return output_path

def add_payoff_matrix_to_pdf(pdf, ranked_ideas, y_position=None):
    """
    Añade la matriz de payoff a un PDF existente.
    
    Args:
        pdf: objeto FPDF
        ranked_ideas: lista de ideas rankeadas
        y_position: posición Y donde insertar la matriz (optional)
        
    Returns:
        y_position actualizada después de insertar la matriz
    """
    # Generar matriz de payoff
    matrix_path = save_payoff_matrix_to_file(ranked_ideas)
    
    # Si no se especifica posición, usar la actual
    if y_position is None:
        y_position = pdf.get_y()
    
    # Verificar si hay suficiente espacio en la página actual
    if y_position + 120 > pdf.h - 20:  # 120 es una altura estimada para la matriz
        pdf.add_page()
        y_position = pdf.get_y()
    
    # Añadir título
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(44, 62, 80)  # Azul oscuro
    pdf.set_y(y_position)
    pdf.cell(0, 10, "Matriz de Payoff - Esfuerzo vs Beneficio", 0, 1, 'C')
    y_position = pdf.get_y() + 5
    
    # Añadir leyenda explicativa
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 5, "La matriz muestra la relación entre el esfuerzo requerido y el beneficio potencial de cada idea. Las ideas están numeradas según su posición en el ranking.", 0, 'C')
    y_position = pdf.get_y() + 5
    
    # Calcular ancho para mantener proporciones
    available_width = pdf.w - 20  # Margen de 10mm en cada lado
    image_width = min(160, available_width)
    
    # Añadir imagen centrada
    x_pos = (pdf.w - image_width) / 2
    pdf.image(matrix_path, x=x_pos, y=y_position, w=image_width)
    
    # Actualizar posición vertical (imagen + espacio adicional)
    return y_position + image_width + 10 
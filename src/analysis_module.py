import re
from typing import List, Dict, Tuple, Optional
from pdf_generator import generate_analysis_pdf

class AnalysisManager:
    def __init__(self):
        self.analyzed_ideas = []
        self.analysis_points = None
    
    def validate_analysis_format(self, text: str) -> Tuple[str, bool]:
        """Valida el formato del texto de análisis"""
        if not text or not isinstance(text, str):
            return "❌ Error: El texto está vacío.", False
        
        # Verificar la frase introductoria
        if "analiza esta idea considerando los siguientes aspectos:" not in text.lower():
            return "❌ Error: Falta la frase introductoria correcta.", False
        
        # Buscar puntos numerados
        lines = text.split('\n')
        points_found = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Buscar puntos numerados con título y descripción
            match = re.match(r'^(\d+)\.\s*([^:]+):\s*(.+)$', line)
            if match:
                number = int(match.group(1))
                title = match.group(2).strip()
                description = match.group(3).strip()
                points_found.append((number, title, description))
        
        if not points_found:
            return "❌ Error: No se encontraron puntos de análisis válidos.", False
        
        # Verificar números consecutivos
        numbers = [p[0] for p in points_found]
        if numbers != list(range(1, len(points_found) + 1)):
            return "❌ Error: Los números de los puntos deben ser consecutivos.", False
        
        # Almacenar los puntos validados
        self.analysis_points = text
        return f"✅ Formato válido: {len(points_found)} puntos detectados", True
    
    def set_ideas_to_analyze(self, ideas: List[Dict]) -> bool:
        """Establece las ideas que serán analizadas"""
        if not ideas:
            return False
        self.analyzed_ideas = ideas
        return True
    
    def perform_analysis(self) -> Tuple[str, Optional[str], str]:
        """Realiza el análisis de las ideas usando los puntos validados"""
        try:
            if not self.analyzed_ideas:
                return "❌ Error: No hay ideas para analizar.", None, "0"
            
            if not self.analysis_points:
                return "❌ Error: No hay puntos de análisis validados.", None, "0"
            
            # Extraer los puntos de análisis
            points = []
            lines = self.analysis_points.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'^(\d+)\.\s*([^:]+):\s*(.+)$', line)
                if match:
                    number = int(match.group(1))
                    title = match.group(2).strip()
                    description = match.group(3).strip()
                    points.append((number, title, description))
            
            if not points:
                return "❌ Error: No se encontraron puntos de análisis válidos.", None, "0"
            
            # Analizar cada idea
            results = []
            for idea in self.analyzed_ideas:
                idea_analysis = {
                    'text': idea.get('idea', '') if isinstance(idea, dict) else str(idea),
                    'analysis': {}
                }
                
                for _, title, description in points:
                    # Aquí iría la lógica de análisis real usando OpenAI
                    # Por ahora usamos un placeholder
                    idea_analysis['analysis'][title] = f"Análisis de {title} para la idea"
                
                results.append(idea_analysis)
            
            # Generar PDF
            pdf_path = generate_analysis_pdf(results)
            if not pdf_path:
                return "❌ Error: No se pudo generar el PDF.", None, "0"
            
            return f"✅ Análisis completado: {len(results)} ideas analizadas", pdf_path, str(len(results))
            
        except Exception as e:
            return f"❌ Error en el análisis: {str(e)}", None, "0"
    
    def clear_analysis(self):
        """Limpia el estado del análisis"""
        self.analysis_points = None
        return "Estado: El formato ha cambiado. Por favor, valida nuevamente.", False

# Instancia global del gestor de análisis
analysis_manager = AnalysisManager() 
import requests
from bs4 import BeautifulSoup

def scrape_targets(scraping_requests: list[dict]) -> list[dict]:
    """
    scraping_requests: [{'url': str, 'campos': [str] o [{'campo': str, 'regex': str}]}]
    Devuelve: [{'url': ..., 'datos': {'campo1': val1, 'campo2': val2}, 'ok': bool}]
    """
    results = []
    for req in scraping_requests:
        url = req.get("url")
        campos = req.get("campos", [])
        datos = {}
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            for campo in campos:
                # Permitir dicts con regex custom
                if isinstance(campo, dict):
                    nombre = campo.get('campo')
                    regex = campo.get('regex')
                else:
                    nombre = campo
                    regex = None
                match = search_value_in_text(text, nombre, regex)
                if match:
                    datos[nombre] = match
        except Exception as e:
            datos["error"] = str(e)
        results.append({
            "url": url,
            "datos": datos,
            "ok": bool(datos) and "error" not in datos
        })
    return results

def search_value_in_text(text: str, campo: str, regex: str = None) -> str:
    """
    Búsqueda flexible de un campo en texto largo.
    Si se pasa regex custom, la usa. Si no, usa patrones predefinidos.
    """
    import re
    patterns = {
        "año fundación": r"(fundad[ao]\s+en\s+)?(\d{4})",
        "precio": r"(\$\s?\d+[kKmM]?)",
        "empresa": r"(empresa\s[\w\s]+)",
        "web": r"https?://[\w\.-]+",
        "email": r"[\w\.-]+@[\w\.-]+",
        "teléfono": r"\+?\d[\d\s\-]{7,}\d",
        # Añade aquí más patrones según necesidades
    }
    pattern = regex or patterns.get(campo.lower())
    if not pattern:
        return ""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else "" 
import re, json, os
from openai_config import get_openai_client, get_deployment_name
import spacy
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from collections import OrderedDict

client        = get_openai_client()
DEPLOYMENT    = get_deployment_name()
nlp           = spacy.load("es_core_news_sm")   # 14 MB, suficiente

# --- 1.1  mapa rápido de dominios problemáticos ----------
DOMAIN_OVERRIDES = {
    "antifouling": ["antifouling", "biofouling", "hull cleaning",
                    "ultrasonic antifouling", "barnacle prevention",
                    "marine growth control"],
    # añade más dominios si los necesitas
}

MEDICAL_TERMS = re.compile(r"\b(médic|diagnóstic|ecograf|embaraz|feto|vascular)\b", re.I)

def _extract_keyphrases(text, top_k=6):
    """keyphrases rápidas usando POS pattern + frecuencia"""
    doc = nlp(text.lower())
    cands = [tok.lemma_ for tok in doc
             if tok.pos_ in ("NOUN", "PROPN", "ADJ") and len(tok) > 3]
    freq  = {}
    for w in cands:
        freq[w] = freq.get(w, 0) + 1
    return [w for w,_ in sorted(freq.items(), key=lambda x: -x[1])[:top_k]]

def _ask_llm_for_queries(text, seed_kw):
    prompt = f"""
Eres un analista competitivo.  
*Idea*: «{text}»  
*Palabras clave semilla*: {', '.join(seed_kw)}  

Devuélveme JSON con EXACTAMENTE 8 consultas de búsqueda
cortas (máx 8-10 palabras), variando entre inglés y español,
sin términos médicos a menos que la idea sea del sector salud.
Ejemplo de formato:

{{
  "queries": [
    "ultrasonic antifouling system",
    "biofouling barnacle prevention hull",
    ...
  ]
}}
"""
    rsp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[{"role": "system",
                   "content": "Responde solo con el JSON pedido."},
                  {"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200
    )
    try:
        data = json.loads(rsp.choices[0].message.content.strip())
        return data.get("queries", [])
    except Exception:
        return []

def generate_queries(idea_text, k=6):
    """
    Genera hasta k queries cortas y multi-idioma para búsqueda competitiva. Incluye al menos una con filetype:pdf.
    """
    # Heurística simple: extraer palabras clave largas
    words = [w for w in re.findall(r'\w+', idea_text.lower()) if len(w) > 4]
    uniq = list(OrderedDict.fromkeys(words))
    queries = []
    if uniq:
        queries.append(" ".join(uniq[:2]))
        queries.append(f"{uniq[0]} filetype:pdf")
    # Añadir traducciones básicas
    if 'market' not in uniq:
        queries.append("market filetype:pdf")
    if 'competitors' not in uniq:
        queries.append("competitors")
    if 'benchmarking' not in uniq:
        queries.append("benchmarking filetype:pdf")
    # Limitar a k
    return queries[:k]

def generate_queries_old(idea_text: str) -> list[str]:
    """API principal que usarán el resto de módulos"""
    idea_low = idea_text.lower()

    # 1️⃣ Dominio forzado si encontramos keyword explícita
    for dom_kw, dom_queries in DOMAIN_OVERRIDES.items():
        if dom_kw in idea_low:
            return dom_queries

    # 2️⃣ Extracción de keyphrases locales
    keys = _extract_keyphrases(idea_text)

    # 3️⃣ Pedirle al LLM
    llm_queries = _ask_llm_for_queries(idea_text, keys)

    # 4️⃣ Post-filter anti-médico
    llm_queries = [q for q in llm_queries if not MEDICAL_TERMS.search(q)]

    # 5️⃣ Si todo falla, fallback seguro
    if not llm_queries:
        llm_queries = [f"{' '.join(keys[:2])} technology",
                       f"{' '.join(keys[:2])} industry trend"]
    return llm_queries 
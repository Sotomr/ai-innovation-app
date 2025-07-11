from openai_config import get_openai_client, get_deployment_name

def get_llm_keywords(text, k=3, lang='es'):
    client = get_openai_client()
    DEPLOYMENT_NAME = get_deployment_name()
    if lang == 'en':
        prompt = f"Return {k} keywords in English, separated by commas, no phrases: '{text[:120]}'"
    else:
        prompt = f"Devuelve {k} palabras clave, separadas por comas, sin frases: «{text[:120]}»"
    rsp = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": "Eres un experto en síntesis de información."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=20
    )
    kws = [w.strip() for w in rsp.choices[0].message.content.split(",") if w.strip()]
    return " ".join(kws[:k]) 
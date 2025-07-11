import os
import json
from openai_config import get_openai_client, get_deployment_name

client = get_openai_client()
DEPLOYMENT_NAME = get_deployment_name()

def build_report(prompt_blob: str, idea: str) -> dict:
    """
    prompt_blob = texto concatenado de todo lo scrap-eado.
    Devuelve un dict con claves:
      {seccion: {"texto": "...", "fuente":"web"|"llm"} }
    """
    system = (
        "Eres consultor senior. Redacta un informe profesional de la idea "
        "usando la información proporcionada. Señala en cada párrafo si "
        "la información proviene de la web (‘[WEB]’) o es inferencia tuya "
        "sin cita (‘[LLM]’). Devuelve un objeto JSON con las secciones "
        "Resumen, Mercado, Benchmarking, DAFO, Recomendaciones."
    )
    user = f"IDEA:\n{idea}\n\nDATOS WEB (puedes citar literal):\n{prompt_blob[:12000]}"
    resp = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=4096,
        response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content) 
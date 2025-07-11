def merge_llm_and_data(borrador: dict, datos_scrapeados: list[dict]) -> dict:
    from openai_config import get_openai_client, get_deployment_name
    import json

    prompt = (
        "Aquí tienes un informe preliminar (borrador) y una lista de datos extraídos de páginas web. "
        "Revisa el informe, completa los huecos, y añade los datos donde correspondan. "
        "Incluye citas o referencias cuando uses los datos externos. "
        "Devuelve SOLO un objeto JSON con la estructura final del informe, sin texto fuera del JSON.\n\n"
        "BORRADOR:\n" + json.dumps(borrador, ensure_ascii=False) +
        "\n\nDATOS SCRAPEADOS:\n" + json.dumps(datos_scrapeados, ensure_ascii=False)
    )

    client = get_openai_client()
    deployment = get_deployment_name()
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "Eres un analista que mejora un informe integrando datos externos."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=16000,
        response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content) 
import boto3, json, time, sys
s=boto3.Session(profile_name='nexus'); c=s.client('bedrock-runtime',region_name='eu-west-1')

SYSTEM = """Eres el asistente de WhatsApp de "Clínica Boreal", un centro de medicina estética en Caracas.
Reglas estrictas:
- Responde SIEMPRE en español neutro, tuteando, máximo 3 frases, sin emojis.
- NUNCA inventes precios, disponibilidad ni datos clínicos. Si el dato lo da una herramienta, llama a la herramienta ANTES de responder.
- No des consejo médico. Si preguntan por contraindicaciones, deriva a consulta con el especialista.
- Si el cliente pide cita, necesitas: servicio, fecha y hora. Si falta algo, pregunta solo por lo que falta.
"""
TOOLS = {"tools":[
 {"toolSpec":{"name":"consultar_disponibilidad","description":"Consulta huecos libres de la agenda para un servicio y una fecha.",
  "inputSchema":{"json":{"type":"object","properties":{
    "servicio":{"type":"string","description":"Nombre del servicio, p.ej. 'botox', 'limpieza facial'"},
    "fecha":{"type":"string","description":"Fecha en formato YYYY-MM-DD"}},"required":["servicio","fecha"]}}}},
 {"toolSpec":{"name":"consultar_precio","description":"Precio vigente de un servicio del catálogo.",
  "inputSchema":{"json":{"type":"object","properties":{
    "servicio":{"type":"string"}},"required":["servicio"]}}}},
 {"toolSpec":{"name":"crear_cita","description":"Reserva una cita ya confirmada por el cliente.",
  "inputSchema":{"json":{"type":"object","properties":{
    "servicio":{"type":"string"},"fecha":{"type":"string"},"hora":{"type":"string"},
    "nombre_cliente":{"type":"string"}},"required":["servicio","fecha","hora","nombre_cliente"]}}}}]}

CASES = [
 ("A. tool simple + fecha relativa", "Hola, quiero saber si tienen hueco para botox el jueves que viene"),
 ("B. dos tools en un turno", "¿Cuánto cuesta la limpieza facial y qué horas tienen libres el 2026-09-03?"),
 ("C. NO debe llamar tool (fuera de alcance)", "¿El botox es peligroso si tengo la tensión alta?"),
 ("D. falta info, debe preguntar", "Quiero reservar"),
]
MODELS=["openai.gpt-oss-120b-1:0","qwen.qwen3-32b-v1:0","zai.glm-4.7-flash","minimax.minimax-m2.5","nvidia.nemotron-super-3-120b"]
today="Hoy es martes 2026-08-25."
for mid in MODELS:
    print(f"\n{'='*78}\nMODELO: {mid}")
    for name,msg in CASES:
        try:
            t0=time.time()
            r=c.converse(modelId=mid,
                system=[{"text":SYSTEM+"\n"+today}],
                messages=[{"role":"user","content":[{"text":msg}]}],
                toolConfig=TOOLS,
                inferenceConfig={"maxTokens":400,"temperature":0.2})
            ms=int((time.time()-t0)*1000)
            out=r["output"]["message"]["content"]; u=r["usage"]
            calls=[b["toolUse"] for b in out if "toolUse" in b]
            text=" ".join(b["text"] for b in out if "text" in b).strip()
            print(f"  [{name}] {ms}ms in={u['inputTokens']} out={u['outputTokens']}")
            for tc in calls: print(f"     TOOL -> {tc['name']}({json.dumps(tc['input'],ensure_ascii=False)})")
            if text: print(f"     TEXT -> {text[:260]}")
            if not calls and not text: print("     (vacío)")
        except Exception as e:
            print(f"  [{name}] ERROR: {str(e)[:160]}")

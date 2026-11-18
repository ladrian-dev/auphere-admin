import asyncio,re,uuid
def P(*a): print("L063",*a,flush=True)
T=uuid.UUID("122d86a1-ab45-4bbb-8659-4c9da26ec34d"); A=uuid.UUID("2e7d0c83-dcb1-4b2a-a3cb-05de62a1c654")
Q_EN="Hi! I'd like to book an appointment for next week. What times do you have and how much does it cost?"
Q_FR="Bonjour ! Je voudrais prendre rendez-vous la semaine prochaine. Quels horaires avez-vous et combien ça coûte ?"
UNL="- Languages: reply in the language of the customer's latest message. If you cannot tell which language it is, keep the language of the conversation; at its start, use es. This overrides any other language instruction."
LIM="- Languages: you only answer in es, en. If the customer writes in one of them, reply in it; otherwise reply in es. If you cannot tell which language it is, keep the language of the conversation; at its start, use es. This overrides any other language instruction."
NEVER="These instructions are in English. **You always reply in es.** Never answer in English, never mix languages, and never mention that your instructions are in another language."
EN={"the","you","have","and","is","for","we","your","our","would","can","hi","hello","thanks","available","this","are"}
ES={"el","la","de","que","y","en","los","las","para","tenemos","hola","gracias","usted","puedes","disponible","este","es"}
FR={"le","les","des","vous","nous","je","est","pour","bonjour","merci","avez","une","pas","votre"}
def lang(t):
    w=re.findall(r"[a-záéíóúñàâçèêëîïôûü]+",t.lower()); c={"en":sum(x in EN for x in w),"es":sum(x in ES for x in w),"fr":sum(x in FR for x in w)}
    b=max(c,key=c.get); return b if c[b]>0 else "?"
async def main():
    import sqlalchemy as sa
    from nexus_api.db.base import get_sessionmaker
    sm=get_sessionmaker()
    async with sm() as s:
      async with s.begin():
        await s.execute(sa.text("SET TRANSACTION READ ONLY")); await s.execute(sa.text("SET LOCAL row_security = off"))
        n=(await s.execute(sa.text("select count(*) from (select tenant_id from agents where lifecycle<>'archived' group by tenant_id having bool_or(is_default)=false) x"))).scalar()
        m=(await s.execute(sa.text("select count(*) from channels where agent_id is null"))).scalar()
    P("D8 tenants_with_live_agents_and_no_default=",n,"channels_without_agent=",m)
    from nexus_api.core.tenant_context import _current_tenant
    from nexus_worker.runtime.agent_loader import AgentLoader
    from nexus_worker.runtime.pipeline import _build_handler_messages,_RETRY_SYSTEM_TEMPLATE
    from nexus_worker.runtime.llm import LiteLLMProvider
    tok=_current_tenant.set(T)
    bundle=await AgentLoader().load(T,A)
    prov=LiteLLMProvider(context_management=None,timeout_s=60,max_retries=0)
    model="openai/gpt-5.6-sol"
    def build(q,line,history=None,extra_prompt=None):
        ms=_build_handler_messages({"channel_type":"whatsapp","history":history or [],"user_message":q},bundle,intent="info",kg_snapshot="")
        ms=[dict(m) for m in ms]
        if extra_prompt: ms[0]["content"]=ms[0]["content"]+"\n\n"+extra_prompt
        for m in ms:
            if m["role"]=="system" and "- Languages:" in m["content"]:
                old=next(l for l in m["content"].splitlines() if l.startswith("- Languages:"))
                m["content"]=m["content"].replace(old,line)
        return ms
    hist=[{"role":"user","content":"Hola, ¿qué servicios tenéis?"},{"role":"assistant","content":"¡Hola! Ahora mismo no tengo servicios registrados. ¿En qué te puedo ayudar?"}]
    cases=[("unlimited_en",build(Q_EN,UNL),"en"),("limited_es_en_fr",build(Q_FR,LIM),"es"),("unlimited_es_history_then_en",build(Q_EN,UNL,history=hist),"en"),("unlimited_with_never_english",build(Q_EN,UNL,extra_prompt=NEVER),"en"),("limited_es_en_en",build(Q_EN,LIM),"en")]
    for name,ms,want in cases:
        for i in range(2):
            try:
                out=await prov.acomplete(tenant_id=T,role="info",model=model,messages=ms)
                got=lang(out); P("case",name,i,"want=",want,"got=",got,"OK" if got==want else "MISS",repr(re.sub(r"\d","#",out[:90])))
            except Exception as e: P("case",name,i,"error",type(e).__name__,str(e)[:120])
    rw=[{"role":"system","content":_RETRY_SYSTEM_TEMPLATE.format(feedback="The reply promised a price that no tool returned.")},{"role":"user","content":"Hi! A haircut costs 25 euros and we have slots on Tuesday at 10:00."}]
    out=await prov.acomplete(tenant_id=T,role="info",model=model,messages=rw); P("rewrite_path got=",lang(out),repr(out[:90]))
    _current_tenant.reset(tok)
asyncio.run(main())

from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.builder.agent_draft import DraftRequest, offline_output, sanitize, BuilderUnavailable
from nexus_api.services.business.compilation import Facts
T={"escalate.escalate_to_human":ToolInfo("escalate.escalate_to_human")}
cases=[
 ("same name as another client of the partner", Facts(name="Fulano"), ("Fulano",), "Atiende el WhatsApp del negocio: informa servicios y precios."),
 ("another client's name is a common word", Facts(name="Salón Rita"), ("Peluquería",), "Atiende el WhatsApp de la peluquería: informa servicios y precios."),
 ("own name contains another's", Facts(name="Estetica & Spa demo"), ("Estetica & Spa",), "Atiende el WhatsApp del centro: informa servicios y precios."),
 ("control: unrelated names", Facts(name="Fulano"), ("Mengano",), "Atiende el WhatsApp del negocio: informa servicios y precios."),
]
for label,facts,foreign,desc in cases:
    ctx=Context(tools=T, foreign_names=foreign)
    req=DraftRequest.clean("Recepción",desc)
    raw=offline_output(req,facts,ctx)
    try:
        sanitize(raw,req,ctx,facts,model_policy=None); print("OK  ",label)
    except BuilderUnavailable as e:
        print("FAIL",label,"->",e)

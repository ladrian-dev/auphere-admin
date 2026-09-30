"""Spec 017 (R5.1, R5.2, R5.6): cómo se llama cada capacidad para un partner.

Un partner no distingue una herramienta de una habilidad, y `booking.create`
no le dice nada. Aquí el catálogo interno se convierte en algo que se puede
leer sin saber cómo está hecho por dentro: un nombre de negocio, una
descripción, la función a la que pertenece y para qué sectores es.

Tres reglas que este fichero cumple y que sus tests fijan:

- **Nada desaparece por no estar traducido.** Una capacidad que el catálogo
  añada antes que este mapa se enseña con su nombre técnico, en «Otras».
  Esconderla sería peor que enseñarla fea.
- **La función es la pregunta del negocio**, no la del código: «Citas»,
  «Pedidos», «Mensajes», «Escalado», «Conocimiento», «Otras».
- **El sector sale de las etiquetas que nombran un vertical.** `booking`
  dice lo que hace; `barbershop` dice para quién es. Solo las segundas
  filtran.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Kind = Literal["tool", "skill"]
Function = Literal["appointments", "orders", "messages", "escalation", "knowledge", "other"]

FUNCTIONS: tuple[Function, ...] = (
    "appointments",
    "orders",
    "messages",
    "escalation",
    "knowledge",
    "other",
)


class CapabilityName(TypedDict, total=False):
    name: dict[str, str]
    description: dict[str, str]
    function: Function
    #: Solo para habilidades, que no traen etiquetas de catálogo; las
    #: herramientas lo deducen de las suyas.
    sectors: list[str]
    #: La integración que hace falta cuando el catálogo no la enlaza por
    #: `connector_id`. Hoy solo AgendaPro: se conecta pegando la URL pública
    #: de la agenda en el tenant, no con una fila de conector, así que sus
    #: herramientas quedaron sueltas y la pantalla no podía avisar.
    requires: str


def _t(
    es_name: str,
    en_name: str,
    es_desc: str,
    en_desc: str,
    function: Function,
    sectors: list[str] | None = None,
    requires: str | None = None,
) -> CapabilityName:
    entry: CapabilityName = {
        "name": {"es": es_name, "en": en_name},
        "description": {"es": es_desc, "en": en_desc},
        "function": function,
    }
    if sectors is not None:
        entry["sectors"] = sectors
    if requires is not None:
        entry["requires"] = requires
    return entry


#: Los verticales que el producto reconoce, tomados de las plantillas de
#: siembra. Una etiqueta de catálogo solo nombra un sector si está aquí.
VERTICALS: frozenset[str] = frozenset(
    {
        "barbershop",
        "beauty_salon",
        "clinica",
        "cobranza",
        "dental",
        "inventario",
        "medspa",
        "nail_studio",
        "restaurante",
        "spa",
        "woocommerce_sales",
    }
)

CAPABILITY_NAMES: dict[tuple[Kind, str], CapabilityName] = {
    # ── Catálogo de Meta (spec 022) — solo con catálogo enlazado ─────
    ("tool", "catalog.search_products"): _t(
        "Buscar en el catálogo",
        "Search the catalogue",
        "Encuentra productos del catálogo de Meta por nombre, con precio y disponibilidad.",
        "Finds products in the Meta catalogue by name, with price and availability.",
        "orders",
        requires="channel_catalog",
    ),
    ("tool", "catalog.get_product"): _t(
        "Enviar productos del catálogo",
        "Send catalogue products",
        "Lee la ficha de un producto y la manda como tarjeta de WhatsApp, con foto y precio.",
        "Reads a product's details and sends it as a WhatsApp card, with photo and price.",
        "orders",
        requires="channel_catalog",
    ),
    # ── Citas ──────────────────────────────────────────────────────────
    ("tool", "booking.create_appointment"): _t(
        "Reservar una cita",
        "Book an appointment",
        "Deja la cita puesta en la agenda del negocio.",
        "Puts the appointment in the business's calendar.",
        "appointments",
        requires="agendapro",
    ),
    ("tool", "booking.check_availability"): _t(
        "Consultar disponibilidad",
        "Check availability",
        "Mira qué huecos quedan antes de proponer nada.",
        "Looks at what slots are free before proposing anything.",
        "appointments",
        requires="agendapro",
    ),
    ("tool", "booking.modify_appointment"): _t(
        "Cambiar una cita",
        "Change an appointment",
        "Mueve una cita ya reservada a otro hueco.",
        "Moves an existing appointment to another slot.",
        "appointments",
    ),
    ("tool", "booking.cancel_appointment"): _t(
        "Cancelar una cita",
        "Cancel an appointment",
        "Anula una cita y libera el hueco.",
        "Cancels an appointment and frees the slot.",
        "appointments",
    ),
    ("tool", "booking.get_appointments"): _t(
        "Consultar las citas de un cliente",
        "Look up a client's appointments",
        "Dice qué citas tiene un cliente y cuándo.",
        "Says which appointments a client has and when.",
        "appointments",
    ),
    ("tool", "agendapro.get_today_appointments"): _t(
        "Ver las citas de hoy",
        "See today's appointments",
        "Lee la agenda del día desde AgendaPro.",
        "Reads the day's calendar from AgendaPro.",
        "appointments",
    ),
    ("tool", "agendapro.scrape_no_shows"): _t(
        "Detectar ausencias",
        "Spot no-shows",
        "Encuentra las citas a las que nadie se presentó.",
        "Finds the appointments nobody turned up to.",
        "appointments",
    ),
    ("tool", "queue.join_queue"): _t(
        "Apuntarse a la fila",
        "Join the queue",
        "Mete al cliente en la fila de espera sin cita.",
        "Puts the client in the walk-in queue.",
        "appointments",
    ),
    ("tool", "queue.get_position"): _t(
        "Decir el puesto en la fila",
        "Say the place in the queue",
        "Dice cuántos hay delante.",
        "Says how many people are ahead.",
        "appointments",
    ),
    ("tool", "queue.get_estimated_wait"): _t(
        "Decir cuánto falta",
        "Say how long the wait is",
        "Calcula la espera con la fila de ese momento.",
        "Works out the wait from the queue at that moment.",
        "appointments",
    ),
    ("tool", "queue.check_in"): _t(
        "Registrar la llegada",
        "Check someone in",
        "Marca que el cliente ya está en el local.",
        "Marks that the client has arrived.",
        "appointments",
    ),
    ("tool", "queue.remove_from_queue"): _t(
        "Sacar de la fila",
        "Take out of the queue",
        "Quita al cliente de la espera.",
        "Removes the client from the queue.",
        "appointments",
    ),
    # ── Pedidos y cobros ───────────────────────────────────────────────
    ("tool", "woocommerce.build_checkout_link"): _t(
        "Mandar un enlace de pago",
        "Send a checkout link",
        "Prepara el carrito y manda el enlace para pagarlo.",
        "Builds the cart and sends the link to pay it.",
        "orders",
    ),
    ("tool", "inventory.search_products"): _t(
        "Buscar productos",
        "Search products",
        "Busca en el catálogo por lo que pide el cliente.",
        "Searches the catalogue for what the client asks.",
        "orders",
    ),
    ("tool", "inventory.get_product"): _t(
        "Consultar un producto",
        "Look up a product",
        "Dice precio y detalles de un producto.",
        "Says a product's price and details.",
        "orders",
    ),
    ("tool", "inventory.check_stock"): _t(
        "Consultar el stock",
        "Check stock",
        "Dice cuántas unidades quedan.",
        "Says how many units are left.",
        "orders",
    ),
    ("tool", "inventory.low_stock"): _t(
        "Avisar de stock bajo",
        "Flag low stock",
        "Lista lo que está a punto de agotarse.",
        "Lists what is about to run out.",
        "orders",
    ),
    ("tool", "billing.find_client"): _t(
        "Buscar un cliente",
        "Find a client",
        "Encuentra la ficha de cobro de un cliente.",
        "Finds a client's billing record.",
        "orders",
    ),
    ("tool", "billing.get_account"): _t(
        "Consultar una cuenta",
        "Look up an account",
        "Dice el estado de una cuenta de cobro.",
        "Says the state of a billing account.",
        "orders",
    ),
    ("tool", "billing.get_my_debt"): _t(
        "Decirle al cliente lo que debe",
        "Tell the client what they owe",
        "Responde el saldo pendiente de quien pregunta.",
        "Answers the outstanding balance of whoever asks.",
        "orders",
    ),
    ("tool", "billing.get_debtor_by_phone"): _t(
        "Buscar una deuda por teléfono",
        "Find a debt by phone",
        "Identifica al deudor por su número.",
        "Identifies the debtor by their number.",
        "orders",
    ),
    ("tool", "billing.list_overdue"): _t(
        "Listar los pagos vencidos",
        "List overdue payments",
        "Saca quién debe y desde cuándo.",
        "Lists who owes and since when.",
        "orders",
    ),
    ("tool", "billing.create_account"): _t(
        "Crear una cuenta de cobro",
        "Create a billing account",
        "Abre la ficha de cobro de un cliente nuevo.",
        "Opens the billing record of a new client.",
        "orders",
    ),
    ("tool", "billing.update_account"): _t(
        "Actualizar una cuenta",
        "Update an account",
        "Corrige los datos de una cuenta de cobro.",
        "Corrects the details of a billing account.",
        "orders",
    ),
    ("tool", "billing.add_charge"): _t(
        "Añadir un cargo",
        "Add a charge",
        "Suma un importe a lo que el cliente debe.",
        "Adds an amount to what the client owes.",
        "orders",
    ),
    ("tool", "billing.apply_discount"): _t(
        "Aplicar un descuento",
        "Apply a discount",
        "Rebaja lo que el cliente debe.",
        "Reduces what the client owes.",
        "orders",
    ),
    ("tool", "billing.register_payment"): _t(
        "Registrar un pago",
        "Register a payment",
        "Anota que el cliente ha pagado.",
        "Records that the client has paid.",
        "orders",
    ),
    ("tool", "billing.update_status"): _t(
        "Cambiar el estado de un cobro",
        "Change a charge's status",
        "Marca un cobro como pagado, pendiente o anulado.",
        "Marks a charge as paid, pending or void.",
        "orders",
    ),
    ("tool", "billing.send_reminders"): _t(
        "Mandar recordatorios de pago",
        "Send payment reminders",
        "Avisa a quien tiene un pago pendiente.",
        "Nudges whoever has a payment outstanding.",
        "orders",
    ),
    ("tool", "woocommerce.list_products"): _t(
        "Listar productos de la tienda",
        "List the shop's products",
        "Saca el catálogo de la tienda del cliente.",
        "Pulls the client's shop catalogue.",
        "orders",
    ),
    ("tool", "woocommerce.get_product"): _t(
        "Consultar un producto de la tienda",
        "Look up a shop product",
        "Dice precio, stock y detalles de un producto.",
        "Says a product's price, stock and details.",
        "orders",
    ),
    ("tool", "woocommerce.list_product_variations"): _t(
        "Ver tallas y variantes",
        "See sizes and variants",
        "Lista las variantes de un producto: talla, color, formato.",
        "Lists a product's variants: size, colour, format.",
        "orders",
    ),
    ("tool", "woocommerce.list_categories"): _t(
        "Ver las categorías de la tienda",
        "See the shop's categories",
        "Dice cómo está organizado el catálogo.",
        "Says how the catalogue is organised.",
        "orders",
    ),
    ("tool", "woocommerce.list_orders"): _t(
        "Listar pedidos",
        "List orders",
        "Saca los pedidos de la tienda.",
        "Pulls the shop's orders.",
        "orders",
    ),
    ("tool", "woocommerce.get_order"): _t(
        "Consultar un pedido",
        "Look up an order",
        "Dice por dónde va un pedido y qué lleva.",
        "Says where an order stands and what is in it.",
        "orders",
    ),
    ("tool", "woocommerce.list_customers"): _t(
        "Listar clientes de la tienda",
        "List shop customers",
        "Saca los clientes registrados en la tienda.",
        "Pulls the customers registered in the shop.",
        "orders",
    ),
    ("tool", "woocommerce.get_customer"): _t(
        "Consultar un cliente de la tienda",
        "Look up a shop customer",
        "Dice los datos y los pedidos de un cliente.",
        "Says a customer's details and orders.",
        "orders",
    ),
    ("tool", "woocommerce.create_order"): _t(
        "Crear un pedido",
        "Create an order",
        "Deja el pedido hecho en la tienda.",
        "Places the order in the shop.",
        "orders",
    ),
    ("tool", "woocommerce.update_order"): _t(
        "Cambiar un pedido",
        "Change an order",
        "Corrige lo que lleva un pedido antes de enviarlo.",
        "Corrects what an order contains before it ships.",
        "orders",
    ),
    ("tool", "woocommerce.update_order_status"): _t(
        "Cambiar el estado de un pedido",
        "Change an order's status",
        "Marca un pedido como pagado, enviado o cancelado.",
        "Marks an order as paid, shipped or cancelled.",
        "orders",
    ),
    ("tool", "woocommerce.add_order_note"): _t(
        "Añadir una nota a un pedido",
        "Add a note to an order",
        "Deja escrito algo en el pedido para el negocio.",
        "Writes something on the order for the business.",
        "orders",
    ),
    # ── Mensajes ───────────────────────────────────────────────────────
    ("tool", "notification.send_text"): _t(
        "Enviar un mensaje",
        "Send a message",
        "Manda texto al cliente por el canal.",
        "Sends text to the client through the channel.",
        "messages",
    ),
    ("tool", "notification.send_template"): _t(
        "Enviar una plantilla de WhatsApp",
        "Send a WhatsApp template",
        "Manda uno de los mensajes que Meta tiene aprobados.",
        "Sends one of the messages Meta has approved.",
        "messages",
    ),
    ("tool", "notification.send_image"): _t(
        "Enviar una imagen",
        "Send an image",
        "Manda una foto al cliente.",
        "Sends a photo to the client.",
        "messages",
    ),
    ("tool", "notification.send_document"): _t(
        "Enviar un documento",
        "Send a document",
        "Manda un PDF o un fichero.",
        "Sends a PDF or a file.",
        "messages",
    ),
    ("tool", "notification.send_audio"): _t(
        "Enviar un audio",
        "Send audio",
        "Manda una nota de voz.",
        "Sends a voice note.",
        "messages",
    ),
    ("tool", "notification.send_video"): _t(
        "Enviar un vídeo",
        "Send a video",
        "Manda un vídeo al cliente.",
        "Sends a video to the client.",
        "messages",
    ),
    ("tool", "notification.send_location"): _t(
        "Enviar una ubicación",
        "Send a location",
        "Manda el punto del mapa donde está el negocio.",
        "Sends the map point where the business is.",
        "messages",
    ),
    ("tool", "notification.send_reaction"): _t(
        "Reaccionar a un mensaje",
        "React to a message",
        "Pone un emoji sobre lo que el cliente escribió.",
        "Puts an emoji on what the client wrote.",
        "messages",
    ),
    ("tool", "notification.schedule_reminder"): _t(
        "Programar un recordatorio",
        "Schedule a reminder",
        "Deja preparado un aviso para más tarde.",
        "Leaves a reminder ready for later.",
        "messages",
    ),
    ("tool", "notification.cancel_scheduled"): _t(
        "Cancelar un aviso programado",
        "Cancel a scheduled reminder",
        "Retira un recordatorio que aún no ha salido.",
        "Withdraws a reminder that has not gone out yet.",
        "messages",
    ),
    ("tool", "response.send_interactive"): _t(
        "Enviar botones o una lista",
        "Send buttons or a list",
        "Da a elegir sin que el cliente tenga que escribir.",
        "Offers choices so the client need not type.",
        "messages",
    ),
    # ── Escalado ───────────────────────────────────────────────────────
    ("tool", "escalate.escalate_to_human"): _t(
        "Pasar a una persona",
        "Hand over to a human",
        "Avisa al equipo y deja de responder.",
        "Alerts the team and stops answering.",
        "escalation",
    ),
    ("tool", "operator.consult_owner"): _t(
        "Preguntar al responsable",
        "Ask the owner",
        "Consulta una duda al negocio sin cortar la conversación.",
        "Asks the business a question without dropping the conversation.",
        "escalation",
    ),
    # ── Otras ──────────────────────────────────────────────────────────
    ("tool", "client.get_history"): _t(
        "Consultar el historial del cliente",
        "Look up a client's history",
        "Recuerda lo que ese cliente ha hecho antes.",
        "Remembers what that client has done before.",
        "other",
    ),
    ("tool", "client.get_preferences"): _t(
        "Consultar las preferencias del cliente",
        "Look up client preferences",
        "Dice lo que ese cliente suele pedir.",
        "Says what that client usually asks for.",
        "other",
    ),
    ("tool", "client.update_preferences"): _t(
        "Guardar las preferencias del cliente",
        "Save client preferences",
        "Anota una preferencia para la próxima vez.",
        "Notes a preference for next time.",
        "other",
    ),
    ("tool", "commission.calculate_commission"): _t(
        "Calcular una comisión",
        "Work out a commission",
        "Saca la comisión de un servicio.",
        "Works out the commission on a service.",
        "other",
    ),
    ("tool", "commission.get_barber_earnings"): _t(
        "Consultar lo que ha ganado un profesional",
        "Look up a professional's earnings",
        "Dice cuánto lleva ganado en el periodo.",
        "Says how much they have earned in the period.",
        "other",
    ),
    ("tool", "commission.get_daily_report"): _t(
        "Ver el informe del día",
        "See the day's report",
        "Resume lo facturado en la jornada.",
        "Sums up what was billed during the day.",
        "other",
    ),
    # ── Stripe, Calendly y HubSpot (spec 023) — la lista cerrada ───────
    # La clave es el slug del proveedor, que es el ``tool_catalog.name`` de
    # un conector dinámico. Toda entrada de ``toolkits.TOOLKIT_ALLOWLISTS``
    # tiene la suya; el test de la lista lo exige.
    ("tool", "STRIPE_SEARCH_CUSTOMERS"): _t(
        "Buscar un cliente en Stripe",
        "Find a customer in Stripe",
        "Encuentra a un cliente por su nombre o su correo.",
        "Finds a customer by name or email.",
        "orders",
    ),
    ("tool", "STRIPE_SEARCH_PAYMENT_INTENTS"): _t(
        "Ver el estado de un cobro",
        "Check a payment's status",
        "Busca los cobros de un cliente y dice si cada uno está pagado, pendiente o fallido.",
        "Looks up a customer's payments and says whether each one is paid, pending or failed.",
        "orders",
    ),
    ("tool", "STRIPE_RETRIEVE_PAYMENT_INTENT"): _t(
        "Ver el detalle de un cobro",
        "See a payment's details",
        "Lee un cobro concreto: importe, fecha y estado.",
        "Reads one payment: amount, date and status.",
        "orders",
    ),
    ("tool", "STRIPE_LIST_INVOICES"): _t(
        "Ver las facturas de un cliente",
        "See a customer's invoices",
        "Lista las facturas de un cliente y cuáles siguen sin pagar.",
        "Lists a customer's invoices and which ones are still unpaid.",
        "orders",
    ),
    ("tool", "STRIPE_LIST_PAYMENT_LINKS"): _t(
        "Ver los enlaces de pago",
        "See the payment links",
        "Lista los enlaces de pago que el negocio ya tiene, para mandar el que toca.",
        "Lists the payment links the business already has, to send the right one.",
        "orders",
    ),
    ("tool", "STRIPE_LIST_PRODUCTS"): _t(
        "Consultar productos",
        "Look up products",
        "Lista los productos que el negocio vende en Stripe.",
        "Lists the products the business sells in Stripe.",
        "orders",
    ),
    ("tool", "STRIPE_LIST_PRICES"): _t(
        "Consultar precios",
        "Look up prices",
        "Dice cuánto cuesta cada producto.",
        "Says what each product costs.",
        "orders",
    ),
    ("tool", "STRIPE_LIST_REFUNDS"): _t(
        "Ver reembolsos",
        "See refunds",
        "Lista los reembolsos hechos y en qué estado están.",
        "Lists the refunds made and their state.",
        "orders",
    ),
    ("tool", "STRIPE_CREATE_CUSTOMER"): _t(
        "Dar de alta un cliente en Stripe",
        "Add a customer in Stripe",
        "Crea la ficha de un cliente nuevo para poder cobrarle.",
        "Creates a new customer so they can be charged.",
        "orders",
    ),
    ("tool", "STRIPE_CREATE_PAYMENT_LINK"): _t(
        "Crear un enlace de pago",
        "Create a payment link",
        "Genera un enlace de pago nuevo para un producto o un importe.",
        "Generates a new payment link for a product or an amount.",
        "orders",
    ),
    ("tool", "STRIPE_CREATE_REFUND"): _t(
        "Reembolsar un cobro",
        "Refund a payment",
        "Devuelve el dinero de un cobro, entero o en parte.",
        "Returns the money of a payment, in full or in part.",
        "orders",
    ),
    ("tool", "STRIPE_SEND_INVOICE"): _t(
        "Enviar una factura",
        "Send an invoice",
        "Manda una factura al cliente por correo para que la pague.",
        "Emails an invoice to the customer so they can pay it.",
        "orders",
    ),
    ("tool", "CALENDLY_WHO_AM_I"): _t(
        "Identificar la agenda conectada",
        "Identify the connected calendar",
        "Sabe de quién es la agenda de Calendly conectada; hace falta para consultar lo demás.",
        "Knows whose Calendly calendar is connected; needed before anything else can be looked up.",
        "appointments",
    ),
    ("tool", "CALENDLY_LIST_EVENT_TYPES"): _t(
        "Ver los tipos de cita",
        "See the appointment types",
        "Lista los servicios que se pueden reservar y cuánto dura cada uno.",
        "Lists the services that can be booked and how long each one takes.",
        "appointments",
    ),
    ("tool", "CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES"): _t(
        "Consultar huecos en Calendly",
        "Check free slots in Calendly",
        "Dice qué horas quedan libres para un tipo de cita en unos días.",
        "Says which times are free for an appointment type over a few days.",
        "appointments",
    ),
    ("tool", "CALENDLY_LIST_SCHEDULED_EVENTS"): _t(
        "Ver las citas reservadas",
        "See booked appointments",
        "Lista las citas que ya están reservadas en un periodo.",
        "Lists the appointments already booked in a period.",
        "appointments",
    ),
    ("tool", "CALENDLY_GET_EVENT"): _t(
        "Ver una cita",
        "See an appointment",
        "Lee una cita concreta: cuándo es, dónde y con quién.",
        "Reads one appointment: when, where and with whom.",
        "appointments",
    ),
    ("tool", "CALENDLY_LIST_EVENT_INVITEES"): _t(
        "Ver quién tiene la cita",
        "See who holds the appointment",
        "Dice quién reservó una cita y con qué contacto.",
        "Says who booked an appointment and their contact details.",
        "appointments",
    ),
    ("tool", "CALENDLY_LIST_USER_BUSY_TIMES"): _t(
        "Ver cuándo está ocupado",
        "See when the calendar is busy",
        "Lista las horas ocupadas de la agenda en los próximos días.",
        "Lists the calendar's busy hours over the next few days.",
        "appointments",
    ),
    ("tool", "CALENDLY_POST_INVITEE"): _t(
        "Reservar una cita en Calendly",
        "Book an appointment in Calendly",
        "Reserva una cita a nombre del cliente en un hueco libre.",
        "Books an appointment for the client in a free slot.",
        "appointments",
    ),
    ("tool", "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK"): _t(
        "Crear un enlace de reserva",
        "Create a booking link",
        "Genera un enlace de un solo uso para que el cliente elija su hora.",
        "Generates a single-use link so the client can pick their time.",
        "appointments",
    ),
    ("tool", "CALENDLY_CANCEL_SCHEDULED_EVENT"): _t(
        "Cancelar una cita en Calendly",
        "Cancel an appointment in Calendly",
        "Cancela una cita reservada y avisa a quien la tenía.",
        "Cancels a booked appointment and notifies whoever had it.",
        "appointments",
    ),
    ("tool", "HUBSPOT_SEARCH_CONTACTS"): _t(
        "Buscar un contacto",
        "Find a contact",
        "Encuentra a quien escribe por su teléfono, su correo o su nombre.",
        "Finds whoever is writing by phone, email or name.",
        "other",
    ),
    ("tool", "HUBSPOT_LIST_CONTACT_NOTES"): _t(
        "Ver las notas de un contacto",
        "See a contact's notes",
        "Lee lo que el negocio ha anotado sobre ese contacto.",
        "Reads what the business has noted about that contact.",
        "other",
    ),
    ("tool", "HUBSPOT_SEARCH_DEALS"): _t(
        "Buscar una oportunidad",
        "Find a deal",
        "Encuentra las oportunidades de venta abiertas con un contacto.",
        "Finds the open sales opportunities with a contact.",
        "other",
    ),
    ("tool", "HUBSPOT_GET_DEAL"): _t(
        "Ver una oportunidad",
        "See a deal",
        "Lee una oportunidad de venta: importe, fase y fecha prevista.",
        "Reads one sales opportunity: amount, stage and expected date.",
        "other",
    ),
    ("tool", "HUBSPOT_SEARCH_TICKETS"): _t(
        "Buscar una incidencia",
        "Find a support case",
        "Encuentra las incidencias abiertas de un contacto.",
        "Finds a contact's open support cases.",
        "other",
    ),
    ("tool", "HUBSPOT_GET_TICKET"): _t(
        "Ver una incidencia",
        "See a support case",
        "Lee una incidencia: qué pasó, en qué estado está y quién la lleva.",
        "Reads one support case: what happened, its state and who handles it.",
        "other",
    ),
    ("tool", "HUBSPOT_CREATE_CONTACT"): _t(
        "Dar de alta un contacto",
        "Add a contact",
        "Crea la ficha de alguien nuevo con su teléfono y su nombre.",
        "Creates a record for someone new with their phone and name.",
        "other",
    ),
    ("tool", "HUBSPOT_UPDATE_CONTACT"): _t(
        "Cambiar los datos de un contacto",
        "Update a contact's details",
        "Corrige el teléfono, el correo o el nombre de un contacto.",
        "Corrects a contact's phone, email or name.",
        "other",
    ),
    ("tool", "HUBSPOT_CREATE_NOTE"): _t(
        "Anotar en la ficha",
        "Add a note to the record",
        "Deja una nota en la ficha del contacto con lo que se habló.",
        "Leaves a note on the contact's record with what was discussed.",
        "other",
    ),
    ("tool", "HUBSPOT_CREATE_DEAL"): _t(
        "Abrir una oportunidad",
        "Open a deal",
        "Abre una oportunidad de venta para un contacto.",
        "Opens a sales opportunity for a contact.",
        "other",
    ),
    ("tool", "HUBSPOT_CREATE_TICKET"): _t(
        "Abrir una incidencia",
        "Open a support case",
        "Registra una incidencia para que alguien del negocio la atienda.",
        "Logs a support case for someone at the business to handle.",
        "other",
    ),
    # ── Habilidades ────────────────────────────────────────────────────
    ("skill", "escalation-policy"): _t(
        "Cuándo pasar a una persona",
        "When to hand over to a human",
        "Fija en qué casos el agente deja de responder y avisa al equipo.",
        "Sets when the agent stops answering and alerts the team.",
        "escalation",
        [],
    ),
    ("skill", "whatsapp-24h-window"): _t(
        "Respetar la ventana de 24 horas",
        "Respect the 24-hour window",
        "Evita escribir fuera del plazo que Meta permite sin plantilla.",
        "Avoids writing outside the window Meta allows without a template.",
        "messages",
        [],
    ),
    ("skill", "whatsapp-native-components"): _t(
        "Usar botones y listas de WhatsApp",
        "Use WhatsApp buttons and lists",
        "Elige el componente adecuado en vez de pedir que escriban.",
        "Picks the right component instead of asking people to type.",
        "messages",
        [],
    ),
    ("skill", "anti-hallucination-booking"): _t(
        "No confirmar una cita sin comprobarla",
        "Never confirm a booking without checking",
        "Prohíbe dar por hecha una reserva que el sistema no ha devuelto.",
        "Forbids treating a booking as done when the system has not returned it.",
        "appointments",
        [],
    ),
    ("skill", "pre-op-screening"): _t(
        "Preguntas antes de un tratamiento",
        "Questions before a treatment",
        "Cuestionario obligatorio antes de reservar un procedimiento.",
        "Mandatory questionnaire before booking a procedure.",
        "appointments",
        ["medspa", "clinica", "dental"],
    ),
    ("skill", "post-op-symptom-triage"): _t(
        "Triaje de síntomas tras un tratamiento",
        "Symptom triage after a treatment",
        "Clasifica en tres niveles y escala lo urgente.",
        "Sorts into three levels and escalates what is urgent.",
        "escalation",
        ["medspa", "clinica", "dental"],
    ),
    ("skill", "medical-claims-discipline"): _t(
        "No prometer resultados médicos",
        "Never promise medical outcomes",
        "Prohíbe afirmar lo que un tratamiento va a conseguir.",
        "Forbids claiming what a treatment will achieve.",
        "knowledge",
        ["medspa", "clinica", "dental"],
    ),
    ("skill", "phi-redaction"): _t(
        "No repetir datos clínicos",
        "Never repeat clinical data",
        "Impide que el agente escriba información clínica del paciente.",
        "Stops the agent writing a patient's clinical information.",
        "knowledge",
        ["medspa", "clinica", "dental"],
    ),
    ("skill", "aesthetic-procedures-kb"): _t(
        "Responder sobre los tratamientos",
        "Answer about the treatments",
        "Responde con el catálogo de procedimientos del negocio.",
        "Answers from the business's catalogue of procedures.",
        "knowledge",
        ["medspa", "beauty_salon", "spa"],
    ),
    ("skill", "before-after-photos"): _t(
        "Cómo tratar las fotos de antes y después",
        "How to handle before-and-after photos",
        "Fija qué hace el agente cuando le mandan o le piden fotos.",
        "Sets what the agent does when photos are sent or asked for.",
        "messages",
        ["medspa", "beauty_salon", "spa"],
    ),
}


def business_name(key: str, kind: Kind, lang: str) -> str:
    """El nombre para el partner; el técnico si aún no tiene uno."""
    entry = CAPABILITY_NAMES.get((kind, key))
    if entry is None:
        return key
    return entry["name"].get(lang) or entry["name"]["es"]


def description_of(key: str, kind: Kind, lang: str) -> str:
    entry = CAPABILITY_NAMES.get((kind, key))
    if entry is None:
        return ""
    return entry["description"].get(lang) or entry["description"]["es"]


def function_of(key: str, kind: Kind) -> Function:
    """A qué grupo de la pantalla pertenece. Lo que no esté en el mapa cae en
    «Otras»: se ve, que es lo que importa."""
    entry = CAPABILITY_NAMES.get((kind, key))
    return entry["function"] if entry else "other"


def sectors_of(key: str, kind: Kind, tags: list[str] | None) -> list[str]:
    """Para qué sectores es. Vacío = común a todos.

    Las herramientas lo deducen de sus etiquetas de catálogo —solo las que
    nombran un vertical, no las que describen lo que hacen—; las habilidades
    no traen etiquetas, así que lo dice el mapa.
    """
    entry = CAPABILITY_NAMES.get((kind, key))
    if entry is not None and "sectors" in entry:
        return list(entry["sectors"])
    return [t for t in (tags or []) if t in VERTICALS]


def requires_connector(key: str, kind: Kind) -> str | None:
    """Qué integración hace falta cuando el catálogo no la enlaza.

    `booking.check_availability` y `booking.create_appointment` leen
    `tenants.agendapro_public_url`, así que sin la agenda enlazada no
    funcionan — pero en `tool_catalog` figuran como nativas, sin
    `connector_id`, porque AgendaPro no se conecta con una fila de conector.
    Sin esto la pantalla las daría por utilizables y mentiría.

    Cancelar, modificar y consultar citas NO entran: están fuera del flujo
    público y el agente las escala al dueño, así que no dependen de la
    agenda (`api/admin/integrations.py`).
    """
    entry = CAPABILITY_NAMES.get((kind, key))
    return entry.get("requires") if entry else None

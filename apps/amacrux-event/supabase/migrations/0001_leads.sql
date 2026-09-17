-- Base de leads del Diagnóstico IA de Amacrux.
-- Ejecutar en Supabase → SQL Editor (una vez). Solo la service role escribe/lee:
-- RLS activada sin políticas; el panel de Supabase se usa con la cuenta del proyecto.

create table if not exists public.leads (
  id               uuid primary key default gen_random_uuid(),
  created_at       timestamptz not null default now(),
  idempotency_key  uuid not null unique,
  name             text not null,
  company          text not null,
  email            text not null,
  phone            text,
  role             text,
  interest         text not null,
  consent_contact  boolean not null,
  consent_marketing boolean not null default false,
  campaign         text,
  utm              jsonb,
  answers          jsonb not null,          -- valores internos de las 12 respuestas
  answers_labels   jsonb not null,          -- etiquetas legibles en español
  score_total      integer not null check (score_total between 0 and 100),
  score_range      text not null,           -- exploracion | oportunidad_inicial | oportunidad_prioritaria | alta_intencion
  lead_tier        text not null,           -- frio | tibio | caliente | muy_caliente (interno)
  segment          jsonb not null,
  recommendations  jsonb not null,          -- [{id, title, category, category_label}]
  email_delivered  boolean,
  email_id         text,
  mode             text not null default 'live'
);

create index if not exists leads_created_at_idx on public.leads (created_at desc);
create index if not exists leads_email_idx on public.leads (lower(email));
create index if not exists leads_campaign_idx on public.leads (campaign);

alter table public.leads enable row level security;

-- Vista cómoda para preparar reuniones: contacto → empresa → problemas → nivel → recomendaciones.
create or replace view public.leads_panel as
select
  created_at,
  name                                   as nombre,
  company                                as empresa,
  email                                  as correo,
  phone                                  as telefono,
  answers_labels->>'rol'                 as rol,
  answers_labels->>'sector'              as sector,
  answers_labels->>'tamano_equipo'       as tamano_equipo,
  answers_labels->>'clientes'            as clientes,
  answers_labels->>'como_trabajan'       as como_trabajan,
  answers_labels->>'uso_ia'              as uso_ia,
  answers_labels->>'datos'               as datos,
  answers_labels->'fricciones'           as fricciones,
  answers_labels->'objetivos'            as objetivos,
  answers_labels->>'urgencia'            as urgencia,
  answers_labels->>'apoyo_tecnico'       as apoyo_tecnico,
  answers_labels->>'inversion'           as inversion,
  score_total                            as puntuacion,
  score_range                            as nivel,
  lead_tier                              as etiqueta_interna,
  recommendations->0->>'title'           as recomendacion_1,
  recommendations->1->>'title'           as recomendacion_2,
  recommendations->2->>'title'           as recomendacion_3,
  campaign                               as campana,
  email_delivered                        as correo_enviado,
  mode                                   as modo,
  id
from public.leads
order by created_at desc;

-- Borrado por solicitud de la persona (derechos):
--   delete from public.leads where lower(email) = lower('persona@empresa.com');

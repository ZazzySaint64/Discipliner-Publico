-- Schema do Supabase (Postgres) pro Discipliner.
--
-- Espelha as tabelas do database.py (SQLite local), mas com user_id em cada
-- linha e RLS (Row Level Security) garantindo que cada usuário só lê/escreve
-- as próprias linhas — é o Postgres que barra, não o app, então mesmo se o
-- app tiver um bug ninguém lê dado de outro usuário.
--
-- A tabela "account" antiga (senha com hash local) some: quem cuida de
-- login/senha/recuperação agora é o Supabase Auth (schema auth.*, já vem
-- pronto). auth.uid() abaixo é o id do usuário logado.
--
-- Como aplicar: Supabase → seu projeto → SQL Editor → cola isso inteiro → Run.

create table if not exists missions (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    periodicity text not null check (periodicity in ('diaria', 'semanal', 'mensal')),
    difficulty text not null check (difficulty in ('facil', 'media', 'dificil')),
    points integer not null,
    last_completed_date text,
    custom_days text not null default ''
);
alter table missions enable row level security;
create policy "missions: dono le/escreve" on missions
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table if not exists completions (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    mission_id bigint,
    mission_name text not null,
    date text not null,
    points integer not null,
    obs text not null default '',
    periodicity text not null default 'diaria'
);
alter table completions enable row level security;
create policy "completions: dono le/escreve" on completions
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table if not exists streak_freezes (
    user_id uuid not null references auth.users(id) on delete cascade,
    month text not null,
    frozen_date text,
    primary key (user_id, month)
);
alter table streak_freezes enable row level security;
create policy "streak_freezes: dono le/escreve" on streak_freezes
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table if not exists app_settings (
    user_id uuid primary key references auth.users(id) on delete cascade,
    language text not null default 'pt',
    dark_mode boolean not null default true,
    accent_theme text not null default 'floresta',
    reminder_enabled boolean not null default false,
    reminder_time text not null default '20:00',
    best_streak integer not null default 0,
    best_streak_semanal integer not null default 0,
    best_streak_mensal integer not null default 0,
    onboarding_done boolean not null default false,
    avatar text not null default 'idle'
);
alter table app_settings enable row level security;
create policy "app_settings: dono le/escreve" on app_settings
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Guarda o resultado de uma compra validada. Escrita só pelo backend
-- (service_role, via Edge Functions stripe-webhook / mercadopago-webhook, que
-- validam com o provedor antes de gravar) — o app nunca escreve aqui direto,
-- só lê o próprio status. Por isso a policy é só de SELECT pro dono.
--
-- Provider-agnóstica DE PROPÓSITO: o que faz alguém ser Premium é EXISTIR uma
-- linha aqui, não COMO pagou. Quando integrar o Google Play Billing, é só
-- adicionar um play-billing-webhook que valida com a Play Developer API e faz
-- o mesmo upsert com provider='play' — nada muda no app nem em
-- account.sync_premium_status.
--   provider        : 'stripe' | 'mercadopago' | 'play'
--   purchase_token  : id de referência do provedor (Checkout Session cs_… do
--                     Stripe, payment id do MP, purchaseToken da Play)
--   payment_intent  : só Stripe (pi_…), guardado pra estorno programático
create table if not exists purchases (
    user_id uuid primary key references auth.users(id) on delete cascade,
    entitlement text not null default 'premium',
    provider text not null default 'stripe',
    purchase_token text,
    payment_intent text,
    purchased_at timestamptz
);
alter table purchases enable row level security;
create policy "purchases: dono le" on purchases
    for select using (auth.uid() = user_id);

-- Colunas novas pra quem já tinha a tabela purchases criada (o "create table
-- if not exists" acima não altera uma tabela existente). Seguro reexecutar.
alter table purchases add column if not exists provider text not null default 'stripe';
alter table purchases add column if not exists payment_intent text;

-- Idempotência dos webhooks: o Stripe re-envia eventos, o Mercado Pago manda
-- várias notificações pro mesmo pagamento. A Edge Function grava aqui ANTES de
-- creditar; PK repetida (23505) = re-entrega, ignora. Sem policy: só o
-- service_role (Edge Functions) toca nisso — anon/authenticated nem enxerga.
create table if not exists webhook_events (
    provider text not null,
    event_id text not null,
    seen_at timestamptz not null default now(),
    primary key (provider, event_id)
);
alter table webhook_events enable row level security;

-- "Carta morta": pagamento confirmado pelo provedor mas SEM como saber de quem
-- é (link aberto sem client_reference_id/external_reference e e-mail não bateu).
-- Em vez de perder o pagamento em silêncio, registra aqui pra conciliar na mão
-- pelo painel. Sem policy: só o service_role.
create table if not exists unmatched_purchases (
    id bigint generated always as identity primary key,
    provider text not null,
    reason text not null,
    payload jsonb not null,
    resolved boolean not null default false,
    created_at timestamptz not null default now()
);
alter table unmatched_purchases enable row level security;

-- Cria a linha de settings automaticamente quando alguém termina o cadastro
-- (equivalente ao "INSERT OR IGNORE ... VALUES (1)" do SQLite local, só que
-- agora dispara por usuário via trigger em vez de rodar 1x no init_db()).
create or replace function public.handle_new_user()
returns trigger as $$
begin
    insert into public.app_settings (user_id) values (new.id);
    return new;
end;
$$ language plpgsql security definer set search_path = '';
-- só o trigger chama; sem isso anon/authenticated alcançam via /rest/v1/rpc
revoke execute on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Backup na nuvem (ver backup.py / supabase_client.upload_backup) — sobe o
-- daily_quest.db (SQLite local) INTEIRO como está, não as tabelas relacionais
-- acima linha a linha. Simples de propósito: o banco local continua sendo a
-- fonte da verdade, isso é só uma cópia de segurança presa à conta, restaurada
-- manualmente (nunca sozinha, pra não arriscar sobrescrever dado sem querer —
-- ver README > Backup na Nuvem). 1 arquivo por conta, path prefixado com o
-- próprio user_id (storage.foldername pega o 1º pedaço do caminho).
insert into storage.buckets (id, name, public)
values ('backups', 'backups', false)
on conflict (id) do nothing;

create policy "backups: dono le/escreve a propria pasta"
on storage.objects for all
using (bucket_id = 'backups' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'backups' and (storage.foldername(name))[1] = auth.uid()::text);

-- Relato remoto de crash (ver crash_reporter.py) — ANÔNIMO, só dado técnico:
-- o traceback, a versão do app/OS, e um install_id aleatório gerado no 1º boot
-- (NÃO é user_id, não liga a ninguém — só serve pra contar aparelhos
-- distintos). Sem e-mail, nome ou conteúdo de missão. A policy é só de INSERT
-- pra qualquer um (a anon key basta): assim o app grava sem precisar de login,
-- e como NÃO existe policy de SELECT, ninguém lê isso pela anon key — você lê
-- no painel do Supabase (Table Editor / SQL Editor), que roda como service_role.
create table if not exists crash_reports (
    id bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    install_id text not null default '',
    app_version text not null default '',
    platform text not null default '',
    os_version text not null default '',
    error_type text not null default '',
    traceback text not null
);
alter table crash_reports enable row level security;
create policy "crash_reports: qualquer um insere" on crash_reports
    for insert with check (true);
-- qualquer um insere com a chave pública: sem teto de tamanho, dava pra
-- encher o banco com textos gigantes (migração crash_reports_limites_tamanho)
alter table crash_reports
    add constraint crash_reports_install_id_len check (length(install_id) <= 64),
    add constraint crash_reports_app_version_len check (length(app_version) <= 20),
    add constraint crash_reports_platform_len check (length(platform) <= 20),
    add constraint crash_reports_os_version_len check (length(os_version) <= 200),
    add constraint crash_reports_error_type_len check (length(error_type) <= 200),
    add constraint crash_reports_traceback_len check (length(traceback) <= 10000);

-- Telemetria mínima de retenção (ver telemetry.py): 1 linha por aparelho/dia/
-- tipo, anônima (install_id aleatório). Só INSERT, sem SELECT pela anon key;
-- a policy só aceita a data de hoje (±2 dias de fuso), então não dá pra
-- encher o histórico com datas inventadas. Consultas de D1/D7 no README.
create table if not exists app_activity (
    install_id text not null check (install_id ~ '^[0-9a-f]{32}$'),
    day date not null,
    kind text not null check (kind in ('open', 'complete')),
    app_version text not null default '' check (length(app_version) <= 20),
    created_at timestamptz not null default now(),
    primary key (install_id, day, kind)
);
alter table app_activity enable row level security;
create policy "app_activity: qualquer um insere o dia de hoje" on app_activity
    for insert to anon, authenticated
    with check (day between current_date - 2 and current_date + 2);

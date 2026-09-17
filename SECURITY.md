# Segurança

## Como reportar uma vulnerabilidade

Não abra uma issue pública. Use o botão **Report a vulnerability** na aba **Security** deste repositório: o relato fica privado entre você e eu até ser corrigido.

## O que está (e o que não está) neste repositório

O app fala com o Supabase direto do celular, então duas coisas aparecem no código de propósito:

- A **URL do projeto** e a **chave publicável** (`sb_publishable_...`) em `supabase_client.py`. Elas vão dentro do APK de qualquer jeito, qualquer pessoa extrai com um `unzip`. Não são segredo: o que protege os dados é o banco.
- O **esquema do banco** (`supabase_schema.sql`), com as regras de acesso.

O que **nunca** entra aqui (ver `.gitignore`):

- A chave `service_role` do Supabase e os segredos das Edge Functions (Stripe, Mercado Pago). Eles ficam só nos secrets do projeto Supabase.
- Arquivos `.env`, chaves de assinatura do Android (`*.keystore`, `*.jks`) e certificados.
- O banco local do app (`daily_quest.db`), que guarda a sessão de quem usa.

## Como os dados ficam protegidos

- **Row Level Security** em todas as tabelas: cada conta só lê e grava as próprias linhas. As tabelas anônimas (relato de crash e telemetria de retenção) só aceitam `INSERT`, ninguém lê pela chave pública, e o banco limita o tamanho e o formato do que entra.
- **Backups na nuvem** num bucket privado, um arquivo por conta. A sessão de login é removida do arquivo antes de exportar ou subir.
- **Links do e-mail** (login, senha nova): o app só aceita o link do e-mail que o próprio aparelho pediu, uma vez só, porque qualquer app ou página consegue abrir um `discipliner://`.
- **Apagar conta** exige um código novo enviado por e-mail; a Edge Function só aceita uma sessão confirmada por código nos últimos 10 minutos.
- **Pagamentos** são confirmados no servidor: os webhooks validam a assinatura (Stripe) ou buscam o pagamento de novo na API (Mercado Pago), com idempotência.
- **Relato de crash e telemetria** são anônimos: só um identificador aleatório de instalação, nunca e-mail, nome ou conteúdo de missão.

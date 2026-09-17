// Apaga a conta de QUEM chama: backup na nuvem, compra vinculada e o usuário
// do Supabase Auth. Roda como Edge Function (não direto do app) porque apagar
// usuário exige a service_role, que nunca vai pro app.
//
// Deploy: supabase functions deploy delete-account
// (SUPABASE_URL/SUPABASE_ANON_KEY/SUPABASE_SERVICE_ROLE_KEY já vêm injetados.)
//
// Proteção contra apagar sem querer / com sessão roubada: não basta estar
// logado. O JWT tem que ter nascido de um CÓDIGO recém-digitado — o app pede o
// código por e-mail (/auth/v1/otp), a pessoa digita, o /auth/v1/verify devolve
// uma sessão nova com `amr: [{method: "otp", timestamp}]`, e é ESSA sessão que
// chama aqui. Sessão antiga (sem otp recente no amr) recebe 403. Ou seja: só
// apaga quem tem acesso ao e-mail da conta, agora.
//
// verify_jwt LIGADO: a assinatura do token é checada antes do código rodar.

import { createClient } from "npm:@supabase/supabase-js@2";

const JANELA_SEGUNDOS = 10 * 60; // o código tem que ter sido confirmado há no máximo 10 min

function claimsDoJwt(token: string): Record<string, unknown> {
  const meio = token.split(".")[1] ?? "";
  const base64 = meio.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(meio.length / 4) * 4, "=");
  return JSON.parse(atob(base64));
}

Deno.serve(async (req) => {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) {
    return new Response("sem autenticação", { status: 401 });
  }

  // QUEM está chamando sai do próprio JWT — nunca de um user_id no corpo
  const supabaseUser = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: authHeader } } },
  );
  const { data: { user }, error: authError } = await supabaseUser.auth.getUser();
  if (authError || !user) {
    return new Response("token inválido", { status: 401 });
  }

  let claims: Record<string, unknown>;
  try {
    claims = claimsDoJwt(authHeader.replace(/^Bearer\s+/i, ""));
  } catch {
    return new Response("token ilegível", { status: 401 });
  }
  const agora = Math.floor(Date.now() / 1000);
  const amr = Array.isArray(claims.amr) ? claims.amr as Array<{ method?: string; timestamp?: number }> : [];
  const codigoRecente = amr.some((m) =>
    (m.method === "otp" || m.method === "magiclink") &&
    typeof m.timestamp === "number" && agora - m.timestamp <= JANELA_SEGUNDOS
  );
  if (!codigoRecente) {
    return new Response("confirme com o código enviado por e-mail", { status: 403 });
  }

  const admin = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  // backup na nuvem: a pasta inteira da pessoa (hoje 1 arquivo, daily_quest.db)
  const { data: arquivos } = await admin.storage.from("backups").list(user.id);
  if (arquivos && arquivos.length > 0) {
    const { error } = await admin.storage.from("backups").remove(arquivos.map((f) => `${user.id}/${f.name}`));
    if (error) {
      return new Response(`falha ao apagar o backup: ${error.message}`, { status: 500 });
    }
  }

  // compra vinculada (a FK com on delete cascade também cuidaria disso, mas
  // explícito não depende de como a tabela foi criada no projeto)
  await admin.from("purchases").delete().eq("user_id", user.id);

  const { error: deleteError } = await admin.auth.admin.deleteUser(user.id);
  if (deleteError) {
    return new Response(`falha ao apagar a conta: ${deleteError.message}`, { status: 500 });
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
});

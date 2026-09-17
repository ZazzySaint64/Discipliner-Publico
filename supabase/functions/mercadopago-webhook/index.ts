// Webhook do Mercado Pago — igual em espírito ao stripe-webhook (única
// coisa com permissão de escrever "comprei" na tabela purchases). O
// Mercado Pago só manda o ID do pagamento na notificação, não o status —
// por isso SEMPRE rebusca o pagamento de verdade na API deles com o access
// token antes de confiar em qualquer coisa (a notificação em si não é
// assinada, dá pra forjar; buscar de volta com o token secreto não dá).
//
// Deploy: supabase functions deploy mercadopago-webhook
// Configura em Mercado Pago > Sua aplicação > Webhooks: URL = a que o
// deploy imprimir, evento "payments".
//
// verify_jwt = false pra essa function (ver supabase/config.toml) — o
// Mercado Pago não manda o cabeçalho de autenticação do Supabase.

import { createClient } from "npm:@supabase/supabase-js@2";

const MP_ACCESS_TOKEN = Deno.env.get("MERCADOPAGO_ACCESS_TOKEN")!;
const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

async function releaseClaim(eventId: string) {
  await supabase.from("webhook_events")
    .delete().match({ provider: "mercadopago", event_id: eventId });
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  let paymentId = url.searchParams.get("data.id") || url.searchParams.get("id");
  if (!paymentId) {
    try {
      const body = await req.json();
      paymentId = body?.data?.id ?? null;
    } catch {
      // corpo vazio — o Mercado Pago às vezes só manda pela query string mesmo
    }
  }
  if (!paymentId) {
    return new Response("sem id de pagamento", { status: 400 });
  }

  const resp = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { "Authorization": `Bearer ${MP_ACCESS_TOKEN}` },
  });
  if (!resp.ok) {
    console.error(`Mercado Pago: não achou o pagamento ${paymentId}`);
    return new Response("pagamento não encontrado", { status: 404 });
  }
  const payment = await resp.json();

  // Só age no pagamento APROVADO. O MP manda notificação a cada mudança de
  // estado (pending -> approved -> ...); as outras a gente só confirma e
  // ignora — por isso a marca de idempotência (webhook_events) só é gravada
  // aqui dentro, depois de aprovado, senão a notificação "pending" travaria
  // a "approved" como duplicada.
  if (payment.status !== "approved") {
    return new Response("pagamento não aprovado — ignorado", { status: 200 });
  }

  // external_reference = user_id do Supabase, anexado na criação do
  // pagamento (ver create-pix-payment/index.ts)
  const userId = payment.external_reference;
  if (!userId) {
    const dead = await supabase.from("unmatched_purchases").insert({
      provider: "mercadopago",
      reason: "pagamento aprovado sem external_reference",
      payload: payment as Record<string, unknown>,
    });
    if (dead.error) {
      console.error("falha ao registrar unmatched_purchases:", dead.error);
      return new Response("erro ao registrar pagamento sem dono", { status: 500 });
    }
    console.error("PAGAMENTO NÃO ATRIBUÍDO (mercadopago):", payment.id, "— conciliar manualmente");
    return new Response("pago mas sem dono — registrado pra conciliação", { status: 200 });
  }

  // Idempotência: dedup pelo id do pagamento aprovado. PK repetida (23505) =
  // já creditado numa notificação anterior.
  const claim = await supabase.from("webhook_events")
    .insert({ provider: "mercadopago", event_id: String(payment.id) });
  if (claim.error) {
    if (claim.error.code === "23505") {
      return new Response("pagamento já processado", { status: 200 });
    }
    console.error("webhook_events insert falhou:", claim.error);
    return new Response("erro de idempotência", { status: 500 });
  }

  const { error } = await supabase.from("purchases").upsert({
    user_id: userId,
    entitlement: "premium",
    provider: "mercadopago",
    purchase_token: String(payment.id),
    purchased_at: new Date().toISOString(),
  }, { onConflict: "user_id" });
  if (error) {
    console.error(error);
    await releaseClaim(String(payment.id));
    return new Response("erro ao gravar a compra", { status: 500 });
  }

  return new Response("ok", { status: 200 });
});

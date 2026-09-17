// Webhook do Stripe — a única coisa no sistema com permissão de escrever
// "comprei" na tabela purchases (usa a service_role key, que só existe aqui
// dentro, nunca no app). O app nunca escreve status de compra direto: dá
// pra forjar client-side, aqui não, porque exige a assinatura do Stripe.
//
// Deploy: supabase functions deploy stripe-webhook
// Segredos (uma vez só): supabase secrets set STRIPE_SECRET_KEY=sk_... STRIPE_WEBHOOK_SECRET=whsec_...
// (SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY já vêm injetados automaticamente
// pelo runtime das Edge Functions — não precisa setar esses dois.)
//
// Depois do deploy, cria o endpoint em Stripe Dashboard > Developers > Webhooks,
// apontando pra URL que o "supabase functions deploy" imprimir, ouvindo o
// evento "checkout.session.completed" — daí o Stripe te dá o STRIPE_WEBHOOK_SECRET.
//
// QUANDO FOR PRA PLAY STORE: o Google Play Billing substitui o Payment Link do
// Stripe (cartão). Aí é só criar um play-billing-webhook que valida a compra
// com a Play Developer API e faz o MESMO upsert em `purchases` com
// provider='play'. Nada aqui nem em account.sync_premium_status muda — o que
// define Premium é EXISTIR a linha em purchases, não como pagou.

import Stripe from "npm:stripe@17";
import { createClient } from "npm:@supabase/supabase-js@2";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, {
  apiVersion: "2024-06-20",
});
const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET")!;
const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// App pequeno: varrer a lista de usuários pra achar um por e-mail resolve. Só
// é usado no fallback (link aberto sem client_reference_id). Se um dia a base
// crescer, trocar por uma query direta em auth.users.
async function findUserIdByEmail(email: string): Promise<string | null> {
  const target = email.trim().toLowerCase();
  for (let page = 1; page <= 20; page++) {
    const { data, error } = await supabase.auth.admin.listUsers({ page, perPage: 1000 });
    if (error || !data?.users?.length) return null;
    const hit = data.users.find((u) => (u.email ?? "").toLowerCase() === target);
    if (hit) return hit.id;
    if (data.users.length < 1000) return null;
  }
  return null;
}

// Libera a marca de idempotência pra o próximo retry do Stripe re-processar.
// Só é chamado nos caminhos que devolvem 5xx (falha transitória de banco).
async function releaseClaim(eventId: string) {
  await supabase.from("webhook_events")
    .delete().match({ provider: "stripe", event_id: eventId });
}

Deno.serve(async (req) => {
  const signature = req.headers.get("stripe-signature");
  if (!signature) {
    return new Response("sem cabeçalho stripe-signature", { status: 400 });
  }
  const body = await req.text();

  let event: Stripe.Event;
  try {
    // versão "Async" de propósito: o Deno não tem a API de crypto síncrona
    // que o SDK do Stripe usa por padrão no Node
    event = await stripe.webhooks.constructEventAsync(body, signature, webhookSecret);
  } catch (err) {
    return new Response(`Assinatura inválida: ${(err as Error).message}`, { status: 400 });
  }

  // Idempotência: o Stripe reenvia o MESMO evento (retry automático, ou
  // "Resend" no painel). Grava o id ANTES de processar; PK repetida (23505) =
  // re-entrega → confirma e sai. Se o processamento abaixo falhar com 5xx, a
  // marca é liberada (releaseClaim) pra o retry funcionar.
  const claim = await supabase.from("webhook_events")
    .insert({ provider: "stripe", event_id: event.id });
  if (claim.error) {
    if (claim.error.code === "23505") {
      return new Response("evento já processado", { status: 200 });
    }
    console.error("webhook_events insert falhou:", claim.error);
    return new Response("erro de idempotência", { status: 500 });
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;

    // Só credita compra ÚNICA e EFETIVAMENTE PAGA. checkout.session.completed
    // também dispara pra mode="subscription" e pode chegar com payment_status
    // != "paid" (métodos assíncronos, ou estados intermediários de cartão).
    if (session.mode !== "payment" || session.payment_status !== "paid") {
      return new Response("sessão não é compra única paga — ignorada", { status: 200 });
    }

    // client_reference_id = user_id do Supabase, anexado pelo app ao abrir o
    // link (ver account.open_purchase_page).
    let userId: string | null = session.client_reference_id ?? null;

    // Fallback: link aberto "pelado" (vazado, ou o app falhou em anexar o
    // param). Tenta pelo e-mail do checkout antes de desistir.
    if (!userId) {
      const email = session.customer_details?.email ?? session.customer_email ?? null;
      userId = email ? await findUserIdByEmail(email) : null;
    }

    if (!userId) {
      // Pago, mas sem como saber de quem é: NÃO some calado — registra pra
      // conciliação manual. Se nem isso gravar, devolve 5xx pra o Stripe
      // reenviar (pode gravar na próxima).
      const dead = await supabase.from("unmatched_purchases").insert({
        provider: "stripe",
        reason: "sem client_reference_id e e-mail não bateu com nenhum usuário",
        payload: session as unknown as Record<string, unknown>,
      });
      if (dead.error) {
        console.error("falha ao registrar unmatched_purchases:", dead.error);
        await releaseClaim(event.id);
        return new Response("erro ao registrar pagamento sem dono", { status: 500 });
      }
      console.error("PAGAMENTO NÃO ATRIBUÍDO (stripe):", session.id, "— conciliar manualmente");
      return new Response("pago mas sem dono — registrado pra conciliação", { status: 200 });
    }

    const paymentIntent = typeof session.payment_intent === "string"
      ? session.payment_intent
      : null;

    const { error } = await supabase.from("purchases").upsert({
      user_id: userId,
      entitlement: "premium",
      provider: "stripe",
      purchase_token: session.id,
      payment_intent: paymentIntent,
      purchased_at: new Date().toISOString(),
    }, { onConflict: "user_id" });
    if (error) {
      console.error(error);
      await releaseClaim(event.id);
      return new Response("erro ao gravar a compra", { status: 500 });
    }
  }

  return new Response("ok", { status: 200 });
});

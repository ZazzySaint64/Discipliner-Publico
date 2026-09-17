// Cria uma preferência de Checkout Pro (Mercado Pago) pro Premium via Pix —
// devolve a URL de checkout hospedada pelo Mercado Pago pro app abrir no
// navegador (mesmo padrão do Stripe, ver account.open_purchase_page). Roda
// como Edge Function (não direto do app) porque precisa do
// MERCADOPAGO_ACCESS_TOKEN, que é secreto (equivalente à
// service_role/STRIPE_SECRET_KEY: nunca no app).
//
// Deploy: supabase functions deploy create-pix-payment
// Segredo (uma vez só): supabase secrets set MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
// (SUPABASE_URL/SUPABASE_ANON_KEY já vêm injetados automaticamente.)
//
// Checkout Pro em vez de POST /v1/payments direto: essa aplicação não está
// homologada pro Checkout API (chamada direta), só pro Checkout Pro
// (redirecionamento) — ver "Qualidade da integração" no painel do MP.
// Chamar /v1/payments sem homologação dá "Unauthorized use of live
// credentials". Checkout Pro não passa por essa exigência.
//
// verify_jwt continua LIGADO (padrão) de propósito — só usuário logado no
// app pode pedir uma preferência nova, diferente do mercadopago-webhook
// (esse sim precisa ficar público, é o Mercado Pago quem chama).

import { createClient } from "npm:@supabase/supabase-js@2";

const MP_ACCESS_TOKEN = Deno.env.get("MERCADOPAGO_ACCESS_TOKEN")!;
// preço do Premium em Real — ajusta aqui se o valor em dólar mudar
// (ver account.py > STRIPE_PAYMENT_LINK_USD, hoje US$ 3)
const PREMIUM_PRICE_BRL = 15.0;

// só Pix passa (exclui os outros meios do Checkout Pro) — o botão "Pix" no
// app precisa continuar significando Pix, o "Cartão" já é o Stripe
const NON_PIX_PAYMENT_TYPES = [
  "credit_card", "debit_card", "prepaid_card", "ticket",
  "atm", "digital_currency", "digital_wallet", "voucher_card",
].map((id) => ({ id }));

Deno.serve(async (req) => {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) {
    return new Response("sem autenticação", { status: 401 });
  }

  // resolve QUEM está chamando a partir do próprio JWT dele — nunca confia
  // em nenhum "user_id" que o corpo da requisição possa mandar
  const supabaseUser = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: authHeader } } },
  );
  const { data: { user }, error: authError } = await supabaseUser.auth.getUser();
  if (authError || !user) {
    return new Response("token inválido", { status: 401 });
  }

  const resp = await fetch("https://api.mercadopago.com/checkout/preferences", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${MP_ACCESS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      items: [{
        title: "Discipliner Premium",
        quantity: 1,
        currency_id: "BRL",
        unit_price: PREMIUM_PRICE_BRL,
      }],
      external_reference: user.id,
      payer: { email: user.email },
      payment_methods: { excluded_payment_types: NON_PIX_PAYMENT_TYPES },
    }),
  });
  const preference = await resp.json();
  if (!resp.ok) {
    // só status/mensagem: a resposta inteira pode trazer payer.email
    console.error("Mercado Pago recusou a preferência:", resp.status, preference.message);
    return new Response(
      JSON.stringify({ error: preference.message || "falha ao criar o checkout" }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  return new Response(
    JSON.stringify({ checkout_url: preference.init_point }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
});

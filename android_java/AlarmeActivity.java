package com.zazzysaint.dailyquest;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Vibrator;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

// Tela do alarme de missão — o "despertador" do app.
//
// Por que Java e não uma tela Kivy: o alarme precisa ACENDER a tela e passar
// por cima do bloqueio no instante em que dispara. Uma tela Kivy só existe
// depois de o Python subir (vários segundos) e, com o aparelho dormindo, a
// PythonActivity nem chega a rodar o Kivy — testado no emulador: o app era
// aberto pelo alarme e ficava parado, sem tela e sem som. Aqui é tudo nativo:
// showWhenLocked/turnScreenOn já no onCreate, toque e vibração na hora.
//
// Quem abre: android_alarm.abrir_tela_alarme (serviço, com o app fechado; ou o
// próprio app aberto). Os textos já vêm traduzidos nos extras. p4a_hooks.py
// copia este arquivo pro projeto gerado, e android_manifest_extra.xml declara
// a <activity>.
public class AlarmeActivity extends Activity {
    private static final long TETO_MS = 5 * 60 * 1000;  // não toca pra sempre se ninguém encerrar
    private static final int FUNDO = Color.rgb(18, 18, 18);
    private static final int VERDE = Color.rgb(158, 184, 89);
    private static final int VERMELHO = Color.rgb(217, 102, 117);

    private Ringtone toque;
    private Vibrator vibrador;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView horario;
    private TextView missao;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        } else {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(montar());
        preencher(getIntent());
        tocar();
        handler.postDelayed(new Runnable() {
            public void run() {
                encerrar();
            }
        }, TETO_MS);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        // outro alarme disparou com esta tela aberta: mostra o novo, sem
        // empilhar um segundo toque
        super.onNewIntent(intent);
        setIntent(intent);
        preencher(intent);
    }

    @Override
    public void onBackPressed() {
        encerrar();
    }

    @Override
    protected void onDestroy() {
        parar();
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private View montar() {
        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        raiz.setGravity(Gravity.CENTER_HORIZONTAL);
        raiz.setBackgroundColor(FUNDO);
        raiz.setPadding(dp(28), dp(56), dp(28), dp(36));

        horario = texto(68, VERDE, true);
        raiz.addView(horario, largura(LinearLayout.LayoutParams.WRAP_CONTENT));

        TextView titulo = texto(18, Color.rgb(178, 178, 178), false);
        titulo.setText(extra("titulo", ""));
        raiz.addView(titulo, largura(LinearLayout.LayoutParams.WRAP_CONTENT));

        ImageView focum = new ImageView(this);
        int imagem = getResources().getIdentifier("focum_alarm", "drawable", getPackageName());
        if (imagem != 0) {
            focum.setImageResource(imagem);
        }
        focum.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams espaco = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        espaco.topMargin = dp(12);
        espaco.bottomMargin = dp(12);
        raiz.addView(focum, espaco);

        missao = texto(32, Color.rgb(242, 242, 242), true);
        raiz.addView(missao, largura(LinearLayout.LayoutParams.WRAP_CONTENT));

        Button botao = new Button(this);
        botao.setText(extra("botao", "OK"));
        botao.setAllCaps(false);
        botao.setTextColor(Color.WHITE);
        botao.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        botao.setTypeface(Typeface.DEFAULT_BOLD);
        GradientDrawable fundoBotao = new GradientDrawable();
        fundoBotao.setColor(VERMELHO);
        fundoBotao.setCornerRadius(dp(14));
        botao.setBackground(fundoBotao);
        botao.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                encerrar();
            }
        });
        LinearLayout.LayoutParams parametrosBotao = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(64));
        parametrosBotao.topMargin = dp(24);
        raiz.addView(botao, parametrosBotao);
        return raiz;
    }

    private void preencher(Intent intent) {
        horario.setText(intent.getStringExtra("horario"));
        missao.setText(intent.getStringExtra("nome"));
        // aberta pela notificação de alarme (plano B, sem "sobrepor a outros
        // apps"): cancela ela — o som insistente dela para e fica só o daqui
        int notifId = intent.getIntExtra("notif_id", -1);
        if (notifId >= 0) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.cancel(notifId);
            }
        }
    }

    private void tocar() {
        try {
            Uri som = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (som == null) {
                som = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            }
            toque = RingtoneManager.getRingtone(this, som);
            if (toque != null) {
                // volume de ALARME: toca mesmo com o celular no silencioso
                toque.setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build());
                if (Build.VERSION.SDK_INT >= 28) {
                    toque.setLooping(true);
                }
                toque.play();
            }
        } catch (Exception e) {
            // sem som ainda sobra a tela e a vibração
        }
        try {
            vibrador = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (vibrador != null) {
                vibrador.vibrate(new long[] {0, 700, 500}, 0);
            }
        } catch (Exception e) {
            vibrador = null;
        }
    }

    private void parar() {
        if (toque != null) {
            toque.stop();
            toque = null;
        }
        if (vibrador != null) {
            vibrador.cancel();
            vibrador = null;
        }
    }

    private void encerrar() {
        parar();
        // plano B do serviço (sem permissão de sobreposição) toca de lá; o
        // encerrar daqui derruba ele também
        try {
            stopService(new Intent().setClassName(getPackageName(), getPackageName() + ".ServiceReminder"));
        } catch (Exception e) {
            // não estava rodando
        }
        finish();
    }

    private String extra(String chave, String padrao) {
        String valor = getIntent().getStringExtra(chave);
        return valor != null ? valor : padrao;
    }

    private TextView texto(int sp, int cor, boolean negrito) {
        TextView t = new TextView(this);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(cor);
        t.setGravity(Gravity.CENTER);
        if (negrito) {
            t.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return t;
    }

    private LinearLayout.LayoutParams largura(int altura) {
        return new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, altura);
    }

    private int dp(int valor) {
        return Math.round(valor * getResources().getDisplayMetrics().density);
    }
}

package com.zazzysaint.dailyquest;

import android.app.Activity;

import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.LoadAdError;
import com.google.android.gms.ads.interstitial.InterstitialAd;
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback;

// Ponte mínima pro intersticial do AdMob. Só isto precisa ser Java: o callback
// de load do SDK atual (InterstitialAdLoadCallback) é uma CLASSE ABSTRATA, e o
// pyjnius só implementa interfaces. Banner e consentimento (UMP) ficam em
// ads.py, pyjnius puro. p4a_hooks.py copia este arquivo pro projeto gerado.
public class AdMobBridge {
    private static InterstitialAd sAd = null;
    private static boolean sLoading = false;

    public static void loadInterstitial(final Activity activity, final String adUnitId) {
        if (sAd != null || sLoading) {
            return;
        }
        sLoading = true;
        activity.runOnUiThread(new Runnable() {
            public void run() {
                InterstitialAd.load(
                    activity, adUnitId, new AdRequest.Builder().build(),
                    new InterstitialAdLoadCallback() {
                        @Override
                        public void onAdLoaded(InterstitialAd ad) {
                            sAd = ad;
                            sLoading = false;
                        }

                        @Override
                        public void onAdFailedToLoad(LoadAdError error) {
                            sAd = null;
                            sLoading = false;
                        }
                    });
            }
        });
    }

    public static void showInterstitial(final Activity activity, final String adUnitId) {
        activity.runOnUiThread(new Runnable() {
            public void run() {
                if (sAd != null) {
                    sAd.show(activity);
                    sAd = null;
                }
                loadInterstitial(activity, adUnitId);  // já deixa o próximo carregando
            }
        });
    }
}

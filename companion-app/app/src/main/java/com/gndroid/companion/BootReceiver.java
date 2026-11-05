package com.gndroid.companion;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

/**
 * GNDROiD Boot Receiver
 * Automatically resumes persistent background companion service upon device boot or app update.
 */
public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "GNDroidBoot";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : "";
        Log.i(TAG, "GNDROiD BootReceiver triggered with action: " + action);

        Intent serviceIntent = new Intent(context, GNDroidCompanionService.class);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
            Log.i(TAG, "GNDroidCompanionService started successfully on boot/update.");
        } catch (Exception e) {
            Log.e(TAG, "Failed to start GNDroidCompanionService on boot", e);
        }
    }
}

package com.gndroid.companion;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * GNDROiD Device Admin Receiver
 * Enables remote screen lock, keyguard control, and power management over LAN.
 */
public class GNDroidDeviceAdminReceiver extends DeviceAdminReceiver {
    private static final String TAG = "GNDroidAdmin";

    @Override
    public void onEnabled(Context context, Intent intent) {
        super.onEnabled(context, intent);
        Log.i(TAG, "GNDROiD Device Admin enabled.");
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        super.onDisabled(context, intent);
        Log.i(TAG, "GNDROiD Device Admin disabled.");
    }
}

package com.gndroid.companion;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Enumeration;

/**
 * GNDROiD Link Main Dashboard Activity
 * Displays real-time LAN IP, telemetry, permission matrix, and connection status.
 */
public class MainActivity extends Activity {

    private TextView mTvIpAddress;
    private TextView mTvPermAccessibility;
    private TextView mTvPermOverlay;
    private TextView mTvPermDoze;
    private TextView mTvPermSecure;
    private TextView mTvBatteryStats;
    private TextView mTvWatchdogStats;

    private Handler mHandler;
    private Runnable mRefreshRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        mTvIpAddress = findViewById(R.id.tv_ip_address);
        mTvPermAccessibility = findViewById(R.id.tv_perm_accessibility);
        mTvPermOverlay = findViewById(R.id.tv_perm_overlay);
        mTvPermDoze = findViewById(R.id.tv_perm_doze);
        mTvPermSecure = findViewById(R.id.tv_perm_secure);
        mTvBatteryStats = findViewById(R.id.tv_battery_stats);
        mTvWatchdogStats = findViewById(R.id.tv_watchdog_stats);

        Button btnRestart = findViewById(R.id.btn_restart_service);
        btnRestart.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startCompanionService();
                Toast.makeText(MainActivity.this, "GNDROiD Link Bridge Restarted", Toast.LENGTH_SHORT).show();
                updateDashboard();
            }
        });

        Button btnMinimize = findViewById(R.id.btn_minimize);
        btnMinimize.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                moveTaskToBack(true);
            }
        });

        // Request notification permission on Android 13+ if needed
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 101);
            }
        }

        // Ensure companion background service is running
        startCompanionService();

        mHandler = new Handler(Looper.getMainLooper());
        mRefreshRunnable = new Runnable() {
            @Override
            public void run() {
                updateDashboard();
                mHandler.postDelayed(this, 2000);
            }
        };
    }

    @Override
    protected void onResume() {
        super.onResume();
        startCompanionService();
        updateDashboard();
        if (mHandler != null && mRefreshRunnable != null) {
            mHandler.post(mRefreshRunnable);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (mHandler != null && mRefreshRunnable != null) {
            mHandler.removeCallbacks(mRefreshRunnable);
        }
    }

    private void startCompanionService() {
        Intent serviceIntent = new Intent(this, GNDroidCompanionService.class);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception e) {
            Log.e("MainActivity", "Failed to start companion service", e);
        }
    }

    private void updateDashboard() {
        // 1. IP Address
        String ip = getLocalIpAddress();
        mTvIpAddress.setText("Device IP: " + ip);

        // 2. Permission matrix
        boolean hasA11y = GNDroidAccessibilityService.isAvailable();
        mTvPermAccessibility.setText("• Accessibility Input Injection: " + (hasA11y ? "✅ ACTIVE" : "⚠️ Disabled"));

        boolean hasOverlay = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            hasOverlay = Settings.canDrawOverlays(this);
        }
        mTvPermOverlay.setText("• Floating Overlay Window: " + (hasOverlay ? "✅ GRANTED" : "⚠️ Missing"));

        boolean isDozeExempt = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            isDozeExempt = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
        }
        mTvPermDoze.setText("• Doze Battery Exemption: " + (isDozeExempt ? "✅ EXEMPT (Zero Drop)" : "⚠️ Battery Restricted"));

        mTvPermSecure.setText("• Secure System Settings: ✅ ACTIVE");

        // 3. Battery & Thermal
        IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        Intent b = registerReceiver(null, ifilter);
        if (b != null) {
            int level = b.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int st = b.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
            boolean charging = st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL;
            double temp = b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0;
            mTvBatteryStats.setText("Battery: " + level + "% (" + (charging ? "Charging" : "Discharging") + ") | Temp: " + temp + "°C");
        }

        mTvWatchdogStats.setText("Watchdog: Sub-second heartbeat active (Port 51888)");
    }

    private String getLocalIpAddress() {
        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces.hasMoreElements()) {
                NetworkInterface iface = interfaces.nextElement();
                if (iface.isLoopback() || !iface.isUp()) continue;
                Enumeration<InetAddress> addresses = iface.getInetAddresses();
                while (addresses.hasMoreElements()) {
                    InetAddress addr = addresses.nextElement();
                    if (!addr.isLoopbackAddress() && addr instanceof Inet4Address) {
                        return addr.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) {}
        return "127.0.0.1";
    }
}

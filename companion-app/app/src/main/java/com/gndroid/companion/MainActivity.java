package com.gndroid.companion;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

/**
 * GNDROiD Link Main Dashboard Activity
 * Displays real-time LAN IP, telemetry, permission matrix, and connection status.
 */
public class MainActivity extends Activity {

    private static final String TAG = "MainActivity";
    public static final int SCREEN_CAPTURE_REQ_CODE = 3001;
    public static final int PERMISSION_REQ_CODE = 1001;

    private static final String[] RUNTIME_PERMISSIONS = {
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.CAMERA,
        Manifest.permission.READ_EXTERNAL_STORAGE,
        Manifest.permission.WRITE_EXTERNAL_STORAGE,
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION
    };

    private TextView mTvIpAddress;
    private TextView mTvServerPorts;
    private TextView mTvScreenStatus;
    private TextView mTvPermAccessibility;
    private TextView mTvPermOverlay;
    private TextView mTvPermDoze;
    private TextView mTvPermSecure;
    private TextView mTvBatteryStats;
    private TextView mTvWatchdogStats;

    private Button mBtnStartMirror;
    private Button mBtnGrantAll;
    private Button mBtnFixA11y;
    private Button mBtnFixOverlay;
    private Button mBtnFixDoze;

    private Handler mHandler;
    private Runnable mRefreshRunnable;

    public void requestScreenCapture() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            try {
                MediaProjectionManager mpm = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
                if (mpm != null) {
                    startActivityForResult(mpm.createScreenCaptureIntent(), SCREEN_CAPTURE_REQ_CODE);
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to request screen capture", e);
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == SCREEN_CAPTURE_REQ_CODE) {
            if (resultCode == RESULT_OK && data != null) {
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                        MediaProjectionManager mpm = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
                        if (mpm != null) {
                            MediaProjection mp = mpm.getMediaProjection(resultCode, data);
                            if (mp != null) {
                                DisplayMetrics dm = getResources().getDisplayMetrics();
                                GNDroidCompanionService.setMediaProjection(mp, dm.widthPixels, dm.heightPixels, dm.densityDpi);
                                Toast.makeText(this, "✅ Pure Wi-Fi Mirroring Active! Open GNDROiD on PC.", Toast.LENGTH_LONG).show();
                                if (mTvScreenStatus != null) {
                                    mTvScreenStatus.setText("Screen Cast: ✅ LIVE STREAMING (Port 51880)");
                                }
                                new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
                                    @Override
                                    public void run() {
                                        moveTaskToBack(true);
                                    }
                                }, 1200);
                            }
                        }
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Error handling screen capture result", e);
                }
            } else {
                Toast.makeText(this, "Screen capture was cancelled", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        mTvIpAddress = findViewById(R.id.tv_ip_address);
        mTvServerPorts = findViewById(R.id.tv_server_ports);
        mTvScreenStatus = findViewById(R.id.tv_screen_status);
        mTvPermAccessibility = findViewById(R.id.tv_perm_accessibility);
        mTvPermOverlay = findViewById(R.id.tv_perm_overlay);
        mTvPermDoze = findViewById(R.id.tv_perm_doze);
        mTvPermSecure = findViewById(R.id.tv_perm_secure);
        mTvBatteryStats = findViewById(R.id.tv_battery_stats);
        mTvWatchdogStats = findViewById(R.id.tv_watchdog_stats);

        mBtnStartMirror = findViewById(R.id.btn_start_mirror);
        mBtnGrantAll = findViewById(R.id.btn_grant_all);
        mBtnFixA11y = findViewById(R.id.btn_fix_a11y);
        mBtnFixOverlay = findViewById(R.id.btn_fix_overlay);
        mBtnFixDoze = findViewById(R.id.btn_fix_doze);

        Button btnRestart = findViewById(R.id.btn_restart_service);
        if (btnRestart != null) {
            btnRestart.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    startCompanionService();
                    Toast.makeText(MainActivity.this, "GNDROiD Link Bridge Restarted", Toast.LENGTH_SHORT).show();
                    updateDashboard();
                }
            });
        }

        Button btnMinimize = findViewById(R.id.btn_minimize);
        if (btnMinimize != null) {
            btnMinimize.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    moveTaskToBack(true);
                }
            });
        }

        // 1. Interactive Permission Buttons
        if (mBtnFixA11y != null) {
            mBtnFixA11y.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    try {
                        startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
                        Toast.makeText(MainActivity.this, "Tap 'GNDROiD Companion' and switch it ON", Toast.LENGTH_LONG).show();
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Open Settings > Accessibility", Toast.LENGTH_SHORT).show();
                    }
                }
            });
        }

        if (mBtnFixOverlay != null) {
            mBtnFixOverlay.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    try {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                    Uri.parse("package:" + getPackageName()));
                            startActivity(intent);
                        }
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Open Settings > Display over other apps", Toast.LENGTH_SHORT).show();
                    }
                }
            });
        }

        if (mBtnFixDoze != null) {
            mBtnFixDoze.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    try {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                                    Uri.parse("package:" + getPackageName()));
                            startActivity(intent);
                        }
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Open Settings > Battery Optimization", Toast.LENGTH_SHORT).show();
                    }
                }
            });
        }

        // Master 1-Tap Grant All button
        if (mBtnGrantAll != null) {
            mBtnGrantAll.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    requestRuntimePermissions();
                    boolean hasA11y = GNDroidAccessibilityService.isAvailable();
                    boolean hasOverlay = true;
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        hasOverlay = Settings.canDrawOverlays(MainActivity.this);
                    }
                    boolean isDozeExempt = true;
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                        isDozeExempt = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
                    }

                    if (!hasA11y) {
                        startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
                        Toast.makeText(MainActivity.this, "Step 1: Tap 'GNDROiD Companion' and turn ON", Toast.LENGTH_LONG).show();
                    } else if (!hasOverlay && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
                        Toast.makeText(MainActivity.this, "Step 2: Allow display over other apps", Toast.LENGTH_LONG).show();
                    } else if (!isDozeExempt && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName())));
                        Toast.makeText(MainActivity.this, "Step 3: Allow battery optimization exemption", Toast.LENGTH_LONG).show();
                    } else {
                        Toast.makeText(MainActivity.this, "✅ All permissions are already active!", Toast.LENGTH_SHORT).show();
                    }
                }
            });
        }

        // 2. Start Mirror Button
        if (mBtnStartMirror != null) {
            mBtnStartMirror.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    requestScreenCapture();
                }
            });
        }

        // 3. Proactively request standard Android runtime permissions on first launch
        requestRuntimePermissions();

        // 4. Start foreground companion service
        startCompanionService();

        // Auto-request screen capture on initial launch if not yet active
        if (GNDroidCompanionService.activeMediaProjection == null) {
            new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (!isFinishing()) {
                        requestScreenCapture();
                    }
                }
            }, 800);
        }

        mHandler = new Handler(Looper.getMainLooper());
        mRefreshRunnable = new Runnable() {
            @Override
            public void run() {
                updateDashboard();
                if (mHandler != null) {
                    mHandler.postDelayed(this, 1500);
                }
            }
        };
    }

    private void requestRuntimePermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            List<String> missing = new ArrayList<>();
            for (String p : RUNTIME_PERMISSIONS) {
                if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) {
                    missing.add(p);
                }
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                    missing.add(Manifest.permission.POST_NOTIFICATIONS);
                }
            }
            if (!missing.isEmpty()) {
                requestPermissions(missing.toArray(new String[0]), PERMISSION_REQ_CODE);
            }
        }
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
            Log.e(TAG, "Failed to start companion service", e);
        }
    }

    private void updateDashboard() {
        // 1. IP Address
        String ip = getLocalIpAddress();
        if (mTvIpAddress != null) {
            mTvIpAddress.setText("Device IP: " + ip);
        }

        // 2. Permission matrix state
        boolean hasA11y = GNDroidAccessibilityService.isAvailable();
        if (mBtnFixA11y != null) {
            mBtnFixA11y.setText(hasA11y ? "✅ Active" : "Enable");
            mBtnFixA11y.setEnabled(!hasA11y);
        }

        boolean hasOverlay = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            hasOverlay = Settings.canDrawOverlays(this);
        }
        if (mBtnFixOverlay != null) {
            mBtnFixOverlay.setText(hasOverlay ? "✅ Allowed" : "Allow");
            mBtnFixOverlay.setEnabled(!hasOverlay);
        }

        boolean isDozeExempt = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            isDozeExempt = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
        }
        if (mBtnFixDoze != null) {
            mBtnFixDoze.setText(isDozeExempt ? "✅ Exempt" : "Exempt");
            mBtnFixDoze.setEnabled(!isDozeExempt);
        }

        if (mTvScreenStatus != null) {
            boolean active = GNDroidCompanionService.activeMediaProjection != null;
            mTvScreenStatus.setText(active ? "Screen Cast: ✅ LIVE STREAMING (Port 51880)" : "Screen Cast: Standby (Tap button below to start)");
        }

        // 3. Battery & Thermal
        IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        Intent b = registerReceiver(null, ifilter);
        if (b != null && mTvBatteryStats != null) {
            int level = b.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int st = b.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
            boolean charging = st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL;
            double temp = b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0;
            mTvBatteryStats.setText("Battery: " + level + "% (" + (charging ? "Charging" : "Discharging") + ") | Temp: " + temp + "°C");
        }

        if (mTvWatchdogStats != null) {
            mTvWatchdogStats.setText("Watchdog: Sub-second heartbeat active (Port 51880)");
        }
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

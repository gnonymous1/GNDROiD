package com.gndroid.companion;

import android.app.admin.DevicePolicyManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.StatFs;
import android.provider.Settings;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

/**
 * GNDROiD Embedded High-Performance LAN Remote Server
 * Operates on TCP port 51888. Provides sub-second heartbeat, navigation injection,
 * volume/power control, clipboard synchronization, line-speed direct file push,
 * and remote application launcher over local Wi-Fi.
 */
public class GNDroidRemoteServer {

    private static final String TAG = "GNDroidServer";
    public static final int PORT = 51888;

    private final Context mContext;
    private final Handler mMainHandler;
    private ServerSocket mServerSocket = null;
    private ExecutorService mThreadPool = null;
    private volatile boolean mRunning = false;

    public GNDroidRemoteServer(Context context) {
        mContext = context.getApplicationContext();
        mMainHandler = new Handler(Looper.getMainLooper());
    }

    public synchronized void start() {
        if (mRunning) return;
        mRunning = true;
        mThreadPool = Executors.newCachedThreadPool();

        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    mServerSocket = new ServerSocket(PORT);
                    mServerSocket.setReuseAddress(true);
                    Log.i(TAG, "GNDROiD Remote Server listening on TCP port " + PORT);

                    while (mRunning && !mServerSocket.isClosed()) {
                        try {
                            final Socket client = mServerSocket.accept();
                            client.setTcpNoDelay(true);
                            client.setSoTimeout(15000);
                            mThreadPool.execute(new Runnable() {
                                @Override
                                public void run() {
                                    handleClient(client);
                                }
                            });
                        } catch (Exception e) {
                            if (!mRunning) break;
                        }
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Server socket error on port " + PORT, e);
                }
            }
        }, "GNDroidRemoteServer-Acceptor").start();
    }

    public synchronized void stop() {
        mRunning = false;
        if (mServerSocket != null) {
            try {
                mServerSocket.close();
            } catch (Exception ignored) {}
            mServerSocket = null;
        }
        if (mThreadPool != null) {
            mThreadPool.shutdownNow();
            mThreadPool = null;
        }
        Log.i(TAG, "GNDROiD Remote Server stopped.");
    }

    private void handleClient(Socket socket) {
        try {
            InputStream in = new BufferedInputStream(socket.getInputStream());
            OutputStream out = new BufferedOutputStream(socket.getOutputStream());

            // Read HTTP request line & headers
            BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
            String reqLine = reader.readLine();
            if (reqLine == null || reqLine.isEmpty()) {
                socket.close();
                return;
            }

            String[] parts = reqLine.split(" ");
            if (parts.length < 2) {
                socket.close();
                return;
            }
            String method = parts[0].toUpperCase();
            String uri = parts[1];

            // Parse headers
            int contentLength = 0;
            String headerLine;
            String fileNameHeader = "";
            while ((headerLine = reader.readLine()) != null && !headerLine.isEmpty()) {
                String lower = headerLine.toLowerCase();
                if (lower.startsWith("content-length:")) {
                    try {
                        contentLength = Integer.parseInt(headerLine.substring(15).trim());
                    } catch (Exception ignored) {}
                } else if (lower.startsWith("x-filename:")) {
                    fileNameHeader = headerLine.substring(11).trim();
                }
            }

            // Route endpoints
            if ("OPTIONS".equals(method)) {
                sendResponse(out, 200, "application/json", "{\"status\": \"ok\"}");
                return;
            }

            if ("/".equals(uri) || "/index.html".equals(uri)) {
                try {
                    InputStream assetIn = mContext.getAssets().open("www/index.html");
                    ByteArrayOutputStream baos = new ByteArrayOutputStream();
                    byte[] b = new byte[4096];
                    int r;
                    while ((r = assetIn.read(b)) != -1) {
                        baos.write(b, 0, r);
                    }
                    assetIn.close();
                    sendResponse(out, 200, "text/html", baos.toString("UTF-8"));
                    return;
                } catch (Exception e) {
                    sendResponse(out, 200, "text/html", "<h1>GNDROiD Link Web Console</h1><p>Active</p>");
                    return;
                }
            }

            if (uri.startsWith("/ping")) {
                JSONObject res = new JSONObject();
                res.put("pong", true);
                res.put("timestamp", System.currentTimeMillis());
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            if (uri.startsWith("/status") || uri.startsWith("/api/v1/status")) {
                JSONObject res = buildStatusJson();
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            if (uri.startsWith("/api/v1/clipboard")) {
                if ("GET".equals(method)) {
                    String clipText = getClipboardSync();
                    JSONObject res = new JSONObject();
                    res.put("text", clipText != null ? clipText : "");
                    sendResponse(out, 200, "application/json", res.toString());
                } else if ("POST".equals(method)) {
                    String body = readBody(reader, contentLength);
                    JSONObject json = new JSONObject(body);
                    String text = json.optString("text", "");
                    setClipboardSync(text);
                    JSONObject res = new JSONObject();
                    res.put("success", true);
                    sendResponse(out, 200, "application/json", res.toString());
                }
                return;
            }

            if (uri.startsWith("/api/v1/control") && "POST".equals(method)) {
                String body = readBody(reader, contentLength);
                JSONObject json = new JSONObject(body);
                String action = json.optString("action", "");
                boolean ok = handleControlAction(action, json);
                JSONObject res = new JSONObject();
                res.put("success", ok);
                res.put("action", action);
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            if (uri.startsWith("/api/v1/apps") && "GET".equals(method)) {
                JSONObject res = listInstalledAppsJson();
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            if (uri.startsWith("/api/v1/launch_app") && "POST".equals(method)) {
                String body = readBody(reader, contentLength);
                JSONObject json = new JSONObject(body);
                String pkg = json.optString("package", "");
                boolean ok = launchApp(pkg);
                JSONObject res = new JSONObject();
                res.put("success", ok);
                res.put("package", pkg);
                sendResponse(out, ok ? 200 : 400, "application/json", res.toString());
                return;
            }

            if (uri.startsWith("/api/v1/upload") && "POST".equals(method)) {
                // Line-speed direct file upload over Wi-Fi
                String fname = fileNameHeader.isEmpty() ? "upload_" + System.currentTimeMillis() + ".dat" : fileNameHeader;
                File targetDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                if (targetDir == null || !targetDir.exists()) {
                    targetDir = mContext.getExternalFilesDir(null);
                }
                File targetFile = new File(targetDir, fname);
                FileOutputStream fos = new FileOutputStream(targetFile);

                char[] cbuf = new char[8192];
                int totalRead = 0;
                while (totalRead < contentLength) {
                    int toRead = Math.min(cbuf.length, contentLength - totalRead);
                    int r = reader.read(cbuf, 0, toRead);
                    if (r == -1) break;
                    byte[] bytes = new String(cbuf, 0, r).getBytes(StandardCharsets.ISO_8859_1);
                    fos.write(bytes);
                    totalRead += r;
                }
                fos.flush();
                fos.close();

                JSONObject res = new JSONObject();
                res.put("success", true);
                res.put("path", targetFile.getAbsolutePath());
                res.put("size", targetFile.length());
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            // Fallback 404
            sendResponse(out, 404, "application/json", "{\"error\": \"Not Found\"}");

        } catch (Exception e) {
            // Log.e(TAG, "Client handle exception", e);
        } finally {
            try {
                socket.close();
            } catch (Exception ignored) {}
        }
    }

    private String readBody(BufferedReader reader, int length) throws Exception {
        if (length <= 0) return "{}";
        char[] buf = new char[length];
        int read = 0;
        while (read < length) {
            int r = reader.read(buf, read, length - read);
            if (r == -1) break;
            read += r;
        }
        return new String(buf, 0, read);
    }

    private void sendResponse(OutputStream out, int code, String contentType, String body) throws Exception {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        String header = "HTTP/1.1 " + code + " OK\r\n" +
                "Content-Type: " + contentType + "; charset=utf-8\r\n" +
                "Content-Length: " + b.length + "\r\n" +
                "Access-Control-Allow-Origin: *\r\n" +
                "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n" +
                "Access-Control-Allow-Headers: Content-Type, X-Filename\r\n" +
                "Connection: close\r\n\r\n";
        out.write(header.getBytes(StandardCharsets.UTF_8));
        out.write(b);
        out.flush();
    }

    private boolean handleControlAction(String action, JSONObject params) {
        GNDroidAccessibilityService a11y = GNDroidAccessibilityService.getInstance();
        AudioManager am = (AudioManager) mContext.getSystemService(Context.AUDIO_SERVICE);
        PowerManager pm = (PowerManager) mContext.getSystemService(Context.POWER_SERVICE);

        try {
            switch (action) {
                case "back":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
                case "home":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME);
                case "recents":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_RECENTS);
                case "notifications":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS);
                case "quick_settings":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS);
                case "power":
                    return a11y != null && a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_POWER_DIALOG);
                case "lock":
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && a11y != null) {
                        return a11y.performGlobal(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN);
                    }
                    DevicePolicyManager dpm = (DevicePolicyManager) mContext.getSystemService(Context.DEVICE_POLICY_SERVICE);
                    ComponentName admin = new ComponentName(mContext, GNDroidDeviceAdminReceiver.class);
                    if (dpm != null && dpm.isAdminActive(admin)) {
                        dpm.lockNow();
                        return true;
                    }
                    return false;
                case "wake":
                    if (pm != null) {
                        @SuppressWarnings("deprecation")
                        PowerManager.WakeLock wl = pm.newWakeLock(
                                PowerManager.FULL_WAKE_LOCK |
                                PowerManager.ACQUIRE_CAUSES_WAKEUP |
                                PowerManager.ON_AFTER_RELEASE,
                                "GNDROiD:RemoteWake");
                        wl.acquire(1500);
                        return true;
                    }
                    return false;
                case "volume_up":
                    if (am != null) {
                        am.adjustSuggestedStreamVolume(AudioManager.ADJUST_RAISE, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI);
                        return true;
                    }
                    return false;
                case "volume_down":
                    if (am != null) {
                        am.adjustSuggestedStreamVolume(AudioManager.ADJUST_LOWER, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI);
                        return true;
                    }
                    return false;
                case "volume_mute":
                    if (am != null) {
                        am.adjustSuggestedStreamVolume(AudioManager.ADJUST_TOGGLE_MUTE, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI);
                        return true;
                    }
                    return false;
                case "tap":
                    if (a11y != null) {
                        float x = (float) params.optDouble("x", 0);
                        float y = (float) params.optDouble("y", 0);
                        return a11y.injectTap(x, y);
                    }
                    return false;
                case "swipe":
                    if (a11y != null) {
                        float x1 = (float) params.optDouble("x1", 0);
                        float y1 = (float) params.optDouble("y1", 0);
                        float x2 = (float) params.optDouble("x2", 0);
                        float y2 = (float) params.optDouble("y2", 0);
                        long dur = params.optLong("duration", 300);
                        return a11y.injectSwipe(x1, y1, x2, y2, dur);
                    }
                    return false;
            }
        } catch (Exception e) {
            Log.e(TAG, "Error executing action: " + action, e);
        }
        return false;
    }

    private String getClipboardSync() {
        final AtomicReference<String> ref = new AtomicReference<>("");
        final Object lock = new Object();
        mMainHandler.post(new Runnable() {
            @Override
            public void run() {
                try {
                    ClipboardManager cm = (ClipboardManager) mContext.getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null && cm.hasPrimaryClip() && cm.getPrimaryClip().getItemCount() > 0) {
                        CharSequence cs = cm.getPrimaryClip().getItemAt(0).getText();
                        if (cs != null) ref.set(cs.toString());
                    }
                } catch (Exception ignored) {}
                synchronized (lock) {
                    lock.notifyAll();
                }
            }
        });
        synchronized (lock) {
            try {
                lock.wait(500);
            } catch (InterruptedException ignored) {}
        }
        return ref.get();
    }

    private void setClipboardSync(final String text) {
        mMainHandler.post(new Runnable() {
            @Override
            public void run() {
                try {
                    ClipboardManager cm = (ClipboardManager) mContext.getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) {
                        ClipData clip = ClipData.newPlainText("GNDROiD", text);
                        cm.setPrimaryClip(clip);
                    }
                } catch (Exception ignored) {}
            }
        });
    }

    private boolean launchApp(String packageName) {
        if (packageName == null || packageName.isEmpty()) return false;
        try {
            PackageManager pm = mContext.getPackageManager();
            Intent intent = pm.getLaunchIntentForPackage(packageName);
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                mContext.startActivity(intent);
                return true;
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to launch package: " + packageName, e);
        }
        return false;
    }

    private JSONObject listInstalledAppsJson() {
        JSONObject res = new JSONObject();
        JSONArray array = new JSONArray();
        try {
            PackageManager pm = mContext.getPackageManager();
            List<PackageInfo> pkgs = pm.getInstalledPackages(0);
            for (PackageInfo pi : pkgs) {
                if (pm.getLaunchIntentForPackage(pi.packageName) != null) {
                    JSONObject app = new JSONObject();
                    app.put("name", pi.applicationInfo.loadLabel(pm).toString());
                    app.put("package", pi.packageName);
                    app.put("version", pi.versionName != null ? pi.versionName : "");
                    app.put("system", (pi.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0);
                    array.put(app);
                }
            }
            res.put("apps", array);
            res.put("count", array.length());
        } catch (Exception e) {
            Log.e(TAG, "Error listing apps", e);
        }
        return res;
    }

    private JSONObject buildStatusJson() {
        JSONObject obj = new JSONObject();
        try {
            obj.put("status", "online");
            obj.put("version", "2.3.0");
            obj.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
            obj.put("model", Build.MODEL);
            obj.put("android_version", Build.VERSION.RELEASE);
            obj.put("sdk_int", Build.VERSION.SDK_INT);

            // Battery
            IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            Intent b = mContext.registerReceiver(null, ifilter);
            if (b != null) {
                obj.put("battery", b.getIntExtra(BatteryManager.EXTRA_LEVEL, -1));
                int st = b.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                obj.put("charging", st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL);
                obj.put("temp_c", b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0);
            }

            // Power / Screen
            PowerManager pm = (PowerManager) mContext.getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                boolean isInteractive = Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH ?
                        pm.isInteractive() : pm.isScreenOn();
                obj.put("screen_on", isInteractive);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    obj.put("is_ignoring_battery_optimizations", pm.isIgnoringBatteryOptimizations(mContext.getPackageName()));
                }
            }

            // Storage free
            File path = Environment.getDataDirectory();
            StatFs stat = new StatFs(path.getPath());
            long freeBytes = (long) stat.getAvailableBlocks() * (long) stat.getBlockSize();
            obj.put("free_storage_mb", freeBytes / (1024 * 1024));

            obj.put("accessibility_active", GNDroidAccessibilityService.isAvailable());
            obj.put("timestamp", System.currentTimeMillis());

        } catch (Exception ignored) {}
        return obj;
    }
}

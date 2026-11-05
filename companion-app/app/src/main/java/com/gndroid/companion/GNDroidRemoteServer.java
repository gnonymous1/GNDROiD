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
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
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
 * GNDROiD Embedded High-Performance Dual-Port LAN Remote Server
 * Operates simultaneously on TCP port 51888 (Primary) and 51880 (Nexus Compatible).
 * Provides sub-second heartbeat, live screen streaming (JPEG / MJPEG),
 * touch / navigation injection, volume/power control, clipboard sync,
 * and remote application launcher over local Wi-Fi with ZERO USB CABLE.
 */
public class GNDroidRemoteServer {

    private static final String TAG = "GNDroidServer";
    public static final int PORT = 51888;
    public static final int PORT_PRIMARY = 51888;
    public static final int PORT_SECONDARY = 51880;

    private final Context mContext;
    private final Handler mMainHandler;
    private ServerSocket mServerSocketPrimary = null;
    private ServerSocket mServerSocketSecondary = null;
    private ExecutorService mThreadPool = null;
    private volatile boolean mRunning = false;
    private static byte[] sPlaceholderJpeg = null;

    public GNDroidRemoteServer(Context context) {
        mContext = context.getApplicationContext();
        mMainHandler = new Handler(Looper.getMainLooper());
    }

    public synchronized void start() {
        if (mRunning) return;
        mRunning = true;
        mThreadPool = Executors.newCachedThreadPool();

        startAcceptor(PORT_PRIMARY, true);
        startAcceptor(PORT_SECONDARY, false);
    }

    private void startAcceptor(final int port, final boolean isPrimary) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                ServerSocket serverSocket = null;
                try {
                    serverSocket = new ServerSocket(port);
                    serverSocket.setReuseAddress(true);
                    if (isPrimary) {
                        mServerSocketPrimary = serverSocket;
                    } else {
                        mServerSocketSecondary = serverSocket;
                    }
                    Log.i(TAG, "GNDROiD Server listening on port " + port);

                    while (mRunning && !serverSocket.isClosed()) {
                        try {
                            final Socket client = serverSocket.accept();
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
                    Log.w(TAG, "Server socket note on port " + port + ": " + e.getMessage());
                } finally {
                    if (serverSocket != null && !serverSocket.isClosed()) {
                        try { serverSocket.close(); } catch (Exception ignored) {}
                    }
                }
            }
        }, "GNDroidServer-" + port).start();
    }

    public synchronized void stop() {
        mRunning = false;
        if (mServerSocketPrimary != null) {
            try { mServerSocketPrimary.close(); } catch (Exception ignored) {}
            mServerSocketPrimary = null;
        }
        if (mServerSocketSecondary != null) {
            try { mServerSocketSecondary.close(); } catch (Exception ignored) {}
            mServerSocketSecondary = null;
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

            if ("OPTIONS".equals(method)) {
                sendResponse(out, 204, "text/plain", "");
                return;
            }

            // 1. Root / Web HUD
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

            // 2. Heartbeat Ping / Version
            if (uri.startsWith("/ping") || uri.startsWith("/version")) {
                JSONObject res = new JSONObject();
                res.put("pong", true);
                res.put("version", "2.4.0");
                res.put("apkInstalled", true);
                res.put("timestamp", System.currentTimeMillis());
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            // 3. Live Screen Capture (JPEG Frame)
            if (uri.startsWith("/api/v1/screen") || uri.startsWith("/screen.jpg") || uri.startsWith("/screen/raw")) {
                byte[] frame = GNDroidCompanionService.lastLiveScreenJpeg;
                if (frame != null && frame.length > 50) {
                    sendByteResponse(out, 200, "image/jpeg", frame);
                } else {
                    sendByteResponse(out, 200, "image/jpeg", getPlaceholderJpeg());
                }
                return;
            }

            // 4. Live Screen Capture (MJPEG Continuous Stream)
            if (uri.startsWith("/stream.mjpeg") || uri.startsWith("/stream") || uri.startsWith("/mjpeg")) {
                try {
                    socket.setTcpNoDelay(true);
                    socket.setSoTimeout(0);
                } catch (Exception ignored) {}

                String mjpegHeader = "HTTP/1.1 200 OK\r\n" +
                                     "Content-Type: multipart/x-mixed-replace; boundary=--frame\r\n" +
                                     "Access-Control-Allow-Origin: *\r\n" +
                                     "Cache-Control: no-cache, no-store, must-revalidate\r\n" +
                                     "Pragma: no-cache\r\n" +
                                     "Connection: close\r\n\r\n";
                out.write(mjpegHeader.getBytes(StandardCharsets.UTF_8));
                out.flush();

                byte[] lastSent = null;
                long lastTime = 0;

                while (mRunning && !socket.isClosed() && socket.isConnected()) {
                    byte[] frame = GNDroidCompanionService.lastLiveScreenJpeg;
                    if (frame == null || frame.length < 50) {
                        frame = getPlaceholderJpeg();
                    }
                    long now = System.currentTimeMillis();
                    if (frame != null && (frame != lastSent || (now - lastTime >= 250))) {
                        String part = "--frame\r\n" +
                                      "Content-Type: image/jpeg\r\n" +
                                      "Content-Length: " + frame.length + "\r\n\r\n";
                        out.write(part.getBytes(StandardCharsets.UTF_8));
                        out.write(frame);
                        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
                        out.flush();
                        lastSent = frame;
                        lastTime = now;
                    }
                    try {
                        Thread.sleep(30);
                    } catch (InterruptedException ie) {
                        break;
                    }
                }
                return;
            }

            // 5. Screen Info JSON (Base64 fallback)
            if (uri.startsWith("/screen") && !uri.startsWith("/screen.")) {
                byte[] frame = GNDroidCompanionService.lastLiveScreenJpeg;
                if (frame == null) frame = getPlaceholderJpeg();
                String b64 = android.util.Base64.encodeToString(frame, android.util.Base64.NO_WRAP);
                JSONObject json = new JSONObject();
                json.put("base64FrameData", b64);
                json.put("format", "JPEG");
                json.put("width", GNDroidCompanionService.screenCaptureWidth);
                json.put("height", GNDroidCompanionService.screenCaptureHeight);
                sendResponse(out, 200, "application/json", json.toString());
                return;
            }

            // 6. Device Status & Telemetry
            if (uri.startsWith("/status") || uri.startsWith("/api/v1/status") || uri.startsWith("/api/v1/mobile/status")) {
                JSONObject res = buildStatusJson();
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            // 7. Clipboard
            if (uri.startsWith("/api/v1/clipboard") || uri.startsWith("/clipboard")) {
                if ("GET".equals(method)) {
                    String clipText = getClipboardSync();
                    JSONObject res = new JSONObject();
                    res.put("text", clipText != null ? clipText : "");
                    sendResponse(out, 200, "application/json", res.toString());
                } else if ("POST".equals(method)) {
                    String body = readBody(reader, contentLength);
                    JSONObject json = new JSONObject(body);
                    String text = json.optString("text", json.optString("data", ""));
                    setClipboardSync(text);
                    JSONObject res = new JSONObject();
                    res.put("success", true);
                    sendResponse(out, 200, "application/json", res.toString());
                }
                return;
            }

            // 8. Tap / Touch Input (Query params & JSON support)
            if (uri.startsWith("/tap") || uri.startsWith("/touch") || uri.startsWith("/input")) {
                float x = -1;
                float y = -1;
                int qIdx = uri.indexOf('?');
                if (qIdx >= 0) {
                    String query = uri.substring(qIdx + 1);
                    for (String param : query.split("&")) {
                        if (param.startsWith("x=")) {
                            try { x = Float.parseFloat(param.substring(2)); } catch (Exception ignored) {}
                        } else if (param.startsWith("y=")) {
                            try { y = Float.parseFloat(param.substring(2)); } catch (Exception ignored) {}
                        }
                    }
                }
                if (contentLength > 0 && (x < 0 || y < 0)) {
                    String body = readBody(reader, contentLength);
                    try {
                        JSONObject obj = new JSONObject(body);
                        if (obj.has("x")) x = (float) obj.optDouble("x", -1);
                        if (obj.has("y")) y = (float) obj.optDouble("y", -1);
                        if (obj.has("normX")) x = (float) obj.optDouble("normX", x);
                        if (obj.has("normY")) y = (float) obj.optDouble("normY", y);
                    } catch (Exception ignored) {}
                }
                if (x >= 0 && y >= 0) {
                    if (x <= 1.0f && y <= 1.0f && GNDroidCompanionService.screenCaptureWidth > 0) {
                        x = x * GNDroidCompanionService.screenCaptureWidth;
                        y = y * GNDroidCompanionService.screenCaptureHeight;
                    }
                    GNDroidAccessibilityService a11y = GNDroidAccessibilityService.getInstance();
                    boolean ok = (a11y != null) && a11y.injectTap(x, y);
                    JSONObject res = new JSONObject();
                    res.put("success", ok);
                    res.put("x", x);
                    res.put("y", y);
                    sendResponse(out, 200, "application/json", res.toString());
                    return;
                }
            }

            // 9. Command / Exec
            if (uri.startsWith("/command") || uri.startsWith("/exec")) {
                String body = readBody(reader, contentLength);
                String cmd = body.trim();
                if (cmd.startsWith("{")) {
                    try {
                        JSONObject obj = new JSONObject(cmd);
                        cmd = obj.optString("command", obj.optString("keyOrCommandText", ""));
                    } catch (Exception ignored) {}
                }
                boolean ok = handleCommandText(cmd);
                JSONObject res = new JSONObject();
                res.put("success", ok);
                res.put("command", cmd);
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            // 10. Control Action (GNDROiD standard)
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

            // 11. Apps List
            if (uri.startsWith("/api/v1/apps") && "GET".equals(method)) {
                JSONObject res = listInstalledAppsJson();
                sendResponse(out, 200, "application/json", res.toString());
                return;
            }

            // 12. Launch App
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

            // 13. File Upload (Safe directory path)
            if (uri.startsWith("/api/v1/upload") && "POST".equals(method)) {
                String fname = fileNameHeader.isEmpty() ? "upload_" + System.currentTimeMillis() + ".dat" : fileNameHeader;
                File targetDir = mContext.getExternalFilesDir(null);
                if (targetDir == null || !targetDir.exists()) {
                    targetDir = mContext.getFilesDir();
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

    private void sendByteResponse(OutputStream out, int code, String contentType, byte[] data) {
        try {
            String header = "HTTP/1.1 " + code + " OK\r\n" +
                    "Content-Type: " + contentType + "\r\n" +
                    "Content-Length: " + data.length + "\r\n" +
                    "Access-Control-Allow-Origin: *\r\n" +
                    "Cache-Control: no-cache, no-store, must-revalidate\r\n" +
                    "Connection: close\r\n\r\n";
            out.write(header.getBytes(StandardCharsets.UTF_8));
            out.write(data);
            out.flush();
        } catch (Exception ignored) {}
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

    private synchronized byte[] getPlaceholderJpeg() {
        if (sPlaceholderJpeg == null) {
            try {
                Bitmap bmp = Bitmap.createBitmap(480, 800, Bitmap.Config.ARGB_8888);
                Canvas canvas = new Canvas(bmp);
                canvas.drawColor(Color.rgb(15, 23, 42)); // Slate 900
                Paint paint = new Paint();
                paint.setAntiAlias(true);
                paint.setColor(Color.WHITE);
                paint.setTextSize(26);
                paint.setTextAlign(Paint.Align.CENTER);
                canvas.drawText("GNDROiD Link Active", 240, 360, paint);
                paint.setColor(Color.rgb(56, 189, 248)); // Sky blue
                paint.setTextSize(18);
                canvas.drawText("Tap 'Start Screen Mirror' on Phone", 240, 410, paint);
                paint.setColor(Color.rgb(148, 163, 184)); // Slate 400
                paint.setTextSize(14);
                canvas.drawText("Pure Wi-Fi Wireless KVM (Zero Cable)", 240, 450, paint);
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                bmp.compress(Bitmap.CompressFormat.JPEG, 80, baos);
                sPlaceholderJpeg = baos.toByteArray();
                bmp.recycle();
            } catch (Exception e) {
                sPlaceholderJpeg = new byte[0];
            }
        }
        return sPlaceholderJpeg;
    }

    private boolean handleCommandText(String cmd) {
        if (cmd == null || cmd.isEmpty()) return false;
        String upper = cmd.toUpperCase().trim();
        if (upper.contains("KEY BACK") || upper.equals("BACK")) {
            return handleControlAction("back", new JSONObject());
        } else if (upper.contains("KEY HOME") || upper.equals("HOME")) {
            return handleControlAction("home", new JSONObject());
        } else if (upper.contains("KEY RECENTS") || upper.equals("RECENTS")) {
            return handleControlAction("recents", new JSONObject());
        } else if (upper.contains("KEY POWER") || upper.equals("POWER")) {
            return handleControlAction("power", new JSONObject());
        } else if (upper.contains("KEY WAKE") || upper.equals("WAKE")) {
            return handleControlAction("wake", new JSONObject());
        } else if (upper.contains("VOL_UP") || upper.contains("VOLUME_UP")) {
            return handleControlAction("volume_up", new JSONObject());
        } else if (upper.contains("VOL_DOWN") || upper.contains("VOLUME_DOWN")) {
            return handleControlAction("volume_down", new JSONObject());
        }
        return false;
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
                        if (params.has("normX")) x = (float) params.optDouble("normX", 0);
                        if (params.has("normY")) y = (float) params.optDouble("normY", 0);
                        if (x <= 1.0f && y <= 1.0f && GNDroidCompanionService.screenCaptureWidth > 0) {
                            x = x * GNDroidCompanionService.screenCaptureWidth;
                            y = y * GNDroidCompanionService.screenCaptureHeight;
                        }
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
                        if (x1 <= 1.0f && y1 <= 1.0f && GNDroidCompanionService.screenCaptureWidth > 0) {
                            x1 = x1 * GNDroidCompanionService.screenCaptureWidth;
                            y1 = y1 * GNDroidCompanionService.screenCaptureHeight;
                            x2 = x2 * GNDroidCompanionService.screenCaptureWidth;
                            y2 = y2 * GNDroidCompanionService.screenCaptureHeight;
                        }
                        return a11y.injectSwipe(x1, y1, x2, y2, dur);
                    }
                    return false;
                default:
                    return false;
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling control action: " + action, e);
            return false;
        }
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
                synchronized (lock) { lock.notifyAll(); }
            }
        });
        synchronized (lock) {
            try { lock.wait(500); } catch (Exception ignored) {}
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
            List<PackageInfo> packages = pm.getInstalledPackages(0);
            for (PackageInfo pi : packages) {
                boolean isSystem = (pi.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
                if (!isSystem || pm.getLaunchIntentForPackage(pi.packageName) != null) {
                    JSONObject app = new JSONObject();
                    app.put("package", pi.packageName);
                    app.put("name", pi.applicationInfo.loadLabel(pm).toString());
                    app.put("version", pi.versionName != null ? pi.versionName : "");
                    app.put("is_system", isSystem);
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
            obj.put("version", "2.4.0");
            obj.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
            obj.put("model", Build.MODEL);
            obj.put("hostname", Build.MODEL);
            obj.put("deviceModel", Build.MODEL);
            obj.put("manufacturer", Build.MANUFACTURER);
            obj.put("isMobile", true);
            obj.put("apkInstalled", true);
            obj.put("android_version", Build.VERSION.RELEASE);
            obj.put("screen_cast_active", GNDroidCompanionService.lastLiveScreenJpeg != null);
            obj.put("screen_width", GNDroidCompanionService.screenCaptureWidth);
            obj.put("screen_height", GNDroidCompanionService.screenCaptureHeight);
            obj.put("sdk_int", Build.VERSION.SDK_INT);

            IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            Intent b = mContext.registerReceiver(null, ifilter);
            if (b != null) {
                obj.put("battery", b.getIntExtra(BatteryManager.EXTRA_LEVEL, -1));
                int st = b.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                obj.put("charging", st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL);
                obj.put("temp_c", b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0);
            }

            PowerManager pm = (PowerManager) mContext.getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                boolean isInteractive = Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH ?
                        pm.isInteractive() : pm.isScreenOn();
                obj.put("screen_on", isInteractive);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    obj.put("is_ignoring_battery_optimizations", pm.isIgnoringBatteryOptimizations(mContext.getPackageName()));
                }
            }

            File path = Environment.getDataDirectory();
            StatFs stat = new StatFs(path.getPath());
            long freeBytes = (long) stat.getAvailableBlocks() * (long) stat.getBlockSize();
            obj.put("free_storage_mb", freeBytes / (1024 * 1024));

            GNDroidAccessibilityService a11y = GNDroidAccessibilityService.getInstance();
            obj.put("accessibility_active", a11y != null);
            obj.put("timestamp", System.currentTimeMillis());

        } catch (Exception e) {
            Log.e(TAG, "Error building status JSON", e);
        }
        return obj;
    }
}

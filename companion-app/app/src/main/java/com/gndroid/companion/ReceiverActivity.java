package com.gndroid.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * GNDROiD TV & Peer-to-Peer Remote Display Client Activity
 * Runs on Android TV, Tablets, or secondary Phones to connect to another
 * Android device running GNDROiD Companion, stream its display at low latency,
 * and relay TV Remote D-Pad / Touch controls back to the host device.
 */
public class ReceiverActivity extends Activity {

    private static final String TAG = "ReceiverActivity";

    private FrameLayout mFlRoot;
    private FrameLayout mFlViewport;
    private ImageView mIvRemoteScreen;
    private LinearLayout mLlToolbar;
    private TextView mTvStreamStats;

    private ScrollView mSvDiscovery;
    private TextView mTvDiscoveryStatus;
    private EditText mEtTargetIp;
    private Button mBtnDirectConnect;
    private LinearLayout mLlRadarList;
    private Button mBtnRefreshRadar;
    private Button mBtnReturnDashboard;

    private Handler mHandler;
    private ExecutorService mNetworkExecutor;
    private final AtomicBoolean mIsStreaming = new AtomicBoolean(false);
    private Thread mStreamThread = null;
    private Thread mRadarThread = null;
    private String mConnectedIp = null;

    private final ConcurrentHashMap<String, JSONObject> mDiscoveredDevices = new ConcurrentHashMap<>();

    private float mTouchDownX = 0;
    private float mTouchDownY = 0;
    private long mTouchDownTime = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_receiver);

        mHandler = new Handler(Looper.getMainLooper());
        mNetworkExecutor = Executors.newFixedThreadPool(4);

        initViews();
        startRadarDiscovery();
    }

    private void initViews() {
        mFlRoot = findViewById(R.id.fl_root);
        mFlViewport = findViewById(R.id.fl_viewport);
        mIvRemoteScreen = findViewById(R.id.iv_remote_screen);
        mLlToolbar = findViewById(R.id.ll_toolbar);
        mTvStreamStats = findViewById(R.id.tv_stream_stats);

        mSvDiscovery = findViewById(R.id.sv_discovery);
        mTvDiscoveryStatus = findViewById(R.id.tv_discovery_status);
        mEtTargetIp = findViewById(R.id.et_target_ip);
        mBtnDirectConnect = findViewById(R.id.btn_direct_connect);
        mLlRadarList = findViewById(R.id.ll_radar_list);
        mBtnRefreshRadar = findViewById(R.id.btn_refresh_radar);
        mBtnReturnDashboard = findViewById(R.id.btn_return_dashboard);

        // Pre-fill target IP with default
        mEtTargetIp.setText("192.168.100.245");

        mBtnDirectConnect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String ip = mEtTargetIp.getText().toString().trim();
                if (ip.isEmpty()) {
                    Toast.makeText(ReceiverActivity.this, "Please enter an IP address", Toast.LENGTH_SHORT).show();
                    return;
                }
                connectToHost(ip);
            }
        });

        mBtnRefreshRadar.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendDiscoveryProbe();
                Toast.makeText(ReceiverActivity.this, "Scanning Subnet Radar...", Toast.LENGTH_SHORT).show();
            }
        });

        mBtnReturnDashboard.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();
            }
        });

        // HUD Buttons
        findViewById(R.id.btn_hud_back).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendAction("back");
            }
        });

        findViewById(R.id.btn_hud_home).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendAction("home");
            }
        });

        findViewById(R.id.btn_hud_recents).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendAction("recents");
            }
        });

        findViewById(R.id.btn_hud_text).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showTypeDialog();
            }
        });

        findViewById(R.id.btn_hud_disconnect).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                disconnect();
            }
        });

        // Touch event listener on the mirrored screen
        mIvRemoteScreen.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                return handleScreenTouch(event);
            }
        });
    }

    public void connectToHost(final String ip) {
        disconnect();
        mConnectedIp = ip;
        mIsStreaming.set(true);

        mSvDiscovery.setVisibility(View.GONE);
        mFlViewport.setVisibility(View.VISIBLE);
        mTvStreamStats.setText("Connecting to " + ip + "...");

        mStreamThread = new Thread(new Runnable() {
            @Override
            public void run() {
                streamWorker(ip);
            }
        }, "Receiver-StreamWorker");
        mStreamThread.start();
    }

    public void disconnect() {
        mIsStreaming.set(false);
        if (mStreamThread != null) {
            mStreamThread.interrupt();
            mStreamThread = null;
        }
        mHandler.post(new Runnable() {
            @Override
            public void run() {
                mFlViewport.setVisibility(View.GONE);
                mSvDiscovery.setVisibility(View.VISIBLE);
                mTvStreamStats.setText("Disconnected");
                mConnectedIp = null;
            }
        });
    }

    private void streamWorker(String hostIp) {
        String mjpegUrl = "http://" + hostIp + ":51888/stream.mjpeg";
        int frameCount = 0;
        long lastFpsTime = System.currentTimeMillis();

        while (mIsStreaming.get()) {
            HttpURLConnection conn = null;
            InputStream in = null;
            try {
                URL url = new URL(mjpegUrl);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestProperty("User-Agent", "GNDROiD-AndroidReceiver");
                conn.setConnectTimeout(4000);
                conn.setReadTimeout(10000);
                conn.connect();

                in = conn.getInputStream();
                byte[] chunk = new byte[16384];
                ByteArrayOutputStream frameBuf = new ByteArrayOutputStream(65536);

                int prevByte = -1;
                boolean inFrame = false;

                while (mIsStreaming.get()) {
                    int bytesRead = in.read(chunk);
                    if (bytesRead <= 0) break;

                    for (int i = 0; i < bytesRead; i++) {
                        int b = chunk[i] & 0xFF;

                        // Check for JPEG Start of Image (SOI) FF D8
                        if (!inFrame && prevByte == 0xFF && b == 0xD8) {
                            inFrame = true;
                            frameBuf.reset();
                            frameBuf.write(0xFF);
                            frameBuf.write(0xD8);
                        } else if (inFrame) {
                            frameBuf.write(b);
                            // Check for JPEG End of Image (EOI) FF D9
                            if (prevByte == 0xFF && b == 0xD9) {
                                inFrame = false;
                                byte[] jpegBytes = frameBuf.toByteArray();
                                if (jpegBytes.length > 100) {
                                    final Bitmap bmp = BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.length);
                                    if (bmp != null) {
                                        frameCount++;
                                        long now = System.currentTimeMillis();
                                        if (now - lastFpsTime >= 1000) {
                                            final int fps = frameCount;
                                            frameCount = 0;
                                            lastFpsTime = now;
                                            mHandler.post(new Runnable() {
                                                @Override
                                                public void run() {
                                                    mTvStreamStats.setText("⚡ LIVE | " + mConnectedIp + " | " + fps + " FPS");
                                                }
                                            });
                                        }

                                        mHandler.post(new Runnable() {
                                            @Override
                                            public void run() {
                                                if (mIsStreaming.get() && mIvRemoteScreen != null) {
                                                    mIvRemoteScreen.setImageBitmap(bmp);
                                                }
                                            }
                                        });
                                    }
                                }
                                frameBuf.reset();
                            }
                        }
                        prevByte = b;
                    }
                }
            } catch (Exception e) {
                Log.w(TAG, "Stream connection error: " + e.getMessage());
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ignored) {
                    break;
                }
            } finally {
                if (in != null) {
                    try { in.close(); } catch (Exception ignored) {}
                }
                if (conn != null) {
                    try { conn.disconnect(); } catch (Exception ignored) {}
                }
            }
        }
    }

    private boolean handleScreenTouch(MotionEvent event) {
        if (mConnectedIp == null || mIvRemoteScreen.getDrawable() == null) return false;

        // Calculate normalized touch position inside the actual displayed image rect
        float[] norm = getNormalizedCoordinates(event.getX(), event.getY());
        if (norm == null) return false;

        float normX = norm[0];
        float normY = norm[1];

        int action = event.getActionMasked();
        switch (action) {
            case MotionEvent.ACTION_DOWN:
                mTouchDownX = normX;
                mTouchDownY = normY;
                mTouchDownTime = System.currentTimeMillis();
                return true;

            case MotionEvent.ACTION_UP:
                long duration = System.currentTimeMillis() - mTouchDownTime;
                float dx = Math.abs(normX - mTouchDownX);
                float dy = Math.abs(normY - mTouchDownY);

                if (dx < 0.04f && dy < 0.04f) {
                    // Tap
                    sendTap(normX, normY);
                } else {
                    // Swipe
                    sendSwipe(mTouchDownX, mTouchDownY, normX, normY, Math.max(150, Math.min(500, (int) duration)));
                }
                return true;
        }
        return false;
    }

    private float[] getNormalizedCoordinates(float viewX, float viewY) {
        if (mIvRemoteScreen == null || mIvRemoteScreen.getDrawable() == null) return null;

        Matrix matrix = mIvRemoteScreen.getImageMatrix();
        RectF rect = new RectF();
        rect.set(0, 0, mIvRemoteScreen.getDrawable().getIntrinsicWidth(),
                mIvRemoteScreen.getDrawable().getIntrinsicHeight());
        matrix.mapRect(rect);

        if (viewX < rect.left || viewX > rect.right || viewY < rect.top || viewY > rect.bottom) {
            return null; // Clicked on letterbox padding
        }

        float normX = (viewX - rect.left) / rect.width();
        float normY = (viewY - rect.top) / rect.height();
        return new float[]{normX, normY};
    }

    // Android TV Remote D-Pad & Key Interceptor
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (mFlViewport.getVisibility() == View.VISIBLE && mConnectedIp != null) {
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_CENTER:
                case KeyEvent.KEYCODE_ENTER:
                    sendAction("tap");
                    return true;

                case KeyEvent.KEYCODE_DPAD_UP:
                    sendSwipe(0.5f, 0.7f, 0.5f, 0.3f, 250);
                    return true;

                case KeyEvent.KEYCODE_DPAD_DOWN:
                    sendSwipe(0.5f, 0.3f, 0.5f, 0.7f, 250);
                    return true;

                case KeyEvent.KEYCODE_DPAD_LEFT:
                    sendSwipe(0.8f, 0.5f, 0.2f, 0.5f, 250);
                    return true;

                case KeyEvent.KEYCODE_DPAD_RIGHT:
                    sendSwipe(0.2f, 0.5f, 0.8f, 0.5f, 250);
                    return true;

                case KeyEvent.KEYCODE_BACK:
                    sendAction("back");
                    return true;

                case KeyEvent.KEYCODE_HOME:
                    sendAction("home");
                    return true;

                case KeyEvent.KEYCODE_MENU:
                case KeyEvent.KEYCODE_APP_SWITCH:
                    sendAction("recents");
                    return true;

                case KeyEvent.KEYCODE_VOLUME_UP:
                    sendAction("volume_up");
                    return true;

                case KeyEvent.KEYCODE_VOLUME_DOWN:
                    sendAction("volume_down");
                    return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    private void sendAction(final String actionName) {
        JSONObject json = new JSONObject();
        try {
            json.put("action", actionName);
            sendPostControl(json);
        } catch (Exception ignored) {}
    }

    private void sendTap(float normX, float normY) {
        JSONObject json = new JSONObject();
        try {
            json.put("action", "tap");
            json.put("normX", normX);
            json.put("normY", normY);
            sendPostControl(json);
        } catch (Exception ignored) {}
    }

    private void sendSwipe(float x1, float y1, float x2, float y2, int duration) {
        JSONObject json = new JSONObject();
        try {
            json.put("action", "swipe");
            json.put("normX1", x1);
            json.put("normY1", y1);
            json.put("normX2", x2);
            json.put("normY2", y2);
            json.put("duration", duration);
            sendPostControl(json);
        } catch (Exception ignored) {}
    }

    private void sendPostControl(final JSONObject payload) {
        if (mConnectedIp == null) return;
        final String targetUrl = "http://" + mConnectedIp + ":51888/api/v1/control";

        mNetworkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(targetUrl);
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setRequestProperty("Content-Type", "application/json");
                    conn.setConnectTimeout(1500);
                    conn.setReadTimeout(1500);
                    conn.setDoOutput(true);

                    byte[] data = payload.toString().getBytes(StandardCharsets.UTF_8);
                    try (OutputStream out = conn.getOutputStream()) {
                        out.write(data);
                    }
                    int code = conn.getResponseCode();
                    Log.d(TAG, "Sent control action, response: " + code);
                } catch (Exception e) {
                    Log.w(TAG, "Failed to send control: " + e.getMessage());
                } finally {
                    if (conn != null) {
                        try { conn.disconnect(); } catch (Exception ignored) {}
                    }
                }
            }
        });
    }

    private void showTypeDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle("Type to Mirrored Device");
        final EditText input = new EditText(this);
        input.setHint("Enter text to type...");
        builder.setView(input);

        builder.setPositiveButton("Send", new DialogInterface.OnClickListener() {
            @Override
            public void onClick(DialogInterface dialog, int which) {
                String text = input.getText().toString();
                if (!text.isEmpty()) {
                    JSONObject json = new JSONObject();
                    try {
                        json.put("action", "key");
                        json.put("text", text);
                        sendPostControl(json);
                    } catch (Exception ignored) {}
                }
            }
        });
        builder.setNegativeButton("Cancel", null);
        builder.show();
    }

    // Subnet Radar UDP Discovery
    private void startRadarDiscovery() {
        mRadarThread = new Thread(new Runnable() {
            @Override
            public void run() {
                DatagramSocket socket = null;
                try {
                    socket = new DatagramSocket();
                    socket.setBroadcast(true);
                    sendDiscoveryProbe();

                    byte[] buf = new byte[2048];
                    while (!Thread.currentThread().isInterrupted()) {
                        DatagramPacket packet = new DatagramPacket(buf, buf.length);
                        try {
                            socket.setSoTimeout(3000);
                            socket.receive(packet);
                            String raw = new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8).trim();
                            if (raw.contains("GNDROID_BEACON") || raw.contains("\"magic\"")) {
                                String senderIp = packet.getAddress().getHostAddress();
                                JSONObject json;
                                if (raw.startsWith("{")) {
                                    json = new JSONObject(raw);
                                } else if (raw.contains("{")) {
                                    json = new JSONObject(raw.substring(raw.indexOf("{")));
                                } else {
                                    continue;
                                }
                                onDeviceDiscovered(senderIp, json);
                            }
                        } catch (Exception ignored) {
                            sendDiscoveryProbe();
                        }
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Radar discovery socket error: " + e.getMessage());
                } finally {
                    if (socket != null && !socket.isClosed()) {
                        socket.close();
                    }
                }
            }
        }, "Receiver-RadarListener");
        mRadarThread.start();
    }

    private void sendDiscoveryProbe() {
        mNetworkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    DatagramSocket s = new DatagramSocket();
                    s.setBroadcast(true);
                    byte[] data = "GNDROID_DISCOVER".getBytes(StandardCharsets.UTF_8);
                    DatagramPacket p = new DatagramPacket(data, data.length, InetAddress.getByName("255.255.255.255"), GNDroidBeacon.BEACON_PORT);
                    s.send(p);
                    s.close();
                } catch (Exception ignored) {}
            }
        });
    }

    private void onDeviceDiscovered(final String ip, final JSONObject info) {
        mDiscoveredDevices.put(ip, info);
        mHandler.post(new Runnable() {
            @Override
            public void run() {
                updateRadarUI();
            }
        });
    }

    private void updateRadarUI() {
        if (mLlRadarList == null) return;
        mLlRadarList.removeAllViews();

        if (mDiscoveredDevices.isEmpty()) {
            mTvDiscoveryStatus.setText("Scanning local Wi-Fi for active devices...");
            return;
        }

        mTvDiscoveryStatus.setText("Found " + mDiscoveredDevices.size() + " active device(s) on Wi-Fi:");

        for (final String ip : mDiscoveredDevices.keySet()) {
            JSONObject dev = mDiscoveredDevices.get(ip);
            String model = dev != null ? dev.optString("model", "Android Device") : "Android Device";
            boolean castActive = dev != null && dev.optBoolean("screen_cast_active", false);

            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.HORIZONTAL);
            card.setBackgroundResource(R.drawable.bg_card);
            card.setPadding(24, 20, 24, 20);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            lp.setMargins(0, 0, 0, 16);
            card.setLayoutParams(lp);
            card.setFocusable(true);
            card.setFocusableInTouchMode(true);

            LinearLayout infoCol = new LinearLayout(this);
            infoCol.setOrientation(LinearLayout.VERTICAL);
            LinearLayout.LayoutParams infoLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f);
            infoCol.setLayoutParams(infoLp);

            TextView tvTitle = new TextView(this);
            tvTitle.setText("📱 " + model);
            tvTitle.setTextSize(15);
            tvTitle.setTextColor(0xFF0F172A);
            tvTitle.setTypeface(null, android.graphics.Typeface.BOLD);
            infoCol.addView(tvTitle);

            TextView tvSub = new TextView(this);
            tvSub.setText("IP: " + ip + " | Cast: " + (castActive ? "🟢 Active" : "Standby"));
            tvSub.setTextSize(12);
            tvSub.setTextColor(0xFF64748B);
            infoCol.addView(tvSub);

            card.addView(infoCol);

            Button btnConnect = new Button(this);
            btnConnect.setText("Connect ⚡");
            btnConnect.setTextSize(12);
            btnConnect.setTextColor(0xFFFFFFFF);
            btnConnect.setBackgroundColor(0xFF0284C7);
            btnConnect.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    connectToHost(ip);
                }
            });
            card.addView(btnConnect);

            card.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    connectToHost(ip);
                }
            });

            mLlRadarList.addView(card);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        disconnect();
        if (mRadarThread != null) {
            mRadarThread.interrupt();
        }
        if (mNetworkExecutor != null) {
            mNetworkExecutor.shutdownNow();
        }
    }
}

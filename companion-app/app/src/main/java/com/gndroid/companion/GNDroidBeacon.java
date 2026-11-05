package com.gndroid.companion;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

import org.json.JSONObject;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

/**
 * GNDROiD Subnet Radar Beacon
 * Broadcasts device presence, status, and LAN telemetry on UDP port 51880
 * so the PC controller discovers the device instantly with zero manual configuration.
 */
public class GNDroidBeacon {

    private static final String TAG = "GNDroidBeacon";
    public static final int BEACON_PORT = 51880;
    public static final String MAGIC_HEADER = "GNDROID_BEACON";

    private final Context mContext;
    private volatile boolean mRunning = false;
    private Thread mBroadcastThread = null;
    private Thread mListenerThread = null;
    private DatagramSocket mSocket = null;

    public GNDroidBeacon(Context context) {
        mContext = context.getApplicationContext();
    }

    public synchronized void start() {
        if (mRunning) return;
        mRunning = true;

        try {
            mSocket = new DatagramSocket(BEACON_PORT);
            mSocket.setBroadcast(true);
            mSocket.setReuseAddress(true);
        } catch (Exception e) {
            Log.w(TAG, "Could not bind to beacon port " + BEACON_PORT + ", creating unbound socket for broadcast", e);
            try {
                mSocket = new DatagramSocket();
                mSocket.setBroadcast(true);
            } catch (Exception ex) {
                Log.e(TAG, "Failed to create DatagramSocket", ex);
                mRunning = false;
                return;
            }
        }

        // Periodic broadcast thread
        mBroadcastThread = new Thread(new Runnable() {
            @Override
            public void run() {
                while (mRunning) {
                    try {
                        sendBeacon();
                        Thread.sleep(2000);
                    } catch (InterruptedException e) {
                        break;
                    } catch (Exception e) {
                        Log.e(TAG, "Error sending beacon", e);
                    }
                }
            }
        }, "GNDroidBeacon-Broadcast");
        mBroadcastThread.start();

        // Inbound discovery listener thread (responds immediately to "GNDROID_DISCOVER")
        mListenerThread = new Thread(new Runnable() {
            @Override
            public void run() {
                byte[] buf = new byte[1024];
                while (mRunning && mSocket != null && !mSocket.isClosed()) {
                    try {
                        DatagramPacket packet = new DatagramPacket(buf, buf.length);
                        mSocket.receive(packet);
                        String msg = new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8).trim();
                        if (msg.contains("GNDROID_DISCOVER") || msg.contains("PING")) {
                            byte[] reply = buildBeaconJson().toString().getBytes(StandardCharsets.UTF_8);
                            DatagramPacket replyPacket = new DatagramPacket(
                                    reply, reply.length, packet.getAddress(), packet.getPort());
                            mSocket.send(replyPacket);
                        }
                    } catch (Exception ignored) {
                    }
                }
            }
        }, "GNDroidBeacon-Listener");
        mListenerThread.start();

        Log.i(TAG, "GNDROiD Subnet Radar Beacon active on port " + BEACON_PORT);
    }

    public synchronized void stop() {
        mRunning = false;
        if (mSocket != null && !mSocket.isClosed()) {
            try {
                mSocket.close();
            } catch (Exception ignored) {}
        }
        if (mBroadcastThread != null) {
            mBroadcastThread.interrupt();
            mBroadcastThread = null;
        }
        if (mListenerThread != null) {
            mListenerThread.interrupt();
            mListenerThread = null;
        }
        Log.i(TAG, "GNDROiD Subnet Radar Beacon stopped.");
    }

    private void sendBeacon() {
        if (mSocket == null || mSocket.isClosed()) return;
        try {
            JSONObject json = buildBeaconJson();
            byte[] data = json.toString().getBytes(StandardCharsets.UTF_8);

            // 1. Broadcast to universal 255.255.255.255
            InetAddress broad = InetAddress.getByName("255.255.255.255");
            DatagramPacket p = new DatagramPacket(data, data.length, broad, BEACON_PORT);
            mSocket.send(p);

            // 2. Broadcast to specific interface subnet broadcasts
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces.hasMoreElements()) {
                NetworkInterface iface = interfaces.nextElement();
                if (iface.isLoopback() || !iface.isUp()) continue;
                for (InterfaceAddress addr : iface.getInterfaceAddresses()) {
                    InetAddress broadcast = addr.getBroadcast();
                    if (broadcast != null) {
                        DatagramPacket pSub = new DatagramPacket(data, data.length, broadcast, BEACON_PORT);
                        mSocket.send(pSub);
                    }
                }
            }
        } catch (Exception e) {
            // Log.d(TAG, "Beacon cycle skipped: " + e.getMessage());
        }
    }

    public JSONObject buildBeaconJson() {
        JSONObject obj = new JSONObject();
        try {
            obj.put("magic", MAGIC_HEADER);
            obj.put("version", "2.3.0");
            obj.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
            obj.put("model", Build.MODEL);
            obj.put("manufacturer", Build.MANUFACTURER);
            obj.put("android_ver", Build.VERSION.RELEASE);
            obj.put("sdk_int", Build.VERSION.SDK_INT);
            obj.put("port", GNDroidRemoteServer.PORT);

            // Battery info
            IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            Intent bStatus = mContext.registerReceiver(null, ifilter);
            int level = -1;
            boolean charging = false;
            if (bStatus != null) {
                level = bStatus.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int status = bStatus.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                           status == BatteryManager.BATTERY_STATUS_FULL;
            }
            obj.put("battery", level);
            obj.put("charging", charging);

            // Screen state
            PowerManager pm = (PowerManager) mContext.getSystemService(Context.POWER_SERVICE);
            boolean isInteractive = pm != null && (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH ?
                    pm.isInteractive() : pm.isScreenOn());
            obj.put("screen_on", isInteractive);

            // Capabilities
            obj.put("a11y_active", GNDroidAccessibilityService.isAvailable());
            obj.put("timestamp", System.currentTimeMillis());
        } catch (Exception ignored) {}
        return obj;
    }
}

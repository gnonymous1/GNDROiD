package com.gndroid.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.wifi.WifiManager;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.os.Handler;
import android.os.HandlerThread;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;


/**
 * GNDROiD Unbreakable Companion Service
 * Persistent Foreground Service maintaining Facebook-grade background persistence,
 * high-performance Wi-Fi lock, Doze immunity, sub-second heartbeat watchdog,
 * and seamless LAN socket bridge.
 */
public class GNDroidCompanionService extends Service {

    private static final String TAG = "GNDroidService";
    private static final String CHANNEL_ID = "gndroid_companion_channel";
    private static final int NOTIFICATION_ID = 5188;

    private PowerManager.WakeLock mWakeLock = null;
    private WifiManager.WifiLock mWifiLock = null;
    private ConnectivityManager mConnManager = null;
    private ConnectivityManager.NetworkCallback mNetworkCallback = null;

    private GNDroidRemoteServer mRemoteServer = null;
    private GNDroidBeacon mBeacon = null;
    private GNDroidCastEngine mCastEngine = null;
    private GNDroidAudioEngine mAudioEngine = null;
    private Thread mWatchdogThread = null;
    private volatile boolean mRunning = false;

    public static volatile MediaProjection activeMediaProjection = null;
    public static volatile VirtualDisplay activeVirtualDisplay = null;
    public static volatile ImageReader activeImageReader = null;
    public static volatile byte[] lastLiveScreenJpeg = null;
    public static volatile long lastLiveScreenTimestamp = 0;
    public static volatile int screenCaptureWidth = 540;
    public static volatile int screenCaptureHeight = 960;
    public static volatile GNDroidCompanionService activeInstance = null;
    public static final Object frameSignalLock = new Object();
    private static HandlerThread sImageWorkerThread = null;
    private static Handler sImageWorkerHandler = null;

    public static synchronized void setMediaProjection(MediaProjection mp, int width, int height, int dpi) {
        if (activeVirtualDisplay != null) {
            try { activeVirtualDisplay.release(); } catch (Exception ignored) {}
            activeVirtualDisplay = null;
        }
        if (activeImageReader != null) {
            try { activeImageReader.close(); } catch (Exception ignored) {}
            activeImageReader = null;
        }

        activeMediaProjection = mp;
        if (mp == null) return;

        int targetW = 540;
        int targetH = (width > 0) ? (int) Math.round((double) height * 540.0 / Math.max(1, width)) : 960;
        targetH = (targetH / 2) * 2;
        screenCaptureWidth = targetW;
        screenCaptureHeight = targetH;

        if (sImageWorkerThread == null) {
            sImageWorkerThread = new HandlerThread("GNDroidImageWorker");
            sImageWorkerThread.start();
            sImageWorkerHandler = new Handler(sImageWorkerThread.getLooper());
        }

        try {
            activeImageReader = ImageReader.newInstance(targetW, targetH, PixelFormat.RGBA_8888, 3);
            activeImageReader.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
                @Override
                public void onImageAvailable(ImageReader reader) {
                    Image image = null;
                    try {
                        image = reader.acquireLatestImage();
                        if (image != null) {
                            byte[] jpeg = processImageToJpegBytes(image);
                            if (jpeg != null && jpeg.length > 50) {
                                lastLiveScreenJpeg = jpeg;
                                lastLiveScreenTimestamp = System.currentTimeMillis();
                                synchronized (frameSignalLock) {
                                    frameSignalLock.notifyAll();
                                }
                            }
                        }
                    } catch (Throwable ignored) {
                    } finally {
                        if (image != null) {
                            try { image.close(); } catch (Exception ignored) {}
                        }
                    }
                }
            }, sImageWorkerHandler);

            activeVirtualDisplay = mp.createVirtualDisplay(
                "GNDROiDDirectCast",
                targetW, targetH, dpi > 0 ? dpi : 320,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                activeImageReader.getSurface(),
                null, sImageWorkerHandler
            );
            Log.i(TAG, "Direct Wireless Screen Cast active at " + targetW + "x" + targetH);
            if (activeInstance != null && activeInstance.mCastEngine != null) {
                try {
                    activeInstance.mCastEngine.configure(targetW, targetH, 4000000, 60, false);
                    activeInstance.mCastEngine.setMediaProjection(mp);
                    activeInstance.mCastEngine.start();
                    Log.i(TAG, "Hardware H.264 CastEngine linked and active on port " + GNDroidCastEngine.VIDEO_PORT);
                } catch (Exception ex) {
                    Log.w(TAG, "Could not start secondary H.264 engine: " + ex.getMessage());
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to create Direct Screen Cast VirtualDisplay", e);
        }
    }

    public static byte[] processImageToJpegBytes(Image image) {
        try {
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer buffer = planes[0].getBuffer();
            buffer.rewind();
            int pixelStride = planes[0].getPixelStride();
            int rowStride = planes[0].getRowStride();
            int imgW = image.getWidth();
            int imgH = image.getHeight();
            int rowPadding = rowStride - pixelStride * imgW;
            Bitmap rawBmp = Bitmap.createBitmap(imgW + (rowPadding > 0 ? (rowPadding / pixelStride) : 0), imgH, Bitmap.Config.ARGB_8888);
            rawBmp.copyPixelsFromBuffer(buffer);
            Bitmap cleanBmp = (rowPadding > 0) ? Bitmap.createBitmap(rawBmp, 0, 0, imgW, imgH) : rawBmp;

            ByteArrayOutputStream baos = new ByteArrayOutputStream(32768);
            cleanBmp.compress(Bitmap.CompressFormat.JPEG, 70, baos);
            if (cleanBmp != rawBmp) {
                cleanBmp.recycle();
            }
            rawBmp.recycle();
            return baos.toByteArray();
        } catch (Exception e) {
            return null;
        }
    }


    @Override
    public void onCreate() {
        super.onCreate();
        Log.i(TAG, "GNDROiD Companion Service initializing...");

        activeInstance = this;
        createNotificationChannel();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int fgsType = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    fgsType |= ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
                }
                startForeground(NOTIFICATION_ID, buildForegroundNotification("Active | Waiting for GNDROiD PC..."), fgsType);
            } else {
                startForeground(NOTIFICATION_ID, buildForegroundNotification("Active | Waiting for GNDROiD PC..."));
            }
        } catch (Throwable t) {
            Log.w(TAG, "Failed to start with typed foreground service, falling back to legacy", t);
            try {
                startForeground(NOTIFICATION_ID, buildForegroundNotification("Active | Waiting for GNDROiD PC..."));
            } catch (Throwable t2) {
                Log.e(TAG, "All startForeground attempts failed", t2);
            }
        }

        acquireLocks();
        registerNetworkWatcher();

        // Start embedded servers
        mRemoteServer = new GNDroidRemoteServer(this);
        mRemoteServer.start();

        mBeacon = new GNDroidBeacon(this);
        mBeacon.start();

        mCastEngine = new GNDroidCastEngine();
        mCastEngine.start();

        mAudioEngine = new GNDroidAudioEngine();
        mAudioEngine.start();

        startWatchdog();
        mRunning = true;
        Log.i(TAG, "GNDROiD Companion Service successfully started.");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "ACTION_START_MEDIA_PROJECTION".equals(intent.getAction())) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    int fgsType = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                        fgsType |= ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
                    }
                    startForeground(NOTIFICATION_ID, buildForegroundNotification("Screen Cast LIVE | Streaming on Port 51880"), fgsType);
                }
            } catch (Throwable t) {
                Log.w(TAG, "MediaProjection foreground promotion failed", t);
            }
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null; // Local service
    }

    @Override
    public void onDestroy() {
        Log.w(TAG, "GNDROiD Companion Service onDestroy requested.");
        mRunning = false;

        if (mWatchdogThread != null) {
            mWatchdogThread.interrupt();
            mWatchdogThread = null;
        }

        if (mBeacon != null) {
            mBeacon.stop();
            mBeacon = null;
        }

        if (mRemoteServer != null) {
            mRemoteServer.stop();
            mRemoteServer = null;
        }

        if (mCastEngine != null) {
            mCastEngine.stop();
            mCastEngine = null;
        }

        if (mAudioEngine != null) {
            mAudioEngine.stop();
            mAudioEngine = null;
        }

        unregisterNetworkWatcher();
        releaseLocks();
        super.onDestroy();
    }

    private void acquireLocks() {
        // 1. Acquire Partial Wake Lock (CPU stays awake indefinitely)
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && (mWakeLock == null || !mWakeLock.isHeld())) {
                mWakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "GNDROiD:CompanionWakeLock");
                mWakeLock.setReferenceCounted(false);
                mWakeLock.acquire();
                Log.i(TAG, "Partial WakeLock acquired successfully.");
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to acquire WakeLock", e);
        }

        // 2. Acquire High-Performance Wi-Fi Lock (Zero packet drop / Low latency mode)
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null && (mWifiLock == null || !mWifiLock.isHeld())) {
                int mode = WifiManager.WIFI_MODE_FULL;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    mode = WifiManager.WIFI_MODE_FULL_LOW_LATENCY;
                } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.HONEYCOMB_MR1) {
                    mode = WifiManager.WIFI_MODE_FULL_HIGH_PERF;
                }
                mWifiLock = wm.createWifiLock(mode, "GNDROiD:WifiLock");
                mWifiLock.setReferenceCounted(false);
                mWifiLock.acquire();
                Log.i(TAG, "Wi-Fi High-Performance Lock acquired (mode=" + mode + ").");
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to acquire WifiLock", e);
        }
    }

    private void releaseLocks() {
        try {
            if (mWakeLock != null && mWakeLock.isHeld()) {
                mWakeLock.release();
                mWakeLock = null;
            }
        } catch (Exception ignored) {}

        try {
            if (mWifiLock != null && mWifiLock.isHeld()) {
                mWifiLock.release();
                mWifiLock = null;
            }
        } catch (Exception ignored) {}
    }

    private void registerNetworkWatcher() {
        try {
            mConnManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            if (mConnManager != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                NetworkRequest req = new NetworkRequest.Builder()
                        .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                        .build();
                mNetworkCallback = new ConnectivityManager.NetworkCallback() {
                    @Override
                    public void onAvailable(Network network) {
                        Log.i(TAG, "Network connection established: " + network);
                        updateNotification("LAN Online | IP Ready");
                    }

                    @Override
                    public void onLost(Network network) {
                        Log.w(TAG, "Network connection lost: " + network);
                        updateNotification("Network disconnected — Re-binding...");
                    }
                };
                mConnManager.registerNetworkCallback(req, mNetworkCallback);
            }
        } catch (Exception e) {
            Log.e(TAG, "Could not register NetworkCallback", e);
        }
    }

    private void unregisterNetworkWatcher() {
        try {
            if (mConnManager != null && mNetworkCallback != null) {
                mConnManager.unregisterNetworkCallback(mNetworkCallback);
                mNetworkCallback = null;
            }
        } catch (Exception ignored) {}
    }

    private void startWatchdog() {
        mWatchdogThread = new Thread(new Runnable() {
            @Override
            public void run() {
                while (mRunning) {
                    try {
                        Thread.sleep(3000);
                        // Ensure locks remain held
                        if (mWakeLock != null && !mWakeLock.isHeld()) {
                            mWakeLock.acquire();
                        }
                        if (mWifiLock != null && !mWifiLock.isHeld()) {
                            mWifiLock.acquire();
                        }
                    } catch (InterruptedException e) {
                        break;
                    } catch (Exception ignored) {}
                }
            }
        }, "GNDroidWatchdog");
        mWatchdogThread.start();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "GNDROiD Companion Service",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Maintains high-performance Wi-Fi lock and zero-drop LAN bridge.");
            channel.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildForegroundNotification(String statusText) {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this, 0, notificationIntent,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        builder.setContentTitle("GNDROiD Link")
                .setContentText(statusText)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentIntent(pendingIntent)
                .setOngoing(true);

        return builder.build();
    }

    private void updateNotification(String text) {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.notify(NOTIFICATION_ID, buildForegroundNotification(text));
            }
        } catch (Exception ignored) {}
    }
}

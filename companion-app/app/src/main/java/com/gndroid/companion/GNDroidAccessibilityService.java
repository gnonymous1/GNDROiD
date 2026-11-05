package com.gndroid.companion;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Path;
import android.os.Build;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;

/**
 * GNDROiD Accessibility Service
 * Provides low-latency programmatic touch injection and system navigation
 * without requiring ADB root or desktop touch emulation overhead.
 */
public class GNDroidAccessibilityService extends AccessibilityService {

    private static final String TAG = "GNDroidA11y";
    private static volatile GNDroidAccessibilityService sInstance = null;

    public static GNDroidAccessibilityService getInstance() {
        return sInstance;
    }

    public static boolean isAvailable() {
        return sInstance != null;
    }

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        sInstance = this;
        Log.i(TAG, "GNDROiD Accessibility Service connected and ready for touch injection.");
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Passive listener
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "GNDROiD Accessibility Service interrupted.");
    }

    @Override
    public boolean onUnbind(android.content.Intent intent) {
        sInstance = null;
        return super.onUnbind(intent);
    }

    /**
     * Executes a global system action (BACK, HOME, RECENTS, NOTIFICATIONS, etc.)
     */
    public boolean performGlobal(int action) {
        try {
            return performGlobalAction(action);
        } catch (Exception e) {
            Log.e(TAG, "Failed to perform global action " + action, e);
            return false;
        }
    }

    /**
     * Programmatically injects a tap at (x, y) coordinates.
     */
    public boolean injectTap(float x, float y) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            return false;
        }
        try {
            Path path = new Path();
            path.moveTo(x, y);
            GestureDescription.StrokeDescription stroke =
                    new GestureDescription.StrokeDescription(path, 0, 50);
            GestureDescription.Builder builder = new GestureDescription.Builder();
            builder.addStroke(stroke);
            return dispatchGesture(builder.build(), null, null);
        } catch (Exception e) {
            Log.e(TAG, "Error injecting tap at (" + x + ", " + y + ")", e);
            return false;
        }
    }

    /**
     * Programmatically injects a swipe gesture from (x1, y1) to (x2, y2).
     */
    public boolean injectSwipe(float x1, float y1, float x2, float y2, long durationMs) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            return false;
        }
        try {
            Path path = new Path();
            path.moveTo(x1, y1);
            path.lineTo(x2, y2);
            long dur = Math.max(50, Math.min(durationMs, 2000));
            GestureDescription.StrokeDescription stroke =
                    new GestureDescription.StrokeDescription(path, 0, dur);
            GestureDescription.Builder builder = new GestureDescription.Builder();
            builder.addStroke(stroke);
            return dispatchGesture(builder.build(), null, null);
        } catch (Exception e) {
            Log.e(TAG, "Error injecting swipe", e);
            return false;
        }
    }
}

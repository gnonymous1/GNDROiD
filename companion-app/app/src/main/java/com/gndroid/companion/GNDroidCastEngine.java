package com.gndroid.companion;

import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.projection.MediaProjection;
import android.os.Build;
import android.util.Log;
import android.view.Surface;

import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * GNDROiD Hardware MediaCodec Low-Latency Video Cast Engine
 * Captures display buffer via MediaProjection/VirtualDisplay, encodes hardware H.264 (AVC)
 * or H.265 (HEVC) at 30-120 FPS and 4-64 Mbps, and streams low-latency Annex-B NAL units
 * directly over TCP port 51886.
 */
public class GNDroidCastEngine {

    private static final String TAG = "GNDroidCast";
    public static final int VIDEO_PORT = 51886;

    private MediaCodec mEncoder;
    private Surface mInputSurface;
    private VirtualDisplay mVirtualDisplay;
    private MediaProjection mMediaProjection;
    private ServerSocket mServerSocket;
    private final AtomicBoolean mIsStreaming = new AtomicBoolean(false);
    private Thread mStreamingThread;

    private int mWidth = 1080;
    private int mHeight = 2400;
    private int mBitrate = 16_000_000; // 16 Mbps default
    private int mFps = 60;
    private String mMimeType = "video/avc"; // H.264 default

    public GNDroidCastEngine() {}

    public void configure(int width, int height, int bitrate, int fps, boolean useH265) {
        mWidth = width > 0 ? width : 1080;
        mHeight = height > 0 ? height : 2400;
        mBitrate = bitrate > 0 ? bitrate : 16_000_000;
        mFps = fps > 0 ? fps : 60;
        mMimeType = useH265 ? "video/hevc" : "video/avc";
    }

    public void setMediaProjection(MediaProjection projection) {
        mMediaProjection = projection;
    }

    public synchronized boolean start() {
        if (mIsStreaming.get()) return true;

        try {
            mServerSocket = new ServerSocket(VIDEO_PORT);
            mServerSocket.setReuseAddress(true);
            mIsStreaming.set(true);

            mStreamingThread = new Thread(new Runnable() {
                @Override
                public void run() {
                    listenAndStream();
                }
            }, "GNDroidCast-Worker");
            mStreamingThread.start();
            Log.i(TAG, "GNDROiD Cast Engine initialized on port " + VIDEO_PORT);
            return true;
        } catch (Exception e) {
            Log.e(TAG, "Failed to start Cast Engine", e);
            stop();
            return false;
        }
    }

    public synchronized void stop() {
        mIsStreaming.set(false);
        try {
            if (mServerSocket != null && !mServerSocket.isClosed()) {
                mServerSocket.close();
            }
        } catch (Exception ignored) {}

        if (mStreamingThread != null) {
            mStreamingThread.interrupt();
            mStreamingThread = null;
        }

        cleanupEncoder();
        Log.i(TAG, "GNDROiD Cast Engine stopped.");
    }

    private void listenAndStream() {
        while (mIsStreaming.get() && mServerSocket != null && !mServerSocket.isClosed()) {
            try {
                Socket client = mServerSocket.accept();
                client.setTcpNoDelay(true);
                client.setSendBufferSize(256 * 1024);
                Log.i(TAG, "PC Client connected for direct video stream: " + client.getRemoteSocketAddress());
                streamToClient(client);
            } catch (Exception e) {
                if (!mIsStreaming.get()) break;
            }
        }
    }

    private void streamToClient(Socket socket) {
        OutputStream out = null;
        try {
            out = socket.getOutputStream();
            initEncoder();

            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
            byte[] header = null;

            while (mIsStreaming.get() && socket.isConnected() && !socket.isClosed()) {
                int outputBufferId = mEncoder.dequeueOutputBuffer(bufferInfo, 10000);
                if (outputBufferId >= 0) {
                    ByteBuffer outputBuffer = mEncoder.getOutputBuffer(outputBufferId);
                    if (outputBuffer != null) {
                        outputBuffer.position(bufferInfo.offset);
                        outputBuffer.limit(bufferInfo.offset + bufferInfo.size);

                        byte[] data = new byte[bufferInfo.size];
                        outputBuffer.get(data);

                        // Save SPS/PPS config header
                        if ((bufferInfo.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                            header = data.clone();
                        } else {
                            // Prepend header to keyframes if required
                            if ((bufferInfo.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0 && header != null) {
                                out.write(header);
                            }
                            out.write(data);
                            out.flush();
                        }
                    }
                    mEncoder.releaseOutputBuffer(outputBufferId, false);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Direct video streaming client disconnected: " + e.getMessage());
        } finally {
            cleanupEncoder();
            try {
                if (out != null) out.close();
                socket.close();
            } catch (Exception ignored) {}
        }
    }

    private void initEncoder() throws Exception {
        cleanupEncoder();
        MediaFormat format = MediaFormat.createVideoFormat(mMimeType, mWidth, mHeight);
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        format.setInteger(MediaFormat.KEY_BIT_RATE, mBitrate);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, mFps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1); // 1 keyframe per second
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            format.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);
        }

        mEncoder = MediaCodec.createEncoderByType(mMimeType);
        mEncoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        mInputSurface = mEncoder.createInputSurface();
        mEncoder.start();

        if (mMediaProjection != null) {
            mVirtualDisplay = mMediaProjection.createVirtualDisplay(
                    "GNDROiD-VirtualDisplay",
                    mWidth, mHeight, 400,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    mInputSurface, null, null);
        }
    }

    private void cleanupEncoder() {
        try {
            if (mVirtualDisplay != null) {
                mVirtualDisplay.release();
                mVirtualDisplay = null;
            }
        } catch (Exception ignored) {}

        try {
            if (mInputSurface != null) {
                mInputSurface.release();
                mInputSurface = null;
            }
        } catch (Exception ignored) {}

        try {
            if (mEncoder != null) {
                mEncoder.stop();
                mEncoder.release();
                mEncoder = null;
            }
        } catch (Exception ignored) {}
    }

    public boolean isStreaming() {
        return mIsStreaming.get();
    }
}

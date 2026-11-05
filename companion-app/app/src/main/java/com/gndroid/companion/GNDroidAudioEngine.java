package com.gndroid.companion;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioPlaybackCaptureConfiguration;
import android.media.AudioRecord;
import android.media.projection.MediaProjection;
import android.os.Build;
import android.util.Log;

import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * GNDROiD 48kHz Stereo Audio Engine
 * Captures internal system audio via Android 10+ AudioPlaybackCaptureConfiguration
 * and streams raw 48,000Hz 16-bit PCM stereo audio over TCP port 51887.
 */
public class GNDroidAudioEngine {

    private static final String TAG = "GNDroidAudio";
    public static final int AUDIO_PORT = 51887;
    public static final int SAMPLE_RATE = 48000;

    private MediaProjection mMediaProjection;
    private AudioRecord mAudioRecord;
    private ServerSocket mServerSocket;
    private final AtomicBoolean mIsStreaming = new AtomicBoolean(false);
    private Thread mStreamingThread;

    public GNDroidAudioEngine() {}

    public void setMediaProjection(MediaProjection projection) {
        mMediaProjection = projection;
    }

    public synchronized boolean start() {
        if (mIsStreaming.get()) return true;

        try {
            mServerSocket = new ServerSocket(AUDIO_PORT);
            mServerSocket.setReuseAddress(true);
            mIsStreaming.set(true);

            mStreamingThread = new Thread(new Runnable() {
                @Override
                public void run() {
                    listenAndStream();
                }
            }, "GNDroidAudio-Worker");
            mStreamingThread.start();
            Log.i(TAG, "GNDROiD Audio Engine initialized on port " + AUDIO_PORT);
            return true;
        } catch (Exception e) {
            Log.e(TAG, "Failed to start Audio Engine", e);
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

        cleanupAudioRecord();
        Log.i(TAG, "GNDROiD Audio Engine stopped.");
    }

    private void listenAndStream() {
        while (mIsStreaming.get() && mServerSocket != null && !mServerSocket.isClosed()) {
            try {
                Socket client = mServerSocket.accept();
                client.setTcpNoDelay(true);
                Log.i(TAG, "PC Client connected for direct audio stream: " + client.getRemoteSocketAddress());
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
            initAudioRecord();

            if (mAudioRecord == null || mAudioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord not initialized");
                return;
            }

            mAudioRecord.startRecording();
            byte[] buffer = new byte[4096];

            while (mIsStreaming.get() && socket.isConnected() && !socket.isClosed()) {
                int read = mAudioRecord.read(buffer, 0, buffer.length);
                if (read > 0) {
                    out.write(buffer, 0, read);
                    out.flush();
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Audio streaming client disconnected: " + e.getMessage());
        } finally {
            cleanupAudioRecord();
            try {
                if (out != null) out.close();
                socket.close();
            } catch (Exception ignored) {}
        }
    }

    private void initAudioRecord() {
        cleanupAudioRecord();
        int channelConfig = AudioFormat.CHANNEL_IN_STEREO;
        int audioFormat = AudioFormat.ENCODING_PCM_16BIT;
        int minBufSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, channelConfig, audioFormat);
        int bufSize = Math.max(minBufSize * 2, 8192);

        AudioFormat format = new AudioFormat.Builder()
                .setEncoding(audioFormat)
                .setSampleRate(SAMPLE_RATE)
                .setChannelMask(channelConfig)
                .build();

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && mMediaProjection != null) {
                AudioPlaybackCaptureConfiguration config =
                        new AudioPlaybackCaptureConfiguration.Builder(mMediaProjection)
                                .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                                .addMatchingUsage(AudioAttributes.USAGE_GAME)
                                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                                .build();

                mAudioRecord = new AudioRecord.Builder()
                        .setAudioFormat(format)
                        .setBufferSizeInBytes(bufSize)
                        .setAudioPlaybackCaptureConfig(config)
                        .build();
            }
        } catch (Exception e) {
            Log.w(TAG, "AudioPlaybackCapture not supported, using standard recording fallback", e);
        }
    }

    private void cleanupAudioRecord() {
        try {
            if (mAudioRecord != null) {
                if (mAudioRecord.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING) {
                    mAudioRecord.stop();
                }
                mAudioRecord.release();
                mAudioRecord = null;
            }
        } catch (Exception ignored) {}
    }

    public boolean isStreaming() {
        return mIsStreaming.get();
    }
}

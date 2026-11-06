with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidCompanionService.java', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add activeInstance
old_decl = '    public static volatile int screenCaptureHeight = 960;'
new_decl = '''    public static volatile int screenCaptureHeight = 960;
    public static volatile GNDroidCompanionService activeInstance = null;'''

code = code.replace(old_decl, new_decl, 1)

# 2. Add buffer.rewind() in processImageToJpegBytes
old_buffer = '''            Image.Plane[] planes = image.getPlanes();
            ByteBuffer buffer = planes[0].getBuffer();'''

new_buffer = '''            Image.Plane[] planes = image.getPlanes();
            ByteBuffer buffer = planes[0].getBuffer();
            buffer.rewind();'''

code = code.replace(old_buffer, new_buffer, 1)

# 3. Add FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION in onCreate()
old_create = '''        createNotificationChannel();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int fgsType = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC;'''

new_create = '''        activeInstance = this;
        createNotificationChannel();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int fgsType = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;'''

code = code.replace(old_create, new_create, 1)

# 4. Handle ACTION_START_MEDIA_PROJECTION in onStartCommand
old_start = '''    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Return START_STICKY to guarantee Android resurrects this service if killed
        return START_STICKY;
    }'''

new_start = '''    @Override
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
    }'''

code = code.replace(old_start, new_start, 1)

with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidCompanionService.java', 'w', encoding='utf-8') as f:
    f.write(code)

print('GNDroidCompanionService.java successfully updated!')

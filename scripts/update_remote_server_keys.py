with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidRemoteServer.java', 'r', encoding='utf-8') as f:
    code = f.read()

target = """                case "swipe":
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
                    return false;"""

replacement = """                case "swipe":
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
                case "key":
                    if (a11y != null) {
                        String text = params.optString("text", "");
                        return a11y.injectText(text);
                    }
                    return false;
                case "backspace":
                    if (a11y != null) {
                        return a11y.injectBackspace();
                    }
                    return false;
                case "enter":
                    if (a11y != null) {
                        return a11y.injectText("\\n");
                    }
                    return false;"""

if target in code:
    code = code.replace(target, replacement, 1)
    with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidRemoteServer.java', 'w', encoding='utf-8') as f:
        f.write(code)
    print("GNDroidRemoteServer.java updated with key/backspace/enter handlers!")
else:
    print("Target block not found in GNDroidRemoteServer.java")

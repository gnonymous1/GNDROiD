with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidAccessibilityService.java', 'r', encoding='utf-8') as f:
    code = f.read()

# Check imports
if "import android.os.Bundle;" not in code:
    code = code.replace("import android.view.accessibility.AccessibilityNodeInfo;", "import android.view.accessibility.AccessibilityNodeInfo;\nimport android.os.Bundle;")

text_methods = """
    public boolean injectText(String text) {
        if (text == null || text.isEmpty()) return false;
        try {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return false;
            AccessibilityNodeInfo focus = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (focus == null) {
                focus = root.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY);
            }
            if (focus != null) {
                CharSequence existing = focus.getText();
                String newText = (existing != null ? existing.toString() : "") + text;
                Bundle args = new Bundle();
                args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, newText);
                boolean res = focus.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                focus.recycle();
                root.recycle();
                return res;
            }
            root.recycle();
        } catch (Exception ignored) {}
        return false;
    }

    public boolean injectBackspace() {
        try {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return false;
            AccessibilityNodeInfo focus = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (focus != null) {
                CharSequence existing = focus.getText();
                if (existing != null && existing.length() > 0) {
                    String newText = existing.subSequence(0, existing.length() - 1).toString();
                    Bundle args = new Bundle();
                    args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, newText);
                    boolean res = focus.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                    focus.recycle();
                    root.recycle();
                    return res;
                }
                focus.recycle();
            }
            root.recycle();
        } catch (Exception ignored) {}
        return false;
    }
"""

idx = code.rfind('}')
new_code = code[:idx] + text_methods + "\n}\n"

with open(r'companion-app\app\src\main\java\com\gndroid\companion\GNDroidAccessibilityService.java', 'w', encoding='utf-8') as f:
    f.write(new_code)

print("GNDroidAccessibilityService.java updated with text/backspace injection.")

package org.lala.client;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import org.kivy.android.PythonActivity;

/**
 * Opt-in touch overlay attached to the existing foreground-service process.
 * The window is not a second service. Only masked, non-credential status is shown.
 */
public final class FloatingOverlay {
    private static final String PREFS = "wlre_overlay";
    private static final String ENABLED = "enabled";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static WindowManager windows;
    private static WindowManager.LayoutParams position;
    private static LinearLayout root;
    private static LinearLayout panel;
    private static TextView ball;
    private static TextView detail;
    private static String lastStatus = "";
    private static boolean expanded = false;

    private FloatingOverlay() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean isEnabled(Context context) {
        return prefs(context).getBoolean(ENABLED, false) && Settings.canDrawOverlays(context);
    }

    public static boolean setEnabled(Context context, boolean enabled) {
        if (enabled && !Settings.canDrawOverlays(context)) return false;
        prefs(context).edit().putBoolean(ENABLED, enabled).apply();
        Context app = context.getApplicationContext();
        MAIN.post(() -> {
            if (isEnabled(app)) show(app);
            else removeWindow();
        });
        return true;
    }

    public static void restore(Context context) {
        if (!Settings.canDrawOverlays(context)) {
            // Do not silently reactivate after a revoked special permission.
            prefs(context).edit().putBoolean(ENABLED, false).apply();
            return;
        }
        if (isEnabled(context)) {
            Context app = context.getApplicationContext();
            MAIN.post(() -> { if (isEnabled(app)) show(app); });
        }
    }

    /** Remove the window on service shutdown without changing opt-in preference. */
    public static void destroy(Context context) {
        MAIN.post(FloatingOverlay::removeWindow);
    }

    public static void updateStatus(Context context, String statusJson) {
        if (!isEnabled(context) || statusJson == null || statusJson.length() > 8192) return;
        if (statusJson.equals(lastStatus)) return;
        lastStatus = statusJson;
        Context app = context.getApplicationContext();
        MAIN.post(() -> {
            if (!isEnabled(app)) { removeWindow(); return; }
            show(app);
            render(statusJson);
        });
    }

    private static int dp(Context context, float value) {
        return (int) (value * context.getResources().getDisplayMetrics().density + 0.5f);
    }

    private static GradientDrawable background(int color, int radius, int stroke, int strokeColor) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radius);
        if (stroke > 0) drawable.setStroke(stroke, strokeColor);
        return drawable;
    }

    private static TextView text(Context context, int size, int color) {
        TextView view = new TextView(context);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private static void show(Context context) {
        if (root != null || !Settings.canDrawOverlays(context)) return;
        try {
            windows = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
            if (windows == null) return;
            root = new LinearLayout(context);
            root.setOrientation(LinearLayout.VERTICAL);

            ball = text(context, 17, Color.WHITE);
            ball.setText("✦\n0");
            ball.setGravity(Gravity.CENTER);
            ball.setBackground(background(0xff173a65, dp(context, 36), dp(context, 2), 0xff52c6eb));
            ball.setElevation(dp(context, 8));
            root.addView(ball, new LinearLayout.LayoutParams(dp(context, 58), dp(context, 58)));

            panel = new LinearLayout(context);
            panel.setOrientation(LinearLayout.VERTICAL);
            panel.setPadding(dp(context, 14), dp(context, 10), dp(context, 14), dp(context, 12));
            panel.setBackground(background(0xf520304a, dp(context, 16), dp(context, 1), 0xff4b8fbc));
            panel.setElevation(dp(context, 8));
            LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(dp(context, 286), -2);
            pp.topMargin = dp(context, 6);
            root.addView(panel, pp);

            TextView heading = text(context, 16, 0xffa5eaff);
            heading.setText("飄流 RE:LaLa｜連線狀態");
            panel.addView(heading);
            detail = text(context, 13, Color.WHITE);
            detail.setText("等待連線狀態同步");
            LinearLayout.LayoutParams dpLine = new LinearLayout.LayoutParams(-1, -2);
            dpLine.topMargin = dp(context, 8);
            dpLine.bottomMargin = dp(context, 8);
            panel.addView(detail, dpLine);

            TextView open = text(context, 14, 0xff87e5ff);
            open.setText("返回 LaLa 主畫面  ›");
            open.setPadding(0, dp(context, 6), 0, dp(context, 6));
            open.setOnClickListener(v -> {
                Intent intent = new Intent(context, PythonActivity.class);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                context.startActivity(intent);
                collapse();
            });
            panel.addView(open);
            TextView hide = text(context, 13, 0xffc9d5e3);
            hide.setText("隱藏懸浮小球（不斷線）");
            hide.setPadding(0, dp(context, 6), 0, dp(context, 4));
            hide.setOnClickListener(v -> setEnabled(context, false));
            panel.addView(hide);
            panel.setVisibility(View.GONE);

            position = new WindowManager.LayoutParams(
                -2, -2, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                    | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT);
            position.gravity = Gravity.TOP | Gravity.START;
            position.x = prefs(context).getInt("x", dp(context, 12));
            position.y = prefs(context).getInt("y", dp(context, 128));
            clamp(context);
            ball.setOnTouchListener(new View.OnTouchListener() {
                float downX, downY;
                int firstX, firstY;
                boolean dragged;
                final int slop = ViewConfiguration.get(context).getScaledTouchSlop();

                @Override public boolean onTouch(View v, MotionEvent event) {
                    if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                        downX = event.getRawX();
                        downY = event.getRawY();
                        firstX = position.x;
                        firstY = position.y;
                        dragged = false;
                        return true;
                    }
                    if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
                        int dx = Math.round(event.getRawX() - downX);
                        int dy = Math.round(event.getRawY() - downY);
                        if (Math.abs(dx) > slop || Math.abs(dy) > slop) dragged = true;
                        if (dragged && root != null) {
                            position.x = firstX + dx;
                            position.y = firstY + dy;
                            clamp(context);
                            windows.updateViewLayout(root, position);
                        }
                        return true;
                    }
                    if (event.getActionMasked() == MotionEvent.ACTION_UP) {
                        if (!dragged) toggle(context);
                        else prefs(context).edit().putInt("x", position.x).putInt("y", position.y).apply();
                        return true;
                    }
                    return true;
                }
            });
            windows.addView(root, position);
            if (!lastStatus.isEmpty()) render(lastStatus);
        } catch (RuntimeException error) {
            // Never crash the foreground service if the system rejects an overlay.
            removeWindow();
        }
    }

    private static void toggle(Context context) {
        if (panel == null || root == null) return;
        expanded = !expanded;
        panel.setVisibility(expanded ? View.VISIBLE : View.GONE);
        clamp(context);
        try { windows.updateViewLayout(root, position); }
        catch (RuntimeException ignored) { removeWindow(); }
    }

    private static void collapse() {
        expanded = false;
        if (panel != null) panel.setVisibility(View.GONE);
    }

    private static void clamp(Context context) {
        if (position == null || windows == null) return;
        DisplayMetrics metrics = new DisplayMetrics();
        windows.getDefaultDisplay().getMetrics(metrics);
        int width = root != null && expanded ? dp(context, 286) : dp(context, 58);
        int height = root != null && expanded ? dp(context, 350) : dp(context, 58);
        position.x = Math.max(0, Math.min(position.x, Math.max(0, metrics.widthPixels - width)));
        position.y = Math.max(0, Math.min(position.y, Math.max(0, metrics.heightPixels - height)));
    }

    private static void render(String data) {
        if (root == null || ball == null || detail == null) return;
        try {
            JSONObject state = new JSONObject(data);
            int online = state.optInt("online", 0);
            int active = state.optInt("active", 0);
            int total = state.optInt("total", 0);
            ball.setText("✦\n" + online);
            StringBuilder lines = new StringBuilder();
            lines.append("在線 ").append(online).append(" / 活動 ").append(active)
                 .append(" / 總數 ").append(total);
            JSONArray accounts = state.optJSONArray("accounts");
            if (accounts != null) {
                for (int i = 0; i < Math.min(accounts.length(), 6); i++) {
                    JSONObject account = accounts.optJSONObject(i);
                    if (account == null) continue;
                    lines.append("\n\n").append(account.optString("name", "帳號"))
                        .append(" · ").append(account.optString("server", ""))
                        .append("\n").append(account.optString("connection", "未知"))
                        .append("｜").append(account.optString("battle", "AI 未啟用"));
                }
            }
            if (total > 6) lines.append("\n\n另有 ").append(total - 6).append(" 個帳號");
            if (total == 0) lines.append("\n\n尚無遊戲連線");
            detail.setText(lines.toString());
        } catch (Exception ignored) {
            detail.setText("狀態暫時無法更新");
        }
    }

    private static void removeWindow() {
        if (root != null && windows != null) {
            try { windows.removeViewImmediate(root); }
            catch (RuntimeException ignored) {}
        }
        root = null;
        panel = null;
        ball = null;
        detail = null;
        position = null;
        windows = null;
        expanded = false;
    }
}

package org.lala.client;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import org.kivy.android.PythonActivity;

/**
 * Opt-in role-overview bubble owned by the existing foreground service.
 * The bubble uses the actual installed application's launcher icon.
 * Only credential-free, bounded game status enters this window.
 */
public final class FloatingOverlay {
    private static final String PREFS = "wlre_overlay";
    private static final String ENABLED = "enabled";
    private static final int NAVY = 0xff0c1730;
    private static final int CARD = 0xff182b47;
    private static final int CYAN = 0xff67daf1;
    private static final int MUTED = 0xffacbfd6;
    private static final int GREEN = 0xff55dbb0;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static WindowManager windows;
    private static WindowManager.LayoutParams position;
    private static LinearLayout root;
    private static FrameLayout ball;
    private static TextView badge;
    private static LinearLayout panel;
    private static LinearLayout list;
    private static ScrollView scroller;
    private static TextView totalLine;
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
            prefs(context).edit().putBoolean(ENABLED, false).apply();
            return;
        }
        Context app = context.getApplicationContext();
        if (isEnabled(app)) MAIN.post(() -> { if (isEnabled(app)) show(app); });
    }

    /** Hide the overlay when the service terminates, without ending any sessions here. */
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
            render(app, statusJson);
        });
    }

    private static int dp(Context context, float value) {
        return (int) (value * context.getResources().getDisplayMetrics().density + 0.5f);
    }

    private static GradientDrawable rounded(int fill, int radius, int stroke, int strokeColor) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(radius);
        if (stroke > 0) drawable.setStroke(stroke, strokeColor);
        return drawable;
    }

    private static GradientDrawable circle(int fill, int stroke, int strokeColor) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setShape(GradientDrawable.OVAL);
        drawable.setColor(fill);
        if (stroke > 0) drawable.setStroke(stroke, strokeColor);
        return drawable;
    }

    private static TextView text(Context context, String value, int size, int color) {
        TextView v = new TextView(context);
        v.setText(value);
        v.setTextSize(size);
        v.setTextColor(color);
        v.setGravity(Gravity.CENTER_VERTICAL);
        v.setIncludeFontPadding(false);
        return v;
    }

    private static void show(Context context) {
        if (root != null || !Settings.canDrawOverlays(context)) return;
        try {
            windows = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
            if (windows == null) return;
            root = new LinearLayout(context);
            root.setOrientation(LinearLayout.VERTICAL);

            // The same drawable is used as the application's launcher icon.
            ball = new FrameLayout(context);
            ball.setBackground(circle(0xff123456, dp(context, 2), CYAN));
            ball.setElevation(dp(context, 12));
            ImageView icon = new ImageView(context);
            try {
                Drawable launcher = context.getPackageManager()
                    .getApplicationIcon(context.getPackageName());
                icon.setImageDrawable(launcher);
            } catch (Exception ignored) {
                icon.setImageResource(android.R.drawable.sym_def_app_icon);
            }
            icon.setScaleType(ImageView.ScaleType.CENTER_CROP);
            icon.setBackground(circle(NAVY, 0, Color.TRANSPARENT));
            icon.setClipToOutline(true);
            FrameLayout.LayoutParams imagePosition = new FrameLayout.LayoutParams(
                dp(context, 48), dp(context, 48), Gravity.CENTER);
            ball.addView(icon, imagePosition);

            badge = text(context, "0", 11, NAVY);
            badge.setGravity(Gravity.CENTER);
            badge.setBackground(circle(CYAN, dp(context, 1), NAVY));
            FrameLayout.LayoutParams badgePosition = new FrameLayout.LayoutParams(
                dp(context, 23), dp(context, 23), Gravity.BOTTOM | Gravity.RIGHT);
            badgePosition.rightMargin = dp(context, -2);
            badgePosition.bottomMargin = dp(context, -1);
            ball.addView(badge, badgePosition);
            root.addView(ball, new LinearLayout.LayoutParams(dp(context, 60), dp(context, 60)));

            buildPanel(context);
            position = new WindowManager.LayoutParams(
                -2, -2, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                    | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT);
            position.gravity = Gravity.TOP | Gravity.LEFT;
            position.x = prefs(context).getInt("x", dp(context, 12));
            position.y = prefs(context).getInt("y", dp(context, 120));
            clamp(context);
            ball.setOnTouchListener(new View.OnTouchListener() {
                float downX, downY;
                int firstX, firstY;
                boolean dragged;
                final int slop = ViewConfiguration.get(context).getScaledTouchSlop();

                @Override public boolean onTouch(View v, MotionEvent event) {
                    if (position == null || windows == null || root == null) return false;
                    switch (event.getActionMasked()) {
                        case MotionEvent.ACTION_DOWN:
                            downX = event.getRawX();
                            downY = event.getRawY();
                            firstX = position.x;
                            firstY = position.y;
                            dragged = false;
                            return true;
                        case MotionEvent.ACTION_MOVE:
                            int deltaX = Math.round(event.getRawX() - downX);
                            int deltaY = Math.round(event.getRawY() - downY);
                            if (Math.abs(deltaX) > slop || Math.abs(deltaY) > slop) dragged = true;
                            if (dragged) {
                                position.x = firstX + deltaX;
                                position.y = firstY + deltaY;
                                clamp(context);
                                try { windows.updateViewLayout(root, position); }
                                catch (RuntimeException ignored) { removeWindow(); }
                            }
                            return true;
                        case MotionEvent.ACTION_UP:
                            if (!dragged) toggle(context);
                            else prefs(context).edit()
                                .putInt("x", position.x).putInt("y", position.y).apply();
                            return true;
                        default:
                            return true;
                    }
                }
            });
            windows.addView(root, position);
            if (!lastStatus.isEmpty()) render(context, lastStatus);
        } catch (RuntimeException ignored) {
            // Overlay display errors must never stop the foreground game service.
            removeWindow();
        }
    }

    private static void buildPanel(Context context) {
        DisplayMetrics screen = new DisplayMetrics();
        windows.getDefaultDisplay().getMetrics(screen);
        int width = Math.max(dp(context, 180), Math.min(dp(context, 336),
            screen.widthPixels - dp(context, 22)));
        int scrollHeight = Math.max(dp(context, 150), Math.min(dp(context, 360),
            screen.heightPixels - dp(context, 330)));

        panel = new LinearLayout(context);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(context, 14), dp(context, 14), dp(context, 14), dp(context, 12));
        panel.setBackground(rounded(0xf60c1931, dp(context, 20), dp(context, 1), 0xff3e7399));
        panel.setElevation(dp(context, 14));
        LinearLayout.LayoutParams panelPosition = new LinearLayout.LayoutParams(width, -2);
        panelPosition.topMargin = dp(context, 8);
        root.addView(panel, panelPosition);

        LinearLayout heading = new LinearLayout(context);
        heading.setGravity(Gravity.CENTER_VERTICAL);
        heading.setOrientation(LinearLayout.HORIZONTAL);
        ImageView appIcon = new ImageView(context);
        try {
            appIcon.setImageDrawable(context.getPackageManager()
                .getApplicationIcon(context.getPackageName()));
        } catch (Exception ignored) {
            appIcon.setImageResource(android.R.drawable.sym_def_app_icon);
        }
        appIcon.setScaleType(ImageView.ScaleType.FIT_CENTER);
        heading.addView(appIcon, new LinearLayout.LayoutParams(dp(context, 34), dp(context, 34)));
        TextView title = text(context, "  角色概況", 19, Color.WHITE);
        title.setTypeface(null, 1);
        heading.addView(title, new LinearLayout.LayoutParams(0, dp(context, 36), 1));
        TextView close = text(context, "⌄", 25, CYAN);
        close.setGravity(Gravity.CENTER);
        close.setOnClickListener(v -> collapse(context));
        heading.addView(close, new LinearLayout.LayoutParams(dp(context, 36), dp(context, 36)));
        panel.addView(heading);

        totalLine = text(context, "連線狀態同步中", 12, CYAN);
        totalLine.setPadding(0, dp(context, 8), 0, dp(context, 12));
        panel.addView(totalLine);

        scroller = new ScrollView(context);
        scroller.setFillViewport(false);
        scroller.setVerticalScrollBarEnabled(true);
        list = new LinearLayout(context);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(0, dp(context, 3), dp(context, 4), dp(context, 3));
        scroller.addView(list);
        panel.addView(scroller, new LinearLayout.LayoutParams(-1, scrollHeight));

        LinearLayout actions = new LinearLayout(context);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        actions.setPadding(0, dp(context, 12), 0, 0);
        TextView open = action(context, "返回 LaLa", CYAN);
        open.setOnClickListener(v -> {
            try {
                Intent intent = new Intent(context, PythonActivity.class);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                context.startActivity(intent);
                collapse(context);
            } catch (RuntimeException ignored) { /* no changes to session service */ }
        });
        actions.addView(open, new LinearLayout.LayoutParams(0, dp(context, 42), 1));
        TextView hide = action(context, "隱藏小球", MUTED);
        hide.setOnClickListener(v -> setEnabled(context, false));
        LinearLayout.LayoutParams hideSize = new LinearLayout.LayoutParams(0, dp(context, 42), 1);
        hideSize.leftMargin = dp(context, 8);
        actions.addView(hide, hideSize);
        panel.addView(actions);
        panel.setVisibility(View.GONE);
    }

    private static TextView action(Context context, String title, int color) {
        TextView action = text(context, title, 13, color);
        action.setGravity(Gravity.CENTER);
        action.setBackground(rounded(0xff1b3453, dp(context, 12),
            dp(context, 1), 0xff365c7a));
        return action;
    }

    private static void toggle(Context context) {
        if (panel == null || root == null) return;
        expanded = !expanded;
        panel.setVisibility(expanded ? View.VISIBLE : View.GONE);
        relayout(context);
    }

    private static void collapse(Context context) {
        expanded = false;
        if (panel != null) panel.setVisibility(View.GONE);
        relayout(context);
    }

    private static void relayout(Context context) {
        if (windows == null || position == null || root == null) return;
        clamp(context);
        try { windows.updateViewLayout(root, position); }
        catch (RuntimeException ignored) { removeWindow(); }
    }

    private static void clamp(Context context) {
        if (position == null || windows == null) return;
        DisplayMetrics screen = new DisplayMetrics();
        windows.getDefaultDisplay().getMetrics(screen);
        int width = expanded && panel != null ? Math.max(dp(context, 60),
            Math.min(dp(context, 336), screen.widthPixels - dp(context, 22))) : dp(context, 60);
        int height = expanded && panel != null ? Math.min(
            screen.heightPixels - dp(context, 20), dp(context, 550)) : dp(context, 60);
        position.x = Math.max(0, Math.min(position.x, Math.max(0, screen.widthPixels - width)));
        position.y = Math.max(0, Math.min(position.y, Math.max(0, screen.heightPixels - height)));
    }

    private static void render(Context context, String json) {
        if (root == null || badge == null || list == null || totalLine == null) return;
        try {
            JSONObject data = new JSONObject(json);
            int online = data.optInt("online", 0);
            int active = data.optInt("active", 0);
            int total = data.optInt("total", 0);
            badge.setText(online > 99 ? "99+" : String.valueOf(online));
            badge.setBackground(circle(online > 0 ? GREEN : CYAN, dp(context, 1), NAVY));
            totalLine.setText("● 在線 " + online + "   ·   活動 " + active + "   ·   帳號 " + total);
            int scrollTop = scroller != null ? scroller.getScrollY() : 0;
            list.removeAllViews();
            JSONArray accounts = data.optJSONArray("accounts");
            if (accounts != null) {
                for (int i = 0; i < Math.min(accounts.length(), 6); i++) {
                    JSONObject account = accounts.optJSONObject(i);
                    if (account != null) addAccountCard(context, account);
                }
            }
            if (total == 0) addPlaceholder(context, "尚無遊戲連線", "登入角色後顯示角色概況");
            if (total > 6) addPlaceholder(context, "另有 " + (total - 6) + " 個帳號", "請返回 LaLa 查看完整清單");
            if (scroller != null) scroller.post(() -> scroller.scrollTo(0, scrollTop));
        } catch (Exception ignored) {
            list.removeAllViews();
            addPlaceholder(context, "狀態暫時無法更新", "請返回 LaLa 主畫面確認");
        }
    }

    private static void addAccountCard(Context context, JSONObject account) {
        LinearLayout card = new LinearLayout(context);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(context, 12), dp(context, 11),
            dp(context, 12), dp(context, 12));
        card.setBackground(rounded(CARD, dp(context, 14), dp(context, 1), 0xff315477));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.bottomMargin = dp(context, 10);
        list.addView(card, lp);

        TextView accountName = text(context, account.optString("name", "角色狀態"), 16, CYAN);
        accountName.setTypeface(null, 1);
        card.addView(accountName);
        TextView server = text(context,
            account.optString("server", "") + "  ·  " + account.optString("connection", "未知"),
            12, MUTED);
        server.setPadding(0, dp(context, 4), 0, dp(context, 9));
        card.addView(server);

        JSONObject overview = account.optJSONObject("overview");
        if (overview == null) {
            TextView waiting = text(context, "角色概況：待角色入場同步", 13, MUTED);
            card.addView(waiting);
            TextView battle = text(context, account.optString("battle", "AI 未運作"), 12, MUTED);
            battle.setPadding(0, dp(context, 6), 0, 0);
            card.addView(battle);
            return;
        }
        JSONArray profiles = overview.optJSONArray("profiles");
        if (profiles != null) {
            for (int i = 0; i < profiles.length(); i++) {
                JSONObject profile = profiles.optJSONObject(i);
                if (profile != null) addProfile(context, card, profile);
            }
        }
        int additional = overview.optInt("remaining_profiles", 0);
        if (additional > 0) {
            TextView extra = text(context, "另外 " + additional + " 位夥伴請到角色概況查看", 11, MUTED);
            extra.setPadding(0, dp(context, 5), 0, 0);
            card.addView(extra);
        }
        JSONObject statuses = overview.optJSONObject("statuses");
        if (statuses != null) {
            addRule(context, card);
            addStatus(context, card, "自動戰鬥", statuses.optString("battle", "待同步"), CYAN);
            addStatus(context, card, "自動徘徊", statuses.optString("roaming", "待同步"), CYAN);
            addStatus(context, card, "事件", statuses.optString("event", "待同步"), MUTED);
        }
        addRule(context, card);
        TextView expTitle = text(context, "經驗效率", 13, CYAN);
        expTitle.setTypeface(null, 1);
        card.addView(expTitle);
        JSONArray efficiency = overview.optJSONArray("efficiency");
        if (efficiency == null || efficiency.length() == 0) {
            addStatus(context, card, "統計", "等待有效戰鬥樣本", MUTED);
        } else {
            for (int i = 0; i < efficiency.length(); i++) {
                JSONObject entry = efficiency.optJSONObject(i);
                if (entry == null) continue;
                addStatus(context, card, entry.optString("name", "角色"),
                    entry.optString("average", "等待樣本"), MUTED);
                addStatus(context, card, "近10場", entry.optString("recent10", "等待樣本"), MUTED);
                addStatus(context, card, "近30場", entry.optString("recent30", "等待樣本"), MUTED);
            }
        }
    }

    private static void addProfile(Context context, LinearLayout card, JSONObject profile) {
        TextView title = text(context,
            profile.optString("name", "角色") + "  Lv." + profile.optString("level", "—"),
            13, Color.WHITE);
        title.setPadding(0, dp(context, 10), 0, dp(context, 5));
        title.setTypeface(null, 1);
        card.addView(title);
        addVital(context, card, "HP", profile.optString("hp", "—"),
            profile.optString("max_hp", "—"), 0xfffc7e87);
        addVital(context, card, "SP", profile.optString("sp", "—"),
            profile.optString("max_sp", "—"), 0xff7eafff);
    }

    private static void addVital(Context context, LinearLayout card, String label,
                                 String current, String maximum, int color) {
        LinearLayout row = new LinearLayout(context);
        row.setGravity(Gravity.CENTER_VERTICAL);
        TextView value = text(context, label + "  " + current + "/" + maximum, 11, MUTED);
        row.addView(value, new LinearLayout.LayoutParams(0, dp(context, 18), 1));
        ProgressBar bar = new ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        bar.setProgress(Math.round(1000f * ratio(current, maximum)));
        bar.setProgressTintList(ColorStateList.valueOf(color));
        bar.setProgressBackgroundTintList(ColorStateList.valueOf(0xff2d4460));
        row.addView(bar, new LinearLayout.LayoutParams(dp(context, 98), dp(context, 5)));
        card.addView(row, new LinearLayout.LayoutParams(-1, dp(context, 23)));
    }

    private static float ratio(String current, String maximum) {
        try {
            float n = Float.parseFloat(current);
            float d = Float.parseFloat(maximum);
            return d > 0 ? Math.max(0, Math.min(n / d, 1)) : 0;
        } catch (NumberFormatException ignored) {
            return 0; // missing stats never become fake HP/SP
        }
    }

    private static void addRule(Context context, LinearLayout card) {
        View divider = new View(context);
        divider.setBackgroundColor(0xff315477);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, dp(context, 1));
        lp.topMargin = dp(context, 12);
        lp.bottomMargin = dp(context, 7);
        card.addView(divider, lp);
    }

    private static void addStatus(Context context, LinearLayout card,
                                  String title, String value, int color) {
        TextView label = text(context, title + "：", 12, color);
        TextView line = text(context, value, 12, 0xffdde9f8);
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams labelWidth = new LinearLayout.LayoutParams(dp(context, 71), -2);
        row.addView(label, labelWidth);
        row.addView(line, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = dp(context, 7);
        card.addView(row, lp);
    }

    private static void addPlaceholder(Context context, String title, String subtitle) {
        TextView line = text(context, title + "\n" + subtitle, 13, MUTED);
        line.setPadding(dp(context, 12), dp(context, 18), dp(context, 12), dp(context, 18));
        line.setBackground(rounded(CARD, dp(context, 14), dp(context, 1), 0xff315477));
        list.addView(line);
    }

    private static void removeWindow() {
        if (root != null && windows != null) {
            try { windows.removeViewImmediate(root); }
            catch (RuntimeException ignored) {}
        }
        windows = null;
        position = null;
        root = null;
        ball = null;
        badge = null;
        panel = null;
        scroller = null;
        list = null;
        totalLine = null;
        expanded = false;
    }
}

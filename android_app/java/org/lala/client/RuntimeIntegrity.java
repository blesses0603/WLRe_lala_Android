package org.lala.client;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import java.security.MessageDigest;

/**
 * Phase07 runtime signer pin. This Java code is compiled into the Android APK.
 *
 * The build injects ONLY the public certificate SHA-256 fingerprint into the
 * temporary staging copy, never the private signing key. Unconfigured local
 * builds intentionally fail closed at startup instead of silently trusting
 * an unpinned signer.
 *
 * Repacking attackers can patch client code; this is a defense-in-depth
 * consistency check, not attestation, anti-root, or anti-hook protection.
 */
public final class RuntimeIntegrity {
    private RuntimeIntegrity() {}

    private static final String EXPECTED_PACKAGE = "org.lala.client.wlrelala";
    private static final String EXPECTED_CERT_SHA256 = "__WLRE_SIGNER_PIN__";

    public static String status(Context context) {
        if (context == null) return "CONTEXT_UNAVAILABLE";
        if (!EXPECTED_CERT_SHA256.matches("[0-9a-f]{64}")) return "UNPINNED";
        if (!EXPECTED_PACKAGE.equals(context.getPackageName())) return "PACKAGE_MISMATCH";
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return "UNSUPPORTED_API";
        try {
            PackageManager pm = context.getPackageManager();
            PackageInfo packageInfo = pm.getPackageInfo(
                EXPECTED_PACKAGE, PackageManager.GET_SIGNING_CERTIFICATES
            );
            if (packageInfo == null || packageInfo.signingInfo == null ||
                packageInfo.signingInfo.hasMultipleSigners()) {
                return "MULTIPLE_OR_MISSING_SIGNERS";
            }
            Signature[] current = packageInfo.signingInfo.getApkContentsSigners();
            if (current == null || current.length != 1) {
                return "MULTIPLE_OR_MISSING_SIGNERS";
            }
            byte[] cert = MessageDigest.getInstance("SHA-256").digest(current[0].toByteArray());
            byte[] pinned = decodeFingerprint(EXPECTED_CERT_SHA256);
            if (pinned == null || !MessageDigest.isEqual(cert, pinned)) {
                return "SIGNER_MISMATCH";
            }
            return "OK";
        } catch (Exception exception) {
            // Exception text and certificate details must not enter the app log.
            return "VERIFY_FAILED";
        }
    }

    private static byte[] decodeFingerprint(String hex) {
        if (hex == null || !hex.matches("[0-9a-f]{64}")) return null;
        byte[] data = new byte[32];
        for (int i = 0; i < data.length; i++) {
            int hi = Character.digit(hex.charAt(i * 2), 16);
            int lo = Character.digit(hex.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) return null;
            data[i] = (byte) ((hi << 4) | lo);
        }
        return data;
    }
}

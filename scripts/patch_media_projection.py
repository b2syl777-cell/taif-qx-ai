from pathlib import Path

p = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/ScreenCaptureService.kt")
s = p.read_text()

if "import android.os.Handler" not in s:
    s = s.replace("import android.os.IBinder\n", "import android.os.IBinder\nimport android.os.Handler\nimport android.os.Looper\nimport android.content.pm.ServiceInfo\n")

if "private var projectionCallback:" not in s:
    s = s.replace(
        "    private var imageReader: ImageReader? = null\n",
        "    private var imageReader: ImageReader? = null\n    private var projectionCallback: MediaProjection.Callback? = null\n"
    )

s = s.replace(
    "        startForeground(NOTIFICATION_ID, createNotification())",
    """        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, createNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIFICATION_ID, createNotification())
        }"""
)

old = """            mediaProjection = mpManager.getMediaProjection(resultCode, data)
            setupVirtualDisplay()"""
new = """            mediaProjection = mpManager.getMediaProjection(resultCode, data)
            // Android 14+ requires a callback to be registered before creating a virtual display.
            projectionCallback = object : MediaProjection.Callback() {
                override fun onStop() {
                    virtualDisplay?.release()
                    virtualDisplay = null
                    imageReader?.close()
                    imageReader = null
                    mediaProjection = null
                }
            }
            mediaProjection?.registerCallback(projectionCallback!!, Handler(Looper.getMainLooper()))
            setupVirtualDisplay()"""
if old in s:
    s = s.replace(old, new)
elif "registerCallback(projectionCallback!!" not in s:
    raise SystemExit("Could not find MediaProjection initialization block; refusing unsafe patch.")

p.write_text(s)
print("Patched Android MediaProjection callback and foreground service type.")

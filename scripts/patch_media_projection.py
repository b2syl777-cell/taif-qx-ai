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


# Add a clearly visible one-tap SCAN NOW button to the main dashboard.
home = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ui/screens/HomeScreen.kt")
hs = home.read_text()
if "onScanNow: () -> Unit" not in hs:
    hs = hs.replace(
        "    onToggleFloatingService: () -> Unit\n",
        "    onToggleFloatingService: () -> Unit,\n    onScanNow: () -> Unit\n"
    )
    marker = """        // Market & Timeframe Selector
"""
    button = """        // Main one-tap chart scan action
        Button(
            onClick = onScanNow,
            modifier = Modifier.fillMaxWidth().height(62.dp),
            colors = ButtonDefaults.buttonColors(containerColor = CyberCyan, contentColor = DarkBackground),
            shape = RoundedCornerShape(14.dp)
        ) {
            Icon(Icons.Default.CenterFocusStrong, contentDescription = null)
            Spacer(modifier = Modifier.width(10.dp))
            Text("SCAN NOW • GET SIGNAL", fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
        }

"""
    if marker not in hs:
        raise SystemExit("HomeScreen insertion point not found")
    hs = hs.replace(marker, button + marker, 1)
    home.write_text(hs)

# Wire the dashboard button to start/trigger the floating scanner service.
activity = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/MainActivity.kt")
asrc = activity.read_text()
asrc = asrc.replace(
    "                                onToggleFloatingService = { toggleFloatingService() }\n",
    "                                onToggleFloatingService = { toggleFloatingService() },\n                                onScanNow = { scanNow() }\n"
)
if "private fun scanNow()" not in asrc:
    insert_before = "    private fun toggleFloatingService() {"
    scan_method = """    private fun scanNow() {
        if (!hasOverlayPermission) {
            requestOverlayPermission()
            Toast.makeText(this, "Allow Display over other apps, then tap SCAN NOW again.", Toast.LENGTH_LONG).show()
            return
        }
        if (!isProjectionRunning) {
            requestProjectionPermission()
            Toast.makeText(this, "After allowing screen capture, tap SCAN NOW again.", Toast.LENGTH_LONG).show()
            return
        }
        isFloatingServiceRunning = true
        val scanIntent = Intent(this, FloatingScannerService::class.java).apply {
            action = FloatingScannerService.ACTION_SCAN
        }
        startService(scanIntent)
    }

"""
    if insert_before not in asrc:
        raise SystemExit("MainActivity insertion point not found")
    asrc = asrc.replace(insert_before, scan_method + insert_before, 1)
activity.write_text(asrc)

# Let the service queue a scan until the MediaProjection binder is connected.
service = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
fs = service.read_text()
if "private var pendingScan = false" not in fs:
    fs = fs.replace(
        "    private var isBound = false\n",
        "    private var isBound = false\n    private var pendingScan = false\n"
    )
    fs = fs.replace(
        "            isBound = true\n",
        "            isBound = true\n            if (pendingScan) { pendingScan = false; onScanTriggered() }\n",
        1
    )
    insert_before = "    override fun onBind(intent: Intent?): IBinder? = null\n"
    start_command = """    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_SCAN) {
            if (isBound && screenCaptureService != null) {
                onScanTriggered()
            } else {
                pendingScan = true
            }
        }
        return START_STICKY
    }

"""
    if insert_before not in fs:
        raise SystemExit("FloatingScannerService onBind insertion point not found")
    fs = fs.replace(insert_before, start_command + insert_before, 1)
    if "companion object {" in fs:
        fs = fs.replace(
            "    companion object {",
            "    companion object {\n        const val ACTION_SCAN = \"com.taif.qxai.action.SCAN_NOW\"",
            1
        )
    else:
        fs = fs.replace(
            "class FloatingScannerService : Service() {",
            "class FloatingScannerService : Service() {\n    companion object { const val ACTION_SCAN = \"com.taif.qxai.action.SCAN_NOW\" }",
            1
        )
service.write_text(fs)

print("Added dashboard SCAN NOW button and queued scan action.")

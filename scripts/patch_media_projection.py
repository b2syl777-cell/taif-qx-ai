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
        "    private var isBound = false" + chr(10),
        "    private var isBound = false" + chr(10) + "    private var pendingScan = false" + chr(10)
    )
    fs = fs.replace(
        "            isBound = true" + chr(10),
        "            isBound = true" + chr(10) + "            if (pendingScan) { pendingScan = false; onScanTriggered() }" + chr(10),
        1
    )
    insert_before = "    override fun onBind(intent: Intent?): IBinder? = null" + chr(10)
    start_command = """    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_SCAN) {
            if (isBound && screenCaptureService != null) onScanTriggered()
            else pendingScan = true
        }
        return START_STICKY
    }

"""
    if insert_before not in fs:
        raise SystemExit("FloatingScannerService onBind insertion point not found")
    fs = fs.replace(insert_before, start_command + insert_before, 1)

if "const val ACTION_SCAN" not in fs:
    fs = fs.replace(
        "class FloatingScannerService : Service() {",
        "class FloatingScannerService : Service() {" + chr(10) + '    companion object { const val ACTION_SCAN = "com.taif.qxai.action.SCAN_NOW" }',
        1
    )
service.write_text(fs)


# Do not silently fall back to Local AI when Gemini API fails.
service = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
fs = service.read_text()
old_call = '''            val geminiResult = withContext(Dispatchers.IO) {
                geminiRepo.analyzeChartImage(bitmap, "OTC", "EUR/USD (OTC)", "1M").getOrNull()
            }'''
new_call = '''            val geminiResponse = withContext(Dispatchers.IO) {
                geminiRepo.analyzeChartImage(bitmap, "OTC", "EUR/USD (OTC)", "1M")
            }
            val geminiResult = geminiResponse.getOrElse { error ->
                showSimpleResult(
                    "GEMINI API FAILED",
                    error.message ?: "Gemini request failed. Check internet and API access.",
                    Color.parseColor("#FF1744")
                )
                return@launch
            }'''
if old_call in fs:
    fs = fs.replace(old_call, new_call, 1)
elif "val geminiResponse = withContext(Dispatchers.IO)" not in fs:
    raise SystemExit("Could not find Gemini result block; refusing to patch.")
service.write_text(fs)

# Gemini 3.x responses can contain non-text parts before the answer; select the first text part.
repo = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ai/GeminiAnalysisRepository.kt")
gs = repo.read_text()
old_extract = '''            val textOutput = candidates[0].asJsonObject
                .getAsJsonObject("content")
                .getAsJsonArray("parts")[0].asJsonObject
                .get("text").asString'''
new_extract = '''            val responseParts = candidates[0].asJsonObject
                .getAsJsonObject("content")
                .getAsJsonArray("parts")
            val textOutput = responseParts
                .firstOrNull { part ->
                    part.isJsonObject && part.asJsonObject.has("text") &&
                        !part.asJsonObject.get("text").isJsonNull
                }
                ?.asJsonObject
                ?.get("text")
                ?.asString
                ?: return@withContext Result.failure(Exception("Gemini returned no readable text. Check API/model response."))'''
if old_extract in gs:
    gs = gs.replace(old_extract, new_extract, 1)
elif "val responseParts = candidates[0]" not in gs:
    raise SystemExit("Could not find Gemini response parser; refusing to patch.")
repo.write_text(gs)
print("Gemini failures will now be shown instead of silently using Local AI; response parsing is more robust.")

print("Added dashboard SCAN NOW button, action constant, queued scan action, and Gemini API diagnostics.")


# Reliability patch: wait briefly for a fresh MediaProjection frame and always show
# a visible status/error message instead of silently appearing to do nothing.
from pathlib import Path as _Path
_fp = _Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_fs = _fp.read_text()

_start = _fs.find("    private fun captureAndProcess() {")
_end = _fs.find("    private fun triggerHaptic(", _start)
if _start < 0 or _end < 0:
    raise SystemExit("Could not locate captureAndProcess() safely.")

_new_func = """    private fun captureAndProcess() {
        serviceScope.launch {
            showSimpleResult("SCANNING...", "Capturing chart and starting AI analysis. Please wait.", Color.parseColor("#00E5FF"))
            val bitmap = withContext(Dispatchers.IO) {
                var captured: Bitmap? = null
                repeat(18) {
                    captured = screenCaptureService?.captureCurrentScreen()
                    if (captured != null) return@withContext captured
                    delay(180)
                }
                captured
            }
            if (bitmap == null) {
                showSimpleResult(
                    "SCREEN NOT READY",
                    "No fresh screen frame received. Reopen Taif QX AI, allow screen capture, then scan again.",
                    Color.parseColor("#FF1744")
                )
                return@launch
            }

            val localResult = withContext(Dispatchers.Default) {
                LocalChartAnalyzer.analyzeBitmap(bitmap)
            }

            val sharedPrefs = getSharedPreferences("taif_qx_prefs", Context.MODE_PRIVATE)
            val apiKey = sharedPrefs.getString("gemini_api_key", "") ?: ""
            val geminiRepo = GeminiAnalysisRepository { apiKey }
            val geminiResponse = withContext(Dispatchers.IO) {
                geminiRepo.analyzeChartImage(bitmap, "OTC", "EUR/USD (OTC)", "1M")
            }
            val geminiResult = geminiResponse.getOrNull()

            val finalSignal = DualEngineConsensus.combineResults(
                local = localResult,
                gemini = geminiResult,
                marketType = MarketType.OTC,
                pair = "EUR/USD (OTC)",
                timeframe = "1M"
            )

            triggerHaptic(finalSignal.finalSignal)
            showResultCard(finalSignal)
            if (geminiResult == null) {
                val reason = geminiResponse.exceptionOrNull()?.message ?: "Gemini API did not return a result."
                android.widget.Toast.makeText(
                    applicationContext,
                    "Local analysis shown; Gemini unavailable: " + reason.take(180),
                    android.widget.Toast.LENGTH_LONG
                ).show()
            }
        }
    }

"""
_fs = _fs[:_start] + _new_func + _fs[_end:]

# The previous implementation of showSimpleResult() was empty, so scan failures
# were completely invisible. Replace it with a visible Android toast.
_old_simple = """    private fun showSimpleResult(title: String, message: String, color: Int) {
        // Simple error or info notification card
    }"""
_new_simple = """    private fun showSimpleResult(title: String, message: String, color: Int) {
        android.widget.Toast.makeText(
            applicationContext,
            "$title\\n$message",
            android.widget.Toast.LENGTH_LONG
        ).show()
    }"""
if _old_simple in _fs:
    _fs = _fs.replace(_old_simple, _new_simple, 1)
elif "private fun showSimpleResult(title: String, message: String, color: Int)" not in _fs:
    raise SystemExit("Could not locate showSimpleResult() safely.")
_fp.write_text(_fs)
print("Added scan-frame retries and visible scan/API status messages.")

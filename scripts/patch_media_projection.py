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


# Advanced chart reading: screenshot asset detection, expanded indicators and one scan per tap.
from pathlib import Path as _P
_model = _P("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/model/TradingModels.kt")
_ms = _model.read_text()
_ms = _ms.replace(
    '    val bollingerPosition: String = "INSIDE"\n)',
    '''    val bollingerPosition: String = "INSIDE",
    val adxValue: Double = 0.0,
    val atrState: String = "NOT_VISIBLE",
    val stochasticK: Double = 50.0,
    val vwapPosition: String = "NOT_VISIBLE",
    val volumeTrend: String = "NOT_VISIBLE",
    val ichimokuTrend: String = "NOT_VISIBLE",
    val fibonacciZone: String = "NOT_VISIBLE"
)'''
)
_ms = _ms.replace(
    '    val indicators: IndicatorData = IndicatorData()\n)',
    '''    val indicators: IndicatorData = IndicatorData(),
    val assetName: String = "Asset not detected",
    val marketName: String = "Market not detected",
    val detectedTimeframe: String = "Timeframe not detected"
)'''
)
_model.write_text(_ms)

_repo = _P("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ai/GeminiAnalysisRepository.kt")
_rs = _repo.read_text()
_prompt_start = _rs.find('            val prompt = """')
_prompt_end = _rs.find('            """.trimIndent()', _prompt_start)
if _prompt_start < 0 or _prompt_end < 0:
    raise SystemExit("Gemini prompt block not found.")
_prompt = '''            val prompt = """
                You are a careful visual chart-reading assistant. Analyze ONLY what is genuinely visible.
                Identify the exact asset/pair and market label printed in the screenshot. Never assume EUR/USD.
                If the label is cropped or unreadable return "Asset not detected". Read visible timeframe or return "Timeframe not detected".
                Examine latest candles, swing highs/lows and trend structure. Check EMA 9/21/50/200, RSI 14,
                MACD line/signal/histogram, Bollinger squeeze/expansion, VWAP, ATR volatility, ADX strength,
                Stochastic K/D, Ichimoku cloud, volume spikes, support/resistance, breakout/retest,
                Fibonacci retracement only when swing anchors are visible.
                Identify bullish/bearish engulfing, hammer, hanging man, shooting star, morning/evening star,
                doji, dragonfly/gr avestone doji, inside bar, pin bar, marubozu, tweezer top/bottom,
                three soldiers/crows, candle body/wick ratio and rejection wicks.
                Do not invent numeric readings or report indicators that are not visible; use NOT_VISIBLE.
                Do not infer news or real-time prices from an image. CALL/PUT only if multiple visible factors agree;
                otherwise NO_SIGNAL. Confidence is a cautious visual score, not win probability.
                Return JSON only:
                {"signal":"CALL|PUT|NO_SIGNAL","confidence":0,
                 "assetName":"exact visible asset or Asset not detected",
                 "marketName":"exact visible market label or Market not detected",
                 "detectedTimeframe":"visible timeframe or Timeframe not detected",
                 "patterns":["..."],"summary":"evidence-based reasoning",
                 "emaTrend":"BULLISH|BEARISH|NEUTRAL|NOT_VISIBLE","rsiValue":50,
                 "macdCondition":"BULLISH|BEARISH|NEUTRAL|NOT_VISIBLE",
                 "bollingerPosition":"UPPER|LOWER|MIDDLE|NOT_VISIBLE",
                 "adxValue":0,"atrState":"LOW|NORMAL|HIGH|NOT_VISIBLE",
                 "stochasticK":50,"vwapPosition":"ABOVE|BELOW|AT|NOT_VISIBLE",
                 "volumeTrend":"RISING|FALLING|AVERAGE|NOT_VISIBLE",
                 "ichimokuTrend":"BULLISH|BEARISH|NEUTRAL|NOT_VISIBLE",
                 "fibonacciZone":"38.2%|50%|61.8%|NOT_VISIBLE"}
            '''.rstrip()
_rs = _rs[:_prompt_start] + _prompt + _rs[_prompt_end+len('            """.trimIndent()'):]
_old_text = '''            val textOutput = candidates[0].asJsonObject
                .getAsJsonObject("content")
                .getAsJsonArray("parts")[0].asJsonObject
                .get("text").asString'''
if _old_text in _rs:
    _rs = _rs.replace(_old_text, '''            val responseParts = candidates[0].asJsonObject.getAsJsonObject("content").getAsJsonArray("parts")
            val textOutput = responseParts.firstOrNull {
                it.isJsonObject && it.asJsonObject.has("text") && !it.asJsonObject.get("text").isJsonNull
            }?.asJsonObject?.get("text")?.asString
                ?: return@withContext Result.failure(Exception("Gemini returned no readable text."))''', 1)
_rs = _rs.replace(
    '            val bollingerPosition = parsedOutput.get("bollingerPosition")?.asString ?: "INSIDE"\n',
    '''            val bollingerPosition = parsedOutput.get("bollingerPosition")?.asString ?: "NOT_VISIBLE"
            val assetName = parsedOutput.get("assetName")?.asString ?: "Asset not detected"
            val marketName = parsedOutput.get("marketName")?.asString ?: "Market not detected"
            val detectedTimeframe = parsedOutput.get("detectedTimeframe")?.asString ?: "Timeframe not detected"
            fun jsonString(key: String) = parsedOutput.get(key)?.takeIf { !it.isJsonNull }?.asString ?: "NOT_VISIBLE"
            fun jsonDouble(key: String, fallback: Double = 0.0) = parsedOutput.get(key)?.takeIf { !it.isJsonNull }?.asDouble ?: fallback
'''
)
_rs = _rs.replace(
    '''                        bollingerPosition = bollingerPosition
                    )
                )''',
    '''                        bollingerPosition = bollingerPosition,
                        adxValue = jsonDouble("adxValue"),
                        atrState = jsonString("atrState"),
                        stochasticK = jsonDouble("stochasticK", 50.0),
                        vwapPosition = jsonString("vwapPosition"),
                        volumeTrend = jsonString("volumeTrend"),
                        ichimokuTrend = jsonString("ichimokuTrend"),
                        fibonacciZone = jsonString("fibonacciZone")
                    ),
                    assetName = assetName,
                    marketName = marketName,
                    detectedTimeframe = detectedTimeframe
                )'''
)
_repo.write_text(_rs)

_service = _P("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_ss = _service.read_text()
if "import kotlinx.coroutines.sync.withLock" not in _ss:
    _ss = _ss.replace("import kotlinx.coroutines.*\n", "import kotlinx.coroutines.*\nimport kotlinx.coroutines.sync.withLock\n")
if "private val scanMutex" not in _ss:
    _ss = _ss.replace(
        "    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())",
        "    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())\n    private val scanMutex = kotlinx.coroutines.sync.Mutex()"
    )
_beg = _ss.find("    private fun captureAndProcess() {")
_fin = _ss.find("    private fun triggerHaptic(", _beg)
if _beg < 0 or _fin < 0:
    raise SystemExit("captureAndProcess() boundaries not found.")
_new_capture = '''    private var activeScanJob: Job? = null

    private fun captureAndProcess() {
        // Latest tap wins: cancel an older scan and immediately start fresh.
        activeScanJob?.cancel()
        activeScanJob = serviceScope.launch {
                showSimpleResult("SCANNING...", "Reading this screen and detecting its market label...", Color.parseColor("#00E5FF"))
                val bitmap = withContext(Dispatchers.IO) {
                    var captured: Bitmap? = null
                    repeat(20) {
                        captured = screenCaptureService?.captureCurrentScreen()
                        if (captured != null) return@withContext captured
                        delay(150)
                    }
                    captured
                }
                if (bitmap == null) {
                    showSimpleResult("CAPTURE FAILED", "No screen frame arrived. Re-enable screen capture and try again.", Color.parseColor("#FF1744"))
                    return@withLock
                }
                val localResult = withContext(Dispatchers.Default) { LocalChartAnalyzer.analyzeBitmap(bitmap) }
                val sharedPrefs = getSharedPreferences("taif_qx_prefs", Context.MODE_PRIVATE)
                val apiKey = sharedPrefs.getString("gemini_api_key", "") ?: ""
                val geminiRepo = GeminiAnalysisRepository { apiKey }
                val geminiResponse = withContext(Dispatchers.IO) {
                    geminiRepo.analyzeChartImage(bitmap, "AUTO_DETECT", "DETECT_FROM_SCREENSHOT", "AUTO_DETECT")
                }
                val geminiResult = geminiResponse.getOrNull()
                val detectedPair = geminiResult?.assetName
                    ?.takeIf { it.isNotBlank() && !it.equals("Asset not detected", true) }
                    ?: "Asset not detected in screenshot"
                val detectedTimeframe = geminiResult?.detectedTimeframe
                    ?.takeIf { it.isNotBlank() && !it.equals("Timeframe not detected", true) }
                    ?: "Timeframe not detected"
                val detectedMarket = geminiResult?.marketName ?: "Market not detected"
                val marketType = when {
                    detectedMarket.contains("OTC", true) -> MarketType.OTC
                    detectedPair.contains("BTC", true) || detectedPair.contains("ETH", true) -> MarketType.CRYPTO
                    else -> MarketType.FOREX
                }
                val finalSignal = DualEngineConsensus.combineResults(
                    local = localResult,
                    gemini = geminiResult,
                    marketType = marketType,
                    pair = detectedPair,
                    timeframe = detectedTimeframe
                )
                triggerHaptic(finalSignal.finalSignal)
                showResultCard(finalSignal)
                if (geminiResult == null) {
                    val reason = geminiResponse.exceptionOrNull()?.message ?: "Gemini analysis unavailable"
                    android.widget.Toast.makeText(applicationContext, "Gemini unavailable; screenshot asset cannot be verified. " + reason.take(140), android.widget.Toast.LENGTH_LONG).show()
                } else if (detectedPair == "Asset not detected in screenshot") {
                    android.widget.Toast.makeText(applicationContext, "Market label is not readable in this screenshot.", android.widget.Toast.LENGTH_LONG).show()
                }
        }
    }

'''
_ss = _ss[:_beg] + _new_capture + _ss[_fin:]
_marker = '''            // Summary
            val summaryText = TextView(this@FloatingScannerService).apply {'''
_add = '''            // Expanded indicator checklist; NOT_VISIBLE means the screenshot did not expose it.
            val advanced = signal.geminiAnalysis?.indicators ?: signal.localAnalysis.indicators
            val indicatorText = TextView(this@FloatingScannerService).apply {
                text = "EMA: " + advanced.emaTrend + " | RSI: " + advanced.rsiValue + " | MACD: " + advanced.macdCondition + "\\n" +
                    "Bollinger: " + advanced.bollingerPosition + " | ADX: " + advanced.adxValue + " | ATR: " + advanced.atrState + "\\n" +
                    "Stochastic K: " + advanced.stochasticK + " | VWAP: " + advanced.vwapPosition + "\\n" +
                    "Volume: " + advanced.volumeTrend + " | Ichimoku: " + advanced.ichimokuTrend + " | Fib: " + advanced.fibonacciZone
                setTextColor(Color.parseColor("#B7C8DC"))
                textSize = 10f
                setPadding(0, (6 * density).toInt(), 0, (6 * density).toInt())
            }
            addView(indicatorText)

            // Summary
            val summaryText = TextView(this@FloatingScannerService).apply {'''
if _marker in _ss:
    _ss = _ss.replace(_marker, _add, 1)
_service.write_text(_ss)
print("Added screenshot asset detection, expanded visible-indicator analysis, and one fresh scan per tap.")


# Ensure the generated Kotlin raw prompt string is explicitly closed before request construction.
from pathlib import Path as _PromptPath
_prompt_file = _PromptPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ai/GeminiAnalysisRepository.kt")
_prompt_source = _prompt_file.read_text()
_prompt_req = _prompt_source.find("            val requestJson = JsonObject()")
_prompt_decl = _prompt_source.find("            val prompt = \"\"\"")
if _prompt_decl >= 0 and _prompt_req > _prompt_decl:
    _prompt_segment = _prompt_source[_prompt_decl:_prompt_req]
    if not _prompt_segment.rstrip().endswith('\"\"\"'):
        _prompt_source = _prompt_source[:_prompt_req] + '            \"\"\"\n\n' + _prompt_source[_prompt_req:]
        _prompt_file.write_text(_prompt_source)


# User-selected real/OTC market and custom expiry/timeframe controls.
from pathlib import Path as _UiPath
_model_ui = _UiPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/model/TradingModels.kt")
_model_ui_text = _model_ui.read_text()
_model_ui_text = _model_ui_text.replace('FOREX("Forex")', 'FOREX("Real Market (Forex)")')
_model_ui.write_text(_model_ui_text)

_home_ui = _UiPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ui/screens/HomeScreen.kt")
_home_ui_text = _home_ui.read_text()
if "import android.content.Context" not in _home_ui_text:
    _home_ui_text = _home_ui_text.replace("package com.taif.qxai.ui.screens\n", "package com.taif.qxai.ui.screens\n\nimport android.content.Context\n", 1)
if "import androidx.compose.ui.platform.LocalContext" not in _home_ui_text:
    _home_ui_text = _home_ui_text.replace("import androidx.compose.ui.Modifier\n", "import androidx.compose.ui.Modifier\nimport androidx.compose.ui.platform.LocalContext\n", 1)

_old_state = '''    var selectedMarket by remember { mutableStateOf(MarketType.OTC) }
    var selectedTimeframe by remember { mutableStateOf("1M") }'''
_new_state = '''    val appContext = LocalContext.current
    val prefs = remember { appContext.getSharedPreferences("taif_qx_prefs", Context.MODE_PRIVATE) }
    val initialMarket = remember {
        runCatching { MarketType.valueOf(prefs.getString("selected_market_type", "OTC") ?: "OTC") }
            .getOrDefault(MarketType.OTC)
    }
    var selectedMarket by remember { mutableStateOf(initialMarket) }
    var selectedTimeframe by remember { mutableStateOf(prefs.getString("selected_timeframe", "1M") ?: "1M") }
    var customTimeframe by remember { mutableStateOf("") }
    val customTimeframes = remember {
        mutableStateListOf<String>().apply {
            addAll(prefs.getStringSet("custom_timeframes", emptySet()) ?: emptySet())
        }
    }
    LaunchedEffect(selectedMarket, selectedTimeframe) {
        prefs.edit()
            .putString("selected_market_type", selectedMarket.name)
            .putString("selected_timeframe", selectedTimeframe)
            .apply()
    }'''
if _old_state in _home_ui_text:
    _home_ui_text = _home_ui_text.replace(_old_state, _new_state, 1)
elif "var customTimeframe by remember" not in _home_ui_text:
    raise SystemExit("HomeScreen state anchor missing; refusing UI patch.")

_home_ui_text = _home_ui_text.replace(
    'listOf("1M", "2M", "5M").forEach { tf ->',
    'listOf("5s", "10s", "15s", "30s").forEach { tf ->',
    1
)
_custom_ui = '''                Text(
                    text = "MINUTE PRESETS",
                    style = MaterialTheme.typography.bodyLarge,
                    color = TextSecondary
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf("1M", "2M", "5M").forEach { tf ->
                        FilterChip(
                            selected = selectedTimeframe == tf,
                            onClick = { selectedTimeframe = tf },
                            label = { Text(tf, fontWeight = FontWeight.Bold) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = NeonGreen,
                                selectedLabelColor = DarkBackground
                            )
                        )
                    }
                }

                Text("CUSTOM EXPIRY (examples: 45s, 3m)", color = TextSecondary, fontSize = 12.sp)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = customTimeframe,
                        onValueChange = { customTimeframe = it.filter { ch -> ch.isDigit() || ch == 's' || ch == 'S' || ch == 'm' || ch == 'M' }.take(4) },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        label = { Text("e.g. 45s or 3m") }
                    )
                    Button(
                        onClick = {
                            val candidate = customTimeframe.trim().lowercase()
                            if (Regex("^[1-9][0-9]{0,2}(s|m)$").matches(candidate)) {
                                if (!customTimeframes.contains(candidate)) customTimeframes.add(candidate)
                                prefs.edit().putStringSet("custom_timeframes", customTimeframes.toSet()).apply()
                                selectedTimeframe = candidate
                                customTimeframe = ""
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = CyberCyan, contentColor = DarkBackground)
                    ) { Text("ADD") }
                }
                if (customTimeframes.isNotEmpty()) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        customTimeframes.forEach { tf ->
                            FilterChip(
                                selected = selectedTimeframe == tf,
                                onClick = { selectedTimeframe = tf },
                                label = { Text(tf, fontWeight = FontWeight.Bold) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = NeonGreen,
                                    selectedLabelColor = DarkBackground
                                )
                            )
                        }
                    }
                }
'''
_anchor = '''        // AI Architecture Info Card'''
if "CUSTOM EXPIRY (examples: 45s, 3m)" not in _home_ui_text:
    if _anchor not in _home_ui_text:
        raise SystemExit("HomeScreen custom timeframe insertion point missing.")
    _home_ui_text = _home_ui_text.replace(_anchor, _custom_ui + "\n" + _anchor, 1)
_home_ui.write_text(_home_ui_text)
print("Added explicit Real Market selector label, fast expiry presets, custom timeframe entry, and persisted selection.")

# Make the floating scanner use the selected market/timeframe, not hardcoded EUR/USD or 1M.
_scan_ui = _UiPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_scan_ui_text = _scan_ui.read_text()
_pref_anchor = '''                val apiKey = sharedPrefs.getString("gemini_api_key", "") ?: ""
                val geminiRepo = GeminiAnalysisRepository { apiKey }'''
_pref_new = '''                val apiKey = sharedPrefs.getString("gemini_api_key", "") ?: ""
                val selectedMarketName = sharedPrefs.getString("selected_market_type", "OTC") ?: "OTC"
                val selectedTimeframe = sharedPrefs.getString("selected_timeframe", "1M") ?: "1M"
                val geminiRepo = GeminiAnalysisRepository { apiKey }'''
if _pref_anchor in _scan_ui_text:
    _scan_ui_text = _scan_ui_text.replace(_pref_anchor, _pref_new, 1)
elif "val selectedMarketName = sharedPrefs.getString" not in _scan_ui_text:
    raise SystemExit("Floating scanner preferences anchor missing.")

_scan_ui_text = _scan_ui_text.replace(
    'geminiRepo.analyzeChartImage(bitmap, "AUTO_DETECT", "DETECT_FROM_SCREENSHOT", "AUTO_DETECT")',
    'geminiRepo.analyzeChartImage(bitmap, selectedMarketName, "DETECT_FROM_SCREENSHOT", selectedTimeframe)',
    1
)
_market_block = '''                val marketType = when {
                    detectedMarket.contains("OTC", true) -> MarketType.OTC
                    detectedPair.contains("BTC", true) || detectedPair.contains("ETH", true) -> MarketType.CRYPTO
                    else -> MarketType.FOREX
                }'''
_market_replacement = '''                val marketType = runCatching { MarketType.valueOf(selectedMarketName) }
                    .getOrDefault(MarketType.OTC)'''
if _market_block in _scan_ui_text:
    _scan_ui_text = _scan_ui_text.replace(_market_block, _market_replacement, 1)
elif "MarketType.valueOf(selectedMarketName)" not in _scan_ui_text:
    raise SystemExit("Floating scanner market selection block missing.")
_scan_ui_text = _scan_ui_text.replace(
    'timeframe = detectedTimeframe',
    'timeframe = selectedTimeframe',
    1
)
_scan_ui.write_text(_scan_ui_text)
print("Floating scan now applies the saved market and selected expiry/timeframe to Gemini and result display.")


# Strict two-engine mode: never issue a directional signal from Local-only or Gemini-only.
# Both engines must independently return the same direction; otherwise display NO_SIGNAL.
from pathlib import Path as _StrictPath
_consensus_file = _StrictPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/ai/DualEngineConsensus.kt")
_consensus_text = _consensus_file.read_text()
_guard = """        // Strict dual confirmation: require both engines and matching directional signals.
        if (gemini == null || local.signal == SignalType.NO_SIGNAL ||
            gemini.signal == SignalType.NO_SIGNAL || local.signal != gemini.signal) {
            val reason = when {
                gemini == null -> "Gemini analysis failed or unavailable. Local result alone is not enough."
                local.signal != gemini.signal -> "Engine disagreement: Local ${local.signal} vs Gemini ${gemini.signal}. Wait for agreement."
                else -> "Both engines did not confirm a clear direction."
            }
            return FinalTradeSignal(
                finalSignal = SignalType.NO_SIGNAL,
                confidence = 0,
                marketType = marketType,
                pair = pair,
                timeframe = timeframe,
                geminiAnalysis = gemini,
                localAnalysis = local,
                patterns = (local.patterns + (gemini?.patterns ?: emptyList())).distinct(),
                mtgPlan = MartingalePlan(
                    step = 0,
                    advice = "NO TRADE — both Local and Gemini must agree. Do not use MTG to recover losses.",
                    multiplier = 0.0,
                    recommendedAmount = 0.0
                ),
                technicalSummary = reason,
                keyLevels = KeyLevels(support = "N/A", resistance = "N/A")
            )
        }

"""
if "Strict dual confirmation: require both engines" not in _consensus_text:
    _anchor = "        // If Gemini is available"
    if _anchor not in _consensus_text:
        raise SystemExit("DualEngineConsensus insertion point not found")
    _consensus_text = _consensus_text.replace(_anchor, _guard + _anchor, 1)
    _consensus_file.write_text(_consensus_text)

# Show both independent engine outputs in the floating result card.
_scanner_file = _StrictPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_scanner_text = _scanner_file.read_text()
_engine_ui = """            // Independent Local and Gemini results (visible separately).
            val engineBreakdown = TextView(this@FloatingScannerService).apply {
                val local = signal.localAnalysis
                val gemini = signal.geminiAnalysis
                text = "LOCAL: ${local.signal} (${local.confidence}%)\\n${local.summary}\\n\\n" +
                    if (gemini == null) {
                        "GEMINI: FAILED / NO RESPONSE\\nA combined directional signal is blocked."
                    } else {
                        "GEMINI: ${gemini.signal} (${gemini.confidence}%)\\n${gemini.summary}"
                    }
                setTextColor(Color.parseColor("#D3DEEA"))
                textSize = 10.5f
                setPadding(0, (8 * density).toInt(), 0, (8 * density).toInt())
            }
            addView(engineBreakdown)

"""
_card_anchor = "val summaryText = TextView(this@FloatingScannerService).apply {"
if "Independent Local and Gemini results (visible separately)." not in _scanner_text:
    if _card_anchor not in _scanner_text:
        raise SystemExit("Result card summary insertion point not found")
    _scanner_text = _scanner_text.replace(_card_anchor, _engine_ui + _card_anchor, 1)
    _scanner_file.write_text(_scanner_text)

print("Strict Local+Gemini agreement enabled; independent engine results are displayed.")


# Make the floating signal card easier to read and show the real Gemini failure reason.
from pathlib import Path as _DiagPath
_diag_service = _DiagPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_diag_text = _diag_service.read_text()

# Include a short, sanitized Gemini error in the card rather than only a generic NO RESPONSE.
_diag_old = """                val finalSignal = DualEngineConsensus.combineResults(
                    local = localResult,
                    gemini = geminiResult,
                    marketType = marketType,
                    pair = detectedPair,
                    timeframe = selectedTimeframe
                )
                triggerHaptic(finalSignal.finalSignal)
                showResultCard(finalSignal)
                if (geminiResult == null) {
                    val reason = geminiResponse.exceptionOrNull()?.message ?: "Gemini analysis unavailable"
                    android.widget.Toast.makeText(applicationContext, "Gemini unavailable; screenshot asset cannot be verified. " + reason.take(140), android.widget.Toast.LENGTH_LONG).show()
                } else if (detectedPair == "Asset not detected in screenshot") {"""
_diag_new = """                val rawGeminiError = geminiResponse.exceptionOrNull()?.message
                    ?.replace(apiKey, "[API_KEY_HIDDEN]")
                    ?.replace(Regex("AIza[A-Za-z0-9_-]{20,}"), "[API_KEY_HIDDEN]")
                    ?.take(500)
                val geminiError = when {
                    rawGeminiError?.contains("429") == true ||
                        rawGeminiError?.contains("quota", ignoreCase = true) == true ||
                        rawGeminiError?.contains("RESOURCE_EXHAUSTED", ignoreCase = true) == true ->
                        "Gemini quota/rate limit reached (HTTP 429). Wait for quota reset, or use an API key from a project with available Gemini quota. Change key in app Settings, then tap Scan again. This is a quota issue, not a chart-reading error."
                    rawGeminiError?.contains("403") == true ->
                        "Gemini access denied (403). Check API key, project permissions, and billing/quota settings in Google AI Studio."
                    rawGeminiError?.contains("400") == true ->
                        "Gemini request rejected (400). Check selected model/API compatibility and request settings."
                    rawGeminiError?.contains("503") == true ->
                        "Gemini service is busy (503). Wait briefly and scan again."
                    rawGeminiError?.contains("timeout", ignoreCase = true) == true ->
                        "Gemini request timed out. Check internet and scan again."
                    else -> rawGeminiError ?: "No response. Check internet, API key, quota, and model access."
                }
                val combinedSignal = DualEngineConsensus.combineResults(
                    local = localResult,
                    gemini = geminiResult,
                    marketType = marketType,
                    pair = detectedPair,
                    timeframe = selectedTimeframe
                )
                val finalSignal = if (geminiResult == null) {
                    combinedSignal.copy(
                        technicalSummary = combinedSignal.technicalSummary +
                            "\\n\\nGEMINI ERROR: " + (geminiError ?: "No response. Check internet, API key, quota, and model access.")
                    )
                } else combinedSignal
                triggerHaptic(finalSignal.finalSignal)
                showResultCard(finalSignal)
                if (geminiResult == null) {
                    android.widget.Toast.makeText(applicationContext, "Gemini failed. Check the card; wait/retry or update API key in Settings.", android.widget.Toast.LENGTH_LONG).show()
                } else if (detectedPair == "Asset not detected in screenshot") {"""
if _diag_old in _diag_text:
    _diag_text = _diag_text.replace(_diag_old, _diag_new, 1)
elif "GEMINI ERROR:" not in _diag_text:
    raise SystemExit("Gemini diagnostic insertion anchor missing.")

# Enlarge card and make direction labels explicit.
_diag_text = _diag_text.replace("(320 * density).toInt()", "(350 * density).toInt()")
_diag_text = _diag_text.replace('SignalType.CALL -> "▲ CALL (${signal.confidence}%)"', 'SignalType.CALL -> "▲ CALL / UP (${signal.confidence}%)"')
_diag_text = _diag_text.replace('SignalType.PUT -> "▼ PUT (${signal.confidence}%)"', 'SignalType.PUT -> "▼ PUT / DOWN (${signal.confidence}%)"')
_diag_text = _diag_text.replace(
    "textSize = 24f\n                typeface = Typeface.DEFAULT_BOLD",
    "textSize = 30f\n                typeface = Typeface.DEFAULT_BOLD"
)
_diag_text = _diag_text.replace(
    "textSize = 11f\n            }\n            addView(summaryText)",
    "textSize = 12f\n            }\n            addView(summaryText)"
)
_diag_service.write_text(_diag_text)
print("Added visible Gemini API failure details and larger CALL/UP and PUT/DOWN labels.")


# Floating overlay should be compact: show only the final direction/status.
# Detailed Local/Gemini breakdown and diagnostics belong in the in-app History.
from pathlib import Path as _CompactPath
_compact_file = _CompactPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_compact = _compact_file.read_text()
_compact_anchor = "            addView(summaryText)"
_compact_code = """            // Keep the floating overlay compact; details are retained in signal/history data.
            engineBreakdown.visibility = View.GONE
            indicatorText.visibility = View.GONE
            summaryText.visibility = View.GONE
"""
if "Keep the floating overlay compact" not in _compact:
    if _compact_anchor not in _compact:
        raise SystemExit("Compact floating overlay anchor missing")
    _compact = _compact.replace(_compact_anchor, _compact_anchor + "\n" + _compact_code, 1)
_compact_file.write_text(_compact)
print("Floating overlay now shows only the main signal; detailed analysis stays in history.")

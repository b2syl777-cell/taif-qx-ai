from pathlib import Path

p = Path("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
s = p.read_text()

anchor = '                val localResult = withContext(Dispatchers.Default) { LocalChartAnalyzer.analyzeBitmap(bitmap) }\n'
insert = """                // Fast user feedback after local analysis; never present it as a confirmed signal.
                val localDirection = localResult.signal.name
                val localConfidence = localResult.confidence
                showSimpleResult(
                    "LOCAL CHECK READY",
                    "Local: $localDirection ($localConfidence%). Waiting for Gemini cross-check. No confirmed signal yet.",
                    Color.parseColor("#00E5FF")
                )
"""

if "LOCAL CHECK READY" not in s:
    if anchor not in s:
        raise SystemExit("Local analysis insertion point not found; refusing to patch.")
    s = s.replace(anchor, anchor + insert, 1)
    p.write_text(s)
    print("Added immediate local-analysis status before Gemini confirmation.")
else:
    print("Fast local feedback patch already present; no changes needed.")


# Start Gemini immediately after screenshot capture, concurrently with local analysis.
# Gemini request latency is independent of local CPU analysis; only final signal waits for both.
from pathlib import Path as _ParallelPath
_parallel_file = _ParallelPath("project/taif-qx-ai-android/app/src/main/java/com/taif/qxai/service/FloatingScannerService.kt")
_parallel_src = _parallel_file.read_text()
_begin = _parallel_src.find("    private fun captureAndProcess() {")
_end = _parallel_src.find("    private fun triggerHaptic(", _begin)
if _begin < 0 or _end < 0:
    raise SystemExit("Could not locate scan function for parallel Gemini patch.")
_parallel_func = r'''    private fun captureAndProcess() {
        activeScanJob?.cancel()
        activeScanJob = serviceScope.launch {
            showSimpleResult("SCANNING...", "Capturing screen; Local and Gemini will start together.", Color.parseColor("#00E5FF"))
            val bitmap = withContext(Dispatchers.IO) {
                var frame: Bitmap? = null
                repeat(12) {
                    frame = screenCaptureService?.captureCurrentScreen()
                    if (frame != null) return@withContext frame
                    delay(100)
                }
                frame
            }
            if (bitmap == null) {
                showSimpleResult("CAPTURE FAILED", "No screen frame. Re-enable screen capture and scan again.", Color.parseColor("#FF1744"))
                return@launch
            }

            val prefs = getSharedPreferences("taif_qx_prefs", Context.MODE_PRIVATE)
            val apiKey = prefs.getString("gemini_api_key", "") ?: ""
            val marketName = prefs.getString("selected_market_type", "OTC") ?: "OTC"
            val timeframe = prefs.getString("selected_timeframe", "1M") ?: "1M"
            val geminiRepo = GeminiAnalysisRepository { apiKey }

            // Start Gemini network request first; Local analysis runs while Gemini is processing.
            val geminiTask = async(Dispatchers.IO) {
                geminiRepo.analyzeChartImage(bitmap, marketName, "DETECT_FROM_SCREENSHOT", timeframe)
            }
            val localResult = withContext(Dispatchers.Default) {
                LocalChartAnalyzer.analyzeBitmap(bitmap)
            }

            showSimpleResult(
                "LOCAL READY • GEMINI RUNNING",
                "Local: ${localResult.signal.name} (${localResult.confidence}%). Gemini is analyzing the same screenshot now.",
                Color.parseColor("#00E5FF")
            )

            val geminiResponse = geminiTask.await()
            val geminiResult = geminiResponse.getOrNull()
            val detectedPair = geminiResult?.assetName
                ?.takeIf { it.isNotBlank() && !it.equals("Asset not detected", true) }
                ?: "Asset not detected in screenshot"
            val detectedTimeframe = geminiResult?.detectedTimeframe
                ?.takeIf { it.isNotBlank() && !it.equals("Timeframe not detected", true) }
                ?: timeframe
            val marketType = runCatching { MarketType.valueOf(marketName) }.getOrDefault(MarketType.OTC)

            var finalSignal = DualEngineConsensus.combineResults(
                local = localResult,
                gemini = geminiResult,
                marketType = marketType,
                pair = detectedPair,
                timeframe = detectedTimeframe
            )
            if (geminiResult == null) {
                val reason = geminiResponse.exceptionOrNull()?.message
                    ?.replace(apiKey, "[API_KEY_HIDDEN]")
                    ?.take(350) ?: "Gemini request failed. Check internet/API key/quota."
                finalSignal = finalSignal.copy(
                    technicalSummary = finalSignal.technicalSummary + "\nGemini error: " + reason
                )
            }
            triggerHaptic(finalSignal.finalSignal)
            showResultCard(finalSignal)
        }
    }

'''
_parallel_src = _parallel_src[:_begin] + _parallel_func + _parallel_src[_end:]
_parallel_file.write_text(_parallel_src)
print("Gemini now starts immediately in parallel with local screenshot analysis.")

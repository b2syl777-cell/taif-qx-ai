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

!macro NSIS_HOOK_POSTINSTALL
  ; Tauri stores declared resources under $INSTDIR\resources. Copy only the
  ; consumer runtime files to the app root so the existing universal launcher
  ; and all three interface choices keep one stable layout.
  SetOutPath "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\JaneConverter.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\JaneConverter.exe" "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\JaneConverterEngine.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\JaneConverterEngine.exe" "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\JaneConverterPython.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\JaneConverterPython.exe" "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\JaneConverterNative.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\JaneConverterNative.exe" "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\ffmpeg.exe" "$INSTDIR"
  IfFileExists "$INSTDIR\resources\runtime\ffprobe.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\ffprobe.exe" "$INSTDIR"

  CreateDirectory "$INSTDIR\browser-extension"
  IfFileExists "$INSTDIR\resources\runtime\browser-extension\manifest.json" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\runtime\browser-extension\*.*" "$INSTDIR\browser-extension"

  ; Keep the installer's shortcut focused on the universal launcher. The
  ; launcher itself retains Main UI, Legacy Rust, and Legacy Python routing.
  Delete "$DESKTOP\JaneConverter.lnk"
  Delete "$SMPROGRAMS\JaneConverter\JaneConverter.lnk"
  CreateDirectory "$SMPROGRAMS\JaneConverter"
  CreateShortCut "$DESKTOP\JaneConverter.lnk" "$INSTDIR\JaneConverter.exe" "" "$INSTDIR\JaneConverter.exe" 0
  CreateShortCut "$SMPROGRAMS\JaneConverter\JaneConverter.lnk" "$INSTDIR\JaneConverter.exe" "" "$INSTDIR\JaneConverter.exe" 0

  ; Runtime files are implementation details, but remain available beside the
  ; app for the explicit recovery/diagnostic options.
  SetFileAttributes "$INSTDIR\JaneConverterEngine.exe" HIDDEN
  SetFileAttributes "$INSTDIR\JaneConverterPython.exe" HIDDEN
  SetFileAttributes "$INSTDIR\JaneConverterNative.exe" HIDDEN
  SetFileAttributes "$INSTDIR\ffmpeg.exe" HIDDEN
  SetFileAttributes "$INSTDIR\ffprobe.exe" HIDDEN
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  Delete "$DESKTOP\JaneConverter.lnk"
  Delete "$SMPROGRAMS\JaneConverter\JaneConverter.lnk"
  RMDir "$SMPROGRAMS\JaneConverter"
!macroend

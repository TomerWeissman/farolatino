; FaroAI Windows installer — wraps the PyInstaller onedir bundle into a
; conventional Setup.exe.
;
; Per-user install (no admin required):
;   - Lands in %LOCALAPPDATA%\FaroAI\
;   - Start Menu shortcut + optional Desktop shortcut
;   - Uninstall via "Add or remove programs"
;
; The user-data dir (%APPDATA%\FaroAI\, where credentials.env + cache + run
; logs live) is intentionally NOT touched on uninstall. A reinstall preserves
; everything; only a manual sweep of %APPDATA%\FaroAI\ wipes user state.
;
; Build prerequisites (handled by GitHub Actions / build_windows.ps1):
;   - PyInstaller has produced dist\FaroAI\FaroAI.exe
;   - NSIS is installed (choco install nsis on the runner)
;
; Build invocation (from project root):
;   makensis /DVERSION=0.2.0 packaging\installer.nsi
;
; Output: dist\FaroAI-Setup-vX.Y.Z.exe

Unicode true

; Build-time variable. PowerShell passes /DVERSION=… so the .exe filename
; matches the GitHub Releases tag.
!ifndef VERSION
  !define VERSION "0.2.0-dev"
!endif

Name "FaroAI"
OutFile "..\dist\FaroAI-Setup-v${VERSION}.exe"

; Per-user install — no admin elevation, no UAC prompt. Writing to
; %LOCALAPPDATA% is the standard "I'm a normal user installing an app
; for myself" pattern (Slack, VS Code, Discord all do this).
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\FaroAI"
InstallDirRegKey HKCU "Software\FaroAI" "InstallDir"

ShowInstDetails show
ShowUninstDetails show
SetCompressor /SOLID lzma

; Modern UI 2 — looks like a normal Windows installer wizard.
!include "MUI2.nsh"

; License page intentionally skipped (internal tool).
!define MUI_ABORTWARNING
; Branded installer wizard icon (title bar + window). Path is relative
; to this .nsi file, which lives in packaging/. FaroAI.ico is the same
; multi-resolution .ico embedded in FaroAI.exe by PyInstaller.
!define MUI_ICON "FaroAI.ico"
!define MUI_UNICON "FaroAI.ico"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"


Section "FaroAI" SecMain
  SectionIn RO

  SetOutPath "$INSTDIR"

  ; Copy the entire PyInstaller onedir tree. /r = recursive.
  ; The `dist\FaroAI` source is produced by PyInstaller via the spec
  ; file in this directory; PowerShell ensures it exists before
  ; invoking makensis.
  File /r "..\dist\FaroAI\*.*"

  ; Start Menu shortcut. Per-user (CurrentUser) — survives reinstalls,
  ; doesn't require admin.
  CreateDirectory "$SMPROGRAMS\FaroAI"
  CreateShortcut "$SMPROGRAMS\FaroAI\FaroAI.lnk" "$INSTDIR\FaroAI.exe" "" "$INSTDIR\FaroAI.exe"
  CreateShortcut "$SMPROGRAMS\FaroAI\Uninstall FaroAI.lnk" "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut — easy to undo, harmless to add.
  CreateShortcut "$DESKTOP\FaroAI.lnk" "$INSTDIR\FaroAI.exe" "" "$INSTDIR\FaroAI.exe"

  ; Uninstaller binary.
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Add to "Add or remove programs". Per-user keys mean no admin needed.
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "DisplayName" "FaroAI"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "Publisher" "FaroLatino"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "DisplayIcon" "$INSTDIR\FaroAI.exe,0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI" \
    "NoRepair" 1

  WriteRegStr HKCU "Software\FaroAI" "InstallDir" "$INSTDIR"
SectionEnd


Section "Uninstall"
  ; Remove the install dir entirely. Code lives here; user data lives
  ; under %APPDATA%\FaroAI\ which we deliberately DO NOT touch — that
  ; way a reinstall picks up where the user left off (credentials,
  ; conversations, cache all preserved).
  RMDir /r "$INSTDIR"

  Delete "$SMPROGRAMS\FaroAI\FaroAI.lnk"
  Delete "$SMPROGRAMS\FaroAI\Uninstall FaroAI.lnk"
  RMDir "$SMPROGRAMS\FaroAI"

  Delete "$DESKTOP\FaroAI.lnk"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaroAI"
  DeleteRegKey HKCU "Software\FaroAI"

  ; Note in detail log what survived for the user's reference.
  DetailPrint "User data preserved at: $APPDATA\FaroAI"
  DetailPrint "  (delete that folder manually to wipe credentials + history)"
SectionEnd

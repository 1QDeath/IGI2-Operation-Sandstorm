@echo off
rem build the release ASI loader (version.dll, x86); run from work\release\asiloader
cd /d "%~dp0"
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
cl /nologo /O1 /MT /LD /W3 asiloader.c /Fe:version.dll /link /DEF:version.def /NOIMPLIB kernel32.lib || exit /b 1
del *.obj *.exp *.lib 2>nul

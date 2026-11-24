/* version.dll - a minimal ASI loader for IGI 2 (Operation Sandstorm release, written for it 11-23; ours, no third-party code).
   igi2.exe imports version.dll; Windows finds this one next to the exe first. It forwards every version.dll function to the real
   system version.dll and loads every *.asi in the game folder (IGI2HD.asi = sharp menu pictures, IGI2Fly.asi = fly mode test copy).
   Build: build.bat (MSVC x86). */
#include <windows.h>
static HMODULE real;
static FARPROC fp[17];
static const char *names[17] = {
  "GetFileVersionInfoA",
  "GetFileVersionInfoByHandle",
  "GetFileVersionInfoExA",
  "GetFileVersionInfoExW",
  "GetFileVersionInfoSizeA",
  "GetFileVersionInfoSizeExA",
  "GetFileVersionInfoSizeExW",
  "GetFileVersionInfoSizeW",
  "GetFileVersionInfoW",
  "VerFindFileA",
  "VerFindFileW",
  "VerInstallFileA",
  "VerInstallFileW",
  "VerLanguageNameA",
  "VerLanguageNameW",
  "VerQueryValueA",
  "VerQueryValueW",
};
__declspec(naked) void p_GetFileVersionInfoA(void) { __asm { jmp dword ptr [fp + 0] } }
__declspec(naked) void p_GetFileVersionInfoByHandle(void) { __asm { jmp dword ptr [fp + 4] } }
__declspec(naked) void p_GetFileVersionInfoExA(void) { __asm { jmp dword ptr [fp + 8] } }
__declspec(naked) void p_GetFileVersionInfoExW(void) { __asm { jmp dword ptr [fp + 12] } }
__declspec(naked) void p_GetFileVersionInfoSizeA(void) { __asm { jmp dword ptr [fp + 16] } }
__declspec(naked) void p_GetFileVersionInfoSizeExA(void) { __asm { jmp dword ptr [fp + 20] } }
__declspec(naked) void p_GetFileVersionInfoSizeExW(void) { __asm { jmp dword ptr [fp + 24] } }
__declspec(naked) void p_GetFileVersionInfoSizeW(void) { __asm { jmp dword ptr [fp + 28] } }
__declspec(naked) void p_GetFileVersionInfoW(void) { __asm { jmp dword ptr [fp + 32] } }
__declspec(naked) void p_VerFindFileA(void) { __asm { jmp dword ptr [fp + 36] } }
__declspec(naked) void p_VerFindFileW(void) { __asm { jmp dword ptr [fp + 40] } }
__declspec(naked) void p_VerInstallFileA(void) { __asm { jmp dword ptr [fp + 44] } }
__declspec(naked) void p_VerInstallFileW(void) { __asm { jmp dword ptr [fp + 48] } }
__declspec(naked) void p_VerLanguageNameA(void) { __asm { jmp dword ptr [fp + 52] } }
__declspec(naked) void p_VerLanguageNameW(void) { __asm { jmp dword ptr [fp + 56] } }
__declspec(naked) void p_VerQueryValueA(void) { __asm { jmp dword ptr [fp + 60] } }
__declspec(naked) void p_VerQueryValueW(void) { __asm { jmp dword ptr [fp + 64] } }

static void load_asis(void)
{
    char dir[MAX_PATH], pat[MAX_PATH], path[MAX_PATH], *s;
    WIN32_FIND_DATAA fd; HANDLE h;
    GetModuleFileNameA(0, dir, MAX_PATH);
    s = strrchr(dir, '\\'); if (s) s[1] = 0; else dir[0] = 0;
    lstrcpyA(pat, dir); lstrcatA(pat, "*.asi");
    h = FindFirstFileA(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        lstrcpyA(path, dir); lstrcatA(path, fd.cFileName);
        LoadLibraryA(path);
    } while (FindNextFileA(h, &fd));
    FindClose(h);
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD why, LPVOID r)
{
    if (why == DLL_PROCESS_ATTACH) {
        char sys[MAX_PATH]; int i;
        DisableThreadLibraryCalls(inst);
        GetSystemDirectoryA(sys, MAX_PATH);          /* a 32-bit process gets SysWOW64 here */
        lstrcatA(sys, "\\version.dll");
        real = LoadLibraryA(sys);
        if (!real) return FALSE;
        for (i = 0; i < 17; i++) fp[i] = GetProcAddress(real, names[i]);
        load_asis();
    }
    return TRUE;
}

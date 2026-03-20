import os
import sys
import re
import hashlib
import time
import ctypes
import subprocess
from packaging.version import Version

VERSION = "1.0.5"
MIN_AG_VERSION = "1.20.5"
USE_COLOR = False

CSI = "\x1b["
COLOR_RESET = CSI + "0m"
COLOR_CYAN = CSI + "36m"
COLOR_GREEN = CSI + "32m"
COLOR_YELLOW = CSI + "33m"
COLOR_RED = CSI + "31m"
COLOR_BOLD = CSI + "1m"

def enable_ansi():
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        new_mode = mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if new_mode == mode.value:
            return True
        return bool(kernel32.SetConsoleMode(handle, new_mode))
    except Exception:
        return False

def setup_console():
    global USE_COLOR
    if os.name == "nt":
        os.system("chcp 65001 >nul")
    USE_COLOR = enable_ansi()

def color(text, *styles):
    if not USE_COLOR or not styles:
        return text
    return "".join(styles) + text + COLOR_RESET

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    C = COLOR_CYAN
    B = COLOR_BOLD
    G = COLOR_GREEN
    Y = COLOR_YELLOW
    R = COLOR_RESET if USE_COLOR else ""
    def c(text, *styles): return color(text, *styles)

    print()
    print(c("  ╔═══════════════════════════════════════════════╗", C, B))
    print(c("  ║  ", C, B) + c("Open AG Patcher", B) + c(" v", C) + c(VERSION, G, B) + c("                       ║", C, B))
    print(c("  ║  ", C, B) + c("Region bypass for Antigravity", C) + c("                ║", C, B))
    print(c("  ║  ", C, B) + c("Clean", G) + c(" • ", C) + c("No keys", G) + c(" • ", C) + c("No telemetry", G) + c("               ║", C, B))
    print(c("  ║  ", C, B) + c("Telegram Channel: ", Y) + c("t.me/avencoresyt", G) + c("           ║", C, B))
    print(c("  ║  ", C, B) + c("YouTube Channel:  ", Y) + c("youtube.com/@avencores", G) + c("     ║", C, B))
    print(c("  ╚═══════════════════════════════════════════════╝", C, B))
    print()

def is_admin():
    try:
        if os.name == 'posix':
            return os.getuid() == 0
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    if os.name != 'nt':
        return True

    if is_admin():
        return True
    
    # Автоматическое повышение прав с обработкой путей с пробелами
    if getattr(sys, 'frozen', False):
        executable = sys.executable
        args_str = ' '.join([f'"{a}"' for a in sys.argv[1:]])
    else:
        executable = sys.executable
        # sys.argv[0] — это скрипт; передаём его явно, остальные аргументы следом
        script = sys.argv[0]
        args_str = ' '.join([f'"{a}"' for a in [script] + sys.argv[1:]])
    
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args_str, None, 1)
        return ret > 32
    except Exception:
        return False

def find_install_root():
    candidates =[]

    if os.name == 'posix':
        candidates.append("/usr/share/antigravity")

    if os.name == 'nt':
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(os.path.join(local_app_data, "Programs", "Antigravity"))
        pf = os.environ.get("PROGRAMFILES")
        if pf:
            candidates.append(os.path.join(pf, "Antigravity"))
        pfx86 = os.environ.get("PROGRAMFILES(X86)")
        if pfx86:
            candidates.append(os.path.join(pfx86, "Antigravity"))

        try:
            import winreg
            for hive, key_path in[
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{AA73B3E3-C6C8-45C8-B1DC-4AE56C751432}_is1"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{AA73B3E3-C6C8-45C8-B1DC-4AE56C751432}_is1")
            ]:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        install_loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_loc and install_loc.strip():
                            candidates.append(install_loc.strip())
                except OSError:
                    pass
        except ImportError:
            pass

    for path in candidates:
        for sub in[
            os.path.join("resources", "app", "out", "main.js"),
            os.path.join("resources", "app", "main.js")
        ]:
            if os.path.exists(os.path.join(path, sub)):
                return path
    return ""

def find_main_js(root):
    for sub in[
        os.path.join("resources", "app", "out", "main.js"),
        os.path.join("resources", "app", "main.js"),
        "main.js"
    ]:
        p = os.path.join(root, sub)
        if os.path.exists(p):
            return p
    return ""

def get_ag_version(main_js_path):
    """
    Читает версию Antigravity из реестра Windows или package.json на Linux.
    """
    if os.name == 'posix':
        # Сначала пробуем dpkg (apt-установка)
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", "antigravity"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                ver = result.stdout.strip()
                if ver:
                    return ver
        except Exception:
            pass

        # rpm-based (Fedora, RHEL, openSUSE и др.)
        try:
            result = subprocess.run(
                ["rpm", "-q", "--queryformat", "%{VERSION}", "antigravity"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                ver = result.stdout.strip()
                if ver:
                    return ver
        except Exception:
            pass

        # Fallback: package.json (portable / snap / flatpak)
        for rel in (
            os.path.join(os.path.dirname(main_js_path), "..", "package.json"),
            os.path.join(os.path.dirname(main_js_path), "package.json"),
        ):
            pkg = os.path.normpath(rel)
            if os.path.exists(pkg):
                try:
                    import json
                    with open(pkg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    ver = data.get("version", "").strip()
                    if ver:
                        return ver
                except Exception:
                    pass
        return None

    if os.name == 'nt':
        try:
            import winreg
            for hive, key_path in[
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{AA73B3E3-C6C8-45C8-B1DC-4AE56C751432}_is1"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{AA73B3E3-C6C8-45C8-B1DC-4AE56C751432}_is1")
            ]:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        display_ver, _ = winreg.QueryValueEx(key, "DisplayVersion")
                        if display_ver and display_ver.strip():
                            return display_ver.strip()
                except OSError:
                    pass
        except ImportError:
            pass

    return None

def check_ag_version(main_js_path):
    """
    Проверяет, что версия Antigravity не ниже MIN_AG_VERSION.
    Возвращает (ok, detected_version_str):
      ok = True   — версия подходит
      ok = False  — версия слишком старая
      ok = None   — не удалось определить / распарсить
    """
    ver_str = get_ag_version(main_js_path)

    if ver_str is None:
        return None, None

    try:
        detected = Version(ver_str)
        minimum  = Version(MIN_AG_VERSION)
        return detected >= minimum, ver_str
    except Exception:
        return None, ver_str

def parse_version_safe(ver_str):
    if not ver_str:
        return None
    try:
        return Version(ver_str)
    except Exception:
        return None

def backup_version_meta_path(backup_path):
    return backup_path + ".version"

def load_backup_version(backup_path):
    meta_path = backup_version_meta_path(backup_path)
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            ver_str = f.read().strip()
        return ver_str or None
    except Exception:
        return None

def save_backup_version(backup_path, version_str):
    if not version_str:
        return
    meta_path = backup_version_meta_path(backup_path)
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(version_str.strip())
    except Exception as e:
        print(color(f"  [!] Could not save backup version metadata: {e}", COLOR_YELLOW))

def save_backup_hash(backup_path):
    h = file_hash(backup_path)
    if h != "?":
        try:
            with open(backup_path + ".sha256", "w", encoding="utf-8") as f:
                f.write(h)
        except Exception as e:
            print(color(f"  [!] Could not save backup hash: {e}", COLOR_YELLOW))

def verify_backup_hash(backup_path):
    hash_file = backup_path + ".sha256"
    if not os.path.exists(hash_file):
        return None  # нет данных — не проверяем
    try:
        with open(hash_file, "r", encoding="utf-8") as f:
            saved = f.read().strip()
        return file_hash(backup_path) == saved
    except Exception:
        return None

def format_bytes(size_bytes):
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"

def warn_about_unsafe_backup(main_js_path, installed_version_str=None, current_content=None):
    backup_path = main_js_path + ".bak"
    if not os.path.exists(backup_path):
        return True, False

    installed_version_str = installed_version_str or get_ag_version(main_js_path)
    installed_version = parse_version_safe(installed_version_str)
    backup_version_str = load_backup_version(backup_path)
    backup_version = parse_version_safe(backup_version_str)
    backup_size = file_size(backup_path)
    current_size = file_size(main_js_path)
    warnings = []

    if installed_version and backup_version and backup_version < installed_version:
        warnings.append(f"backup version {backup_version_str} is older than installed {installed_version_str}")

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_content = f.read()
    except Exception as e:
        print(color(f"  [!] Backup check error: {e}", COLOR_YELLOW))
        return False, False

    if backup_size <= 2048 or len(backup_content.strip()) <= 512:
        warnings.append(f"backup size is only {format_bytes(backup_size)} and it looks almost empty")
    elif current_size and backup_size < max(4096, current_size // 10):
        warnings.append(
            f"backup is much smaller than current main.js ({format_bytes(backup_size)} vs {format_bytes(current_size)})"
        )

    if current_content is not None:
        if backup_content == current_content:
            if installed_version_str and not backup_version_str:
                save_backup_version(backup_path, installed_version_str)
        elif not is_already_patched(current_content):
            warnings.append("backup does not match the current unpatched main.js")
        else:
            # Текущий файл запатчен, а бэкап отличается — возможно, бэкап от другой версии
            warnings.append("backup does not match the current (patched) main.js — it may be from a different version")

    if not warnings:
        return True, False

    for warning in warnings:
        print(color(f"  [!] Backup warning: {warning}", COLOR_YELLOW))
    print(color("  [!] Restoring this backup may break Antigravity.", COLOR_YELLOW))
    print(color(f"  [i] Backup kept: {os.path.basename(backup_path)}", COLOR_YELLOW))
    return True, True

def apply_patches(content):
    results =[]
    original = content

    # 1. if(isGoogleInternal) -> if(true)
    re_if_internal = re.compile(r'if\(this\.([a-zA-Z_$]+)\.isGoogleInternal\)')
    matches =[m.group(0) for m in re_if_internal.finditer(content)]
    old = content
    content = re_if_internal.sub('if(true)', content)
    if content != old:
        unique_matches = list(set(matches))
        results.append({
            "Name": "if(isGoogleInternal) → if(true)",
            "Applied": True,
            "Detail": f"replaced {len(matches)} occurrences: {unique_matches}"
        })
    else:
        results.append({"Name": "if(isGoogleInternal) → if(true)", "Applied": False, "Detail": ""})

    # 2. onboardUser injection
    re_internal_block = re.compile(r'(await\s+this\.([a-zA-Z_$]+)\.loadCodeAssist\(([a-zA-Z_$]+)\))(;const\{settings)')
    internal_match = re_internal_block.search(content)

    if internal_match:
        var_svc = internal_match.group(2)
        arg_name = internal_match.group(3)

        onboard_code = f';try{{await this.{var_svc}.onboardUser("standard-tier",{arg_name})}}catch(_e){{try{{await this.{var_svc}.onboardUser("free-tier",{arg_name})}}catch(_e2){{}}}}'

        old = content
        replacement = internal_match.group(1) + onboard_code + internal_match.group(4)
        content = content.replace(internal_match.group(0), replacement, 1)

        results.append({
            "Name": "onboardUser injection (internal path)",
            "Applied": content != old,
            "Detail": f"this.{var_svc}.onboardUser() before refreshUserStatus"
        })
    else:
        re_load_ca = re.compile(r'(await\s+this\.([a-zA-Z_$]+)\.loadCodeAssist\(([a-zA-Z_$]+)\))')
        lca_match = re_load_ca.search(content)
        if lca_match:
            var_svc = lca_match.group(2)
            arg_name = lca_match.group(3)
            injection = f';try{{await this.{var_svc}.onboardUser("standard-tier",{arg_name})}}catch(_e){{try{{await this.{var_svc}.onboardUser("free-tier",{arg_name})}}catch(_e2){{}}}}'
            
            old = content
            replacement = lca_match.group(1) + injection
            content = content.replace(lca_match.group(0), replacement, 1)
            
            results.append({
                "Name": "onboardUser injection (fallback)",
                "Applied": content != old,
                "Detail": f"this.{var_svc}.onboardUser() after loadCodeAssist"
            })
        else:
            results.append({"Name": "onboardUser injection", "Applied": False, "Detail": "loadCodeAssist not found"})

    # 3. ideName -> antigravity-insiders
    old = content
    content = content.replace('ideName:"antigravity"', 'ideName:"antigravity-insiders"')
    results.append({
        "Name": "ideName → antigravity-insiders",
        "Applied": content != old,
        "Detail": ""
    })

    # 4. refreshUserStatus wrapper
    re_refresh = re.compile(r'await this\.(([a-zA-Z_$]+\.)?refreshUserStatus\(([a-zA-Z_$]+)\))')
    refresh_matches = list(re_refresh.finditer(content))

    if refresh_matches:
        old = content
        # Итерируем в обратном порядке по позициям, чтобы замены не сдвигали
        # индексы ещё не обработанных совпадений
        for rm in reversed(refresh_matches):
            full = rm.group(0)
            inner_call = rm.group(1)
            arg_r = rm.group(3)
            wrapped = f'await(async()=>{{try{{return await this.{inner_call}}}catch(_e){{return{{settings:{{}},userTier:"pro",oauthTokenInfo:{arg_r}}}}}}})()'
            start, end = rm.start(), rm.end()
            content = content[:start] + wrapped + content[end:]

        results.append({
            "Name": "refreshUserStatus → wrapped with fallback",
            "Applied": content != old,
            "Detail": f"{len(refresh_matches)} calls wrapped"
        })
    else:
        results.append({"Name": "refreshUserStatus wrapper", "Applied": False, "Detail": ""})

    return content, results

def is_already_patched(content):
    # Проверяем конкретные строки, внедрённые патчем, а не просто if(true),
    # которое слишком часто встречается в минифицированном JS
    return 'ideName:"antigravity-insiders"' in content and 'onboardUser(' in content

def file_hash(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return "?"

def file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def format_size_mb(path):
    size_mb = file_size(path) / 1024 / 1024
    return f"{size_mb:.1f} MB"

def print_target_info(main_js_path, show_search_line=False):
    if show_search_line:
        print("  [*] Searching for Antigravity installation...")
    print(f"  [*] Target: {color(main_js_path, COLOR_CYAN)}")
    ver_str = get_ag_version(main_js_path)
    if ver_str:
        print(f"  [*] Antigravity version: {color(ver_str, COLOR_GREEN)}")
    else:
        print(color("  [!] Antigravity version: not detected", COLOR_YELLOW))
    print(f"  [*] Size:   {color(format_size_mb(main_js_path), COLOR_GREEN)}")

def prompt_yn(question):
    question = question.rstrip()
    prompt = f"  [?] {question} ({color('y', COLOR_GREEN)}/{color('n', COLOR_RED)}): "
    return input(prompt).strip().lower()

def redraw_main_screen(main_js_path, show_search_line=False):
    clear_screen()
    print_banner()
    print_target_info(main_js_path, show_search_line=show_search_line)
    print()

def do_patch(main_js_path, show_search_line=False):
    # --- Проверка минимальной версии ---
    ver_ok, ver_str = check_ag_version(main_js_path)

    if ver_ok is False:
        # Версия определена, но ниже минимальной
        print(color(f"  [!] Unsupported version: {ver_str}", COLOR_RED))
        print(color(f"  [!] Minimum required: {MIN_AG_VERSION}", COLOR_RED))
        print("  [i] Please update Antigravity and try again.")
        c = prompt_yn("Proceed anyway?")
        if c != 'y':
            return
    elif ver_ok is None and ver_str is None:
        # Версия в реестре не найдена
        print(color("  [!] Could not detect Antigravity version (registry key not found).", COLOR_YELLOW))
        c = prompt_yn("Proceed without version check?")
        if c != 'y':
            return
    elif ver_ok is None and ver_str is not None:
        # Версия найдена, но не удалось распарсить
        print(color(f"  [!] Could not parse version string: {ver_str}", COLOR_YELLOW))
        c = prompt_yn("Proceed anyway?")
        if c != 'y':
            return
    # else: ver_ok is True — версия подходит, продолжаем

    try:
        with open(main_js_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [!] Read error: {e}")
        return

    if is_already_patched(content):
        print("  [i] File appears already patched.")
        c = prompt_yn("Apply anyway?")
        if c != 'y':
            clear_screen()
            print_banner()
            print_target_info(main_js_path, show_search_line=show_search_line)
            return

    backup_path = main_js_path + ".bak"

    need_new_backup = True
    if os.path.exists(backup_path):
        backup_size = file_size(backup_path)
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_content = f.read()
            backup_looks_empty = backup_size <= 2048 or len(backup_content.strip()) <= 512
        except Exception:
            backup_looks_empty = True

        if backup_looks_empty:
            print(color("  [!] Existing backup looks empty or corrupted — replacing it.", COLOR_YELLOW))
        elif is_already_patched(backup_content):
            print(color("  [!] Existing backup is itself patched — replacing it with clean copy.", COLOR_YELLOW))
        else:
            need_new_backup = False
            print("  [i] Backup already exists")

    if need_new_backup:
        print("  [*] Creating backup...")
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)
            save_backup_version(backup_path, ver_str)
            save_backup_hash(backup_path)
            print(f"  [+] Backup: {os.path.basename(backup_path)}")
        except Exception as e:
            print(f"  [!] Backup error: {e}")
            return

    hash_before = file_hash(main_js_path)

    print("  [*] Applying patches...")
    print()

    new_content, results = apply_patches(content)

    applied = 0
    for r in results:
        icon = "  ✓" if r.get("Applied") else "  ✗"
        if r.get("Applied"):
            applied += 1
        detail = f" — {r.get('Detail')}" if r.get("Detail") else ""
        print(f"{icon} {r['Name']}{detail}")
    print()

    if applied == 0:
        print("  [!] No patches applied.")
        return

    try:
        with open(main_js_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        print(f"  [!] Write error: {e}")
        return

    hash_after = file_hash(main_js_path)
    print(f"  [+] Patches: {applied}/{len(results)} applied")
    if hash_before != "?" and hash_after != "?":
        print(f"  [+] Before:  {hash_before[:8]}...{hash_before[56:]}")
        print(f"  [+] After:   {hash_after[:8]}...{hash_after[56:]}")
    print(f"  [+] Done at  {time.strftime('%H:%M:%S')}")
    print()
    print("  Restart Antigravity and sign in.")

def do_restore(main_js_path, show_search_line=False):
    import shutil

    current_content = None
    try:
        with open(main_js_path, "r", encoding="utf-8") as f:
            current_content = f.read()
    except Exception:
        pass

    backup_ok, backup_has_warnings = warn_about_unsafe_backup(main_js_path, current_content=current_content)
    if not backup_ok:
        return

    backup_path = main_js_path + ".bak"

    # Разделяем "не найден" и "нечитаем"
    if not os.path.exists(backup_path):
        print(f"  [!] Backup file not found: {backup_path}")
        return
    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            data = f.read()
    except Exception as e:
        print(f"  [!] Could not read backup: {e}")
        return

    # Проверка целостности по хэшу
    hash_ok = verify_backup_hash(backup_path)
    if hash_ok is False:
        print(color("  [!] Backup hash mismatch — file may be corrupted!", COLOR_RED))
        c = prompt_yn("Restore anyway?")
        if c != 'y':
            print("  [i] Restore cancelled.")
            return

    # Предупреждение, если бэкап сам является пропатченной версией
    if is_already_patched(data):
        print(color("  [!] Backup itself appears to be patched!", COLOR_YELLOW))
        c = prompt_yn("Restore this patched backup?")
        if c != 'y':
            print("  [i] Restore cancelled.")
            return

    restore_question = "Restore this backup anyway?" if backup_has_warnings else "Restore backup?"
    c = prompt_yn(restore_question)
    if c != 'y':
        print("  [i] Restore cancelled.")
        return

    hash_before = file_hash(main_js_path)

    # Атомарная запись через временный файл
    tmp_path = main_js_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(data)
        shutil.move(tmp_path, main_js_path)
    except Exception as e:
        print(f"\n  [!] Restore error: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return

    hash_after = file_hash(main_js_path)

    # Удаляем мета-файлы бэкапа — после восстановления они уже неактуальны
    for ext in (".version", ".sha256"):
        meta = backup_path + ext
        if os.path.exists(meta):
            try:
                os.remove(meta)
            except Exception:
                pass

    print_target_info(main_js_path, show_search_line=show_search_line)
    print()
    if hash_before not in ("?",) and hash_before != hash_after and hash_after != "?":
        print(f"  [+] Before: {hash_before[:8]}...{hash_before[56:]}")
        print(f"  [+] After:  {hash_after[:8]}...{hash_after[56:]}")
    print(f"  [+] Done at {time.strftime('%H:%M:%S')}")
    print("\n  [+] Restored from backup!")

def main():
    setup_console()
    print_banner()

    main_js_path = ""
    root = ""

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.endswith("main.js"):
            main_js_path = arg
        else:
            root = arg
            main_js_path = find_main_js(root)

    if not main_js_path:
        cwd = os.getcwd()
        local = os.path.join(cwd, "main.js")
        if os.path.exists(local):
            main_js_path = local
            print("  [*] Found main.js in current directory")

    searched = False
    if not main_js_path:
        print("  [*] Searching for Antigravity installation...")
        searched = True
        root = find_install_root()
        if root:
            main_js_path = find_main_js(root)

    if not main_js_path:
        print("  [!] main.js not found!")
        print("  [i] Put main.js next to ag_patcher.py, or specify path:")
        if os.name == 'nt':
            print("      python ag_patcher.py C:\\path\\to\\Antigravity")
        else:
            print("      python ag_patcher.py /usr/share/antigravity")
        input("\n  Press Enter to exit...")
        return

    redraw_main_screen(main_js_path, show_search_line=searched)

    while True:
        print(color("  1. Apply patch", COLOR_GREEN))
        print(color("  2. Restore from backup", COLOR_YELLOW))
        print(color("  3. Open GitHub repository", COLOR_CYAN))
        print(color("  0. Exit", COLOR_RED))
        
        choice = input(color("\n  > ", COLOR_CYAN, COLOR_BOLD)).strip()
        print()

        if choice in ("0", ""):
            return

        handled = True
        clear_screen()
        print_banner()

        if choice == "1":
            do_patch(main_js_path, show_search_line=searched)
        elif choice == "2":
            do_restore(main_js_path, show_search_line=searched)
        elif choice == "3":
            import webbrowser
            print_target_info(main_js_path, show_search_line=searched)
            print()
            url = "https://github.com/AvenCores/open-antigravity-unlock"
            webbrowser.open(url)
            print(f"  [+] Opening: {color(url, COLOR_CYAN)}")
        else:
            handled = False
            print("  [!] Invalid choice")
        print()

        if handled:
            input("  Press Enter to return to menu...")
            redraw_main_screen(main_js_path, show_search_line=searched)

if __name__ == "__main__":
    if os.name == 'nt' and not is_admin():
        if run_as_admin():
            sys.exit(0)
        else:
            print("  [!] Could not elevate privileges. The script may fail to modify files.")
    elif os.name == 'posix' and not is_admin():
        print("  [!] Root access is required to patch files in /usr/share/antigravity.")
        c = input(f"  [?] Re-launch with sudo? ({color('y', COLOR_GREEN)}/{color('n', COLOR_RED)}): ").strip().lower()
        if c == 'y':
            try:
                os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
            except Exception as e:
                print(f"  [!] Failed to re-launch with sudo: {e}")
                sys.exit(1)
        else:
            print(color("  [!] Proceeding without root. Write errors are possible.", COLOR_YELLOW))
            print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [i] Exiting...")
        sys.exit(0)
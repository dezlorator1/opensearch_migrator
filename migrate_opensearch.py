#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
from pathlib import Path


def load_config():
    """Загрузить конфигурацию из .env файла"""
    config = {}
    env_path = Path(__file__).parent / '.env'

    # Если .env не найден, ищем в рабочей директории
    if not env_path.exists():
        env_path = Path.cwd() / '.env'

    # Если .env все еще не найден, ищем в /workspace
    if not env_path.exists():
        env_path = Path('/workspace') / '.env'

    if not env_path.exists():
        print(f"❌ Error: .env file not found!")
        print(f"Searched locations:")
        print(f"  - {Path(__file__).parent / '.env'}")
        print(f"  - {Path.cwd() / '.env'}")
        print(f"  - {Path('/workspace') / '.env'}")
        print(f"\n💡 Create .env file from .env.example template")
        sys.exit(1)

    print(f"→ Loading config from: {env_path}")

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Пропускаем комментарии и пустые строки
            if not line or line.startswith('#'):
                continue

            # Парсим KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Убираем кавычки если они есть (одинарные или двойные)
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                config[key] = value

    # Проверяем обязательные параметры
    required_keys = ['GITLAB_TOKEN', 'GITLAB_DOMAIN']
    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        print(f"❌ Error: Missing required config keys: {', '.join(missing_keys)}")
        print(f"Please check your .env file")
        sys.exit(1)

    # Проверяем что токен не пустой и не содержит placeholder
    if not config['GITLAB_TOKEN'] or 'your-token-here' in config['GITLAB_TOKEN'].lower():
        print(f"❌ Error: GITLAB_TOKEN is not set properly in .env file")
        print(f"Please replace 'your-token-here' with your actual GitLab token")
        sys.exit(1)

    # Проверяем что домен не содержит протокол
    if config['GITLAB_DOMAIN'].startswith('http://') or config['GITLAB_DOMAIN'].startswith('https://'):
        print(f"⚠️  Warning: GITLAB_DOMAIN should not include protocol (http:// or https://)")
        config['GITLAB_DOMAIN'] = config['GITLAB_DOMAIN'].replace('https://', '').replace('http://', '')
        print(f"   Corrected to: {config['GITLAB_DOMAIN']}")

    # Устанавливаем значения по умолчанию
    config.setdefault('GIT_USER_NAME', 'OpenSearch Migration Bot')
    config.setdefault('GIT_USER_EMAIL', 'migration-bot@example.com')

    print(f"✓ Config loaded successfully")
    print(f"  - GitLab domain: {config['GITLAB_DOMAIN']}")
    print(f"  - GitLab token: {config['GITLAB_TOKEN'][:10]}...{config['GITLAB_TOKEN'][-4:]} (masked)")
    print(f"  - Git user: {config['GIT_USER_NAME']} <{config['GIT_USER_EMAIL']}>")

    return config


def run_command(cmd, cwd=None, check=True, show_output=True):
    """Выполнить команду и вернуть результат"""
    if show_output:
        print(f"→ Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False
    )

    if show_output:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

    if check and result.returncode != 0:
        raise Exception(f"Command failed with code {result.returncode}")

    return result


def setup_git_credentials(config):
    """Настроить Git для использования токена и правильной обработки line endings"""
    print("\n→ Setting up Git credentials...")

    git_credentials_path = Path.home() / ".git-credentials"

    # ВАЖНО: Формат должен быть точным!
    # https://oauth2:TOKEN@domain.com (без слэша в конце!)
    credentials_content = f"https://oauth2:{config['GITLAB_TOKEN']}@{config['GITLAB_DOMAIN']}\n"

    # Создаем файл с credentials
    with open(git_credentials_path, 'w') as f:
        f.write(credentials_content)

    # Устанавливаем права доступа
    os.chmod(git_credentials_path, 0o600)

    print(f"✓ Created .git-credentials at: {git_credentials_path}")

    # Проверяем содержимое (маскируем токен)
    with open(git_credentials_path, 'r') as f:
        content = f.read().strip()
        masked_content = content[:20] + "***" + content[-20:] if len(content) > 40 else "***"
        print(f"  Content (masked): {masked_content}")

    # Настраиваем Git user info
    run_command(["git", "config", "--global", "user.name", config['GIT_USER_NAME']], show_output=False)
    run_command(["git", "config", "--global", "user.email", config['GIT_USER_EMAIL']], show_output=False)

    # Настраиваем Git на использование credential helper
    run_command(["git", "config", "--global", "credential.helper", "store"], show_output=False)

    # КРИТИЧНО: Настраиваем обработку окончаний строк для Windows/Linux
    run_command(["git", "config", "--global", "core.autocrlf", "input"], show_output=False)
    run_command(["git", "config", "--global", "core.whitespace", "cr-at-eol"], show_output=False)

    print(f"✓ Git config updated:")
    print(f"  - user.name: {config['GIT_USER_NAME']}")
    print(f"  - user.email: {config['GIT_USER_EMAIL']}")
    print(f"  - credential.helper: store")
    print(f"  - core.autocrlf: input")

    # Проверяем что Git видит credentials
    print("\n→ Verifying Git credential helper...")
    result = run_command(
        ["git", "config", "--global", "--get", "credential.helper"],
        check=False,
        show_output=False
    )
    if result.stdout.strip() == "store":
        print("✓ Git credential helper is configured correctly")
    else:
        print(f"⚠️  Warning: Git credential helper returned: {result.stdout.strip()}")


def test_git_authentication(project_path, config):
    """Тестируем что Git аутентификация работает"""
    print("\n→ Testing Git authentication...")

    # Пробуем сделать git ls-remote для проверки доступа
    result = run_command(
        ["git", "ls-remote", "--heads", "origin"],
        cwd=project_path,
        check=False,
        show_output=False
    )

    if result.returncode == 0:
        print("✓ Git authentication successful!")
        return True
    else:
        print("❌ Git authentication FAILED!")
        print(f"\nError output:")
        print(result.stderr)

        print(f"\n🔍 Debug info:")
        print(f"  - GitLab domain: {config['GITLAB_DOMAIN']}")
        print(f"  - Token starts with: {config['GITLAB_TOKEN'][:10]}...")
        print(f"  - Credentials file: {Path.home() / '.git-credentials'}")

        # Проверяем remote URL
        remote_result = run_command(
            ["git", "remote", "get-url", "origin"],
            cwd=project_path,
            check=False,
            show_output=False
        )
        if remote_result.returncode == 0:
            print(f"  - Remote URL: {remote_result.stdout.strip()}")

        return False


def check_working_directory_clean(project_path):
    """Проверить что в рабочей директории нет незакоммиченных изменений"""
    print("→ Checking for uncommitted changes...")

    # Проверяем статус с игнорированием CRLF различий
    result = run_command(
        ["git", "diff", "--ignore-cr-at-eol", "--name-only"],
        cwd=project_path,
        check=False,
        show_output=False
    )

    modified_files = result.stdout.strip()

    # Проверяем staged changes
    result_staged = run_command(
        ["git", "diff", "--cached", "--ignore-cr-at-eol", "--name-only"],
        cwd=project_path,
        check=False,
        show_output=False
    )

    staged_files = result_staged.stdout.strip()

    # Проверяем untracked files
    result_untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=project_path,
        check=False,
        show_output=False
    )

    untracked_files = result_untracked.stdout.strip()

    if modified_files or staged_files or untracked_files:
        print("\n⚠️  WARNING: Repository has uncommitted changes!")
        if modified_files:
            print("\nModified files:")
            print(modified_files)
        if staged_files:
            print("\nStaged files:")
            print(staged_files)
        if untracked_files:
            print("\nUntracked files:")
            print(untracked_files)

        print("\n❌ ERROR: Please commit or stash your changes before running migration.")
        print("   Run: git status")
        return False

    print("✓ Working directory is clean")
    return True


def normalize_version(version):
    """
    Обрезать .0 в конце версии для отображения
    3.5.0 -> 3.5
    3.5.1 -> 3.5.1
    """
    if version.endswith('.0'):
        return version[:-2]
    return version


def find_all_pom_files(project_path):
    """Найти все pom.xml файлы в проекте (включая multi-module проекты)"""
    pom_files = []

    # Основной pom.xml в корне
    root_pom = project_path / "pom.xml"
    if root_pom.exists():
        pom_files.append(root_pom)

    # Ищем pom.xml в подмодулях
    for item in project_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            module_pom = item / "pom.xml"
            if module_pom.exists():
                pom_files.append(module_pom)

    return pom_files


def update_pom_version(pom_path, new_version):
    """Обновить версию opensearch в pom.xml"""
    with open(pom_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ищем <opensearch.version>X.X.X</opensearch.version>
    pattern = r'<opensearch\.version>.*?</opensearch\.version>'
    new_tag = f'<opensearch.version>{new_version}</opensearch.version>'

    if not re.search(pattern, content):
        # Если не найден, возвращаем False (этот pom не содержит opensearch.version)
        return False

    updated_content = re.sub(pattern, new_tag, content)

    # Записываем с Unix line endings (LF)
    with open(pom_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(updated_content)

    return True


def main():
    parser = argparse.ArgumentParser(description='Migrate OpenSearch version in Maven project')
    parser.add_argument('--project-path', required=True, help='Path to the project')
    parser.add_argument('--version', required=True, help='New OpenSearch version (e.g., 3.5.0)')
    parser.add_argument('--feat', required=True, help='Feature number (e.g., 3185)')
    parser.add_argument('--force', action='store_true', help='Force migration even if there are uncommitted changes (DANGEROUS!)')

    args = parser.parse_args()

    # Загружаем конфигурацию из .env
    print("=" * 60)
    print("Loading configuration...")
    print("=" * 60)
    config = load_config()

    project_path = Path(args.project_path).resolve()
    opensearch_version = args.version
    feat_number = args.feat

    # Версия для отображения (обрезаем .0 если есть)
    display_version = normalize_version(opensearch_version)

    # Формируем полный номер задачи
    task_number = f"SMDEV-{feat_number}"

    print("\n" + "=" * 60)
    print(f"OpenSearch Migration Tool")
    print("=" * 60)
    print(f"Project: {project_path}")
    print(f"OpenSearch version: {opensearch_version} (display: {display_version})")
    print(f"Task number: {task_number}")
    print("=" * 60)

    if not project_path.exists():
        print(f"✗ Error: Project path does not exist: {project_path}")
        sys.exit(1)

    # Список файлов для коммита
    files_to_commit = []

    try:
        # Настраиваем Git credentials и line endings перед началом работы
        print("\n[0/8] Setting up Git credentials and line endings...")
        setup_git_credentials(config)

        # 0.5 Тестируем аутентификацию
        print("\n[0.5/8] Testing Git authentication...")
        if not test_git_authentication(project_path, config):
            print("\n❌ Cannot proceed without working Git authentication")
            print("\n💡 Troubleshooting steps:")
            print("   1. Check your GITLAB_TOKEN in .env file")
            print("   2. Make sure token has 'read_repository' permission")
            print("   3. Verify GITLAB_DOMAIN matches your remote URL")
            print("   4. Try: git ls-remote origin")
            sys.exit(1)

        # 1. Checkout dev and pull
        print("\n[1/8] Switching to dev branch and pulling changes...")
        run_command(["git", "checkout", "dev"], cwd=project_path)
        run_command(["git", "pull", "origin", "dev"], cwd=project_path)

        # 1.5 Проверяем что рабочая директория чистая
        print("\n[1.5/8] Checking working directory status...")
        if not check_working_directory_clean(project_path):
            if not args.force:
                print("\n💡 TIP: Use --force flag to proceed anyway (not recommended)")
                sys.exit(1)
            else:
                print("\n⚠️  Proceeding with --force flag (you may lose uncommitted changes!)")

        # 2. Create feature branch
        branch_name = f"feature/{task_number}-opensearch-{display_version}"
        print(f"\n[2/8] Creating feature branch: {branch_name}")
        run_command(["git", "checkout", "-b", branch_name], cwd=project_path)

        # 3. Update pom.xml files
        print(f"\n[3/8] Updating pom.xml files...")
        pom_files = find_all_pom_files(project_path)

        if not pom_files:
            print(f"✗ Error: No pom.xml files found in {project_path}")
            sys.exit(1)

        print(f"Found {len(pom_files)} pom.xml file(s)")
        updated_poms = []

        for pom_path in pom_files:
            relative_path = pom_path.relative_to(project_path)
            print(f"  Checking: {relative_path}")

            if update_pom_version(pom_path, opensearch_version):
                print(f"  ✓ Updated: {relative_path}")
                updated_poms.append(pom_path)
                files_to_commit.append(str(relative_path))
            else:
                print(f"  - Skipped: {relative_path} (no opensearch.version found)")

        if not updated_poms:
            print(f"✗ Error: No pom.xml files contain <opensearch.version> tag")
            sys.exit(1)

        print(f"\n✓ Updated {len(updated_poms)} pom.xml file(s)")

        # 4. Create changelogs directory
        print(f"\n[4/8] Creating changelogs directory...")
        changelogs_dir = project_path / "changelogs"
        changelogs_dir.mkdir(exist_ok=True)
        print(f"✓ Directory created/verified: {changelogs_dir}")

        # 5. Create changelog file
        changelog_filename = f"{task_number}.dependency.md"
        changelog_path = changelogs_dir / changelog_filename
        changelog_content = f"Версия opensearch поднята до {display_version}\n"

        print(f"\n[5/8] Creating changelog file: {changelog_filename}")
        # Записываем с Unix line endings
        with open(changelog_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(changelog_content)
        print(f"✓ Changelog created: {changelog_path}")

        # Добавляем changelog в список файлов для коммита
        changelog_relative_path = changelog_path.relative_to(project_path)
        files_to_commit.append(str(changelog_relative_path))

        # 6. Run Maven build
        print(f"\n[6/8] Running Maven build...")
        result = run_command(
            ["mvn", "clean", "compile", "install"],
            cwd=project_path,
            check=False
        )

        if result.returncode != 0:
            print("\n✗ Maven build FAILED!")
            print("Changes are NOT committed.")
            print(f"You are on branch: {branch_name}")
            print("\n💡 You can:")
            print("   1. Fix the issues manually")
            print("   2. Run: git add . && git commit -m 'message'")
            print(f"   3. Or run: git checkout dev && git branch -D {branch_name}")
            sys.exit(1)

        print("✓ Maven build SUCCESS")

        # 7. Commit changes (только конкретные файлы!)
        commit_message = f"[{task_number}] Версия opensearch поднята до {display_version}"
        print(f"\n[7/8] Committing changes...")
        print(f"Files to commit:")
        for file in files_to_commit:
            print(f"  - {file}")

        # Добавляем только конкретные файлы
        for file in files_to_commit:
            run_command(["git", "add", file], cwd=project_path, show_output=False)

        # Проверяем что действительно есть изменения для коммита
        result = run_command(
            ["git", "diff", "--cached", "--name-only"],
            cwd=project_path,
            check=False,
            show_output=False
        )

        if not result.stdout.strip():
            print("⚠️  Warning: No changes to commit (files might be identical)")
            print("Aborting...")
            sys.exit(1)

        print(f"\nCommit message: {commit_message}")
        run_command(["git", "commit", "-m", commit_message], cwd=project_path)

        # 8. Show final status
        print(f"\n[8/8] Verifying commit...")
        print("\n" + "=" * 60)
        print("✓ SUCCESS!")
        print("=" * 60)
        print(f"Task: {task_number}")
        print(f"Branch: {branch_name}")
        print(f"Commit: {commit_message}")
        print("\nCommitted files:")
        for file in files_to_commit:
            print(f"  - {file}")
        print("\nLast commit:")
        run_command(["git", "log", "-1", "--oneline"], cwd=project_path)
        print("\n⚠️  Changes are NOT pushed to remote (manual push required)")
        print(f"\n💡 To push: git push origin {branch_name}")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
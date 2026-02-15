#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
from pathlib import Path


# Захардкоженный токен GitLab
GITLAB_TOKEN = "token"
GITLAB_DOMAIN = "domain"  # Замените на ваш домен GitLab


def run_command(cmd, cwd=None, check=True):
    """Выполнить команду и вернуть результат"""
    print(f"→ Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    if check and result.returncode != 0:
        raise Exception(f"Command failed with code {result.returncode}")
    
    return result


def setup_git_credentials():
    """Настроить Git для использования токена и правильной обработки line endings"""
    git_credentials_path = Path.home() / ".git-credentials"
    credentials_content = f"https://oauth2:{GITLAB_TOKEN}@{GITLAB_DOMAIN}\n"
    
    # Создаем файл с credentials
    with open(git_credentials_path, 'w') as f:
        f.write(credentials_content)
    
    # Устанавливаем права доступа
    os.chmod(git_credentials_path, 0o600)
    
    # Настраиваем Git на использование credential helper
    run_command(["git", "config", "--global", "credential.helper", "store"])
    
    # КРИТИЧНО: Настраиваем обработку окончаний строк для Windows/Linux
    # core.autocrlf=input: конвертирует CRLF→LF при commit, оставляет как есть при checkout
    run_command(["git", "config", "--global", "core.autocrlf", "input"])
    
    # Игнорируем различия в whitespace (включая CRLF)
    run_command(["git", "config", "--global", "core.whitespace", "cr-at-eol"])
    
    # Не показывать файлы как измененные только из-за line endings
    run_command(["git", "config", "--global", "diff.algorithm", "minimal"])
    
    print(f"✓ Git credentials configured for {GITLAB_DOMAIN}")
    print(f"✓ Git line endings configured (Windows CRLF compatibility)")


def normalize_line_endings_in_repo(project_path):
    """Нормализовать окончания строк в репозитории после checkout"""
    print("→ Normalizing line endings in repository...")
    
    # Сбрасываем индекс и рабочую директорию
    # Это заставит Git пересмотреть все файлы с новыми настройками
    result = run_command(
        ["git", "status", "--porcelain"],
        cwd=project_path,
        check=False
    )
    
    if result.stdout.strip():
        print("→ Detected modified files due to line endings, resetting...")
        # Сбрасываем изменения связанные с line endings
        run_command(["git", "reset", "--hard", "HEAD"], cwd=project_path)
    
    print("✓ Line endings normalized")


def normalize_version(version):
    """
    Обрезать .0 в конце версии для отображения
    3.5.0 -> 3.5
    3.5.1 -> 3.5.1
    """
    if version.endswith('.0'):
        return version[:-2]
    return version


def update_pom_version(pom_path, new_version):
    """Обновить версию opensearch в pom.xml"""
    with open(pom_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем <opensearch.version>X.X.X</opensearch.version>
    pattern = r'<opensearch\.version>.*?</opensearch\.version>'
    new_tag = f'<opensearch.version>{new_version}</opensearch.version>'
    
    if not re.search(pattern, content):
        raise Exception("opensearch.version tag not found in pom.xml")
    
    updated_content = re.sub(pattern, new_tag, content)
    
    # Записываем с Unix line endings (LF)
    with open(pom_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(updated_content)
    
    print(f"✓ Updated pom.xml: opensearch.version -> {new_version}")


def main():
    parser = argparse.ArgumentParser(description='Migrate OpenSearch version in Maven project')
    parser.add_argument('--project-path', required=True, help='Path to the project')
    parser.add_argument('--version', required=True, help='New OpenSearch version (e.g., 3.5.0)')
    parser.add_argument('--feat', required=True, help='Feature number (e.g., 1234)')
    
    args = parser.parse_args()
    
    project_path = Path(args.project_path).resolve()
    opensearch_version = args.version
    feat_number = args.feat
    
    # Версия для отображения (обрезаем .0 если есть)
    display_version = normalize_version(opensearch_version)
    
    print("=" * 60)
    print(f"OpenSearch Migration Tool")
    print("=" * 60)
    print(f"Project: {project_path}")
    print(f"OpenSearch version: {opensearch_version} (display: {display_version})")
    print(f"Feature number: {feat_number}")
    print("=" * 60)
    
    if not project_path.exists():
        print(f"✗ Error: Project path does not exist: {project_path}")
        sys.exit(1)
    
    pom_path = project_path / "pom.xml"
    if not pom_path.exists():
        print(f"✗ Error: pom.xml not found in {project_path}")
        sys.exit(1)
    
    try:
        # Настраиваем Git credentials и line endings перед началом работы
        print("\n[0/8] Setting up Git credentials and line endings...")
        setup_git_credentials()
        
        # 1. Checkout dev and pull
        print("\n[1/8] Switching to dev branch and pulling changes...")
        run_command(["git", "checkout", "dev"], cwd=project_path)
        run_command(["git", "pull", "origin", "dev"], cwd=project_path)
        
        # 1.5 Нормализуем line endings после pull
        print("\n[1.5/8] Normalizing line endings after pull...")
        normalize_line_endings_in_repo(project_path)
        
        # 2. Create feature branch
        branch_name = f"feature/{feat_number}-opensearch-{display_version}"
        print(f"\n[2/8] Creating feature branch: {branch_name}")
        run_command(["git", "checkout", "-b", branch_name], cwd=project_path)
        
        # 3. Update pom.xml
        print(f"\n[3/8] Updating pom.xml...")
        update_pom_version(pom_path, opensearch_version)
        
        # 4. Create changelogs directory
        print(f"\n[4/8] Creating changelogs directory...")
        changelogs_dir = project_path / "changelogs"
        changelogs_dir.mkdir(exist_ok=True)
        print(f"✓ Directory created/verified: {changelogs_dir}")
        
        # 5. Create changelog file
        changelog_filename = f"SMDEV-{feat_number}.dependency.md"
        changelog_path = changelogs_dir / changelog_filename
        changelog_content = f"Версия opensearch поднята до {display_version}\n"
        
        print(f"\n[5/8] Creating changelog file: {changelog_filename}")
        # Записываем с Unix line endings
        with open(changelog_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(changelog_content)
        print(f"✓ Changelog created: {changelog_path}")
        
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
            sys.exit(1)
        
        print("✓ Maven build SUCCESS")
        
        # 7. Commit changes
        commit_message = f"[SMDEV-{feat_number}] Версия opensearch поднята до {display_version}"
        print(f"\n[7/8] Committing changes...")
        run_command(["git", "add", "."], cwd=project_path)
        run_command(["git", "commit", "-m", commit_message], cwd=project_path)
        
        # 8. Show final status
        print(f"\n[8/8] Verifying commit...")
        print("\n" + "=" * 60)
        print("✓ SUCCESS!")
        print("=" * 60)
        print(f"Branch: {branch_name}")
        print(f"Commit: {commit_message}")
        print("\nLast commit:")
        run_command(["git", "log", "-1", "--oneline"], cwd=project_path)
        print("\n⚠️  Changes are NOT pushed to remote (manual push required)")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
# OpenSearch Migration Tool

Автоматизированный инструмент для обновления версий OpenSearch в Maven проектах.

## Возможности

- Автоматическое переключение на dev ветку и pull изменений
- Создание feature branch с правильным именованием
- Обновление версии OpenSearch в pom.xml
- Генерация changelog файлов
- Запуск Maven build для проверки
- Автоматический commit при успешной сборке
- Использование вашего локального Maven кэша и settings.xml
- Аутентификация в GitLab через токен

## Подготовка

### 1. Отредактируйте migrate_opensearch.py

Откройте файл и замените:
```python
GITLAB_TOKEN = "glpat-your-token-here"  # Ваш GitLab токен
GITLAB_DOMAIN = "gitlab.your-domain.com"  # Ваш домен GitLab
```

### 2. Отредактируйте docker-compose.yml

Укажите правильный путь к вашим проектам:
```yaml
volumes:
  - <path_to_projects>:/projects  # ИЗМЕНИТЕ на ваш путь
  - <path_to_m2>:/root/.m2       # Путь к Maven кэшу
```

### 3. Проверьте settings.xml

Убедитесь, что в `<path_to_m2>\settings.xml` настроен доступ к вашему приватному Maven репозиторию:
```xml
<settings>
  <servers>
    <server>
      <id>your-repo-id</id>
      <configuration>
        <httpHeaders>
          <property>
            <name>Private-Token</name>
            <value>YOUR_MAVEN_REPO_TOKEN</value>
          </property>
        </httpHeaders>
      </configuration>
    </server>
  </servers>
</settings>
```

## Использование

### Запуск контейнера
```bash
# Соберите образ
docker-compose build

# Запустите контейнер
docker-compose run --rm opensearch-migrator
```

### Миграция одного проекта
```bash
python3 /usr/local/bin/migrate_opensearch.py \
  --project-path /projects/your-project-name \
  --version 3.5.0 \
  --feat 1234
```

Или через алиас:
```bash
migrate --project-path /projects/your-project-name --version 3.5.0 --feat 1234
```

### Миграция нескольких проектов
```bash
for project in project1 project2 project3; do
  migrate --project-path /projects/$project --version 3.5.0 --feat 1234
done
```

## Примеры

### Версия с .0 в конце
```bash
migrate --project-path /projects/user-service --version 3.5.0 --feat 1234
```
Результат:
- Ветка: `feature/1234-opensearch-3.5`
- Changelog: `1234.dependency.md` с текстом "Версия opensearch поднята до 3.5"
- pom.xml: `<opensearch.version>3.5.0</opensearch.version>`
- Commit: `[1234] Версия opensearch поднята до 3.5`

### Версия без .0 в конце
```bash
migrate --project-path /projects/auth-service --version 3.5.1 --feat 5678
```
Результат:
- Ветка: `feature/5678-opensearch-3.5.1`
- Changelog: `5678.dependency.md` с текстом "Версия opensearch поднята до 3.5.1"
- pom.xml: `<opensearch.version>3.5.1</opensearch.version>`
- Commit: `[5678] Версия opensearch поднята до 3.5.1`

## Как работает Maven с вашим settings.xml

1. Docker монтирует вашу директорию `.m2` внутрь контейнера
2. Maven автоматически использует `/root/.m2/settings.xml` из вашего компа
3. Все зависимости из локального кэша доступны
4. При необходимости Maven использует ваш токен для доступа к приватному репозиторию

## Как работает Git аутентификация

1. Скрипт автоматически создает файл `.git-credentials` с вашим токеном
2. Git использует этот файл для аутентификации при `git pull`
3. Токен работает для операций clone, fetch, pull
4. Push НЕ выполняется автоматически (по вашему требованию)

## Проверка после миграции

После успешной миграции вы можете:

1. Проверить изменения:
```bash
cd /projects/your-project
git diff HEAD~1
git log -1 -p
```

2. Запушить изменения вручную:
```bash
git push origin feature/1234-opensearch-3.5
```

3. Создать Merge Request в GitLab

## Структура проекта
```
opensearch-migrator/
├── Dockerfile                 # Образ с Python, Java, Maven, Git
├── docker-compose.yml         # Конфигурация для запуска
├── migrate_opensearch.py      # Основной скрипт миграции
├── README.md                  # Эта документация
└── .gitignore                 # Игнорируемые файлы
```

## Требования к токенам

### GitLab Token (для Git операций)
Разрешения:
- `read_api` - для доступа к API (если нужно)
- `read_repository` - для git pull
- `write_repository` - если захотите включить автоматический push

### Maven Repository Token (в settings.xml)
Разрешения зависят от вашего Maven репозитория (обычно read access).
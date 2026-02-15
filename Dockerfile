FROM python:3.12-slim

# Устанавливаем необходимые зависимости
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    gnupg \
    ca-certificates \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем OpenJDK 22
RUN wget -O- https://packages.adoptium.net/artifactory/api/gpg/key/public | tee /etc/apt/trusted.gpg.d/adoptium.asc && \
    echo "deb https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print$2}' /etc/os-release) main" | tee /etc/apt/sources.list.d/adoptium.list && \
    apt-get update && \
    apt-get install -y temurin-22-jdk && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Maven
ENV MAVEN_VERSION=3.9.9
RUN wget https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz && \
    tar -xzf apache-maven-${MAVEN_VERSION}-bin.tar.gz -C /opt && \
    rm apache-maven-${MAVEN_VERSION}-bin.tar.gz && \
    ln -s /opt/apache-maven-${MAVEN_VERSION} /opt/maven

# Настраиваем переменные окружения
ENV JAVA_HOME=/usr/lib/jvm/temurin-22-jdk-amd64
ENV MAVEN_HOME=/opt/maven
ENV PATH="${MAVEN_HOME}/bin:${JAVA_HOME}/bin:${PATH}"

# Устанавливаем рабочую директорию
WORKDIR /workspace

# Копируем скрипт миграции
COPY migrate_opensearch.py /usr/local/bin/migrate_opensearch.py
RUN chmod +x /usr/local/bin/migrate_opensearch.py

# Настраиваем базовые параметры Git
RUN git config --global user.name "OpenSearch Migration Bot" && \
    git config --global user.email "migration-bot@example.com" && \
    git config --global credential.helper store && \
    git config --global core.autocrlf input && \
    git config --global core.whitespace cr-at-eol

# Создаем алиас для удобства
RUN echo 'alias migrate="python3 /usr/local/bin/migrate_opensearch.py"' >> /root/.bashrc

# Проверяем установку
RUN java -version && mvn -version && git --version && python3 --version

CMD ["/bin/bash"]
"""DATA ONLY: marker file -> ecosystem -> suggested image + default commands.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

MARKERS = {
    "package.json": ("node", "node:20", ["npm ci", "npm test"]),
    "pnpm-lock.yaml": ("node", "node:20", ["pnpm i --frozen-lockfile"]),
    "yarn.lock": ("node", "node:20", ["yarn install --frozen-lockfile"]),
    "pyproject.toml": ("python", "python:3.12", ["pip install -e .", "pytest"]),
    "requirements.txt": ("python", "python:3.12", ["pip install -r requirements.txt", "pytest"]),
    "go.mod": ("go", "golang:1.22", ["go build ./...", "go test ./..."]),
    "Cargo.toml": ("rust", "rust:1.79", ["cargo build", "cargo test"]),
    "pom.xml": ("java", "maven:3.9-eclipse-temurin-21", ["mvn -B verify"]),
    "build.gradle": ("java", "gradle:8-jdk21", ["gradle build"]),
    "build.gradle.kts": ("java", "gradle:8-jdk21", ["gradle build"]),
    "Gemfile": ("ruby", "ruby:3.3", ["bundle install", "bundle exec rake"]),
    "composer.json": ("php", "php:8.3-cli", ["composer install", "composer test"]),
    "Dockerfile": ("container", "", []),
    "docker-compose.yml": ("compose", "", []),
    "CMakeLists.txt": ("cpp", "gcc:13", ["make"]),
    "Makefile": ("cpp", "gcc:13", ["make"]),
}

# `*.csproj` / `*.sln` can't be plain filename keys — matched by suffix instead.
EXTENSION_MARKERS = {
    ".csproj": ("dotnet", "mcr.microsoft.com/dotnet/sdk:8.0", ["dotnet test"]),
    ".sln": ("dotnet", "mcr.microsoft.com/dotnet/sdk:8.0", ["dotnet test"]),
}

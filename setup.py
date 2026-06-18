"""
Setup configuration for the Video AI Studio package.
"""
from setuptools import setup, find_packages
import os

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

# Development dependencies
dev_requirements = []
if os.path.exists("requirements-dev.txt"):
    with open("requirements-dev.txt", "r", encoding="utf-8") as fh:
        dev_requirements = fh.read().splitlines()

setup(
    name="video-ai-studio",
    version="1.0.0",
    author="Video AI Studio Team",
    author_email="team@videoaistudio.com",
    description="AI-Powered Video Processing SaaS Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/video-ai-studio",
    project_urls={
        "Documentation": "https://docs.videoaistudio.com",
        "Bug Tracker": "https://github.com/yourusername/video-ai-studio/issues",
        "Source Code": "https://github.com/yourusername/video-ai-studio",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Framework :: Flask",
        "Natural Language :: English",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": dev_requirements,
        "production": [
            "gunicorn>=21.2.0",
            # "eventlet>=0.33.3",
            "gevent==23.9.1,"
            "whitenoise>=6.5.0",
        ],
        "testing": [
            "pytest>=7.4.3",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.1",
            "pytest-flask>=1.2.0",
            "factory-boy>=3.3.0",
            "faker>=21.0.0",
        ],
        "monitoring": [
            "prometheus-client>=0.19.0",
            "opentelemetry-api>=1.21.0",
            "opentelemetry-sdk>=1.21.0",
            "opentelemetry-instrumentation-flask>=0.41b0",
            "opentelemetry-exporter-otlp>=1.21.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "video-ai=src.main:main",
            "video-ai-cli=app.cli:cli",
        ],
        "flask.commands": [
            "create-user=app.cli:create_user_command",
            "upgrade-tier=app.cli:upgrade_tier",
            "cleanup=app.cli:cleanup",
            "stats=app.cli:stats",
        ],
    },
    include_package_data=True,
    package_data={
        "": [
            "*.yaml",
            "*.json",
            "*.html",
            "*.css",
            "*.js",
            "*.md",
        ],
    },
    data_files=[
        ("config", [
            "config/tier_config.yaml",
            "config/ai_models.yaml",
            "config/video_quality.yaml",
            "config/rate_limits.yaml",
            "config/video_styles.json",
            "config/languages.json",
        ]),
        ("templates", [
            "templates/*.html",
            "templates/auth/*.html",
            "templates/dashboard/*.html",
            "templates/billing/*.html",
            "templates/admin/*.html",
            "templates/components/*.html",
            "templates/errors/*.html",
        ]),
        ("static", [
            "static/css/*.css",
            "static/js/*.js",
            "static/fonts/Inter/*.woff2",
            "static/fonts/FontAwesome/*",
            "static/images/logo/*.svg",
            "static/images/icons/*.svg",
            "static/images/styles/*.jpg",
        ]),
    ],
    keywords=[
        "video",
        "ai",
        "processing",
        "saas",
        "flask",
        "openai",
        "gemini",
        "stability-ai",
        "ffmpeg",
    ],
    license="MIT",
    platforms=["any"],
    zip_safe=False,
)
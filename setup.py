from setuptools import setup, find_packages
import os

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="jarvis-assistant",
    version="1.0.0",
    author="Darshit Patel",
    author_email="darshitp091@gmail.com",
    description="A high-performance, privacy-first, Stark-inspired desktop voice & vision AI assistant for Windows.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/darshitp091/Jarvis",
    project_urls={
        "Bug Tracker": "https://github.com/darshitp091/Jarvis/issues",
        "Source Code": "https://github.com/darshitp091/Jarvis",
    },
    packages=find_packages(),
    py_modules=["main"],
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "pyyaml",
        "loguru",
        "requests",
        "ollama",
        "sounddevice",
        "numpy",
        "pyautogui",
        "pywin32",
    ],
    entry_points={
        "console_scripts": [
            "jarvis=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: System :: Systems Administration",
    ],
)

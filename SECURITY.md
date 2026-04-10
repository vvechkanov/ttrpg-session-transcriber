# Security Policy

## Supported Versions

TTRPG Session Transcriber is in active development. Security fixes will be released for the latest minor version.

| Version | Supported          |
| ------- | ------------------ |
| 0.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public issue**.

Instead, email **vechkanov90@gmail.com** with:

- A description of the vulnerability and its potential impact
- Steps to reproduce
- Any suggested mitigation, if you have one

You should receive an initial response within 7 days. We will work with you to verify the issue and prepare a fix.

## Scope

This project processes audio files locally on the user's machine. The main attack surfaces are:

- **Installer (.exe)** — code that downloads and installs Python, PyTorch, ASR backends, and ffmpeg from public sources
- **Audio file parsing** — handling of `.flac`, `.ogg`, `.wav` and other audio inputs via ffmpeg / soundfile / librosa
- **Foundry VTT chat log parsing** — handling of user-supplied JSON / text files
- **Hugging Face model downloads** — pre-downloaded models from public repositories

If you find a way to make the installer execute arbitrary code, exploit a parser bug to read or write arbitrary files, or trigger remote code execution via crafted audio or chat logs, that is in scope.

## Out of Scope

- Vulnerabilities in upstream dependencies (faster-whisper, PyTorch, ffmpeg, etc.) — please report those to their respective maintainers
- Issues that require physical access to the user's machine
- Social engineering attacks

# Contributing

Thanks for your interest in Vocet. Bug reports, fixes and small, focused improvements are welcome.

## Reporting a bug

Open an issue on [GitHub](https://github.com/KMGSL67/vocet/issues) with:

- your Windows version, and your processor and graphics chip;
- what you did, what you expected, and what happened;
- the relevant part of the log, if there is one: Settings > General > Log files opens the folder. The logs never contain your dictated text, and your user name is already replaced, but please read what you paste.

## Development setup

You need Windows 11 (64-bit; Windows 10 is untested) and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/KMGSL67/vocet.git
cd vocet
uv sync
uv run python -m vocet
```

`python -m vocet` runs Vocet with a console window, which is handy for development. The installed shortcut uses `vocet.pyw` and Python's windowless `pythonw.exe` instead.

To keep a development copy away from your real settings and history, set `VOCET_HOME` to an empty folder before starting it:

```
set VOCET_HOME=%TEMP%\vocet-dev
uv run python -m vocet
```

With `VOCET_HOME` set, "Start with Windows" writes a file in that folder instead of changing the registry.

## Project layout

| Path | What it is |
|---|---|
| `vocet/app.py` | Start-up, the dictation flow, the tray icon |
| `vocet/hotkey.py`, `vocet/audio.py`, `vocet/speech.py`, `vocet/engines.py` | Push-to-talk keys, microphone, speech recognition |
| `vocet/textproc.py`, `vocet/formatter.py`, `vocet/ai_format.py` | Clean-up, dictionary and snippets, the optional AI formatting and its guard |
| `vocet/insertion.py` | Pasting into the focused app and restoring the clipboard |
| `vocet/privacy.py`, `vocet/integrity.py`, `vocet/model_download.py` | Network guard, log redaction, model pinning and checksums, the model download |
| `vocet/window.py`, `vocet/ui/` | The Qt Quick (QML) window and its components |
| `vocet/pill.py` | The floating bar shown while you dictate |

## Guidelines

- **Privacy first.** Never log dictated text, clipboard contents or window titles. Don't add network access; the model download is the only exception, and it goes through `privacy.NetworkGuard`.
- **New models** must be pinned to a commit with every file's size and SHA-256 in `vocet/models_manifest.json`.
- **New dependencies** need a permissive or LGPL license, and a short reason in the pull request.
- **UI colours** come only from the theme tokens in `vocet/brand.py`. A new QML component must be listed in `vocet/ui/components/qmldir`.
- **Shaders:** after editing `vocet/ui/components/shaders/glass.frag`, rebuild `glass.frag.qsb` with Qt's `qsb` tool: `qsb --qt6 -o glass.frag.qsb glass.frag`.
- Keep pull requests small and describe how you tested them.

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).

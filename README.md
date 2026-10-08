# Vocet

> **Beta.** Vocet 0.9 is an early release. It has been tested on Windows 11 with Intel graphics; other PCs are new territory. If something doesn't work, please [open an issue](https://github.com/KMGSL67/vocet/issues). Use it at your own risk (see [Disclaimer](#disclaimer)).

Offline dictation for Windows. Hold **Ctrl + Win**, speak, let go, and your words appear wherever you're typing: Word, Outlook, a browser, a chat app, a code editor.

Speech recognition runs on your own PC with [Whisper](https://github.com/openai/whisper) through Intel's [OpenVINO](https://github.com/openvinotoolkit/openvino). Your voice is never uploaded. After a one-time model download, Vocet works without an internet connection.

## Features

- **Push to talk.** Hold Ctrl + Win (or another key you pick) while you speak. Press Space while holding to keep listening hands-free; Esc cancels.
- **Local speech recognition.** Whisper large-v3-turbo by default. It runs on an Intel GPU or NPU when there is one, and falls back to the processor otherwise.
- **Your languages.** English, German, French, Spanish, Chinese and Hindi (beta). Vocet detects which of the languages you chose you are speaking.
- **Dictionary.** Teach it names and jargon ("Kubernetes"), and fix words it keeps mishearing.
- **Snippets.** Say a short phrase ("my address") and Vocet types the full text.
- **History.** Your recent dictations, searchable, so nothing is lost if a paste goes wrong. Kept for 30 days by default, and you can turn it off.
- **Optional AI formatting.** A small local language model (Phi-4-mini) fixes punctuation, removes filler words and lays out lists. A strict check makes sure it only tidies your words and never changes what you said. It's off by default and also runs entirely on your PC.
- **Calm glass UI.** Follows Windows' light or dark mode, with a violet accent (or one of four others).

## Requirements

- Windows 11, 64-bit. (Windows 10 should work but hasn't been tested yet.)
- About 2 GB of free disk space (the app, its Python environment and the speech model). AI formatting needs another 2.4 GB.
- A microphone.
- An Intel GPU or NPU makes recognition fastest. Without one, Vocet runs on the processor, more slowly; the English-only Fast model (Settings > Speech model) is quicker there.
- AI formatting needs an Intel GPU and at least 16 GB of memory, and works in English, German, French and Spanish.

## Install

1. **Download Vocet:** [click here to download it](https://github.com/KMGSL67/vocet/archive/refs/heads/main.zip) (or, at the top of this page, click the green **Code** button > **Download ZIP**).
2. Open your **Downloads** folder, right-click the ZIP file > **Extract All** > **Extract**.
3. In the new folder, double-click **install.cmd**.

> [!NOTE]
> If Windows says **"Windows protected your PC"**: click **More info**, then **Run anyway**. Vocet isn't signed yet because it's a free beta.

Vocet opens by itself when it's installed. Next time, find it in the Start menu or on your desktop.

The first time Vocet opens, it offers to download its speech model (about 0.8 GB, one time, from Hugging Face). Nothing downloads until you press the button. After that, Vocet works offline.

Good to know:

- Installing takes a few minutes and needs an internet connection. It sets Vocet up for your Windows account only, with no administrator rights. If the helper tool [uv](https://docs.astral.sh/uv/) isn't on your PC yet, the installer gets it first.
- Afterwards you can delete the ZIP and the extracted folder.
- To update Vocet, do the same three steps with a new download. Your settings, history and speech model are kept.

### Optional: AI formatting

Open Vocet's folder (paste `%LOCALAPPDATA%\Programs\Vocet` into the File Explorer address bar and press Enter) and double-click **download-ai-model.cmd** to download the AI formatting model (about 2.4 GB, one time, from Hugging Face). Then switch on **AI formatting** in Vocet's Settings.

### Uninstall

Open **Settings > Apps > Installed apps**, find **Vocet**, and choose **Uninstall** (or double-click **uninstall.cmd** in Vocet's folder). If Vocet is open, it asks you to quit it first. It removes Vocet, its speech model, the shortcuts and the "Start with Windows" entry, then asks before deleting your settings and history in `%LOCALAPPDATA%\Vocet`. The helper tool uv stays installed.

## Using Vocet

| Action | How |
|---|---|
| Dictate | Hold **Ctrl + Win**, speak, let go |
| Keep listening hands-free | Press **Space** while holding the keys, then tap the keys again to finish |
| Cancel | **Esc** while listening |
| Open the window | Click the tray icon |
| Pause dictation | Tray icon menu > Pause dictation |

You can pick another key (Right Ctrl, Right Alt, the Menu key, Scroll Lock or Pause) in Settings. Vocet doesn't type into password fields.

## Privacy

Your voice, your text and your history stay on your PC. The only thing the app downloads is a model, and only when you ask it to. See [PRIVACY.md](PRIVACY.md) for exactly what is stored and which hosts are contacted.

## Running from source

```
uv sync
uv run python -m vocet
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

Vocet is free software provided **"as is", without warranty of any kind**, as stated in the [MIT License](LICENSE). You use it at your own risk. The authors and contributors are not liable for any damage, data loss or other harm arising from installing or using it.

What it does to your PC, so you can judge for yourself: it installs into `%LOCALAPPDATA%\Programs\Vocet` (the app, its Python environment and the speech model) and runs as your normal Windows user, with no administrator rights. It adds Start menu and Desktop shortcuts and an entry in Installed apps, and keeps its settings, history and logs in `%LOCALAPPDATA%\Vocet`. If uv isn't installed, the installer installs it for your user. If you switch on "Start with Windows", it adds a startup entry for your user. It types text into the window you're dictating into, like a keyboard would. Uninstalling (Settings > Apps, or `uninstall.cmd`) removes the install folder, the shortcuts, the Installed apps entry and the startup entry and, if you confirm, its data.

## License

Vocet is released under the [MIT License](LICENSE). It uses third-party software and models under their own licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

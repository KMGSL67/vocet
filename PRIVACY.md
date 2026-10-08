# Privacy

Vocet is built to keep your voice and your words on your PC. This page says exactly what it stores, where, and when it uses the network. Every statement here describes what the code in this repository does.

## What stays on your PC

**Your voice.** The microphone is open only while you hold the dictation keys (or while hands-free listening is on, or while you test the microphone in the welcome screen). The recording is kept in memory, transcribed on your PC, and then discarded. Vocet never writes your audio to disk and never sends it anywhere.

**Your data folder: `%LOCALAPPDATA%\Vocet`**

| File | What's in it |
|---|---|
| `history.db` | Your dictations: the text, the time, the app you dictated into (its name and program path, used to show its icon), the language and the model used. Kept for 30 days by default. Settings > Privacy lets you choose 1 day, 7 days, forever, or no history at all, and delete it. |
| `settings.json` | Your settings, including your dictionary words and snippets. |
| `logs\vocet.log`, `logs\crash.log` | Timings and errors only. They never contain dictated text, clipboard contents or window titles. Your Windows user name and profile path are replaced with placeholders, so a log is safe to attach to a bug report. |
| `model-hashes.json`, `hardware.json`, `loading.json` | Bookkeeping: model file checksums, and which graphics chip worked or crashed, so a bad driver isn't retried every start. |
| `openvino-cache\`, `sounds\`, `grain.png` | Compiled GPU kernels, and the sounds and background texture Vocet generates for itself. |

**The models** are stored in the `models` folder inside Vocet's own folder.

**The clipboard.** Vocet types your text by pasting it, then puts back whatever was on your clipboard before. Your dictation never stays on the clipboard. Vocet doesn't type into password fields, and it doesn't keep what you said into one.

**Other apps.** Vocet notes which program has the keyboard focus (to paste into it and to show its icon in your history), and asks Windows whether the focused field is a password field. It never reads window titles or the contents of other apps.

## What goes over the network

The app makes **no network connections** except one kind: **a model download that you start yourself**.

| Download | When | Hosts |
|---|---|---|
| Speech model (Whisper, about 0.8 GB for the default) | Only when you press **Download** in the welcome screen or in Settings > Speech model | `huggingface.co`, `hf.co` and their subdomains (Hugging Face's file servers) |
| AI formatting model (Phi-4-mini, about 2.4 GB) | Only when you run `download-ai-model.cmd` | the same Hugging Face hosts |

How a download is kept in check:

- Vocet blocks every outgoing network connection from its own Python code, except to your own PC. During a download, and only for its duration, it lets connections through to the Hugging Face hosts above, and nothing else. Every blocked attempt is counted, and Settings > Privacy shows the count if there ever is one.
- Only one fixed version (commit) of each model is downloaded, and only the files listed in `vocet/models_manifest.json`. Every file's size and SHA-256 checksum is checked before it's used, and again before every load. No code files are downloaded from the model repository.
- No account, token or identifier is sent. Hugging Face's own telemetry is switched off.
- OpenVINO, the inference library, would otherwise send a usage event when it's first imported. Vocet writes OpenVINO's documented opt-out file (`%LOCALAPPDATA%\Intel Corporation\openvino_telemetry`) before loading it.

There is no analytics, no crash reporting, no update check and no account.

One honest limit: the connection blocker sees connections made by Python code. It can't see connections made directly by native libraries. None of Vocet's libraries are configured to connect anywhere, and the opt-outs above cover the ones that could.

## The installer

`install.cmd` (not the app) uses the network once, to set Vocet up:

- If [uv](https://docs.astral.sh/uv/) isn't installed, it downloads uv's official installer from `astral.sh`, which fetches uv from GitHub.
- `uv sync` downloads Vocet's Python libraries from the Python Package Index (`pypi.org`, `files.pythonhosted.org`) and, the first time, a Python 3.11 build from GitHub (Vocet always uses its own copy of Python, not one already on your PC).

After that, nothing else is installed or updated unless you run it again.

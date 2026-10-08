"""Downloads the optional AI formatting model (Phi-4-mini, OpenVINO INT4 build) once.

    download-ai-model.cmd          (in Vocet's folder; it runs the line below)
    .venv\\Scripts\\python.exe -m vocet.get_ai_model

The same path as the speech-model download (model_download.py): only the commit pinned in
models_manifest.json, only the files it lists, every file's size and SHA-256 checked before it's
moved into models\\llm\\phi-4-mini, and the network guard lets connections through only to
Hugging Face's hosts while it runs. After that, AI formatting can be switched on in Settings.
"""

import sys

from . import ai_format, integrity, model_download, privacy


def main() -> int:
    guard = privacy.lock_down()
    p = model_download.plan("llm", ai_format.MODEL)
    if integrity.present(p.key, p.target):
        print(f"The AI formatting model is already on this PC ({p.target}).")
        return 0
    print(f"Downloading the AI formatting model ({model_download.size_label(p.total)}) from {model_download.SOURCE}.")
    print("Press Ctrl+C to stop; running this again continues where it stopped.")
    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = int(100 * done / total) if total else 100
        if pct != last[0]:
            last[0] = pct
            print(f"\r  {pct:3d} %  ({model_download.size_label(done) if done else '0 MB'} of "
                  f"{model_download.size_label(total)})", end="", flush=True)

    try:
        with guard.allowing(model_download.HF_HOSTS):
            model_download.run(p, on_progress=progress, on_verifying=lambda: print("\nChecking the files..."))
    except KeyboardInterrupt:
        print("\nStopped. Run it again to continue.")
        return 1
    except Exception as exc:  # noqa: BLE001 - one plain sentence for the console
        print(f"\n{model_download.error_message(exc)} ({type(exc).__name__})")
        return 1
    finally:
        guard.uninstall()
    print("Done. Open Vocet's Settings and switch on AI formatting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

// Settings: six inset groups, most-used first. Every row says what it does;
// footers explain the consequence in plain words. Nothing here moves unless you touch it.
import QtQuick
import QtQuick.Layouts
import "components" as C

C.Page {
    id: page
    title: "Settings"

    readonly property var s: backend.settings
    readonly property int popUpWidth: 240     // every pop-up the same width, so their edges line up
    // A switch's 40 px track sits in a 44 px hit area: pull it 2 px right, so every trailing
    // control (pop-ups, buttons, switches, swatches) ends on the same line.
    readonly property int switchInset: -2

    // ------------------------------------------------------------------ copy

    // Shortcut: the keys' own caveat, when there is one worth knowing before you pick it.
    readonly property var hotkeyCaveats: ({
        "ralt": "On Swiss and German keyboards this is AltGr, which types @ # | [ ].",
        "menu": "Not every keyboard has one."
    })
    readonly property string shortcutDescription:
        "Hold it while you speak. " + (hotkeyCaveats[s.hotkey] || "Other keys still work normally.")

    readonly property string handsFreeDescription: backend.hotkeyIsCombo
        ? "Press Space while holding " + backend.hotkeyName + " to keep listening. Press " + backend.hotkeyName + " again to finish."
        : "Double-tap " + backend.hotkeyName + " to keep listening. Tap it once more to finish."

    // Languages you speak: a multi-select; Vocet detects among only these, and with one
    // it always writes that language. The sentences use English names, the control native ones.
    readonly property var languageNames: ({ "en": "English", "de": "German", "fr": "French", "es": "Spanish",
                                            "zh": "Chinese", "hi": "Hindi" })
    readonly property var chosenLanguages: s.languages || ["en"]
    readonly property string languageDescription:
        (chosenLanguages.length === 1 ? "Vocet always writes " + languageNames[chosenLanguages[0]] + "."
                                      : "Vocet picks the language you’re speaking.")
        + (chosenLanguages.indexOf("hi") >= 0 ? " Hindi is in beta, so expect more mistakes." : "")
    // Remove filler words: the sounds it drops in the languages you speak.
    readonly property var fillerExamples: ({ "en": "“um”", "de": "“äh”", "fr": "“euh”", "es": "“eh”",
                                             "zh": "“嗯”", "hi": "“अं”" })
    readonly property string fillerDescription: {
        const e = chosenLanguages.map(k => fillerExamples[k])
        const listed = e.length === 1 ? e[0] : e.slice(0, -1).join(", ") + " and " + e[e.length - 1]
        return "Removes sounds like " + listed + "."
    }

    // Speech model: what each choice means for you, without the hardware names, and without
    // speed or battery comparisons nobody has measured.
    readonly property var presetDescriptions: ({
        "fast": "English only. Smallest model.",
        "balanced": "English only. More accurate than Fast.",
        "accurate": "Fewest mistakes. Needed for German and other languages."
    })
    readonly property string aiFormattingText:
        "Tries to fix spelling, lists and self-corrections, on your PC. If you keep history, your original words stay on Home."
    readonly property string modelFooter: backend.status === "Ready" ? "Loaded and ready."
        : backend.status.indexOf("Loading") === 0 ? backend.status + (backend.status.endsWith(".") ? "" : "…")
        : backend.status === "Model failed to load"
            ? "Couldn’t load the speech model. Quit Vocet from its tray icon and start it again. If that doesn’t help, send the log files below."
        : backend.status


    // ------------------------------------------------------------------ groups

    // Two columns once the page is wide enough for two ~650 px columns (a maximised 1920 px
    // window): every row keeps its label and control within reach, and the page still fills the
    // window beside the sidebar. Reading order: left column top to bottom, then the right one.
    // Narrower, the right column simply follows the left one.
    readonly property bool twoColumns: columnWidth >= 1320
    revealTargets: twoColumns ? [dictationGroup, appearanceGroup, microphoneGroup, privacyGroup, modelGroup, generalGroup]
                              : [dictationGroup, microphoneGroup, modelGroup, appearanceGroup, privacyGroup, generalGroup]

    GridLayout {
        id: columnsGrid
        Layout.fillWidth: true
        columns: page.twoColumns ? 2 : 1
        columnSpacing: theme.space7
        rowSpacing: theme.space7
        readonly property real columnW: page.twoColumns ? Math.floor((page.columnWidth - columnSpacing) / 2) : page.columnWidth

        ColumnLayout {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: columnsGrid.columnW
            Layout.maximumWidth: columnsGrid.columnW
            spacing: theme.space7

            C.Group {
                id: dictationGroup
                title: "Dictation"
                footer: "Languages other than English need the Most accurate speech model."

                C.SettingRow {
                    title: "Shortcut"
                    description: page.shortcutDescription
                    C.PopUpButton {
                        objectName: "shortcutPicker"
                        Layout.preferredWidth: page.popUpWidth
                        model: backend.hotkeys
                        textRole: "label"
                        valueRole: "key"
                        value: page.s.hotkey
                        onPicked: (v) => backend.setSetting("hotkey", v)
                    }
                }
                C.SettingRow {
                    title: "Hands-free"
                    description: page.handsFreeDescription
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.hands_free
                        onToggled: backend.setSetting("hands_free", checked)
                    }
                }
                C.SettingRow {
                    title: "Languages you speak"
                    description: page.languageDescription
                    C.MultiPopUpButton {
                        objectName: "languagesPicker"
                        Layout.preferredWidth: page.popUpWidth
                        model: backend.spokenLanguages
                        values: page.chosenLanguages
                        onPicked: (values) => backend.setSetting("languages", values)
                    }
                }
                C.SettingRow {
                    title: "Remove filler words"
                    description: page.fillerDescription
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.remove_fillers
                        onToggled: backend.setSetting("remove_fillers", checked)
                    }
                }
                C.SettingRow {
                    title: "AI formatting"
                    // backend.aiFormattingStatus: "Getting AI formatting ready…", "On", or why this PC can't
                    // backend.aiFormattingLanguageNote: one sentence when it skips some of your languages
                    // "On" alone would replace the explanation: keep it and say the state first
                    description: (backend.aiFormattingStatus === "On" ? "On. " + page.aiFormattingText
                                 : backend.aiFormattingStatus !== "" ? backend.aiFormattingStatus
                                 : page.aiFormattingText)
                                 + (backend.aiFormattingLanguageNote !== "" ? " " + backend.aiFormattingLanguageNote : "")
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.ai_formatting === true
                        enabled: checked || backend.aiFormattingAvailable   // on stays switchable, so you can turn it off
                        onToggled: backend.setSetting("ai_formatting", checked)
                    }
                }
            }

            C.Group {
                id: microphoneGroup
                title: "Microphone"

                C.SettingRow {
                    title: "Input"
                    description: "If it’s unplugged, Vocet uses the Windows default."
                    C.PopUpButton {
                        objectName: "micPicker"
                        Layout.preferredWidth: page.popUpWidth
                        model: backend.mics
                        textRole: "label"
                        valueRole: "name"
                        value: page.s.mic || ""
                        onPicked: (v) => backend.setSetting("mic", v)
                    }
                }
                C.SettingRow {
                    title: "Sounds"
                    description: "A soft tick when Vocet starts and stops listening."
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.sounds
                        onToggled: backend.setSetting("sounds", checked)
                    }
                }
            }

            C.Group {
                id: modelGroup
                title: "Speech model"
                footer: page.modelFooter

                C.Row {  // only on a PC without the speech model: its download, which you start
                    visible: (backend.speechModel.state || "ready") !== "ready"
                    ModelDownload { Layout.fillWidth: true; showReady: false }
                }
                Repeater {
                    model: backend.presets
                    C.ChoiceRow {
                        required property var modelData
                        title: modelData.label
                        description: page.presetDescriptions[modelData.key]
                        checked: page.s.preset === modelData.key
                        onClicked: backend.setSetting("preset", modelData.key)
                    }
                }
            }
        }

        ColumnLayout {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: columnsGrid.columnW
            Layout.maximumWidth: columnsGrid.columnW
            spacing: theme.space7

            C.Group {
                id: appearanceGroup
                title: "Appearance"
                footer: "Vocet follows Windows’ light or dark mode."

                C.SettingRow {
                    title: "Accent colour"
                    description: picker.currentLabel
                    C.AccentPicker {
                        id: picker
                        Layout.rightMargin: -4          // 28 px targets around 20 px circles: the last circle meets the edge
                        value: page.s.accent
                        onPicked: (name) => backend.setSetting("accent", name)
                    }
                }
                C.SettingRow {
                    title: "Show the Vocet bar when idle"
                    description: "A small bar at the bottom of the screen. Off: Vocet appears only while you dictate."
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.show_idle
                        onToggled: backend.setSetting("show_idle", checked)
                    }
                }
            }

            C.Group {
                id: privacyGroup
                title: "Privacy"

                C.SettingRow {
                    // Only what the code guarantees; the blocked count only when there is one to report.
                    title: "Network use"
                    description: "Vocet doesn’t send your voice anywhere. The only download is the speech model, and only when you start it."
                        + (backend.networkBlocked > 0 ? " Vocet blocked " + backend.networkBlocked
                           + (backend.networkBlocked === 1 ? " connection attempt; the log files have the details." : " connection attempts; the log files have the details.") : "")
                    C.Icon {
                        name: "shield"
                        size: 16
                        color: theme.textSecondary
                        Accessible.ignored: true
                    }
                }
                C.SettingRow {
                    title: "Keep history"
                    description: "Saved only on this PC, in your user folder."
                    C.PopUpButton {
                        objectName: "historyPicker"
                        Layout.preferredWidth: page.popUpWidth
                        model: backend.historyOptions
                        textRole: "label"
                        valueRole: "days"
                        value: page.s.history_days === null || page.s.history_days === undefined ? -1 : page.s.history_days
                        onPicked: (v) => backend.setSetting("history_days", v)
                    }
                }
                C.SettingRow {
                    title: "Delete history"
                    description: "Deletes every dictation saved on this PC."
                    C.Button {
                        text: "Delete all history…"
                        kind: "destructive"
                        onClicked: confirmClear.open()
                    }
                }
            }

            C.Group {
                id: generalGroup
                title: "General"
                footer: "Speech recognition by OpenAI Whisper."

                C.SettingRow {
                    title: "Start Vocet with Windows"
                    description: "Vocet waits in the tray, ready for your shortcut."
                    C.Switch {
                        Layout.rightMargin: page.switchInset
                        checked: page.s.start_with_windows
                        onToggled: backend.setSetting("start_with_windows", checked)
                    }
                }
                C.SettingRow {
                    title: "Welcome"
                    description: "The short tour from your first start: the shortcut, your microphone and a practice run."
                    C.Button {
                        objectName: "showWelcome"
                        text: "Show again"
                        onClicked: backend.showWelcome()
                    }
                }
                C.SettingRow {
                    title: "Log files"
                    description: "Timings and errors only. Vocet doesn’t write what you said to the log."
                    C.Button {
                        text: "Open folder"
                        onClicked: backend.openLogs()
                    }
                }
            }
        }
    }

    C.ConfirmDialog {
        id: confirmClear
        objectName: "confirmClear"
        title: "Delete all history?"
        message: "This removes every dictation saved on this PC. You can’t undo this."
        confirmText: "Delete all"
        destructive: true
        onConfirmed: backend.clearHistory()
    }
}

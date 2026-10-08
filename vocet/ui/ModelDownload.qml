// The speech model's download, for a PC that doesn't have it yet: the welcome's
// "Your voice" step and Settings › Speech model. It never starts by itself: you press Download.
// Reads backend.speechModel ({state, progress, size, doneLabel, source, message}; see window.py):
//   ready        one line with a checkmark (the welcome only: Settings hides the row then)
//   needed       what it is, how big, where from, and that it's checked; [Download]
//   downloading  a determinate bar, "312 MB of 0.8 GB"; [Cancel]
//   verifying    the bar full, "Checking the download (SHA-256)…"
//   failed       the reason in one sentence; [Try again]
//   cancelled    as needed, with "Download cancelled."
//   ModelDownload { Layout.fillWidth: true; showReady: true }
import QtQuick
import QtQuick.Layouts
import "components" as C

ColumnLayout {
    id: dl
    property bool showReady: true
    readonly property var m: backend.speechModel || ({ state: "ready" })
    readonly property string state: m.state || "ready"
    readonly property bool busy: state === "downloading" || state === "verifying"
    readonly property Item primaryButton: action
    spacing: theme.space3
    visible: state !== "ready" || showReady

    RowLayout {  // ready
        visible: dl.state === "ready"
        spacing: theme.space3
        C.Icon { name: "checkmark"; size: 16; color: theme.success; Layout.alignment: Qt.AlignVCenter }
        C.Txt {
            text: "The speech model is on this PC and ready."
            textStyle: "callout"
            tone: "secondary"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }

    ColumnLayout {  // everything else
        visible: dl.state !== "ready"
        spacing: theme.space3
        Layout.fillWidth: true

        RowLayout {
            spacing: theme.space5
            Layout.fillWidth: true
            ColumnLayout {
                spacing: theme.space1
                Layout.fillWidth: true
                C.Txt {
                    text: dl.busy ? "Downloading the speech model" : "Vocet needs its speech model"
                    textStyle: "body"
                    semibold: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                C.Txt {
                    text: dl.state === "downloading" ? dl.m.doneLabel + " of " + dl.m.size + " from " + dl.m.source
                        : dl.state === "verifying" ? "Checking the download…"
                        : dl.state === "failed" ? dl.m.message
                        : (dl.state === "cancelled" ? "Download cancelled. " : "")
                          + "A one-time download of " + dl.m.size + " from " + dl.m.source
                          + ". Vocet checks the file before using it."
                    textStyle: "callout"
                    tone: dl.state === "failed" ? "danger" : "secondary"
                    tabular: dl.state === "downloading"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Accessible.role: Accessible.StaticText
                }
            }
            C.Button {
                id: action
                visible: dl.state !== "verifying"
                text: dl.state === "downloading" ? "Cancel" : dl.state === "failed" ? "Try again" : "Download"
                onClicked: dl.state === "downloading" ? backend.cancelDownload() : backend.downloadModel()
                Layout.alignment: Qt.AlignVCenter
            }
            C.Spinner { visible: dl.state === "verifying"; running: visible; size: 16; Layout.alignment: Qt.AlignVCenter }
        }
        C.ProgressBar {
            visible: dl.busy
            value: dl.state === "verifying" ? 1 : (dl.m.progress || 0)
            label: "Downloading the speech model, " + Math.round(100 * (dl.m.progress || 0)) + " %"
            Layout.fillWidth: true
        }
    }
}

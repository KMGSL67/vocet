// Snippets: say a short phrase, Vocet types the full text.
// "New snippet…" in the header opens a sheet ("When I say" / "Vocet types"). Rows show the
// trigger and a one-line preview, and open the edit sheet on click; remove on hover or focus.
import QtQuick
import QtQuick.Layouts
import "components" as C

C.Page {
    id: page
    title: "Snippets"
    description: "Say a short phrase, and Vocet types the full text instead."
    headerAction: C.Button {
        id: newButton
        text: "New snippet…"
        kind: "primary"
        onClicked: page.openNew()
    }

    readonly property var snippets: backend.settings.snippets
    property int editIndex: -1

    function openNew() {
        editIndex = -1
        sheet.returnFocus = null              // back to what opened it (New snippet…, or Ctrl+N's focus)
        sheet.title = "New snippet"
        sheet.primaryText = "Add snippet"
        triggerField.text = ""
        bodyField.text = ""
        sheet.open()
    }

    function openEdit(index, data) {
        editIndex = index
        // back to the row: saving rebuilds the rows, so look it up when the sheet closes
        sheet.returnFocus = () => snippetRows.itemAt(Math.min(index, snippetRows.count - 1))
        sheet.title = "Edit snippet"
        sheet.primaryText = "Save"
        triggerField.text = data.trigger
        bodyField.text = data.text
        sheet.open()
    }

    // Removing a row rebuilds the list: the focus goes on to the next row's remove button (the
    // previous one at the end, New snippet… once none are left) instead of nowhere.
    function removeAt(index, ring) {
        backend.removeSnippet(index)
        const reason = ring ? Qt.TabFocusReason : Qt.OtherFocusReason
        Qt.callLater(() => {
            const next = snippetRows.count > 0 ? snippetRows.itemAt(Math.min(index, snippetRows.count - 1)) : null
            if (next) next.removeButton.forceActiveFocus(reason)
            else newButton.forceActiveFocus(reason)
        })
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: page.active
        onActivated: page.openNew()
    }

    C.Group {
        visible: page.snippets.length > 0
        Repeater {
            id: snippetRows
            model: page.snippets
            delegate: C.Row {
                id: snipRow
                required property var modelData
                required property int index
                readonly property Item removeButton: snippetRemove
                interactive: true
                minHeight: 52
                onClicked: page.openEdit(index, modelData)
                RowLayout {
                    Layout.fillWidth: true
                    spacing: theme.space4
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: theme.space1
                        C.Txt {
                            text: snipRow.modelData.trigger
                            textStyle: "headline"
                            heading: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        C.Txt {
                            text: snipRow.modelData.text
                            textStyle: "footnote"
                            tone: "secondary"
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            Layout.fillWidth: true
                        }
                    }
                    C.IconButton {
                        id: snippetRemove
                        iconName: "close"
                        label: "Remove " + snipRow.modelData.trigger
                        opacity: snipRow.isHovered || hovered || visualFocus ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: theme.motionFast } }
                        onClicked: page.removeAt(snipRow.index, visualFocus)
                    }
                }
            }
        }
    }

    C.EmptyState {
        visible: page.snippets.length === 0
        iconName: "snippets"
        title: "No snippets yet"
        text: "Save text you type often, like an email address or a meeting link, then say a short phrase to insert it."
    }

    C.Sheet {
        id: sheet
        objectName: "snippetSheet"
        primaryEnabled: triggerField.text.trim() !== "" && bodyField.text.trim() !== ""
        onAccepted: {
            if (page.editIndex >= 0)
                backend.updateSnippet(page.editIndex, triggerField.text.trim(), bodyField.text.trim())
            else
                backend.addSnippet(triggerField.text.trim(), bodyField.text.trim())
        }

        C.TextField {
            id: triggerField
            label: "When I say"
            placeholderText: "my calendar link"
            Layout.fillWidth: true
        }
        C.TextArea {
            id: bodyField
            objectName: "snippetBody"
            label: "Vocet types"
            placeholderText: "https://cal.example.com/me"
            Layout.fillWidth: true
        }
    }
}

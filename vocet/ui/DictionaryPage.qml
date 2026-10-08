// Dictionary: names, jargon and product words Vocet should spell
// right. An add row inside the group, then rows A-Z laid out as a two-column table under its
// fields: the term under "Add a word or name", "fixes "…"" under "Often heard as", and the
// remove button (hover or focus) under Add. Vocet gives these words to the speech model as hints.
// As in Snippets, a row opens the edit sheet on click (or Enter): "Edit word" with the same two
// fields, [Save] [Cancel]; a term another entry already has is refused in the sheet.
import QtQuick
import QtQuick.Layouts
import "components" as C

C.Page {
    id: page
    title: "Dictionary"
    description: "Names and terms Vocet should spell correctly. If it still mishears one, add what it hears."

    readonly property var words: backend.settings.dictionary
    readonly property var sorted: {
        const list = words.slice()
        list.sort((a, b) => a.term.localeCompare(b.term, undefined, { sensitivity: "base" }))
        return list
    }

    function add() {
        if (term.text.trim() === "") return
        backend.addWord(term.text.trim(), heard.text.trim())
        term.text = ""
        heard.text = ""
        term.forceActiveFocus()
    }

    // the entry's index in backend.settings.dictionary (rows show it sorted), -1 if it's gone
    function indexOf(t) {
        const key = t.toLowerCase()
        return words.findIndex(w => w.term.toLowerCase() === key)
    }

    // Removing a word rebuilds the rows: the focus goes on to the next row's remove button (the
    // previous one at the end, the add field once none are left) instead of nowhere.
    function removeRow(t, ring) {
        const i = indexOf(t)
        if (i < 0) return
        const row = sorted.findIndex(w => w.term.toLowerCase() === t.toLowerCase())
        backend.removeWord(i)
        const reason = ring ? Qt.TabFocusReason : Qt.OtherFocusReason
        Qt.callLater(() => {
            const next = wordRows.count > 0 ? wordRows.itemAt(Math.max(0, Math.min(row, wordRows.count - 1))) : null
            if (next) next.removeButton.forceActiveFocus(reason)
            else term.input.forceActiveFocus(reason)
        })
    }

    property string editing: ""          // the term of the entry in the edit sheet
    readonly property int editIndex: editing !== "" ? indexOf(editing) : -1
    // another entry already has the new term: updateWord would refuse it, so the sheet says so
    readonly property bool editClash: {
        const t = editTerm.text.trim().toLowerCase()
        return t !== "" && words.some((w, i) => i !== editIndex && w.term.toLowerCase() === t)
    }

    function openEdit(entry) {
        editing = entry.term
        // back to the entry's row: saving rebuilds (and re-sorts) the rows, so look it up when the
        // sheet closes, under its new term if it was renamed
        sheet.returnFocus = () => {
            const key = editing.toLowerCase()
            for (let i = 0; i < wordRows.count; i++) {
                const r = wordRows.itemAt(i)
                if (r && r.modelData.term.toLowerCase() === key) return r
            }
            return null
        }
        editTerm.text = entry.term
        editHeard.text = entry.heard
        sheet.open()
    }

    function saveEdit() {
        const t = editTerm.text.trim()
        backend.updateWord(editIndex, t, editHeard.text.trim())
        if (indexOf(t) >= 0) editing = t          // saved: the row now goes by the new term
    }

    C.Group {
        title: "Words"
        count: page.words.length > 0 ? page.words.length + (page.words.length === 1 ? " word" : " words") : ""
        footer: "Vocet gives these words to the speech model as hints."

        C.Row {  // the add row: its two fields are the table's two columns
            id: addRow
            RowLayout {
                id: addLayout
                Layout.fillWidth: true
                spacing: theme.space3
                C.TextField {
                    id: term
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignBottom
                    label: "Word or name"
                    placeholderText: "Add a word or name"
                    onAccepted: page.add()
                }
                C.TextField {
                    id: heard
                    // the second column: 40 % of the fields, 200 px at least
                    Layout.preferredWidth: Math.max(200, Math.round((addLayout.width - addButton.width - 2 * addLayout.spacing) * 0.4))
                    Layout.alignment: Qt.AlignBottom
                    label: "Often heard as"
                    placeholderText: "Optional"
                    onAccepted: page.add()
                }
                C.Button {
                    id: addButton
                    text: "Add"
                    kind: "primary"
                    Layout.alignment: Qt.AlignBottom
                    enabled: term.text.trim() !== ""
                    onClicked: page.add()
                }
            }
        }

        C.Row {
            visible: page.words.length === 0
            C.Txt {
                text: "No words yet. Add names you say often: people, projects, places."
                textStyle: "body"
                tone: "secondary"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }

        Repeater {
            id: wordRows
            model: page.sorted
            delegate: C.Row {  // the word under the first field, what it fixes under the second
                id: wordRow
                required property var modelData
                readonly property Item removeButton: removeBtn
                objectName: "dictionaryRow"
                Layout.fillWidth: true
                minHeight: 44
                interactive: true                       // click or Enter: the edit sheet, as in Snippets
                onClicked: page.openEdit(modelData)
                Accessible.name: modelData.term + (modelData.heard !== "" ? ", fixes " + modelData.heard : "")
                Accessible.description: "Edit"
                HoverHandler { id: rowHover }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: addLayout.spacing
                    C.Txt {
                        text: wordRow.modelData.term
                        textStyle: "body"
                        elide: Text.ElideRight
                        Layout.leftMargin: term.input.leftPadding        // on the field's text
                        Layout.preferredWidth: term.width - term.input.leftPadding
                        Layout.maximumWidth: term.width - term.input.leftPadding
                    }
                    C.Txt {
                        text: wordRow.modelData.heard !== "" ? "fixes “" + wordRow.modelData.heard + "”" : ""
                        textStyle: "callout"
                        tone: "secondary"
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        Layout.leftMargin: heard.input.leftPadding
                    }
                    Item {  // under the Add button: the remove button, on hover or focus
                        Layout.preferredWidth: addButton.width
                        implicitHeight: removeBtn.implicitHeight
                        C.IconButton {
                            id: removeBtn
                            anchors.right: parent.right
                            iconName: "close"
                            label: "Remove " + wordRow.modelData.term
                            opacity: rowHover.hovered || hovered || visualFocus ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: theme.motionFast } }
                            onClicked: page.removeRow(wordRow.modelData.term, visualFocus)
                        }
                    }
                }
            }
        }
    }

    C.Sheet {
        id: sheet
        objectName: "dictionarySheet"
        title: "Edit word"
        primaryText: "Save"
        primaryEnabled: page.editIndex >= 0 && editTerm.text.trim() !== "" && !page.editClash
        onAccepted: page.saveEdit()

        C.TextField {
            id: editTerm
            objectName: "dictionaryEditTerm"
            label: "Word or name"
            placeholderText: "Kubernetes"
            error: page.editClash ? "“" + text.trim() + "” is already in your dictionary." : ""
            Layout.fillWidth: true
        }
        C.TextField {
            id: editHeard
            objectName: "dictionaryEditHeard"
            label: "Often heard as"
            placeholderText: "Optional"
            Layout.fillWidth: true
        }
    }
}

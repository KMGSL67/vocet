// A choice row: one option of a radio group, where the whole row is the control.
// Hover fillHover, click selects, and a 16 px accentText checkmark marks the current choice
// (a shape, not only a colour). Tab lands on the current choice; ↑/↓ move between the rows
// of the same group; Space or Enter selects. Announced as a radio button with its state.
//   C.Group {
//       title: "Speech model"
//       Repeater {
//           model: backend.presets
//           C.ChoiceRow {
//               required property var modelData
//               title: modelData.label; description: modelData.detail
//               checked: backend.settings.preset === modelData.key
//               onClicked: backend.setSetting("preset", modelData.key)
//           }
//       }
//   }
import QtQuick
import QtQuick.Layouts
import "." as C

C.Row {
    id: choice
    property string title: ""
    property string description: ""
    // `checked` is AbstractButton's own; checkable stays false, so a click never toggles it:
    // bind it to the setting and react in onClicked.
    readonly property bool isChoiceRow: true

    interactive: true
    focusPolicy: checked ? Qt.StrongFocus : Qt.ClickFocus
    Accessible.role: Accessible.RadioButton
    Accessible.name: title
    Accessible.description: description
    Accessible.checkable: true
    Accessible.checked: checked

    function step(delta) {
        const rows = []
        const kids = parent ? parent.children : []
        for (let i = 0; i < kids.length; i++)
            if (kids[i].isChoiceRow && kids[i].visible && kids[i].enabled)
                rows.push(kids[i])
        const next = rows[rows.indexOf(choice) + delta]
        if (next)
            next.forceActiveFocus(Qt.TabFocusReason)
    }
    Keys.onUpPressed: step(-1)
    Keys.onDownPressed: step(1)

    RowLayout {
        Layout.fillWidth: true
        spacing: theme.space7
        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: theme.space2
            C.Txt {
                text: choice.title
                textStyle: "body"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                Accessible.ignored: true
            }
            C.Txt {
                visible: choice.description !== ""
                text: choice.description
                textStyle: "subheadline"
                tone: "secondary"
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                Accessible.ignored: true
            }
        }
        C.Icon {
            name: "checkmark"
            size: 16
            color: theme.accentText
            opacity: choice.checked ? 1 : 0
            Layout.alignment: Qt.AlignVCenter
        }
    }
}

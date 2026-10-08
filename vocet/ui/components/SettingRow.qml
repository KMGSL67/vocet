// A settings row: title in body textPrimary, optional description below in
// subheadline textSecondary (wraps, up to 3 lines), the control trailing and vertically
// centred, at least 24 px from the text. Min height 44 (one line), about 64 with a description.
// No hover state: only the control reacts. Several controls get 12 px between them.
//   C.SettingRow {
//       title: "Hands-free"
//       description: "Press Space while holding Ctrl + Win to keep listening."
//       C.Switch { checked: …; onToggled: … }
//   }
// Controls with an empty `label` get the row title as their accessible name, and the
// description as their accessible description.
import QtQuick
import QtQuick.Layouts
import "." as C

C.Row {
    id: setting
    property string title: ""
    property string description: ""
    default property alias control: slot.data

    interactive: false
    // The 12 px vertical padding belongs to the text; a 32 px control may use it, so a
    // one-line row with a pop-up or segmented control stays 44 px.
    topPadding: 6
    bottomPadding: 6
    implicitHeight: Math.max(minHeight, texts.implicitHeight + 2 * theme.space4, slot.implicitHeight + 12)

    function labelControls() {
        for (let i = 0; i < slot.children.length; i++) {
            const c = slot.children[i]
            if (c.label !== undefined && c.label === "")
                c.label = Qt.binding(() => setting.title)
            if (c.Accessible && c.Accessible.description === "" && setting.description !== "")
                c.Accessible.description = Qt.binding(() => setting.description)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: theme.space7
        ColumnLayout {
            id: texts
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: theme.space2
            C.Txt {
                text: setting.title
                textStyle: "body"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            C.Txt {
                visible: setting.description !== ""
                text: setting.description
                textStyle: "subheadline"
                tone: "secondary"
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.maximumWidth: 560
            }
        }
        RowLayout {
            id: slot
            Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
            spacing: theme.space4
            onChildrenChanged: setting.labelControls()
        }
    }
    Component.onCompleted: labelControls()
}

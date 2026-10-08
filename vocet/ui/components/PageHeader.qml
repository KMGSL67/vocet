// A page header: the title in largeTitle, naming the page, never the app. At most
// one trailing action (the 240 px search field or one button), vertically centred on the
// title line. An optional description in callout textSecondary, 4 px below, max 560 px and
// 2 lines, and an optional accessory under it (the status line on Home).
// C.Page builds one from its title/description/headerAction/headerAccessory; use this
// directly only for a custom layout.
import QtQuick
import QtQuick.Layouts
import "." as C

Item {
    id: header
    property string title: ""
    property string description: ""
    property alias action: actionSlot.data
    property alias accessory: accessorySlot.data
    implicitWidth: column.implicitWidth
    implicitHeight: column.implicitHeight

    ColumnLayout {
        id: column
        width: parent.width
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            spacing: theme.space7
            C.Txt {
                text: header.title
                textStyle: "largeTitle"
                heading: true
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
            }
            RowLayout {
                id: actionSlot
                visible: children.length > 0
                Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                spacing: theme.space4
            }
        }
        C.Txt {
            visible: header.description !== ""
            text: header.description
            textStyle: "callout"
            tone: "secondary"
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.maximumWidth: 560
            Layout.topMargin: theme.space2
        }
        ColumnLayout {
            id: accessorySlot
            visible: children.length > 0
            Layout.fillWidth: true
            Layout.topMargin: theme.space2
            spacing: 0
        }
    }
}

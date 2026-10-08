// An empty state: an optional 32 px glyph (textTertiary), a title2 title, a body
// textSecondary line (max 360 px, centred) and at most one plain or secondary action. It sits
// 48 px under the header. Every blank screen says what to do next. No logo here.
//   C.EmptyState {
//       iconName: "history"
//       title: "No dictations yet"
//       text: "Hold Ctrl + Win in any app, say something, and let go. Your words appear where you're typing."
//       actionText: "Try it here"; onAction: …
//   }
import QtQuick
import QtQuick.Layouts
import "." as C

ColumnLayout {
    id: empty
    property string iconName: ""
    property string title: ""
    property string text: ""
    property string actionText: ""
    property string actionKind: "plain"
    signal action()

    Layout.fillWidth: true
    Layout.topMargin: theme.space10 - theme.space6   // 48 px under the header (the page adds 20)
    spacing: 0

    // A layout is only as wide as its widest-allowed child; this one lets it fill the column,
    // so the content centres in the page rather than hugging the left.
    Item { Layout.fillWidth: true; implicitHeight: 0 }
    C.Icon {
        visible: empty.iconName !== ""
        name: empty.iconName
        size: 32
        color: theme.textTertiary
        Layout.alignment: Qt.AlignHCenter
        Layout.bottomMargin: theme.space4
    }
    C.Txt {
        text: empty.title
        textStyle: "title2"
        heading: true
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        Layout.fillWidth: true
        Layout.maximumWidth: 360
        Layout.alignment: Qt.AlignHCenter
    }
    C.Txt {
        visible: empty.text !== ""
        text: empty.text
        textStyle: "body"
        tone: "secondary"
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        Layout.fillWidth: true
        Layout.maximumWidth: 360
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: theme.space2
    }
    C.Button {
        visible: empty.actionText !== ""
        text: empty.actionText
        kind: empty.actionKind
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: theme.space5
        onClicked: empty.action()
    }
}

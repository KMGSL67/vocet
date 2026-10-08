// Home's practice box: "Try it here" in the empty state reveals it, so the
// first dictation is taught by doing. One multi-line field, centred under the empty state
// (max 480 px), with a footnote. It takes the focus as soon as it appears, so holding the
// shortcut types straight into it. Esc closes it.
// Deliberately not boxed in a group: a field well inside a group box read as a card in a card.
//   HomePractice { visible: page.practiceOpen; onDismissed: page.practiceOpen = false }
import QtQuick
import QtQuick.Layouts
import "components" as C

ColumnLayout {
    id: practice
    property alias text: field.text
    signal dismissed()

    function focusField() { field.input.forceActiveFocus(Qt.OtherFocusReason) }
    onVisibleChanged: if (visible) Qt.callLater(focusField)
    Component.onCompleted: if (visible) Qt.callLater(focusField)

    Layout.fillWidth: true
    Layout.maximumWidth: 480
    Layout.alignment: Qt.AlignHCenter
    spacing: 0

    C.TextArea {
        id: field
        Layout.fillWidth: true
        minHeight: 96
        maxHeight: 200
        placeholderText: "Hold " + backend.hotkeyName + ", say “Hello”, and let go."
        accessibleName: "Practice dictation"
        Keys.onEscapePressed: practice.dismissed()
    }
    C.Txt {
        text: "If you keep history, what you say here is saved like any other dictation."
        textStyle: "footnote"
        tone: "secondary"
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        Layout.fillWidth: true
        Layout.topMargin: theme.space4
    }
}

// A toast, only for results with no better inline home ("Dictation deleted" with
// Undo). Bottom centre of the content column, 24 px above the bottom of the content area, so
// it never covers a page header or its search field. 40 px high, fits its content (max 480),
// radius 10, level 1: optional 16 px glyph, callout message, a plain 28 px action, a 24 px close
// button. In 200 ms (opacity, rising y +8 → 0), out 150 ms.
// Stays 6 s, paused while hovered or focused. One at a time: show() replaces the current one.
// Announced as an alert. Every action also has a shortcut (Main: Ctrl+Z undoes a delete).
//   toast.show("Dictation deleted", { action: "Undo", onAction: () => backend.undoDelete() })
import QtQuick
import QtQuick.Layouts
import "." as C

FocusScope {
    id: toast
    property string message: ""
    property string iconName: ""
    property string actionText: ""
    property var onAction: null
    property bool shown: false
    property int timeout: 6000

    function show(text, options) {
        const o = options || {}
        message = text
        iconName = o.icon || ""
        actionText = o.action || ""
        onAction = o.onAction || null
        shown = true
        outAnim.stop()
        if (!inAnim.running && opacity < 1) {
            shift.y = backend.reducedMotion ? 0 : 8
            inAnim.restart()
        }
        timer.restart()
        Accessible.announce(text)
    }
    function hide() {
        if (!shown) return
        shown = false
        inAnim.stop()
        outAnim.restart()
    }

    width: Math.min(480, content.implicitWidth + 16 + 8)
    height: 40
    opacity: 0
    visible: opacity > 0
    Accessible.role: Accessible.AlertMessage
    Accessible.name: message

    Timer {
        id: timer
        interval: toast.timeout
        running: toast.shown && !hover.hovered && !toast.activeFocus
        onTriggered: toast.hide()
    }
    ParallelAnimation {
        id: inAnim
        NumberAnimation { target: toast; property: "opacity"; to: 1; duration: backend.reducedMotion ? theme.motionFast : theme.motionMedium; easing.type: Easing.OutCubic }
        NumberAnimation { target: shift; property: "y"; to: 0; duration: theme.motionMedium; easing.type: Easing.OutCubic }
    }
    NumberAnimation {
        id: outAnim
        target: toast
        property: "opacity"
        to: 0
        duration: backend.reducedMotion ? theme.motionFast : theme.motionBase
        easing.type: Easing.InCubic
    }

    Item {
        anchors.fill: parent
        transform: Translate { id: shift }
        HoverHandler { id: hover }
        C.Surface { anchors.fill: parent; level: 1; radius: theme.radiusToast }
        RowLayout {
            id: content
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: theme.space3
            C.Icon {
                visible: toast.iconName !== ""
                name: toast.iconName
                size: 16
                Layout.alignment: Qt.AlignVCenter
            }
            C.Txt {
                text: toast.message
                textStyle: "callout"
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.maximumWidth: 360
                Layout.alignment: Qt.AlignVCenter
                Layout.rightMargin: toast.actionText !== "" ? theme.space1 : theme.space2
                Accessible.ignored: true
            }
            C.Button {
                visible: toast.actionText !== ""
                text: toast.actionText
                kind: "plain"
                small: true
                Layout.alignment: Qt.AlignVCenter
                onClicked: {
                    if (toast.onAction) toast.onAction()
                    toast.hide()
                }
            }
            C.IconButton {
                iconName: "close"
                label: "Dismiss"
                size: 24
                Layout.alignment: Qt.AlignVCenter
                onClicked: toast.hide()
            }
        }
    }
}

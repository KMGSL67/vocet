// One keyboard key (design v4): 22 px high, min 28 px wide, 7 px side padding, radius 7, a small
// raised glass cap (C.Glass kind "keycap"). Label caption2 textPrimary.
// `large`: the welcome's hero keys (40 px high, min 56 wide, radius 10, headline label).
// `pressed`: the cap sinks 2 px and its shadow tightens (120 ms; instant under reduced motion).
// Use C.KeyCombo for a whole shortcut; it gives the group its spoken name.
import QtQuick
import "." as C

Item {
    id: cap
    property string label: ""
    property bool large: false
    property bool pressed: false
    implicitWidth: large ? Math.max(56, text.implicitWidth + 28) : Math.max(28, text.implicitWidth + 14)
    implicitHeight: large ? Math.max(40, text.implicitHeight + 16) : Math.max(22, text.implicitHeight + 8)
    Accessible.ignored: true

    Item {
        id: face
        width: parent.width
        height: parent.height
        y: cap.pressed ? 2 : 0
        Behavior on y { enabled: !backend.reducedMotion; NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        C.Glass { anchors.fill: parent; kind: "keycap"; radius: cap.large ? 10 : 7; shadow: !cap.pressed }
        Rectangle {  // pressed: the cap dims a little, like a key that's held down
            anchors.fill: parent
            radius: cap.large ? 10 : 7
            color: theme.fillPressed
            opacity: cap.pressed ? 1 : 0
            Behavior on opacity { enabled: !backend.reducedMotion; NumberAnimation { duration: 120 } }
        }
        C.Txt {
            id: text
            anchors.centerIn: parent
            text: cap.label
            textStyle: cap.large ? "headline" : "caption2"
            Accessible.ignored: true
        }
    }
}

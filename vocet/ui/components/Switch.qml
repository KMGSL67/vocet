// On/off switch (design v4 "Calm glass"): a 44 × 26 capsule in a 48 × 30 hit area.
// Off: a neutral glass groove with a white knob (small shadow). On: the accent's solid capsule
// with a faint sheen; the knob in switchOnThumb (white; black on Mono's white track).
// Hover: a faint wash. Pressed: the knob widens 4 px. Disabled: 40 %.
// The knob slides over 200 ms OutCubic and the track cross-fades 150 ms; instant under reduced
// motion. Switches live only in rows, and clicking the row text doesn't toggle.
//   C.Switch { label: "Hands-free"; checked: s.hands_free; onToggled: backend.setSetting("hands_free", checked) }
import QtQuick
import QtQuick.Effects
import QtQuick.Templates as T
import "." as C

T.Switch {
    id: sw
    property string label: ""
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"

    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down
    readonly property bool isFocused: demoState === "focus" || visualFocus
    readonly property int moveMs: backend.reducedMotion ? 0 : theme.motionMedium
    readonly property int fadeMs: backend.reducedMotion ? 0 : theme.motionBase

    implicitWidth: 48
    implicitHeight: 30
    padding: 0
    spacing: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.4
    Accessible.name: label
    Accessible.checkable: true
    Accessible.checked: checked

    indicator: Item {
        id: track
        width: 44
        height: 26
        x: Math.round((sw.width - width) / 2)
        y: Math.round((sw.height - height) / 2)

        C.Glass { anchors.fill: parent; kind: "track"; radius: height / 2 }
        C.Glass {
            anchors.fill: parent
            kind: "accent"
            radius: height / 2
            opacity: sw.checked ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: sw.fadeMs; easing.type: Easing.OutCubic } }
        }
        Rectangle {  // hover wash
            anchors.fill: parent
            radius: height / 2
            color: sw.checked ? Qt.rgba(1, 1, 1, theme.btnHover) : theme.fillHover
            opacity: sw.isHovered && !sw.isPressed ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: sw.fadeMs } }
        }
        Item {
            id: knob
            readonly property real d: 22
            height: d
            width: d + (sw.isPressed ? 4 : 0)
            x: sw.checked ? track.width - 2 - width : 2
            y: 2
            Behavior on x { NumberAnimation { duration: sw.moveMs; easing.type: Easing.OutCubic } }
            Behavior on width { NumberAnimation { duration: sw.moveMs; easing.type: Easing.OutCubic } }
            RectangularShadow {
                anchors.fill: parent
                anchors.topMargin: 1.5
                radius: height / 2
                blur: 5
                color: theme.mode === "dark" ? "#59000000" : "#33000000"
                visible: !theme.highContrast
            }
            Rectangle {
                anchors.fill: parent
                radius: height / 2
                antialiasing: true
                color: sw.checked ? theme.switchOnThumb : theme.thumb
                border.width: theme.highContrast ? 1 : 0
                border.color: theme.strokeStrong
                Behavior on color { ColorAnimation { duration: sw.fadeMs; easing.type: Easing.OutCubic } }
            }
        }
        C.FocusRing { show: sw.isFocused; controlRadius: height / 2 }
    }
    contentItem: Item {}
}

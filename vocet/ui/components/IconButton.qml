// An icon-only button (v4): a 28 × 28 circle, 16 px glyph in textSecondary; hover
// fillHover + textPrimary, pressed fillPressed, disabled 40 %. `label` is required: it's the
// tooltip and the accessible name. confirm() shows a success check for 1.2 s (after Copy).
//   C.IconButton { iconName: "copy"; label: "Copy"; onClicked: { backend.copyText(id); confirm() } }
import QtQuick
import QtQuick.Templates as T
import "." as C

T.AbstractButton {
    id: btn
    property string iconName: ""
    property string glyph: ""          // or a raw code point
    property string label: ""
    property int size: 28              // 24 for the toast's close button
    property int glyphSize: size >= 28 ? 16 : 12
    property bool confirmed: false
    property bool showTooltip: true
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"

    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down
    readonly property bool isFocused: demoState === "focus" || visualFocus

    function confirm() {
        confirmed = true
        resetConfirm.restart()
    }

    implicitWidth: size
    implicitHeight: size
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.Button
    Accessible.name: label
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    Timer { id: resetConfirm; interval: 1200; onTriggered: btn.confirmed = false }

    background: C.Fill {
        radius: height / 2
        hovered: btn.isHovered
        pressed: btn.isPressed
        tint: btn.isPressed ? theme.fillPressed : btn.isHovered ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
        C.FocusRing { show: btn.isFocused; controlRadius: height / 2 }
    }
    contentItem: Item {
        C.Icon {
            anchors.centerIn: parent
            name: btn.iconName
            glyph: btn.glyph
            size: btn.glyphSize
            color: btn.isHovered || btn.isPressed ? theme.textPrimary : theme.textSecondary
            opacity: btn.confirmed ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: theme.motionFast } }
        }
        C.Icon {
            anchors.centerIn: parent
            name: "checkmark"
            size: btn.glyphSize
            color: theme.success
            opacity: btn.confirmed ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: theme.motionFast } }
        }
    }

    C.Tooltip {
        text: btn.confirmed ? "Copied" : btn.label
        visible: btn.showTooltip && btn.label !== "" && (btn.hovered || btn.visualFocus)
    }
}

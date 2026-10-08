// A push button (design v4 "Calm glass"): a capsule, 34 px high (28 small), 18 px side padding,
// min width 72 (96 in dialogs), a semibold label, optional 16 px icon with an 8 px gap.
// Sentence case, verb-first; a trailing "…" only when more input follows ("Clear history…").
//   C.Button { text: "Add"; kind: "primary"; onClicked: … }
// kind: primary (one per view: the accent's solid capsule, a faint sheen, no glow)
//       secondary (most actions: raised neutral glass) | plain (inline text: Undo, Resume)
//       destructive (glass, danger label; `filled: true` = dangerFill, only in a confirm dialog).
// Hover lightens (primary) or tints (glass) over 150 ms; pressed dims and scales to 0.97 in
// 120 ms. Under reduced motion only the colour changes, at most 100 ms.
import QtQuick
import QtQuick.Templates as T
import "." as C

T.Button {
    id: btn
    property string kind: "secondary"
    property bool filled: false        // destructive only: dangerFill + onDanger, for confirm dialogs
    property string iconName: ""
    property bool dialog: false        // min width 96
    property bool small: false         // 28 px high, 12 px padding (toast, status line)
    property string accessibleName: text
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"

    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down
    readonly property bool isFocused: demoState === "focus" || visualFocus
    readonly property bool dangerFilled: kind === "destructive" && filled
    readonly property bool glassy: kind === "secondary" || (kind === "destructive" && !filled)
    readonly property bool mono: theme.accentName === "mono"
    // Mono: the accent's text colour is the label colour, so plain buttons need a shape cue.
    readonly property bool monoAccent: Qt.colorEqual(theme.accentText, theme.textPrimary)

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: kind === "plain" ? (small ? 8 : 12) : small ? 12 : 18
    rightPadding: leftPadding
    topPadding: 0
    bottomPadding: 0
    implicitHeight: Math.max(small ? 28 : 34, label.implicitHeight + 12)
    implicitWidth: Math.max(small || kind === "plain" ? 0 : dialog ? 96 : 72, implicitContentWidth + leftPadding + rightPadding)
    opacity: enabled ? 1 : 0.45
    scale: isPressed && !backend.reducedMotion ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.Button
    Accessible.name: accessibleName
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    readonly property color labelColor: kind === "primary" ? theme.onAccent
        : dangerFilled ? theme.onDanger
        : kind === "destructive" ? theme.dangerText
        : kind === "plain" ? theme.accentText
        : theme.textPrimary

    background: Item {
        C.Glass {
            anchors.fill: parent
            visible: btn.kind === "primary"
            kind: "accent"
            radius: height / 2
        }
        Rectangle {
            anchors.fill: parent
            visible: btn.dangerFilled
            radius: height / 2
            color: theme.dangerFill
        }
        C.Glass {
            anchors.fill: parent
            visible: btn.glassy
            kind: "control"
            radius: height / 2
        }
        C.Fill {  // hover lift / press dim
            anchors.fill: parent
            radius: height / 2
            hovered: btn.isHovered
            pressed: btn.isPressed
            readonly property color over: btn.kind === "primary" || btn.dangerFilled
                ? (btn.mono && theme.mode === "dark" ? Qt.rgba(0, 0, 0, 0.06) : Qt.rgba(1, 1, 1, theme.btnHover))
                : btn.glassy ? theme.controlHover : theme.fillHover
            readonly property color down: btn.kind === "primary" || btn.dangerFilled ? Qt.rgba(0, 0, 0, 0.16)
                : btn.glassy ? theme.controlPressed : theme.fillPressed
            tint: !btn.enabled ? Qt.alpha(over, 0) : btn.isPressed ? down : btn.isHovered ? over : Qt.alpha(over, 0)
            border.width: theme.highContrast ? 1 : 0
            border.color: theme.strokeStrong
        }
        C.FocusRing { show: btn.isFocused; controlRadius: height / 2 }
    }

    contentItem: Item {
        implicitWidth: content.implicitWidth
        implicitHeight: label.implicitHeight
        Row {
            id: content
            anchors.centerIn: parent
            spacing: theme.space3
            C.Icon {
                visible: btn.iconName !== ""
                name: btn.iconName
                size: 16
                color: btn.labelColor
                anchors.verticalCenter: parent.verticalCenter
            }
            C.Txt {
                id: label
                text: btn.text
                textStyle: "body"
                semibold: btn.kind !== "plain"
                color: btn.labelColor
                font.underline: btn.kind === "plain" && btn.monoAccent && btn.enabled
                anchors.verticalCenter: parent.verticalCenter
                Accessible.ignored: true
            }
        }
    }
}

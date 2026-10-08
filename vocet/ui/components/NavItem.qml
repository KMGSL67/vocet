// One sidebar destination (design v4): a 40 px capsule (40 × 40 in the rail). The 16 px icon at
// x 15, the label at x 46. Unselected: icon textSecondary, label regular. Selected: a neutral
// glass lens behind it (C.Sidebar draws one that glides between items; standalone, the item
// draws its own), the icon in accentText and the label semibold: the accent is only the icon.
// Hover: a faint wash (100 / 150 ms). In the rail the label goes and a tooltip names the page.
// C.Sidebar handles ↑/↓.
import QtQuick
import QtQuick.Templates as T
import "." as C

T.AbstractButton {
    id: item
    property string iconName: ""
    property string label: ""
    property bool selected: false
    property bool rail: false
    property bool ownHighlight: true   // false: the sidebar draws the (gliding) selection
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"

    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down
    readonly property bool isFocused: demoState === "focus" || visualFocus

    implicitWidth: rail ? 40 : 204
    implicitHeight: Math.max(40, theme.bodyLine + 20)
    hoverEnabled: true
    focusPolicy: selected ? Qt.StrongFocus : Qt.ClickFocus
    Accessible.role: Accessible.PageTab
    Accessible.name: label
    Accessible.selected: selected
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    background: Item {
        C.Glass {
            anchors.fill: parent
            visible: item.selected && item.ownHighlight
            kind: "navSel"
            radius: height / 2
        }
        C.Fill {
            anchors.fill: parent
            radius: height / 2
            hovered: item.isHovered
            pressed: item.isPressed
            tint: item.isPressed ? theme.fillPressed
                : item.isHovered && !item.selected ? theme.fillHover
                : Qt.alpha(theme.fillHover, 0)
            border.width: theme.highContrast && item.selected ? 2 : 0
            border.color: theme.strokeStrong
        }
        C.FocusRing { show: item.isFocused; controlRadius: height / 2 }
    }
    contentItem: Item {
        C.Icon {
            x: item.rail ? Math.round((item.width - width) / 2) : 15
            anchors.verticalCenter: parent.verticalCenter
            name: item.iconName
            size: Math.round(16 * Math.min(1.25, theme.textScale))   // grows a little with Windows' Text size
            color: item.selected ? theme.accentText : theme.textSecondary
            Behavior on color { enabled: !backend.reducedMotion; ColorAnimation { duration: theme.motionBase } }
        }
        C.Txt {
            visible: !item.rail
            x: 46
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 12
            text: item.label
            textStyle: "body"
            semibold: item.selected
            elide: Text.ElideRight
            Accessible.ignored: true
        }
    }
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0

    C.Tooltip {
        text: item.label
        visible: item.rail && (item.hovered || item.visualFocus)
    }
}

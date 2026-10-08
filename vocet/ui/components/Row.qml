// One row of an inset grouped section. Padding 12 vertical, 16 horizontal,
// min height 44, grows with its content (and with Windows' Text size). A hairline separator
// inset 16 px from the leading edge, flush right, except after the last row.
// Put content in it as a layout:  C.Row { RowLayout { … } }
//
// interactive: hover fillHover (100/150 ms), pressed fillPressed, focusable, emits clicked().
//   The wash is a rounded shape 6 px inside the card (washInset). Rows show keyboard focus as a
//   highlight (fillSelected), not a ring. Separators are inset 16 px on both sides.
// selected:    fillSelected (the keyboard-selected history row).
// first/last:  round the highlight to the group's 12 px corners. C.Group sets them for you.
// boxed:       the row paints its own slice of the glass card (C.Glass sliceTop/sliceBottom): use
//   it for ListView delegates (history), where one card per day comes from the rows themselves:
//     first: ListView.previousSection !== ListView.section
//     last:  ListView.nextSection !== ListView.section
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

T.AbstractButton {
    id: row
    property bool interactive: false
    property bool selected: false
    property bool first: false
    property bool last: false
    property bool boxed: false
    property bool separator: !last
    property real separatorInset: theme.space5
    property real washInset: 6          // the hover wash sits 6 px inside the card
    property int minHeight: 44
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"
    default property alias content: body.data

    readonly property bool isHovered: demoState === "hover" || (interactive && hovered)
    readonly property bool isPressed: demoState === "pressed" || (interactive && down)
    readonly property bool isFocused: demoState === "focus" || (interactive && visualFocus)
    readonly property real topRadius: first ? theme.radiusGroup : 0
    readonly property real bottomRadius: last ? theme.radiusGroup : 0
    readonly property real hairline: 1 / Screen.devicePixelRatio

    Layout.fillWidth: true
    hoverEnabled: interactive
    focusPolicy: interactive ? Qt.StrongFocus : Qt.NoFocus
    leftPadding: theme.space5
    rightPadding: theme.space5
    topPadding: theme.space4
    bottomPadding: theme.space4
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: Math.max(minHeight, implicitContentHeight + topPadding + bottomPadding)
    Accessible.role: interactive ? Accessible.ListItem : Accessible.Grouping
    Keys.onReturnPressed: if (interactive) clicked()
    Keys.onEnterPressed: if (interactive) clicked()

    background: Item {
        C.Glass {  // the day card's slice (ListView use): no corners, rim or shadow where the box goes on
            visible: row.boxed
            anchors.fill: parent
            kind: "card"
            radius: theme.radiusGroup
            sliceTop: !row.first
            sliceBottom: !row.last
            rimSpanTop: 56
            rimSpanBottom: 44
        }
        C.Fill {  // hover, press and the keyboard selection: a rounded wash inset in the card
            anchors.fill: parent
            anchors.leftMargin: row.washInset
            anchors.rightMargin: row.washInset
            anchors.topMargin: row.first ? row.washInset : 0
            anchors.bottomMargin: row.last ? row.washInset : 0
            radius: theme.radiusGroup - row.washInset
            hovered: row.isHovered
            pressed: row.isPressed
            tint: row.isPressed ? theme.fillPressed
                : (row.selected || row.isFocused) ? theme.fillSelected
                : row.isHovered ? theme.fillHover
                : Qt.alpha(theme.fillHover, 0)
            border.width: theme.highContrast && (row.selected || row.isFocused) ? 2 : 0
            border.color: theme.strokeStrong
        }
        Rectangle {
            visible: row.separator
            x: row.separatorInset
            width: parent.width - x - theme.space5
            height: row.hairline
            y: parent.height - height
            color: theme.separator
        }
    }
    contentItem: ColumnLayout {
        id: body
        spacing: 0
    }
}

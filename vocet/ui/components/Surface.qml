// An elevated panel (design v4): opaque bgElevated with a glass rim and a soft shadow, drawn in
// one static pass (C.Glass kind "elevated").
// level 1: menus, pop-up lists, tooltips, the toast (shadow y 4, blur 16, shadow1).
// level 2: dialogs and sheets (shadow y 12, blur 36, shadow2).
import QtQuick
import "." as C

Item {
    id: surface
    property int level: 1
    property real radius: theme.radiusMenu

    C.Glass { anchors.fill: parent; kind: "elevated"; level: surface.level; radius: surface.radius }
    Rectangle {
        visible: theme.highContrast
        anchors.fill: parent
        radius: surface.radius
        color: "transparent"
        border.width: 1
        border.color: theme.strokeStrong
    }
}

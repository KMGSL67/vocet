// A Segoe Fluent Icons glyph in a square box: 16 px beside 14 px text, 12 px for
// chevrons, clear buttons and inline status, 20 px in dialogs and the toast, 32 px in empty
// states. Decorative: icon-only controls carry the accessible name, not the icon.
//   C.Icon { name: "search" }                  names: see Glyphs.qml
//   C.Icon { glyph: ""; size: 12 }       or a raw code point
import QtQuick
import "." as C

Item {
    id: icon
    property string name: ""
    property string glyph: ""
    property int size: 16
    property color color: theme.textSecondary
    property real nudgeX: 0                    // optical centring of asymmetric glyphs
    property real nudgeY: 0
    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    Text {
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: icon.nudgeX
        anchors.verticalCenterOffset: icon.nudgeY
        text: icon.glyph !== "" ? icon.glyph : (C.Glyphs.map[icon.name] || "")
        font.family: "Segoe Fluent Icons"
        font.pixelSize: icon.size
        color: icon.color
        Accessible.ignored: true
    }
}

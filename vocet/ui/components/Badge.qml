// An outline capsule for a short code, like the language badge "DE" on a history row:
// 16 px high, hairline strokeField, caption2 textSecondary with +0.4 px tracking in
// all caps. It stays an outline: a filled badge fails contrast on a hovered row.
//   C.Badge { text: "DE"; accessibleName: "German" }
import QtQuick
import "." as C

Rectangle {
    id: badge
    property string text: ""
    property string accessibleName: text
    implicitWidth: label.implicitWidth + 12
    implicitHeight: Math.max(16, label.implicitHeight + 2)
    radius: height / 2
    color: "transparent"
    border.width: 1 / Screen.devicePixelRatio
    border.color: theme.strokeField
    Accessible.role: Accessible.StaticText
    Accessible.name: accessibleName

    C.Txt {
        id: label
        anchors.centerIn: parent
        text: badge.text.toUpperCase()
        textStyle: "caption2"
        tone: "secondary"
        font.letterSpacing: 0.4
        lineHeightMode: Text.ProportionalHeight
        lineHeight: 1
        Accessible.ignored: true
    }
}

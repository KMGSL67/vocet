// One command in a C.Menu: 32 px, radius 4, body text; hover or keyboard highlight fillHover.
// destructive: the label in dangerText (Delete). checkable items get a checkmark column.
import QtQuick
import QtQuick.Templates as T
import "." as C

T.MenuItem {
    id: item
    property bool destructive: false
    implicitWidth: leftPadding + implicitContentWidth + rightPadding
    implicitHeight: Math.max(32, theme.bodyLine + 12)
    leftPadding: checkable ? 28 : 12
    rightPadding: 12
    hoverEnabled: true
    Accessible.name: text

    contentItem: C.Txt {
        text: item.text
        textStyle: "body"
        tone: !item.enabled ? "disabled" : item.destructive ? "danger" : "primary"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        Accessible.ignored: true
    }
    indicator: C.Icon {
        x: 6
        y: Math.round((item.height - height) / 2)
        visible: item.checked
        name: "checkmark"
        size: 12
        color: theme.accentText
    }
    arrow: null
    background: Rectangle {
        radius: theme.radiusMenuItem
        color: item.highlighted ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
    }
}

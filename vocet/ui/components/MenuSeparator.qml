// A hairline between groups of commands in a C.Menu.
import QtQuick
import QtQuick.Templates as T

T.MenuSeparator {
    topPadding: 4
    bottomPadding: 4
    leftPadding: 8
    rightPadding: 8
    implicitWidth: 40
    implicitHeight: topPadding + bottomPadding + 1
    contentItem: Rectangle {
        implicitHeight: 1 / Screen.devicePixelRatio
        color: theme.separator
    }
}

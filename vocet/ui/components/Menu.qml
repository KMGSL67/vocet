// A context menu: level-1 surface, radius 8, 4 px padding, 32 px items.
// Open it with popup() on right-click, Shift+F10 or the Menu key. Every command in it also
// exists as a button and a shortcut.
//   C.Menu {
//       id: rowMenu
//       C.MenuItem { text: "Copy"; onTriggered: … }
//       C.MenuSeparator {}
//       C.MenuItem { text: "Delete"; destructive: true; onTriggered: … }
//   }
import QtQuick
import QtQuick.Templates as T
import "." as C

T.Menu {
    id: menu
    padding: 4
    margins: 8
    overlap: 0
    implicitWidth: Math.max(implicitBackgroundWidth, contentWidth + leftPadding + rightPadding)
    implicitHeight: contentHeight + topPadding + bottomPadding
    delegate: C.MenuItem {}

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: backend.reducedMotion ? 0 : 120; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: backend.reducedMotion ? 0 : 80; easing.type: Easing.InCubic }
    }
    contentItem: ListView {
        implicitWidth: {
            let w = 0
            for (let i = 0; i < count; i++) {
                const it = menu.itemAt(i)
                if (it) w = Math.max(w, it.implicitWidth)
            }
            return w
        }
        implicitHeight: contentHeight
        model: menu.contentModel
        interactive: contentHeight > height
        clip: true
        currentIndex: menu.currentIndex
        boundsBehavior: Flickable.StopAtBounds
        T.ScrollBar.vertical: C.ScrollBar {}
    }
    background: C.Surface {
        implicitWidth: 160
        level: 1
        radius: theme.radiusMenu
    }
}

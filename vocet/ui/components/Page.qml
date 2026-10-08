// A page (design v4): a scroll container whose content column fills the window (max 2400 px),
// 24 px from the sidebar's slot (16 in the rail layout under 760 px) and 34 px to the window's
// edge. 24 px top, 48 px bottom.
// No rubber band (StopAtBounds); PgUp, PgDn, Home and End scroll it; overlay scroll bar.
// The keyboard focus is scrolled into view (ensureVisible).
//
//   C.Page {
//       title: "Dictionary"
//       description: "Names, jargon and product words Vocet should spell right."
//       headerAction: C.Button { text: "New snippet…"; kind: "primary" }   // at most one
//       C.Group { … }                     // content: 20 px under the header, 24 px between items
//       C.Group { … }
//   }
//
// pinnedHeader: the header stays put and content scrolls under it; a hairline fades in
//   (150 ms) once content passes beneath. That's the whole scroll-edge effect.
// list: give a ListView instead of column content (Home's history). The page pins the
//   header, lays the list out below it, adds the scroll bar and the 8/48 px end margins.
//   Place delegates with page.columnX / page.columnWidth.
// active: set by Main while the page is the current one.
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

FocusScope {
    id: page
    property bool active: false
    property string title: ""
    property string description: ""
    property bool pinnedHeader: list !== null
    property alias headerAction: header.action
    property alias headerAccessory: header.accessory
    property Flickable list: null
    default property alias content: body.data

    readonly property bool rail: Window.width > 0 && Window.width < 760
    readonly property real sidePadding: rail ? theme.space5 : theme.space7      // from the sidebar pane's margin
    readonly property real endPadding: rail ? theme.space6 : 34                  // to the window's edge
    // The content starts beside the sidebar and fills the window (like Mail or Linear). A fixed
    // or centred column left a big empty band on a maximised window, and so
    // did the old 1680 px cap on a 2560 px screen. Wide windows are handled inside the column
    // instead: Settings goes to two columns, text keeps a readable measure (HomeRow), controls
    // keep their natural width (the quick card's segmented control).
    readonly property real columnMax: 2400
    readonly property real columnWidth: Math.max(0, Math.min(columnMax, width - sidePadding - endPadding))
    readonly property real columnX: sidePadding
    readonly property Flickable flickable: list !== null ? list : flick
    readonly property bool scrolled: flickable.contentY > flickable.originY - flickable.topMargin + 0.5
    readonly property real hairline: 1 / Screen.devicePixelRatio

    function scrollToTop() { flickable.contentY = flickable.originY - flickable.topMargin }
    readonly property real scrollTop: flickable.originY - flickable.topMargin
    readonly property real scrollBottom: Math.max(scrollTop, flickable.originY + flickable.contentHeight + flickable.bottomMargin - flickable.height)
    readonly property bool atEnd: flickable.contentY >= scrollBottom - 0.5
    function scrollOn() { flickable.contentY = Math.min(scrollBottom, flickable.contentY + flickable.height * 0.8) }  // render_window.py --scroll

    // The entrance (design v4 motion): the content items fade in and rise, 35 ms apart (the first
    // six; the rest together). Main plays it when the page opens and after the opening mark.
    // Pages with a list override revealContent() (Home).
    property var reveals: []
    property var revealTargets: null   // the items to reveal, in order (default: the content's children)
    Component { id: revealComponent; C.Reveal {} }
    function revealContent() {
        if (backend.reducedMotion) return
        let n = 0
        const items = revealTargets || body.children
        for (let i = 0; i < items.length; i++) {
            const child = items[i]
            if (!child.visible) continue
            let r = null
            for (let k = 0; k < reveals.length; k++)
                if (reveals[k].target === child) r = reveals[k]
            if (!r) {
                r = revealComponent.createObject(page, { target: child })
                reveals.push(r)
            }
            r.play(Math.min(n, 5) * theme.motionStagger)
            n++
        }
    }

    onListChanged: {
        if (!list) return
        list.parent = listSlot
        list.anchors.fill = listSlot
        list.boundsBehavior = Flickable.StopAtBounds
        list.clip = true
        list.topMargin = theme.space3
        list.bottomMargin = theme.space10
        if (!list.T.ScrollBar.vertical)
            list.T.ScrollBar.vertical = scrollBarComponent.createObject(list)
    }
    Component { id: scrollBarComponent; C.ScrollBar {} }

    // The keyboard focus stays in view: when Tab or a shortcut moves it to a
    // control above or below what's shown, the page scrolls just enough to show the control and
    // 24 px around it (200 ms OutCubic; at once under reduced motion). Not after a mouse press:
    // moving the control from under the pointer would cancel the click.
    function ensureVisible(item) {
        const f = page.flickable
        if (!item || !f || !f.visible || item.focusReason === Qt.MouseFocusReason) return
        let p = item
        while (p && p !== f.contentItem) p = p.parent
        if (!p) return                                  // not on this page's scrolling content
        const r = item.mapToItem(f.contentItem, 0, 0, item.width, item.height)
        const margin = theme.space7
        const top = f.originY - f.topMargin
        const bottom = Math.max(top, f.originY + f.contentHeight + f.bottomMargin - f.height)
        let y = f.contentY
        if (r.y - margin < y || r.height + 2 * margin > f.height) y = r.y - margin
        else if (r.y + r.height + margin > y + f.height) y = r.y + r.height + margin - f.height
        y = Math.max(top, Math.min(bottom, y))
        if (Math.abs(y - f.contentY) < 0.5) return
        focusScroll.stop()
        if (backend.reducedMotion) {
            f.contentY = y
        } else {
            focusScroll.target = f
            focusScroll.from = f.contentY
            focusScroll.to = y
            focusScroll.start()
        }
    }
    NumberAnimation { id: focusScroll; property: "contentY"; duration: theme.motionMedium; easing.type: Easing.OutCubic }
    Connections {
        target: page.Window.window
        enabled: page.active
        function onActiveFocusItemChanged() { page.ensureVisible(page.Window.activeFocusItem) }
    }

    Keys.onPressed: (event) => {
        const f = page.flickable
        const top = f.originY - f.topMargin
        const bottom = Math.max(top, f.originY + f.contentHeight + f.bottomMargin - f.height)
        let y = f.contentY
        if (event.key === Qt.Key_PageDown) y += f.height * 0.875
        else if (event.key === Qt.Key_PageUp) y -= f.height * 0.875
        else if (event.key === Qt.Key_Home && event.modifiers === Qt.NoModifier) y = top
        else if (event.key === Qt.Key_End && event.modifiers === Qt.NoModifier) y = bottom
        else return
        focusScroll.stop()
        f.contentY = Math.max(top, Math.min(bottom, y))
        event.accepted = true
    }

    // The pinned header area: opaque, above the scrolling content.
    Item {
        id: pinnedArea
        visible: page.pinnedHeader
        z: 2
        width: page.width
        height: page.pinnedHeader ? theme.space7 + header.implicitHeight + theme.space4 : 0
        Rectangle { anchors.fill: parent; color: theme.bgWindow }
        Rectangle {  // the scroll-edge hairline
            width: parent.width
            height: page.hairline
            y: parent.height - height
            color: theme.separator
            opacity: page.scrolled ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: theme.motionBase; easing.type: Easing.OutCubic } }
        }
    }

    C.PageHeader {
        id: header
        z: 3
        parent: page.pinnedHeader ? pinnedArea : headerHolder
        x: page.pinnedHeader ? page.columnX : 0
        y: page.pinnedHeader ? theme.space7 : 0
        width: page.columnWidth
        title: page.title
        description: page.description
    }

    Flickable {
        id: flick
        visible: page.list === null
        anchors.fill: parent
        anchors.topMargin: pinnedArea.height
        contentWidth: width
        contentHeight: body.y + body.implicitHeight + theme.space10
        boundsBehavior: Flickable.StopAtBounds
        acceptedButtons: Qt.NoButton          // wheel, touch and the scroll bar; no drag-to-scroll with a mouse
        clip: true
        T.ScrollBar.vertical: C.ScrollBar {}

        Item {
            id: headerHolder
            visible: !page.pinnedHeader
            x: page.columnX
            y: theme.space7
            width: page.columnWidth
            height: page.pinnedHeader ? 0 : header.implicitHeight
        }
        ColumnLayout {
            id: body
            x: page.columnX
            y: page.pinnedHeader ? theme.space3 : headerHolder.y + headerHolder.height + theme.space6
            width: page.columnWidth
            spacing: theme.space7
        }
    }

    Item {
        id: listHost
        visible: page.list !== null
        anchors.fill: parent
        anchors.topMargin: pinnedArea.height
        Item { id: listSlot; anchors.fill: parent }
    }
}

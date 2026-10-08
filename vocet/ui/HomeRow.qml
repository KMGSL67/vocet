// One dictation on Home (design v4): the ListView delegate of HistoryPage.qml.
//
//  (✉) I think this project is actually pretty cool, and I want      5 min ago   ← the time; on hover or
//      to use it every day.                                                          keyboard selection it
//      Word  DE                                                                      gives way to [⧉] [🗑]
//
// The app is a monochrome glyph in a neutral 32 px circle (C.AppIcon), not its colourful icon.
// When: "Just now" under a minute, "5 min ago" under an hour, then the time ("17:02"); the day
// header above already names the day, so older rows don't repeat it. Hovering the time shows the
// full date and time. HistoryPage ticks `now` once a minute while Home is on screen.
// Text first: body textPrimary, at most 3 lines, then an ellipsis. Click or Enter expands the
// row to the full text (200 ms InOutCubic) and collapses it again. The text stops short of the
// time and the actions, so they never cover words, and wraps at about 120 characters (840 px at
// 100 % text) on wide windows. One glass card per day: the row paints its
// own slice of it (C.Row boxed), rounded on the first and last rows of a day; the last row of a
// day carries the 24 px gap to the next day's header below its box.
// Keyboard (↑/↓ or J/K, Enter, Ctrl+C, Delete, Menu) lives in HistoryPage's ListView: rows never
// take focus themselves. The keyboard selection is fillSelected plus a 2 px focus ring inside the
// box; the mouse only ever gets the quieter fillHover, so the two never look alike.
import QtQuick
import QtQuick.Layouts
import "components" as C

C.Row {
    id: row
    required property int index
    required property var model           // roles: entryId text time createdAt fullTime day app appPath language words outcome
    readonly property int entryId: model.entryId
    readonly property string time: model.time
    readonly property real createdAt: model.createdAt || 0
    readonly property string fullTime: model.fullTime || ""
    property real now: 0                  // seconds since the epoch, ticked by HistoryPage
    readonly property string when: {
        const ago = now - createdAt
        if (now <= 0 || createdAt <= 0 || ago >= 3600) return time
        if (ago < 60) return "Just now"
        return Math.floor(ago / 60) + " min ago"
    }
    readonly property string app: model.app || ""
    readonly property string appPath: model.appPath || ""
    readonly property string language: model.language || ""
    readonly property string outcome: model.outcome || ""
    text: model.text || ""

    property real columnX: 0              // the page's content column, inside the full-width list
    property real columnWidth: width - 2 * columnX
    property bool keyboardSelected: false // current item while the list has keyboard focus
    property bool open: false             // expanded (or expanding)
    readonly property bool expanded: open || heightAnim.running
    property real textHeight: body.implicitHeight   // animated on expand / collapse
    readonly property bool expandable: body.truncated || open || heightAnim.running
    readonly property bool actionsShown: isHovered || keyboardSelected || copyButton.confirmed
                                         || copyButton.hovered || deleteButton.hovered
    readonly property bool isLastOfAll: ListView.view && index === ListView.view.count - 1
    readonly property real gapBelow: last && !isLastOfAll ? theme.space7 : 0
    readonly property string languageName: ({ "de": "German", "fr": "French", "es": "Spanish", "zh": "Chinese", "hi": "Hindi",
                                              "it": "Italian", "nl": "Dutch", "pt": "Portuguese" })[language] || language.toUpperCase()

    signal activated()                    // clicked: HistoryPage selects the row
    signal copyRequested()
    signal deleteRequested()
    signal menuRequested(real x, real y)

    // Expand or collapse the text. While the box animates, the full text stays laid out (and is
    // clipped), so collapsing elides only once the box has shrunk: nothing jumps.
    function toggle() {
        if (!expandable) return
        const from = textHeight
        heightAnim.stop()
        open = !open
        const to = open ? body.implicitHeight : Math.min(body.implicitHeight, 3 * theme.bodyLine)
        if (backend.reducedMotion || Math.abs(to - from) < 0.5) {
            textHeight = Qt.binding(() => body.implicitHeight)
            return
        }
        heightAnim.from = from
        heightAnim.to = to
        textHeight = from
        heightAnim.start()
    }
    function copy() {
        backend.copyText(entryId)
        copyButton.confirm()
    }

    width: ListView.view ? ListView.view.width : 0
    boxed: true
    interactive: true
    focusPolicy: Qt.NoFocus
    selected: keyboardSelected
    first: ListView.previousSection !== ListView.section
    last: ListView.nextSection !== ListView.section
    leftInset: columnX
    rightInset: Math.max(0, width - columnX - columnWidth)
    bottomInset: gapBelow
    readonly property real iconSlot: 62           // the app circle (16 + 32) and a 14 px gap
    readonly property real trailing: Math.max(whenLabel.implicitWidth, 56) + theme.space5  // time or actions
    leftPadding: leftInset + iconSlot
    rightPadding: rightInset + theme.space5
    separatorInset: iconSlot
    bottomPadding: theme.space4 + gapBelow
    containmentMask: background          // hover and clicks only inside the box, not the margins or the gap
    Accessible.name: when + ", " + (app || "Unknown app") + ": " + text
    Accessible.description: expandable ? (open ? "Expanded" : "Collapsed") : ""

    onClicked: { activated(); toggle() }

    NumberAnimation {
        id: heightAnim
        target: row
        property: "textHeight"
        duration: theme.motionMedium
        easing.type: Easing.InOutCubic
        onFinished: row.textHeight = Qt.binding(() => body.implicitHeight)
    }

    TapHandler {  // right-click: the context menu (Shift+F10 and the Menu key are in HistoryPage)
        acceptedButtons: Qt.RightButton
        onTapped: (point) => { row.activated(); row.menuRequested(point.position.x, point.position.y) }
    }

    Item {
        id: textBox
        Layout.fillWidth: true
        Layout.rightMargin: row.trailing         // the text ends before the time and the actions
        // A readable measure (about 120 characters) on a maximised window: past it, lines get
        // hard to follow back to their start. The time stays at the row's trailing edge.
        Layout.maximumWidth: Math.round(840 * theme.textScale)
        implicitHeight: row.textHeight
        clip: heightAnim.running
        C.Txt {
            id: body
            width: parent.width
            text: row.text
            wrapMode: Text.Wrap
            maximumLineCount: row.expanded ? 100000 : 3
            elide: Text.ElideRight
            Accessible.ignored: true
        }
    }

    C.AppIcon {  // the app, as a glyph in a neutral circle, level with the first lines
        parent: row
        x: row.leftInset + theme.space5
        y: row.topPadding + 5
        app: row.app
        path: row.appPath
    }

    C.Txt {  // when, at the trailing edge of the first line; the full date and time on hover
        id: whenLabel
        parent: row
        anchors.right: parent.right
        anchors.rightMargin: row.rightInset + theme.space5
        y: row.topPadding + Math.round((theme.bodyLine - height) / 2)
        text: row.when
        textStyle: "footnote"
        tone: "secondary"
        tabular: true
        opacity: row.actionsShown ? 0 : 1
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: theme.motionFast; easing.type: Easing.OutCubic } }
        Accessible.ignored: true
        HoverHandler { id: whenHover }
        C.Tooltip { text: row.fullTime; visible: whenHover.hovered && row.fullTime !== "" }
    }

    RowLayout {  // metadata: app, language, outcome
        Layout.fillWidth: true
        Layout.topMargin: 4
        Layout.rightMargin: row.trailing
        spacing: 6
        C.Txt {
            text: row.app || "Unknown app"
            textStyle: "footnote"
            tone: "secondary"
            Layout.alignment: Qt.AlignVCenter
            Accessible.ignored: true
        }
        C.Badge {
            visible: row.language !== "" && row.language !== "en"
            text: row.language
            accessibleName: row.languageName
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 2
            HoverHandler { id: badgeHover }
            C.Tooltip { text: row.languageName; visible: badgeHover.hovered }
        }
        C.Icon {
            visible: row.outcome === "copied"
            name: "info"
            size: 12
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 4
        }
        C.Txt {
            visible: row.outcome === "copied"
            text: "Not pasted, saved here"
            textStyle: "footnote"
            tone: "secondary"
            Layout.alignment: Qt.AlignVCenter
        }
        Item { Layout.fillWidth: true }
    }

    Row {  // the actions, aligned to the first text line; always in the accessibility tree
        parent: row
        anchors.right: parent.right
        anchors.rightMargin: row.rightInset + theme.space3
        y: row.topPadding + Math.round((theme.bodyLine - 28) / 2)
        spacing: 0
        opacity: row.actionsShown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: theme.motionFast; easing.type: Easing.OutCubic } }
        C.IconButton {
            id: copyButton
            iconName: "copy"
            label: "Copy"
            focusPolicy: Qt.NoFocus
            onClicked: row.copyRequested()
        }
        C.IconButton {
            id: deleteButton
            iconName: "delete"
            label: "Delete"
            focusPolicy: Qt.NoFocus
            onClicked: row.deleteRequested()
        }
    }

    Rectangle {  // the keyboard focus ring, round the selection wash, inside the card
        parent: row.background
        visible: row.keyboardSelected
        anchors.fill: parent             // the background already spans the box (the insets)
        anchors.leftMargin: row.washInset - 2
        anchors.rightMargin: row.washInset - 2
        anchors.topMargin: row.first ? row.washInset - 2 : 1
        anchors.bottomMargin: row.last ? row.washInset - 2 : 1
        radius: theme.radiusGroup - row.washInset + 2
        color: "transparent"
        border.width: 2
        border.color: theme.focus
        antialiasing: true
    }

    // A new dictation arriving while the window is open grows in (height 200 ms, opacity 150 ms
    // after 50 ms); a deleted one fades (120 ms) and then closes its gap (180 ms). Resets
    // (search, undo) and the first fill of the list don't animate.
    property real reveal: 1
    height: Math.round(implicitHeight * reveal)
    clip: reveal < 1
    transform: Translate { id: slide }
    ListView.onAdd: {
        if (backend.reducedMotion) return
        reveal = 0
        opacity = 0
        slide.y = -theme.risePage
        addAnim.start()
    }
    ListView.onRemove: {
        if (backend.reducedMotion) return
        ListView.delayRemove = true
        removeAnim.start()
    }
    ParallelAnimation {
        id: addAnim
        NumberAnimation { target: row; property: "reveal"; to: 1; duration: theme.motionMedium; easing.type: Easing.OutCubic }
        NumberAnimation { target: slide; property: "y"; to: 0; duration: theme.motionReveal; easing.type: Easing.OutCubic }
        SequentialAnimation {
            PauseAnimation { duration: 50 }
            NumberAnimation { target: row; property: "opacity"; to: 1; duration: theme.motionBase; easing.type: Easing.OutCubic }
        }
    }
    SequentialAnimation {
        id: removeAnim
        NumberAnimation { target: row; property: "opacity"; to: 0; duration: 120; easing.type: Easing.InCubic }
        NumberAnimation { target: row; property: "reveal"; to: 0; duration: 180; easing.type: Easing.OutCubic }
        ScriptAction { script: row.ListView.delayRemove = false }
    }
}

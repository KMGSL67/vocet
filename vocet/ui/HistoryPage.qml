// Home (design v4 "Calm glass"): see that Vocet is ready, how much you've said, and find and
// reuse what you said.
//
//   Home                                               ( ⌕ Search history )  ( 🎙 Try it )  ← pinned header
//   Good afternoon. Hold Ctrl + Win and speak where you're typing.
//   ╭ Words this week ─────────────── ▁ ▃ ▂ ▅ ▃ ▁ █ ╮  ╭ Remove filler words           (●) ╮
//   │ 1,240   (+18 %) vs last week                  │  │──────────────────────────────────│
//   ╰ About 38 minutes saved, at 40 words a minute ─╯  ╰ Speech model  [Fast|Bal|Most acc]╯
//   Today                                                                          ← sticks while its day scrolls
//   ╭──────────────────────────────────────────────────────────────────────────╮
//   │ (✉) I think this project is actually pretty cool, and I want…   2 min ago │
//   │     Word                                                                  │
//   ╰──────────────────────────────────────────────────────────────────────────╯
//
// The week card: words in the last 7 days, a chip against the 7 days before (hidden when there's
// nothing to compare), time saved against typing, and one bar per day with today's in the
// accent; the bars widen with the card (14-24 px). The count ticks to a new value (600 ms). The
// quick card repeats Settings' two most-used choices as two rows, each control at its natural
// width on its label's line (stacked only when the card is too narrow). Both cards take their
// height from their text, so Windows' Text size grows them; side by side they share a height.
// Rows: HomeRow.qml. Keyboard: Tab lands on the list; ↑/↓ or J/K
// select, Enter expands, Ctrl+C copies, Delete deletes (Undo in the toast, or Ctrl+Z in Main),
// Shift+F10 or the Menu key opens the context menu. Ctrl+F (Main) and "/" call focusSearch(); ↓ in
// the search field moves into the results, Esc twice returns to the list. Times read "Just now" /
// "5 min ago" for the last hour: `now` ticks every 30 s, only while Home is on screen (not hidden
// to the tray, not minimised).
// Empty: "No dictations yet" with Try it here, which reveals a practice box ("Try it" in the
// header does the same). Searching with no match: "No results for “…”" with Clear search.
// When the page opens, the cards and the first rows fade in and rise, 35 ms apart.
import QtQuick
import QtQuick.Layouts
import "components" as C

C.Page {
    id: page
    title: "Home"
    description: greeting + ". Hold " + backend.hotkeyName + " and speak where you’re typing."
    pinnedHeader: true
    headerAction: [
        C.SearchField {
            id: search
            implicitWidth: Math.round((page.rail ? 180 : 220) * Math.min(1.3, theme.textScale))
            onSearched: (query) => { page.query = query; backend.search(query) }
            onDownPressed: page.focusList(0)
            onEscapedEmpty: page.focusList(-1)
        },
        C.Button {
            text: "Try it"
            kind: "primary"
            iconName: "microphone"
            onClicked: page.openPractice()
        }
    ]
    list: history

    property string query: ""
    property bool practiceOpen: false
    readonly property bool noHistory: history.count === 0 && query === ""
    readonly property bool noResults: history.count === 0 && query !== ""
    readonly property string greeting: {
        const h = new Date(page.now * 1000).getHours()
        return h < 5 ? "Hello" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    function focusSearch() { search.focusAndSelect() }
    function focusList(index) {
        if (history.count === 0) return
        if (index >= 0) history.currentIndex = index
        else if (history.currentIndex < 0) history.currentIndex = 0
        history.keyboard = true
        history.forceActiveFocus(Qt.TabFocusReason)
        history.positionViewAtIndex(history.currentIndex, ListView.Contain)
    }
    function openPractice() {
        if (page.query !== "") search.clear()
        page.practiceOpen = true
        page.keepTop = true
        page.scrollToTop()
    }
    property string practiceText: ""       // kept while you leave the page and come back
    function clearSearch() {
        search.clear()
        search.focusAndSelect()
    }

    // The entrance: the two cards, then the first rows on screen, 35 ms apart (at most 6 staggered).
    property var rowReveals: []
    Component { id: rowRevealComponent; C.Reveal {} }
    function revealFor(item) {
        // A row's delegate goes away on every search keystroke or when it scrolls out of the
        // cache; its Reveal goes with it, so their number never grows.
        const alive = []
        for (let i = 0; i < rowReveals.length; i++) {
            if (rowReveals[i].target === null) rowReveals[i].destroy()
            else alive.push(rowReveals[i])
        }
        rowReveals = alive
        for (let i = 0; i < rowReveals.length; i++)
            if (rowReveals[i].target === item) return rowReveals[i]
        const r = rowRevealComponent.createObject(page, { target: item })
        rowReveals.push(r)
        return r
    }
    function revealContent() {
        if (backend.reducedMotion) return
        let n = 0
        if (dashboardItem && dashboardItem.visible) {
            statsReveal.play(0)
            quickReveal.play(theme.motionStagger)
            n = 2
        }
        const top = history.contentY
        for (let i = 0; i < history.count && n < 8; i++) {
            const it = history.itemAtIndex(i)
            if (!it || it.y + it.height < top || it.y > top + history.height) continue
            revealFor(it).play(Math.min(n, 5) * theme.motionStagger)
            n++
        }
    }
    property bool keepTop: true           // you're at the top of the list (updated when you scroll)
    Connections {
        target: history
        function onMovementEnded() { page.keepTop = history.contentY <= history.originY - history.topMargin + 1 }
    }
    property Item dashboardItem: null     // set by the list's header, which is built later
    property Item statsItem: null
    property Item quickItem: null
    C.Reveal { id: statsReveal; target: page.statsItem }
    C.Reveal { id: quickReveal; target: page.quickItem }

    onActiveChanged: if (!active && practiceText === "") practiceOpen = false

    // "/" focuses search, as on the web. Text fields take "/" as typing before a shortcut sees it.
    Shortcut { sequence: "/"; enabled: page.active; onActivated: page.focusSearch() }

    property real now: Date.now() / 1000   // for the rows' "5 min ago" and the greeting
    Timer {
        interval: 30000
        repeat: true
        triggeredOnStart: true
        // Not while minimised: a minimised window is still `visible`.
        running: page.active && page.Window.window !== null && page.Window.visibility !== Window.Hidden
                 && page.Window.visibility !== Window.Minimized
        onTriggered: page.now = Date.now() / 1000
    }

    // Remove filler words: the sounds it removes in the languages you speak (as in Settings)
    readonly property var fillerExamples: ({ "en": "“um”", "de": "“äh”", "fr": "“euh”", "es": "“eh”",
                                             "zh": "“嗯”", "hi": "“अं”" })
    readonly property string fillerDescription: {
        const e = (backend.settings.languages || ["en"]).map(k => fillerExamples[k] || "").filter(x => x !== "")
        const listed = e.length <= 1 ? (e[0] || "“um”") : e.slice(0, -1).join(", ") + " and " + e[e.length - 1]
        return "Removes sounds like " + listed + "."
    }

    // ------------------------------------------------------------------ the week's numbers
    readonly property var stats: backend.stats || ({})
    readonly property int weekWords: stats.words || 0
    readonly property int prevWords: stats.prev_words || 0
    readonly property var daily: stats.daily || [0, 0, 0, 0, 0, 0, 0]
    readonly property var dayLabels: stats.daily_labels || ["M", "T", "W", "T", "F", "S", "S"]
    readonly property int maxDay: Math.max.apply(null, daily.concat([1]))
    readonly property int changePct: prevWords > 0 ? Math.round((weekWords - prevWords) * 100 / prevWords) : 0
    property real shownWords: 0            // ticks to weekWords
    property bool numbersReady: false
    onWeekWordsChanged: {
        if (!numbersReady || backend.reducedMotion) { shownWords = weekWords; return }
        tick.stop()
        tick.from = shownWords
        tick.to = weekWords
        tick.start()
    }
    Component.onCompleted: { shownWords = weekWords; numbersReady = true }
    NumberAnimation { id: tick; target: page; property: "shownWords"; duration: theme.motionNumber; easing.type: Easing.OutCubic }

    ListView {
        id: history
        property bool keyboard: false      // the selection came from the keyboard: show it
        model: backend.historyModel
        currentIndex: -1
        activeFocusOnTab: count > 0
        keyNavigationEnabled: true
        acceptedButtons: Qt.NoButton       // wheel, touch and the scroll bar; no drag-to-scroll with a mouse (Windows)
        highlightFollowsCurrentItem: false
        highlightMoveDuration: 0
        reuseItems: false
        cacheBuffer: 480
        Accessible.role: Accessible.List
        Accessible.name: "Your dictations"

        onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
        // At the top, stay at the top while the header and rows settle (their heights follow the
        // text, so the first layouts and a resize move the list's origin).
        onOriginYChanged: if (page.keepTop && !moving) Qt.callLater(page.scrollToTop)
        onHeightChanged: if (page.keepTop && !moving) Qt.callLater(page.scrollToTop)
        onCountChanged: if (currentIndex >= count) currentIndex = count - 1

        Keys.onPressed: (event) => {
            const row = currentItem
            if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                keyboard = true               // the ListView itself moves the selection
                return
            }
            if ((event.key === Qt.Key_J || event.key === Qt.Key_K) && event.modifiers === Qt.NoModifier) {
                if (event.key === Qt.Key_J) incrementCurrentIndex()
                else decrementCurrentIndex()
                keyboard = true
                positionViewAtIndex(currentIndex, ListView.Contain)
                event.accepted = true
                return
            }
            if (!row) return
            if (event.matches(StandardKey.Copy)) {
                row.copy()
            } else if (event.key === Qt.Key_Delete) {
                backend.deleteEntry(row.entryId)
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                row.toggle()
            } else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                page.openMenu(row, 16 + page.columnX, row.topPadding + theme.bodyLine)
            } else {
                return
            }
            keyboard = true
            positionViewAtIndex(currentIndex, ListView.Contain)
            event.accepted = true
        }

        header: Item {
            width: history.width
            height: headerColumn.implicitHeight + (history.count > 0 ? theme.space4 : 0)
            // The cards' heights follow their text: when they grow (the first layout, a resize)
            // while you're at the top, stay at the top instead of scrolling part of them away.
            onHeightChanged: if (page.keepTop) Qt.callLater(page.scrollToTop)
            ColumnLayout {
                id: headerColumn
                x: page.columnX
                width: page.columnWidth
                spacing: 0

                GridLayout {  // the week card and the quick card (stacked when the column is narrow)
                    id: dashboard
                    visible: page.query === ""
                    // Side by side, the week card takes 58 % and the quick card the rest, but the quick
                    // card never gets less than it needs to show the Speech model control whole (its
                    // segments never shrink below their labels). The cards sit side by side only
                    // while the week card then keeps at least 400 px (its words beside the chart);
                    // narrower, they stack, each the column's full width. All from measured widths,
                    // so a larger Windows text size stacks them sooner.
                    readonly property real share: page.columnWidth - columnSpacing
                    readonly property real quickNeed: Math.ceil(speech.naturalWidth) + 2 * quickBody.x
                    readonly property real quickWide: Math.max(share - Math.round(share * 0.58), quickNeed)
                    readonly property bool wide: share - quickWide >= Math.round(400 * Math.max(1, theme.textScale))
                    // Side by side, both cards are as tall as the taller one's content (at least
                    // 176): the heights come from the text, so a larger Windows text size grows them.
                    readonly property real rowHeight: Math.max(176, statsCard.need, quickCard.need)
                    Layout.fillWidth: true
                    Layout.topMargin: theme.space2
                    Layout.bottomMargin: page.noHistory ? 0 : theme.space3
                    columns: wide ? 2 : 1
                    columnSpacing: theme.space5
                    rowSpacing: theme.space5
                    Component.onCompleted: { page.dashboardItem = dashboard; page.statsItem = statsCard; page.quickItem = quickCard }

                    Item {  // Words this week
                        id: statsCard
                        objectName: "statsCard"
                        readonly property real need: statsText.implicitHeight + 40
                        Layout.preferredWidth: dashboard.wide ? dashboard.share - dashboard.quickWide : page.columnWidth
                        Layout.preferredHeight: dashboard.wide ? dashboard.rowHeight : Math.max(176, need)
                        Accessible.role: Accessible.StaticText
                        Accessible.name: Number(page.weekWords).toLocaleString(Qt.locale(), "f", 0) + " words this week"
                            + (page.prevWords > 0 ? ", " + Math.abs(page.changePct) + " % " + (page.changePct >= 0 ? "more" : "fewer") + " than last week" : "")
                        C.Glass { anchors.fill: parent; kind: "card" }
                        ColumnLayout {  // the words: a label, the count, the change, the time saved
                            id: statsText
                            x: 24
                            y: 20
                            width: (chart.visible ? chart.x - theme.space7 : statsCard.width - theme.space7) - x
                            spacing: 0
                            C.Txt {
                                text: "Words this week"
                                textStyle: "callout"
                                semibold: true
                                tone: "secondary"
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                Accessible.ignored: true
                            }
                            C.Txt {
                                text: Number(Math.round(page.shownWords)).toLocaleString(Qt.locale(), "f", 0)
                                textStyle: "display"
                                tabular: true
                                Layout.leftMargin: -2          // the display face's side bearing
                                Accessible.ignored: true
                            }
                            RowLayout {
                                visible: page.prevWords > 0
                                spacing: theme.space3
                                Layout.topMargin: theme.space1
                                Rectangle {  // the change, in a neutral chip
                                    implicitWidth: chipText.implicitWidth + 16
                                    implicitHeight: Math.max(22, chipText.implicitHeight + 6)
                                    radius: height / 2
                                    color: theme.chipFill
                                    C.Txt {
                                        id: chipText
                                        anchors.centerIn: parent
                                        text: (page.changePct >= 0 ? "+" : "−") + Math.abs(page.changePct) + "\u00A0%"
                                        textStyle: "footnote"
                                        semibold: true
                                        tabular: true
                                        Accessible.ignored: true
                                    }
                                }
                                C.Txt {
                                    text: "vs last week"
                                    textStyle: "callout"
                                    tone: "secondary"
                                    Accessible.ignored: true
                                }
                            }
                            C.Txt {
                                Layout.topMargin: theme.space3
                                Layout.fillWidth: true
                                text: page.weekWords === 0 ? "Your first dictation starts the count."
                                    : (page.stats.saved_min || 0) >= 1 ? "About " + page.stats.saved_min + (page.stats.saved_min === 1 ? " minute" : " minutes") + " saved, at 40 words a minute"
                                    : "Less than a minute saved so far, at 40 words a minute"
                                textStyle: "footnote"
                                tone: "tertiary"
                                wrapMode: Text.Wrap          // wraps beside the chart, never truncates
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                Accessible.ignored: true
                            }
                        }
                        Row {  // one bar per day, today's in the accent; it widens with the card
                            id: chart
                            // the space right of the words (which keep at least 260 px): 164-384 px
                            readonly property real span: Math.max(164, Math.min(384, statsCard.width - 24 - 260 - 26 - theme.space7))
                            readonly property real barW: Math.min(24, Math.max(14, Math.round(span / 7 * 0.45)))
                            anchors.right: parent.right
                            anchors.rightMargin: 26
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 18
                            spacing: Math.floor((span - 7 * barW) / 6)
                            visible: statsCard.width > 360
                            Accessible.ignored: true
                            Repeater {
                                model: 7
                                Column {
                                    required property int index
                                    readonly property bool today: index === 6
                                    readonly property real share: (page.daily[index] || 0) / page.maxDay
                                    // the day's share animates, not the bar's height: a resize (the
                                    // bars widen with the card) never animates, only new numbers do
                                    property real shownShare: share
                                    Behavior on shownShare { enabled: !backend.reducedMotion && page.numbersReady; NumberAnimation { duration: theme.motionNumber; easing.type: Easing.OutCubic } }
                                    spacing: 8
                                    Item {
                                        width: chart.barW
                                        height: 96
                                        Rectangle {
                                            visible: !parent.parent.today
                                            anchors.bottom: parent.bottom
                                            width: chart.barW
                                            height: Math.max(chart.barW, 96 * parent.parent.shownShare)
                                            radius: width / 2
                                            antialiasing: true
                                            gradient: Gradient {
                                                GradientStop { position: 0; color: Qt.alpha(theme.bar, theme.barA * 1.25) }
                                                GradientStop { position: 1; color: Qt.alpha(theme.bar, theme.barA * 0.6) }
                                            }
                                        }
                                        Item {
                                            visible: parent.parent.today
                                            anchors.bottom: parent.bottom
                                            width: chart.barW
                                            height: Math.max(chart.barW, 96 * parent.parent.shownShare)
                                            C.Glass { anchors.fill: parent; kind: "accent"; radius: width / 2 }
                                        }
                                    }
                                    C.Txt {
                                        text: page.dayLabels[index] || ""
                                        textStyle: "caption1"
                                        semibold: parent.today
                                        tone: parent.today ? "primary" : "tertiary"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                    }
                                }
                            }
                        }
                    }

                    Item {  // quick settings: the two choices people change most, as two settings rows
                        id: quickCard
                        objectName: "quickCard"
                        readonly property real need: quickBody.implicitHeight + 36
                        Layout.preferredWidth: dashboard.wide ? dashboard.quickWide : page.columnWidth
                        Layout.preferredHeight: dashboard.wide ? dashboard.rowHeight : need
                        C.Glass { anchors.fill: parent; kind: "card" }
                        ColumnLayout {
                            id: quickBody
                            x: 22
                            width: quickCard.width - 44
                            y: Math.round((quickCard.height - implicitHeight) / 2)
                            spacing: 0
                            RowLayout {
                                spacing: theme.space5
                                Layout.fillWidth: true
                                ColumnLayout {
                                    spacing: theme.space1
                                    Layout.fillWidth: true
                                    C.Txt { text: "Remove filler words"; textStyle: "body"; semibold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                    C.Txt { text: page.fillerDescription; textStyle: "callout"; tone: "secondary"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                }
                                C.Switch {
                                    id: fillers
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.rightMargin: -2   // the 40 px track ends on the card's inner edge
                                    label: "Remove filler words"
                                    checked: backend.settings.remove_fillers === true
                                    onToggled: backend.setSetting("remove_fillers", checked)
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.topMargin: theme.space5
                                Layout.bottomMargin: theme.space5
                                implicitHeight: 1 / Screen.devicePixelRatio
                                color: theme.separator
                            }
                            GridLayout {  // Speech model: label and control on one line, as in Settings;
                                          // stacked (and filling) only when the card is too narrow
                                id: modelRow
                                readonly property bool inline: quickBody.width >= speech.naturalWidth + modelLabel.implicitWidth + theme.space5
                                columns: inline ? 2 : 1
                                columnSpacing: theme.space5
                                rowSpacing: theme.space3
                                Layout.fillWidth: true
                                C.Txt {
                                    id: modelLabel
                                    text: "Speech model"
                                    textStyle: "body"
                                    semibold: true
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                }
                                C.Segmented {
                                    id: speech
                                    objectName: "speechModelControl"
                                    Layout.alignment: modelRow.inline ? Qt.AlignRight | Qt.AlignVCenter : Qt.AlignLeft
                                    Layout.preferredWidth: modelRow.inline ? naturalWidth : quickBody.width
                                    fillWidth: modelRow.inline ? 0 : quickBody.width
                                    label: "Speech model"
                                    model: backend.presets.map(p => ({ key: p.key, label: p.label }))   // the names Settings uses
                                    value: backend.settings.preset
                                    onPicked: (v) => backend.setSetting("preset", v)
                                }
                            }
                        }
                    }
                }

                C.EmptyState {
                    visible: page.noHistory
                    Layout.topMargin: theme.space8
                    iconName: "history"
                    title: "No dictations yet"
                    text: "Click where you want to type, hold " + backend.hotkeyName + ", say something, and let go. Your words appear there."
                    actionText: page.practiceOpen ? "" : "Try it here"
                    onAction: page.practiceOpen = true
                }
                C.EmptyState {
                    visible: page.noResults
                    Layout.topMargin: theme.space5
                    iconName: "search"
                    title: "No results for “" + page.query + "”"
                    text: "Try a different word."
                    actionText: "Clear search"
                    onAction: page.clearSearch()
                }
                HomePractice {
                    visible: page.practiceOpen && !page.noResults
                    text: page.practiceText
                    onTextChanged: page.practiceText = text
                    Layout.topMargin: page.noHistory ? theme.space7 : theme.space4
                    onDismissed: { page.practiceOpen = false; search.focusAndSelect() }
                }
            }
        }

        section.property: "day"
        section.criteria: ViewSection.FullString
        section.labelPositioning: ViewSection.InlineLabels | ViewSection.CurrentLabelAtStart
        section.delegate: C.GroupHeader {
            required property string section
            title: section
            width: ListView.view ? ListView.view.width : page.width
            columnX: page.columnX
            columnWidth: page.columnWidth
            topSpacing: theme.space4     // the day above ends with its own 24 px gap (HomeRow)
            stuck: ListView.view !== null && ListView.view.contentY > ListView.view.originY && y - ListView.view.contentY < 0.5
        }

        delegate: HomeRow {
            columnX: page.columnX
            columnWidth: page.columnWidth
            now: page.now
            keyboardSelected: ListView.isCurrentItem && history.keyboard && history.activeFocus
            onActivated: {
                history.keyboard = false
                history.currentIndex = index
                history.forceActiveFocus(Qt.MouseFocusReason)
            }
            onCopyRequested: copy()
            onDeleteRequested: {
                history.currentIndex = index
                backend.deleteEntry(entryId)
            }
            onMenuRequested: (x, y) => page.openMenu(this, x, y)
        }

        displaced: Transition {
            enabled: !backend.reducedMotion
            NumberAnimation { property: "y"; duration: theme.motionMedium; easing.type: Easing.OutCubic }
        }
    }

    // One context menu for every row: Copy, a separator, then Delete.
    property Item menuRow: null
    function openMenu(row, x, y) {
        menuRow = row
        rowMenu.popup(row, x, y)
    }
    function openMenuAt(index) {  // the menu of row `index` (keyboard and render_window.py)
        const row = history.itemAtIndex(index)
        if (row) openMenu(row, 16 + page.columnX, row.topPadding + theme.bodyLine)
    }
    C.Menu {
        id: rowMenu
        C.MenuItem { text: "Copy"; onTriggered: if (page.menuRow) page.menuRow.copy() }
        C.MenuSeparator {}
        C.MenuItem {
            text: "Delete"
            destructive: true
            onTriggered: if (page.menuRow) backend.deleteEntry(page.menuRow.entryId)
        }
        onClosed: page.menuRow = null
    }
}

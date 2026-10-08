// The sidebar (design v4 "Calm glass"): a floating glass pane, 10 px from the window's edges,
// 228 px wide (56 in the rail). The lockup (glyph 22 × 18 and "vocet" 19 px) at the top, then
// Home, Dictionary, Snippets, Settings (40 px capsules, 4 px apart), and a small status card at
// the foot: Ready and the shortcut, Listening, Loading, Paused (+ Resume) or a problem (opens
// Settings). The selection is one neutral glass lens that glides to the current page
// (260 ms OutCubic; instant under reduced motion); only its icon takes the accent.
// rail (window under 760 px): glyph only, 40 × 40 items with tooltips, and the status becomes
// a 6 px dot on the glyph, with a tooltip.
// Keyboard: Tab lands on the current item, ↑/↓ move, Enter or Space opens.
//   C.Sidebar { current: root.current; rail: root.rail; onNavigate: (page) => root.navigate(page) }
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

Item {
    id: side
    property string current: "home"
    property bool rail: false
    property string status: backend.status
    property bool listening: backend.listening
    property var pages: [
        { key: "home", label: "Home", icon: "home" },
        { key: "dictionary", label: "Dictionary", icon: "dictionary" },
        { key: "snippets", label: "Snippets", icon: "snippets" },
        { key: "settings", label: "Settings", icon: "settings" }
    ]
    readonly property alias logoSlot: logo    // where the opening mark lands (OpeningMark.qml)
    property real glyphOpacity: 1             // the opening mark hides the lockup while it plays
    property real wordOpacity: 1
    signal navigate(string page)
    // The selection glides only when the page changes (not on the first layout or a resize).
    property bool glide: false
    property bool ready: false
    Component.onCompleted: ready = true
    onCurrentIndexChanged: if (ready) { glide = true; glideOff.restart() }
    Timer { id: glideOff; interval: theme.motionGlide + 50; onTriggered: side.glide = false }
    signal resumeRequested()

    readonly property string statusKind: listening ? "listening"
        : status === "Ready" ? "ready"
        : (status.indexOf("Loading") === 0 || status.indexOf("Switching") === 0) ? "loading"
        : status === "Paused" ? "paused" : "problem"
    readonly property bool showStatus: statusKind !== "ready" && statusKind !== "listening"
    readonly property int moveMs: backend.reducedMotion ? 0 : theme.motionMedium
    readonly property int currentIndex: {
        for (let i = 0; i < pages.length; i++)
            if (pages[i].key === current) return i
        return -1
    }

    function focusItem(i) {
        const it = repeater.itemAt(Math.max(0, Math.min(repeater.count - 1, i)))
        if (it) it.forceActiveFocus(Qt.TabFocusReason)
    }

    implicitWidth: rail ? 76 : 248
    Accessible.role: Accessible.PageTabList
    Accessible.name: "Pages"

    C.Glass {  // the pane
        id: pane
        x: 10
        y: 10
        width: side.width - 20
        height: side.height - 20
        kind: "pane"
        radius: side.rail ? 18 : theme.radiusPane
    }

    C.Logo {
        id: logo
        x: side.rail ? pane.x + Math.round((pane.width - width) / 2) : pane.x + 26
        y: pane.y + 28
        width: 22
        height: 18
        opacity: side.glyphOpacity
        Behavior on x { NumberAnimation { duration: side.moveMs; easing.type: Easing.InOutCubic } }

        Rectangle {  // rail: the status as a dot on the glyph
            visible: side.rail && side.showStatus
            width: 6
            height: 6
            radius: 3
            x: parent.width - 2
            y: -3
            color: side.statusKind === "problem" ? theme.warning : theme.textSecondary
            HoverHandler { id: dotHover }
            C.Tooltip { text: side.status; visible: dotHover.hovered }
        }
    }
    Text {
        x: logo.x + logo.width + 10
        anchors.verticalCenter: logo.verticalCenter
        anchors.verticalCenterOffset: -1
        opacity: side.rail ? 0 : side.wordOpacity
        visible: opacity > 0
        text: "vocet"
        font.family: "Segoe UI Variable Display Semibold"
        font.pixelSize: 19
        font.weight: Font.DemiBold
        color: theme.textPrimary
        Accessible.ignored: true
    }

    C.Glass {  // the selection: one lens that glides to the current page
        id: selection
        visible: side.currentIndex >= 0
        x: nav.x
        y: nav.y + Math.max(0, side.currentIndex) * (height + nav.spacing)
        width: nav.width
        height: repeater.count > 0 && repeater.itemAt(0) ? repeater.itemAt(0).height : 40
        kind: "navSel"
        radius: height / 2
        Behavior on y { enabled: side.glide && !backend.reducedMotion; NumberAnimation { duration: theme.motionGlide; easing.type: Easing.OutCubic } }
    }

    Column {
        id: nav
        x: pane.x + (side.rail ? 8 : 12)
        y: pane.y + 78
        width: pane.width - (side.rail ? 16 : 24)
        spacing: 4
        Repeater {
            id: repeater
            model: side.pages
            C.NavItem {
                required property var modelData
                required property int index
                width: nav.width
                rail: side.rail
                ownHighlight: false
                label: modelData.label
                iconName: modelData.icon
                selected: side.current === modelData.key
                onClicked: side.navigate(modelData.key)
                Keys.onUpPressed: side.focusItem(index - 1)
                Keys.onDownPressed: side.focusItem(index + 1)
            }
        }
    }

    // The status card at the foot of the pane. Its height follows its text (Windows' Text size),
    // 66 px at 100 %: a line with the indicator and the title, then the shortcut or the detail.
    T.AbstractButton {
        id: statusCard
        visible: !side.rail && pane.height > nav.y + nav.height + height + 24
        x: pane.x + 12
        width: pane.width - 24
        height: Math.max(66, statusBody.implicitHeight + 22)
        y: pane.y + pane.height - height - 12
        hoverEnabled: side.statusKind === "problem"
        focusPolicy: side.statusKind === "problem" ? Qt.StrongFocus : Qt.NoFocus
        Accessible.role: side.statusKind === "problem" ? Accessible.Link : Accessible.StaticText
        Accessible.name: side.statusKind === "ready" ? "Ready. Hold " + keys.Accessible.name + " and speak where you’re typing."
                       : title.text + ". " + detail.text
        onClicked: if (side.statusKind === "problem") side.navigate("settings")

        background: Item {
            C.Glass { anchors.fill: parent; kind: "card"; radius: 16; shadow: false }
            C.Fill {
                anchors.fill: parent
                radius: 16
                hovered: statusCard.hovered
                pressed: statusCard.down
                tint: statusCard.down ? theme.fillPressed : statusCard.hovered ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
            }
            C.FocusRing { show: statusCard.visualFocus; controlRadius: 16 }
        }
        contentItem: Item {
            ColumnLayout {
                id: statusBody
                x: 14
                y: Math.round((statusCard.height - implicitHeight) / 2)
                width: statusCard.width - 14 - 10
                spacing: theme.space2
                RowLayout {
                    spacing: 8
                    Layout.fillWidth: true
                    Item {  // the leading indicator: dot, spinner or glyph, in a 12 px slot, centred on the title
                        implicitWidth: 12
                        implicitHeight: 12
                        Layout.alignment: Qt.AlignVCenter
                        Rectangle {
                            visible: side.statusKind === "ready" || side.statusKind === "listening"
                            anchors.centerIn: parent
                            width: 8
                            height: 8
                            radius: 4
                            color: side.statusKind === "listening" ? theme.accentText : theme.success
                        }
                        C.Spinner {
                            anchors.centerIn: parent
                            size: 12
                            running: side.statusKind === "loading" && statusCard.visible
                            visible: side.statusKind === "loading"
                        }
                        C.Icon {
                            anchors.centerIn: parent
                            visible: side.statusKind === "paused" || side.statusKind === "problem"
                            name: side.statusKind === "paused" ? "pause" : "warning"
                            size: 12
                            color: side.statusKind === "problem" ? theme.warning : theme.textSecondary
                        }
                    }
                    C.Txt {
                        id: title
                        Layout.fillWidth: true
                        text: side.statusKind === "ready" ? "Ready"
                            : side.statusKind === "listening" ? "Listening…"
                            : side.statusKind === "loading" ? "Getting ready"
                            : side.statusKind === "paused" ? "Paused"
                            : side.status === "Speech model not downloaded" ? "Speech model missing"
                            : side.status === "Model failed to load" ? "Speech model didn’t load"
                            : "Needs attention"
                        textStyle: "callout"
                        semibold: true
                        elide: Text.ElideRight
                        Accessible.ignored: true
                    }
                }
                Row {
                    visible: side.statusKind === "ready"
                    spacing: theme.space2
                    C.Txt {
                        text: "Hold"
                        textStyle: "footnote"
                        tone: "secondary"
                        anchors.verticalCenter: parent.verticalCenter
                        Accessible.ignored: true
                    }
                    C.KeyCombo {
                        id: keys
                        keys: backend.hotkeyKeys
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                C.Txt {
                    id: detail
                    visible: side.statusKind !== "ready" && side.statusKind !== "paused"
                    Layout.fillWidth: true
                    text: side.statusKind === "listening" ? "Speak, then let go."
                        : side.statusKind === "loading" ? side.status + (backend.loadProgress > 0 && backend.loadProgress < 1 ? " · " + Math.round(backend.loadProgress * 100) + " %" : "")
                        : side.status === "Speech model not downloaded" ? "Download it in Settings."
                        : side.status === "Model failed to load" ? "See Settings for what to do."
                        : side.status
                    textStyle: "footnote"
                    tone: "secondary"
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    Accessible.ignored: true
                }
                C.Button {
                    id: resume
                    visible: side.statusKind === "paused"
                    Layout.leftMargin: -8               // the plain button's padding: its label lines up
                    text: "Resume"
                    kind: "plain"
                    small: true
                    onClicked: side.resumeRequested()
                }
            }
        }
    }
}
